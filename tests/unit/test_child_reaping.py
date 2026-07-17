# ==============================================================================
# FILE        : tests/unit/test_child_reaping.py
# ==============================================================================
# Synopsis    : Unit tests for child process handles, reaping, and liveness
# Description : Every socat process launched by the framework is a direct child
#               of the management process. An exited child stays in the process
#               table as a zombie until its exit status is collected, and a
#               zombie still answers signal 0. These tests use real child
#               processes to prove that liveness reporting is truthful for an
#               exited-but-uncollected child, that collecting the status clears
#               the process table entry, and that handles do not accumulate.
# Version     : 1.0.1
# ==============================================================================

"""Unit tests for child process handles, reaping, and liveness."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from socat_manager.process import (
    _child_handles,
    _is_zombie,
    process_is_running,
    reap_child,
    register_child,
)


def _proc_state(pid: int) -> str:
    """Return the single-letter process state from /proc, or 'gone'."""
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.exists():
        return "gone"
    _, _, remainder = stat_path.read_text().rpartition(")")
    fields = remainder.split()
    return fields[0] if fields else "gone"


def _spawn_short_lived() -> subprocess.Popen:
    """Launch a child that exits almost immediately, in its own process group."""
    return subprocess.Popen(["sleep", "0.05"], preexec_fn=os.setsid)


def _spawn_long_lived() -> subprocess.Popen:
    """Launch a child that stays alive for the duration of a test."""
    return subprocess.Popen(["sleep", "30"], preexec_fn=os.setsid)


class TestZombieDetection:
    """Tests for _is_zombie()."""

    def test_exited_uncollected_child_is_a_zombie(self):
        """A child that has exited but not been collected is in state Z."""
        proc = _spawn_short_lived()
        pid = proc.pid
        time.sleep(0.4)  # The child has certainly exited by now.

        try:
            assert _proc_state(pid) == "Z"
            assert _is_zombie(pid) is True
        finally:
            proc.wait()

    def test_running_child_is_not_a_zombie(self):
        """A running child is not in the zombie state."""
        proc = _spawn_long_lived()
        try:
            assert _is_zombie(proc.pid) is False
        finally:
            proc.kill()
            proc.wait()

    def test_absent_pid_is_not_a_zombie(self):
        """A PID with no process table entry is not reported as a zombie."""
        assert _is_zombie(999_999) is False


class TestProcessIsRunning:
    """Tests for process_is_running()."""

    def test_running_child_reports_running(self):
        """A live registered child reports as running."""
        proc = _spawn_long_lived()
        register_child(proc)
        try:
            assert process_is_running(proc.pid) is True
        finally:
            proc.kill()
            proc.wait()
            _child_handles.pop(proc.pid, None)

    def test_exited_child_reports_not_running(self):
        """An exited child reports as not running.

        A zombie still answers signal 0, so a liveness check based on signal 0
        alone would report this process as alive indefinitely and any poll
        waiting for its death would never finish.
        """
        proc = _spawn_short_lived()
        pid = proc.pid
        register_child(proc)
        time.sleep(0.4)

        # Signal 0 still succeeds against the uncollected entry.
        os.kill(pid, 0)

        assert process_is_running(pid) is False

    def test_exited_unregistered_process_reports_not_running(self):
        """An exited child reports as dead even without a retained handle.

        The zombie check covers processes this instance did not launch, such as
        a session adopted from a previous invocation.
        """
        proc = _spawn_short_lived()
        pid = proc.pid
        time.sleep(0.4)

        try:
            assert _is_zombie(pid) is True
            assert process_is_running(pid) is False
        finally:
            proc.wait()

    def test_invalid_pid_reports_not_running(self):
        """A non-positive PID is never running."""
        assert process_is_running(0) is False
        assert process_is_running(-1) is False


class TestReapChild:
    """Tests for reap_child()."""

    def test_reaping_clears_the_process_table_entry(self):
        """Collecting the exit status removes the zombie."""
        proc = _spawn_short_lived()
        pid = proc.pid
        register_child(proc)
        time.sleep(0.4)

        assert _proc_state(pid) == "Z"

        reap_child(pid)

        assert _proc_state(pid) == "gone"

    def test_reaping_returns_the_exit_status(self):
        """The collected exit status is returned."""
        proc = subprocess.Popen(["sh", "-c", "exit 3"], preexec_fn=os.setsid)
        register_child(proc)
        time.sleep(0.3)

        assert reap_child(proc.pid) == 3

    def test_reaping_drops_the_handle(self):
        """A collected child leaves no handle behind, so the map cannot grow."""
        proc = _spawn_short_lived()
        pid = proc.pid
        register_child(proc)
        assert pid in _child_handles

        time.sleep(0.4)
        reap_child(pid)

        assert pid not in _child_handles

    def test_reaping_a_running_child_leaves_it_alone(self):
        """A child that is still running is not collected and keeps its handle."""
        proc = _spawn_long_lived()
        register_child(proc)
        try:
            assert reap_child(proc.pid) is None
            assert proc.pid in _child_handles
        finally:
            proc.kill()
            proc.wait()
            _child_handles.pop(proc.pid, None)

    def test_reaping_an_unknown_pid_is_a_no_op(self):
        """Collecting a PID this process never launched returns nothing."""
        assert reap_child(999_999) is None

    def test_liveness_check_collects_the_child(self):
        """Observing death through process_is_running() also collects the child.

        This is what keeps the watchdog's death poll from leaving a zombie
        behind on every restart.
        """
        proc = _spawn_short_lived()
        pid = proc.pid
        register_child(proc)
        time.sleep(0.4)

        assert process_is_running(pid) is False

        assert _proc_state(pid) == "gone"
        assert pid not in _child_handles


class TestWatchdogDeathDetection:
    """End-to-end check that the watchdog's death poll terminates."""

    def test_wait_for_pid_death_returns_for_an_exited_child(self, paths):
        """The death poll returns once the monitored child exits.

        The watchdog polls a child of this process. An exited child remains in
        the process table until collected, and a zombie answers signal 0, so a
        poll based on signal 0 alone would never observe the death and the
        watchdog would stop restarting after its first replacement. The poll
        must return, and it must leave no zombie behind.
        """
        from socat_manager.watchdog import _wait_for_pid_death

        proc = _spawn_short_lived()
        pid = proc.pid
        register_child(proc)

        start = time.monotonic()
        _wait_for_pid_death(pid, "deadbeef", paths)
        elapsed = time.monotonic() - start

        assert elapsed < 10, "death poll did not observe the exit"
        assert _proc_state(pid) == "gone", "monitored child was left as a zombie"

# ==============================================================================
# FILE        : tests/unit/test_stop_reaping.py
# ==============================================================================
# Synopsis    : Regression tests for stop-path child collection
# Description : When a single process both launches and stops a session — as the
#               interactive menu does — the socat process is a direct child of
#               that process. A child that has been killed remains in the
#               process table as a zombie until its exit status is collected,
#               and a zombie still answers signal 0. The stop sequence must
#               therefore evaluate liveness with the zombie-aware primitive and
#               collect the child, so that it reports the stop truthfully and
#               leaves no zombie or lingering handle behind. These tests use a
#               real child process to exercise that path.
# Version     : 1.0.1
# ==============================================================================

"""Regression tests for stop-path child collection."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import socat_manager.process as proc
from socat_manager.process import register_child, stop_session
from socat_manager.session import session_register


def _proc_state(pid: int) -> str:
    """Return the single-letter process state from /proc, or 'gone'."""
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.exists():
        return "gone"
    _, _, remainder = stat_path.read_text().rpartition(")")
    fields = remainder.split()
    return fields[0] if fields else "gone"


def _launch_in_process_child() -> int:
    """Launch a real child in its own process group and register its handle.

    This mirrors what launch_socat_session() does: the process is a direct
    child of this process and its Popen handle is retained.
    """
    child = subprocess.Popen(["sleep", "30"], preexec_fn=os.setsid)
    register_child(child)
    return child.pid


class TestStopReapsChild:
    """The stop sequence collects a child it terminates."""

    def test_stop_reports_success_for_a_killed_child(self, paths):
        """stop_session returns True when it has actually killed the process.

        A killed child becomes a zombie that still answers signal 0. A
        verification written against signal 0 alone would read the zombie as
        alive and report the stop as possibly incomplete. The zombie-aware
        verification must report the stop as successful.
        """
        pid = _launch_in_process_child()
        session_register(
            sid="deadbeef", name="stopme", pid=pid, pgid=pid,
            mode="listen", proto="tcp4", lport=0,  # lport 0 skips port checks
        )

        result = stop_session("deadbeef")

        assert result is True

    def test_stop_leaves_no_zombie(self, paths):
        """After stopping, the terminated child is collected, not left a zombie."""
        pid = _launch_in_process_child()
        session_register(
            sid="cafe1234", name="stopme", pid=pid, pgid=pid,
            mode="listen", proto="tcp4", lport=0,
        )

        stop_session("cafe1234")

        assert _proc_state(pid) == "gone"

    def test_stop_drops_the_child_handle(self, paths):
        """After stopping, the child's handle is removed from the registry."""
        pid = _launch_in_process_child()
        session_register(
            sid="beef5678", name="stopme", pid=pid, pgid=pid,
            mode="listen", proto="tcp4", lport=0,
        )

        stop_session("beef5678")

        assert pid not in proc._child_handles

    def test_stop_completes_promptly_when_process_dies(self, paths):
        """The grace loop ends when the process dies rather than waiting it out.

        A killed child that reads as a live zombie would keep the grace loop
        polling for the full stop_grace_seconds. With zombie-aware liveness the
        loop ends once the process is actually dead, so a clean stop does not
        consume the whole grace period.
        """
        pid = _launch_in_process_child()
        session_register(
            sid="fade9012", name="stopme", pid=pid, pgid=pid,
            mode="listen", proto="tcp4", lport=0,
        )

        start = time.monotonic()
        stop_session("fade9012")
        elapsed = time.monotonic() - start

        # A SIGTERMed sleep dies almost immediately; the stop must not burn the
        # full grace period (5s) polling a zombie.
        assert elapsed < 4.0

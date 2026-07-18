# ==============================================================================
# FILE        : tests/unit/test_child_registry_concurrency.py
# ==============================================================================
# Synopsis    : Concurrency tests for the child process handle registry
# Description : The registry in process.py is reached from more than one thread
#               at once — each watchdog runs on its own daemon thread while the
#               main thread services status and stop requests. These tests drive
#               register_child, reap_child, and process_is_running from many
#               threads concurrently and assert that the lock keeps the map
#               consistent: no update is lost, every terminated child is
#               collected, and no handle is left behind.
# Version     : 1.0.2
# ==============================================================================

"""Concurrency tests for the child process handle registry."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time

import socat_manager.process as proc
from socat_manager.process import process_is_running, reap_child, register_child


def _spawn_child() -> subprocess.Popen[bytes]:
    """Spawn a real, isolated child process for registry exercises."""
    return subprocess.Popen(["sleep", "30"], preexec_fn=os.setsid)


def _proc_gone(pid: int) -> bool:
    return not os.path.exists(f"/proc/{pid}")


class TestRegistryConcurrency:
    """The registry lock keeps concurrent access consistent."""

    def test_no_updates_lost_under_concurrent_registration(self):
        """Concurrent register_child calls all land — none overwrite another."""
        children = [_spawn_child() for _ in range(40)]
        try:
            barrier = threading.Barrier(len(children))
            errors: list[str] = []

            def do_register(handle: subprocess.Popen[bytes]) -> None:
                try:
                    barrier.wait()  # release all threads together for contention
                    register_child(handle)
                except Exception as exc:  # noqa: BLE001 - surfaced via assertion
                    errors.append(repr(exc))

            threads = [
                threading.Thread(target=do_register, args=(c,)) for c in children
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert errors == []
            for c in children:
                assert c.pid in proc._child_handles
        finally:
            for c in children:
                try:
                    os.kill(c.pid, signal.SIGKILL)
                except OSError:
                    pass
                reap_child(c.pid)
                try:
                    c.wait(timeout=1)
                except Exception:
                    pass

    def test_concurrent_register_and_reap_leaves_no_handle_or_zombie(self):
        """Each thread registers, kills, and collects its own child cleanly."""
        errors: list[str] = []
        pids: list[int] = []
        pids_lock = threading.Lock()

        def worker() -> None:
            try:
                child = _spawn_child()
                with pids_lock:
                    pids.append(child.pid)
                register_child(child)
                os.kill(child.pid, signal.SIGKILL)
                # Poll until observed dead; process_is_running reaps on the way.
                for _ in range(200):
                    if not process_is_running(child.pid):
                        break
                    time.sleep(0.01)
                reap_child(child.pid)
                if child.pid in proc._child_handles:
                    errors.append(f"handle leaked for {child.pid}")
                if not _proc_gone(child.pid):
                    errors.append(f"zombie left for {child.pid}")
            except Exception as exc:  # noqa: BLE001 - surfaced via assertion
                errors.append(repr(exc))

        threads = [threading.Thread(target=worker) for _ in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        # None of the children remain tracked.
        for pid in pids:
            assert pid not in proc._child_handles

    def test_reap_of_unknown_pid_is_safe_under_contention(self):
        """Concurrent reap_child of PIDs never registered returns None, no error."""
        errors: list[str] = []

        def worker(base: int) -> None:
            try:
                for offset in range(50):
                    # PIDs far outside any registered range; must be a clean no-op.
                    assert reap_child(-(base * 50 + offset + 1)) is None
            except Exception as exc:  # noqa: BLE001 - surfaced via assertion
                errors.append(repr(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

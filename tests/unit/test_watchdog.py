# ==============================================================================
# FILE        : tests/unit/test_watchdog.py
# ==============================================================================
# Synopsis    : Unit tests for the watchdog auto-restart monitor
# Description : Tests watchdog_loop() and start_watchdog() with the redesigned
#               API that MONITORS an existing PID first, then re-launches on
#               death. Verifies stop signal detection, max restarts, exponential
#               backoff, and configurable parameters.
# Version     : 1.0.1
# ==============================================================================

"""Unit tests for the watchdog auto-restart monitor."""

from __future__ import annotations

import threading
from unittest.mock import patch

from socat_manager.session import session_read_field, session_register
from socat_manager.watchdog import start_watchdog, watchdog_loop


class TestWatchdogLoop:
    """Tests for watchdog_loop() behavior."""

    @patch("socat_manager.watchdog.session_unregister")
    @patch("socat_manager.watchdog._launch_replacement", return_value=0)
    @patch("socat_manager.watchdog._wait_for_pid_death")
    def test_stop_signal_during_initial_monitor(self, mock_wait, mock_launch, mock_unreg, paths):
        """If .stop file exists when initial PID dies, watchdog should exit without restarting."""
        # Create .stop file so watchdog exits after initial PID death
        stop_file = paths.session_dir / "aabb1122.stop"
        stop_file.touch()

        watchdog_loop(
            session_id="aabb1122",
            session_name="test-watchdog",
            cmd=["socat", "TCP4-LISTEN:8080,reuseaddr,fork", "OPEN:/tmp/log,creat,append"],
            initial_pid=54321,
            max_restarts=5,
        )

        # Should monitor initial PID but never launch a replacement
        mock_wait.assert_called_once()
        mock_launch.assert_not_called()

    @patch("socat_manager.watchdog.session_unregister")
    @patch("socat_manager.watchdog.time.sleep")
    @patch("socat_manager.watchdog._launch_replacement")
    @patch("socat_manager.watchdog._wait_for_pid_death")
    def test_restart_updates_session_record(
        self, mock_wait, mock_launch, mock_sleep, mock_unreg, paths,
    ):
        """Each restart rewrites the session file with the replacement PID.

        The session file is the authoritative record of process identity. If it
        is not updated, liveness checks and the stop sequence act on the
        terminated predecessor while the replacement keeps holding the port.
        """
        session_register(
            sid="aabb1122", name="wd-update", pid=54321, pgid=54321,
            mode="listen", proto="tcp4", lport=8080,
        )

        mock_launch.side_effect = [10001, 10002]

        watchdog_loop(
            session_id="aabb1122",
            session_name="wd-update",
            cmd=["socat", "test"],
            initial_pid=54321,
            max_restarts=2,
        )

        # The record must name the final replacement, not the initial PID.
        session_file = paths.session_dir / "aabb1122.session"
        assert session_read_field(session_file, "PID") == "10002"
        assert session_read_field(session_file, "PGID") == "10002"

    @patch("socat_manager.watchdog.session_unregister")
    @patch("socat_manager.watchdog.time.sleep")
    @patch("socat_manager.watchdog.session_update_process")
    @patch("socat_manager.watchdog._launch_replacement")
    @patch("socat_manager.watchdog._wait_for_pid_death")
    def test_session_update_called_once_per_restart(
        self, mock_wait, mock_launch, mock_update, mock_sleep, mock_unreg, paths,
    ):
        """The session record is updated exactly once per successful restart."""
        mock_launch.side_effect = [10001, 10002, 10003]

        watchdog_loop(
            session_id="aabb1122",
            session_name="wd-update",
            cmd=["socat", "test"],
            initial_pid=54321,
            max_restarts=3,
        )

        assert mock_update.call_count == 3
        assert mock_update.call_args_list[0].kwargs == {"pid": 10001, "pgid": 10001}
        assert mock_update.call_args_list[2].kwargs == {"pid": 10003, "pgid": 10003}

    @patch("socat_manager.watchdog.session_unregister")
    @patch("socat_manager.watchdog.time.sleep")
    @patch("socat_manager.watchdog.session_update_process")
    @patch("socat_manager.watchdog._launch_replacement", return_value=0)
    @patch("socat_manager.watchdog._wait_for_pid_death")
    def test_failed_launch_does_not_update_session(
        self, mock_wait, mock_launch, mock_update, mock_sleep, mock_unreg, paths,
    ):
        """A failed replacement launch must not rewrite the session record."""
        watchdog_loop(
            session_id="aabb1122",
            session_name="wd-update",
            cmd=["socat", "test"],
            initial_pid=54321,
            max_restarts=3,
        )

        mock_update.assert_not_called()

    @patch("socat_manager.watchdog.session_unregister")
    @patch("socat_manager.watchdog.time.sleep")
    @patch("socat_manager.watchdog._launch_replacement")
    @patch("socat_manager.watchdog._wait_for_pid_death")
    def test_max_restarts_enforced(self, mock_wait, mock_launch, mock_sleep, mock_unreg, paths):
        """Watchdog should stop after max_restarts attempts."""
        # _launch_replacement returns a PID each time (simulates successful re-launch)
        mock_launch.side_effect = [10001, 10002, 10003]

        watchdog_loop(
            session_id="aabb1122",
            session_name="test",
            cmd=["socat", "test"],
            initial_pid=54321,
            max_restarts=3,
        )

        # Initial wait + 3 restart waits = 4 calls to _wait_for_pid_death
        assert mock_wait.call_count == 4
        # 3 re-launches
        assert mock_launch.call_count == 3
        mock_unreg.assert_called_once_with("aabb1122")

    @patch("socat_manager.watchdog.session_unregister")
    @patch("socat_manager.watchdog.time.sleep")
    @patch("socat_manager.watchdog._launch_replacement")
    @patch("socat_manager.watchdog._wait_for_pid_death")
    def test_exponential_backoff(self, mock_wait, mock_launch, mock_sleep, mock_unreg, paths):
        """Sleep intervals should follow exponential backoff: 1, 2, 4..."""
        mock_launch.side_effect = [10001, 10002, 10003]

        watchdog_loop(
            session_id="aabb1122",
            session_name="test",
            cmd=["socat", "test"],
            initial_pid=54321,
            max_restarts=3,
            backoff_initial=1,
        )

        # Extract sleep durations
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [1, 2, 4]

    @patch("socat_manager.watchdog.session_unregister")
    @patch("socat_manager.watchdog.time.sleep")
    @patch("socat_manager.watchdog._launch_replacement")
    @patch("socat_manager.watchdog._wait_for_pid_death")
    def test_backoff_caps_at_60(self, mock_wait, mock_launch, mock_sleep, mock_unreg, paths):
        """Backoff should cap at 60 seconds."""
        mock_launch.side_effect = list(range(10001, 10009))

        watchdog_loop(
            session_id="aabb1122",
            session_name="test",
            cmd=["socat", "test"],
            initial_pid=54321,
            max_restarts=8,
            backoff_initial=1,
        )

        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [1, 2, 4, 8, 16, 32, 60, 60]

    @patch("socat_manager.watchdog.session_unregister")
    @patch("socat_manager.watchdog.time.sleep")
    @patch("socat_manager.watchdog._launch_replacement")
    @patch("socat_manager.watchdog._wait_for_pid_death")
    def test_custom_backoff_initial(self, mock_wait, mock_launch, mock_sleep, mock_unreg, paths):
        """Custom backoff_initial should be respected."""
        mock_launch.side_effect = [10001, 10002]

        watchdog_loop(
            session_id="aabb1122",
            session_name="test",
            cmd=["socat", "test"],
            initial_pid=54321,
            max_restarts=2,
            backoff_initial=5,
        )

        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [5, 10]

    @patch("socat_manager.watchdog.session_unregister")
    @patch("socat_manager.watchdog.time.sleep")
    @patch("socat_manager.watchdog._launch_replacement", return_value=0)
    @patch("socat_manager.watchdog._wait_for_pid_death")
    def test_launch_failure_exits(self, mock_wait, mock_launch, mock_sleep, mock_unreg, paths):
        """If re-launch fails (returns 0), watchdog should exit."""
        watchdog_loop(
            session_id="aabb1122",
            session_name="test",
            cmd=["socat", "test"],
            initial_pid=54321,
            max_restarts=3,
        )

        # Initial wait, then one failed re-launch attempt
        assert mock_wait.call_count == 1  # Only initial monitor
        assert mock_launch.call_count == 1
        mock_unreg.assert_called_once()

    @patch("socat_manager.watchdog.session_unregister")
    @patch("socat_manager.watchdog.time.sleep")
    @patch("socat_manager.watchdog._launch_replacement")
    @patch("socat_manager.watchdog._wait_for_pid_death")
    def test_stop_signal_during_restart(self, mock_wait, mock_launch, mock_sleep, mock_unreg, paths):
        """If .stop file appears during restart backoff, watchdog should exit."""
        def create_stop_on_second_sleep(duration):
            """Create .stop file on second sleep call."""
            if mock_sleep.call_count >= 2:
                (paths.session_dir / "aabb1122.stop").touch()

        mock_launch.side_effect = [10001, 10002, 10003]
        mock_sleep.side_effect = create_stop_on_second_sleep

        watchdog_loop(
            session_id="aabb1122",
            session_name="test",
            cmd=["socat", "test"],
            initial_pid=54321,
            max_restarts=5,
        )

        # Should have stopped early due to .stop file
        assert mock_launch.call_count < 5


class TestStartWatchdog:
    """Tests for start_watchdog() thread launcher."""

    @patch("socat_manager.watchdog.watchdog_loop")
    def test_returns_daemon_thread(self, mock_loop):
        thread = start_watchdog(
            session_id="aabb1122",
            session_name="test",
            cmd=["socat", "test"],
            initial_pid=54321,
        )
        assert isinstance(thread, threading.Thread)
        assert thread.daemon is True
        assert thread.name == "watchdog-aabb1122"

    @patch("socat_manager.watchdog.watchdog_loop")
    def test_passes_correct_args(self, mock_loop):
        start_watchdog(
            session_id="aabb1122",
            session_name="test-session",
            cmd=["socat", "-v", "TCP4-LISTEN:8080"],
            initial_pid=54321,
            max_restarts=5,
            backoff_initial=3,
            stderr_redirect="/tmp/capture.log",
        )
        import time
        time.sleep(0.1)

        mock_loop.assert_called_once_with(
            "aabb1122", "test-session",
            ["socat", "-v", "TCP4-LISTEN:8080"],
            54321, 5, 3, "/tmp/capture.log",
        )

    @patch("socat_manager.watchdog.watchdog_loop")
    def test_default_params(self, mock_loop):
        start_watchdog(
            session_id="aabb1122",
            session_name="test",
            cmd=["socat", "test"],
            initial_pid=99999,
        )
        import time
        time.sleep(0.1)

        mock_loop.assert_called_once_with(
            "aabb1122", "test", ["socat", "test"],
            99999, 0, 1, "",
        )

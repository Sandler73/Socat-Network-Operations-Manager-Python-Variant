# ==============================================================================
# FILE        : tests/unit/test_process.py
# ==============================================================================
# Synopsis    : Unit tests for process management edge cases
# Description : Tests kill_by_port(), _is_socat_process(), _extract_pids_from_line(),
#               and check_port_freed() with mocked system calls.
# Version     : 1.0.2
# ==============================================================================

"""Unit tests for process management edge cases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from socat_manager.process import (
    _extract_pids_from_line,
    _is_socat_process,
    check_port_freed,
    kill_by_port,
)


class TestExtractPidsFromLine:
    """Tests for _extract_pids_from_line()."""

    def test_extracts_single_pid(self):
        pids: set[int] = set()
        _extract_pids_from_line('users:(("socat",pid=12345,fd=4))', pids)
        assert pids == {12345}

    def test_extracts_multiple_pids(self):
        pids: set[int] = set()
        _extract_pids_from_line('users:(("socat",pid=111,fd=4),("socat",pid=222,fd=5))', pids)
        assert pids == {111, 222}

    def test_no_pid_in_line(self):
        pids: set[int] = set()
        _extract_pids_from_line("LISTEN 0 128 *:8080 *:*", pids)
        assert pids == set()

    def test_empty_line(self):
        pids: set[int] = set()
        _extract_pids_from_line("", pids)
        assert pids == set()


class TestIsSocatProcess:
    """Tests for _is_socat_process()."""

    @patch("socat_manager.process.Path")
    def test_socat_process(self, mock_path_cls):
        mock_path = MagicMock()
        mock_path.read_text.return_value = "socat\n"
        mock_path_cls.return_value = mock_path
        assert _is_socat_process(12345) is True

    @patch("socat_manager.process.Path")
    def test_non_socat_process(self, mock_path_cls):
        mock_path = MagicMock()
        mock_path.read_text.return_value = "nginx\n"
        mock_path_cls.return_value = mock_path
        assert _is_socat_process(12345) is False

    @patch("socat_manager.process.Path")
    def test_proc_not_found(self, mock_path_cls):
        mock_path = MagicMock()
        mock_path.read_text.side_effect = OSError
        mock_path_cls.return_value = mock_path
        assert _is_socat_process(99999) is False


class TestKillByPort:
    """Tests for kill_by_port()."""

    @patch("socat_manager.process._is_socat_process", return_value=True)
    @patch("socat_manager.process.os.kill")
    @patch("socat_manager.process.subprocess.run")
    def test_kills_socat_processes(self, mock_run, mock_kill, mock_is_socat):
        """Should find and kill socat processes on the port."""
        import signal
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='LISTEN 0 128 *:8080 \tusers:(("socat",pid=12345,fd=4))\n',
        )
        kill_by_port(8080, "tcp4")
        mock_kill.assert_called_with(12345, signal.SIGKILL)

    @patch("socat_manager.process._is_socat_process", return_value=False)
    @patch("socat_manager.process.os.kill")
    @patch("socat_manager.process.subprocess.run")
    def test_does_not_kill_non_socat(self, mock_run, mock_kill, mock_is_socat):
        """Should NOT kill processes that aren't socat."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='LISTEN 0 128 *:8080 \tusers:(("nginx",pid=12345,fd=4))\n',
        )
        kill_by_port(8080, "tcp4")
        mock_kill.assert_not_called()

    @patch("socat_manager.process.subprocess.run")
    def test_tcp_query_is_transport_and_family_scoped(self, mock_run):
        """A tcp4 cleanup queries TCP listeners in the IPv4 family only."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        kill_by_port(8080, "tcp4")
        argv = mock_run.call_args_list[0].args[0]
        assert argv[0] == "ss"
        assert "-t" in argv
        assert "-4" in argv
        assert "-p" in argv
        assert "-u" not in argv
        assert "-6" not in argv

    @patch("socat_manager.process.subprocess.run")
    def test_udp_query_is_transport_and_family_scoped(self, mock_run):
        """A udp4 cleanup queries UDP listeners in the IPv4 family only."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        kill_by_port(5353, "udp4")
        argv = mock_run.call_args_list[0].args[0]
        assert argv[0] == "ss"
        assert "-u" in argv
        assert "-4" in argv
        assert "-p" in argv
        assert "-t" not in argv
        assert "-6" not in argv

    @patch("socat_manager.process.subprocess.run", side_effect=FileNotFoundError)
    def test_handles_missing_ss(self, mock_run):
        """Should handle ss not being available."""
        kill_by_port(8080, "tcp4")  # Should not raise


class TestCheckPortFreed:
    """Tests for check_port_freed()."""

    @patch("socat_manager.process.check_port_available", return_value=True)
    def test_port_freed_immediately(self, mock_avail):
        assert check_port_freed(8080, "tcp4", retries=3) is True
        assert mock_avail.call_count == 1  # No retry needed

    @patch("socat_manager.process.time.sleep")
    @patch("socat_manager.process.check_port_available", side_effect=[False, False, True])
    def test_port_freed_after_retries(self, mock_avail, mock_sleep):
        assert check_port_freed(8080, "tcp4", retries=3) is True
        assert mock_avail.call_count == 3

    @patch("socat_manager.process.time.sleep")
    @patch("socat_manager.process.check_port_available", return_value=False)
    def test_port_never_freed(self, mock_avail, mock_sleep):
        assert check_port_freed(8080, "tcp4", retries=3) is False
        assert mock_avail.call_count == 3

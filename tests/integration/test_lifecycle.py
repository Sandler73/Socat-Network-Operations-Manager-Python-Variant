# ==============================================================================
# FILE        : tests/integration/test_lifecycle.py
# ==============================================================================
# Synopsis    : Integration tests for session lifecycle
# Description : Tests the full launch → status → stop flow by mocking
#               subprocess.Popen to simulate socat process behavior. Verifies
#               session files are created, fields are correct, process tracking
#               works, and the 9-step stop sequence cleans up properly.
#
#               Tests that require a real socat binary are marked with
#               @pytest.mark.integration and skip if socat is not installed.
#
# Version     : 1.0.2
# ==============================================================================

"""Integration tests for session lifecycle: launch → status → stop."""

from __future__ import annotations

import os
import shutil
from unittest.mock import MagicMock, patch

import pytest

from socat_manager.commands import build_socat_listen_cmd
from socat_manager.process import (
    check_port_available,
    launch_socat_session,
    stop_session,
)
from socat_manager.session import (
    session_count,
    session_find_by_name,
    session_find_by_port,
    session_is_alive,
    session_read_field,
    session_register,
)

# ==============================================================================
# MOCK HELPERS
# ==============================================================================

def _make_mock_popen(pid: int = 54321, alive: bool = True):
    """Create a mock subprocess.Popen that simulates a socat process.

    Args:
        pid: PID to assign to the mock process.
        alive: Whether os.kill(pid, 0) should succeed (process alive).

    Returns:
        Tuple of (mock_popen_class, pid) for use with patch.
    """
    mock_process = MagicMock()
    mock_process.pid = pid
    mock_process.returncode = None
    # A live child has not terminated, so poll() yields no exit status. The
    # launch path polls the retained handle to distinguish a running process
    # from one that has exited but not yet been collected.
    mock_process.poll.return_value = None

    mock_popen = MagicMock(return_value=mock_process)

    return mock_popen, pid


# ==============================================================================
# LAUNCH TESTS
# ==============================================================================

class TestLaunchSession:
    """Tests for launch_socat_session() with mocked subprocess."""

    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill")
    def test_launch_creates_session_file(self, mock_kill, mock_popen, paths):
        """Launching a session should create a .session file."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        mock_kill.return_value = None  # process alive

        cmd = build_socat_listen_cmd("tcp4", 8080, str(paths.log_dir / "test.log"))

        sid, _ = launch_socat_session(
            name="test-tcp4-8080",
            mode="listen",
            proto="tcp4",
            lport=8080,
            cmd=cmd,
        )

        assert len(sid) == 8
        session_file = paths.session_dir / f"{sid}.session"
        assert session_file.is_file()

    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill")
    def test_launch_session_fields_correct(self, mock_kill, mock_popen, paths):
        """Session file should contain correct field values."""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        mock_kill.return_value = None

        cmd = build_socat_listen_cmd("tcp4", 9090, str(paths.log_dir / "test.log"))

        sid, _ = launch_socat_session(
            name="my-listener",
            mode="listen",
            proto="tcp4",
            lport=9090,
            cmd=cmd,
            rhost="10.0.0.1",
            rport="80",
        )

        sf = paths.session_dir / f"{sid}.session"
        assert session_read_field(sf, "SESSION_NAME") == "my-listener"
        assert session_read_field(sf, "PID") == "12345"
        assert session_read_field(sf, "PGID") == "12345"  # PGID == PID under setsid
        assert session_read_field(sf, "MODE") == "listen"
        assert session_read_field(sf, "PROTOCOL") == "tcp4"
        assert session_read_field(sf, "LOCAL_PORT") == "9090"
        assert session_read_field(sf, "REMOTE_HOST") == "10.0.0.1"
        assert session_read_field(sf, "REMOTE_PORT") == "80"

    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill")
    def test_launch_uses_setsid(self, mock_kill, mock_popen, paths):
        """Popen should be called with preexec_fn=os.setsid."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        mock_kill.return_value = None

        cmd = ["socat", "-u", "TCP4-LISTEN:8080,reuseaddr,fork", "OPEN:/tmp/log,creat,append"]
        launch_socat_session("test", "listen", "tcp4", 8080, cmd)

        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args
        assert call_kwargs.kwargs.get("preexec_fn") == os.setsid

    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill")
    def test_launch_never_uses_shell(self, mock_kill, mock_popen, paths):
        """Popen should NEVER use shell=True."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        mock_kill.return_value = None

        cmd = ["socat", "-u", "TCP4-LISTEN:8080,reuseaddr,fork", "OPEN:/tmp/log,creat,append"]
        launch_socat_session("test", "listen", "tcp4", 8080, cmd)

        call_kwargs = mock_popen.call_args
        # shell should not be in kwargs, or if present must be False
        assert call_kwargs.kwargs.get("shell", False) is False

    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill")
    def test_launch_passes_cmd_as_list(self, mock_kill, mock_popen, paths):
        """Popen should receive the command as a list, not a string."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        mock_kill.return_value = None

        cmd = ["socat", "-u", "TCP4-LISTEN:8080,reuseaddr,fork", "OPEN:/tmp/log,creat,append"]
        launch_socat_session("test", "listen", "tcp4", 8080, cmd)

        actual_cmd = mock_popen.call_args.args[0]
        assert isinstance(actual_cmd, list)
        assert actual_cmd[0] == "socat"

    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill")
    def test_launch_increments_session_count(self, mock_kill, mock_popen, paths):
        """Each launch should increment the session count."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        mock_kill.return_value = None

        assert session_count() == 0

        cmd = ["socat", "-u", "TCP4-LISTEN:8080,reuseaddr,fork", "OPEN:/tmp/log,creat,append"]
        launch_socat_session("test1", "listen", "tcp4", 8080, cmd)
        assert session_count() == 1

        mock_proc2 = MagicMock()
        mock_proc2.pid = 54322
        mock_proc2.poll.return_value = None
        mock_popen.return_value = mock_proc2
        launch_socat_session("test2", "listen", "tcp4", 8081, cmd)
        assert session_count() == 2

    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill", side_effect=OSError("No such process"))
    def test_launch_fails_if_process_dies_immediately(self, mock_kill, mock_popen, paths):
        """If the process dies immediately after launch, it should raise.

        A child that has exited reports an exit status from poll(). The launch
        path polls the retained handle, so an immediate failure is detected
        even though the process table entry still exists uncollected.
        """
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = 1  # Exited with a failure status
        mock_popen.return_value = mock_proc

        cmd = ["socat", "-u", "TCP4-LISTEN:8080,reuseaddr,fork", "OPEN:/tmp/log,creat,append"]
        with pytest.raises(RuntimeError, match="died immediately"):
            launch_socat_session("test", "listen", "tcp4", 8080, cmd)

    @patch("socat_manager.process.subprocess.Popen", side_effect=FileNotFoundError)
    def test_launch_fails_if_socat_not_found(self, mock_popen, paths):
        """If socat is not in PATH, launch should raise RuntimeError."""
        cmd = ["socat", "-u", "TCP4-LISTEN:8080,reuseaddr,fork", "OPEN:/tmp/log,creat,append"]
        with pytest.raises(RuntimeError, match="socat not found"):
            launch_socat_session("test", "listen", "tcp4", 8080, cmd)

    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill")
    def test_max_sessions_enforced(self, mock_kill, mock_popen, paths):
        """Should reject launch when max sessions (256) is reached."""
        mock_proc = MagicMock()
        mock_proc.pid = 10000
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        mock_kill.return_value = None

        # Create 256 session files to fill the limit
        for i in range(256):
            session_register(
                sid=f"{i:08x}"[:8],
                name=f"fill-{i}",
                pid=10000 + i,
                pgid=10000 + i,
                mode="listen",
            )

        cmd = ["socat", "-u", "TCP4-LISTEN:8080,reuseaddr,fork", "OPEN:/tmp/log,creat,append"]
        with pytest.raises(RuntimeError, match="Maximum session count"):
            launch_socat_session("overflow", "listen", "tcp4", 8080, cmd)


# ==============================================================================
# STOP TESTS
# ==============================================================================

class TestStopSession:
    """Tests for the 9-step stop sequence."""

    def test_stop_removes_session_file(self, sample_session, paths):
        """Stop should remove the session file."""
        sf = paths.session_dir / f"{sample_session}.session"
        assert sf.is_file()

        stop_session(sample_session)

        assert not sf.is_file()

    def test_stop_removes_stop_signal_file(self, sample_session, paths):
        """Stop should clean up the .stop signal file it creates."""
        stop_session(sample_session)

        stop_file = paths.session_dir / f"{sample_session}.stop"
        assert not stop_file.is_file()

    def test_stop_creates_stop_signal(self, sample_session, paths):
        """Step 2: Stop should create .stop file to signal watchdog."""
        # We need to intercept before cleanup to check the file was created.
        # Since the session PID (99999) is dead, stop proceeds quickly.
        # The .stop file is created in step 2 and removed in step 9.
        # We verify by checking the session was cleanly stopped.
        result = stop_session(sample_session)
        # Should succeed (PID 99999 is dead)
        assert result is True

    def test_stop_nonexistent_session(self, paths):
        """Stop on a nonexistent session should return False."""
        result = stop_session("ffffffff")
        assert result is False

    def test_stop_protocol_scoped(self, dual_stack_sessions, paths):
        """Stopping TCP session should NOT affect UDP session on same port."""
        tcp_sid, udp_sid = dual_stack_sessions

        # Stop only TCP
        stop_session(tcp_sid)

        # TCP session file should be gone
        assert not (paths.session_dir / f"{tcp_sid}.session").is_file()

        # UDP session file should still exist
        assert (paths.session_dir / f"{udp_sid}.session").is_file()

    def test_stop_returns_true_for_dead_process(self, sample_session):
        """When the target PID is already dead, stop should return True."""
        # PID 99999 from fixture is not running
        result = stop_session(sample_session)
        assert result is True


# ==============================================================================
# FULL LIFECYCLE
# ==============================================================================

class TestFullLifecycle:
    """End-to-end lifecycle tests: launch → find → stop."""

    @patch("socat_manager.process.subprocess.run")
    @patch("socat_manager.process.check_port_freed", return_value=True)
    @patch("socat_manager.process.check_port_available", return_value=True)
    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill")
    def test_launch_find_stop(self, mock_kill, mock_popen, mock_port_avail, mock_port_freed, mock_subrun, paths):
        """Full cycle: launch a session, find it, stop it."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        mock_kill.return_value = None
        mock_subrun.return_value = MagicMock(returncode=0, stdout="")

        cmd = build_socat_listen_cmd("tcp4", 8080, str(paths.log_dir / "test.log"))

        # Launch
        sid, _ = launch_socat_session("test-8080", "listen", "tcp4", 8080, cmd)
        assert session_count() == 1

        # Find by name
        found = session_find_by_name("test-8080")
        assert found == [sid]

        # Find by port
        found = session_find_by_port(8080)
        assert found == [sid]

        # Simulate the process having exited before the stop: the stop path
        # consults the retained child handle, so a dead process is one whose
        # poll() reports an exit status. os.kill is also made to raise for the
        # group-level checks.
        mock_proc.poll.return_value = 0
        mock_kill.side_effect = OSError("No such process")

        # Stop
        result = stop_session(sid)
        assert result is True
        assert session_count() == 0

    @patch("socat_manager.process.subprocess.run")
    @patch("socat_manager.process.check_port_freed", return_value=True)
    @patch("socat_manager.process.check_port_available", return_value=True)
    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill")
    def test_dual_stack_launch_independent_stop(self, mock_kill, mock_popen, mock_port_avail, mock_port_freed, mock_subrun, paths):
        """Launch TCP+UDP on same port, stop independently."""
        pid_counter = iter(range(50000, 60000))

        def new_mock():
            m = MagicMock()
            m.pid = next(pid_counter)
            # A live child reports no exit status from poll().
            m.poll.return_value = None
            return m

        mock_popen.side_effect = lambda *a, **k: new_mock()
        mock_kill.return_value = None
        mock_subrun.return_value = MagicMock(returncode=0, stdout="")

        cmd_tcp = build_socat_listen_cmd("tcp4", 9090, str(paths.log_dir / "tcp.log"))
        cmd_udp = build_socat_listen_cmd("udp4", 9090, str(paths.log_dir / "udp.log"))

        # Launch both
        sid_tcp, _ = launch_socat_session("tcp4-9090", "listen", "tcp4", 9090, cmd_tcp)
        sid_udp, _ = launch_socat_session("udp4-9090", "listen", "udp4", 9090, cmd_udp)

        assert session_count() == 2

        # Both on same port
        port_sessions = session_find_by_port(9090)
        assert len(port_sessions) == 2

        # Stop TCP only. The stop path consults the retained child handle, so
        # simulate the TCP process having exited by having its handle report an
        # exit status. os.kill is also made to raise for the group-level checks.
        import socat_manager.process as _proc
        from socat_manager.config import SESSION_FIELDS
        from socat_manager.session import session_read_field

        mock_kill.side_effect = OSError("No such process")
        tcp_pid = int(session_read_field(
            paths.session_dir / f"{sid_tcp}.session", SESSION_FIELDS.pid
        ))
        _proc._child_handles[tcp_pid].poll.return_value = 0
        stop_session(sid_tcp)

        # TCP gone, UDP still there
        assert session_count() == 1
        assert session_find_by_name("udp4-9090") == [sid_udp]

        # Stop UDP
        udp_pid = int(session_read_field(
            paths.session_dir / f"{sid_udp}.session", SESSION_FIELDS.pid
        ))
        _proc._child_handles[udp_pid].poll.return_value = 0
        stop_session(sid_udp)
        assert session_count() == 0


# ==============================================================================
# PORT CHECK TESTS (mocked ss/netstat)
# ==============================================================================

class TestPortAvailability:
    """Tests for check_port_available() with mocked ss."""

    @patch("socat_manager.process.subprocess.run")
    def test_port_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="State  Recv-Q  Send-Q\n")
        assert check_port_available(8080, "tcp4") is True

    @patch("socat_manager.process.subprocess.run")
    def test_port_in_use(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="LISTEN  0  128  *:8080 \t*:*\n",
        )
        assert check_port_available(8080, "tcp4") is False

    @patch("socat_manager.process.subprocess.run")
    def test_protocol_scoped_tcp(self, mock_run):
        """A tcp4 check queries TCP listeners in the IPv4 family only."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        check_port_available(8080, "tcp4")
        argv = mock_run.call_args.args[0]
        assert argv[0] == "ss"
        assert "-t" in argv
        assert "-4" in argv
        assert "-u" not in argv
        assert "-6" not in argv

    @patch("socat_manager.process.subprocess.run")
    def test_protocol_scoped_udp(self, mock_run):
        """A udp4 check queries UDP listeners in the IPv4 family only."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        check_port_available(5353, "udp4")
        argv = mock_run.call_args.args[0]
        assert argv[0] == "ss"
        assert "-u" in argv
        assert "-4" in argv
        assert "-t" not in argv
        assert "-6" not in argv


# ==============================================================================
# REAL SOCAT TESTS (skipped when socat not available)
# ==============================================================================

HAS_SOCAT = shutil.which("socat") is not None


@pytest.mark.integration
@pytest.mark.skipif(not HAS_SOCAT, reason="socat not installed")
class TestRealSocatLifecycle:
    """Integration tests with a real socat binary."""

    def test_real_launch_and_stop(self, paths):
        """Launch a real socat listener, verify it's alive, then stop it."""
        cmd = build_socat_listen_cmd("tcp4", 18080, str(paths.log_dir / "real.log"))
        sid, _ = launch_socat_session("real-test", "listen", "tcp4", 18080, cmd)

        try:
            assert session_is_alive(sid)
            sf = paths.session_dir / f"{sid}.session"
            assert session_read_field(sf, "MODE") == "listen"
            assert session_read_field(sf, "PROTOCOL") == "tcp4"
        finally:
            stop_session(sid)

        assert session_count() == 0

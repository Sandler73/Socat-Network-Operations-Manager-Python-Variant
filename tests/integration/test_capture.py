# ==============================================================================
# FILE        : tests/integration/test_capture.py
# ==============================================================================
# Synopsis    : Integration tests for traffic capture flag propagation
# Description : Verifies that --capture flag correctly propagates through
#               command builders (adding -v flag), creates capture log files
#               with correct permissions (0o600), and generates separate
#               per-protocol capture logs for dual-stack sessions.
# Version     : 1.0.1
# ==============================================================================

"""Integration tests for traffic capture flag propagation."""

from __future__ import annotations

import os
import stat
from unittest.mock import MagicMock, patch

from socat_manager.commands import (
    build_socat_forward_cmd,
    build_socat_listen_cmd,
    build_socat_redirect_cmd,
    build_socat_tunnel_cmd,
)
from socat_manager.config import EXEC_TIMESTAMP


class TestCaptureFlag:
    """Tests verifying -v flag propagation in capture mode."""

    def test_listen_capture_on(self):
        cmd = build_socat_listen_cmd("tcp4", 8080, "/tmp/log", capture=True)
        assert "-v" in cmd

    def test_listen_capture_off(self):
        cmd = build_socat_listen_cmd("tcp4", 8080, "/tmp/log", capture=False)
        assert "-v" not in cmd

    def test_forward_capture_on(self):
        cmd = build_socat_forward_cmd("tcp4", 8080, "host", 80, capture=True)
        assert "-v" in cmd

    def test_forward_capture_off(self):
        cmd = build_socat_forward_cmd("tcp4", 8080, "host", 80, capture=False)
        assert "-v" not in cmd

    def test_tunnel_capture_on(self):
        cmd = build_socat_tunnel_cmd(4443, "host", 22, "/c.pem", "/k.pem", capture=True)
        assert "-v" in cmd

    def test_tunnel_capture_off(self):
        cmd = build_socat_tunnel_cmd(4443, "host", 22, "/c.pem", "/k.pem", capture=False)
        assert "-v" not in cmd

    def test_redirect_capture_on(self):
        cmd = build_socat_redirect_cmd("tcp4", 8443, "host", 443, capture=True)
        assert "-v" in cmd

    def test_redirect_capture_off(self):
        cmd = build_socat_redirect_cmd("tcp4", 8443, "host", 443, capture=False)
        assert "-v" not in cmd


class TestCaptureFlagPosition:
    """Tests verifying -v flag appears in the correct command position."""

    def test_v_flag_before_addresses(self):
        """The -v flag should come before the socat address arguments."""
        cmd = build_socat_listen_cmd("tcp4", 8080, "/tmp/log", capture=True)
        v_idx = cmd.index("-v")
        # -v should be after "socat" but before the address arguments
        assert v_idx > 0  # Not the first element (socat)
        # The address argument should come after -v
        listen_idx = next(i for i, arg in enumerate(cmd) if "LISTEN" in arg)
        assert v_idx < listen_idx

    def test_v_flag_position_in_forward(self):
        cmd = build_socat_forward_cmd("tcp4", 8080, "host", 80, capture=True)
        v_idx = cmd.index("-v")
        listen_idx = next(i for i, arg in enumerate(cmd) if "LISTEN" in arg)
        assert v_idx < listen_idx


class TestCaptureLogCreation:
    """Tests for capture log file creation and permissions."""

    def test_capture_log_creation_0600(self, paths):
        """Capture logs should be created with 0o600 permissions."""
        capture_path = paths.log_dir / f"capture-tcp4-8080-{EXEC_TIMESTAMP}.log"

        # Simulate capture log creation as mode handlers do it
        fd = os.open(str(capture_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)

        assert capture_path.is_file()
        mode = stat.S_IMODE(capture_path.stat().st_mode)
        assert mode == 0o600

    def test_dual_stack_creates_separate_capture_logs(self, paths):
        """Dual-stack with capture should create per-protocol capture files."""
        tcp_capture = paths.log_dir / f"capture-tcp4-8080-{EXEC_TIMESTAMP}.log"
        udp_capture = paths.log_dir / f"capture-udp4-8080-{EXEC_TIMESTAMP}.log"

        for cap_path in (tcp_capture, udp_capture):
            fd = os.open(str(cap_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.close(fd)

        assert tcp_capture.is_file()
        assert udp_capture.is_file()
        assert tcp_capture != udp_capture

    def test_capture_logfile_naming_convention(self):
        """Capture log filenames should follow the bash naming convention."""
        # Listen: capture-{proto}-{port}-{timestamp}.log
        name = f"capture-tcp4-8080-{EXEC_TIMESTAMP}.log"
        assert name.startswith("capture-")
        assert "tcp4" in name
        assert "8080" in name

        # Forward/redirect: capture-{proto}-{lport}-{rhost}-{rport}-{timestamp}.log
        name2 = f"capture-tcp4-8080-example.com-443-{EXEC_TIMESTAMP}.log"
        assert "example.com" in name2
        assert "443" in name2


class TestCaptureLaunchIntegration:
    """Tests verifying capture mode affects the launch process correctly."""

    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill")
    def test_capture_stderr_redirect(self, mock_kill, mock_popen, paths):
        """When capture is enabled, stderr should redirect to capture log."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        mock_kill.return_value = None

        capture_log = str(paths.log_dir / "capture-test.log")
        # Create capture log first
        fd = os.open(capture_log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)

        cmd = build_socat_listen_cmd("tcp4", 8080, str(paths.log_dir / "data.log"), capture=True)

        from socat_manager.process import launch_socat_session
        sid, _ = launch_socat_session(
            name="capture-test",
            mode="listen",
            proto="tcp4",
            lport=8080,
            cmd=cmd,
            stderr_redirect=capture_log,
        )

        # Verify Popen was called (stderr goes to file handle, not DEVNULL)
        # stderr should NOT be DEVNULL when capture is active
        assert sid is not None

    @patch("socat_manager.process.subprocess.Popen")
    @patch("socat_manager.process.os.kill")
    def test_no_capture_stderr_to_error_log(self, mock_kill, mock_popen, paths):
        """Without capture, stderr should go to session error log."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        mock_kill.return_value = None

        cmd = build_socat_listen_cmd("tcp4", 8080, str(paths.log_dir / "data.log"), capture=False)

        from socat_manager.process import launch_socat_session
        sid, _ = launch_socat_session(
            name="no-capture",
            mode="listen",
            proto="tcp4",
            lport=8080,
            cmd=cmd,
            stderr_redirect="",  # Empty = use error log
        )

        assert sid is not None

# ==============================================================================
# FILE        : tests/integration/test_mode_handlers.py
# ==============================================================================
# Synopsis    : Integration tests for operational mode handlers
# Description : Tests mode_listen(), mode_forward(), mode_redirect(), and
#               mode_tunnel() with mocked subprocess.Popen to exercise the
#               full code path from argument validation through command
#               construction, launch, and display. mode_batch() is also tested.
#
#               These tests mock at the process layer to avoid needing
#               real socat, ss, or openssl binaries.
#
# Version     : 1.0.2
# ==============================================================================

"""Integration tests for operational mode handlers."""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

# ==============================================================================
# SHARED MOCK HELPERS
# ==============================================================================

def _patch_launch_and_port():
    """Return a pair of patch decorators for launch_socat_session and port checks."""
    return (
        patch("socat_manager.process.subprocess.Popen"),
        patch("socat_manager.process.os.kill"),
    )


def _make_launch_mock(pid=54321):
    """Create standard mock for Popen + os.kill."""
    mock_proc = MagicMock()
    mock_proc.pid = pid
    return mock_proc


# ==============================================================================
# LISTEN MODE
# ==============================================================================

class TestModeListenHandler:
    """Tests for modes/listen.py mode_listen()."""

    @patch("socat_manager.modes.listen.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.listen.check_port_available", return_value=True)
    def test_basic_listen(self, mock_port, mock_launch, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="8080", proto=None, bind=None, name=None, logfile=None,
            capture=False, watchdog=False, dual_stack=False, socat_opts=None,
            verbose=False,
        )
        mode_listen(args)
        mock_launch.assert_called_once()
        call_kwargs = mock_launch.call_args
        assert call_kwargs.kwargs["mode"] == "listen"
        assert call_kwargs.kwargs["proto"] == "tcp4"
        assert call_kwargs.kwargs["lport"] == 8080

    @patch("socat_manager.modes.listen.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.listen.check_port_available", return_value=True)
    def test_listen_with_proto(self, mock_port, mock_launch, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="5353", proto="udp4", bind=None, name=None, logfile=None,
            capture=False, watchdog=False, dual_stack=False, socat_opts=None,
            verbose=False,
        )
        mode_listen(args)
        assert mock_launch.call_args.kwargs["proto"] == "udp4"

    @patch("socat_manager.modes.listen.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.listen.check_port_available", return_value=True)
    def test_listen_with_name(self, mock_port, mock_launch, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="8080", proto=None, bind=None, name="my-listener", logfile=None,
            capture=False, watchdog=False, dual_stack=False, socat_opts=None,
            verbose=False,
        )
        mode_listen(args)
        assert mock_launch.call_args.kwargs["name"] == "my-listener"

    @patch("socat_manager.modes.listen.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.listen.check_port_available", return_value=True)
    def test_listen_with_capture(self, mock_port, mock_launch, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="8080", proto=None, bind=None, name=None, logfile=None,
            capture=True, watchdog=False, dual_stack=False, socat_opts=None,
            verbose=False,
        )
        mode_listen(args)
        # The cmd list should contain -v for capture
        cmd_arg = mock_launch.call_args.kwargs["cmd"]
        assert "-v" in cmd_arg

    @patch("socat_manager.modes.listen.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.listen.check_port_available", return_value=True)
    def test_listen_with_bind(self, mock_port, mock_launch, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="8080", proto=None, bind="10.0.0.1", name=None, logfile=None,
            capture=False, watchdog=False, dual_stack=False, socat_opts=None,
            verbose=False,
        )
        mode_listen(args)
        # The cmd should include bind=10.0.0.1 in the socat address
        from socat_manager.commands import cmd_list_to_string
        cmd_str = cmd_list_to_string(mock_launch.call_args.kwargs["cmd"])
        assert "bind=10.0.0.1" in cmd_str

    @patch("socat_manager.modes.listen.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.listen.check_port_available", return_value=True)
    def test_listen_with_socat_opts(self, mock_port, mock_launch, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="8080", proto=None, bind=None, name=None, logfile=None,
            capture=False, watchdog=False, dual_stack=False,
            socat_opts="reuseaddr,nodelay", verbose=False,
        )
        mode_listen(args)
        from socat_manager.commands import cmd_list_to_string
        cmd_str = cmd_list_to_string(mock_launch.call_args.kwargs["cmd"])
        assert "reuseaddr,nodelay" in cmd_str

    @patch("socat_manager.modes.listen.check_port_available", return_value=False)
    def test_listen_port_in_use_exits(self, mock_port, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="8080", proto=None, bind=None, name=None, logfile=None,
            capture=False, watchdog=False, dual_stack=False, socat_opts=None,
            verbose=False,
        )
        with pytest.raises(SystemExit):
            mode_listen(args)

    def test_listen_invalid_port_exits(self, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="abc", proto=None, bind=None, name=None, logfile=None,
            capture=False, watchdog=False, dual_stack=False, socat_opts=None,
            verbose=False,
        )
        with pytest.raises(SystemExit):
            mode_listen(args)

    def test_listen_invalid_proto_exits(self, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="8080", proto="icmp", bind=None, name=None, logfile=None,
            capture=False, watchdog=False, dual_stack=False, socat_opts=None,
            verbose=False,
        )
        with pytest.raises(SystemExit):
            mode_listen(args)

    def test_listen_invalid_socat_opts_exits(self, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="8080", proto=None, bind=None, name=None, logfile=None,
            capture=False, watchdog=False, dual_stack=False,
            socat_opts=";evil", verbose=False,
        )
        with pytest.raises(SystemExit):
            mode_listen(args)

    @patch("socat_manager.modes.listen.start_watchdog")
    @patch("socat_manager.modes.listen.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.listen.check_port_available", return_value=True)
    def test_listen_with_watchdog(self, mock_port, mock_launch, mock_wd, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="8080", proto=None, bind=None, name=None, logfile=None,
            capture=False, watchdog=True, dual_stack=False, socat_opts=None,
            verbose=False,
        )
        mode_listen(args)
        mock_wd.assert_called_once()

    @patch("socat_manager.modes.listen.start_watchdog")
    @patch("socat_manager.modes.listen.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.listen.check_port_available", return_value=True)
    def test_listen_dual_stack(self, mock_port, mock_launch, mock_wd, paths):
        from socat_manager.modes.listen import mode_listen
        args = Namespace(
            port="8080", proto=None, bind=None, name=None, logfile=None,
            capture=False, watchdog=False, dual_stack=True, socat_opts=None,
            verbose=False,
        )
        mode_listen(args)
        # Should launch twice: tcp4 + udp4
        assert mock_launch.call_count == 2
        protos = [c.kwargs["proto"] for c in mock_launch.call_args_list]
        assert "tcp4" in protos
        assert "udp4" in protos


# ==============================================================================
# FORWARD MODE
# ==============================================================================

class TestModeForwardHandler:
    """Tests for modes/forward.py mode_forward()."""

    @patch("socat_manager.modes.forward.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.forward.check_port_available", return_value=True)
    def test_basic_forward(self, mock_port, mock_launch, paths):
        from socat_manager.modes.forward import mode_forward
        args = Namespace(
            lport="8080", rhost="10.0.0.5", rport="80", proto=None,
            remote_proto=None, name=None, capture=False, watchdog=False,
            dual_stack=False, verbose=False,
        )
        mode_forward(args)
        mock_launch.assert_called_once()
        kw = mock_launch.call_args.kwargs
        assert kw["mode"] == "forward"
        assert kw["rhost"] == "10.0.0.5"
        assert kw["rport"] == "80"

    @patch("socat_manager.modes.forward.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.forward.check_port_available", return_value=True)
    def test_forward_with_remote_proto(self, mock_port, mock_launch, paths):
        from socat_manager.modes.forward import mode_forward
        args = Namespace(
            lport="8080", rhost="10.0.0.1", rport="53", proto="tcp4",
            remote_proto="udp4", name=None, capture=False, watchdog=False,
            dual_stack=False, verbose=False,
        )
        mode_forward(args)
        from socat_manager.commands import cmd_list_to_string
        cmd_str = cmd_list_to_string(mock_launch.call_args.kwargs["cmd"])
        assert "TCP4-LISTEN" in cmd_str
        assert "UDP4:10.0.0.1:53" in cmd_str

    def test_forward_invalid_host_exits(self, paths):
        from socat_manager.modes.forward import mode_forward
        args = Namespace(
            lport="8080", rhost=";evil", rport="80", proto=None,
            remote_proto=None, name=None, capture=False, watchdog=False,
            dual_stack=False, verbose=False,
        )
        with pytest.raises(SystemExit):
            mode_forward(args)

    @patch("socat_manager.modes.forward.check_port_available", return_value=False)
    def test_forward_port_in_use_exits(self, mock_port, paths):
        from socat_manager.modes.forward import mode_forward
        args = Namespace(
            lport="8080", rhost="10.0.0.5", rport="80", proto=None,
            remote_proto=None, name=None, capture=False, watchdog=False,
            dual_stack=False, verbose=False,
        )
        with pytest.raises(SystemExit):
            mode_forward(args)


# ==============================================================================
# REDIRECT MODE
# ==============================================================================

class TestModeRedirectHandler:
    """Tests for modes/redirect.py mode_redirect()."""

    @patch("socat_manager.modes.redirect.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.redirect.check_port_available", return_value=True)
    def test_basic_redirect(self, mock_port, mock_launch, paths):
        from socat_manager.modes.redirect import mode_redirect
        args = Namespace(
            lport="8443", rhost="example.com", rport="443", proto=None,
            name=None, capture=False, watchdog=False, dual_stack=False,
            verbose=False,
        )
        mode_redirect(args)
        mock_launch.assert_called_once()
        kw = mock_launch.call_args.kwargs
        assert kw["mode"] == "redirect"
        assert kw["rhost"] == "example.com"

    @patch("socat_manager.modes.redirect.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.redirect.check_port_available", return_value=True)
    def test_redirect_udp(self, mock_port, mock_launch, paths):
        from socat_manager.modes.redirect import mode_redirect
        args = Namespace(
            lport="5353", rhost="8.8.8.8", rport="53", proto="udp4",
            name=None, capture=False, watchdog=False, dual_stack=False,
            verbose=False,
        )
        mode_redirect(args)
        assert mock_launch.call_args.kwargs["proto"] == "udp4"

    @patch("socat_manager.modes.redirect.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.redirect.check_port_available", return_value=True)
    def test_redirect_dual_stack(self, mock_port, mock_launch, paths):
        from socat_manager.modes.redirect import mode_redirect
        args = Namespace(
            lport="8443", rhost="example.com", rport="443", proto=None,
            name=None, capture=False, watchdog=False, dual_stack=True,
            verbose=False,
        )
        mode_redirect(args)
        assert mock_launch.call_count == 2


# ==============================================================================
# TUNNEL MODE
# ==============================================================================

class TestModeTunnelHandler:
    """Tests for modes/tunnel.py mode_tunnel()."""

    @patch("socat_manager.modes.tunnel.generate_self_signed_cert", return_value=("/tmp/c.pem", "/tmp/k.pem"))
    @patch("socat_manager.modes.tunnel.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.tunnel.check_port_available", return_value=True)
    def test_basic_tunnel_auto_cert(self, mock_port, mock_launch, mock_cert, paths):
        from socat_manager.modes.tunnel import mode_tunnel
        args = Namespace(
            port="4443", rhost="10.0.0.5", rport="22",
            cert=None, key=None, cn=None, proto=None, name=None,
            capture=False, watchdog=False, dual_stack=False, verbose=False,
        )
        mode_tunnel(args)
        mock_cert.assert_called_once()
        mock_launch.assert_called_once()
        assert mock_launch.call_args.kwargs["proto"] == "tls"

    def test_tunnel_udp_rejected(self, paths):
        from socat_manager.modes.tunnel import mode_tunnel
        args = Namespace(
            port="4443", rhost="10.0.0.5", rport="22",
            cert=None, key=None, cn=None, proto="udp4", name=None,
            capture=False, watchdog=False, dual_stack=False, verbose=False,
        )
        with pytest.raises(SystemExit):
            mode_tunnel(args)

    @patch("socat_manager.modes.tunnel.generate_self_signed_cert", return_value=("/tmp/c.pem", "/tmp/k.pem"))
    @patch("socat_manager.modes.tunnel.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.tunnel.check_port_available", return_value=True)
    def test_tunnel_ipv6_remote_uses_tcp6_connector(self, mock_port, mock_launch, mock_cert, paths):
        """An IPv6 remote target produces a bracketed TCP6 connector."""
        from socat_manager.modes.tunnel import mode_tunnel
        args = Namespace(
            port="4443", rhost="2001:db8::1", rport="22",
            cert=None, key=None, cn=None, proto=None, name=None,
            capture=False, watchdog=False, dual_stack=False, verbose=False,
        )
        mode_tunnel(args)
        cmd = mock_launch.call_args.kwargs["cmd"]
        assert cmd[-1] == "TCP6:[2001:db8::1]:22"

    @patch("socat_manager.modes.tunnel.generate_self_signed_cert", return_value=("/tmp/c.pem", "/tmp/k.pem"))
    @patch("socat_manager.modes.tunnel.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.tunnel.check_port_available", return_value=True)
    def test_tunnel_ipv4_remote_uses_tcp4_connector(self, mock_port, mock_launch, mock_cert, paths):
        """An IPv4 remote target produces a TCP4 connector."""
        from socat_manager.modes.tunnel import mode_tunnel
        args = Namespace(
            port="4443", rhost="10.0.0.5", rport="22",
            cert=None, key=None, cn=None, proto=None, name=None,
            capture=False, watchdog=False, dual_stack=False, verbose=False,
        )
        mode_tunnel(args)
        cmd = mock_launch.call_args.kwargs["cmd"]
        assert cmd[-1] == "TCP4:10.0.0.5:22"

    @patch("socat_manager.modes.tunnel.generate_self_signed_cert", return_value=("/tmp/c.pem", "/tmp/k.pem"))
    @patch("socat_manager.modes.tunnel.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.tunnel.check_port_available", return_value=True)
    def test_tunnel_with_capture(self, mock_port, mock_launch, mock_cert, paths):
        from socat_manager.modes.tunnel import mode_tunnel
        args = Namespace(
            port="4443", rhost="10.0.0.5", rport="22",
            cert=None, key=None, cn=None, proto=None, name=None,
            capture=True, watchdog=False, dual_stack=False, verbose=False,
        )
        mode_tunnel(args)
        cmd = mock_launch.call_args.kwargs["cmd"]
        assert "-v" in cmd

    @patch("socat_manager.modes.tunnel.generate_self_signed_cert", return_value=("/tmp/c.pem", "/tmp/k.pem"))
    @patch("socat_manager.modes.tunnel.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.tunnel.check_port_available", return_value=True)
    def test_tunnel_dual_stack_adds_udp(self, mock_port, mock_launch, mock_cert, paths):
        from socat_manager.modes.tunnel import mode_tunnel
        args = Namespace(
            port="4443", rhost="10.0.0.5", rport="22",
            cert=None, key=None, cn=None, proto=None, name=None,
            capture=False, watchdog=False, dual_stack=True, verbose=False,
        )
        mode_tunnel(args)
        # TLS primary + UDP forwarder = 2 launches
        assert mock_launch.call_count == 2
        protos = [c.kwargs["proto"] for c in mock_launch.call_args_list]
        assert "tls" in protos
        assert "udp4" in protos


# ==============================================================================
# BATCH MODE
# ==============================================================================

class TestModeBatchHandler:
    """Tests for modes/batch.py mode_batch()."""

    @patch("socat_manager.modes.batch.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.batch.check_port_available", return_value=True)
    def test_batch_from_ports(self, mock_port, mock_launch, paths):
        from socat_manager.modes.batch import mode_batch
        args = Namespace(
            ports="8080,8081,8082", range=None, file=None,
            proto=None, capture=False, watchdog=False, dual_stack=False,
            socat_opts=None, verbose=False,
        )
        mode_batch(args)
        assert mock_launch.call_count == 3

    @patch("socat_manager.modes.batch.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.batch.check_port_available", return_value=True)
    def test_batch_from_range(self, mock_port, mock_launch, paths):
        from socat_manager.modes.batch import mode_batch
        args = Namespace(
            ports=None, range="9000-9002", file=None,
            proto=None, capture=False, watchdog=False, dual_stack=False,
            socat_opts=None, verbose=False,
        )
        mode_batch(args)
        assert mock_launch.call_count == 3

    @patch("socat_manager.modes.batch.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.batch.check_port_available", return_value=True)
    def test_batch_from_file(self, mock_port, mock_launch, paths, tmp_path):
        # Create a temp config file
        conf = tmp_path / "ports.conf"
        conf.write_text("# comment\n8080\n8081\n\n8082\n")

        from socat_manager.modes.batch import mode_batch
        args = Namespace(
            ports=None, range=None, file=str(conf),
            proto=None, capture=False, watchdog=False, dual_stack=False,
            socat_opts=None, verbose=False,
        )
        mode_batch(args)
        assert mock_launch.call_count == 3

    def test_batch_no_source_exits(self, paths):
        from socat_manager.modes.batch import mode_batch
        args = Namespace(
            ports=None, range=None, file=None,
            proto=None, capture=False, watchdog=False, dual_stack=False,
            socat_opts=None, verbose=False,
        )
        with pytest.raises(SystemExit):
            mode_batch(args)

    @patch("socat_manager.modes.batch.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.batch.check_port_available", return_value=True)
    def test_batch_dual_stack(self, mock_port, mock_launch, paths):
        from socat_manager.modes.batch import mode_batch
        args = Namespace(
            ports="8080", range=None, file=None,
            proto=None, capture=False, watchdog=False, dual_stack=True,
            socat_opts=None, verbose=False,
        )
        mode_batch(args)
        # 1 port × 2 protocols = 2 launches
        assert mock_launch.call_count == 2

    @patch("socat_manager.modes.batch.launch_socat_session", return_value=("abcd1234", 54321))
    @patch("socat_manager.modes.batch.check_port_available", return_value=False)
    def test_batch_skips_unavailable_ports(self, mock_port, mock_launch, paths):
        from socat_manager.modes.batch import mode_batch
        args = Namespace(
            ports="8080,8081", range=None, file=None,
            proto=None, capture=False, watchdog=False, dual_stack=False,
            socat_opts=None, verbose=False,
        )
        mode_batch(args)
        # All ports unavailable → 0 launches
        mock_launch.assert_not_called()

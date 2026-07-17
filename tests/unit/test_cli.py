# ==============================================================================
# FILE        : tests/unit/test_cli.py
# ==============================================================================
# Synopsis    : Unit tests for CLI argument parser
# Description : Exercises all argparse subcommand configurations, flag parsing,
#               defaults, and error handling to achieve coverage on cli.py.
# Version     : 1.0.1
# ==============================================================================

"""Unit tests for CLI argument parser."""

import pytest

from socat_manager.cli import build_parser


class TestBuildParser:
    """Tests for build_parser() construction."""

    def test_returns_parser(self):
        parser = build_parser()
        assert parser is not None
        assert parser.prog == "socat-manager"

    def test_all_subcommands_present(self):
        parser = build_parser()
        # Access the subparsers action
        subparsers_actions = [
            a for a in parser._subparsers._group_actions
            if hasattr(a, "choices")
        ]
        assert len(subparsers_actions) == 1
        choices = list(subparsers_actions[0].choices.keys())
        expected = ["listen", "batch", "forward", "tunnel", "redirect", "status", "stop", "menu"]
        for mode in expected:
            assert mode in choices, f"Missing subcommand: {mode}"

    def test_version_flag(self):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0


class TestListenParser:
    """Tests for listen subcommand parser."""

    def test_port_required(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["listen"])

    def test_port_short_flag(self):
        args = build_parser().parse_args(["listen", "-p", "8080"])
        assert args.port == "8080"

    def test_port_long_flag(self):
        args = build_parser().parse_args(["listen", "--port", "8080"])
        assert args.port == "8080"

    def test_all_optional_flags(self):
        args = build_parser().parse_args([
            "listen", "--port", "8080",
            "--proto", "udp4",
            "--bind", "10.0.0.1",
            "--name", "test-session",
            "--logfile", "/tmp/test.log",
            "--capture",
            "--watchdog",
            "--dual-stack",
            "--socat-opts", "reuseaddr",
            "-v",
        ])
        assert args.proto == "udp4"
        assert args.bind == "10.0.0.1"
        assert args.name == "test-session"
        assert args.logfile == "/tmp/test.log"
        assert args.capture is True
        assert args.watchdog is True
        assert args.dual_stack is True
        assert args.socat_opts == "reuseaddr"
        assert args.verbose is True

    def test_defaults(self):
        args = build_parser().parse_args(["listen", "--port", "8080"])
        assert args.proto is None
        assert args.bind is None
        assert args.name is None
        assert args.logfile is None
        assert args.capture is False
        assert args.watchdog is False
        assert args.dual_stack is False
        assert args.socat_opts is None
        assert args.verbose is False


class TestBatchParser:
    """Tests for batch subcommand parser."""

    def test_ports_flag(self):
        args = build_parser().parse_args(["batch", "--ports", "21,22,80"])
        assert args.ports == "21,22,80"

    def test_range_flag(self):
        args = build_parser().parse_args(["batch", "--range", "8000-8010"])
        assert args.range == "8000-8010"

    def test_file_flag(self):
        args = build_parser().parse_args(["batch", "--file", "ports.conf"])
        assert args.file == "ports.conf"

    def test_batch_optional_flags(self):
        args = build_parser().parse_args([
            "batch", "--ports", "80",
            "--proto", "tcp6",
            "--capture",
            "--watchdog",
            "--dual-stack",
            "--socat-opts", "fork",
            "-v",
        ])
        assert args.proto == "tcp6"
        assert args.capture is True
        assert args.watchdog is True
        assert args.dual_stack is True
        assert args.socat_opts == "fork"
        assert args.verbose is True


class TestForwardParser:
    """Tests for forward subcommand parser."""

    def test_required_flags(self):
        args = build_parser().parse_args([
            "forward", "--lport", "8080", "--rhost", "10.0.0.5", "--rport", "80",
        ])
        assert args.lport == "8080"
        assert args.rhost == "10.0.0.5"
        assert args.rport == "80"

    def test_missing_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["forward", "--lport", "8080"])

    def test_remote_proto(self):
        args = build_parser().parse_args([
            "forward", "--lport", "8080", "--rhost", "h", "--rport", "80",
            "--remote-proto", "udp4",
        ])
        assert args.remote_proto == "udp4"


class TestTunnelParser:
    """Tests for tunnel subcommand parser."""

    def test_required_flags(self):
        args = build_parser().parse_args([
            "tunnel", "--port", "4443", "--rhost", "10.0.0.5", "--rport", "22",
        ])
        assert args.port == "4443"
        assert args.rhost == "10.0.0.5"
        assert args.rport == "22"

    def test_cert_and_key(self):
        args = build_parser().parse_args([
            "tunnel", "-p", "4443", "--rhost", "h", "--rport", "22",
            "--cert", "/tmp/c.pem", "--key", "/tmp/k.pem",
        ])
        assert args.cert == "/tmp/c.pem"
        assert args.key == "/tmp/k.pem"

    def test_cn_flag(self):
        args = build_parser().parse_args([
            "tunnel", "-p", "4443", "--rhost", "h", "--rport", "22",
            "--cn", "myserver.local",
        ])
        assert args.cn == "myserver.local"


class TestRedirectParser:
    """Tests for redirect subcommand parser."""

    def test_required_flags(self):
        args = build_parser().parse_args([
            "redirect", "--lport", "8443", "--rhost", "example.com", "--rport", "443",
        ])
        assert args.lport == "8443"
        assert args.rhost == "example.com"
        assert args.rport == "443"


class TestStatusParser:
    """Tests for status subcommand parser."""

    def test_no_args(self):
        args = build_parser().parse_args(["status"])
        assert args.target is None
        assert args.cleanup is False
        assert args.verbose is False

    def test_positional_target(self):
        args = build_parser().parse_args(["status", "abcd1234"])
        assert args.target == "abcd1234"

    def test_cleanup_flag(self):
        args = build_parser().parse_args(["status", "--cleanup"])
        assert args.cleanup is True

    def test_verbose_flag(self):
        args = build_parser().parse_args(["status", "-v"])
        assert args.verbose is True


class TestStopParser:
    """Tests for stop subcommand parser."""

    def test_positional_target(self):
        args = build_parser().parse_args(["stop", "abcd1234"])
        assert args.target == "abcd1234"

    def test_all_flag(self):
        args = build_parser().parse_args(["stop", "--all"])
        assert args.all is True

    def test_name_flag(self):
        args = build_parser().parse_args(["stop", "--name", "tcp4-8080"])
        assert args.name == "tcp4-8080"

    def test_port_flag(self):
        args = build_parser().parse_args(["stop", "--port", "8080"])
        assert args.port == "8080"

    def test_pid_flag(self):
        args = build_parser().parse_args(["stop", "--pid", "12345"])
        assert args.pid == "12345"

    def test_verbose_flag(self):
        args = build_parser().parse_args(["stop", "-v"])
        assert args.verbose is True


class TestMenuParser:
    """Tests for menu subcommand parser."""

    def test_menu_mode(self):
        args = build_parser().parse_args(["menu"])
        assert args.mode == "menu"

    def test_no_args_gives_none_mode(self):
        args = build_parser().parse_args([])
        assert args.mode is None


class TestHelpAndVersionParsers:
    """Tests for help and version positional commands."""

    def test_help_mode(self):
        args = build_parser().parse_args(["help"])
        assert args.mode == "help"

    def test_version_mode(self):
        args = build_parser().parse_args(["version"])
        assert args.mode == "version"


class TestWatchdogFlags:
    """Tests for --max-restarts and --backoff on all mode parsers."""

    def test_listen_max_restarts(self):
        args = build_parser().parse_args(["listen", "-p", "8080", "--watchdog", "--max-restarts", "5"])
        assert args.max_restarts == 5

    def test_listen_backoff(self):
        args = build_parser().parse_args(["listen", "-p", "8080", "--watchdog", "--backoff", "3"])
        assert args.backoff == 3

    def test_listen_defaults_none(self):
        args = build_parser().parse_args(["listen", "-p", "8080"])
        assert args.max_restarts is None
        assert args.backoff is None

    def test_batch_max_restarts(self):
        args = build_parser().parse_args(["batch", "--ports", "80", "--max-restarts", "20"])
        assert args.max_restarts == 20

    def test_forward_backoff(self):
        args = build_parser().parse_args([
            "forward", "--lport", "8080", "--rhost", "h", "--rport", "80", "--backoff", "5",
        ])
        assert args.backoff == 5

    def test_tunnel_max_restarts(self):
        args = build_parser().parse_args([
            "tunnel", "-p", "4443", "--rhost", "h", "--rport", "22", "--max-restarts", "15",
        ])
        assert args.max_restarts == 15

    def test_redirect_both_flags(self):
        args = build_parser().parse_args([
            "redirect", "--lport", "8443", "--rhost", "h", "--rport", "443",
            "--max-restarts", "3", "--backoff", "10",
        ])
        assert args.max_restarts == 3
        assert args.backoff == 10

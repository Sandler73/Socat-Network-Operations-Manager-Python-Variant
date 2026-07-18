# ==============================================================================
# FILE        : tests/unit/test_commands.py
# ==============================================================================
# Synopsis    : Unit tests for socat command string builders
# Description : Verifies each command builder produces output matching the bash
#               version exactly. Covers all protocol variants, capture mode,
#               extra options, and cross-protocol forwarding.
# Version     : 1.0.2
# ==============================================================================

"""Unit tests for socat command string builders."""


from socat_manager.commands import (
    build_socat_forward_cmd,
    build_socat_listen_cmd,
    build_socat_redirect_cmd,
    build_socat_tunnel_cmd,
    cmd_list_to_string,
)


class TestBuildSocatListenCmd:
    """Tests for build_socat_listen_cmd()."""

    def test_tcp4_basic(self):
        cmd = build_socat_listen_cmd("tcp4", 8080, "/tmp/log.txt")
        s = cmd_list_to_string(cmd)
        assert s == "socat -u TCP4-LISTEN:8080,reuseaddr,fork,backlog=128,keepalive OPEN:/tmp/log.txt,creat,append"

    def test_tcp6(self):
        cmd = build_socat_listen_cmd("tcp6", 8080, "/tmp/log.txt")
        assert "TCP6-LISTEN:8080" in cmd_list_to_string(cmd)

    def test_udp4_no_backlog_no_keepalive(self):
        cmd = build_socat_listen_cmd("udp4", 5353, "/tmp/log.txt")
        s = cmd_list_to_string(cmd)
        assert "UDP4-LISTEN:5353,reuseaddr,fork" in s
        assert "backlog" not in s
        assert "keepalive" not in s

    def test_udp6(self):
        cmd = build_socat_listen_cmd("udp6", 5353, "/tmp/log.txt")
        assert "UDP6-LISTEN:5353" in cmd_list_to_string(cmd)

    def test_capture_mode_adds_v(self):
        cmd = build_socat_listen_cmd("tcp4", 8080, "/tmp/log.txt", capture=True)
        assert "-v" in cmd

    def test_no_capture_no_v(self):
        cmd = build_socat_listen_cmd("tcp4", 8080, "/tmp/log.txt", capture=False)
        assert "-v" not in cmd

    def test_extra_opts_appended(self):
        cmd = build_socat_listen_cmd("tcp4", 8080, "/tmp/log.txt", "bind=10.0.0.1")
        s = cmd_list_to_string(cmd)
        assert "backlog=128,keepalive,bind=10.0.0.1" in s

    def test_unidirectional_flag(self):
        cmd = build_socat_listen_cmd("tcp4", 8080, "/tmp/log.txt")
        assert "-u" in cmd

    def test_returns_list(self):
        cmd = build_socat_listen_cmd("tcp4", 8080, "/tmp/log.txt")
        assert isinstance(cmd, list)
        assert cmd[0] == "socat"


class TestBuildSocatForwardCmd:
    """Tests for build_socat_forward_cmd()."""

    def test_tcp4_basic(self):
        cmd = build_socat_forward_cmd("tcp4", 8080, "10.0.0.5", 80)
        s = cmd_list_to_string(cmd)
        assert s == "socat TCP4-LISTEN:8080,reuseaddr,fork,backlog=128,keepalive TCP4:10.0.0.5:80"

    def test_no_unidirectional_flag(self):
        cmd = build_socat_forward_cmd("tcp4", 8080, "10.0.0.5", 80)
        assert "-u" not in cmd

    def test_cross_protocol(self):
        cmd = build_socat_forward_cmd("tcp4", 8080, "10.0.0.5", 53, "udp4")
        s = cmd_list_to_string(cmd)
        assert "TCP4-LISTEN" in s
        assert "UDP4:10.0.0.5:53" in s

    def test_udp_no_backlog(self):
        cmd = build_socat_forward_cmd("udp4", 5353, "8.8.8.8", 53)
        s = cmd_list_to_string(cmd)
        assert "backlog" not in s

    def test_default_remote_proto_matches_listen(self):
        cmd = build_socat_forward_cmd("udp4", 5353, "8.8.8.8", 53)
        s = cmd_list_to_string(cmd)
        assert "UDP4-LISTEN" in s
        assert "UDP4:8.8.8.8:53" in s

    def test_capture_mode(self):
        cmd = build_socat_forward_cmd("tcp4", 8080, "10.0.0.5", 80, capture=True)
        assert "-v" in cmd

    def test_hostname_in_command(self):
        cmd = build_socat_forward_cmd("tcp4", 80, "example.com", 443)
        assert "TCP4:example.com:443" in cmd_list_to_string(cmd)


class TestBuildSocatTunnelCmd:
    """Tests for build_socat_tunnel_cmd()."""

    def test_basic(self):
        cmd = build_socat_tunnel_cmd(4443, "10.0.0.5", 22, "/tmp/cert.pem", "/tmp/key.pem")
        s = cmd_list_to_string(cmd)
        assert "OPENSSL-LISTEN:4443" in s
        assert "cert=/tmp/cert.pem" in s
        assert "key=/tmp/key.pem" in s
        assert "verify=0" in s
        assert "reuseaddr,fork" in s
        assert "TCP4:10.0.0.5:22" in s

    def test_always_tcp4_remote(self):
        cmd = build_socat_tunnel_cmd(4443, "host.com", 80, "/c.pem", "/k.pem")
        assert "TCP4:host.com:80" in cmd_list_to_string(cmd)

    def test_capture_mode(self):
        cmd = build_socat_tunnel_cmd(4443, "10.0.0.5", 22, "/c.pem", "/k.pem", capture=True)
        assert "-v" in cmd

    def test_no_unidirectional_flag(self):
        cmd = build_socat_tunnel_cmd(4443, "10.0.0.5", 22, "/c.pem", "/k.pem")
        assert "-u" not in cmd


class TestBuildSocatRedirectCmd:
    """Tests for build_socat_redirect_cmd()."""

    def test_tcp4_basic(self):
        cmd = build_socat_redirect_cmd("tcp4", 8443, "example.com", 443)
        s = cmd_list_to_string(cmd)
        assert "TCP4-LISTEN:8443,reuseaddr,fork,backlog=128,keepalive" in s
        assert "TCP4:example.com:443" in s

    def test_udp4(self):
        cmd = build_socat_redirect_cmd("udp4", 5353, "8.8.8.8", 53)
        s = cmd_list_to_string(cmd)
        assert "UDP4-LISTEN:5353,reuseaddr,fork" in s
        assert "UDP4:8.8.8.8:53" in s
        assert "backlog" not in s

    def test_capture_mode(self):
        cmd = build_socat_redirect_cmd("tcp4", 8443, "example.com", 443, capture=True)
        assert "-v" in cmd

    def test_no_unidirectional_flag(self):
        cmd = build_socat_redirect_cmd("tcp4", 8443, "example.com", 443)
        assert "-u" not in cmd

    def test_all_protocol_variants(self):
        for proto, listen, connect in [
            ("tcp4", "TCP4-LISTEN", "TCP4"),
            ("tcp6", "TCP6-LISTEN", "TCP6"),
            ("udp4", "UDP4-LISTEN", "UDP4"),
            ("udp6", "UDP6-LISTEN", "UDP6"),
        ]:
            cmd = build_socat_redirect_cmd(proto, 8080, "host", 80)
            s = cmd_list_to_string(cmd)
            assert listen in s, f"{proto}: expected {listen}"
            assert f"{connect}:host:80" in s, f"{proto}: expected {connect}:host:80"


class TestCmdListToString:
    """Tests for cmd_list_to_string()."""

    def test_basic(self):
        assert cmd_list_to_string(["socat", "-v", "-u", "TCP4-LISTEN:8080"]) == \
            "socat -v -u TCP4-LISTEN:8080"

    def test_empty_list(self):
        assert cmd_list_to_string([]) == ""

    def test_single_element(self):
        assert cmd_list_to_string(["socat"]) == "socat"

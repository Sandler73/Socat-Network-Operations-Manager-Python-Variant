# ==============================================================================
# FILE        : tests/unit/test_source_filtering.py
# ==============================================================================
# Synopsis    : Unit tests for listener source filtering
# Description : Covers the source-range and TCP-wrappers validators, the
#               build_filter_opts assembler (including IPv6 bracketing and
#               address-family checking against the listener protocol), and the
#               appearance of the resulting range= and tcpwrap= options on the
#               listener address of every command builder.
# Version     : 1.0.1
# ==============================================================================

"""Unit tests for listener source filtering."""

from __future__ import annotations

import pytest

from socat_manager.commands import (
    build_filter_opts,
    build_socat_forward_cmd,
    build_socat_listen_cmd,
    build_socat_redirect_cmd,
    build_socat_tunnel_cmd,
)
from socat_manager.validation import (
    ValidationError,
    validate_source_range,
    validate_tcpwrap_name,
)


class TestValidateSourceRange:
    def test_ipv4_network_masked(self):
        assert validate_source_range("10.1.2.3/8") == "10.0.0.0/8"

    def test_ipv4_exact_network(self):
        assert validate_source_range("192.168.1.0/24") == "192.168.1.0/24"

    def test_ipv6_is_bracketed(self):
        assert validate_source_range("2001:db8::/32") == "[2001:db8::]/32"

    def test_ipv6_host_masked_and_bracketed(self):
        assert validate_source_range("2001:db8::1/32") == "[2001:db8::]/32"

    def test_default_route_accepted(self):
        assert validate_source_range("0.0.0.0/0") == "0.0.0.0/0"

    @pytest.mark.parametrize("bad", ["notacidr", "10.0.0.0/33", "999.1.1.1/8", ""])
    def test_invalid_rejected(self, bad):
        with pytest.raises(ValidationError):
            validate_source_range(bad)


class TestValidateTcpwrapName:
    @pytest.mark.parametrize("name", ["socat", "my-daemon_1", "svc.name"])
    def test_valid_names(self, name):
        assert validate_tcpwrap_name(name) == name

    @pytest.mark.parametrize("bad", ["", "bad name", "a;b", "x" * 65, "na$me"])
    def test_invalid_rejected(self, bad):
        with pytest.raises(ValidationError):
            validate_tcpwrap_name(bad)


class TestBuildFilterOpts:
    def test_empty_when_nothing_supplied(self):
        assert build_filter_opts() == ""

    def test_range_only(self):
        assert build_filter_opts(allow="10.0.0.0/8") == "range=10.0.0.0/8"

    def test_tcpwrap_only(self):
        assert build_filter_opts(tcpwrap="socat") == "tcpwrap=socat"

    def test_both_joined(self):
        assert build_filter_opts("10.0.0.0/8", "socat") == (
            "range=10.0.0.0/8,tcpwrap=socat"
        )

    def test_family_match_ok(self):
        assert build_filter_opts("2001:db8::/32", proto="tcp6") == (
            "range=[2001:db8::]/32"
        )

    def test_family_mismatch_v6_range_v4_listener(self):
        with pytest.raises(ValidationError):
            build_filter_opts("2001:db8::/32", proto="tcp4")

    def test_family_mismatch_v4_range_v6_listener(self):
        with pytest.raises(ValidationError):
            build_filter_opts("10.0.0.0/8", proto="udp6")

    def test_no_family_check_without_proto(self):
        # Without a proto, family is not enforced (used by tunnel).
        assert build_filter_opts("2001:db8::/32") == "range=[2001:db8::]/32"


class TestFilterOptsInCommands:
    def _joined(self, cmd: list[str]) -> str:
        return " ".join(cmd)

    def test_listen_places_filter_on_listener(self):
        f = build_filter_opts("10.0.0.0/8", "socat", "tcp4")
        cmd = build_socat_listen_cmd("tcp4", 8080, "/tmp/l.log", "", False, f)
        listener = cmd[cmd.index("-u") + 1]
        assert "range=10.0.0.0/8" in listener
        assert "tcpwrap=socat" in listener
        assert "TCP4-LISTEN:8080" in listener

    def test_forward_places_filter_on_listener_not_connector(self):
        f = build_filter_opts("10.0.0.0/8", proto="tcp4")
        cmd = build_socat_forward_cmd("tcp4", 8080, "1.2.3.4", 80, "tcp4", False, f)
        listener, connector = cmd[1], cmd[2]
        assert "range=10.0.0.0/8" in listener
        assert "range=" not in connector

    def test_redirect_places_filter_on_listener(self):
        f = build_filter_opts("192.168.0.0/16", proto="tcp4")
        cmd = build_socat_redirect_cmd("tcp4", 8443, "x.com", 443, False, f)
        assert "range=192.168.0.0/16" in cmd[1]

    def test_tunnel_places_filter_on_openssl_listener(self):
        f = build_filter_opts("10.0.0.0/8", "socat")
        cmd = build_socat_tunnel_cmd(
            4443, "1.2.3.4", 22, "/c.pem", "/k.pem", False, "tcp4", f
        )
        listener = cmd[1]
        assert listener.startswith("OPENSSL-LISTEN:4443")
        assert "range=10.0.0.0/8" in listener
        assert "tcpwrap=socat" in listener

    def test_ipv6_range_bracketed_in_command(self):
        f = build_filter_opts("2001:db8::/32", proto="tcp6")
        cmd = build_socat_listen_cmd("tcp6", 8080, "/tmp/l.log", "", False, f)
        listener = cmd[cmd.index("-u") + 1]
        assert "range=[2001:db8::]/32" in listener

    def test_absent_filter_leaves_command_unchanged(self):
        base = build_socat_listen_cmd("tcp4", 8080, "/tmp/l.log")
        with_empty = build_socat_listen_cmd("tcp4", 8080, "/tmp/l.log", "", False, "")
        assert base == with_empty
        assert "range=" not in " ".join(base)

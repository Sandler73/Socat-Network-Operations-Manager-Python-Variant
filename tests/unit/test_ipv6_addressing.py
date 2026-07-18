# ==============================================================================
# FILE        : tests/unit/test_ipv6_addressing.py
# ==============================================================================
# Synopsis    : Unit tests for IPv6 literal formatting in socat addresses
# Description : socat address fields are colon-delimited, so an IPv6 literal
#               must be bracketed for its own colons to be distinguished from
#               the field separator. These tests assert that every builder that
#               embeds a host in an address brackets IPv6 literals, leaves
#               hostnames and IPv4 literals untouched, and produces addresses
#               where the port remains unambiguously parseable.
# Version     : 1.0.2
# ==============================================================================

"""Unit tests for IPv6 literal formatting in socat addresses."""

from __future__ import annotations

import pytest

from socat_manager.commands import (
    build_socat_forward_cmd,
    build_socat_redirect_cmd,
    build_socat_tunnel_cmd,
    format_socat_endpoint,
    format_socat_host,
)


class TestFormatSocatHost:
    """Tests for host formatting."""

    @pytest.mark.parametrize("host", [
        "10.0.0.5",
        "192.168.1.1",
        "example.com",
        "host-01.internal.example.com",
        "localhost",
    ])
    def test_hosts_without_colons_are_unchanged(self, host):
        """Hostnames and IPv4 literals contain no colons and pass through."""
        assert format_socat_host(host) == host

    @pytest.mark.parametrize("host,expected", [
        ("2001:db8::1", "[2001:db8::1]"),
        ("::1", "[::1]"),
        ("fe80::1", "[fe80::1]"),
        ("2001:0db8:0000:0000:0000:0000:0000:0001",
         "[2001:0db8:0000:0000:0000:0000:0000:0001]"),
    ])
    def test_ipv6_literals_are_bracketed(self, host, expected):
        """An IPv6 literal is enclosed in brackets."""
        assert format_socat_host(host) == expected

    def test_already_bracketed_host_is_not_double_bracketed(self):
        """Formatting is idempotent for an already bracketed literal."""
        assert format_socat_host("[2001:db8::1]") == "[2001:db8::1]"

    def test_endpoint_keeps_the_port_parseable(self):
        """The port remains the final colon-delimited field."""
        endpoint = format_socat_endpoint("2001:db8::1", 443)
        assert endpoint == "[2001:db8::1]:443"
        # The address and the port are unambiguously separable.
        address, _, port = endpoint.rpartition(":")
        assert address == "[2001:db8::1]"
        assert port == "443"

    def test_ipv4_endpoint_is_unchanged(self):
        """An IPv4 endpoint keeps its plain HOST:PORT form."""
        assert format_socat_endpoint("10.0.0.5", 80) == "10.0.0.5:80"


class TestBuildersBracketIPv6Remotes:
    """Tests that every builder brackets IPv6 remote targets."""

    def test_forward_brackets_ipv6_remote(self):
        """The forward builder brackets an IPv6 remote target."""
        cmd = build_socat_forward_cmd("tcp6", 8080, "2001:db8::1", 443)
        assert cmd[-1] == "TCP6:[2001:db8::1]:443"

    def test_forward_leaves_ipv4_remote_plain(self):
        """The forward builder leaves an IPv4 remote target unchanged."""
        cmd = build_socat_forward_cmd("tcp4", 8080, "10.0.0.5", 80)
        assert cmd[-1] == "TCP4:10.0.0.5:80"

    def test_forward_leaves_hostname_plain(self):
        """The forward builder leaves a hostname unchanged."""
        cmd = build_socat_forward_cmd("tcp4", 8080, "example.com", 80)
        assert cmd[-1] == "TCP4:example.com:80"

    def test_redirect_brackets_ipv6_remote(self):
        """The redirect builder brackets an IPv6 remote target."""
        cmd = build_socat_redirect_cmd("tcp6", 8443, "2001:db8::1", 443)
        assert cmd[-1] == "TCP6:[2001:db8::1]:443"

    def test_redirect_udp6_brackets_ipv6_remote(self):
        """The redirect builder brackets IPv6 for UDP as well."""
        cmd = build_socat_redirect_cmd("udp6", 5353, "fe80::1", 53)
        assert cmd[-1] == "UDP6:[fe80::1]:53"

    def test_tunnel_brackets_ipv6_remote(self):
        """The tunnel builder brackets an IPv6 remote target."""
        cmd = build_socat_tunnel_cmd(4443, "2001:db8::1", 22, "/c.pem", "/k.pem")
        assert cmd[-1].endswith(":[2001:db8::1]:22")

    def test_no_unbracketed_ipv6_in_any_builder_output(self):
        """No builder emits an IPv6 literal without brackets.

        An unbracketed IPv6 literal produces an address whose port cannot be
        determined, which socat rejects.
        """
        commands = [
            build_socat_forward_cmd("tcp6", 8080, "2001:db8::1", 443),
            build_socat_redirect_cmd("tcp6", 8443, "2001:db8::1", 443),
            build_socat_tunnel_cmd(4443, "2001:db8::1", 22, "/c.pem", "/k.pem"),
        ]
        for cmd in commands:
            remote = cmd[-1]
            assert "2001:db8::1" in remote
            assert "[2001:db8::1]" in remote, f"unbracketed IPv6 literal in {remote!r}"


class TestTunnelRemoteFamily:
    """Tests that the tunnel remote leg selects the correct address family."""

    def test_ipv4_remote_uses_tcp4_connector(self):
        """An IPv4 remote target is reached over a TCP4 connector."""
        cmd = build_socat_tunnel_cmd(4443, "10.0.0.5", 22, "/c.pem", "/k.pem")
        assert cmd[-1] == "TCP4:10.0.0.5:22"

    def test_ipv6_remote_uses_tcp6_connector(self):
        """An IPv6 remote target is reached over a TCP6 connector, bracketed."""
        cmd = build_socat_tunnel_cmd(
            4443, "2001:db8::1", 22, "/c.pem", "/k.pem", remote_proto="tcp6",
        )
        assert cmd[-1] == "TCP6:[2001:db8::1]:22"

    def test_default_remote_family_is_tcp4(self):
        """The remote family defaults to TCP4 when not specified."""
        cmd = build_socat_tunnel_cmd(4443, "example.com", 22, "/c.pem", "/k.pem")
        assert cmd[-1] == "TCP4:example.com:22"

    def test_unknown_remote_proto_falls_back_to_tcp4(self):
        """An unrecognized remote family selector falls back to TCP4."""
        cmd = build_socat_tunnel_cmd(
            4443, "10.0.0.5", 22, "/c.pem", "/k.pem", remote_proto="bogus",
        )
        assert cmd[-1] == "TCP4:10.0.0.5:22"


class TestIsIPv6Literal:
    """Tests for the IPv6 literal predicate used to select the remote family."""

    def test_ipv6_literals_are_detected(self):
        """Values that are IPv6 literals are reported as such."""
        from socat_manager.validation import is_ipv6_literal
        assert is_ipv6_literal("2001:db8::1") is True
        assert is_ipv6_literal("::1") is True
        assert is_ipv6_literal("fe80::1") is True

    def test_hostnames_and_ipv4_are_not_ipv6(self):
        """Hostnames and IPv4 literals are not IPv6 literals."""
        from socat_manager.validation import is_ipv6_literal
        assert is_ipv6_literal("10.0.0.5") is False
        assert is_ipv6_literal("example.com") is False
        assert is_ipv6_literal("localhost") is False

# ==============================================================================
# FILE        : tests/unit/test_port_scoping.py
# ==============================================================================
# Synopsis    : Unit tests for protocol scoping in the port layer
# Description : The protocol model has four members (tcp4, tcp6, udp4, udp6).
#               Every port query must preserve all four, carrying both the
#               transport and the address family. These tests assert that the
#               socket-listing commands are scoped correctly, that a listener
#               of one family does not mask an available port of the other,
#               and that the port-based cleanup path cannot reach across
#               families to terminate an unrelated session.
# Version     : 1.0.2
# ==============================================================================

"""Unit tests for protocol scoping in the port layer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from socat_manager.process import (
    _family_of,
    _scope_flags,
    _transport_of,
    check_port_available,
    kill_by_port,
)


class TestProtocolScopeHelpers:
    """Tests for the transport and address family decomposition."""

    def test_transport_of(self):
        """Transport is derived from the protocol name."""
        assert _transport_of("tcp4") == "tcp"
        assert _transport_of("tcp6") == "tcp"
        assert _transport_of("udp4") == "udp"
        assert _transport_of("udp6") == "udp"

    def test_family_of(self):
        """Address family is derived from the protocol suffix."""
        assert _family_of("tcp4") == "4"
        assert _family_of("udp4") == "4"
        assert _family_of("tcp6") == "6"
        assert _family_of("udp6") == "6"

    def test_scope_flags_cover_all_four_protocols(self):
        """Each protocol maps to a distinct, fully scoped flag set."""
        assert _scope_flags("tcp4") == ["-t", "-4", "-l", "-n"]
        assert _scope_flags("tcp6") == ["-t", "-6", "-l", "-n"]
        assert _scope_flags("udp4") == ["-u", "-4", "-l", "-n"]
        assert _scope_flags("udp6") == ["-u", "-6", "-l", "-n"]

    def test_scope_flags_are_unique_per_protocol(self):
        """No two protocols collapse onto the same query scope."""
        flag_sets = [
            tuple(_scope_flags(p)) for p in ("tcp4", "tcp6", "udp4", "udp6")
        ]
        assert len(set(flag_sets)) == 4


class TestCheckPortAvailableScoping:
    """Tests that check_port_available() queries a single protocol."""

    @patch("socat_manager.process.subprocess.run")
    def test_query_carries_family_flag(self, mock_run):
        """The ss invocation is scoped to the address family of the protocol."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        check_port_available(8080, "tcp6")

        argv = mock_run.call_args.args[0]
        assert argv[0] == "ss"
        assert "-6" in argv
        assert "-4" not in argv
        assert "-t" in argv

    @patch("socat_manager.process.subprocess.run")
    def test_udp4_query_is_udp_and_v4(self, mock_run):
        """A udp4 check queries UDP sockets in the IPv4 family only."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        check_port_available(9090, "udp4")

        argv = mock_run.call_args.args[0]
        assert "-u" in argv
        assert "-4" in argv
        assert "-t" not in argv
        assert "-6" not in argv

    @patch("socat_manager.process.subprocess.run")
    def test_v6_listener_does_not_occupy_the_v4_port(self, mock_run):
        """An IPv6 listener must not make the same IPv4 port look occupied.

        The family flag restricts the listing to IPv4, so the IPv6 listener on
        the same port number is simply not reported and the port is available.
        """
        def listing(argv, **kwargs):
            if "-6" in argv:
                return MagicMock(
                    returncode=0,
                    stdout="State  Recv-Q Send-Q Local Address:Port\n"
                           "LISTEN 0      128              [::]:8080\n",
                )
            # IPv4 listing: nothing bound
            return MagicMock(
                returncode=0,
                stdout="State  Recv-Q Send-Q Local Address:Port\n",
            )

        mock_run.side_effect = listing

        assert check_port_available(8080, "tcp6") is False
        assert check_port_available(8080, "tcp4") is True

    @patch("socat_manager.process.subprocess.run")
    def test_tcp_listener_does_not_occupy_the_udp_port(self, mock_run):
        """A TCP listener must not make the same UDP port look occupied."""
        def listing(argv, **kwargs):
            if "-t" in argv:
                return MagicMock(
                    returncode=0,
                    stdout="LISTEN 0 128 0.0.0.0:8080\n",
                )
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = listing

        assert check_port_available(8080, "tcp4") is False
        assert check_port_available(8080, "udp4") is True


class TestKillByPortScoping:
    """Tests that the port-based cleanup path cannot cross address families."""

    @patch("socat_manager.process._is_socat_process", return_value=True)
    @patch("socat_manager.process.os.kill")
    @patch("socat_manager.process.subprocess.run")
    def test_does_not_kill_across_address_families(
        self, mock_run, mock_kill, mock_is_socat,
    ):
        """Cleaning up tcp4 must not terminate the tcp6 socat on the same port.

        Both sockets can exist simultaneously on the same port number. A stop
        directed at one family must leave the other untouched.
        """
        def listing(argv, **kwargs):
            if "-6" in argv:
                return MagicMock(
                    returncode=0,
                    stdout='LISTEN 0 128 [::]:8080 users:(("socat",pid=6666,fd=5))\n',
                )
            return MagicMock(
                returncode=0,
                stdout='LISTEN 0 128 0.0.0.0:8080 users:(("socat",pid=4444,fd=5))\n',
            )

        mock_run.side_effect = listing

        kill_by_port(8080, "tcp4")

        killed = [c.args[0] for c in mock_kill.call_args_list]
        assert killed == [4444], "cleanup reached a socat of the other family"

    @patch("socat_manager.process._is_socat_process", return_value=True)
    @patch("socat_manager.process.os.kill")
    @patch("socat_manager.process.subprocess.run")
    def test_ss_query_is_family_scoped(self, mock_run, mock_kill, mock_is_socat):
        """The ss query used for cleanup carries the family flag."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        kill_by_port(8080, "udp6")

        argv = mock_run.call_args_list[0].args[0]
        assert argv[0] == "ss"
        assert "-u" in argv
        assert "-6" in argv
        assert "-p" in argv
        assert "-4" not in argv

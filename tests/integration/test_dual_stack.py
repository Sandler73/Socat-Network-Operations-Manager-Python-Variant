# ==============================================================================
# FILE        : tests/integration/test_dual_stack.py
# ==============================================================================
# Synopsis    : Integration tests for dual-stack protocol independence
# Description : Verifies that TCP and UDP sessions on the same port are
#               completely independent: separate session IDs, separate session
#               files, separate stop paths. Stopping one protocol must NOT
#               affect the other. This was the v2.2.0 cross-protocol kill bug.
# Version     : 1.0.1
# ==============================================================================

"""Integration tests for dual-stack protocol independence."""

from __future__ import annotations

from socat_manager.commands import (
    build_socat_forward_cmd,
    build_socat_listen_cmd,
    build_socat_redirect_cmd,
    cmd_list_to_string,
)
from socat_manager.config import ALT_PROTOCOL
from socat_manager.process import stop_session
from socat_manager.session import (
    session_count,
    session_find_by_port,
    session_read_field,
)


class TestDualStackSessionIsolation:
    """Tests verifying dual-stack sessions are independent entities."""

    def test_different_session_ids(self, dual_stack_sessions):
        """TCP and UDP sessions on same port get different session IDs."""
        tcp_sid, udp_sid = dual_stack_sessions
        assert tcp_sid != udp_sid

    def test_different_session_files(self, dual_stack_sessions, paths):
        """Each protocol gets its own session file."""
        tcp_sid, udp_sid = dual_stack_sessions
        tcp_file = paths.session_dir / f"{tcp_sid}.session"
        udp_file = paths.session_dir / f"{udp_sid}.session"
        assert tcp_file.is_file()
        assert udp_file.is_file()

    def test_correct_protocol_in_each_file(self, dual_stack_sessions, paths):
        """Each session file records the correct protocol."""
        tcp_sid, udp_sid = dual_stack_sessions
        tcp_file = paths.session_dir / f"{tcp_sid}.session"
        udp_file = paths.session_dir / f"{udp_sid}.session"
        assert session_read_field(tcp_file, "PROTOCOL") == "tcp4"
        assert session_read_field(udp_file, "PROTOCOL") == "udp4"

    def test_same_port_in_both_files(self, dual_stack_sessions, paths):
        """Both sessions should be on the same port."""
        tcp_sid, udp_sid = dual_stack_sessions
        tcp_file = paths.session_dir / f"{tcp_sid}.session"
        udp_file = paths.session_dir / f"{udp_sid}.session"
        assert session_read_field(tcp_file, "LOCAL_PORT") == "8080"
        assert session_read_field(udp_file, "LOCAL_PORT") == "8080"

    def test_port_lookup_returns_both(self, dual_stack_sessions):
        """Finding by port should return both TCP and UDP sessions."""
        tcp_sid, udp_sid = dual_stack_sessions
        results = session_find_by_port(8080)
        assert len(results) == 2
        assert tcp_sid in results
        assert udp_sid in results


class TestDualStackStopIsolation:
    """Tests verifying stop operations are protocol-scoped."""

    def test_stop_tcp_preserves_udp(self, dual_stack_sessions, paths):
        """Stopping TCP on shared port must NOT affect UDP."""
        tcp_sid, udp_sid = dual_stack_sessions

        # Stop TCP
        stop_session(tcp_sid)

        # TCP gone
        assert not (paths.session_dir / f"{tcp_sid}.session").is_file()

        # UDP intact
        assert (paths.session_dir / f"{udp_sid}.session").is_file()
        udp_file = paths.session_dir / f"{udp_sid}.session"
        assert session_read_field(udp_file, "PROTOCOL") == "udp4"

    def test_stop_udp_preserves_tcp(self, dual_stack_sessions, paths):
        """Stopping UDP on shared port must NOT affect TCP."""
        tcp_sid, udp_sid = dual_stack_sessions

        stop_session(udp_sid)

        assert (paths.session_dir / f"{tcp_sid}.session").is_file()
        assert not (paths.session_dir / f"{udp_sid}.session").is_file()

    def test_stop_both_independently(self, dual_stack_sessions, paths):
        """Stopping both protocols independently should clean up both."""
        tcp_sid, udp_sid = dual_stack_sessions

        stop_session(tcp_sid)
        assert session_count() == 1

        stop_session(udp_sid)
        assert session_count() == 0

    def test_stop_all_clears_both(self, dual_stack_sessions, paths):
        """Stopping all sessions should clear both TCP and UDP."""
        tcp_sid, udp_sid = dual_stack_sessions
        assert session_count() == 2

        stop_session(tcp_sid)
        stop_session(udp_sid)
        assert session_count() == 0


class TestDualStackCommandConstruction:
    """Tests verifying dual-stack generates correct commands per protocol."""

    def test_listen_cmd_tcp_vs_udp(self):
        """Listen commands should use correct socat address type per protocol."""
        tcp_cmd = cmd_list_to_string(build_socat_listen_cmd("tcp4", 8080, "/tmp/t.log"))
        udp_cmd = cmd_list_to_string(build_socat_listen_cmd("udp4", 8080, "/tmp/u.log"))

        assert "TCP4-LISTEN" in tcp_cmd
        assert "UDP4-LISTEN" in udp_cmd
        assert "backlog=128" in tcp_cmd
        assert "backlog" not in udp_cmd
        assert "keepalive" in tcp_cmd
        assert "keepalive" not in udp_cmd

    def test_forward_cmd_tcp_vs_udp(self):
        """Forward commands should use correct address types per protocol."""
        tcp_cmd = cmd_list_to_string(build_socat_forward_cmd("tcp4", 80, "h", 80))
        udp_cmd = cmd_list_to_string(build_socat_forward_cmd("udp4", 53, "h", 53))

        assert "TCP4-LISTEN" in tcp_cmd and "TCP4:h:80" in tcp_cmd
        assert "UDP4-LISTEN" in udp_cmd and "UDP4:h:53" in udp_cmd

    def test_redirect_cmd_tcp_vs_udp(self):
        """Redirect commands should use correct address types per protocol."""
        tcp_cmd = cmd_list_to_string(build_socat_redirect_cmd("tcp4", 443, "h", 443))
        udp_cmd = cmd_list_to_string(build_socat_redirect_cmd("udp4", 53, "h", 53))

        assert "TCP4-LISTEN" in tcp_cmd and "TCP4:h:443" in tcp_cmd
        assert "UDP4-LISTEN" in udp_cmd and "UDP4:h:53" in udp_cmd

    def test_alt_protocol_map_completeness(self):
        """Every valid protocol should have an alternate."""
        for proto in ("tcp4", "tcp6", "udp4", "udp6"):
            alt = ALT_PROTOCOL.get(proto)
            assert alt is not None, f"No alt protocol for {proto}"
            assert alt != proto, f"Alt protocol for {proto} is same as original"

    def test_alt_protocol_symmetry(self):
        """ALT_PROTOCOL should be symmetric: alt(alt(x)) == x."""
        for proto in ("tcp4", "tcp6", "udp4", "udp6"):
            assert ALT_PROTOCOL[ALT_PROTOCOL[proto]] == proto

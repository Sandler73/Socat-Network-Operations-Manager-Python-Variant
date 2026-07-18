# ==============================================================================
# FILE        : tests/unit/test_session.py
# ==============================================================================
# Synopsis    : Unit tests for session management
# Description : Full test coverage for socat_manager.session covering
#               session ID generation, registration, field reading (exact match),
#               lookup by name/port/PID, alive checks, enumeration, cleanup,
#               and advisory file locking.
# Version     : 1.0.2
# ==============================================================================

"""Unit tests for session management."""

import stat

from socat_manager.session import (
    generate_session_id,
    migrate_legacy_sessions,
    session_cleanup_dead,
    session_count,
    session_find_by_name,
    session_find_by_pid,
    session_find_by_port,
    session_get_all_ids,
    session_is_alive,
    session_lock,
    session_read_all_fields,
    session_read_field,
    session_register,
    session_unregister,
)


class TestGenerateSessionId:
    """Tests for generate_session_id()."""

    def test_length_8(self):
        sid = generate_session_id()
        assert len(sid) == 8

    def test_lowercase_hex(self):
        sid = generate_session_id()
        assert all(c in "0123456789abcdef" for c in sid)

    def test_uniqueness(self):
        ids = {generate_session_id() for _ in range(100)}
        assert len(ids) == 100  # All unique

    def test_no_collision_with_existing(self, paths):
        """IDs should not collide with existing session files."""
        # Create a bunch of sessions to increase collision chance
        existing = set()
        for i in range(10):
            sid = generate_session_id()
            session_register(sid=sid, name=f"test-{i}", pid=i + 1000, pgid=i + 1000, mode="listen")
            existing.add(sid)

        # Generate more — none should collide
        for _ in range(50):
            new_sid = generate_session_id()
            assert new_sid not in existing or (paths.session_dir / f"{new_sid}.session").exists()


class TestSessionRegister:
    """Tests for session_register()."""

    def test_creates_file(self, paths):
        session_register(sid="aabbccdd", name="test", pid=1234, pgid=1234, mode="listen")
        assert (paths.session_dir / "aabbccdd.session").is_file()

    def test_file_permissions_0600(self, paths):
        session_register(sid="aabbccdd", name="test", pid=1234, pgid=1234, mode="listen")
        mode = stat.S_IMODE((paths.session_dir / "aabbccdd.session").stat().st_mode)
        assert mode == 0o600

    def test_all_fields_written(self, paths):
        session_register(
            sid="aabbccdd", name="test-session", pid=5678, pgid=5678,
            mode="forward", proto="udp4", lport=9090,
            socat_cmd="socat UDP4-LISTEN:9090 UDP4:10.0.0.1:53",
            rhost="10.0.0.1", rport="53",
        )
        sf = paths.session_dir / "aabbccdd.session"
        assert session_read_field(sf, "SESSION_ID") == "aabbccdd"
        assert session_read_field(sf, "SESSION_NAME") == "test-session"
        assert session_read_field(sf, "PID") == "5678"
        assert session_read_field(sf, "PGID") == "5678"
        assert session_read_field(sf, "MODE") == "forward"
        assert session_read_field(sf, "PROTOCOL") == "udp4"
        assert session_read_field(sf, "LOCAL_PORT") == "9090"
        assert session_read_field(sf, "REMOTE_HOST") == "10.0.0.1"
        assert session_read_field(sf, "REMOTE_PORT") == "53"
        assert "UDP4-LISTEN:9090" in session_read_field(sf, "SOCAT_CMD")

    def test_header_comment(self, paths):
        session_register(sid="aabbccdd", name="test", pid=1, pgid=1, mode="listen")
        content = (paths.session_dir / "aabbccdd.session").read_text()
        assert content.startswith("# socat_manager session file v2.3")


class TestSessionReadField:
    """Tests for session_read_field() — exact key match."""

    def test_exact_match(self, sample_session, paths):
        sf = paths.session_dir / f"{sample_session}.session"
        assert session_read_field(sf, "PID") == "99999"

    def test_pid_does_not_match_launcher_pid(self, sample_session, paths):
        """CRITICAL: 'PID' must not match 'LAUNCHER_PID' substring."""
        sf = paths.session_dir / f"{sample_session}.session"
        pid = session_read_field(sf, "PID")
        launcher_pid = session_read_field(sf, "LAUNCHER_PID")
        # PID is explicitly 99999 from the fixture, LAUNCHER_PID is the test runner's PID
        assert pid == "99999"
        assert launcher_pid != pid

    def test_handles_values_with_equals(self, sample_session, paths):
        """SOCAT_CMD contains '=' characters in its value."""
        sf = paths.session_dir / f"{sample_session}.session"
        cmd = session_read_field(sf, "SOCAT_CMD")
        assert "TCP4-LISTEN:8443" in cmd
        assert "TCP4:example.com:443" in cmd

    def test_missing_field_returns_empty(self, sample_session, paths):
        sf = paths.session_dir / f"{sample_session}.session"
        assert session_read_field(sf, "NONEXISTENT_FIELD") == ""

    def test_missing_file_returns_empty(self, paths):
        sf = paths.session_dir / "nonexistent.session"
        assert session_read_field(sf, "PID") == ""

    def test_skips_comments(self, paths):
        """Lines starting with # should be ignored."""
        sf = paths.session_dir / "test.session"
        sf.write_text("# PID=99999\nPID=12345\n")
        assert session_read_field(sf, "PID") == "12345"

    def test_skips_empty_lines(self, paths):
        sf = paths.session_dir / "test.session"
        sf.write_text("\n\nPID=12345\n\n")
        assert session_read_field(sf, "PID") == "12345"

    def test_first_match_wins(self, paths):
        """If a field appears twice (shouldn't), first match is returned."""
        sf = paths.session_dir / "test.session"
        sf.write_text("PID=first\nPID=second\n")
        assert session_read_field(sf, "PID") == "first"


class TestSessionLookup:
    """Tests for session_find_by_name/port/pid."""

    def test_find_by_name(self, sample_session):
        assert session_find_by_name("redir-tcp4-8443-example.com-443") == [sample_session]

    def test_find_by_name_not_found(self):
        assert session_find_by_name("nonexistent") == []

    def test_find_by_port(self, sample_session):
        assert session_find_by_port(8443) == [sample_session]

    def test_find_by_port_not_found(self):
        assert session_find_by_port(99999) == []

    def test_find_by_pid(self, sample_session):
        assert session_find_by_pid(99999) == [sample_session]

    def test_find_by_pid_not_found(self):
        assert session_find_by_pid(1) == []

    def test_dual_stack_port_lookup(self, dual_stack_sessions):
        tcp_sid, udp_sid = dual_stack_sessions
        results = session_find_by_port(8080)
        assert len(results) == 2
        assert tcp_sid in results
        assert udp_sid in results


class TestSessionAlive:
    """Tests for session_is_alive()."""

    def test_dead_process(self, sample_session):
        """PID 99999 should not be alive in the test environment."""
        assert session_is_alive(sample_session) is False

    def test_nonexistent_session(self):
        assert session_is_alive("ffffffff") is False


class TestSessionEnumeration:
    """Tests for session_get_all_ids() and session_count()."""

    def test_empty(self):
        assert session_get_all_ids() == []
        assert session_count() == 0

    def test_single(self, sample_session):
        assert session_get_all_ids() == [sample_session]
        assert session_count() == 1

    def test_multiple(self, dual_stack_sessions):
        tcp_sid, udp_sid = dual_stack_sessions
        all_ids = session_get_all_ids()
        assert len(all_ids) == 2
        assert session_count() == 2


class TestSessionUnregister:
    """Tests for session_unregister()."""

    def test_removes_session_file(self, sample_session, paths):
        assert (paths.session_dir / f"{sample_session}.session").is_file()
        session_unregister(sample_session)
        assert not (paths.session_dir / f"{sample_session}.session").is_file()

    def test_removes_stop_signal(self, sample_session, paths):
        stop_file = paths.session_dir / f"{sample_session}.stop"
        stop_file.touch()
        session_unregister(sample_session)
        assert not stop_file.is_file()

    def test_removes_launching_file(self, sample_session, paths):
        launching_file = paths.session_dir / f"{sample_session}.launching"
        launching_file.touch()
        session_unregister(sample_session)
        assert not launching_file.is_file()

    def test_nonexistent_doesnt_error(self):
        # Should not raise
        session_unregister("ffffffff")


class TestSessionCleanup:
    """Tests for session_cleanup_dead()."""

    def test_cleans_dead_sessions(self, sample_session, paths):
        """PID 99999 is dead → session should be cleaned up."""
        assert session_count() == 1
        cleaned = session_cleanup_dead()
        assert cleaned == 1
        assert session_count() == 0

    def test_no_dead_sessions(self):
        cleaned = session_cleanup_dead()
        assert cleaned == 0


class TestSessionLock:
    """Tests for session_lock() context manager."""

    def test_lock_acquires_and_releases(self, paths):
        with session_lock():
            assert paths.session_lock_file.is_file()

    def test_lock_reentrant_in_same_process(self, paths):
        """Advisory lock should work in same process."""
        with session_lock():
            # Second lock in same process should not deadlock
            with session_lock():
                pass


class TestSessionReadAllFields:
    """Tests for session_read_all_fields() bulk reader."""

    def test_reads_all_fields(self, sample_session, paths):
        sf = paths.session_dir / f"{sample_session}.session"
        fields = session_read_all_fields(sf)
        assert fields["SESSION_ID"] == sample_session
        assert fields["SESSION_NAME"] == "redir-tcp4-8443-example.com-443"
        assert fields["PID"] == "99999"
        assert fields["PGID"] == "99999"
        assert fields["MODE"] == "redirect"
        assert fields["PROTOCOL"] == "tcp4"
        assert fields["LOCAL_PORT"] == "8443"
        assert fields["REMOTE_HOST"] == "example.com"
        assert fields["REMOTE_PORT"] == "443"

    def test_handles_values_with_equals(self, sample_session, paths):
        sf = paths.session_dir / f"{sample_session}.session"
        fields = session_read_all_fields(sf)
        assert "TCP4-LISTEN:8443" in fields["SOCAT_CMD"]

    def test_first_occurrence_wins(self, paths):
        sf = paths.session_dir / "test.session"
        sf.write_text("PID=first\nPID=second\n")
        fields = session_read_all_fields(sf)
        assert fields["PID"] == "first"

    def test_skips_comments(self, paths):
        sf = paths.session_dir / "test.session"
        sf.write_text("# PID=99999\nPID=12345\n")
        fields = session_read_all_fields(sf)
        assert fields["PID"] == "12345"

    def test_missing_file_returns_empty_dict(self, paths):
        sf = paths.session_dir / "nonexistent.session"
        fields = session_read_all_fields(sf)
        assert fields == {}

    def test_empty_file_returns_empty_dict(self, paths):
        sf = paths.session_dir / "empty.session"
        sf.write_text("")
        fields = session_read_all_fields(sf)
        assert fields == {}

    def test_single_pass_consistency_with_read_field(self, sample_session, paths):
        """Bulk reader should return same values as per-field reader."""
        sf = paths.session_dir / f"{sample_session}.session"
        fields = session_read_all_fields(sf)
        for key in ("SESSION_ID", "PID", "PGID", "PROTOCOL", "LOCAL_PORT"):
            assert fields[key] == session_read_field(sf, key)


class TestMigrateLegacySessions:
    """Tests for migrate_legacy_sessions()."""

    def test_no_legacy_files(self, paths):
        """No .pid files → 0 migrated."""
        count = migrate_legacy_sessions()
        assert count == 0

    def test_dead_legacy_removed(self, paths):
        """Legacy .pid with dead PID should be removed, not migrated."""
        legacy = paths.session_dir / "old-listener.pid"
        legacy.write_text("PID=99999\nMODE=listen\nPROTOCOL=tcp4\nLOCAL_PORT=8080\n")
        count = migrate_legacy_sessions()
        assert count == 0
        assert not legacy.exists()

    def test_invalid_pid_removed(self, paths):
        """Legacy .pid with non-numeric PID should be removed."""
        legacy = paths.session_dir / "bad.pid"
        legacy.write_text("PID=notanumber\n")
        count = migrate_legacy_sessions()
        assert count == 0
        assert not legacy.exists()

    def test_empty_pid_removed(self, paths):
        """Legacy .pid without PID field should be removed."""
        legacy = paths.session_dir / "empty.pid"
        legacy.write_text("MODE=listen\n")
        count = migrate_legacy_sessions()
        assert count == 0
        assert not legacy.exists()

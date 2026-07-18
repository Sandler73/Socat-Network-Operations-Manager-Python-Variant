# ==============================================================================
# FILE        : tests/unit/test_session_update.py
# ==============================================================================
# Synopsis    : Unit tests for session process identity updates
# Description : Tests session_update_process(), which rewrites the PID and PGID
#               of an existing session file while preserving
#               every other field. This is the durable record consulted by
#               liveness checks and by the stop sequence, so the tests assert
#               both field replacement and field preservation, and confirm the
#               updated record drives session_is_alive().
# Version     : 1.0.2
# ==============================================================================

"""Unit tests for session process identity updates."""

from __future__ import annotations

import os

from socat_manager.session import (
    session_is_alive,
    session_read_all_fields,
    session_read_field,
    session_register,
    session_update_process,
)


class TestSessionUpdateProcess:
    """Tests for session_update_process()."""

    def test_updates_pid_and_pgid(self, paths):
        """PID and PGID fields are replaced with the supplied values."""
        session_register(
            sid="11aa22bb", name="update-test", pid=1000, pgid=1000,
            mode="listen", proto="tcp4", lport=8080,
        )

        assert session_update_process("11aa22bb", pid=2000, pgid=2000) is True

        session_file = paths.session_dir / "11aa22bb.session"
        assert session_read_field(session_file, "PID") == "2000"
        assert session_read_field(session_file, "PGID") == "2000"

    def test_preserves_original_started_timestamp(self, paths):
        """The original session-creation time survives a process update.

        STARTED records when the session was created. A watchdog restart
        changes which process the session owns, but not when the session began,
        so the field must be preserved rather than rewritten to the restart
        time.
        """
        session_register(
            sid="99ab99ab", name="started-test", pid=1000, pgid=1000,
            mode="listen", proto="tcp4", lport=8080,
        )
        session_file = paths.session_dir / "99ab99ab.session"

        # Stamp a distinctive original creation time so a rewrite is detectable.
        original_started = "2020-01-01T00:00:00"
        text = session_file.read_text().splitlines()
        text = [
            f"STARTED={original_started}" if line.startswith("STARTED=") else line
            for line in text
        ]
        session_file.write_text("\n".join(text) + "\n")

        assert session_update_process("99ab99ab", pid=2000, pgid=2000) is True

        assert session_read_field(session_file, "STARTED") == original_started

    def test_preserves_all_other_fields(self, paths):
        """Every field other than PID and PGID survives the update."""
        session_register(
            sid="33cc44dd", name="preserve-test", pid=1000, pgid=1000,
            mode="forward", proto="udp6", lport=9090,
            socat_cmd="socat UDP6-LISTEN:9090,reuseaddr,fork UDP6:[2001:db8::1]:53",
            rhost="2001:db8::1", rport="53",
        )

        session_file = paths.session_dir / "33cc44dd.session"
        before = session_read_all_fields(session_file)

        assert session_update_process("33cc44dd", pid=4242, pgid=4242) is True

        after = session_read_all_fields(session_file)

        # Process identity changed
        assert after["PID"] == "4242"
        assert after["PGID"] == "4242"

        # Everything else is byte-identical, including the creation timestamp.
        for field in (
            "SESSION_ID", "SESSION_NAME", "MODE", "PROTOCOL", "LOCAL_PORT",
            "REMOTE_HOST", "REMOTE_PORT", "SOCAT_CMD", "CORRELATION",
            "LAUNCHER_PID", "STARTED",
        ):
            assert after[field] == before[field], f"field {field} was not preserved"

    def test_file_permissions_remain_restrictive(self, paths):
        """The rewritten session file retains 0o600 permissions."""
        session_register(
            sid="55ee66ff", name="perm-test", pid=1000, pgid=1000,
            mode="listen", proto="tcp4", lport=8080,
        )

        assert session_update_process("55ee66ff", pid=2000, pgid=2000) is True

        session_file = paths.session_dir / "55ee66ff.session"
        mode = os.stat(session_file).st_mode & 0o777
        assert mode == 0o600

    def test_no_temporary_file_left_behind(self, paths):
        """The atomic rename leaves no temporary artifact in the session dir."""
        session_register(
            sid="77aa88bb", name="tmp-test", pid=1000, pgid=1000,
            mode="listen", proto="tcp4", lport=8080,
        )

        assert session_update_process("77aa88bb", pid=2000, pgid=2000) is True

        assert list(paths.session_dir.glob("*.tmp")) == []

    def test_missing_session_returns_false(self, paths):
        """Updating a session that does not exist reports failure."""
        assert session_update_process("99cc00dd", pid=2000, pgid=2000) is False

    def test_liveness_follows_the_updated_process(self, paths):
        """session_is_alive() reflects the updated PID, not the original.

        The session is registered against a PID that is not running, so the
        session reads as dead. After the record is updated to the live PID of
        this test process, the same session reads as alive. This is the
        contract the watchdog depends on when it replaces a crashed process.
        """
        dead_pid = 999_999  # Outside the default pid_max range; not running

        session_register(
            sid="aabbccdd", name="liveness-test", pid=dead_pid, pgid=dead_pid,
            mode="listen", proto="tcp4", lport=8080,
        )
        assert session_is_alive("aabbccdd") is False

        live_pid = os.getpid()
        assert session_update_process("aabbccdd", pid=live_pid, pgid=os.getpgid(0)) is True

        assert session_is_alive("aabbccdd") is True

# ==============================================================================
# FILE        : tests/unit/test_session_liveness.py
# ==============================================================================
# Synopsis    : Unit tests for field-based session liveness
# Description : session_is_alive() reads a session's process identity and
#               evaluates it, and the listing and detail views evaluate the
#               fields they have already read rather than re-opening the file.
#               These tests assert the field-based helper reports correctly for
#               live, dead, and group-only cases, and confirm that listing a
#               session does not re-read its file for the liveness check.
# Version     : 1.0.2
# ==============================================================================

"""Unit tests for field-based session liveness."""

from __future__ import annotations

import os
from unittest.mock import patch

from socat_manager.session import (
    process_alive,
    session_is_alive,
    session_list,
    session_register,
)


class TestProcessAlive:
    """Tests for process_alive(), which works from already-read fields."""

    def test_live_pid_reports_alive(self):
        """A running PID reports as alive."""
        assert process_alive(str(os.getpid()), "0") is True

    def test_dead_pid_reports_dead(self):
        """A PID with no process reports as dead."""
        assert process_alive("999999", "0") is False

    def test_empty_fields_report_dead(self):
        """Absent identity fields report as dead."""
        assert process_alive("", "") is False

    def test_non_numeric_pid_reports_dead(self):
        """A malformed PID field does not raise and reports as dead."""
        assert process_alive("not-a-number", "0") is False

    def test_group_fallback_when_pid_absent(self):
        """With no PID, a live process group reports as alive."""
        pgid = str(os.getpgid(0))
        assert process_alive("", pgid) is True

    def test_zero_group_is_not_probed(self):
        """A PGID of 0 is treated as absent, not probed."""
        assert process_alive("", "0") is False

    def test_exited_child_reports_dead_not_zombie(self):
        """An exited but uncollected child reports as dead.

        process_alive routes the primary check through the zombie-aware
        liveness primitive, so a socat child that has exited is not reported
        as a live zombie.
        """
        import subprocess
        import time

        from socat_manager.process import register_child

        proc = subprocess.Popen(["sleep", "0.05"], preexec_fn=os.setsid)
        register_child(proc)
        time.sleep(0.4)
        try:
            # Signal 0 still succeeds against the uncollected entry, but the
            # field-based liveness check reports the process as dead.
            os.kill(proc.pid, 0)
            assert process_alive(str(proc.pid), "0") is False
        finally:
            proc.wait()


class TestSessionIsAlive:
    """Tests for session_is_alive() end to end."""

    def test_live_session_reports_alive(self, paths):
        """A session whose PID is running reports as alive."""
        session_register(
            sid="1a2b3c4d", name="live", pid=os.getpid(), pgid=os.getpid(),
            mode="listen", proto="tcp4", lport=8080,
        )
        assert session_is_alive("1a2b3c4d") is True

    def test_dead_session_reports_dead(self, paths):
        """A session whose PID is not running reports as dead."""
        session_register(
            sid="5e6f7a8b", name="dead", pid=999999, pgid=999999,
            mode="listen", proto="tcp4", lport=8080,
        )
        assert session_is_alive("5e6f7a8b") is False

    def test_missing_session_reports_dead(self, paths):
        """A session ID with no file reports as dead."""
        assert session_is_alive("ffffffff") is False


class TestListingDoesNotRereadForLiveness:
    """Tests that listing evaluates liveness from the fields it already read."""

    def test_session_list_reads_each_file_once(self, paths):
        """Listing opens each session file once, not again for liveness.

        The listing loads every field in a single pass and evaluates liveness
        from those values. A second open per session for the alive check is the
        redundant read this addresses.
        """
        for sid in ("aa11bb22", "cc33dd44", "ee55ff66"):
            session_register(
                sid=sid, name=f"s-{sid}", pid=999999, pgid=999999,
                mode="listen", proto="tcp4", lport=8080,
            )

        opened: list[str] = []
        real_open = open

        def counting_open(path, *args, **kwargs):
            if str(path).endswith(".session"):
                opened.append(str(path))
            return real_open(path, *args, **kwargs)

        with patch("builtins.open", counting_open):
            session_list()

        # One open per session file — no second read for the liveness check.
        session_opens = [p for p in opened if p.endswith(".session")]
        assert len(session_opens) == 3
        assert len(set(session_opens)) == 3

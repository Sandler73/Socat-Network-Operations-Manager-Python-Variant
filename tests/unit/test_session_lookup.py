# ==============================================================================
# FILE        : tests/unit/test_session_lookup.py
# ==============================================================================
# Synopsis    : Unit tests for session lookup and enumeration
# Description : Session files are named {sid}.session, so the session ID is the
#               file stem and is identical to the SESSION_ID field by
#               construction. The lookup and enumeration functions derive the
#               ID from the file name rather than reading the SESSION_ID field
#               back. These tests confirm the lookups still return correct IDs,
#               that malformed file names are skipped, and that a lookup no
#               longer opens each candidate file a second time to recover the
#               ID.
# Version     : 1.0.1
# ==============================================================================

"""Unit tests for session lookup and enumeration."""

from __future__ import annotations

from unittest.mock import patch

from socat_manager.session import (
    _sid_from_file,
    session_find_by_name,
    session_find_by_pid,
    session_find_by_port,
    session_get_all_ids,
    session_register,
)


class TestSidFromFile:
    """Tests for _sid_from_file()."""

    def test_derives_sid_from_stem(self, paths):
        """The session ID is the file stem."""
        session_file = paths.session_dir / "a1b2c3d4.session"
        session_file.write_text("SESSION_ID=a1b2c3d4\n")
        assert _sid_from_file(session_file) == "a1b2c3d4"

    def test_rejects_traversal_in_name(self, paths):
        """A stem containing a parent reference is rejected."""
        # A stem such as 'a..b' contains a parent reference; it must not be
        # returned as a session ID.
        session_file = paths.session_dir / "a..b.session"
        assert _sid_from_file(session_file) == ""

    def test_accepts_readable_and_hex_stems(self, paths):
        """Both hex IDs and readable stems used as session IDs are accepted."""
        assert _sid_from_file(paths.session_dir / "a1b2c3d4.session") == "a1b2c3d4"
        assert _sid_from_file(paths.session_dir / "tcp11111.session") == "tcp11111"


class TestFindReturnsSessionIds:
    """Tests that lookups return the correct session IDs."""

    def test_find_by_name(self, paths):
        """Lookup by name returns the matching session ID."""
        session_register(
            sid="11aa22bb", name="web", pid=1000, pgid=1000,
            mode="listen", proto="tcp4", lport=8080,
        )
        assert session_find_by_name("web") == ["11aa22bb"]

    def test_find_by_port(self, paths):
        """Lookup by port returns the matching session ID."""
        session_register(
            sid="33cc44dd", name="p", pid=1000, pgid=1000,
            mode="listen", proto="tcp4", lport=9090,
        )
        assert session_find_by_port(9090) == ["33cc44dd"]

    def test_find_by_pid(self, paths):
        """Lookup by PID returns the matching session ID."""
        session_register(
            sid="55ee66ff", name="q", pid=4242, pgid=4242,
            mode="listen", proto="tcp4", lport=8080,
        )
        assert session_find_by_pid(4242) == ["55ee66ff"]

    def test_get_all_ids(self, paths):
        """Enumeration returns every session ID."""
        for sid in ("aa11bb22", "cc33dd44"):
            session_register(
                sid=sid, name=f"s-{sid}", pid=1000, pgid=1000,
                mode="listen", proto="tcp4", lport=8080,
            )
        assert sorted(session_get_all_ids()) == ["aa11bb22", "cc33dd44"]

    def test_no_match_returns_empty(self, paths):
        """A lookup with no match returns an empty list."""
        session_register(
            sid="77aa88bb", name="only", pid=1000, pgid=1000,
            mode="listen", proto="tcp4", lport=8080,
        )
        assert session_find_by_name("absent") == []
        assert session_find_by_port(1) == []
        assert session_find_by_pid(1) == []


class TestLookupDoesNotRereadForId:
    """Tests that a lookup does not re-open a matched file to recover the ID."""

    def test_find_by_name_reads_each_file_once(self, paths):
        """A name lookup opens each candidate file once, not twice.

        The ID of a matched file is its stem, so recovering it does not require
        a second read of the file.
        """
        for sid in ("aa11bb22", "cc33dd44", "ee55ff66"):
            session_register(
                sid=sid, name=f"s-{sid}", pid=1000, pgid=1000,
                mode="listen", proto="tcp4", lport=8080,
            )

        opened: list[str] = []
        real_open = open

        def counting_open(path, *args, **kwargs):
            if str(path).endswith(".session"):
                opened.append(str(path))
            return real_open(path, *args, **kwargs)

        # Match every file so the ID recovery path runs for each.
        with patch("builtins.open", counting_open):
            session_find_by_name("s-aa11bb22")

        # Each file opened once for the name read; the matched file is not
        # opened again to recover its ID.
        session_opens = [p for p in opened if p.endswith(".session")]
        assert len(session_opens) == 3
        assert len(set(session_opens)) == 3

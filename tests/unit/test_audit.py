# ==============================================================================
# FILE        : tests/unit/test_audit.py
# ==============================================================================
# Synopsis    : Unit tests for the SQLite audit backend
# Description : Covers enablement resolution (on by default, --no-audit and the
#               SOCAT_MANAGER_AUDIT env opt-out), event and session-history
#               writes, redaction, retention pruning, the read queries with
#               their filters, schema migration idempotency, file permissions,
#               concurrency under WAL, and failure isolation (a write against an
#               unwritable store logs and returns rather than raising).
# Version     : 1.0.2
# ==============================================================================

"""Unit tests for the SQLite audit backend."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Generator

import pytest

import socat_manager.audit as audit

_AUDIT_ENV = (
    "SOCAT_MANAGER_AUDIT",
    "SOCAT_MANAGER_AUDIT_REDACT",
    "SOCAT_MANAGER_AUDIT_RETENTION_DAYS",
    "SOCAT_MANAGER_AUDIT_DB",
)


@pytest.fixture(autouse=True)
def reset_audit_state() -> Generator[None, None, None]:
    """Reset audit module state and env between tests (paths are isolated already)."""
    saved = {k: os.environ.get(k) for k in _AUDIT_ENV}
    for k in _AUDIT_ENV:
        os.environ.pop(k, None)
    audit.set_cli_disabled(False)
    audit._pruned_this_process = False
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    audit.set_cli_disabled(False)
    audit._pruned_this_process = False


class TestEnablement:
    def test_on_by_default(self):
        assert audit.audit_enabled() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "OFF", "False"])
    def test_env_opt_out(self, val):
        os.environ["SOCAT_MANAGER_AUDIT"] = val
        assert audit.audit_enabled() is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "anything"])
    def test_env_truthy_stays_enabled(self, val):
        os.environ["SOCAT_MANAGER_AUDIT"] = val
        assert audit.audit_enabled() is True

    def test_cli_flag_disables(self):
        audit.set_cli_disabled(True)
        assert audit.audit_enabled() is False

    def test_cli_flag_overrides_even_when_env_truthy(self):
        os.environ["SOCAT_MANAGER_AUDIT"] = "1"
        audit.set_cli_disabled(True)
        assert audit.audit_enabled() is False


class TestEventWrites:
    def test_record_event_persists_row(self):
        audit.record_event(
            audit.EVENT_LAUNCH, session_id="deadbeef", name="t",
            mode="listen", proto="tcp4", lport=8080, detail="cmd",
        )
        rows = audit.query_events(session_id="deadbeef")
        assert len(rows) == 1
        assert rows[0]["event_type"] == "launch"
        assert rows[0]["lport"] == 8080

    def test_disabled_writes_nothing(self):
        audit.set_cli_disabled(True)
        audit.record_event(audit.EVENT_LAUNCH, session_id="deadbeef")
        audit.set_cli_disabled(False)
        assert audit.query_events(session_id="deadbeef") == []

    def test_session_start_and_end(self):
        audit.record_session_start("cafe1234", "n", "forward", "tcp4", 8080, "1.2.3.4", 80)
        audit.record_session_end("cafe1234", "stopped")
        hist = audit.query_history(session_id="cafe1234")
        assert len(hist) == 1
        assert hist[0]["final_state"] == "stopped"
        assert hist[0]["ended_ts"] is not None

    def test_session_start_is_insert_or_ignore(self):
        audit.record_session_start("aaaa0001", "first", "listen", "tcp4", 8080)
        audit.record_session_start("aaaa0001", "second", "listen", "tcp4", 8080)
        hist = audit.query_history(session_id="aaaa0001")
        assert len(hist) == 1
        assert hist[0]["name"] == "first"  # original preserved

    def test_restart_increments_count(self):
        audit.record_session_start("bbbb0002", "n", "listen", "tcp4", 8080)
        audit.record_restart("bbbb0002")
        audit.record_restart("bbbb0002")
        hist = audit.query_history(session_id="bbbb0002")
        assert hist[0]["restart_count"] == 2


class TestRedaction:
    def test_no_redaction_by_default(self):
        audit.record_event(
            audit.EVENT_LAUNCH, session_id="s1", rhost="10.0.0.5",
            detail="socat ... TCP4:10.0.0.5:22",
        )
        row = audit.query_events(session_id="s1")[0]
        assert row["rhost"] == "10.0.0.5"
        assert "10.0.0.5" in row["detail"]
        assert row["redacted"] == 0

    def test_redaction_masks_host_and_detail(self):
        os.environ["SOCAT_MANAGER_AUDIT_REDACT"] = "1"
        audit.record_event(
            audit.EVENT_LAUNCH, session_id="s2", rhost="10.0.0.9",
            detail="socat ... TCP4:10.0.0.9:80",
        )
        row = audit.query_events(session_id="s2")[0]
        assert row["rhost"] == "HOST-REDACTED"
        assert "10.0.0.9" not in row["detail"]
        assert row["redacted"] == 1


class TestRetention:
    def test_keep_forever_by_default(self):
        assert audit.retention_days() == 0

    def test_prune_deletes_old_rows(self):
        # Seed rows directly with an old timestamp, then prune.
        audit.record_event(audit.EVENT_LAUNCH, session_id="old1")
        db = audit.audit_db_path()
        with sqlite3.connect(str(db)) as conn:
            conn.execute("UPDATE events SET ts = '2000-01-01T00:00:00Z'")
            conn.commit()
        audit.record_event(audit.EVENT_LAUNCH, session_id="new1")  # recent
        deleted = audit.prune(days=30)
        assert deleted == 1
        remaining = audit.query_events(limit=0)
        assert all(r["session_id"] != "old1" for r in remaining)

    def test_prune_zero_days_is_noop(self):
        audit.record_event(audit.EVENT_LAUNCH, session_id="keep")
        assert audit.prune(days=0) == 0
        assert len(audit.query_events(limit=0)) == 1

    def test_retention_env_parsed(self):
        os.environ["SOCAT_MANAGER_AUDIT_RETENTION_DAYS"] = "45"
        assert audit.retention_days() == 45
        os.environ["SOCAT_MANAGER_AUDIT_RETENTION_DAYS"] = "-5"
        assert audit.retention_days() == 0
        os.environ["SOCAT_MANAGER_AUDIT_RETENTION_DAYS"] = "junk"
        assert audit.retention_days() == 0


class TestQueries:
    def _seed(self):
        audit.record_event(audit.EVENT_LAUNCH, session_id="q1", name="a")
        audit.record_event(audit.EVENT_CRASH, session_id="q1", name="a")
        audit.record_event(audit.EVENT_LAUNCH, session_id="q2", name="b")

    def test_filter_by_session(self):
        self._seed()
        assert len(audit.query_events(session_id="q1")) == 2

    def test_filter_by_type(self):
        self._seed()
        rows = audit.query_events(event_type="crash")
        assert len(rows) == 1 and rows[0]["session_id"] == "q1"

    def test_limit(self):
        self._seed()
        assert len(audit.query_events(limit=1)) == 1

    def test_limit_zero_returns_all(self):
        self._seed()
        assert len(audit.query_events(limit=0)) == 3

    def test_since_filter(self):
        self._seed()
        assert len(audit.query_events(since="2000-01-01")) == 3
        assert len(audit.query_events(since="2999-01-01")) == 0

    def test_most_recent_first(self):
        self._seed()
        rows = audit.query_events()
        assert rows[0]["session_id"] == "q2"  # last inserted


class TestSchemaAndPermissions:
    def test_schema_version_set(self):
        audit.record_event(audit.EVENT_LAUNCH, session_id="s")
        db = audit.audit_db_path()
        with sqlite3.connect(str(db)) as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == audit.SCHEMA_VERSION

    def test_reconnect_is_idempotent(self):
        audit.record_event(audit.EVENT_LAUNCH, session_id="one")
        audit.record_event(audit.EVENT_STOP, session_id="one")  # second connect
        assert len(audit.query_events(session_id="one")) == 2

    def test_db_and_dir_permissions(self):
        audit.record_event(audit.EVENT_LAUNCH, session_id="p")
        db = audit.audit_db_path()
        assert (os.stat(db).st_mode & 0o777) == 0o600
        assert (os.stat(db.parent).st_mode & 0o777) == 0o700


class TestFailureIsolation:
    def test_write_to_unwritable_path_does_not_raise(self):
        # Point the DB at a path whose parent cannot be created (a file).
        blocker = Path(audit.get_paths().base_dir) / "blocker"
        blocker.write_text("x")
        os.environ["SOCAT_MANAGER_AUDIT_DB"] = str(blocker / "sub" / "audit.db")
        # Should log a warning internally and return without raising.
        audit.record_event(audit.EVENT_LAUNCH, session_id="x")
        audit.record_session_start("x", "n", "listen", "tcp4", 8080)
        # Queries against the broken path also degrade to empty, not raise.
        assert audit.query_events() == []

    def test_query_on_missing_store_returns_empty(self):
        os.environ["SOCAT_MANAGER_AUDIT_DB"] = str(
            Path(audit.get_paths().base_dir) / "nope" / "missing.db"
        )
        # No rows, but a fresh DB is created by _connect; result is just empty.
        assert audit.query_events() == []


class TestConcurrency:
    def test_concurrent_writes_are_all_recorded(self):
        errors: list[str] = []

        def worker(idx: int) -> None:
            try:
                for j in range(10):
                    audit.record_event(
                        audit.EVENT_LAUNCH, session_id=f"c{idx:02d}{j}", name="x"
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(audit.query_events(limit=0)) == 100

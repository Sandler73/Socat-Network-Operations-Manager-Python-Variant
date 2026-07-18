# ==============================================================================
# MODULE      : socat_manager/audit.py
# ==============================================================================
# Synopsis    : Persistent SQLite audit store for after-action review.
# Description : Records framework events — session launches, stops, watchdog
#               restarts, crash detections, and errors — to a SQLite database
#               so that a durable history survives the removal of the real-time
#               session files. The store supplements, and never replaces, the
#               KEY=VALUE session files that remain the source of truth for live
#               state and cross-variant interoperability.
#
#               The store is enabled by default and can be disabled with the
#               SOCAT_MANAGER_AUDIT=0 environment variable or the global
#               --no-audit flag. Full operational detail is recorded by default;
#               SOCAT_MANAGER_AUDIT_REDACT=1 masks remote endpoints. History is
#               kept forever by default; SOCAT_MANAGER_AUDIT_RETENTION_DAYS>0
#               enables age-based pruning.
#
#               Every public function is failure-isolated: any database error is
#               logged at WARNING and swallowed so that auditing can never break
#               an operation. sqlite3 is part of the Python standard library, so
#               this adds no external runtime dependency.
# Notes       : - WAL journal mode allows concurrent CLI invocations and the
#                 watchdog threads to write without blocking each other.
#               - Connections are short-lived, one per operation, never shared
#                 across threads.
#               - The audit directory is created 0o700 and the database 0o600.
# Version     : 1.0.2
# ==============================================================================

"""Persistent SQLite audit store for after-action review."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

from socat_manager.logging_setup import get_paths, log_debug, log_warning

# ==============================================================================
# SCHEMA AND EVENT TYPES
# ==============================================================================

# Bumped when the schema changes; migrations key off PRAGMA user_version.
SCHEMA_VERSION: Final[int] = 1

# Recognized event types (free-form column, these are the values emitted).
EVENT_LAUNCH: Final[str] = "launch"
EVENT_STOP: Final[str] = "stop"
EVENT_STOP_FAILED: Final[str] = "stop_failed"
EVENT_RESTART: Final[str] = "restart"
EVENT_CRASH: Final[str] = "crash"
EVENT_CONFIG_CHANGE: Final[str] = "config_change"
EVENT_ERROR: Final[str] = "error"

# Fields accepted by record_event(), in the column order of the events table.
_EVENT_FIELDS: Final[tuple[str, ...]] = (
    "correlation_id",
    "session_id",
    "name",
    "mode",
    "proto",
    "lport",
    "rhost",
    "rport",
    "pid",
    "pgid",
    "detail",
)

_REDACTED_TOKEN: Final[str] = "HOST-REDACTED"  # noqa: S105 - a display token, not a credential

# Precomputed INSERT statement. The column list is built once from the constant
# _EVENT_FIELDS tuple (never from user input); every value is bound with a ?
# placeholder, so this is not an injection surface.
_INSERT_EVENT_SQL: Final[str] = (
    "INSERT INTO events (ts, event_type, redacted, "  # noqa: S608 - constant columns, ? placeholders
    + ", ".join(_EVENT_FIELDS)
    + ") VALUES (?, ?, ?, "
    + ", ".join("?" for _ in _EVENT_FIELDS)
    + ")"
)

# ==============================================================================
# MODULE STATE
# ==============================================================================

# Disabled explicitly by the --no-audit CLI flag for this invocation.
_disabled_by_flag: bool = False

# Retention prune runs at most once per process, after a successful write.
_pruned_this_process: bool = False
_state_lock: threading.Lock = threading.Lock()


# ==============================================================================
# ENABLEMENT AND CONFIGURATION
# ==============================================================================

def set_cli_disabled(disabled: bool) -> None:
    """Record whether the --no-audit flag disabled auditing for this run.

    Args:
        disabled: True when --no-audit was supplied.
    """
    global _disabled_by_flag
    _disabled_by_flag = disabled


def audit_enabled() -> bool:
    """Report whether auditing is active.

    Auditing is on by default. It is off when the --no-audit flag was supplied
    or when SOCAT_MANAGER_AUDIT is set to a false-like value (0, false, no, off).

    Returns:
        True if events should be recorded.
    """
    if _disabled_by_flag:
        return False
    raw: str = os.environ.get("SOCAT_MANAGER_AUDIT", "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _redaction_enabled() -> bool:
    """Report whether remote endpoints should be masked in recorded events."""
    raw: str = os.environ.get("SOCAT_MANAGER_AUDIT_REDACT", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def retention_days() -> int:
    """Return the configured retention window in days (0 means keep forever)."""
    raw: str = os.environ.get("SOCAT_MANAGER_AUDIT_RETENTION_DAYS", "").strip()
    if not raw:
        return 0
    try:
        return max(int(raw), 0)
    except ValueError:
        return 0


def audit_db_path() -> Path:
    """Return the effective audit database path.

    SOCAT_MANAGER_AUDIT_DB overrides the default location under the runtime
    base directory.
    """
    override: str = os.environ.get("SOCAT_MANAGER_AUDIT_DB", "").strip()
    if override:
        return Path(override)
    return get_paths().audit_db


# ==============================================================================
# CONNECTION AND SCHEMA
# ==============================================================================

def _now() -> str:
    """Return the current time as an ISO-8601 UTC string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    """Open the audit database, creating the directory and schema as needed.

    The connection is configured for concurrent multi-process use via WAL and a
    busy timeout, and rows are returned as sqlite3.Row for name access.

    Returns:
        An open sqlite3 connection.
    """
    db_path: Path = audit_db_path()
    audit_dir: Path = db_path.parent

    # Create the directory 0o700 if absent.
    if not audit_dir.is_dir():
        audit_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(str(audit_dir), 0o700)
        except OSError:
            pass

    existed: bool = db_path.exists()

    conn: sqlite3.Connection = sqlite3.connect(str(db_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # Restrict the database file to the owner on first creation.
    if not existed:
        try:
            os.chmod(str(db_path), 0o600)
        except OSError:
            pass

    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables and apply migrations, keyed off PRAGMA user_version."""
    version: int = int(conn.execute("PRAGMA user_version").fetchone()[0])

    if version < 1:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                ts             TEXT NOT NULL,
                correlation_id TEXT,
                event_type     TEXT NOT NULL,
                session_id     TEXT,
                name           TEXT,
                mode           TEXT,
                proto          TEXT,
                lport          INTEGER,
                rhost          TEXT,
                rport          INTEGER,
                pid            INTEGER,
                pgid           INTEGER,
                detail         TEXT,
                redacted       INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

            CREATE TABLE IF NOT EXISTS sessions_history (
                session_id    TEXT PRIMARY KEY,
                name          TEXT,
                mode          TEXT,
                proto         TEXT,
                lport         INTEGER,
                rhost         TEXT,
                rport         INTEGER,
                created_ts    TEXT NOT NULL,
                ended_ts      TEXT,
                restart_count INTEGER NOT NULL DEFAULT 0,
                final_state   TEXT NOT NULL DEFAULT 'running'
            );
            """
        )
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        conn.commit()


# ==============================================================================
# REDACTION
# ==============================================================================

def _apply_redaction(fields: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Mask the remote endpoint in a copy of the fields when redaction is on.

    Replaces the remote host in both the rhost column and any occurrence within
    the detail string with a fixed token. The remote port is retained, as are
    certificate and key paths — the framework never records key material.

    Returns:
        A tuple of (possibly-redacted fields copy, redacted flag).
    """
    if not _redaction_enabled():
        return fields, False

    redacted: dict[str, Any] = dict(fields)
    rhost: Any = redacted.get("rhost")
    if rhost:
        detail: Any = redacted.get("detail")
        if isinstance(detail, str) and str(rhost) in detail:
            redacted["detail"] = detail.replace(str(rhost), _REDACTED_TOKEN)
        redacted["rhost"] = _REDACTED_TOKEN

    return redacted, True


# ==============================================================================
# WRITE OPERATIONS
# ==============================================================================

def record_event(event_type: str, **fields: Any) -> None:
    """Record a single audit event. No-op when auditing is disabled.

    Any database error is logged at WARNING and swallowed so that a failure to
    audit never propagates into the operation being audited.

    Args:
        event_type: One of the EVENT_* constants.
        **fields: Any subset of _EVENT_FIELDS (correlation_id, session_id,
                  name, mode, proto, lport, rhost, rport, pid, pgid, detail).
    """
    if not audit_enabled():
        return

    try:
        clean, redacted = _apply_redaction(fields)
        values: list[Any] = [clean.get(name) for name in _EVENT_FIELDS]

        conn: sqlite3.Connection = _connect()
        try:
            with conn:
                conn.execute(
                    _INSERT_EVENT_SQL,
                    [_now(), event_type, 1 if redacted else 0, *values],
                )
        finally:
            conn.close()

        _maybe_prune()
    except Exception as exc:  # noqa: BLE001 - auditing must never raise
        log_warning(f"Audit event not recorded ({event_type}): {exc}", "audit")


def record_session_start(
    session_id: str,
    name: str,
    mode: str,
    proto: str,
    lport: int,
    rhost: str = "",
    rport: int = 0,
) -> None:
    """Insert a sessions_history row for a newly launched session.

    Uses INSERT OR IGNORE so a re-launch after a watchdog restart does not
    overwrite the original creation time. No-op when disabled; never raises.
    """
    if not audit_enabled():
        return

    try:
        fields, _ = _apply_redaction({"rhost": rhost, "detail": None})
        stored_rhost: Any = fields.get("rhost")

        conn: sqlite3.Connection = _connect()
        try:
            with conn:
                conn.execute(
                    "INSERT OR IGNORE INTO sessions_history "
                    "(session_id, name, mode, proto, lport, rhost, rport, "
                    "created_ts, final_state) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running')",
                    [session_id, name, mode, proto, lport, stored_rhost,
                     rport or None, _now()],
                )
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - auditing must never raise
        log_warning(f"Audit session start not recorded ({session_id}): {exc}", "audit")


def record_session_end(session_id: str, final_state: str) -> None:
    """Mark a session ended in sessions_history. No-op when disabled; never raises."""
    if not audit_enabled():
        return

    try:
        conn: sqlite3.Connection = _connect()
        try:
            with conn:
                conn.execute(
                    "UPDATE sessions_history SET ended_ts = ?, final_state = ? "
                    "WHERE session_id = ?",
                    [_now(), final_state, session_id],
                )
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - auditing must never raise
        log_warning(f"Audit session end not recorded ({session_id}): {exc}", "audit")


def record_restart(session_id: str) -> None:
    """Increment a session's restart counter. No-op when disabled; never raises."""
    if not audit_enabled():
        return

    try:
        conn: sqlite3.Connection = _connect()
        try:
            with conn:
                conn.execute(
                    "UPDATE sessions_history "
                    "SET restart_count = restart_count + 1 WHERE session_id = ?",
                    [session_id],
                )
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - auditing must never raise
        log_warning(f"Audit restart not recorded ({session_id}): {exc}", "audit")


# ==============================================================================
# RETENTION
# ==============================================================================

def _maybe_prune() -> None:
    """Prune old rows once per process when a finite retention window is set."""
    global _pruned_this_process

    days: int = retention_days()
    if days <= 0:
        return

    with _state_lock:
        if _pruned_this_process:
            return
        _pruned_this_process = True

    prune(days)


def prune(days: int) -> int:
    """Delete events older than the given number of days.

    Args:
        days: Retention window; values <= 0 delete nothing.

    Returns:
        The number of event rows deleted (0 on any error or when disabled).
    """
    if days <= 0:
        return 0

    cutoff: str = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        conn: sqlite3.Connection = _connect()
        try:
            with conn:
                cursor: sqlite3.Cursor = conn.execute(
                    "DELETE FROM events WHERE ts < ?", [cutoff]
                )
                deleted: int = cursor.rowcount
        finally:
            conn.close()
        if deleted:
            log_debug(f"Pruned {deleted} audit events older than {days}d", "audit")
        return deleted
    except Exception as exc:  # noqa: BLE001 - auditing must never raise
        log_warning(f"Audit prune failed: {exc}", "audit")
        return 0


# ==============================================================================
# READ OPERATIONS
# ==============================================================================

def query_events(
    session_id: str = "",
    event_type: str = "",
    since: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return recorded events, most recent first, filtered by the arguments.

    Args:
        session_id: Restrict to one session ID.
        event_type: Restrict to one event type.
        since: Restrict to events at or after this ISO-8601 timestamp/date.
        limit: Maximum rows to return (<= 0 means no limit).

    Returns:
        A list of row dicts (empty on error).
    """
    try:
        clauses: list[str] = []
        params: list[Any] = []
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if since:
            clauses.append("ts >= ?")
            params.append(since)

        where: str = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        limit_sql: str = " LIMIT ?" if limit and limit > 0 else ""
        if limit and limit > 0:
            params.append(limit)

        conn: sqlite3.Connection = _connect()
        try:
            # `where` and `limit_sql` are assembled only from the hardcoded
            # fragments above; every filter value is bound via ? in `params`.
            rows = conn.execute(
                f"SELECT * FROM events{where} ORDER BY id DESC{limit_sql}",  # noqa: S608
                params,
            ).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]
    except Exception as exc:  # noqa: BLE001 - reads must not raise into the CLI
        log_warning(f"Audit query failed: {exc}", "audit")
        return []


def query_history(session_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Return session lifecycle summaries, most recent first.

    Args:
        session_id: Restrict to one session ID.
        limit: Maximum rows (<= 0 means no limit).

    Returns:
        A list of row dicts (empty on error).
    """
    try:
        where: str = " WHERE session_id = ?" if session_id else ""
        params: list[Any] = [session_id] if session_id else []
        limit_sql: str = ""
        if limit and limit > 0:
            limit_sql = " LIMIT ?"
            params.append(limit)

        conn: sqlite3.Connection = _connect()
        try:
            # `where` and `limit_sql` are hardcoded fragments; the session_id
            # and limit values are bound via ? in `params`.
            rows = conn.execute(
                f"SELECT * FROM sessions_history{where} "  # noqa: S608
                f"ORDER BY created_ts DESC{limit_sql}",
                params,
            ).fetchall()
        finally:
            conn.close()
        return [dict(row) for row in rows]
    except Exception as exc:  # noqa: BLE001 - reads must not raise into the CLI
        log_warning(f"Audit history query failed: {exc}", "audit")
        return []

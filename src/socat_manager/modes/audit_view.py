# ==============================================================================
# MODULE      : socat_manager/modes/audit_view.py
# ==============================================================================
# Synopsis    : Read-only display handler for the audit subcommand.
# Description : Renders the persistent audit history — recorded events or the
#               per-session lifecycle summary — as a table or as JSON, and
#               applies the configured retention when --prune is given. This
#               handler never modifies live sessions; it only reads the audit
#               store (and prunes it on explicit request).
# Notes       : Query and prune operations are failure-isolated in the audit
#               module, so this handler degrades gracefully to an empty result
#               rather than raising if the store is unavailable.
# Version     : 1.0.1
# ==============================================================================

"""Read-only display handler for the audit subcommand."""

from __future__ import annotations

import json
from typing import Any

from socat_manager import audit
from socat_manager.logging_setup import log_info, print_section


def _print_events(rows: list[dict[str, Any]]) -> None:
    """Print event rows as an aligned table."""
    if not rows:
        log_info("No audit events match the query.", "audit")
        return

    print_section("Audit Events")
    header: str = f"{'TIMESTAMP':<21} {'EVENT':<12} {'SID':<10} {'NAME':<16} DETAIL"
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for row in rows:
        ts: str = str(row.get("ts", ""))
        event: str = str(row.get("event_type", ""))
        sid: str = str(row.get("session_id") or "")
        name: str = str(row.get("name") or "")
        detail: str = str(row.get("detail") or "")
        if len(name) > 16:
            name = name[:15] + "…"
        if len(detail) > 60:
            detail = detail[:59] + "…"
        print(f"  {ts:<21} {event:<12} {sid:<10} {name:<16} {detail}")
    print(f"\n  {len(rows)} event(s)")


def _print_history(rows: list[dict[str, Any]]) -> None:
    """Print session lifecycle summary rows as an aligned table."""
    if not rows:
        log_info("No session history recorded.", "audit")
        return

    print_section("Session History")
    header: str = (
        f"{'SID':<10} {'NAME':<16} {'MODE':<9} {'PROTO':<6} "
        f"{'RESTARTS':<8} {'STATE':<18} CREATED"
    )
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for row in rows:
        sid: str = str(row.get("session_id") or "")
        name: str = str(row.get("name") or "")
        mode: str = str(row.get("mode") or "")
        proto: str = str(row.get("proto") or "")
        restarts: str = str(row.get("restart_count", 0))
        state: str = str(row.get("final_state") or "")
        created: str = str(row.get("created_ts") or "")
        if len(name) > 16:
            name = name[:15] + "…"
        print(
            f"  {sid:<10} {name:<16} {mode:<9} {proto:<6} "
            f"{restarts:<8} {state:<18} {created}"
        )
    print(f"\n  {len(rows)} session(s)")


def mode_audit(args: Any) -> None:
    """Handle the audit subcommand: prune, or query events/history and display.

    Args:
        args: Parsed argparse Namespace with audit-mode attributes
              (session, event_type, since, limit, history, as_json, prune).
    """
    # --- Prune on explicit request ---
    if getattr(args, "prune", False):
        days: int = audit.retention_days()
        if days <= 0:
            log_info(
                "Retention is set to keep forever "
                "(SOCAT_MANAGER_AUDIT_RETENTION_DAYS is 0 or unset); nothing pruned.",
                "audit",
            )
            return
        deleted: int = audit.prune(days)
        log_info(f"Pruned {deleted} event(s) older than {days} day(s).", "audit")
        return

    session: str = getattr(args, "session", None) or ""
    limit: int = getattr(args, "limit", 50)
    as_json: bool = bool(getattr(args, "as_json", False))

    # --- History view ---
    if getattr(args, "history", False):
        rows: list[dict[str, Any]] = audit.query_history(
            session_id=session, limit=limit
        )
        if as_json:
            print(json.dumps(rows, indent=2))
        else:
            _print_history(rows)
        return

    # --- Event view ---
    events: list[dict[str, Any]] = audit.query_events(
        session_id=session,
        event_type=getattr(args, "event_type", None) or "",
        since=getattr(args, "since", None) or "",
        limit=limit,
    )
    if as_json:
        print(json.dumps(events, indent=2))
    else:
        _print_events(events)

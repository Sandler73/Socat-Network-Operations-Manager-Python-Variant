# ==============================================================================
# MODULE      : socat_manager/modes/stop.py
# ==============================================================================
# Synopsis    : Stop mode handler — session termination
# Description : Terminates sessions by session ID, name, port, PID, or all.
#               Protocol-aware: stopping TCP on a shared port does NOT affect
#               UDP, and vice versa. Exact parity with bash mode_stop()
#               (lines 2612-2768).
#
# Notes       : - The actual 9-step stop sequence is in process.stop_session()
#               - This module handles selector routing (which sessions to stop)
#               - --pid is validated as numeric before any use (SEC-01)
#               - After --all, orphaned socat processes are reported
#
# Version     : 1.0.1
# ==============================================================================

"""Stop mode handler — session termination by various selectors."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from socat_manager.logging_setup import (
    _ensure_dirs,
    get_paths,
    log_error,
    log_info,
    log_warning,
    print_banner,
    print_section,
)
from socat_manager.process import stop_session
from socat_manager.session import (
    session_cleanup_dead,
    session_find_by_name,
    session_find_by_pid,
    session_find_by_port,
    session_get_all_ids,
)
from socat_manager.validation import ValidationError, validate_port


def mode_stop(args: Any) -> None:
    """Execute stop mode: terminate sessions.

    Selectors (mutually prioritized):
        positional: Session ID or name (first non-flag argument)
        --all:      Stop all registered sessions
        --name:     Stop by session name
        --port:     Stop all sessions on a port (all protocols)
        --pid:      Stop by PID

    Args:
        args: Parsed argparse Namespace with stop-mode attributes:
              target (positional), all, name, port, pid, verbose.

    Raises:
        SystemExit: If no selector specified or on validation failure.
    """
    _ensure_dirs()
    paths = get_paths()

    stop_all: bool = bool(args.all)
    stop_name: str = args.name or ""
    stop_port: str = args.port or ""
    stop_pid: str = args.pid or ""
    target: str = args.target or ""

    # Require at least one selector
    if not stop_all and not stop_name and not stop_port and not stop_pid and not target:
        log_error(
            "Specify what to stop: <session-id>, --all, --name, --port, or --pid",
            "stop",
        )
        log_info("Run 'socat-manager status' to see active sessions")
        sys.exit(1)

    print_banner("Session Stop")
    stopped: int = 0
    failed: int = 0

    if stop_all:
        # --- Stop all registered sessions ---
        print_section("Stopping All Sessions")

        all_sids: list[str] = session_get_all_ids()
        if not all_sids:
            log_info("No sessions to stop")
        else:
            for sid in all_sids:
                if stop_session(sid):
                    stopped += 1
                else:
                    failed += 1

        # Safety net: report orphaned socat processes
        _cleanup_orphaned_socat()

    elif target:
        # --- Stop by positional argument (session ID or name) ---
        # Try as session ID first (8-char hex)
        if (
            len(target) == 8
            and all(c in "0123456789abcdef" for c in target)
            and (paths.session_dir / f"{target}.session").is_file()
        ):
            if stop_session(target):
                stopped += 1
            else:
                failed += 1
        else:
            # Try as session name
            found_sids: list[str] = session_find_by_name(target)
            if found_sids:
                for sid in found_sids:
                    if stop_session(sid):
                        stopped += 1
                    else:
                        failed += 1
            else:
                log_warning(f"Session '{target}' not found")
                failed += 1

    elif stop_name:
        # --- Stop by session name ---
        name_sids: list[str] = session_find_by_name(stop_name)
        if not name_sids:
            log_warning(f"No sessions found with name '{stop_name}'")
            failed += 1
        else:
            for sid in name_sids:
                if stop_session(sid):
                    stopped += 1
                else:
                    failed += 1

    elif stop_port:
        # --- Stop all sessions on a port (all protocols) ---
        try:
            validate_port(stop_port)
        except ValidationError as exc:
            log_error(str(exc), "stop")
            sys.exit(1)

        port_sids: list[str] = session_find_by_port(stop_port)
        if not port_sids:
            log_warning(f"No sessions found on port {stop_port}")
            failed += 1
        else:
            for sid in port_sids:
                if stop_session(sid):
                    stopped += 1
                else:
                    failed += 1

    elif stop_pid:
        # --- Stop by PID ---
        # Validate PID is numeric (prevents injection into kill calls)
        if not stop_pid.strip().isdigit():
            log_error(f"Invalid PID '{stop_pid}': must be a number", "stop")
            sys.exit(1)

        pid_sids: list[str] = session_find_by_pid(stop_pid)
        if not pid_sids:
            log_warning(f"No sessions found with PID {stop_pid}")
            failed += 1
        else:
            for sid in pid_sids:
                if stop_session(sid):
                    stopped += 1
                else:
                    failed += 1

    print("", file=sys.stderr)
    log_info(f"Stop summary: {stopped} stopped, {failed} failed")

    # Clean up remaining dead session files
    session_cleanup_dead()


def _cleanup_orphaned_socat() -> None:
    """Report any orphaned socat processes not tracked by sessions.

    This is a safety net after --all stop. It checks for socat processes
    still running and logs warnings but does NOT kill them automatically
    (they may belong to other users or instances).
    """
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["pgrep", "-a", "socat"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            log_warning("Orphaned socat processes detected:", "stop")
            for line in result.stdout.strip().splitlines():
                log_warning(f"  {line}", "stop")
            log_info(
                "These may be from other users or unmanaged instances. "
                "Use 'pkill socat' to force-stop all socat processes."
            )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # pgrep not available — skip

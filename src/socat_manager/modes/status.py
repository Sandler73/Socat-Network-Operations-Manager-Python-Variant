# ==============================================================================
# MODULE      : socat_manager/modes/status.py
# ==============================================================================
# Synopsis    : Status mode handler — session listing, detail, and cleanup
# Description : Displays active sessions, detailed session info, or cleans up
#               dead sessions. Accepts optional positional argument matched
#               against session ID, name, or port in that order.
#               Exact parity with bash mode_status() (lines 2504-2581).
#
#
#               - Target resolution: session ID → session name → port
#               - Detail view: 5 sections (metadata, process, port, command, logs)
#               - --cleanup removes dead sessions with advisory lock
#               - Process tree display: pstree → ps --forest → ps (fallback chain)
#
# Version     : 1.0.1
# ==============================================================================

"""Status mode handler — session listing, detail, and cleanup."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from socat_manager.logging_setup import (
    _ensure_dirs,
    get_paths,
    log_error,
    log_info,
    print_banner,
    print_section,
)
from socat_manager.session import (
    session_cleanup_dead,
    session_detail,
    session_find_by_name,
    session_find_by_port,
    session_list,
)


def mode_status(args: Any) -> None:
    """Execute status mode: display session information.

    Lookup priority for the optional positional argument:
        1. Session ID (8-char hex, exact file match)
        2. Session name (exact match across all session files)
        3. Port number (may match multiple sessions for dual-stack)

    Args:
        args: Parsed argparse Namespace with status-mode attributes:
              target (positional), cleanup, verbose.
    """
    _ensure_dirs()
    paths = get_paths()

    # --- Run cleanup if requested ---
    if args.cleanup:
        session_cleanup_dead()

    # --- Specific session lookup ---
    target: str = args.target or ""

    if target:
        print_banner("Session Status")

        # Try as session ID first (8-char hex)
        if len(target) == 8 and all(c in "0123456789abcdef" for c in target):
            session_file = paths.session_dir / f"{target}.session"
            if session_file.is_file():
                session_detail(target)
                return

        # Try as session name
        found_sids: list[str] = session_find_by_name(target)
        if found_sids:
            session_detail(found_sids[0])
            return

        # Try as port number
        if target.isdigit():
            port_sids: list[str] = session_find_by_port(target)
            if port_sids:
                for psid in port_sids:
                    session_detail(psid)
                    print("", file=sys.stderr)
                return

        log_error(
            f"Session '{target}' not found (searched by ID, name, and port)",
            "status",
        )
        log_info("Run 'socat-manager status' to see all sessions")
        sys.exit(1)

    # --- No specific session: show overview ---
    print_banner("Session Status")
    session_list()

    # Show system listeners if verbose
    if args.verbose:
        print_section("System Listeners (socat)")
        _show_system_listeners()


def _show_system_listeners() -> None:
    """Display socat processes detected by ss or netstat.

    Used in verbose mode to show system-level listener information.
    """
    try:
        # TCP listeners
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            tcp_lines: list[str] = [
                line for line in result.stdout.splitlines()
                if "socat" in line.lower()
            ]
            if tcp_lines:
                for line in tcp_lines:
                    print(f"  {line}", file=sys.stderr)
            else:
                print("  (no socat TCP listeners detected via ss)", file=sys.stderr)

        print("", file=sys.stderr)

        # UDP listeners
        result = subprocess.run(
            ["ss", "-ulnp"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            udp_lines: list[str] = [
                line for line in result.stdout.splitlines()
                if "socat" in line.lower()
            ]
            if udp_lines:
                for line in udp_lines:
                    print(f"  {line}", file=sys.stderr)
            else:
                print("  (no socat UDP listeners detected via ss)", file=sys.stderr)

    except FileNotFoundError:
        # Try netstat as fallback
        try:
            result = subprocess.run(
                ["netstat", "-tulnp"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                socat_lines: list[str] = [
                    line for line in result.stdout.splitlines()
                    if "socat" in line.lower()
                ]
                if socat_lines:
                    for line in socat_lines:
                        print(f"  {line}", file=sys.stderr)
                else:
                    print("  (no socat listeners detected)", file=sys.stderr)
        except FileNotFoundError:
            print("  (neither ss nor netstat available)", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("  (ss command timed out)", file=sys.stderr)

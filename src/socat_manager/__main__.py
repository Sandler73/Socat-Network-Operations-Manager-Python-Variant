# ==============================================================================
# MODULE      : socat_manager/__main__.py
# ==============================================================================
# Synopsis    : Entry point for the Socat Network Operations Manager
# Description : Handles CLI argument parsing, mode dispatch, and interactive
#               menu fallback. Installs signal handlers for clean shutdown.
#               Matches bash main() dispatcher (lines 4398-4462).
#
# Execution   : python3 -m socat_manager <MODE> [OPTIONS]
#               python3 -m socat_manager              (interactive menu)
#
# Notes       : - No arguments → interactive menu
#               - 'menu' subcommand → interactive menu
#               - All other modes dispatched to mode handlers
#               - socat availability checked for operational modes only
#                 (not for status, stop, help, version)
#               - Signal handlers: SIGINT, SIGTERM for clean shutdown
#               - No EXIT trap (sessions survive script exit via setsid)
#
# Version     : 1.0.2
# ==============================================================================

"""Entry point for socat-manager: CLI dispatch and menu fallback."""

from __future__ import annotations

import shutil
import signal
import sys
from typing import Any

from socat_manager import __version__
from socat_manager.cli import build_parser
from socat_manager.config import COLORS
from socat_manager.logging_setup import (
    USE_COLOR,
    _ensure_dirs,
    log_critical,
    log_debug,
    log_info,
    setup_logging,
)

# ==============================================================================
# SIGNAL HANDLERS
# ==============================================================================

def _handle_sigterm(signum: int, frame: Any) -> None:
    """Handle SIGTERM for clean shutdown.

    Does NOT stop managed sessions (they survive via setsid).
    Only cleans up the management script itself.

    Args:
        signum: Signal number received.
        frame: Current stack frame (unused).
    """
    log_info("Received SIGTERM — management script exiting", "signal")
    sys.exit(0)


def _handle_sigint(signum: int, frame: Any) -> None:
    """Handle SIGINT (Ctrl+C) for clean exit.

    Args:
        signum: Signal number received.
        frame: Current stack frame (unused).
    """
    print("", file=sys.stderr)
    log_info("Interrupted (Ctrl+C)", "signal")
    sys.exit(130)


def _handle_sighup(signum: int, frame: Any) -> None:
    """Handle SIGHUP (terminal hangup) for clean exit.

    Does NOT stop managed sessions (they survive via setsid).
    Matches bash trap 'cleanup_handler HUP' HUP behavior.

    Args:
        signum: Signal number received.
        frame: Current stack frame (unused).
    """
    log_info("Received SIGHUP — management script exiting", "signal")
    sys.exit(0)


# ==============================================================================
# DEPENDENCY CHECK
# ==============================================================================

def check_socat() -> None:
    """Verify socat is installed and in PATH.

    Prints installation instructions if not found.

    Raises:
        SystemExit: If socat is not found.
    """
    if shutil.which("socat") is None:
        log_critical("socat is not installed or not in PATH", "deps")
        print("", file=sys.stderr)
        if USE_COLOR:
            b, c, r = COLORS.bold, COLORS.cyan, COLORS.reset
            print(f"  {b}Install socat:{r}", file=sys.stderr)
            print(f"    {c}sudo apt-get update && sudo apt-get install -y socat{r}", file=sys.stderr)
            print(f"    {c}# or: sudo yum install -y socat{r}", file=sys.stderr)
            print(f"    {c}# or: sudo pacman -S socat{r}", file=sys.stderr)
        else:
            print("  Install socat:", file=sys.stderr)
            print("    sudo apt-get update && sudo apt-get install -y socat", file=sys.stderr)
            print("    # or: sudo yum install -y socat", file=sys.stderr)
            print("    # or: sudo pacman -S socat", file=sys.stderr)
        print("", file=sys.stderr)
        sys.exit(1)

    # Log version info
    import subprocess
    try:
        result = subprocess.run(
            ["socat", "-V"], capture_output=True, text=True, timeout=5,
        )
        if result.stdout:
            lines = result.stdout.strip().splitlines()
            version_line: str = lines[1].strip() if len(lines) >= 2 else "unknown"
            socat_path: str = shutil.which("socat") or "socat"
            log_debug(f"socat found: {socat_path} ({version_line})", "deps")
    except (subprocess.TimeoutExpired, OSError):
        pass


# ==============================================================================
# LOGGING INITIALIZATION
# ==============================================================================

def initialize_logging(args: Any) -> None:
    """Resolve the logging controls and configure logging for this invocation.

    This is the single initialization point for logging. It runs once per
    invocation, before any path that produces output — the interactive menu,
    the mode handlers, and the startup banner all depend on it. The effective
    level must be resolved and applied before the logger is configured, because
    the configured level is fixed once the handlers are attached.

    The effective console level is derived from three optional controls, in
    order of precedence: an explicit --log-level, then --verbose (DEBUG), then
    --quiet (WARNING), defaulting to INFO. Any of the three may be absent from
    the namespace (not every subcommand defines them), which is handled by
    reading each with a default.

    Args:
        args: Parsed argparse Namespace, which may carry 'log_level',
              'verbose', and 'quiet' attributes.
    """
    import logging

    import socat_manager.logging_setup as ls

    level: int = ls.resolve_log_level(
        log_level=getattr(args, "log_level", None),
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )

    # Keep the convenience predicate aligned with the resolved level so any
    # reader of verbose_mode continues to reflect "are we at DEBUG?".
    ls.verbose_mode = level == logging.DEBUG

    setup_logging(log_level=level)

    # Honor the --no-audit opt-out for this invocation (auditing is on by
    # default). The audit store itself checks SOCAT_MANAGER_AUDIT as well.
    from socat_manager import audit
    audit.set_cli_disabled(bool(getattr(args, "no_audit", False)))


# ==============================================================================
# MODE DISPATCH
# ==============================================================================

def dispatch_mode(args: Any) -> None:
    """Dispatch to the appropriate mode handler based on parsed args.

    Routing only. Logging is configured once per invocation by
    initialize_logging(), which runs before any dispatch.

    Args:
        args: Parsed argparse Namespace with 'mode' attribute.
    """
    mode: str = args.mode

    # Import mode handlers
    from socat_manager.modes.batch import mode_batch
    from socat_manager.modes.forward import mode_forward
    from socat_manager.modes.listen import mode_listen
    from socat_manager.modes.redirect import mode_redirect
    from socat_manager.modes.status import mode_status
    from socat_manager.modes.stop import mode_stop
    from socat_manager.modes.tunnel import mode_tunnel

    # Dispatch
    match mode:
        case "listen":
            mode_listen(args)
        case "batch":
            mode_batch(args)
        case "forward":
            mode_forward(args)
        case "tunnel":
            mode_tunnel(args)
        case "redirect":
            mode_redirect(args)
        case "status":
            mode_status(args)
        case "stop":
            mode_stop(args)
        case "audit":
            from socat_manager.modes.audit_view import mode_audit
            mode_audit(args)
        case "menu":
            from socat_manager.menu import interactive_menu
            interactive_menu()
        case _:
            log_critical(f"Unknown mode: {mode}")
            sys.exit(1)


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

def main() -> None:
    """Main entry point for socat-manager.

    Parses CLI arguments and dispatches to the appropriate handler.
    No arguments (or 'menu' subcommand) launches interactive mode.
    """
    # Install signal handlers
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigint)
    signal.signal(signal.SIGHUP, _handle_sighup)

    # Ensure directory structure exists
    _ensure_dirs()

    # Build and parse CLI arguments
    parser = build_parser()
    args = parser.parse_args()

    # Configure logging once, before any path that produces output. The
    # interactive menu reaches the mode handlers through dispatch_mode(), so
    # initializing here covers the menu and the direct CLI paths alike.
    initialize_logging(args)

    # No mode specified → interactive menu
    if args.mode is None:
        from socat_manager.menu import interactive_menu
        interactive_menu()
        return

    # 'menu' subcommand → interactive menu
    if args.mode == "menu":
        from socat_manager.menu import interactive_menu
        interactive_menu()
        return

    # 'help' positional command → show help and exit
    if args.mode == "help":
        parser.print_help(sys.stderr)
        return

    # 'version' positional command → show version and exit
    if args.mode == "version":
        print(f"socat-manager v{__version__}")
        return

    # Log startup
    import os
    log_info(
        f"=== socat-manager v{__version__} started (mode: {args.mode}) ===",
        "main",
    )
    log_debug(
        f"PID: {os.getpid()}, User: {os.environ.get('USER', 'unknown')}, "
        f"PWD: {os.getcwd()}",
        "main",
    )

    # Migrate legacy v1 session files if any exist
    from socat_manager.session import migrate_legacy_sessions
    migrate_legacy_sessions()

    # Check socat availability for operational modes
    # Skip for status, stop, audit, help — they don't need socat
    needs_socat: bool = args.mode not in ("status", "stop", "audit", "help", "version")
    if needs_socat:
        check_socat()

    # Dispatch to mode handler
    dispatch_mode(args)


# Guard for direct execution
if __name__ == "__main__":
    main()

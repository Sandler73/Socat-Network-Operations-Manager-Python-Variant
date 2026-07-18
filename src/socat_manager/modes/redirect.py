# ==============================================================================
# MODULE      : socat_manager/modes/redirect.py
# ==============================================================================
# Synopsis    : Redirect mode handler -- transparent port redirection
# Description : Redirects/proxies traffic transparently between a local port
#               and a remote target. Bidirectional with optional traffic capture.
#               Exact parity with bash mode_redirect() (lines 2372-2481).
#
#
#               - Bidirectional (no -u flag) -- same as forward
#               - No --remote-proto -- listen and connect use same protocol
#               - Session name auto-generated as redir-{proto}-{lport}-{rhost}-{rport}
#               - Does NOT have --logfile, --socat-opts, or --bind flags
#
# Version     : 1.0.2
# ==============================================================================

"""Redirect mode handler -- transparent port redirection."""

from __future__ import annotations

import os
import sys
from typing import Any

from socat_manager.commands import (
    build_filter_opts,
    build_socat_redirect_cmd,
    cmd_list_to_string,
)
from socat_manager.config import ALT_PROTOCOL, DEFAULTS, EXEC_TIMESTAMP, SYMBOLS
from socat_manager.logging_setup import (
    _ensure_dirs,
    get_paths,
    log_debug,
    log_error,
    log_info,
    log_success,
    log_warning,
    print_banner,
    print_kv,
    print_section,
)
from socat_manager.process import check_port_available, launch_socat_session
from socat_manager.validation import (
    ValidationError,
    validate_hostname,
    validate_port,
    validate_protocol,
    validate_session_name,
)
from socat_manager.watchdog import start_watchdog


def mode_redirect(args: Any) -> None:
    """Execute redirect mode: transparent port redirection.

    Args:
        args: Parsed argparse Namespace with redirect-mode attributes:
              lport, rhost, rport, proto, name, capture, watchdog,
              dual_stack, verbose.

    Raises:
        SystemExit: On validation failure or launch error.
    """
    _ensure_dirs()
    paths = get_paths()

    # --- Validate inputs ---
    try:
        lport: int = validate_port(args.lport)
        rport: int = validate_port(args.rport)
        rhost: str = validate_hostname(args.rhost)
        proto: str = validate_protocol(args.proto or DEFAULTS.protocol)
    except ValidationError as exc:
        log_error(str(exc), "redirect")
        sys.exit(1)

    session_name: str = ""
    if args.name:
        try:
            session_name = validate_session_name(args.name)
        except ValidationError as exc:
            log_error(str(exc), "redirect")
            sys.exit(1)

    capture: bool = bool(args.capture)
    use_watchdog: bool = bool(args.watchdog)
    wd_max_restarts: int = getattr(args, 'max_restarts', None) or 0
    wd_backoff: int = getattr(args, 'backoff', None) or 1
    dual_stack: bool = bool(args.dual_stack)

    # Source-filter options (range=, tcpwrap=), family-checked against proto.
    filter_opts: str = ""
    try:
        filter_opts = build_filter_opts(
            allow=getattr(args, "allow", "") or "",
            tcpwrap=getattr(args, "tcpwrap", "") or "",
            proto=proto,
        )
    except ValidationError as exc:
        log_error(str(exc), "redirect")
        sys.exit(1)

    print_banner("Redirector")

    # --- Check port availability ---
    if not check_port_available(lport, proto):
        log_error(f"Local port {lport} ({proto}) is already in use", "redirect")
        sys.exit(1)

    # --- Defaults ---
    if not session_name:
        session_name = f"redir-{proto}-{lport}-{rhost}-{rport}"

    # --- Capture log ---
    capture_logfile: str = ""
    if capture:
        capture_logfile = str(
            paths.log_dir / f"capture-{proto}-{lport}-{rhost}-{rport}-{EXEC_TIMESTAMP}.log"
        )
        _create_capture_log(capture_logfile)

    # --- Build command ---
    cmd: list[str] = build_socat_redirect_cmd(proto, lport, rhost, rport, capture, filter_opts)

    # --- Display configuration ---
    print_section("Redirect Configuration")
    print_kv("Listen Port", lport)
    alt_display: str = f" + {ALT_PROTOCOL.get(proto, '')}" if dual_stack else ""
    print_kv("Protocol", f"{proto}{alt_display}")
    print_kv("Remote Target", f"{rhost}:{rport}")
    print_kv("Traffic Capture", capture)
    if capture:
        print_kv("Capture Log", capture_logfile)
    print_kv("Session Name", session_name)
    print_kv("Dual-Stack", dual_stack)
    print_kv("Watchdog", use_watchdog)
    log_debug(f"Command: {cmd_list_to_string(cmd)}", "redirect")

    # --- Launch ---
    print_section("Starting Redirector")
    stderr_file: str = capture_logfile if capture else ""

    try:
        primary_sid, primary_pid = launch_socat_session(
            name=session_name,
            mode="redirect",
            proto=proto,
            lport=lport,
            cmd=cmd,
            rhost=rhost,
            rport=str(rport),
            stderr_redirect=stderr_file,
        )
    except RuntimeError as exc:
        log_error(str(exc), "redirect")
        sys.exit(1)

    log_success(
        f"Redirector active: {proto}:{lport} {SYMBOLS.arrow} "
        f"{rhost}:{rport} (SID {primary_sid})"
    )

    if use_watchdog:
        start_watchdog(
            session_id=primary_sid,
            session_name=session_name,
            initial_pid=primary_pid,
            cmd=cmd,
            max_restarts=wd_max_restarts,
            backoff_initial=wd_backoff,
            stderr_redirect=stderr_file,
        )

    # --- Dual-stack ---
    if dual_stack:
        alt_proto: str = ALT_PROTOCOL.get(proto, "")
        if alt_proto and check_port_available(lport, alt_proto):
            alt_name: str = f"redir-{alt_proto}-{lport}-{rhost}-{rport}"
            alt_cmd: list[str] = build_socat_redirect_cmd(
                alt_proto, lport, rhost, rport, capture, filter_opts,
            )

            alt_capture_logfile: str = ""
            alt_stderr: str = ""
            if capture:
                alt_capture_logfile = str(
                    paths.log_dir / f"capture-{alt_proto}-{lport}-{rhost}-{rport}-{EXEC_TIMESTAMP}.log"
                )
                _create_capture_log(alt_capture_logfile)
                alt_stderr = alt_capture_logfile

            try:
                alt_sid, alt_pid = launch_socat_session(
                    name=alt_name,
                    mode="redirect",
                    proto=alt_proto,
                    lport=lport,
                    cmd=alt_cmd,
                    rhost=rhost,
                    rport=str(rport),
                    stderr_redirect=alt_stderr,
                )
                log_success(
                    f"Redirector active: {alt_proto}:{lport} {SYMBOLS.arrow} "
                    f"{rhost}:{rport} (SID {alt_sid})"
                )
                if use_watchdog:
                    start_watchdog(
                        session_id=alt_sid,
                        session_name=alt_name,
                        initial_pid=alt_pid,
                        cmd=alt_cmd,
                        stderr_redirect=alt_stderr,
                    )
            except RuntimeError:
                log_warning(f"Dual-stack {alt_proto} redirector failed on port {lport}")
        elif alt_proto:
            log_warning(f"Port {lport} ({alt_proto}) already in use -- skipping dual-stack")

    log_info(f"Stop with: socat-manager stop {primary_sid}")


def _create_capture_log(path: str) -> None:
    """Create a capture log file with restrictive permissions (0o600)."""
    try:
        fd: int = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)
    except OSError:
        pass  # pre-creating the capture log is best-effort; socat creates it if absent

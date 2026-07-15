# ==============================================================================
# MODULE      : socat_manager/modes/forward.py
# ==============================================================================
# Synopsis    : Forward mode handler — bidirectional port forwarding
# Description : Creates a full-duplex proxy between a local listener and a
#               remote target. Supports protocol selection, dual-stack,
#               cross-protocol forwarding (--remote-proto), traffic capture,
#               and watchdog auto-restart.
#               Exact parity with bash mode_forward() (lines 2071-2190).
#
#
#               - Bidirectional (no -u flag) — full-duplex relay
#               - Cross-protocol via --remote-proto (tcp→udp or reverse)
#               - Does NOT have --logfile, --socat-opts, or --bind flags
#               - Session name auto-generated as fwd-{lport}-{rhost}-{rport}
#
# Version     : 0.9.0
# ==============================================================================

"""Forward mode handler — bidirectional port forwarding."""

from __future__ import annotations

import os
import sys
from typing import Any

from socat_manager.commands import build_socat_forward_cmd, cmd_list_to_string
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


def mode_forward(args: Any) -> None:
    """Execute forward mode: bidirectional port forwarding.

    Args:
        args: Parsed argparse Namespace with forward-mode attributes:
              lport, rhost, rport, proto, remote_proto, name, capture,
              watchdog, dual_stack, verbose.

    Raises:
        SystemExit: On validation failure or launch error.
    """
    _ensure_dirs()
    paths = get_paths()

    # --- Validate required inputs ---
    try:
        lport: int = validate_port(args.lport)
        rport: int = validate_port(args.rport)
        rhost: str = validate_hostname(args.rhost)
        proto: str = validate_protocol(args.proto or DEFAULTS.protocol)
    except ValidationError as exc:
        log_error(str(exc), "forward")
        sys.exit(1)

    # Remote protocol defaults to listen protocol
    remote_proto: str = proto
    if args.remote_proto:
        try:
            remote_proto = validate_protocol(args.remote_proto)
        except ValidationError as exc:
            log_error(str(exc), "forward")
            sys.exit(1)

    session_name: str = ""
    if args.name:
        try:
            session_name = validate_session_name(args.name)
        except ValidationError as exc:
            log_error(str(exc), "forward")
            sys.exit(1)

    capture: bool = bool(args.capture)
    use_watchdog: bool = bool(args.watchdog)
    wd_max_restarts: int = getattr(args, 'max_restarts', None) or 0
    wd_backoff: int = getattr(args, 'backoff', None) or 1
    dual_stack: bool = bool(args.dual_stack)

    # --- Check port availability ---
    if not check_port_available(lport, proto):
        log_error(f"Local port {lport} ({proto}) is already in use", "forward")
        sys.exit(1)

    # --- Defaults ---
    if not session_name:
        session_name = f"fwd-{lport}-{rhost}-{rport}"

    # --- Capture log ---
    capture_logfile: str = ""
    if capture:
        capture_logfile = str(
            paths.log_dir / f"capture-{proto}-{lport}-{rhost}-{rport}-{EXEC_TIMESTAMP}.log"
        )
        _create_capture_log(capture_logfile)

    # --- Build command ---
    cmd: list[str] = build_socat_forward_cmd(
        proto, lport, rhost, rport, remote_proto, capture,
    )

    # --- Display configuration ---
    print_banner("Forwarder")
    print_section("Forward Configuration")
    print_kv("Local Port", f"{lport} ({proto})")
    print_kv("Remote Target", f"{rhost}:{rport} ({remote_proto})")
    print_kv("Direction", "Bidirectional")
    print_kv("Session Name", session_name)
    print_kv("Traffic Capture", capture)
    if capture:
        print_kv("Capture Log", capture_logfile)
    print_kv("Dual-Stack", dual_stack)
    print_kv("Watchdog", use_watchdog)
    log_debug(f"Command: {cmd_list_to_string(cmd)}", "forward")

    # --- Launch ---
    print_section("Starting Forwarder")
    stderr_file: str = capture_logfile if capture else ""

    try:
        primary_sid, primary_pid = launch_socat_session(
            name=session_name,
            mode="forward",
            proto=proto,
            lport=lport,
            cmd=cmd,
            rhost=rhost,
            rport=str(rport),
            stderr_redirect=stderr_file,
        )
    except RuntimeError as exc:
        log_error(str(exc), "forward")
        sys.exit(1)

    log_success(
        f"Forwarder active: {proto}:{lport} {SYMBOLS.forward} "
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
        alt_remote_proto: str = ALT_PROTOCOL.get(remote_proto, "")
        if alt_proto and alt_remote_proto:
            alt_name: str = f"fwd-{alt_proto}-{lport}-{rhost}-{rport}"
            alt_cmd: list[str] = build_socat_forward_cmd(
                alt_proto, lport, rhost, rport, alt_remote_proto, capture,
            )

            alt_capture_logfile: str = ""
            alt_stderr: str = ""
            if capture:
                alt_capture_logfile = str(
                    paths.log_dir / f"capture-{alt_proto}-{lport}-{rhost}-{rport}-{EXEC_TIMESTAMP}.log"
                )
                _create_capture_log(alt_capture_logfile)
                alt_stderr = alt_capture_logfile

            if check_port_available(lport, alt_proto):
                try:
                    alt_sid, alt_pid = launch_socat_session(
                        name=alt_name,
                        mode="forward",
                        proto=alt_proto,
                        lport=lport,
                        cmd=alt_cmd,
                        rhost=rhost,
                        rport=str(rport),
                        stderr_redirect=alt_stderr,
                    )
                    log_success(
                        f"Forwarder active: {alt_proto}:{lport} {SYMBOLS.forward} "
                        f"{rhost}:{rport} (SID {alt_sid})"
                    )
                    if use_watchdog:
                        start_watchdog(
                            session_id=alt_sid,
                            session_name=alt_name,
                            initial_pid=alt_pid,
                            cmd=alt_cmd,
                            max_restarts=wd_max_restarts,
                            backoff_initial=wd_backoff,
                            stderr_redirect=alt_stderr,
                        )
                except RuntimeError:
                    log_warning(f"Dual-stack {alt_proto} forwarder failed on port {lport}")
            else:
                log_warning(f"Port {lport} ({alt_proto}) already in use — skipping dual-stack")

    log_info(f"Stop with: socat-manager stop {primary_sid}")


def _create_capture_log(path: str) -> None:
    """Create a capture log file with restrictive permissions (0o600)."""
    try:
        fd: int = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)
    except OSError:
        pass

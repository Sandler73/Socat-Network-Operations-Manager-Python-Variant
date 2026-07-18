# ==============================================================================
# MODULE      : socat_manager/modes/listen.py
# ==============================================================================
# Synopsis    : Listen mode handler — single TCP/UDP listener
# Description : Starts a single listener on a specified port with options for
#               protocol selection, dual-stack, traffic capture, and watchdog
#               auto-restart. Exact parity with bash mode_listen() (lines 1772-1887).
#
# Notes       : - Dual-stack launches both TCP and UDP with independent sessions
#               - Capture mode creates separate per-protocol capture logs
#               - Watchdog is launched as a daemon thread per session
#               - All inputs validated at boundary before use
#
# Version     : 1.0.2
# ==============================================================================

"""Listen mode handler — single TCP/UDP listener on a port."""

from __future__ import annotations

import os
import sys
from typing import Any

from socat_manager.commands import (
    build_filter_opts,
    build_socat_listen_cmd,
    cmd_list_to_string,
    format_socat_host,
)
from socat_manager.config import (
    ALT_PROTOCOL,
    DEFAULTS,
    EXEC_TIMESTAMP,
)
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
    validate_socat_opts,
    validate_writable_path,
)
from socat_manager.watchdog import start_watchdog


def mode_listen(args: Any) -> None:
    """Execute listen mode: start a single TCP/UDP listener.

    Handles argument validation, port availability checks, command
    construction, process launch, and optional dual-stack/watchdog.

    Args:
        args: Parsed argparse Namespace with listen-mode attributes:
              port, proto, bind, name, logfile, capture, watchdog,
              dual_stack, socat_opts, verbose.

    Raises:
        SystemExit: On validation failure or launch error.
    """
    _ensure_dirs()
    paths = get_paths()

    # --- Validate inputs ---
    try:
        port: int = validate_port(args.port)
        proto: str = validate_protocol(args.proto or DEFAULTS.protocol)
    except ValidationError as exc:
        log_error(str(exc), "listen")
        sys.exit(1)

    # Validate optional inputs
    extra_opts: str = ""
    if args.socat_opts:
        try:
            extra_opts = validate_socat_opts(args.socat_opts)
        except ValidationError as exc:
            log_error(str(exc), "listen")
            sys.exit(1)

    # Source-filter options (range=, tcpwrap=). Family-checked against proto;
    # the dual-stack alternate shares the same address family, so the same
    # fragment applies to both listeners.
    filter_opts: str = ""
    try:
        filter_opts = build_filter_opts(
            allow=getattr(args, "allow", "") or "",
            tcpwrap=getattr(args, "tcpwrap", "") or "",
            proto=proto,
        )
    except ValidationError as exc:
        log_error(str(exc), "listen")
        sys.exit(1)

    session_name: str = ""
    if args.name:
        try:
            session_name = validate_session_name(args.name)
        except ValidationError as exc:
            log_error(str(exc), "listen")
            sys.exit(1)

    bind_addr: str = ""
    if args.bind:
        try:
            bind_addr = validate_hostname(args.bind)
        except ValidationError as exc:
            log_error(str(exc), "listen")
            sys.exit(1)

    capture: bool = bool(args.capture)
    use_watchdog: bool = bool(args.watchdog)
    wd_max_restarts: int = getattr(args, 'max_restarts', None) or 0
    wd_backoff: int = getattr(args, 'backoff', None) or 1
    dual_stack: bool = bool(args.dual_stack)

    # --- Check port availability ---
    if not check_port_available(port, proto):
        log_error(f"Port {port} ({proto}) is already in use", "listen")
        sys.exit(1)

    # --- Defaults ---
    if not session_name:
        session_name = f"{proto}-{port}"

    # Validate the user-provided logfile as a write target: it may not exist
    # yet, so existence is not required, but traversal and shell metacharacters
    # are rejected using the shared validator and its config-defined character
    # set.
    logfile: str = ""
    if args.logfile:
        try:
            logfile = validate_writable_path(args.logfile)
        except ValidationError as exc:
            log_error(str(exc), "listen")
            sys.exit(1)
    else:
        logfile = str(paths.log_dir / f"listener-{proto}-{port}.log")

    # Construct bind address option if specified.
    # IPv6 literals are bracketed so their colons are not read as socat
    # address field separators.
    if bind_addr:
        bind_opt: str = f"bind={format_socat_host(bind_addr)}"
        extra_opts = bind_opt + (f",{extra_opts}" if extra_opts else "")

    # Capture log file
    capture_logfile: str = ""
    if capture:
        capture_logfile = str(
            paths.log_dir / f"capture-{proto}-{port}-{EXEC_TIMESTAMP}.log"
        )
        # Create capture log with restrictive permissions
        _create_capture_log(capture_logfile)

    # --- Build socat command ---
    cmd: list[str] = build_socat_listen_cmd(proto, port, logfile, extra_opts, capture, filter_opts)

    # --- Display configuration ---
    print_banner("Listener")
    print_section("Listener Configuration")
    print_kv("Port", port)
    alt_display: str = f" + {ALT_PROTOCOL.get(proto, '')}" if dual_stack else ""
    print_kv("Protocol", f"{proto}{alt_display}")
    print_kv("Session Name", session_name)
    print_kv("Data Log", logfile)
    print_kv("Traffic Capture", capture)
    if capture:
        print_kv("Capture Log", capture_logfile)
    print_kv("Watchdog", use_watchdog)
    print_kv("Dual-Stack", dual_stack)
    if bind_addr:
        print_kv("Bind Address", bind_addr)
    log_debug(f"Command: {cmd_list_to_string(cmd)}", "listen")

    # --- Launch primary listener ---
    print_section("Starting Listener")

    stderr_file: str = capture_logfile if capture else ""

    try:
        primary_sid, primary_pid = launch_socat_session(
            name=session_name,
            mode="listen",
            proto=proto,
            lport=port,
            cmd=cmd,
            stderr_redirect=stderr_file,
        )
    except RuntimeError as exc:
        log_error(str(exc), "listen")
        sys.exit(1)

    log_success(f"Listener active on {proto}:{port} (SID {primary_sid})")

    # --- Watchdog for primary ---
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

    # --- Dual-stack: launch alternate protocol listener ---
    if dual_stack:
        alt_proto: str = ALT_PROTOCOL.get(proto, "")
        if alt_proto:
            alt_name: str = f"{alt_proto}-{port}"
            alt_logfile: str = str(paths.log_dir / f"listener-{alt_proto}-{port}.log")
            alt_cmd: list[str] = build_socat_listen_cmd(
                alt_proto, port, alt_logfile, extra_opts, capture, filter_opts,
            )

            if check_port_available(port, alt_proto):
                alt_capture_logfile: str = ""
                alt_stderr: str = ""
                if capture:
                    alt_capture_logfile = str(
                        paths.log_dir / f"capture-{alt_proto}-{port}-{EXEC_TIMESTAMP}.log"
                    )
                    _create_capture_log(alt_capture_logfile)
                    alt_stderr = alt_capture_logfile

                try:
                    alt_sid, alt_pid = launch_socat_session(
                        name=alt_name,
                        mode="listen",
                        proto=alt_proto,
                        lport=port,
                        cmd=alt_cmd,
                        stderr_redirect=alt_stderr,
                    )
                    log_success(f"Listener active on {alt_proto}:{port} (SID {alt_sid})")

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
                    log_warning(f"Dual-stack {alt_proto} listener failed on port {port}")
            else:
                log_warning(
                    f"Port {port} ({alt_proto}) already in use — skipping dual-stack"
                )

    log_info(f"Data captured to: {logfile}")
    log_info(f"Stop with: socat-manager stop {primary_sid}")


def _create_capture_log(path: str) -> None:
    """Create a capture log file with restrictive permissions (0o600).

    Args:
        path: Path to the capture log file.
    """
    try:
        fd: int = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)
    except OSError:
        pass

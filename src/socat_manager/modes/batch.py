# ==============================================================================
# MODULE      : socat_manager/modes/batch.py
# ==============================================================================
# Synopsis    : Batch mode handler — multiple listeners from port list/range/file
# Description : Starts multiple listeners from a port list (--ports), port range
#               (--range), or configuration file (--file). Each port gets an
#               independent session. Exact parity with bash mode_batch() (lines 1902-2070).
#
#
#               - Exactly one of --ports, --range, or --file required
#               - Ports are deduplicated and sorted before launching
#               - Unavailable ports are skipped with warning, not fatal
#               - Each port gets independent session ID and log file
#               - Mode string in session files is 'batch-listen'
#
# Version     : 1.0.2
# ==============================================================================

"""Batch mode handler — multiple listeners from port list, range, or config file."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from socat_manager.commands import build_filter_opts, build_socat_listen_cmd
from socat_manager.config import ALT_PROTOCOL, DEFAULTS, EXEC_TIMESTAMP
from socat_manager.logging_setup import (
    _ensure_dirs,
    get_paths,
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
    validate_file_path,
    validate_port,
    validate_port_list,
    validate_port_range,
    validate_protocol,
    validate_socat_opts,
)
from socat_manager.watchdog import start_watchdog


def mode_batch(args: Any) -> None:
    """Execute batch mode: start multiple listeners.

    Supports three port sources (mutually exclusive):
        --ports  : comma-separated port list (e.g., "21,22,80,443")
        --range  : port range (e.g., "8000-8010")
        --file   : config file with one port per line

    Each port gets an independent session with its own session ID.

    Args:
        args: Parsed argparse Namespace with batch-mode attributes.

    Raises:
        SystemExit: On validation failure or if no ports specified.
    """
    _ensure_dirs()
    paths = get_paths()

    # --- Validate protocol ---
    try:
        proto: str = validate_protocol(args.proto or DEFAULTS.protocol)
    except ValidationError as exc:
        log_error(str(exc), "batch")
        sys.exit(1)

    extra_opts: str = ""
    if args.socat_opts:
        try:
            extra_opts = validate_socat_opts(args.socat_opts)
        except ValidationError as exc:
            log_error(str(exc), "batch")
            sys.exit(1)

    # Source-filter options (range=, tcpwrap=), family-checked against proto.
    filter_opts: str = ""
    try:
        filter_opts = build_filter_opts(
            allow=getattr(args, "allow", "") or "",
            tcpwrap=getattr(args, "tcpwrap", "") or "",
            proto=proto,
        )
    except ValidationError as exc:
        log_error(str(exc), "batch")
        sys.exit(1)

    capture: bool = bool(args.capture)
    use_watchdog: bool = bool(args.watchdog)
    wd_max_restarts: int = getattr(args, 'max_restarts', None) or 0
    wd_backoff: int = getattr(args, 'backoff', None) or 1
    dual_stack: bool = bool(args.dual_stack)

    # --- Resolve port list from one of three sources ---
    ports: list[int] = []

    if args.ports:
        try:
            ports = validate_port_list(args.ports)
        except ValidationError as exc:
            log_error(str(exc), "batch")
            sys.exit(1)

    elif args.range:
        try:
            ports = validate_port_range(args.range)
        except ValidationError as exc:
            log_error(str(exc), "batch")
            sys.exit(1)

    elif args.file:
        try:
            validate_file_path(args.file)
        except ValidationError as exc:
            log_error(str(exc), "batch")
            sys.exit(1)

        config_path: Path = Path(args.file)
        if not config_path.is_file():
            log_error(f"Config file not found: {args.file}", "batch")
            sys.exit(1)

        # Read ports from config file (one per line, skip comments/blanks)
        try:
            with open(config_path, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    try:
                        ports.append(validate_port(line))
                    except ValidationError:
                        log_warning(f"Skipping invalid port in config: '{line}'", "batch")
        except OSError as exc:
            log_error(f"Cannot read config file: {exc}", "batch")
            sys.exit(1)

    if not ports:
        log_error(
            "No ports specified. Use --ports, --range, or --file",
            "batch",
        )
        sys.exit(1)

    # Deduplicate and sort ports
    original_count: int = len(ports)
    ports = sorted(set(ports))
    if len(ports) < original_count:
        log_info(
            f"Deduplicated {original_count} ports → {len(ports)} unique",
            "batch",
        )

    # --- Display configuration ---
    print_banner("Batch Listener")
    print_section("Batch Configuration")
    print_kv("Port Count", len(ports))
    print_kv("Protocol", f"{proto}{' + ' + ALT_PROTOCOL.get(proto, '') if dual_stack else ''}")
    print_kv("Traffic Capture", capture)
    print_kv("Watchdog", use_watchdog)
    print_kv("Dual-Stack", dual_stack)

    # --- Launch listeners for each port ---
    print_section("Starting Listeners")

    launched: int = 0
    failed: int = 0

    for port in ports:
        session_name: str = f"{proto}-{port}"
        logfile: str = str(paths.log_dir / f"listener-{proto}-{port}.log")

        if not check_port_available(port, proto):
            log_warning(f"Port {port} ({proto}) already in use — skipping")
            failed += 1
            continue

        capture_logfile: str = ""
        stderr_file: str = ""
        if capture:
            capture_logfile = str(
                paths.log_dir / f"capture-{proto}-{port}-{EXEC_TIMESTAMP}.log"
            )
            _create_capture_log(capture_logfile)
            stderr_file = capture_logfile

        cmd: list[str] = build_socat_listen_cmd(proto, port, logfile, extra_opts, capture, filter_opts)

        try:
            sid, sid_pid = launch_socat_session(
                name=session_name,
                mode="batch-listen",
                proto=proto,
                lport=port,
                cmd=cmd,
                stderr_redirect=stderr_file,
            )
            log_success(f"Listener: {proto}:{port} (SID {sid})")
            launched += 1

            if use_watchdog:
                start_watchdog(
                    session_id=sid,
                    session_name=session_name,
                    initial_pid=sid_pid,
                    cmd=cmd,
                    max_restarts=wd_max_restarts,
                    backoff_initial=wd_backoff,
                    stderr_redirect=stderr_file,
                )
        except RuntimeError as exc:
            log_warning(f"Failed to start listener on port {port}: {exc}")
            failed += 1
            continue

        # Dual-stack: launch alternate protocol
        if dual_stack:
            alt_proto: str = ALT_PROTOCOL.get(proto, "")
            if alt_proto and check_port_available(port, alt_proto):
                alt_name: str = f"{alt_proto}-{port}"
                alt_logfile: str = str(paths.log_dir / f"listener-{alt_proto}-{port}.log")
                alt_cmd: list[str] = build_socat_listen_cmd(
                    alt_proto, port, alt_logfile, extra_opts, capture, filter_opts,
                )

                alt_stderr: str = ""
                if capture:
                    alt_capture: str = str(
                        paths.log_dir / f"capture-{alt_proto}-{port}-{EXEC_TIMESTAMP}.log"
                    )
                    _create_capture_log(alt_capture)
                    alt_stderr = alt_capture

                try:
                    alt_sid, alt_pid = launch_socat_session(
                        name=alt_name,
                        mode="batch-listen",
                        proto=alt_proto,
                        lport=port,
                        cmd=alt_cmd,
                        stderr_redirect=alt_stderr,
                    )
                    log_success(f"Listener: {alt_proto}:{port} (SID {alt_sid})")
                    launched += 1

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

    # --- Summary ---
    print_section("Batch Summary")
    print_kv("Launched", launched)
    print_kv("Failed", failed)
    print_kv("Total Ports", len(ports))


def _create_capture_log(path: str) -> None:
    """Create a capture log file with restrictive permissions (0o600)."""
    try:
        fd: int = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)
    except OSError:
        pass

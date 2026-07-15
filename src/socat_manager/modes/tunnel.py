# ==============================================================================
# MODULE      : socat_manager/modes/tunnel.py
# ==============================================================================
# Synopsis    : Tunnel mode handler — TLS-encrypted tunnel via socat+OpenSSL
# Description : Accepts TLS connections on a local port and forwards plaintext
#               traffic to a remote target. Auto-generates self-signed certs if
#               none provided. TCP only (rejects UDP with guidance). Dual-stack
#               adds a plaintext UDP forwarder with warning.
#               Exact parity with bash mode_tunnel() (lines 2207-2355).
#
#
#               - TLS tunnels are TCP-only by definition
#               - --proto udp rejected with error and guidance
#               - --proto tcp6 triggers warning, falls back to TCP4
#               - Auto-generates cert via openssl if --cert/--key omitted
#               - Dual-stack adds plaintext UDP forwarder (mode: tunnel-udp)
#               - --cn validated via validate_session_name() before use
#
# Version     : 0.9.0
# ==============================================================================

"""Tunnel mode handler — TLS-encrypted tunnel via socat+OpenSSL."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from socat_manager.certs import generate_self_signed_cert
from socat_manager.commands import (
    build_socat_forward_cmd,
    build_socat_tunnel_cmd,
    cmd_list_to_string,
)
from socat_manager.config import EXEC_TIMESTAMP, SYMBOLS
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
    is_ipv6_literal,
    validate_file_path,
    validate_hostname,
    validate_port,
    validate_session_name,
)
from socat_manager.watchdog import start_watchdog


def mode_tunnel(args: Any) -> None:
    """Execute tunnel mode: TLS-encrypted tunnel.

    TLS tunnels are TCP-only by definition. If --proto udp is specified,
    the command exits with an error and guidance to use forward mode.
    Dual-stack adds a plaintext UDP forwarder with a clear warning.

    Args:
        args: Parsed argparse Namespace with tunnel-mode attributes:
              port, rhost, rport, cert, key, cn, name, capture,
              watchdog, dual_stack, proto, verbose.

    Raises:
        SystemExit: On validation failure or launch error.
    """
    _ensure_dirs()
    paths = get_paths()

    # --- Handle --proto: tunnels are TCP-only ---
    if args.proto:
        tunnel_proto: str = args.proto.strip().lower()
        if tunnel_proto in ("udp", "udp4", "udp6"):
            log_error(
                "TLS tunnels require TCP. UDP is not supported for encrypted tunnels.",
                "tunnel",
            )
            log_info(
                "For UDP forwarding, use: socat-manager forward "
                "--proto udp4 --lport <PORT> --rhost <HOST> --rport <PORT>"
            )
            sys.exit(1)
        elif tunnel_proto == "tcp6":
            log_warning("TCP6 TLS tunnels not currently supported; using TCP4", "tunnel")
        elif tunnel_proto not in ("tcp", "tcp4"):
            log_error(f"Invalid protocol: {tunnel_proto}", "tunnel")
            sys.exit(1)

    # --- Validate required inputs ---
    try:
        lport: int = validate_port(args.port)
        rport: int = validate_port(args.rport)
        rhost: str = validate_hostname(args.rhost)
    except ValidationError as exc:
        log_error(str(exc), "tunnel")
        sys.exit(1)

    session_name: str = ""
    if args.name:
        try:
            session_name = validate_session_name(args.name)
        except ValidationError as exc:
            log_error(str(exc), "tunnel")
            sys.exit(1)

    capture: bool = bool(args.capture)
    use_watchdog: bool = bool(args.watchdog)
    wd_max_restarts: int = getattr(args, 'max_restarts', None) or 0
    wd_backoff: int = getattr(args, 'backoff', None) or 1
    dual_stack: bool = bool(args.dual_stack)
    cn: str = args.cn or "localhost"
    # Validate CN — it flows into openssl -subj "/CN=..." argument.
    # Although subprocess argument list prevents shell injection,
    # special characters could break openssl's X.509 subject parsing.
    # Reuse session_name validator (alphanumeric, dots, hyphens, underscores).
    if cn != "localhost":
        try:
            validate_session_name(cn)
        except ValidationError:
            log_error(
                f"Invalid CN '{cn}': only alphanumeric, dots, hyphens, and underscores allowed",
                "tunnel",
            )
            sys.exit(1)

    # Dual-stack advisory
    if dual_stack:
        log_warning(
            "TLS tunnels use TCP only. --dual-stack will add a plaintext "
            "UDP forwarder (unencrypted) on the same port.",
            "tunnel",
        )

    print_banner("Encrypted Tunnel")

    # --- Certificate handling ---
    cert: str = args.cert or ""
    key: str = args.key or ""

    # Warn if only one of cert/key is provided — the other would be auto-generated
    # which means the provided file is effectively ignored
    if cert and not key:
        log_warning(
            f"--cert provided without --key. The certificate '{cert}' will be "
            "ignored and a new self-signed cert+key pair will be generated. "
            "Provide both --cert and --key to use custom certificates.",
            "tunnel",
        )
        cert = ""  # Force regeneration
    elif key and not cert:
        log_warning(
            f"--key provided without --cert. The key '{key}' will be "
            "ignored and a new self-signed cert+key pair will be generated. "
            "Provide both --cert and --key to use custom certificates.",
            "tunnel",
        )
        key = ""  # Force regeneration

    if not cert or not key:
        log_info("No certificate provided; generating self-signed cert...", "tunnel")
        try:
            cert, key = generate_self_signed_cert(cn)
        except RuntimeError as exc:
            log_error(str(exc), "tunnel")
            sys.exit(1)
    else:
        # Validate provided cert/key paths
        try:
            validate_file_path(cert)
            validate_file_path(key)
        except ValidationError as exc:
            log_error(str(exc), "tunnel")
            sys.exit(1)

        if not Path(cert).is_file():
            log_error(f"Certificate not found: {cert}", "tunnel")
            sys.exit(1)
        if not Path(key).is_file():
            log_error(f"Key not found: {key}", "tunnel")
            sys.exit(1)

    # --- Check port availability ---
    if not check_port_available(lport, "tcp4"):
        log_error(f"Local port {lport} (tcp4) is already in use", "tunnel")
        sys.exit(1)

    # --- Defaults ---
    if not session_name:
        session_name = f"tunnel-{lport}-{rhost}-{rport}"

    # --- Capture log ---
    capture_logfile: str = ""
    if capture:
        capture_logfile = str(
            paths.log_dir / f"capture-tls-{lport}-{rhost}-{rport}-{EXEC_TIMESTAMP}.log"
        )
        _create_capture_log(capture_logfile)

    # --- Build command ---
    # The remote leg's address family follows the target: an IPv6 literal is
    # reached over a TCP6 connector, everything else over TCP4 (which also
    # serves hostnames, since socat resolves them itself).
    remote_proto: str = "tcp6" if is_ipv6_literal(rhost) else "tcp4"
    cmd: list[str] = build_socat_tunnel_cmd(
        lport, rhost, rport, cert, key, capture, remote_proto=remote_proto,
    )

    # --- Display configuration ---
    print_section("Tunnel Configuration")
    print_kv("Listen Port", f"{lport} (TLS/SSL)")
    print_kv("Remote Target", f"{rhost}:{rport} (plaintext, IPv{'6' if remote_proto == 'tcp6' else '4'})")
    print_kv("Certificate", cert)
    print_kv("Key", key)
    print_kv("Session Name", session_name)
    print_kv("Traffic Capture", capture)
    if capture:
        print_kv("Capture Log", capture_logfile)
    print_kv("Dual-Stack", dual_stack)
    print_kv("Watchdog", use_watchdog)
    log_debug(f"Command: {cmd_list_to_string(cmd)}", "tunnel")

    # --- Launch ---
    print_section("Starting Tunnel")
    stderr_file: str = capture_logfile if capture else ""

    try:
        primary_sid, primary_pid = launch_socat_session(
            name=session_name,
            mode="tunnel",
            proto="tls",
            lport=lport,
            cmd=cmd,
            rhost=rhost,
            rport=str(rport),
            stderr_redirect=stderr_file,
        )
    except RuntimeError as exc:
        log_error(str(exc), "tunnel")
        sys.exit(1)

    log_success(
        f"Tunnel active: TLS:{lport} {SYMBOLS.tunnel} "
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

    # --- Dual-stack: add plaintext UDP forwarder ---
    if dual_stack:
        if check_port_available(lport, "udp4"):
            udp_name: str = f"fwd-udp4-{lport}-{rhost}-{rport}"
            udp_cmd: list[str] = build_socat_forward_cmd(
                "udp4", lport, rhost, rport, "udp4", capture,
            )

            udp_capture_logfile: str = ""
            udp_stderr: str = ""
            if capture:
                udp_capture_logfile = str(
                    paths.log_dir / f"capture-udp4-{lport}-{rhost}-{rport}-{EXEC_TIMESTAMP}.log"
                )
                _create_capture_log(udp_capture_logfile)
                udp_stderr = udp_capture_logfile

            try:
                udp_sid, udp_pid = launch_socat_session(
                    name=udp_name,
                    mode="tunnel-udp",
                    proto="udp4",
                    lport=lport,
                    cmd=udp_cmd,
                    rhost=rhost,
                    rport=str(rport),
                    stderr_redirect=udp_stderr,
                )
                log_success(
                    f"UDP forwarder active: udp4:{lport} {SYMBOLS.forward} "
                    f"{rhost}:{rport} (SID {udp_sid})"
                )
                if use_watchdog:
                    start_watchdog(
                        session_id=udp_sid,
                        session_name=udp_name,
                        initial_pid=udp_pid,
                        cmd=udp_cmd,
                        max_restarts=wd_max_restarts,
                        backoff_initial=wd_backoff,
                        stderr_redirect=udp_stderr,
                    )
            except RuntimeError:
                log_warning(f"Dual-stack UDP forwarder failed on port {lport}")
        else:
            log_warning(f"Port {lport} (udp4) already in use — skipping dual-stack")

    log_info(f"Connect with: socat - OPENSSL:localhost:{lport},verify=0")
    log_info(f"Stop with: socat-manager stop {primary_sid}")


def _create_capture_log(path: str) -> None:
    """Create a capture log file with restrictive permissions (0o600)."""
    try:
        fd: int = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)
    except OSError:
        pass

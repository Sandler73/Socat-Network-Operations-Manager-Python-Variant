# ==============================================================================
# MODULE      : socat_manager/cli.py
# ==============================================================================
# Synopsis    : CLI argument parser for socat-manager
# Description : Full argparse-based CLI that works identically to the bash
#               version. Uses subparsers for each mode (listen, batch, forward,
#               tunnel, redirect, status, stop, menu) with all flags and options.
#
# Notes       : - Every flag matches the bash --flag name exactly
#               - Positional arguments for status/stop match bash behavior
#               - Global --verbose/-v and --help/-h on all subcommands
#               - 'menu' subcommand launches interactive mode
#
# Version     : 0.9.0
# ==============================================================================

"""CLI argument parser for socat-manager.

Provides the complete argparse configuration for all seven operational
modes plus the interactive menu launcher.
"""

from __future__ import annotations

import argparse

from socat_manager import __version__
from socat_manager.config import SCRIPT_NAME


def build_parser() -> argparse.ArgumentParser:
    """Build and return the complete CLI argument parser.

    Returns:
        Configured ArgumentParser with subparsers for all modes.
    """
    # --- Top-level parser ---
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Socat Network Operations Manager — session-managed socat "
            "network operations across seven modes."
        ),
        epilog=(
            "examples:\n"
            "  %(prog)s listen --port 8080\n"
            "  %(prog)s listen --port 5353 --proto udp4\n"
            "  %(prog)s listen --port 8080 --dual-stack\n"
            "  %(prog)s batch --ports 21,22,80,443\n"
            "  %(prog)s batch --range 8000-8010 --dual-stack\n"
            "  %(prog)s forward --lport 8080 --rhost 10.0.0.5 --rport 80\n"
            "  %(prog)s tunnel --port 4443 --rhost 10.0.0.5 --rport 22\n"
            "  %(prog)s redirect --lport 8443 --rhost example.com --rport 443 --capture\n"
            "  %(prog)s status\n"
            "  %(prog)s status abcd1234\n"
            "  %(prog)s stop --all\n"
            "\n"
            "session management:\n"
            "  Each socat process gets a unique 8-character hex Session ID.\n"
            "  Sessions are tracked in sessions/ via .session metadata files.\n"
            "  Processes run in isolated process groups (via setsid) for\n"
            "  reliable cross-invocation tracking, status, and stop.\n"
            "\n"
            "protocol selection:\n"
            "  --proto <PROTOCOL>   tcp, tcp4, tcp6, udp, udp4, udp6 (default: tcp4)\n"
            "  --dual-stack         Launch both TCP and UDP simultaneously.\n"
            "                       Each protocol gets its own session ID.\n"
            "                       Stop operations are protocol-aware.\n"
            "\n"
            "reliability:\n"
            "  --watchdog enables auto-restart with exponential backoff.\n"
            "  Max 10 restarts before giving up. Backoff: 1s, 2s, 4s... 60s cap.\n"
            "\n"
            "logging:\n"
            "  Master log:     logs/socat-manager-<timestamp>.log\n"
            "  Session logs:   logs/session-<sid>.log\n"
            "  Session errors: logs/session-<sid>-error.log\n"
            "  Capture logs:   logs/capture-<proto>-<port>-<timestamp>.log\n"
            "\n"
            "Run '%(prog)s <mode> --help' for mode-specific options.\n"
            "Run '%(prog)s' with no arguments for interactive menu."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s v{__version__}",
    )

    # --- Subparsers ---
    subparsers = parser.add_subparsers(
        dest="mode",
        title="operational modes",
        metavar="MODE",
    )

    # === LISTEN ===
    p_listen = subparsers.add_parser(
        "listen",
        help="Start a single TCP/UDP listener on a port",
        description=(
            "Start a single TCP or UDP listener that captures incoming data\n"
            "to a log file. The listener forks per connection for concurrent\n"
            "client handling. Use --proto to select UDP or a specific address\n"
            "family, and --dual-stack to listen on both TCP and UDP."
        ),
        epilog=(
            "examples:\n"
            "  %(prog)s --port 8080\n"
            "  %(prog)s --port 5353 --proto udp4\n"
            "  %(prog)s --port 8080 --dual-stack\n"
            "  %(prog)s --port 8080 --capture\n"
            "  %(prog)s --port 4443 --proto tcp6\n"
            "  %(prog)s --port 80 --watchdog --bind 0.0.0.0"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_listen.add_argument("-p", "--port", required=True, help="Port to listen on")
    p_listen.add_argument("--proto", default=None, help="Protocol: tcp, tcp4, tcp6, udp, udp4, udp6 (default: tcp4)")
    p_listen.add_argument("--bind", default=None, help="Bind address for the listener")
    p_listen.add_argument("--name", default=None, help="Session name (default: proto-port)")
    p_listen.add_argument("--logfile", default=None, help="Custom log file path")
    p_listen.add_argument("--capture", action="store_true", help="Enable verbose traffic capture (-v)")
    p_listen.add_argument("--watchdog", action="store_true", help="Enable auto-restart on crash")
    p_listen.add_argument("--max-restarts", type=int, default=None, help="Max watchdog restart attempts (default: 10)")
    p_listen.add_argument("--backoff", type=int, default=None, help="Initial watchdog backoff delay in seconds (default: 1)")
    p_listen.add_argument("--dual-stack", action="store_true", help="Launch both TCP and UDP")
    p_listen.add_argument("--socat-opts", default=None, help="Extra socat address options")
    p_listen.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    # === BATCH ===
    p_batch = subparsers.add_parser(
        "batch",
        help="Start multiple listeners from port list/range/file",
        description=(
            "Start multiple listeners from a comma-separated port list,\n"
            "a port range (START-END), or a config file (one port per line).\n"
            "Each port gets an independent session with its own session ID."
        ),
        epilog=(
            "examples:\n"
            "  %(prog)s --ports 21,22,80,443\n"
            "  %(prog)s --range 8000-8010 --dual-stack\n"
            "  %(prog)s --file conf/ports.conf --watchdog\n"
            "  %(prog)s --ports 80,443 --proto udp4 --capture"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_batch.add_argument("--ports", default=None, help="Comma-separated port list (e.g., 21,22,80,443)")
    p_batch.add_argument("--range", default=None, help="Port range (e.g., 8000-8010)")
    p_batch.add_argument("--file", default=None, help="Config file with one port per line")
    p_batch.add_argument("--proto", default=None, help="Protocol (default: tcp4)")
    p_batch.add_argument("--capture", action="store_true", help="Enable verbose traffic capture")
    p_batch.add_argument("--watchdog", action="store_true", help="Enable auto-restart")
    p_batch.add_argument("--max-restarts", type=int, default=None, help="Max watchdog restart attempts (default: 10)")
    p_batch.add_argument("--backoff", type=int, default=None, help="Initial watchdog backoff seconds (default: 1)")
    p_batch.add_argument("--dual-stack", action="store_true", help="Launch both TCP and UDP per port")
    p_batch.add_argument("--socat-opts", default=None, help="Extra socat address options")
    p_batch.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    # === FORWARD ===
    p_forward = subparsers.add_parser(
        "forward",
        help="Forward traffic between local and remote endpoints",
        description=(
            "Bidirectional traffic relay between a local listener and a\n"
            "remote target. Supports cross-protocol forwarding via\n"
            "--remote-proto (e.g., TCP locally, UDP to remote)."
        ),
        epilog=(
            "examples:\n"
            "  %(prog)s --lport 8080 --rhost 10.0.0.5 --rport 80\n"
            "  %(prog)s --lport 5353 --rhost 8.8.8.8 --rport 53 --proto udp4\n"
            "  %(prog)s --lport 8080 --rhost 10.0.0.1 --rport 53 --remote-proto udp4\n"
            "  %(prog)s --lport 8080 --rhost 10.0.0.5 --rport 80 --capture --dual-stack"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_forward.add_argument("--lport", required=True, help="Local port to listen on")
    p_forward.add_argument("--rhost", required=True, help="Remote host to forward to")
    p_forward.add_argument("--rport", required=True, help="Remote port to forward to")
    p_forward.add_argument("--proto", default=None, help="Listen protocol (default: tcp4)")
    p_forward.add_argument("--remote-proto", default=None, help="Remote protocol (default: match listen)")
    p_forward.add_argument("--name", default=None, help="Session name")
    p_forward.add_argument("--capture", action="store_true", help="Enable traffic capture")
    p_forward.add_argument("--watchdog", action="store_true", help="Enable auto-restart")
    p_forward.add_argument("--max-restarts", type=int, default=None, help="Max watchdog restart attempts (default: 10)")
    p_forward.add_argument("--backoff", type=int, default=None, help="Initial watchdog backoff seconds (default: 1)")
    p_forward.add_argument("--dual-stack", action="store_true", help="Launch both TCP and UDP")
    p_forward.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    # === TUNNEL ===
    p_tunnel = subparsers.add_parser(
        "tunnel",
        help="Create TLS-encrypted tunnel via socat+OpenSSL",
        description=(
            "TLS tunnel: accepts encrypted connections on a local port and\n"
            "forwards plaintext traffic to a remote target. Auto-generates\n"
            "self-signed certificates if --cert/--key are not provided.\n"
            "Tunnel mode is TCP-only; --proto udp is rejected with guidance.\n"
            "--dual-stack adds a plaintext UDP forwarder (unencrypted)."
        ),
        epilog=(
            "examples:\n"
            "  %(prog)s --port 4443 --rhost 10.0.0.5 --rport 22\n"
            "  %(prog)s --port 4443 --rhost 10.0.0.5 --rport 22 --cert /path/cert.pem --key /path/key.pem\n"
            "  %(prog)s --port 4443 --rhost 10.0.0.5 --rport 22 --cn myserver.local\n"
            "  %(prog)s --port 4443 --rhost 10.0.0.5 --rport 22 --capture\n\n"
            "connect to tunnel:\n"
            "  socat - OPENSSL:localhost:4443,verify=0"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_tunnel.add_argument("-p", "--port", required=True, help="Local TLS listen port")
    p_tunnel.add_argument("--rhost", required=True, help="Remote host to tunnel to")
    p_tunnel.add_argument("--rport", required=True, help="Remote port to tunnel to")
    p_tunnel.add_argument("--cert", default=None, help="Certificate PEM file (auto-generated if omitted)")
    p_tunnel.add_argument("--key", default=None, help="Private key PEM file (auto-generated if omitted)")
    p_tunnel.add_argument("--cn", default=None, help="Common Name for auto-generated cert (default: localhost)")
    p_tunnel.add_argument("--proto", default=None, help="Protocol (TCP only — UDP rejected with guidance)")
    p_tunnel.add_argument("--name", default=None, help="Session name")
    p_tunnel.add_argument("--capture", action="store_true", help="Enable traffic capture (shows decrypted traffic)")
    p_tunnel.add_argument("--watchdog", action="store_true", help="Enable auto-restart")
    p_tunnel.add_argument("--max-restarts", type=int, default=None, help="Max watchdog restart attempts (default: 10)")
    p_tunnel.add_argument("--backoff", type=int, default=None, help="Initial watchdog backoff seconds (default: 1)")
    p_tunnel.add_argument("--dual-stack", action="store_true", help="Add plaintext UDP forwarder (unencrypted)")
    p_tunnel.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    # === REDIRECT ===
    p_redirect = subparsers.add_parser(
        "redirect",
        help="Redirect/proxy traffic transparently",
        description=(
            "Transparent port redirection between a local listener and a\n"
            "remote target. Bidirectional with optional traffic capture.\n"
            "Protocol-aware: --proto selects TCP or UDP individually;\n"
            "--dual-stack launches both on the same port."
        ),
        epilog=(
            "examples:\n"
            "  %(prog)s --lport 8443 --rhost example.com --rport 443\n"
            "  %(prog)s --lport 5353 --rhost 8.8.8.8 --rport 53 --proto udp4\n"
            "  %(prog)s --lport 8443 --rhost example.com --rport 443 --dual-stack --capture"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_redirect.add_argument("--lport", required=True, help="Local port to listen on")
    p_redirect.add_argument("--rhost", required=True, help="Remote host to redirect to")
    p_redirect.add_argument("--rport", required=True, help="Remote port to redirect to")
    p_redirect.add_argument("--proto", default=None, help="Protocol (default: tcp4)")
    p_redirect.add_argument("--name", default=None, help="Session name")
    p_redirect.add_argument("--capture", action="store_true", help="Enable traffic capture")
    p_redirect.add_argument("--watchdog", action="store_true", help="Enable auto-restart")
    p_redirect.add_argument("--max-restarts", type=int, default=None, help="Max watchdog restart attempts (default: 10)")
    p_redirect.add_argument("--backoff", type=int, default=None, help="Initial watchdog backoff seconds (default: 1)")
    p_redirect.add_argument("--dual-stack", action="store_true", help="Launch both TCP and UDP")
    p_redirect.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    # === STATUS ===
    p_status = subparsers.add_parser(
        "status",
        help="Display active sessions",
        description=(
            "List all registered sessions or show detailed information for\n"
            "a specific session. The optional argument is matched against\n"
            "session IDs (8-char hex), session names, and port numbers."
        ),
        epilog=(
            "examples:\n"
            "  %(prog)s                          # list all sessions\n"
            "  %(prog)s abcd1234                 # detail by session ID\n"
            "  %(prog)s tcp4-8080                # detail by session name\n"
            "  %(prog)s 8080                     # detail by port (both protocols)\n"
            "  %(prog)s --cleanup                # remove dead session files\n"
            "  %(prog)s -v                       # include system listener info"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_status.add_argument(
        "target", nargs="?", default=None,
        help="Session ID, name, or port for detailed view",
    )
    p_status.add_argument("--cleanup", action="store_true", help="Remove dead session files")
    p_status.add_argument("-v", "--verbose", action="store_true", help="Show system listener info")

    # === STOP ===
    p_stop = subparsers.add_parser(
        "stop",
        help="Stop sessions by ID, name, port, PID, or all",
        description=(
            "Terminate sessions using the 9-step protocol-scoped stop\n"
            "sequence: SIGTERM process group, SIGTERM PID + children,\n"
            "grace period, SIGKILL, port-based cleanup, verification.\n"
            "Stopping TCP on a shared port does NOT affect UDP."
        ),
        epilog=(
            "examples:\n"
            "  %(prog)s abcd1234               # stop by session ID\n"
            "  %(prog)s --all                   # stop all sessions\n"
            "  %(prog)s --name tcp4-8080        # stop by session name\n"
            "  %(prog)s --port 8080             # stop all on port (all protocols)\n"
            "  %(prog)s --pid 12345             # stop by PID"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_stop.add_argument(
        "target", nargs="?", default=None,
        help="Session ID or name to stop",
    )
    p_stop.add_argument("--all", action="store_true", help="Stop all sessions")
    p_stop.add_argument("--name", default=None, help="Stop by session name")
    p_stop.add_argument("--port", default=None, help="Stop all sessions on a port")
    p_stop.add_argument("--pid", default=None, help="Stop by PID")
    p_stop.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    # === MENU ===
    subparsers.add_parser(
        "menu",
        help="Launch interactive menu",
        description="Launch the interactive menu-driven interface.",
    )

    # === HELP (positional alias for --help) ===
    subparsers.add_parser(
        "help",
        help="Show help information",
        description="Display full help information and exit.",
    )

    # === VERSION (positional alias for --version) ===
    subparsers.add_parser(
        "version",
        help="Show version number",
        description="Display the version number and exit.",
    )

    return parser

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
#               - Global --log-level and --quiet/-q on all operational subcommands
#               - --allow (source range) and --tcpwrap on the listener modes
#               - 'menu' subcommand launches interactive mode
#
# Version     : 1.0.2
# ==============================================================================

"""CLI argument parser for socat-manager.

Provides the complete argparse configuration for all seven operational
modes plus the interactive menu launcher.
"""

from __future__ import annotations

import argparse

from socat_manager import __version__
from socat_manager.config import SCRIPT_NAME
from socat_manager.logging_setup import LOG_LEVEL_NAMES


def build_parser() -> argparse.ArgumentParser:
    """Build and return the complete CLI argument parser.

    Returns:
        Configured ArgumentParser with subparsers for all modes.
    """
    # --- Top-level parser ---
    parser = argparse.ArgumentParser(
        prog=SCRIPT_NAME,
        description=(
            "Socat Network Operations Manager — session-managed socat network "
            "operations across seven operational modes (listen, batch, forward, "
            "tunnel, redirect, status, stop), plus an audit-history query and an "
            "interactive menu."
        ),
        epilog=(
            "examples:\n"
            "  %(prog)s listen --port 8080\n"
            "  %(prog)s listen --port 5353 --proto udp4\n"
            "  %(prog)s listen --port 8080 --dual-stack\n"
            "  %(prog)s listen --port 8080 --allow 10.0.0.0/8 --tcpwrap\n"
            "  %(prog)s batch --ports 21,22,80,443\n"
            "  %(prog)s batch --range 8000-8010 --dual-stack\n"
            "  %(prog)s forward --lport 8080 --rhost 10.0.0.5 --rport 80\n"
            "  %(prog)s tunnel --port 4443 --rhost 10.0.0.5 --rport 22\n"
            "  %(prog)s redirect --lport 8443 --rhost example.com --rport 443 --capture\n"
            "  %(prog)s status\n"
            "  %(prog)s status abcd1234\n"
            "  %(prog)s stop --all\n"
            "  %(prog)s audit --history\n"
            "  %(prog)s audit --type crash --since 2026-01-01\n"
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
            "source filtering (listen, batch, forward, tunnel, redirect):\n"
            "  --allow <CIDR>       Accept connections only from an IPv4/IPv6\n"
            "                       source range (socat range=).\n"
            "  --tcpwrap [NAME]     Enforce /etc/hosts.allow and /etc/hosts.deny\n"
            "                       (socat tcpwrap=, default daemon name 'socat').\n"
            "\n"
            "reliability:\n"
            "  --watchdog enables auto-restart with exponential backoff.\n"
            "  Max 10 restarts before giving up. Backoff: 1s, 2s, 4s... 60s cap.\n"
            "\n"
            "logging:\n"
            "  --log-level <LEVEL>  DEBUG, INFO, WARNING, ERROR, CRITICAL (default INFO).\n"
            "  --verbose / -q       Shortcuts for DEBUG / WARNING console output.\n"
            "  Master log:     logs/socat-manager-<timestamp>.log\n"
            "  Session logs:   logs/session-<sid>.log\n"
            "  Session errors: logs/session-<sid>-error.log\n"
            "  Capture logs:   logs/capture-<proto>-<port>-<timestamp>.log\n"
            "\n"
            "auditing:\n"
            "  Session launches, stops, restarts, and crashes are recorded to a\n"
            "  SQLite store under audit/ (on by default). Disable per run with\n"
            "  --no-audit or globally with SOCAT_MANAGER_AUDIT=0. Review history\n"
            "  with '%(prog)s audit'.\n"
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

    # === AUDIT ===
    p_audit = subparsers.add_parser(
        "audit",
        help="Query the persistent audit history",
        description=(
            "Query the persistent audit store (read-only). Shows recorded\n"
            "events — launches, stops, restarts, crashes — or the per-session\n"
            "lifecycle summary. Never modifies live sessions."
        ),
        epilog=(
            "examples:\n"
            "  %(prog)s\n"
            "  %(prog)s --session a1b2c3d4\n"
            "  %(prog)s --type crash --limit 20\n"
            "  %(prog)s --since 2026-07-01 --json\n"
            "  %(prog)s --history\n"
            "  %(prog)s --prune"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_audit.add_argument("--session", default=None, help="Filter to one session ID")
    p_audit.add_argument(
        "--type", default=None, dest="event_type",
        help="Filter by event type (launch, stop, restart, crash, ...)",
    )
    p_audit.add_argument("--since", default=None, help="Only events at/after this ISO date/time")
    p_audit.add_argument("--limit", type=int, default=50, help="Maximum rows (0 = no limit)")
    p_audit.add_argument("--history", action="store_true", help="Show session lifecycle summaries")
    p_audit.add_argument("--json", action="store_true", dest="as_json", help="Output as JSON")
    p_audit.add_argument("--prune", action="store_true", help="Apply the configured retention now")

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

    # --- Global logging controls ---
    # Added uniformly to every operational subcommand so the option set lives in
    # one place. The short verbosity toggle -v is intentionally not reused here:
    # `status -v` already means "show system listener info", so only the
    # collision-free long options --log-level and --quiet (-q) are added. These
    # sit alongside the existing per-command --verbose, which remains a shortcut
    # for --log-level DEBUG. help and version take no options.
    for _sub_name, _sub_parser in subparsers.choices.items():
        if _sub_name in ("help", "version"):
            continue
        _sub_parser.add_argument(
            "--log-level",
            type=str.upper,
            choices=LOG_LEVEL_NAMES,
            default=None,
            metavar="LEVEL",
            help=(
                "Console log level: DEBUG, INFO, WARNING, ERROR, CRITICAL "
                "(default: INFO). Overrides --verbose and --quiet."
            ),
        )
        _sub_parser.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            help="Suppress informational output (alias for --log-level WARNING)",
        )
        _sub_parser.add_argument(
            "--no-audit",
            action="store_true",
            help="Disable audit recording for this invocation (auditing is on by default)",
        )

    # --- Source-filter controls on the modes that accept inbound connections ---
    # These restrict which peers a listener will accept, via socat's address
    # options range= (source subnet) and tcpwrap= (/etc/hosts.allow|deny).
    for _flt_name in ("listen", "batch", "forward", "tunnel", "redirect"):
        _flt_parser = subparsers.choices[_flt_name]
        _flt_parser.add_argument(
            "--allow",
            default=None,
            metavar="CIDR",
            help=(
                "Accept connections only from this source range "
                "(IPv4 or IPv6 CIDR, e.g. 10.0.0.0/8). Maps to socat range=."
            ),
        )
        _flt_parser.add_argument(
            "--tcpwrap",
            nargs="?",
            const="socat",
            default=None,
            metavar="NAME",
            help=(
                "Enforce access via TCP wrappers (/etc/hosts.allow and "
                "/etc/hosts.deny) using the given daemon name (default: socat). "
                "Requires a socat built with libwrap."
            ),
        )

    return parser

# ==============================================================================
# MODULE      : socat_manager/commands.py
# ==============================================================================
# Synopsis    : Socat command string builders for all operational modes
# Description : Constructs socat command argument lists for the four core
#               operational patterns. Each builder returns a list[str]
#               suitable for subprocess.Popen(cmd_list, shell=False).
#
#               Exact parity with bash builders (socat_manager.sh lines 1442-1626):
#                 - build_socat_listen_cmd()   → socat -u PROTO-LISTEN:... OPEN:...
#                 - build_socat_forward_cmd()  → socat PROTO-LISTEN:... PROTO:...
#                 - build_socat_tunnel_cmd()   → socat OPENSSL-LISTEN:... TCP4:...
#                 - build_socat_redirect_cmd() → socat PROTO-LISTEN:... PROTO:...
#
#               Also provides build_socat_cmd_string() for session file recording
#               and watchdog re-launch (returns the command as a single string
#               matching the bash session file SOCAT_CMD= value).
#
# Notes       : - All builders produce argument LISTS — never shell strings
#               - The SOCAT_CMD field in session files stores the joined string
#                 for human readability and bash-variant interoperability
#               - TCP options include backlog and keepalive
#               - UDP options include reuseaddr and fork only
#               - Capture mode adds -v flag for hex dump on stderr
#
# Version     : 0.9.0
# ==============================================================================

"""Socat command string builders for all operational modes.

Each builder returns a list[str] for subprocess.Popen(cmd_list, shell=False).
A companion function joins the list into a string for session file recording.
"""

from __future__ import annotations

from socat_manager.config import (
    DEFAULTS,
    SOCAT_CONNECT_ADDR,
    SOCAT_LISTEN_ADDR,
)

# ==============================================================================
# HELPER: socat address formatting
# ==============================================================================

def format_socat_host(host: str) -> str:
    """Format a host for inclusion in a socat address.

    socat address fields are colon-delimited, so an IPv6 literal must be
    enclosed in square brackets to keep its own colons from being read as
    field separators. Without the brackets, TCP6:2001:db8::1:443 is
    ambiguous — socat cannot tell where the address ends and the port
    begins — and the address is rejected.

    Hostnames and IPv4 literals contain no colons and are returned unchanged.
    A host that is already bracketed is returned unchanged.

    Args:
        host: Hostname, IPv4 literal, or IPv6 literal (already validated).

    Returns:
        The host, bracketed if it is an IPv6 literal.

    Example:
        2001:db8::1  ->  [2001:db8::1]
        10.0.0.5     ->  10.0.0.5
        example.com  ->  example.com
    """
    if ":" not in host:
        return host

    if host.startswith("[") and host.endswith("]"):
        return host

    return f"[{host}]"


def format_socat_endpoint(host: str, port: int | str) -> str:
    """Format a host and port as a socat address endpoint.

    Args:
        host: Hostname, IPv4 literal, or IPv6 literal (already validated).
        port: Port number.

    Returns:
        Endpoint string in HOST:PORT form, with IPv6 literals bracketed.
    """
    return f"{format_socat_host(host)}:{port}"


# ==============================================================================
# HELPER: Command list → string conversion
# ==============================================================================

def cmd_list_to_string(cmd: list[str]) -> str:
    """Join a command argument list into a single string.

    Used for recording in session files (SOCAT_CMD= field) and for
    display purposes. The resulting string matches what bash's
    build_socat_*_cmd() functions echo.

    Args:
        cmd: Command argument list.

    Returns:
        Space-joined command string.
    """
    return " ".join(cmd)


# ==============================================================================
# BUILDER 1: Listen Command
# Bash equivalent: build_socat_listen_cmd() — lines 1442-1489
# ==============================================================================

def build_socat_listen_cmd(
    proto: str,
    port: int,
    logfile: str,
    extra_opts: str = "",
    capture: bool = False,
) -> list[str]:
    """Build a socat command for a single-port listener.

    The listener captures incoming data unidirectionally (-u flag)
    from the network to a log file. When capture mode is enabled,
    socat's -v flag adds verbose hex dump output on stderr.

    Args:
        proto: Normalized protocol (tcp4, tcp6, udp4, udp6).
        port: Port number to listen on.
        logfile: Path to the data capture log file.
        extra_opts: Additional socat address options (pre-validated).
        capture: Whether to enable traffic capture (-v flag).

    Returns:
        Command argument list for subprocess.Popen.

    Example output (as string):
        socat -u TCP4-LISTEN:8080,reuseaddr,fork,backlog=128,keepalive OPEN:/path/log,creat,append
        socat -v -u TCP4-LISTEN:8080,reuseaddr,fork,backlog=128,keepalive OPEN:/path/log,creat,append
    """
    # Map protocol to socat address type
    socat_proto: str = SOCAT_LISTEN_ADDR[proto]

    # Base listener options
    listen_opts: str = "reuseaddr,fork"

    # TCP-specific options: backlog + keepalive
    if proto.startswith("tcp"):
        listen_opts += f",backlog={DEFAULTS.backlog},keepalive"

    # Append user-provided socat address options
    if extra_opts:
        listen_opts += f",{extra_opts}"

    # Build command list
    cmd: list[str] = ["socat"]

    # Capture mode: -v for verbose hex dump on stderr
    if capture:
        cmd.append("-v")

    # -u = unidirectional (from left/listener to right/file)
    cmd.append("-u")

    # Left side: network listener
    cmd.append(f"{socat_proto}:{port},{listen_opts}")

    # Right side: file output (creat=create if missing, append=don't overwrite)
    cmd.append(f"OPEN:{logfile},creat,append")

    return cmd


# ==============================================================================
# BUILDER 2: Forward Command
# Bash equivalent: build_socat_forward_cmd() — lines 1505-1543
# ==============================================================================

def build_socat_forward_cmd(
    listen_proto: str,
    lport: int,
    rhost: str,
    rport: int,
    remote_proto: str = "",
    capture: bool = False,
) -> list[str]:
    """Build a socat command for bidirectional port forwarding.

    Creates a full-duplex proxy between a local listener and a remote
    target. No -u flag (bidirectional). When capture mode is enabled,
    socat's -v flag captures both directions.

    Args:
        listen_proto: Local listen protocol (tcp4, tcp6, udp4, udp6).
        lport: Local port to listen on.
        rhost: Remote host to forward to.
        rport: Remote port to forward to.
        remote_proto: Remote protocol (defaults to listen_proto).
        capture: Whether to enable traffic capture (-v flag).

    Returns:
        Command argument list for subprocess.Popen.

    Example output (as string):
        socat TCP4-LISTEN:8080,reuseaddr,fork,backlog=128 TCP4:10.0.0.5:80
        socat TCP6-LISTEN:8080,reuseaddr,fork,backlog=128 TCP6:[2001:db8::1]:80
    """
    # Default remote protocol matches listen protocol
    if not remote_proto:
        remote_proto = listen_proto

    socat_listen: str = SOCAT_LISTEN_ADDR[listen_proto]
    socat_remote: str = SOCAT_CONNECT_ADDR[remote_proto]

    # Listener options
    listen_opts: str = "reuseaddr,fork"
    if listen_proto.startswith("tcp"):
        listen_opts += f",backlog={DEFAULTS.backlog},keepalive"

    # Build command list (no -u flag — bidirectional)
    cmd: list[str] = ["socat"]

    if capture:
        cmd.append("-v")

    # Left side: local listener
    cmd.append(f"{socat_listen}:{lport},{listen_opts}")

    # Right side: remote connector.
    # IPv6 literals are bracketed so their colons are not read as socat
    # address field separators.
    cmd.append(f"{socat_remote}:{format_socat_endpoint(rhost, rport)}")

    return cmd


# ==============================================================================
# BUILDER 3: Tunnel Command
# Bash equivalent: build_socat_tunnel_cmd() — lines 1559-1583
# ==============================================================================

def build_socat_tunnel_cmd(
    lport: int,
    rhost: str,
    rport: int,
    cert: str,
    key: str,
    capture: bool = False,
    remote_proto: str = "tcp4",
) -> list[str]:
    """Build a socat command for an encrypted (OpenSSL) tunnel.

    Accepts TLS connections on a local port and forwards plaintext
    traffic to a remote target. When capture mode is enabled,
    the hex dump shows DECRYPTED traffic.

    The listener is TLS over TCP. The remote leg's transport is TCP, and its
    address family is selectable so that an IPv6 remote target can be reached:
    a remote_proto of tcp6 produces a TCP6 connector, anything else a TCP4
    connector.

    Args:
        lport: Local port to listen on (encrypted endpoint).
        rhost: Remote host to tunnel to.
        rport: Remote port to tunnel to.
        cert: Path to certificate PEM file.
        key: Path to private key PEM file.
        capture: Whether to enable traffic capture (-v flag).
        remote_proto: Remote address family selector (tcp4 or tcp6).

    Returns:
        Command argument list for subprocess.Popen.

    Example output (as string):
        socat OPENSSL-LISTEN:4443,cert=/path/cert.pem,key=/path/key.pem,verify=0,reuseaddr,fork TCP4:10.0.0.5:22
        socat OPENSSL-LISTEN:4443,cert=/path/cert.pem,key=/path/key.pem,verify=0,reuseaddr,fork TCP6:[2001:db8::1]:22
    """
    cmd: list[str] = ["socat"]

    if capture:
        cmd.append("-v")

    # Left side: OpenSSL listener
    # verify=0: don't verify client certificates (server mode)
    ssl_opts: str = (
        f"OPENSSL-LISTEN:{lport},"
        f"cert={cert},key={key},"
        f"verify=0,reuseaddr,fork"
    )
    cmd.append(ssl_opts)

    # Right side: plaintext TCP connection to remote.
    # The address family follows remote_proto so an IPv6 target is reachable.
    # IPv6 literals are bracketed so their colons are not read as socat
    # address field separators.
    socat_remote: str = SOCAT_CONNECT_ADDR.get(remote_proto, "TCP4")
    cmd.append(f"{socat_remote}:{format_socat_endpoint(rhost, rport)}")

    return cmd


# ==============================================================================
# BUILDER 4: Redirect Command
# Bash equivalent: build_socat_redirect_cmd() — lines 1596-1626
# ==============================================================================

def build_socat_redirect_cmd(
    proto: str,
    lport: int,
    rhost: str,
    rport: int,
    capture: bool = False,
) -> list[str]:
    """Build a socat command for transparent traffic redirection.

    Bidirectional forwarding with optional traffic logging.
    Protocol-aware: supports TCP and UDP independently.

    Args:
        proto: Protocol (tcp4, tcp6, udp4, udp6).
        lport: Local port to listen on.
        rhost: Remote host to redirect to.
        rport: Remote port to redirect to.
        capture: Whether to enable traffic capture (-v flag).

    Returns:
        Command argument list for subprocess.Popen.

    Example output (as string):
        socat TCP4-LISTEN:8443,reuseaddr,fork,backlog=128 TCP4:example.com:443
        socat TCP6-LISTEN:8443,reuseaddr,fork,backlog=128 TCP6:[2001:db8::1]:443
    """
    socat_listen: str = SOCAT_LISTEN_ADDR[proto]
    socat_remote: str = SOCAT_CONNECT_ADDR[proto]

    # Listener options
    listen_opts: str = "reuseaddr,fork"
    if proto.startswith("tcp"):
        listen_opts += f",backlog={DEFAULTS.backlog},keepalive"

    # Build command list (no -u flag — bidirectional)
    cmd: list[str] = ["socat"]

    if capture:
        cmd.append("-v")

    # Left side: local listener
    cmd.append(f"{socat_listen}:{lport},{listen_opts}")

    # Right side: remote connector.
    # IPv6 literals are bracketed so their colons are not read as socat
    # address field separators.
    cmd.append(f"{socat_remote}:{format_socat_endpoint(rhost, rport)}")

    return cmd

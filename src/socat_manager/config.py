# ==============================================================================
# MODULE      : socat_manager/config.py
# ==============================================================================
# Synopsis    : Configuration constants and defaults for socat-manager
# Description : Centralizes all compile-time constants, default values,
#               directory paths, color codes, and status symbols used
#               across the application. All values are immutable (frozen
#               dataclass or module-level constants) to prevent accidental
#               modification at runtime.
#
#               Achieves exact parity with the bash CONSTANTS AND
#               CONFIGURATION section (socat_manager.sh lines 115-187).
#
# Notes       : - No external dependencies (standard library only)
#               - Paths are resolved relative to the script's location
#                 at runtime via resolve_base_dir()
#               - Color codes are conditionally applied based on terminal
#                 detection (see logging_setup.py)
#               - All DEFAULT_* values match bash v2.3.0 exactly
#
# Version     : 1.0.1
# ==============================================================================

"""Configuration constants and defaults for socat-manager.

All values are immutable. Directory paths are resolved at runtime
relative to the entry point's location via resolve_base_dir().
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# ==============================================================================
# SCRIPT METADATA
# ==============================================================================

SCRIPT_NAME: Final[str] = "socat-manager"
SCRIPT_VERSION: Final[str] = "1.0.1"


# ==============================================================================
# DIRECTORY RESOLUTION
# ==============================================================================

def resolve_base_dir() -> Path:
    """Resolve the base directory for runtime data (logs, sessions, certs, conf).

    Resolution order:
        1. SOCAT_MANAGER_BASE environment variable (explicit override)
        2. Parent of the entry-point script's directory
        3. Current working directory as last resort

    Returns:
        Absolute Path to the base directory.
    """
    # Allow explicit override via environment variable
    env_base: str | None = os.environ.get("SOCAT_MANAGER_BASE")
    if env_base:
        return Path(env_base).resolve()

    # Derive from the entry point location (matches bash SCRIPT_DIR behavior)
    # __main__.py lives in src/socat_manager/ — base is two levels up
    # When installed, the package root is the working directory
    main_module: str | None = getattr(sys.modules.get("__main__"), "__file__", None)
    if main_module:
        entry_path: Path = Path(main_module).resolve()
        # If running from source tree: src/socat_manager/__main__.py → project root
        candidate: Path = entry_path.parent.parent.parent
        if (candidate / "src").is_dir() or (candidate / "Makefile").is_file():
            return candidate
        # If running installed: use parent of the package directory
        return entry_path.parent

    # Fallback: current working directory
    return Path.cwd()


# ==============================================================================
# RUNTIME PATHS (resolved lazily, cached)
# ==============================================================================

@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Immutable container for all runtime directory and file paths.

    All paths are derived from base_dir. Directories are NOT created here;
    _ensure_dirs() in the logging/session modules handles creation with
    correct permissions.
    """

    base_dir: Path

    @property
    def log_dir(self) -> Path:
        """Directory for all log files."""
        return self.base_dir / "logs"

    @property
    def session_dir(self) -> Path:
        """Directory for session metadata files (permissions 0o700)."""
        return self.base_dir / "sessions"

    @property
    def conf_dir(self) -> Path:
        """Directory for configuration files (e.g., ports.conf)."""
        return self.base_dir / "conf"

    @property
    def cert_dir(self) -> Path:
        """Directory for TLS certificates and private keys."""
        return self.base_dir / "certs"

    @property
    def audit_dir(self) -> Path:
        """Directory for the persistent audit store (permissions 0o700)."""
        return self.base_dir / "audit"

    @property
    def audit_db(self) -> Path:
        """Default path to the SQLite audit database (permissions 0o600)."""
        return self.audit_dir / "socat-manager-audit.db"

    @property
    def session_lock_file(self) -> Path:
        """Advisory lock file for session directory operations."""
        return self.session_dir / ".lock"


# ==============================================================================
# DEFAULT OPERATIONAL VALUES
# Exact parity with bash readonly DEFAULT_* constants (lines 142-156)
# ==============================================================================

@dataclass(frozen=True, slots=True)
class Defaults:
    """Immutable default operational values.

    Every field corresponds 1:1 to a bash DEFAULT_* or timing constant.
    """

    # Protocol default (IPv4 TCP)
    protocol: str = "tcp4"

    # socat listener backlog depth
    backlog: int = 128

    # Watchdog process-death poll interval (seconds)
    watchdog_poll_interval: int = 1

    # Maximum auto-restarts before watchdog gives up
    watchdog_max_restarts: int = 10

    # Maximum concurrent sessions to prevent resource exhaustion
    max_sessions: int = 256

    # Stop timing constants
    stop_grace_seconds: int = 5
    stop_verify_retries: int = 5
    stop_verify_interval: float = 0.5

    # Process launch stability check delay (seconds)
    launch_stability_delay: float = 0.3


# Singleton instances (module-level, import once)
DEFAULTS: Final[Defaults] = Defaults()


# ==============================================================================
# EXECUTION CONTEXT
# Per-invocation values that are set once at startup and never change.
# ==============================================================================

def _generate_correlation_id() -> str:
    """Generate an 8-character hex correlation ID for this execution.

    Uses uuid4 as primary entropy source.  Falls back to a
    timestamp+PID hash if uuid generation fails unexpectedly.

    Returns:
        8-character lowercase hex string.
    """
    try:
        return uuid.uuid4().hex[:8]
    except Exception:
        # Fallback: hash of timestamp + PID (matches bash fallback behavior)
        seed: str = f"{time.time_ns()}{os.getpid()}"
        return hashlib.sha256(seed.encode()).hexdigest()[:8]


def _generate_exec_timestamp() -> str:
    """Generate an ISO-ish timestamp for this execution.

    Format: YYYY-MM-DDTHH-MM-SS (hyphens in time for safe filenames).
    Matches bash EXEC_TIMESTAMP format exactly.

    Returns:
        Timestamp string safe for use in filenames.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).astimezone()
    return now.strftime("%Y-%m-%dT%H-%M-%S")


# These are computed once at import time and remain constant for the
# lifetime of this process, exactly like bash's readonly variables.
EXEC_TIMESTAMP: Final[str] = _generate_exec_timestamp()
CORRELATION_ID: Final[str] = _generate_correlation_id()
SCRIPT_PID: Final[int] = os.getpid()


# ==============================================================================
# COLOR CODES AND STATUS SYMBOLS
# Terminal output formatting — used by logging_setup.py and menu.py.
# Matches bash color codes (lines 164-187) exactly.
# ==============================================================================

@dataclass(frozen=True, slots=True)
class Colors:
    """ANSI escape sequences for terminal color output.

    These are raw escape strings. The logging and display layers
    gate their use on terminal detection (is stderr a TTY?).
    """

    reset: str = "\033[0m"
    bold: str = "\033[1m"
    dim: str = "\033[2m"
    red: str = "\033[31m"
    green: str = "\033[32m"
    yellow: str = "\033[33m"
    blue: str = "\033[34m"
    magenta: str = "\033[35m"
    cyan: str = "\033[36m"
    white: str = "\033[37m"


@dataclass(frozen=True, slots=True)
class Symbols:
    """Unicode status symbols for terminal output.

    Matches bash SYM_* constants (lines 177-187) exactly.
    """

    ok: str = "✓"
    fail: str = "✗"
    warn: str = "!"
    info: str = "i"
    arrow: str = "→"
    plus: str = "+"
    listen: str = "◉"
    forward: str = "⇄"
    tunnel: str = "⊙"
    session: str = "■"


# Singleton instances
COLORS: Final[Colors] = Colors()
SYMBOLS: Final[Symbols] = Symbols()


# ==============================================================================
# VALID PROTOCOL SET
# Whitelist of accepted protocol identifiers (post-normalization).
# ==============================================================================

VALID_PROTOCOLS: Final[frozenset[str]] = frozenset({
    "tcp4", "tcp6", "udp4", "udp6",
})

# Protocol normalization map (shorthand → canonical)
PROTOCOL_NORMALIZATION: Final[dict[str, str]] = {
    "tcp": "tcp4",
    "tcp4": "tcp4",
    "tcp6": "tcp6",
    "udp": "udp4",
    "udp4": "udp4",
    "udp6": "udp6",
}

# Alternate protocol mapping for dual-stack (tcp4 ↔ udp4, tcp6 ↔ udp6)
ALT_PROTOCOL: Final[dict[str, str]] = {
    "tcp4": "udp4",
    "udp4": "tcp4",
    "tcp6": "udp6",
    "udp6": "tcp6",
}

# Map normalized protocol to socat LISTEN address type
SOCAT_LISTEN_ADDR: Final[dict[str, str]] = {
    "tcp4": "TCP4-LISTEN",
    "tcp6": "TCP6-LISTEN",
    "udp4": "UDP4-LISTEN",
    "udp6": "UDP6-LISTEN",
}

# Map normalized protocol to socat CONNECT address type
SOCAT_CONNECT_ADDR: Final[dict[str, str]] = {
    "tcp4": "TCP4",
    "tcp6": "TCP6",
    "udp4": "UDP4",
    "udp6": "UDP6",
}


# ==============================================================================
# PROTOCOL SCOPE DERIVATION
# A protocol is a transport plus an address family. Every socket query must
# preserve both dimensions: tcp4 and tcp6 listeners are independent sockets
# that can hold the same port number simultaneously, which is precisely what
# dual-stack operation creates. Collapsing the family would let one protocol's
# listener appear to occupy another's port, and would place an unrelated
# session within reach of the port-based cleanup path.
# ==============================================================================

def protocol_transport(proto: str) -> str:
    """Return the transport component of a normalized protocol.

    Args:
        proto: Normalized protocol (tcp4, tcp6, udp4, udp6).

    Returns:
        "udp" for UDP protocols, "tcp" otherwise.
    """
    return "udp" if "udp" in proto else "tcp"


def protocol_family(proto: str) -> str:
    """Return the address family component of a normalized protocol.

    Args:
        proto: Normalized protocol (tcp4, tcp6, udp4, udp6).

    Returns:
        "6" for IPv6 protocols, "4" otherwise.
    """
    return "6" if proto.endswith("6") else "4"


def socket_scope_flags(proto: str) -> list[str]:
    """Build the socket-listing flags that scope a query to one protocol.

    Both ss and netstat accept the same short flags: -t/-u selects the
    transport, -4/-6 selects the address family, -l restricts the listing to
    listening sockets, and -n disables name resolution.

    Args:
        proto: Normalized protocol (tcp4, tcp6, udp4, udp6).

    Returns:
        Flag list, for example ["-t", "-4", "-l", "-n"] for tcp4.
    """
    transport_flag: str = "-u" if protocol_transport(proto) == "udp" else "-t"
    family_flag: str = f"-{protocol_family(proto)}"
    return [transport_flag, family_flag, "-l", "-n"]


# ==============================================================================
# SESSION FILE FORMAT CONSTANTS
# Field names used in session .session files. Must match bash format exactly
# for cross-variant interoperability.
# ==============================================================================

@dataclass(frozen=True, slots=True)
class SessionFields:
    """Session file field names — must match bash session_register() output."""

    session_id: str = "SESSION_ID"
    session_name: str = "SESSION_NAME"
    pid: str = "PID"
    pgid: str = "PGID"
    mode: str = "MODE"
    protocol: str = "PROTOCOL"
    local_port: str = "LOCAL_PORT"
    remote_host: str = "REMOTE_HOST"
    remote_port: str = "REMOTE_PORT"
    socat_cmd: str = "SOCAT_CMD"
    started: str = "STARTED"
    correlation: str = "CORRELATION"
    launcher_pid: str = "LAUNCHER_PID"


SESSION_FIELDS: Final[SessionFields] = SessionFields()

# Session file header template (matches bash heredoc output)
SESSION_FILE_VERSION: Final[str] = "v2.3"


# ==============================================================================
# DEPENDENCY REQUIREMENTS
# Required and optional external commands checked at startup.
# ==============================================================================

# Note: Python variant uses os.setsid() via preexec_fn, NOT the setsid binary.
# The bash variant requires the setsid binary, but Python does not.
REQUIRED_COMMANDS: Final[tuple[str, ...]] = ("socat", "openssl", "ss")
OPTIONAL_COMMANDS: Final[tuple[str, ...]] = ("flock", "lsof", "pstree")


# ==============================================================================
# VALIDATION CONSTANTS
# Boundary limits and patterns used by validation.py.
# ==============================================================================

# Port range limits
PORT_MIN: Final[int] = 1
PORT_MAX: Final[int] = 65535
PRIVILEGED_PORT_THRESHOLD: Final[int] = 1024

# Port range maximum span
PORT_RANGE_MAX_SPAN: Final[int] = 1000

# Session name maximum length
SESSION_NAME_MAX_LENGTH: Final[int] = 64

# Session ID length (hex characters)
SESSION_ID_LENGTH: Final[int] = 8

# Hostname shell metacharacters to reject
HOSTNAME_FORBIDDEN_CHARS: Final[str] = r";|&$`(){}[]<>!#"

# File path forbidden characters
FILEPATH_FORBIDDEN_CHARS: Final[str] = r";|&$`"

# Socat options whitelist pattern (regex character class interior)
SOCAT_OPTS_WHITELIST: Final[str] = r"a-zA-Z0-9=,.:/_\-"

# Session name whitelist pattern (regex character class interior)
SESSION_NAME_WHITELIST: Final[str] = r"a-zA-Z0-9._\-"

# IPv6 validation limits
IPV6_MIN_LENGTH: Final[int] = 2
IPV6_MAX_LENGTH: Final[int] = 39
IPV6_MAX_COLONS: Final[int] = 7

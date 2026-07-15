# ==============================================================================
# MODULE      : socat_manager/validation.py
# ==============================================================================
# Synopsis    : Input validation for all user-supplied parameters
# Description : Implements all 9 validators from the bash version with exact
#               behavioral parity (socat_manager.sh lines 345-636):
#
#               1. validate_port()          — numeric, 1-65535, privileged warn
#               2. validate_port_range()    — START-END format, max 1000 span
#               3. validate_port_list()     — comma/semicolon separated ports
#               4. validate_hostname()      — IPv4, IPv6, RFC 1123 hostname
#               5. validate_protocol()      — whitelist normalize: tcp→tcp4
#               6. validate_file_path()     — reject traversal, metacharacters
#               7. validate_socat_opts()    — whitelist [a-zA-Z0-9=,.:/_-]
#               8. validate_session_name()  — whitelist [a-zA-Z0-9._-], max 64
#               9. validate_session_id()    — exactly 8 lowercase hex chars
#
#               All validators follow whitelist-based design (SEC-01 / CWE-20).
#               Validation occurs at the trust boundary BEFORE any input
#               reaches command builders, session files, or log messages.
#
# Notes       : - Every validator raises ValidationError on invalid input
#               - Validators also log via logging_setup for audit trail
#               - validate_port_range() and validate_port_list() return
#                 lists of valid ports (not generators) for predictable
#                 consumption
#               - Shell metacharacter rejection matches bash patterns exactly
#
# Version     : 0.9.0
# ==============================================================================

"""Input validation for all user-supplied parameters.

All validators raise ValidationError on invalid input. Every function
validates at the trust boundary before data reaches command builders,
session files, or subprocess calls.
"""

from __future__ import annotations

import os
import re
from typing import Final

from socat_manager.config import (
    FILEPATH_FORBIDDEN_CHARS,
    HOSTNAME_FORBIDDEN_CHARS,
    IPV6_MAX_COLONS,
    IPV6_MAX_LENGTH,
    IPV6_MIN_LENGTH,
    PORT_MAX,
    PORT_MIN,
    PORT_RANGE_MAX_SPAN,
    PRIVILEGED_PORT_THRESHOLD,
    PROTOCOL_NORMALIZATION,
    SESSION_ID_LENGTH,
    SESSION_NAME_MAX_LENGTH,
    SESSION_NAME_WHITELIST,
    SOCAT_OPTS_WHITELIST,
)
from socat_manager.logging_setup import log_error, log_warning

# ==============================================================================
# CUSTOM EXCEPTION
# ==============================================================================

class ValidationError(ValueError):
    """Raised when user input fails validation.

    Inherits from ValueError for compatibility with standard exception
    handling patterns. Carries the original input and a human-readable
    reason for logging and user feedback.
    """

    def __init__(self, message: str, *, field: str = "", value: str = "") -> None:
        """Initialize a ValidationError.

        Args:
            message: Human-readable error description.
            field: Name of the field/parameter that failed validation.
            value: The invalid value (sanitized for logging).
        """
        super().__init__(message)
        self.field: str = field
        self.value: str = value


# ==============================================================================
# COMPILED REGEX PATTERNS (compiled once at import time)
# Patterns derived from config.py constants — config is the single source of
# truth for allowed/forbidden character sets.
# ==============================================================================

# Port range format: digits-digits (e.g., "8000-8010")
_PORT_RANGE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(\d+)-(\d+)$")

# Pure numeric string
_NUMERIC_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9]+$")

# IPv4 address: four groups of 1-3 digits separated by dots
_IPV4_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
)

# IPv6 candidate: hex digits and colons only, must contain at least one colon
_IPV6_CANDIDATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F:]+$")

# IPv6 hex group: each group must be 1-4 hex characters
_IPV6_GROUP_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{1,4}$")

# RFC 1123 hostname: alphanumeric, hyphens, dots
# Each label: starts/ends alphanumeric, up to 63 chars, hyphens in middle
_HOSTNAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
    r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
)

# Session ID: exactly 8 lowercase hex characters
_SESSION_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"^[a-f0-9]{{{SESSION_ID_LENGTH}}}$"
)

# Session name whitelist — derived from config.SESSION_NAME_WHITELIST
_SESSION_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"^[{SESSION_NAME_WHITELIST}]+$"
)

# Socat options whitelist — derived from config.SOCAT_OPTS_WHITELIST
_SOCAT_OPTS_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"^[{SOCAT_OPTS_WHITELIST}]+$"
)

# Shell metacharacters forbidden in hostnames — derived from config.HOSTNAME_FORBIDDEN_CHARS
_HOSTNAME_FORBIDDEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[" + re.escape(HOSTNAME_FORBIDDEN_CHARS) + r"]"
)

# Shell metacharacters forbidden in file paths — derived from config.FILEPATH_FORBIDDEN_CHARS
_FILEPATH_FORBIDDEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[" + re.escape(FILEPATH_FORBIDDEN_CHARS) + r"]"
)


# ==============================================================================
# VALIDATOR 1: validate_port
# Bash equivalent: lines 345-366
# ==============================================================================

def validate_port(port: str | int) -> int:
    """Validate a port number is numeric and within valid range (1-65535).

    Warns if the port is privileged (<1024) and the process is not running
    as root, but does NOT reject it — the user may have capabilities or
    plan to run with sudo.

    Args:
        port: Port number as string or integer.

    Returns:
        Validated port number as integer.

    Raises:
        ValidationError: If port is non-numeric or out of range.
    """
    port_str: str = str(port).strip()

    # Must be a positive integer
    if not _NUMERIC_PATTERN.match(port_str):
        msg: str = f"Invalid port '{port_str}': must be a number"
        log_error(msg, "validation")
        raise ValidationError(msg, field="port", value=port_str)

    port_int: int = int(port_str)

    # Must be in valid range
    if port_int < PORT_MIN or port_int > PORT_MAX:
        msg = f"Port {port_int} out of range ({PORT_MIN}-{PORT_MAX})"
        log_error(msg, "validation")
        raise ValidationError(msg, field="port", value=port_str)

    # Warn if privileged port and not root
    if port_int < PRIVILEGED_PORT_THRESHOLD and os.geteuid() != 0:
        log_warning(
            f"Port {port_int} is privileged (<{PRIVILEGED_PORT_THRESHOLD}); "
            "root/sudo required",
            "validation",
        )

    return port_int


# ==============================================================================
# VALIDATOR 2: validate_port_range
# Bash equivalent: lines 377-407
# ==============================================================================

def validate_port_range(range_str: str) -> list[int]:
    """Validate a port range string and return the list of ports.

    Format: START-END where START < END. Maximum span is 1000 ports
    to prevent accidental resource exhaustion.

    Args:
        range_str: Port range string (e.g., "8000-8010").

    Returns:
        List of integer port numbers in the range [START, END].

    Raises:
        ValidationError: If format is invalid, ports are invalid,
                        start >= end, or span exceeds 1000.
    """
    range_str = range_str.strip()

    match = _PORT_RANGE_PATTERN.match(range_str)
    if not match:
        msg: str = f"Invalid port range '{range_str}': use format START-END"
        log_error(msg, "validation")
        raise ValidationError(msg, field="port_range", value=range_str)

    # Validate each endpoint as a port
    start: int = validate_port(match.group(1))
    end: int = validate_port(match.group(2))

    if start >= end:
        msg = f"Range start ({start}) must be less than end ({end})"
        log_error(msg, "validation")
        raise ValidationError(msg, field="port_range", value=range_str)

    # Sanity check: prevent absurdly large ranges
    span: int = end - start + 1
    if span > PORT_RANGE_MAX_SPAN:
        msg = f"Port range too large ({span} ports). Max {PORT_RANGE_MAX_SPAN}."
        log_error(msg, "validation")
        raise ValidationError(msg, field="port_range", value=range_str)

    return list(range(start, end + 1))


# ==============================================================================
# VALIDATOR 3: validate_port_list
# Bash equivalent: lines 417-439
# ==============================================================================

def validate_port_list(list_str: str) -> list[int]:
    """Validate a comma/semicolon-separated port list.

    Sanitizes input by removing spaces and replacing semicolons with
    commas. Skips invalid individual ports but logs warnings for them.
    Returns at least one valid port or raises ValidationError.

    Args:
        list_str: Comma or semicolon separated port numbers
                  (e.g., "21,22,80,443").

    Returns:
        List of valid integer port numbers.

    Raises:
        ValidationError: If no valid ports are found in the list.
    """
    # Sanitize: remove spaces, replace semicolons with commas
    cleaned: str = list_str.replace(" ", "").replace(";", ",")

    valid_ports: list[int] = []
    for token in cleaned.split(","):
        if not token:
            continue
        try:
            valid_ports.append(validate_port(token))
        except ValidationError:
            # Skip invalid entries (bash behavior: warns and continues)
            log_warning(f"Skipping invalid port in list: '{token}'", "validation")

    if not valid_ports:
        msg: str = f"No valid ports found in list '{list_str}'"
        log_error(msg, "validation")
        raise ValidationError(msg, field="port_list", value=list_str)

    return valid_ports


# ==============================================================================
# VALIDATOR 4: validate_hostname
# Bash equivalent: lines 448-500
# ==============================================================================

def validate_hostname(host: str) -> str:
    """Validate a hostname or IP address for use as a network target.

    Accepts:
        - IPv4 addresses (four octets, each 0-255)
        - IPv6 addresses (hex:colon format, length 2-39, max 7 colons)
        - RFC 1123 hostnames (alphanumeric, hyphens, dots)

    Rejects shell metacharacters to prevent command injection.

    Args:
        host: Hostname or IP address string.

    Returns:
        The validated hostname string (unchanged).

    Raises:
        ValidationError: If hostname is empty, contains forbidden
                        characters, or fails all format checks.
    """
    host = host.strip()

    # Empty check
    if not host:
        msg: str = "Empty hostname/IP provided"
        log_error(msg, "validation")
        raise ValidationError(msg, field="hostname", value="")

    # Sanitize: reject dangerous characters (command injection prevention)
    if _HOSTNAME_FORBIDDEN_PATTERN.search(host):
        msg = f"Hostname contains forbidden characters: '{host}'"
        log_error(msg, "validation")
        raise ValidationError(msg, field="hostname", value=host)

    # --- IPv4 validation ---
    ipv4_match = _IPV4_PATTERN.match(host)
    if ipv4_match:
        # Check each octet is 0-255
        for i in range(1, 5):
            octet: int = int(ipv4_match.group(i))
            if octet > 255:
                msg = (
                    f"Invalid IPv4 address: {host} "
                    f"(octet {octet} > 255)"
                )
                log_error(msg, "validation")
                raise ValidationError(msg, field="hostname", value=host)
        return host

    # --- IPv6 validation ---
    if _IPV6_CANDIDATE_PATTERN.match(host) and ":" in host:
        ipv6_len: int = len(host)
        if ipv6_len < IPV6_MIN_LENGTH or ipv6_len > IPV6_MAX_LENGTH:
            msg = (
                f"Invalid IPv6 address: '{host}' "
                f"(length {ipv6_len}, expected {IPV6_MIN_LENGTH}-{IPV6_MAX_LENGTH})"
            )
            log_error(msg, "validation")
            raise ValidationError(msg, field="hostname", value=host)

        # Count colons — max 7 in a valid IPv6 address
        colon_count: int = host.count(":")
        if colon_count > IPV6_MAX_COLONS:
            msg = f"Invalid IPv6 address: '{host}' (too many colons)"
            log_error(msg, "validation")
            raise ValidationError(msg, field="hostname", value=host)

        # Validate each hex group is 1-4 characters.
        # Split by ':' produces empty strings for '::' (compressed zeros) — those are valid.
        groups: list[str] = host.split(":")
        for group in groups:
            if group and not _IPV6_GROUP_PATTERN.match(group):
                msg = (
                    f"Invalid IPv6 address: '{host}' "
                    f"(group '{group}' exceeds 4 hex characters)"
                )
                log_error(msg, "validation")
                raise ValidationError(msg, field="hostname", value=host)

        return host

    # --- Hostname validation (RFC 1123) ---
    if _HOSTNAME_PATTERN.match(host):
        return host

    # None of the formats matched
    msg = f"Invalid hostname/IP: '{host}'"
    log_error(msg, "validation")
    raise ValidationError(msg, field="hostname", value=host)


# ==============================================================================
# VALIDATOR 5: validate_protocol
# Bash equivalent: lines 510-524
# ==============================================================================

def is_ipv6_literal(host: str) -> bool:
    """Report whether a host string is an IPv6 literal.

    A host is treated as an IPv6 literal when it contains a colon and consists
    only of hex digits and colons — the same shape the hostname validator uses
    to route a value into IPv6 handling. Hostnames and IPv4 literals contain no
    colons and return False.

    This is used to select the address family of a connector for a validated
    host, so that an IPv6 target is reached over an IPv6 connector.

    Args:
        host: Host string (expected to have passed validate_hostname).

    Returns:
        True if the host is an IPv6 literal, False otherwise.
    """
    host = host.strip()
    return ":" in host and bool(_IPV6_CANDIDATE_PATTERN.match(host))


def validate_protocol(proto: str) -> str:
    """Validate and normalize a protocol string.

    Accepts shorthand (tcp, udp) and explicit forms (tcp4, tcp6, etc.).
    Returns the normalized canonical protocol string.

    Args:
        proto: Protocol string to validate.

    Returns:
        Normalized protocol string (tcp4, tcp6, udp4, or udp6).

    Raises:
        ValidationError: If protocol is not in the accepted whitelist.
    """
    normalized: str = proto.strip().lower()

    canonical: str | None = PROTOCOL_NORMALIZATION.get(normalized)
    if canonical is None:
        msg: str = (
            f"Invalid protocol '{proto}'. "
            "Supported: tcp, tcp4, tcp6, udp, udp4, udp6"
        )
        log_error(msg, "validation")
        raise ValidationError(msg, field="protocol", value=proto)

    return canonical


# ==============================================================================
# VALIDATOR 6: validate_file_path
# Bash equivalent: lines 532-553
# ==============================================================================

def validate_writable_path(path: str) -> str:
    """Validate a path that will be written to (the file need not yet exist).

    A write target such as a capture or log file is created by socat at launch,
    so unlike validate_file_path() this does not require the path to exist or be
    readable. It applies the same structural safety checks: a non-empty path,
    no parent-directory traversal component, and none of the shell
    metacharacters that config.FILEPATH_FORBIDDEN_CHARS forbids.

    The forbidden character set is taken from configuration, so this validator
    and validate_file_path() share one definition rather than each carrying a
    separate literal.

    Args:
        path: File path string to validate as a write target.

    Returns:
        The validated path string (stripped of surrounding whitespace).

    Raises:
        ValidationError: If the path is empty, contains a traversal component,
                        or contains a forbidden character.
    """
    path = path.strip()

    if not path:
        msg: str = "Empty file path"
        log_error(msg, "validation")
        raise ValidationError(msg, field="file_path", value="")

    # Block path traversal — check for ".." as a path COMPONENT, not substring,
    # so a legal name like "file..ext" is allowed while "../etc/passwd" is not.
    components: list[str] = path.replace("\\", "/").split("/")
    if ".." in components:
        msg = f"Path traversal detected in '{path}'"
        log_error(msg, "validation")
        raise ValidationError(msg, field="file_path", value=path)

    # Block command injection characters, using the shared config definition.
    if _FILEPATH_FORBIDDEN_PATTERN.search(path):
        msg = f"Forbidden characters in path '{path}'"
        log_error(msg, "validation")
        raise ValidationError(msg, field="file_path", value=path)

    return path


def validate_file_path(path: str) -> str:
    """Validate a file path is safe and accessible for use.

    Applies the structural safety checks of validate_writable_path() — a
    non-empty path, no traversal component, no forbidden characters — and then
    adds the requirements specific to an input file: the file must exist and be
    readable by the current user.

    Args:
        path: File path string to validate.

    Returns:
        The validated path string (stripped of surrounding whitespace).

    Raises:
        ValidationError: If path is empty, contains traversal sequences,
                        contains forbidden characters, does not exist,
                        or is not readable.
    """
    # Structural checks shared with write-target validation.
    path = validate_writable_path(path)

    # Verify file exists
    if not os.path.isfile(path):
        msg: str = f"File not found: '{path}'"
        log_error(msg, "validation")
        raise ValidationError(msg, field="file_path", value=path)

    # Verify file is readable
    if not os.access(path, os.R_OK):
        msg = f"File not readable: '{path}'"
        log_error(msg, "validation")
        raise ValidationError(msg, field="file_path", value=path)

    return path


# ==============================================================================
# VALIDATOR 7: validate_socat_opts
# Bash equivalent: lines 567-582
# ==============================================================================

def validate_socat_opts(opts: str) -> str:
    """Validate user-provided socat address options for safety.

    Allows only characters valid in socat address options:
    alphanumeric, equals, commas, dots, colons, hyphens, forward
    slashes, and underscores. Rejects all shell metacharacters.

    Empty string is valid (no extra options).

    Args:
        opts: Socat options string to validate.

    Returns:
        The validated options string (unchanged).

    Raises:
        ValidationError: If options contain forbidden characters.
    """
    opts = opts.strip()

    if not opts:
        return opts  # Empty is valid (no extra opts)

    # Whitelist validation
    if not _SOCAT_OPTS_PATTERN.match(opts):
        msg: str = (
            f"Forbidden characters in socat options '{opts}'. "
            "Allowed: alphanumeric, = , . : / _ -"
        )
        log_error(msg, "validation")
        raise ValidationError(msg, field="socat_opts", value=opts)

    return opts


# ==============================================================================
# VALIDATOR 8: validate_session_name
# Bash equivalent: lines 592-613
# ==============================================================================

def validate_session_name(name: str) -> str:
    """Validate a user-provided session name for safety.

    Allows only alphanumeric characters, hyphens, underscores, and dots.
    Maximum length 64 characters. Prevents injection into session files
    (SESSION_NAME=<value>) and log messages.

    Args:
        name: Session name string to validate.

    Returns:
        The validated session name (unchanged).

    Raises:
        ValidationError: If name is empty, too long, or contains
                        forbidden characters.
    """
    name = name.strip()

    if not name:
        msg: str = "Empty session name"
        log_error(msg, "validation")
        raise ValidationError(msg, field="session_name", value="")

    # Maximum length check
    if len(name) > SESSION_NAME_MAX_LENGTH:
        msg = (
            f"Session name too long ({len(name)} chars, "
            f"max {SESSION_NAME_MAX_LENGTH}): '{name}'"
        )
        log_error(msg, "validation")
        raise ValidationError(msg, field="session_name", value=name)

    # Whitelist: alphanumeric, hyphens, underscores, dots
    if not _SESSION_NAME_PATTERN.match(name):
        msg = (
            f"Invalid characters in session name '{name}'. "
            "Allowed: alphanumeric, . _ -"
        )
        log_error(msg, "validation")
        raise ValidationError(msg, field="session_name", value=name)

    return name


# ==============================================================================
# VALIDATOR 9: validate_session_id
# Bash equivalent: lines 621-636
# ==============================================================================

def validate_session_id(sid: str) -> str:
    """Validate a session ID is a valid 8-character lowercase hex string.

    Prevents injection via session ID parameters that flow into file
    paths (sessions/{sid}.session) and log messages.

    Args:
        sid: Session ID string to validate.

    Returns:
        The validated session ID (unchanged).

    Raises:
        ValidationError: If session ID is empty or not exactly 8
                        lowercase hex characters.
    """
    sid = sid.strip()

    if not sid:
        msg: str = "Empty session ID"
        log_error(msg, "validation")
        raise ValidationError(msg, field="session_id", value="")

    # Session IDs must be exactly 8 lowercase hex characters
    if not _SESSION_ID_PATTERN.match(sid):
        msg = f"Invalid session ID '{sid}': must be {SESSION_ID_LENGTH} hex characters"
        log_error(msg, "validation")
        raise ValidationError(msg, field="session_id", value=sid)

    return sid

# ==============================================================================
# MODULE      : socat_manager/logging_setup.py
# ==============================================================================
# Synopsis    : Structured logging configuration for socat-manager
# Description : Provides the logging infrastructure matching bash's dual-output
#               logging system (socat_manager.sh lines 188-340):
#
#               - Structured format: TIMESTAMP [LEVEL] [corr:ID] [component] msg
#               - Master log: per-execution log file in logs/
#               - Session logs: per-session audit trail
#               - Error logs: per-session stderr capture
#               - Terminal detection: color output only when stderr is a TTY
#               - Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
#
#               Uses Python's logging module with custom formatters.
#               Directory creation is handled once via _ensure_dirs().
#
# Notes       : - Color codes gated on sys.stderr.isatty()
#               - _ensure_dirs() is idempotent with guard flag
#               - Session-level logging writes directly to per-session files
#                 (not via the logging module) for isolation
#               - Capture logs are created by process.py, not here
#
# Version     : 1.0.2
# ==============================================================================

"""Structured logging configuration for socat-manager.

Provides dual-output logging (file + console) with structured formatting,
terminal-aware color codes, and per-session audit logging.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from socat_manager.config import (
    COLORS,
    CORRELATION_ID,
    EXEC_TIMESTAMP,
    SCRIPT_NAME,
    SYMBOLS,
    RuntimePaths,
    resolve_base_dir,
)

# ==============================================================================
# MODULE-LEVEL STATE
# ==============================================================================

# Guard: tracks whether directories have been initialized this execution.
# Prevents redundant mkdir/chmod syscalls on every log write.
_dirs_ensured: bool = False

# Terminal detection: disable color codes when stderr is not a terminal
# (e.g., when output is piped to a file or another command).
# Matches bash USE_COLOR logic (lines 199-202).
USE_COLOR: Final[bool] = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()

# Verbose mode flag — toggled by --verbose / -v flag at CLI parse time.
# Retained as a convenience predicate ("are we at DEBUG?"); the effective level
# is resolved from the full set of logging controls by resolve_log_level().
verbose_mode: bool = False

# Ordered, user-selectable console log levels. The file handler always captures
# from DEBUG; these govern what the console surfaces and are the accepted values
# of the --log-level option.
LOG_LEVEL_NAMES: Final[tuple[str, ...]] = (
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
)

# Cached paths instance
_paths: RuntimePaths | None = None


def get_paths() -> RuntimePaths:
    """Get or create the cached RuntimePaths instance.

    Returns:
        RuntimePaths resolved from the current base directory.
    """
    global _paths
    if _paths is None:
        _paths = RuntimePaths(base_dir=resolve_base_dir())
    return _paths


def set_base_dir(base_dir: Path) -> None:
    """Override the base directory (for testing or explicit configuration).

    Args:
        base_dir: New base directory path.
    """
    global _paths
    _paths = RuntimePaths(base_dir=base_dir)


# ==============================================================================
# DIRECTORY INITIALIZATION
# ==============================================================================

def _ensure_dirs() -> None:
    """Create required directory structure if missing.

    Sets restrictive permissions on session directory (0o700) to protect
    PID/session metadata from unauthorized access. Uses a guard variable
    to avoid redundant mkdir/chmod system calls on every log write.

    Matches bash _ensure_dirs() (lines 213-228).
    """
    global _dirs_ensured
    if _dirs_ensured:
        return

    paths = get_paths()

    # Create directories with appropriate permissions
    # conf_dir is the only non-sensitive directory (uses default umask)
    paths.conf_dir.mkdir(parents=True, exist_ok=True)

    # Security-sensitive directories get restrictive permissions (0o700):
    # - session_dir: contains PIDs, PGIDs, socat commands
    # - log_dir: contains captured traffic (potentially sensitive)
    # - cert_dir: contains TLS private keys
    for secure_dir in (paths.session_dir, paths.log_dir, paths.cert_dir):
        secure_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(secure_dir, 0o700)
        except OSError:
            pass  # Best-effort on permission setting

    _dirs_ensured = True


# ==============================================================================
# STRUCTURED LOG FORMATTER
# ==============================================================================

class StructuredFormatter(logging.Formatter):
    """Custom formatter producing structured log lines.

    Format: TIMESTAMP [LEVEL] [corr:CORRELATION_ID] [component] message

    Matches the bash _log_write() output format (lines 230-270).
    Terminal output includes ANSI color codes when USE_COLOR is True.
    """

    # Level → color mapping for terminal output
    LEVEL_COLORS: dict[int, str] = {
        logging.DEBUG: COLORS.dim,
        logging.INFO: COLORS.cyan,
        logging.WARNING: COLORS.yellow,
        logging.ERROR: COLORS.red,
        logging.CRITICAL: COLORS.red + COLORS.bold,
    }

    def __init__(self, *, use_color: bool = False) -> None:
        """Initialize the structured formatter.

        Args:
            use_color: Whether to include ANSI color escape sequences.
        """
        super().__init__()
        self._use_color: bool = use_color

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record into the structured format.

        Args:
            record: The log record to format.

        Returns:
            Formatted log string.
        """
        # Timestamp in ISO-like format matching bash date output
        timestamp: str = datetime.now(timezone.utc).astimezone().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # Component defaults to 'main' if not set via extra={'component': ...}
        component: str = getattr(record, "component", "main")

        # Level name padded to 8 chars for alignment
        level: str = record.levelname.ljust(8)

        # Core structured message (no color — for file output)
        base_msg: str = (
            f"{timestamp} [{level}] [corr:{CORRELATION_ID}] "
            f"[{component}] {record.getMessage()}"
        )

        if not self._use_color:
            return base_msg

        # Colorized version for terminal output
        color: str = self.LEVEL_COLORS.get(record.levelno, "")
        reset: str = COLORS.reset

        return (
            f"{COLORS.dim}{timestamp}{reset} "
            f"[{color}{level}{reset}] "
            f"[corr:{COLORS.dim}{CORRELATION_ID}{reset}] "
            f"[{COLORS.blue}{component}{reset}] "
            f"{record.getMessage()}"
        )


# ==============================================================================
# LOGGER SETUP
# ==============================================================================

def resolve_log_level(
    *,
    log_level: str | None = None,
    verbose: bool = False,
    quiet: bool = False,
) -> int:
    """Resolve the effective console log level from the CLI logging controls.

    Precedence, highest first:
        1. ``log_level`` — an explicit level name (authoritative).
        2. ``verbose`` — maps to DEBUG.
        3. ``quiet`` — maps to WARNING.
        4. default — INFO.

    ``verbose`` wins over ``quiet`` when both are supplied: surfacing more
    diagnostic detail is the safer default than silently suppressing it. An
    explicit ``log_level`` overrides both shortcuts so a precise level can
    always be selected regardless of the convenience flags.

    Args:
        log_level: Optional level name (case-insensitive) — one of
                   DEBUG, INFO, WARNING, ERROR, CRITICAL.
        verbose: True when --verbose / -v was supplied.
        quiet: True when --quiet / -q was supplied.

    Returns:
        The corresponding ``logging`` level integer.

    Raises:
        ValueError: If ``log_level`` is a non-empty string that does not name
                    a standard logging level.
    """
    if log_level:
        name: str = log_level.strip().upper()
        resolved = getattr(logging, name, None)
        if not isinstance(resolved, int) or name not in LOG_LEVEL_NAMES:
            raise ValueError(f"Unknown log level: {log_level!r}")
        return resolved

    if verbose:
        return logging.DEBUG
    if quiet:
        return logging.WARNING
    return logging.INFO


def setup_logging(*, log_level: int = logging.INFO) -> logging.Logger:
    """Configure and return the application logger with dual output.

    Creates:
        - File handler: writes to master log in logs/ directory
        - Console handler: writes to stderr with optional color

    The master log filename follows the bash convention:
        logs/{SCRIPT_NAME}-{EXEC_TIMESTAMP}.log

    Args:
        log_level: Minimum log level (default: INFO). Set to DEBUG
                   when verbose_mode is True.

    Returns:
        Configured logging.Logger instance.
    """
    _ensure_dirs()

    # Resolve effective log level
    effective_level: int = logging.DEBUG if verbose_mode else log_level

    # Get or create the named logger (not root, to avoid interference)
    logger: logging.Logger = logging.getLogger("socat_manager")

    # Prevent duplicate handler attachment on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(effective_level)
    logger.propagate = False

    # --- File handler: structured, no color ---
    paths = get_paths()
    master_log_path: Path = paths.log_dir / f"{SCRIPT_NAME}-{EXEC_TIMESTAMP}.log"
    try:
        file_handler = logging.FileHandler(str(master_log_path), mode="a")
        file_handler.setLevel(logging.DEBUG)  # File always captures everything
        file_handler.setFormatter(StructuredFormatter(use_color=False))
        logger.addHandler(file_handler)
    except OSError as exc:
        # If we can't write to the log file, warn on stderr and continue
        print(
            f"WARNING: Cannot create log file {master_log_path}: {exc}",
            file=sys.stderr,
        )

    # --- Console handler: structured, colorized if terminal ---
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(effective_level)
    console_handler.setFormatter(StructuredFormatter(use_color=USE_COLOR))
    logger.addHandler(console_handler)

    return logger


def get_logger() -> logging.Logger:
    """Get the application logger, initializing if needed.

    Returns:
        The socat_manager logger instance.
    """
    logger: logging.Logger = logging.getLogger("socat_manager")
    if not logger.handlers:
        return setup_logging()
    return logger


# ==============================================================================
# CONVENIENCE LOG FUNCTIONS
# Match bash log_debug(), log_info(), log_success(), etc. (lines 271-276)
# ==============================================================================

def log_debug(msg: str, component: str = "main") -> None:
    """Log a DEBUG message with component context.

    Args:
        msg: The message to log.
        component: Component/subsystem identifier.
    """
    get_logger().debug(msg, extra={"component": component})


def log_info(msg: str, component: str = "main") -> None:
    """Log an INFO message with component context.

    Args:
        msg: The message to log.
        component: Component/subsystem identifier.
    """
    get_logger().info(msg, extra={"component": component})


def log_warning(msg: str, component: str = "main") -> None:
    """Log a WARNING message with component context.

    Args:
        msg: The message to log.
        component: Component/subsystem identifier.
    """
    get_logger().warning(msg, extra={"component": component})


def log_error(msg: str, component: str = "main") -> None:
    """Log an ERROR message with component context.

    Args:
        msg: The message to log.
        component: Component/subsystem identifier.
    """
    get_logger().error(msg, extra={"component": component})


def log_critical(msg: str, component: str = "main") -> None:
    """Log a CRITICAL message with component context.

    Args:
        msg: The message to log.
        component: Component/subsystem identifier.
    """
    get_logger().critical(msg, extra={"component": component})


def log_success(msg: str, component: str = "main") -> None:
    """Log a success message with green checkmark on terminal.

    Matches bash log_success() (line 273): prints a styled terminal
    message AND writes an INFO-level log entry.

    Args:
        msg: The message to log.
        component: Component/subsystem identifier.
    """
    if USE_COLOR:
        print(
            f"  {COLORS.green}[{SYMBOLS.ok}]{COLORS.reset} {msg}",
            file=sys.stderr,
        )
    else:
        print(f"  [{SYMBOLS.ok}] {msg}", file=sys.stderr)

    # Also write to log file at INFO level
    get_logger().info(msg, extra={"component": component})


# ==============================================================================
# SESSION-LEVEL LOGGING
# Per-session audit trail — writes directly to session log files.
# Matches bash log_session() (lines 286-302).
# ==============================================================================

def log_session(session_id: str, level: str, msg: str) -> None:
    """Write a log entry to a per-session audit log file.

    Session logs are separate from the master log. Each session gets
    its own log file: logs/session-{session_id}.log

    This writes directly to the file (not via the logging module) to
    maintain isolation between session audit trails.

    Args:
        session_id: The 8-character hex session identifier.
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        msg: The message to log.
    """
    _ensure_dirs()

    paths = get_paths()
    session_log_path: Path = paths.log_dir / f"session-{session_id}.log"

    timestamp: str = datetime.now(timezone.utc).astimezone().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    line: str = (
        f"{timestamp} [{level.ljust(8)}] [corr:{CORRELATION_ID}] "
        f"[session:{session_id}] {msg}\n"
    )

    try:
        with open(session_log_path, "a") as fh:
            fh.write(line)
    except OSError:
        # Best-effort: if session log fails, don't crash the operation
        pass


# ==============================================================================
# DISPLAY HELPERS
# Terminal-formatted output for banners, sections, and key-value pairs.
# Matches bash print_banner(), print_section(), print_kv() (lines 304-340).
# ==============================================================================

def print_banner(subtitle: str = "") -> None:
    """Print a styled section banner to stderr.

    Args:
        subtitle: Optional subtitle text (e.g., "Listener", "Forwarder").
    """
    if USE_COLOR:
        header: str = f"{COLORS.bold}{COLORS.cyan}{'=' * 60}{COLORS.reset}"
        title: str = f"{COLORS.bold}  SOCAT Manager{COLORS.reset}"
        if subtitle:
            title += f" {COLORS.dim}— {subtitle}{COLORS.reset}"
    else:
        header = "=" * 60
        title = "  SOCAT Manager"
        if subtitle:
            title += f" — {subtitle}"

    print(header, file=sys.stderr)
    print(title, file=sys.stderr)
    print(header, file=sys.stderr)


def print_section(title: str) -> None:
    """Print a section header to stderr.

    Args:
        title: Section title text.
    """
    if USE_COLOR:
        print(
            f"\n{COLORS.bold}{COLORS.blue}  [{SYMBOLS.arrow}] {title}{COLORS.reset}",
            file=sys.stderr,
        )
    else:
        print(f"\n  [{SYMBOLS.arrow}] {title}", file=sys.stderr)


def print_kv(key: str, value: object) -> None:
    """Print a key-value pair to stderr.

    Args:
        key: The label/key text.
        value: The value to display.
    """
    if USE_COLOR:
        print(
            f"    {COLORS.dim}{key}:{COLORS.reset} {value}",
            file=sys.stderr,
        )
    else:
        print(f"    {key}: {value}", file=sys.stderr)

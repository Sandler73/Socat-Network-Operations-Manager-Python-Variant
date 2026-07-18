# ==============================================================================
# MODULE      : socat_manager/session.py
# ==============================================================================
# Synopsis    : Session management for socat-manager
# Description : Implements all session lifecycle operations with exact parity
#               to the bash version (socat_manager.sh lines 653-1140):
#
#               - Session ID generation (8-char hex, collision-checked)
#               - Session registration (key=value file, 0o600 permissions)
#               - Session field reading (exact key match via split, not regex)
#               - Session lookup (by name, port, PID)
#               - Session alive check (PID + PGID verification)
#               - Session cleanup (remove files for dead processes)
#               - Advisory file locking (fcntl.flock)
#               - Session listing and detail display
#
# Notes       : - Session files use KEY=VALUE format interoperable with bash
#               - Field reading uses str.split('=', 1) for exact key match
#                 (not regex, not 'in' substring -- SEC-01 / CWE-20)
#               - Advisory locking is cooperative (other processes must also
#                 use flock for protection to be effective)
#               - Session directory permissions: 0o700
#               - Session file permissions: 0o600
#               - Values containing '=' are handled correctly (split on first)
#
# Version     : 1.0.2
# ==============================================================================

"""Session management: registration, lookup, cleanup, and locking.

Session files use KEY=VALUE text format interoperable with the bash variant.
All file I/O uses exact key matching and restrictive permissions.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from socat_manager.config import (
    COLORS,
    CORRELATION_ID,
    SCRIPT_PID,
    SESSION_FIELDS,
    SESSION_FILE_VERSION,
    SESSION_ID_LENGTH,
    SYMBOLS,
    RuntimePaths,
    protocol_family,
    protocol_transport,
    socket_scope_flags,
)
from socat_manager.logging_setup import (
    USE_COLOR,
    _ensure_dirs,
    get_paths,
    log_debug,
    log_error,
    log_info,
    log_session,
    log_success,
    log_warning,
    print_kv,
    print_section,
)

# ==============================================================================
# SESSION ID GENERATION
# Bash equivalent: lines 653-728
# ==============================================================================

def generate_session_id() -> str:
    """Generate a unique 8-character hex session ID.

    Uses uuid4 as primary entropy source. Checks for collisions against
    existing session files (extremely unlikely but handled).

    Returns:
        8-character lowercase hex string guaranteed unique among
        current session files.

    Raises:
        RuntimeError: If unable to generate a unique ID after 100 attempts.
    """
    paths: RuntimePaths = get_paths()

    for _ in range(100):
        sid: str = uuid.uuid4().hex[:SESSION_ID_LENGTH]

        # Collision check against existing session files
        session_file: Path = paths.session_dir / f"{sid}.session"
        if not session_file.exists():
            return sid

    raise RuntimeError("Failed to generate unique session ID after 100 attempts")


# ==============================================================================
# ADVISORY FILE LOCKING
# Bash equivalent: lines 730-742
# ==============================================================================

@contextlib.contextmanager
def session_lock() -> Generator[None, None, None]:
    """Acquire an advisory file lock on the session directory.

    Uses fcntl.flock for cooperative locking. This protects against
    race conditions when multiple socat-manager instances modify
    session files concurrently.

    The lock is automatically released when the context manager exits.

    Yields:
        None -- the lock is held for the duration of the with block.

    Raises:
        OSError: If the lock file cannot be opened or locked.
    """
    _ensure_dirs()
    paths: RuntimePaths = get_paths()
    lock_path: Path = paths.session_lock_file

    fd: int = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except BlockingIOError:
        log_debug("Session directory locked by another process", "session")
        # Still yield -- advisory lock is best-effort, not blocking
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass  # the lock is already released or the fd is no longer valid; the fd is closed next regardless
        os.close(fd)


# ==============================================================================
# SESSION REGISTRATION
# Bash equivalent: lines 761-799
# ==============================================================================

def session_register(
    sid: str,
    name: str,
    pid: int,
    pgid: int,
    mode: str,
    proto: str = "tcp4",
    lport: int = 0,
    socat_cmd: str = "",
    rhost: str = "",
    rport: str = "",
) -> None:
    """Register a new socat session by writing a session file.

    Creates a KEY=VALUE text file in the session directory with
    full metadata. File permissions are set to 0o600 to
    protect command strings and PID information.

    The file format is interoperable with the bash version -- a user
    can manage sessions created by either variant interchangeably.

    Args:
        sid: Unique 8-character hex session ID.
        name: Human-readable session name.
        pid: PID of the socat process.
        pgid: Process group ID (PGID) for tree kill.
        mode: Operational mode (listen, forward, tunnel, redirect, etc.).
        proto: Protocol (tcp4, udp4, etc.).
        lport: Local port number.
        socat_cmd: Full socat command string (for restart/audit).
        rhost: Optional remote host.
        rport: Optional remote port.
    """
    _ensure_dirs()
    paths: RuntimePaths = get_paths()
    session_file: Path = paths.session_dir / f"{sid}.session"

    # Defense-in-depth: strip newlines from all string values to prevent
    # KEY=VALUE injection via crafted inputs. All callers already validate
    # inputs, but the register function is the last line of defense.
    sid = sid.replace("\n", "").replace("\r", "")
    name = name.replace("\n", "").replace("\r", "")
    mode = mode.replace("\n", "").replace("\r", "")
    proto = proto.replace("\n", "").replace("\r", "")
    socat_cmd = socat_cmd.replace("\n", "").replace("\r", "")
    rhost = rhost.replace("\n", "").replace("\r", "")
    rport = rport.replace("\n", "").replace("\r", "")

    # Timestamp for session creation
    now: str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    started: str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S")

    # Build session file content (matches bash heredoc format exactly)
    content: str = (
        f"# socat_manager session file {SESSION_FILE_VERSION}\n"
        f"# Generated: {now}\n"
        f"{SESSION_FIELDS.session_id}={sid}\n"
        f"{SESSION_FIELDS.session_name}={name}\n"
        f"{SESSION_FIELDS.pid}={pid}\n"
        f"{SESSION_FIELDS.pgid}={pgid}\n"
        f"{SESSION_FIELDS.mode}={mode}\n"
        f"{SESSION_FIELDS.protocol}={proto}\n"
        f"{SESSION_FIELDS.local_port}={lport}\n"
        f"{SESSION_FIELDS.remote_host}={rhost}\n"
        f"{SESSION_FIELDS.remote_port}={rport}\n"
        f"{SESSION_FIELDS.socat_cmd}={socat_cmd}\n"
        f"{SESSION_FIELDS.started}={started}\n"
        f"{SESSION_FIELDS.correlation}={CORRELATION_ID}\n"
        f"{SESSION_FIELDS.launcher_pid}={SCRIPT_PID}\n"
    )

    # Write with restrictive permissions using os.open + os.fdopen
    # to avoid race condition between open() and chmod()
    fd: int = os.open(
        str(session_file),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
    except Exception:
        # fd is consumed by fdopen even on error, but guard anyway
        try:
            os.close(fd)
        except OSError:
            pass  # fdopen already consumed the descriptor, so there is nothing left to close
        raise

    log_debug(
        f"Session registered: {sid} ({name}, PID {pid}, PGID {pgid})",
        "session",
    )
    log_session(
        sid, "INFO",
        f"Session registered: name={name} pid={pid} pgid={pgid} "
        f"mode={mode} proto={proto} port={lport}",
    )


# ==============================================================================
# SESSION PROCESS UPDATE
# Rewrites the process identity of an existing session in place.
# ==============================================================================

def session_update_process(sid: str, pid: int, pgid: int) -> bool:
    """Update the tracked process identity of an existing session.

    Rewrites the PID and PGID fields of a session file while preserving every
    other field (name, mode, protocol, ports, socat command, correlation ID,
    launcher PID, and the STARTED creation timestamp) and the file header.

    This is the durable record of which process a session currently owns.
    Any component that replaces the process behind a session -- such as the
    watchdog after an unexpected exit -- must call this so that liveness
    checks and the stop sequence act on the process that is actually
    running rather than a terminated predecessor.

    STARTED records when the session was created and is deliberately left
    unchanged: a restart changes which process the session owns, not when the
    session began. Restart events are recorded in the session log.

    The rewrite is performed under the advisory session lock and written
    through a temporary file with 0o600 permissions, then atomically
    renamed over the original. A concurrent reader therefore observes
    either the complete previous record or the complete new one, never a
    partially written file.

    Args:
        sid: Session ID whose process identity is being updated.
        pid: PID of the process the session now owns.
        pgid: Process group ID of the process the session now owns.

    Returns:
        True if the session file was updated, False if it does not exist
        or could not be rewritten.
    """
    paths: RuntimePaths = get_paths()
    session_file: Path = paths.session_dir / f"{sid}.session"

    with session_lock():
        if not session_file.is_file():
            log_warning(
                f"Cannot update process identity -- session file missing: {sid}",
                "session",
            )
            return False

        try:
            with open(session_file, "r") as fh:
                lines: list[str] = fh.read().splitlines()
        except OSError as exc:
            log_error(f"Cannot read session file for update: {sid} ({exc})", "session")
            return False

        # Only the process identity changes. STARTED is preserved so the
        # recorded creation time is not lost across a restart.
        replacements: dict[str, str] = {
            SESSION_FIELDS.pid: str(pid),
            SESSION_FIELDS.pgid: str(pgid),
        }

        updated_lines: list[str] = []
        seen: set[str] = set()

        for line in lines:
            if line.startswith("#") or "=" not in line:
                updated_lines.append(line)
                continue

            key, _, _value = line.partition("=")

            # Only the first occurrence of a key is authoritative, matching
            # the exact-match read behavior of session_read_field().
            if key in replacements and key not in seen:
                updated_lines.append(f"{key}={replacements[key]}")
                seen.add(key)
            else:
                updated_lines.append(line)

        # Append any field that was absent from the original file so the
        # record is complete after the update.
        for key, value in replacements.items():
            if key not in seen:
                updated_lines.append(f"{key}={value}")

        content: str = "\n".join(updated_lines) + "\n"

        # Write through a temporary file in the same directory, then rename.
        # Rename within a directory is atomic, so readers never observe a
        # truncated session record.
        tmp_file: Path = paths.session_dir / f"{sid}.session.tmp"
        try:
            fd: int = os.open(
                str(tmp_file),
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            with os.fdopen(fd, "w") as fh:
                fh.write(content)
            os.replace(str(tmp_file), str(session_file))
        except OSError as exc:
            log_error(f"Cannot write session file for update: {sid} ({exc})", "session")
            try:
                tmp_file.unlink(missing_ok=True)
            except OSError:
                pass  # the temporary file is already gone; the write failure itself is reported above
            return False

    log_debug(f"Session process identity updated: {sid} (PID {pid}, PGID {pgid})", "session")
    log_session(sid, "INFO", f"Session process updated: pid={pid} pgid={pgid}")

    return True


# ==============================================================================
# SESSION UNREGISTRATION
# Bash equivalent: lines 807-814
# ==============================================================================

def session_unregister(sid: str) -> None:
    """Remove a session file and all associated signal files.

    Called after confirmed process termination. Removes:
        - {sid}.session  -- session metadata
        - {sid}.stop     -- stop signal file
        - {sid}.launching -- PID staging file

    Args:
        sid: Session ID to unregister.
    """
    paths: RuntimePaths = get_paths()

    for suffix in (".session", ".stop", ".launching"):
        target: Path = paths.session_dir / f"{sid}{suffix}"
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass  # the artifact is already removed or not writable; unregistering is best-effort

    log_debug(f"Session unregistered: {sid}", "session")
    log_session(sid, "INFO", "Session unregistered")


# ==============================================================================
# SESSION FIELD READING
# Bash equivalent: lines 824-837
# CRITICAL: Uses exact key match (str.split, not regex, not 'in' substring)
# ==============================================================================

def session_read_field(session_file: Path, field: str) -> str:
    """Read a specific field from a session file using exact key match.

    Parses KEY=VALUE lines. Uses split('=', 1) to handle values
    containing '=' characters (e.g., socat command strings with
    cert=path options).

    SECURITY: Uses exact string comparison on the key portion,
    NOT regex matching or substring search. This prevents partial
    key matches (e.g., searching for 'PID' matching 'LAUNCHER_PID').
    Matches bash awk: $1 == key {print substr($0, length(key)+2); exit}

    Args:
        session_file: Path to the session file.
        field: Exact field name to look up (e.g., "PID", "PROTOCOL").

    Returns:
        Field value as string, or empty string if not found.
    """
    if not session_file.is_file():
        return ""

    try:
        with open(session_file, "r") as fh:
            for line in fh:
                line = line.rstrip("\n")

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Split on first '=' only -- key is everything before,
                # value is everything after (may contain '=' characters)
                if "=" not in line:
                    continue

                key, value = line.split("=", 1)

                # EXACT key match -- not startswith, not 'in', not regex
                if key == field:
                    return value

    except OSError:
        pass  # the session file is unreadable or was removed concurrently; treat the field as absent

    return ""


# ==============================================================================
# SESSION LOOKUP FUNCTIONS
# Bash equivalents: lines 845-889
# ==============================================================================

def _sid_from_file(session_file: Path) -> str:
    """Derive a session ID from a session file's name.

    Session files are named ``{sid}.session``, so the session ID is the file
    stem. Deriving it from the name avoids a second read of the file just to
    recover the SESSION_ID field, whose value is identical to the stem by
    construction.

    The stem is checked for the characters that would make it unsafe to use
    in a constructed path (path separators, parent references, or a null
    byte). A file whose name contains any of those is skipped. This mirrors
    the defensive check applied by the stop path before a SID is turned into
    a file path.

    Args:
        session_file: Path to a ``.session`` file.

    Returns:
        The session ID, or an empty string if the file name is empty or
        contains characters that are unsafe in a path.
    """
    sid: str = session_file.stem
    if not sid or "/" in sid or "\\" in sid or ".." in sid or "\0" in sid:
        return ""
    return sid


def session_find_by_name(target_name: str) -> list[str]:
    """Find session IDs matching an exact session name.

    Args:
        target_name: Session name to search for (exact match).

    Returns:
        List of matching session IDs (may be empty).
    """
    paths: RuntimePaths = get_paths()
    results: list[str] = []

    for sf in paths.session_dir.glob("*.session"):
        name: str = session_read_field(sf, SESSION_FIELDS.session_name)
        if name == target_name:
            sid: str = _sid_from_file(sf)
            if sid:
                results.append(sid)

    return results


def session_find_by_port(target_port: int | str) -> list[str]:
    """Find session IDs matching a local port.

    Args:
        target_port: Port number to search for.

    Returns:
        List of matching session IDs (may be empty).
    """
    paths: RuntimePaths = get_paths()
    target_str: str = str(target_port)
    results: list[str] = []

    for sf in paths.session_dir.glob("*.session"):
        port: str = session_read_field(sf, SESSION_FIELDS.local_port)
        if port == target_str:
            sid: str = _sid_from_file(sf)
            if sid:
                results.append(sid)

    return results


def session_find_by_pid(target_pid: int | str) -> list[str]:
    """Find session IDs matching a PID.

    Args:
        target_pid: Process ID to search for.

    Returns:
        List of matching session IDs (may be empty).
    """
    paths: RuntimePaths = get_paths()
    target_str: str = str(target_pid)
    results: list[str] = []

    for sf in paths.session_dir.glob("*.session"):
        pid: str = session_read_field(sf, SESSION_FIELDS.pid)
        if pid == target_str:
            sid: str = _sid_from_file(sf)
            if sid:
                results.append(sid)

    return results


# ==============================================================================
# SESSION ALIVE CHECK
# Bash equivalent: lines 897-922
# ==============================================================================

def process_alive(pid_str: str, pgid_str: str) -> bool:
    """Check whether a recorded process identity is still running.

    Checks the primary PID first, then falls back to the process group; the
    session is alive if either responds. The group fallback covers the case
    where the primary process has been replaced but the group still holds live
    members.

    The primary check routes through process.process_is_running(), so a socat
    process launched by this framework that has exited but not yet been
    collected is correctly reported as dead rather than as a live zombie.

    This operates entirely on values the caller has already read, so a caller
    that has loaded a session's fields does not have to re-open the file to
    determine liveness.

    Args:
        pid_str: Recorded PID as a string (empty if absent).
        pgid_str: Recorded PGID as a string (empty if absent).

    Returns:
        True if the recorded process or its group is alive, False otherwise.
    """
    # Check primary PID first
    if pid_str:
        # process.py imports session.py at module load, so the reverse import
        # is performed lazily here to avoid a circular import. process_is_running
        # is authoritative for children of this process and treats an exited but
        # uncollected socat child as dead rather than as a live zombie.
        from socat_manager.process import process_is_running

        try:
            if process_is_running(int(pid_str)):
                return True
        except ValueError:
            pass  # the PID field is not an integer; fall through to the process-group check below

    # Fallback: check if any process in the group is alive
    if pgid_str and pgid_str != "0":
        try:
            os.killpg(int(pgid_str), 0)
            return True
        except (OSError, ValueError):
            pass  # the PGID is missing, invalid, or its group is gone; the session is not alive

    return False


def session_is_alive(sid: str) -> bool:
    """Check if a registered session's process is still running.

    Reads the session's recorded process identity in a single pass and
    evaluates it via process_alive(). Callers that have already loaded a
    session's fields should call process_alive() directly rather than paying
    for another read.

    Args:
        sid: Session ID to check.

    Returns:
        True if the session's process is alive, False otherwise.
    """
    paths: RuntimePaths = get_paths()
    session_file: Path = paths.session_dir / f"{sid}.session"

    if not session_file.is_file():
        return False

    fields: dict[str, str] = session_read_all_fields(session_file)

    return process_alive(
        fields.get(SESSION_FIELDS.pid, ""),
        fields.get(SESSION_FIELDS.pgid, ""),
    )


# ==============================================================================
# SESSION ENUMERATION
# Bash equivalent: lines 924-932
# ==============================================================================

def session_get_all_ids() -> list[str]:
    """List all registered session IDs.

    Returns:
        List of session ID strings (may be empty).
    """
    paths: RuntimePaths = get_paths()
    results: list[str] = []

    for sf in paths.session_dir.glob("*.session"):
        sid: str = _sid_from_file(sf)
        if sid:
            results.append(sid)

    return results


# ==============================================================================
# SESSION COUNT
# ==============================================================================

def session_count() -> int:
    """Count the number of active session files.

    Returns:
        Number of .session files in the session directory.
    """
    paths: RuntimePaths = get_paths()
    return len(list(paths.session_dir.glob("*.session")))


# ==============================================================================
# SESSION LISTING
# Bash equivalent: lines 939-1013
# ==============================================================================

def session_list() -> bool:
    """List all registered sessions with their status.

    Displays a formatted table of sessions including session ID, name,
    PID, PGID, mode, protocol, port, remote target, and alive/dead status.

    Returns:
        True if any sessions were found, False if none.
    """
    paths: RuntimePaths = get_paths()
    has_sessions: bool = False

    for sf in sorted(paths.session_dir.glob("*.session")):
        has_sessions = True

        # Single-pass bulk read (eliminates N+1 I/O -- was 9 reads per session)
        fields: dict[str, str] = session_read_all_fields(sf)

        sid: str = fields.get(SESSION_FIELDS.session_id, "")
        name: str = fields.get(SESSION_FIELDS.session_name, "")
        pid: str = fields.get(SESSION_FIELDS.pid, "")
        pgid: str = fields.get(SESSION_FIELDS.pgid, "")
        mode: str = fields.get(SESSION_FIELDS.mode, "")
        proto: str = fields.get(SESSION_FIELDS.protocol, "")
        lport: str = fields.get(SESSION_FIELDS.local_port, "")
        rhost: str = fields.get(SESSION_FIELDS.remote_host, "")
        rport: str = fields.get(SESSION_FIELDS.remote_port, "")

        alive: bool = process_alive(pid, pgid)

        # Format remote target
        remote: str = ""
        if rhost:
            remote = f"{rhost}:{rport}" if rport else rhost

        # Status indicator
        if USE_COLOR:
            if alive:
                status: str = f"{COLORS.green}{SYMBOLS.ok} ALIVE{COLORS.reset}"
            else:
                status = f"{COLORS.red}{SYMBOLS.fail} DEAD{COLORS.reset}"
        else:
            status = f"{SYMBOLS.ok} ALIVE" if alive else f"{SYMBOLS.fail} DEAD"

        # Mode symbol
        mode_sym: str = {
            "listen": SYMBOLS.listen,
            "batch-listen": SYMBOLS.listen,
            "forward": SYMBOLS.forward,
            "tunnel": SYMBOLS.tunnel,
            "redirect": SYMBOLS.forward,
        }.get(mode, SYMBOLS.session)

        # Print session line
        line: str = (
            f"  {mode_sym} {sid}  {name:<30s}  "
            f"PID:{pid:<8s} PGID:{pgid:<8s} {proto:<5s} :{lport:<6s}"
        )
        if remote:
            line += f" → {remote}"
        line += f"  [{status}]"

        print(line, file=sys.stderr)

    if not has_sessions:
        log_info("No active sessions found", "status")

    return has_sessions


# ==============================================================================
# SESSION DETAIL
# Bash equivalent: lines 1014-1135
# ==============================================================================

def session_read_all_fields(session_file: Path) -> dict[str, str]:
    """Read all fields from a session file in a single pass.

    Returns a dict of KEY→VALUE pairs. Skips comments and empty lines.
    Uses exact key match via split('=', 1). This avoids the N+1 problem
    of calling session_read_field() once per field.

    Args:
        session_file: Path to the session file.

    Returns:
        Dict of field name → value. Empty dict if file not found.
    """
    fields: dict[str, str] = {}

    if not session_file.is_file():
        return fields

    try:
        with open(session_file, "r") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                # First occurrence wins (matches session_read_field behavior)
                if key not in fields:
                    fields[key] = value
    except OSError:
        pass  # the session file is unreadable or was removed concurrently; return what parsed so far

    return fields


# ==============================================================================
# SESSION DETAIL
# Bash equivalent: lines 1014-1129
# Displays 5 sections: metadata, process status + tree, port status,
# socat command, and associated log files.
# ==============================================================================

def session_detail(sid: str) -> bool:
    """Display detailed information for a specific session.

    Shows all session metadata fields, process status with process tree,
    port binding status via ss, socat command, and associated log files.
    Matches bash session_detail() output (lines 1014-1129).

    Args:
        sid: Session ID to display details for.

    Returns:
        True if session was found, False otherwise.
    """
    import subprocess as _sp

    paths: RuntimePaths = get_paths()
    session_file: Path = paths.session_dir / f"{sid}.session"

    if not session_file.is_file():
        log_error(f"Session not found: {sid}", "status")
        return False

    # Read all fields in a single pass (PERF-01 fix)
    fields: dict[str, str] = session_read_all_fields(session_file)

    name: str = fields.get(SESSION_FIELDS.session_name, "")
    pid: str = fields.get(SESSION_FIELDS.pid, "")
    pgid: str = fields.get(SESSION_FIELDS.pgid, "")
    mode: str = fields.get(SESSION_FIELDS.mode, "")
    proto: str = fields.get(SESSION_FIELDS.protocol, "")
    lport: str = fields.get(SESSION_FIELDS.local_port, "")
    rhost: str = fields.get(SESSION_FIELDS.remote_host, "")
    rport: str = fields.get(SESSION_FIELDS.remote_port, "")
    socat_cmd: str = fields.get(SESSION_FIELDS.socat_cmd, "")
    started: str = fields.get(SESSION_FIELDS.started, "")
    corr: str = fields.get(SESSION_FIELDS.correlation, "")
    launcher: str = fields.get(SESSION_FIELDS.launcher_pid, "")

    # Liveness from the fields already read above -- no second file read.
    alive: bool = process_alive(pid, pgid)

    # --- Section 1: Session Metadata ---
    print_section(f"Session Detail: {sid}")
    print_kv("Session ID", sid)
    print_kv("Session Name", name)
    print_kv("Mode", mode)
    print_kv("Protocol", proto)
    print_kv("Local Port", lport)
    if rhost:
        print_kv("Remote Host", rhost)
    if rport:
        print_kv("Remote Port", rport)
    print_kv("PID", pid)
    print_kv("PGID", pgid)
    print_kv("Started", started)
    print_kv("Correlation ID", corr)
    print_kv("Launcher PID", launcher)

    # --- Section 2: Process Status + Tree ---
    print("", file=sys.stderr)
    print_section("Process Status")

    if alive:
        if USE_COLOR:
            print(f"  {COLORS.green}[{SYMBOLS.ok}] Process is ALIVE{COLORS.reset}", file=sys.stderr)
        else:
            print(f"  [{SYMBOLS.ok}] Process is ALIVE", file=sys.stderr)

        # Show process tree if alive
        if pid:
            print("", file=sys.stderr)
            if USE_COLOR:
                print(f"  {COLORS.dim}Process tree:{COLORS.reset}", file=sys.stderr)
            else:
                print("  Process tree:", file=sys.stderr)

            try:
                result = _sp.run(
                    ["pstree", "-p", pid],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    for line in result.stdout.strip().splitlines():
                        print(f"    {line}", file=sys.stderr)
            except (FileNotFoundError, _sp.TimeoutExpired):
                # Fallback: ps --forest
                try:
                    result = _sp.run(
                        ["ps", "--forest", "-o", "pid,ppid,comm,args", "-g", pgid],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        for line in result.stdout.strip().splitlines():
                            print(f"    {line}", file=sys.stderr)
                except (FileNotFoundError, _sp.TimeoutExpired, OSError):
                    try:
                        result = _sp.run(
                            ["ps", "-o", "pid,ppid,comm", "-p", pid],
                            capture_output=True, text=True, timeout=5,
                        )
                        if result.returncode == 0 and result.stdout.strip():
                            for line in result.stdout.strip().splitlines():
                                print(f"    {line}", file=sys.stderr)
                    except (FileNotFoundError, _sp.TimeoutExpired, OSError):
                        pass  # ps is absent or timed out; the extra diagnostic detail is simply omitted
    else:
        if USE_COLOR:
            print(f"  {COLORS.red}[{SYMBOLS.fail}] Process is DEAD{COLORS.reset}", file=sys.stderr)
        else:
            print(f"  [{SYMBOLS.fail}] Process is DEAD", file=sys.stderr)

    # --- Section 3: Port Status ---
    print("", file=sys.stderr)
    print_section("Port Status")

    if lport and lport != "0":
        # The listing is scoped to the session's own protocol -- its transport
        # and its address family. A tcp4 session is reported against the tcp4
        # socket only, so a listener of another protocol on the same port
        # number is never mistaken for this session's listener.
        scope_proto: str = "tcp4" if proto == "tls" else proto
        scope_label: str = (
            f"{protocol_transport(scope_proto).upper()}"
            f"/IPv{protocol_family(scope_proto)}"
        )

        try:
            result = _sp.run(
                ["ss", *socket_scope_flags(scope_proto), "-p"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                port_info: list[str] = [
                    ln for ln in result.stdout.splitlines()
                    if f":{lport} " in ln or f":{lport}\t" in ln
                    or ln.rstrip().endswith(f":{lport}")
                ]
                if port_info:
                    if USE_COLOR:
                        print(f"  {COLORS.green}[{SYMBOLS.ok}] Port {lport} is LISTENING ({scope_label}){COLORS.reset}", file=sys.stderr)
                    else:
                        print(f"  [{SYMBOLS.ok}] Port {lport} is LISTENING ({scope_label})", file=sys.stderr)
                    for ln in port_info:
                        print(f"    {ln.strip()}", file=sys.stderr)
                else:
                    if USE_COLOR:
                        print(f"  {COLORS.red}[{SYMBOLS.fail}] Port {lport} is NOT listening ({scope_label}){COLORS.reset}", file=sys.stderr)
                    else:
                        print(f"  [{SYMBOLS.fail}] Port {lport} is NOT listening ({scope_label})", file=sys.stderr)

        except (FileNotFoundError, _sp.TimeoutExpired):
            print("  (ss not available for port status check)", file=sys.stderr)

    # --- Section 4: Socat Command ---
    if socat_cmd:
        print("", file=sys.stderr)
        print_section("Socat Command")
        print(f"    {socat_cmd}", file=sys.stderr)

    # --- Section 5: Associated Logs ---
    print("", file=sys.stderr)
    print_section("Associated Logs")

    log_count: int = 0
    for pattern in (
        f"session-{sid}*.log",
        f"session-{sid}-error.log",
        f"capture-*{lport}*.log",
    ):
        for lf in sorted(paths.log_dir.glob(pattern)):
            print(f"    {lf}", file=sys.stderr)
            log_count += 1

    if log_count == 0:
        print("    (no session-specific logs found)", file=sys.stderr)

    return True


# ==============================================================================
# LEGACY SESSION MIGRATION
# Bash equivalent: lines 3499-3543
# ==============================================================================

def migrate_legacy_sessions() -> int:
    """Migrate v1 legacy .pid session files to v2.2+ .session format.

    Scans the session directory for .pid files (pre-v2.2 format), checks
    if the tracked process is alive, and if so creates a new v2.3 .session
    file. Dead legacy sessions are simply removed.

    Returns:
        Number of sessions migrated.
    """
    import subprocess as _sp

    paths: RuntimePaths = get_paths()
    migrated: int = 0

    for old_file in paths.session_dir.glob("*.pid"):
        old_name: str = old_file.stem  # filename without .pid

        # Read fields from legacy format (same KEY=VALUE but .pid extension)
        pid_str: str = ""
        mode_str: str = "unknown"
        proto_str: str = "tcp4"
        lport_str: str = "0"
        rhost_str: str = ""
        rport_str: str = ""

        try:
            with open(old_file, "r") as fh:
                for line in fh:
                    line = line.rstrip("\n")
                    if "=" not in line or line.startswith("#"):
                        continue
                    key, value = line.split("=", 1)
                    match key:
                        case "PID":
                            pid_str = value
                        case "MODE":
                            mode_str = value
                        case "PROTOCOL":
                            proto_str = value
                        case "LOCAL_PORT":
                            lport_str = value
                        case "REMOTE_HOST":
                            rhost_str = value
                        case "REMOTE_PORT":
                            rport_str = value
        except OSError:
            continue

        # Skip if PID is not valid or process is dead
        if not pid_str or not pid_str.isdigit():
            try:
                old_file.unlink(missing_ok=True)
            except OSError:
                pass  # the legacy session file is already gone
            log_debug(f"Removed invalid legacy session: {old_name}", "migrate")
            continue

        pid_int: int = int(pid_str)
        try:
            os.kill(pid_int, 0)
        except OSError:
            # Process is dead -- remove legacy file
            try:
                old_file.unlink(missing_ok=True)
            except OSError:
                pass  # the legacy session file is already gone
            log_debug(f"Removed dead legacy session: {old_name}", "migrate")
            continue

        # Generate session ID for this legacy session
        sid: str = generate_session_id()

        # Derive PGID from the running process
        pgid_int: int = pid_int
        try:
            result = _sp.run(
                ["ps", "-o", "pgid=", "-p", str(pid_int)],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip().isdigit():
                pgid_int = int(result.stdout.strip())
        except (FileNotFoundError, _sp.TimeoutExpired, ValueError):
            pass  # ps is absent, timed out, or returned non-numeric output; the PGID stays unset

        # Create v2.3 session file
        session_register(
            sid=sid,
            name=old_name,
            pid=pid_int,
            pgid=pgid_int,
            mode=mode_str,
            proto=proto_str,
            lport=int(lport_str) if lport_str.isdigit() else 0,
            rhost=rhost_str,
            rport=rport_str,
        )

        # Remove old v1 file
        try:
            old_file.unlink(missing_ok=True)
        except OSError:
            pass  # the legacy session file is already gone after migration

        migrated += 1
        log_info(f"Migrated legacy session '{old_name}' -> SID {sid}", "migrate")

    if migrated > 0:
        log_info(f"Migrated {migrated} legacy session(s) to v2.3 format")

    return migrated


# ==============================================================================
# SESSION CLEANUP (DEAD SESSIONS)
# Bash equivalent: lines 1136-1219
# ==============================================================================

def session_cleanup_dead() -> int:
    """Remove session files for dead processes.

    Acquires advisory lock before iterating to prevent TOCTOU race
    conditions with concurrent stop/launch operations. Both the PID
    and PGID must be confirmed dead before removal. This prevents
    premature cleanup of sessions where the primary PID has been
    replaced but the process group is still alive.

    Returns:
        Number of dead sessions cleaned up.
    """
    paths: RuntimePaths = get_paths()
    cleaned: int = 0

    with session_lock():
        for sf in list(paths.session_dir.glob("*.session")):
            sid: str = session_read_field(sf, SESSION_FIELDS.session_id)
            if not sid:
                continue

            if not session_is_alive(sid):
                name: str = session_read_field(sf, SESSION_FIELDS.session_name)
                log_info(f"Cleaning up dead session: {sid} ({name})", "cleanup")
                session_unregister(sid)
                cleaned += 1

    if cleaned > 0:
        log_success(f"Cleaned up {cleaned} dead session(s)", "cleanup")
    else:
        log_info("No dead sessions found", "cleanup")

    return cleaned

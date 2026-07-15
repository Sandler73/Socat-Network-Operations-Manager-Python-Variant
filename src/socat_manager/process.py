# ==============================================================================
# MODULE      : socat_manager/process.py
# ==============================================================================
# Synopsis    : Process launch, stop, and port management for socat-manager
# Description : Implements the core process lifecycle operations with exact
#               parity to the bash version:
#
#               - launch_socat_session()  — setsid + Popen, PID tracking,
#                                           stability check, session registration
#               - stop_session()          — 9-step stop sequence (SIGTERM →
#                                           wait → SIGKILL → port cleanup)
#               - check_port_available()  — protocol-scoped port availability
#               - check_port_freed()      — retry-based port release verification
#               - kill_by_port()          — last-resort socat-only port kill
#
#               Bash equivalents:
#                 launch_socat_session()  — lines 1221-1329
#                 _stop_session()         — lines 2792-2914
#                 check_port_available()  — lines 1347-1377
#                 check_port_freed()      — lines 1388-1410
#                 _kill_by_port()         — lines 2926-2987
#
# Notes       : - subprocess.Popen with argument lists, NEVER shell=True
#               - os.setsid as preexec_fn for process group isolation
#               - Popen.pid IS the real socat PID (no setsid wrapper issue)
#               - PGID == PID under setsid (session leader)
#               - Protocol scoping in ALL stop/port functions: every port
#                 query carries both the transport (TCP ≠ UDP) and the address
#                 family (IPv4 ≠ IPv6), because tcp4 and tcp6 listeners on the
#                 same port number are independent sockets
#               - kill_by_port() only targets socat processes
#
# Version     : 0.9.0
# ==============================================================================

"""Process launch, stop, and port management for socat-manager.

All process operations use subprocess.Popen with argument lists (never
shell=True). Process isolation via os.setsid ensures each socat process
runs in its own process group.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

from socat_manager.commands import cmd_list_to_string
from socat_manager.config import (
    DEFAULTS,
    SESSION_FIELDS,
    RuntimePaths,
    protocol_family,
    protocol_transport,
    socket_scope_flags,
)
from socat_manager.logging_setup import (
    _ensure_dirs,
    get_paths,
    log_debug,
    log_error,
    log_info,
    log_session,
    log_success,
    log_warning,
)
from socat_manager.session import (
    generate_session_id,
    session_count,
    session_read_field,
    session_register,
    session_unregister,
)

# ==============================================================================
# PROCESS LAUNCH
# Bash equivalent: launch_socat_session() — lines 1221-1329
# ==============================================================================

def launch_socat_session(
    name: str,
    mode: str,
    proto: str,
    lport: int,
    cmd: list[str],
    rhost: str = "",
    rport: str = "",
    stderr_redirect: str = "",
) -> tuple[str, int]:
    """Launch a socat process with session tracking and process isolation.

    Creates a new process group via os.setsid, verifies the process
    survives startup, and registers a session file with metadata.

    Key differences from bash:
        - Python's Popen.pid gives the real socat PID directly
          (no setsid wrapper PID problem, no PID-file handoff needed)
        - Returns (session_id, pid) tuple directly (no global variable
          needed, no $() subshell blocking issue)

    Args:
        name: Human-readable session name.
        mode: Operational mode (listen, forward, tunnel, redirect, etc.).
        proto: Normalized protocol (tcp4, udp4, etc.).
        lport: Local port number.
        cmd: Socat command as argument list for Popen.
        rhost: Optional remote host (for session file recording).
        rport: Optional remote port (for session file recording).
        stderr_redirect: Path to redirect stderr (for capture mode).
                        Empty string = stderr to session error log.

    Returns:
        Tuple of (session_id, pid) where session_id is the 8-character
        hex string and pid is the socat process PID.

    Raises:
        RuntimeError: If launch fails (max sessions, PID death, etc.).
    """
    _ensure_dirs()
    paths: RuntimePaths = get_paths()

    # --- Check maximum session count ---
    active_count: int = session_count()
    if active_count >= DEFAULTS.max_sessions:
        msg: str = (
            f"Maximum session count ({DEFAULTS.max_sessions}) reached. "
            "Stop existing sessions first."
        )
        log_error(msg, "launch")
        raise RuntimeError(msg)

    # --- Generate unique session ID ---
    sid: str = generate_session_id()

    log_debug(f"Launching session {sid} ({name}): {cmd_list_to_string(cmd)}", "launch")
    log_session(sid, "INFO", f"Launching: {cmd_list_to_string(cmd)}")

    # --- Determine stderr destination ---
    error_log: Path = paths.log_dir / f"session-{sid}-error.log"

    stderr_target: int | object
    stderr_file_handle = None  # type: ignore[assignment]

    if stderr_redirect:
        # Capture mode: stderr → capture log file (socat -v hex dumps)
        # File already created with 0o600 by _create_capture_log() before this point
        stderr_file_handle = open(stderr_redirect, "a")
        stderr_target = stderr_file_handle
    else:
        # Normal mode: stderr → session error log
        # Create with 0o600 permissions — error logs may contain command arguments
        # and failure details that should be restricted to owner
        try:
            err_fd: int = os.open(str(error_log), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            stderr_file_handle = os.fdopen(err_fd, "a")
        except OSError:
            # Fallback: open normally if os.open fails
            stderr_file_handle = open(error_log, "a")
        stderr_target = stderr_file_handle

    # --- Launch socat via Popen with setsid ---
    try:
        process: subprocess.Popen[bytes] = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=stderr_target,
            stdin=subprocess.DEVNULL,
            preexec_fn=os.setsid,  # Process group isolation
            close_fds=True,
        )
    except FileNotFoundError:
        if stderr_file_handle:
            stderr_file_handle.close()
        msg = f"socat not found in PATH — cannot launch session {sid} ({name})"
        log_error(msg, "launch")
        raise RuntimeError(msg)
    except OSError as exc:
        if stderr_file_handle:
            stderr_file_handle.close()
        msg = f"Failed to launch session {sid} ({name}): {exc}"
        log_error(msg, "launch")
        raise RuntimeError(msg) from exc

    # Note: stderr file handle is intentionally NOT closed here.
    # The child process inherits it and writes to it. Closing it in
    # the parent is safe because the child has its own fd copy via fork.
    if stderr_file_handle:
        stderr_file_handle.close()

    socat_pid: int = process.pid

    # Retain the handle so the child's exit status can be collected. Without
    # it the process would linger as a zombie after exit, and a zombie still
    # answers signal 0 — any liveness poll based on signal 0 alone would go on
    # reporting the dead process as alive.
    register_child(process)

    # --- Stability check ---
    # Brief pause to verify socat bound the port and is stable
    time.sleep(DEFAULTS.launch_stability_delay)

    if not process_is_running(socat_pid):
        msg = (
            f"Session {sid} ({name}) failed — "
            f"process {socat_pid} died immediately"
        )
        log_error(msg, "launch")
        log_session(sid, "ERROR", f"Process died immediately after launch (PID {socat_pid})")
        raise RuntimeError(msg)

    # --- Under setsid, PGID == PID (session leader) ---
    pgid: int = socat_pid

    # --- Register session ---
    session_register(
        sid=sid,
        name=name,
        pid=socat_pid,
        pgid=pgid,
        mode=mode,
        proto=proto,
        lport=lport,
        socat_cmd=cmd_list_to_string(cmd),
        rhost=rhost,
        rport=str(rport) if rport else "",
    )

    log_session(sid, "INFO", f"Session active: PID={socat_pid} PGID={pgid}")

    return sid, socat_pid


# ==============================================================================
# CHILD PROCESS HANDLES AND REAPING
#
# Every socat process launched by this framework is a direct child of the
# management process. When such a child exits, the kernel keeps its entry in
# the process table until the parent collects its exit status. Until then the
# entry is a zombie.
#
# A zombie still answers signal 0. os.kill(pid, 0) therefore reports a dead
# child as alive for as long as it goes uncollected, which would make any
# liveness poll based on signal 0 alone wait forever on a process that has
# already exited. Retaining the Popen handle solves both halves of the
# problem at once: polling it collects the exit status, which removes the
# zombie, and it reports termination truthfully.
# ==============================================================================

# Handles for children launched by this process, keyed by PID. Entries are
# removed as soon as the child is collected, so the map only ever holds
# processes that are still running.
_child_handles: dict[int, subprocess.Popen[bytes]] = {}
_child_handles_lock: threading.Lock = threading.Lock()


def register_child(process: subprocess.Popen[bytes]) -> None:
    """Record a child process handle so its exit status can be collected.

    Args:
        process: The Popen handle of a freshly launched child.
    """
    with _child_handles_lock:
        _child_handles[process.pid] = process


def reap_child(pid: int) -> int | None:
    """Collect the exit status of a terminated child and drop its handle.

    Collecting the status removes the process table entry, so the child stops
    being a zombie. A child that is still running is left alone.

    Args:
        pid: PID of the child to collect.

    Returns:
        The child's exit status, or None if it is not a child of this process
        or is still running.
    """
    with _child_handles_lock:
        process: subprocess.Popen[bytes] | None = _child_handles.get(pid)

    if process is None:
        return None

    # poll() collects the exit status of a terminated child without blocking.
    status: int | None = process.poll()

    if status is not None:
        with _child_handles_lock:
            _child_handles.pop(pid, None)

    return status


def _is_zombie(pid: int) -> bool:
    """Check whether a PID names a process that has exited but not been reaped.

    Args:
        pid: Process ID to inspect.

    Returns:
        True if the process is in the zombie state, False otherwise.
    """
    try:
        stat: str = Path(f"/proc/{pid}/stat").read_text()
    except (OSError, ValueError):
        return False

    # The state field follows the executable name, which is parenthesized and
    # may itself contain spaces. Split after the closing parenthesis.
    _, _, remainder = stat.rpartition(")")
    fields: list[str] = remainder.split()

    return bool(fields) and fields[0] == "Z"


def process_is_running(pid: int) -> bool:
    """Check whether a process is running, treating an unreaped child as dead.

    For a child of this process the Popen handle is authoritative: polling it
    collects the exit status of a terminated child, which both reports the
    truth and clears the zombie.

    For any other process — one adopted from a previous invocation, for
    instance — signal 0 is used, qualified by a zombie check so that an
    uncollected process is not mistaken for a live one.

    Args:
        pid: Process ID to check.

    Returns:
        True if the process is running, False if it has exited.
    """
    if pid <= 0:
        return False

    with _child_handles_lock:
        process: subprocess.Popen[bytes] | None = _child_handles.get(pid)

    if process is not None:
        if process.poll() is None:
            return True
        # Terminated: the status has now been collected, so drop the handle.
        with _child_handles_lock:
            _child_handles.pop(pid, None)
        return False

    try:
        os.kill(pid, 0)
    except OSError:
        return False

    return not _is_zombie(pid)


# ==============================================================================
# PROTOCOL SCOPE HELPERS
# The protocol model has four members (tcp4, tcp6, udp4, udp6). Every port
# operation must preserve all four, not collapse them to TCP versus UDP.
# Scope derivation lives in config.py, which owns the protocol model; these
# module-level bindings keep the call sites in this module short.
# ==============================================================================

_transport_of = protocol_transport
_family_of = protocol_family
_scope_flags = socket_scope_flags


def _line_matches_port(line: str, port: int) -> bool:
    """Check whether a socket-listing line refers to the given local port.

    Args:
        line: A single line of ss or netstat output.
        port: Port number to match.

    Returns:
        True if the line's address ends with the port number.
    """
    return (
        f":{port} " in line
        or f":{port}\t" in line
        or line.rstrip().endswith(f":{port}")
    )


# ==============================================================================
# PORT AVAILABILITY CHECK
# Bash equivalent: check_port_available() — lines 1347-1377
# ==============================================================================

def check_port_available(port: int, proto: str) -> bool:
    """Check if a port is available for binding on a specific protocol.

    Uses ss (preferred) or netstat to detect existing listeners. The query is
    scoped to both the transport and the address family of the supplied
    protocol, so a tcp6 listener never masks an available tcp4 port and a UDP
    listener never masks an available TCP port. This is what makes dual-stack
    and mixed-family deployments correct.

    Args:
        port: Port number to check.
        proto: Protocol to check (tcp4, tcp6, udp4, udp6).

    Returns:
        True if the port is available, False if in use.
    """
    flags: list[str] = _scope_flags(proto)

    # Try ss first (preferred, modern)
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["ss", *flags],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if _line_matches_port(line, port):
                    return False
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: try netstat (same flag vocabulary)
    try:
        result = subprocess.run(
            ["netstat", *flags],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if _line_matches_port(line, port):
                    return False
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # No tool available; warn and proceed (assume available)
    log_warning(
        f"Neither ss nor netstat available; cannot check port {port}",
        "port-check",
    )
    return True


# ==============================================================================
# PORT FREED VERIFICATION
# Bash equivalent: check_port_freed() — lines 1388-1410
# ==============================================================================

def check_port_freed(
    port: int,
    proto: str,
    retries: int = 0,
) -> bool:
    """Verify that a port has been released after stopping a session.

    Retries multiple times with a delay to account for TIME_WAIT state.
    Scoped to the transport and address family of the supplied protocol, so a
    listener of the other family on the same port number does not keep this
    check reporting the port as still in use.

    Args:
        port: Port number to verify.
        proto: Protocol to check (tcp4, tcp6, udp4, udp6).
        retries: Maximum retry attempts (0 = use default from config).

    Returns:
        True if the port is freed, False if still in use.
    """
    max_retries: int = retries if retries > 0 else DEFAULTS.stop_verify_retries

    for attempt in range(max_retries):
        if check_port_available(port, proto):
            return True
        time.sleep(DEFAULTS.stop_verify_interval)

    return False


# ==============================================================================
# KILL BY PORT (LAST RESORT)
# Bash equivalent: _kill_by_port() — lines 2926-2987
# ==============================================================================

def kill_by_port(port: int, proto: str) -> None:
    """Last-resort function to kill socat processes on a specific port.

    Uses ss or lsof to find PIDs bound to the port. Only targets processes
    whose command name contains 'socat' to avoid killing unrelated services.

    The query is scoped to both the transport and the address family of the
    supplied protocol. Without the family scope this function would enumerate
    listeners of the other family on the same port number and could terminate
    an unrelated socat session — a TCP session on tcp6 while stopping a
    session on tcp4, for example. The two are independent sockets and a stop
    directed at one must never disturb the other.

    Args:
        port: Port number to clean up.
        proto: Protocol scope (tcp4, tcp6, udp4, udp6).
    """
    transport: str = _transport_of(proto)
    family: str = _family_of(proto)
    pids_found: set[int] = set()

    # --- Try ss to find PIDs ---
    # -p adds the owning process to each row; the remaining flags scope the
    # query to one transport and one address family.
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ["ss", *_scope_flags(proto), "-p"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if _line_matches_port(line, port):
                    # Extract PIDs from ss -p output (format: "pid=NNNN")
                    _extract_pids_from_line(line, pids_found)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # --- Fallback: try lsof ---
    # lsof expresses the address family as a separate selector (-i4 / -i6),
    # so the family scope is carried through here as well.
    if not pids_found:
        try:
            lsof_proto: str = "UDP" if transport == "udp" else "TCP"
            result = subprocess.run(
                ["lsof", f"-i{family}", f"-i{lsof_proto}:{port}", "-t"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    line = line.strip()
                    if line.isdigit():
                        pids_found.add(int(line))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # --- Kill only socat processes ---
    for pid in pids_found:
        if _is_socat_process(pid):
            log_debug(f"kill_by_port: killing socat PID {pid} on {proto}:{port}", "stop")
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


def _extract_pids_from_line(line: str, pids: set[int]) -> None:
    """Extract PID numbers from an ss -p output line.

    ss -p includes process info in format: "users:(("socat",pid=12345,fd=4))"
    We extract the numeric PID values.

    Args:
        line: A single line from ss output.
        pids: Set to add found PIDs to (mutated in place).
    """
    # Match pid=NNNN patterns in ss output
    for match in re.finditer(r"pid=(\d+)", line):
        try:
            pids.add(int(match.group(1)))
        except ValueError:
            pass


def _is_socat_process(pid: int) -> bool:
    """Check if a PID belongs to a socat process.

    Reads /proc/{pid}/comm to verify the process name contains 'socat'.
    This prevents kill_by_port from killing unrelated services.

    Args:
        pid: Process ID to check.

    Returns:
        True if the process is socat, False otherwise.
    """
    try:
        comm_path: Path = Path(f"/proc/{pid}/comm")
        comm: str = comm_path.read_text().strip()
        return "socat" in comm.lower()
    except (OSError, ValueError):
        return False


# ==============================================================================
# 9-STEP STOP SEQUENCE
# Bash equivalent: _stop_session() — lines 2792-2914
# ==============================================================================

def stop_session(sid: str) -> bool:
    """Execute the 9-step stop sequence for a session.

    This is the critical stop path. Every step must be protocol-scoped
    to prevent cross-protocol interference on dual-stack configurations.

    Steps:
        1. Read PROTOCOL from session file
        2. Touch .stop signal file (tells watchdog not to restart)
        3. os.killpg(pgid, SIGTERM) — SIGTERM entire process group
        4. os.kill(pid, SIGTERM) — direct SIGTERM to PID
        5. Wait up to STOP_GRACE_SECONDS in 0.5s intervals
        6. SIGKILL if still alive (process group + PID)
        7. kill_by_port() — protocol-scoped fallback
        8. check_port_freed() — verify port released
        9. Remove session file + signal files

    Args:
        sid: Session ID to stop.

    Returns:
        True if session was successfully stopped, False if issues remain.
    """
    # Defense-in-depth: validate sid to prevent path traversal.
    # Production SIDs are uuid4 hex (e.g., "a1b2c3d4"), but test fixtures
    # may use readable SIDs (e.g., "tcp11111"). Reject only dangerous chars.
    if not sid or "/" in sid or "\\" in sid or ".." in sid or "\0" in sid:
        log_error(f"Invalid session ID: '{sid}'", "stop")
        return False

    paths: RuntimePaths = get_paths()
    session_file: Path = paths.session_dir / f"{sid}.session"

    if not session_file.is_file():
        log_warning(f"Session file not found for '{sid}'", "stop")
        return False

    # --- Step 1: Read session metadata ---
    name: str = session_read_field(session_file, SESSION_FIELDS.session_name)
    pid_str: str = session_read_field(session_file, SESSION_FIELDS.pid)
    pgid_str: str = session_read_field(session_file, SESSION_FIELDS.pgid)
    lport_str: str = session_read_field(session_file, SESSION_FIELDS.local_port)
    proto: str = session_read_field(session_file, SESSION_FIELDS.protocol)

    # Default protocol if not recorded (legacy sessions)
    if not proto:
        proto = "tcp4"

    pid: int = int(pid_str) if pid_str and pid_str.isdigit() else 0
    pgid: int = int(pgid_str) if pgid_str and pgid_str.isdigit() else 0
    lport: int = int(lport_str) if lport_str and lport_str.isdigit() else 0

    log_info(
        f"Stopping session {sid} ({name}, PID {pid}, PGID {pgid}, {proto})...",
        "stop",
    )
    log_session(sid, "INFO", f"Stop requested for {proto} session")

    # --- Step 2: Signal watchdog to stop gracefully ---
    stop_file: Path = paths.session_dir / f"{sid}.stop"
    try:
        stop_file.touch(exist_ok=True)
    except OSError:
        pass

    # --- Step 3: SIGTERM the entire process group ---
    if pgid > 0:
        try:
            os.killpg(pgid, 0)  # Check if group exists
            log_debug(f"Sending SIGTERM to process group -{pgid}", "stop")
            os.killpg(pgid, signal.SIGTERM)
        except OSError:
            pass

    # --- Step 4: SIGTERM the specific PID + direct children ---
    if pid > 0:
        try:
            os.kill(pid, 0)  # Check if PID exists
            log_debug(f"Sending SIGTERM to PID {pid}", "stop")
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        # Kill any direct children that may have been forked by socat
        # (belt-and-suspenders alongside the process group kill)
        try:
            subprocess.run(
                ["pkill", "-TERM", "-P", str(pid)],
                capture_output=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # --- Step 5: Wait grace period for clean shutdown ---
    is_dead: bool = False
    max_waits: int = int(DEFAULTS.stop_grace_seconds / DEFAULTS.stop_verify_interval)

    for _ in range(max_waits):
        pid_alive: bool = False
        pgid_alive: bool = False

        if pid > 0:
            try:
                os.kill(pid, 0)
                pid_alive = True
            except OSError:
                pass

        if pgid > 0:
            try:
                os.killpg(pgid, 0)
                pgid_alive = True
            except OSError:
                pass

        if not pid_alive and not pgid_alive:
            is_dead = True
            break

        time.sleep(DEFAULTS.stop_verify_interval)

    # --- Step 6: Force kill if still alive ---
    if not is_dead:
        log_warning(
            f"Session {sid} still alive after grace period, sending SIGKILL...",
            "stop",
        )

        # SIGKILL the process group
        if pgid > 0:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except OSError:
                pass

        # SIGKILL the specific PID and its children
        if pid > 0:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                subprocess.run(
                    ["pkill", "-KILL", "-P", str(pid)],
                    capture_output=True, timeout=5,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        time.sleep(DEFAULTS.stop_verify_interval)

    # --- Step 6b: Verify PID is truly dead ---
    final_check: bool = True
    if pid > 0:
        try:
            os.kill(pid, 0)
            final_check = False  # Still alive
        except OSError:
            final_check = True  # Dead

    # --- Step 7: Fallback — kill by port if still in use (protocol-scoped) ---
    if lport > 0:
        if not check_port_available(lport, proto):
            log_warning(
                f"Port {lport} ({proto}) still in use after kill, "
                "attempting port-based cleanup...",
                "stop",
            )
            kill_by_port(lport, proto)
            time.sleep(DEFAULTS.stop_verify_interval)

    # --- Step 8: Final port verification (protocol-scoped) ---
    if lport > 0:
        if not check_port_freed(lport, proto, retries=DEFAULTS.stop_verify_retries):
            log_warning(
                f"Port {lport} ({proto}) may still be in TIME_WAIT state",
                "stop",
            )

    # --- Step 9: Remove session file and associated signal files ---
    session_unregister(sid)

    if final_check:
        log_success(f"Stopped: {sid} ({name}, {proto})", "stop")
        log_session(sid, "INFO", "Session stopped successfully")
    else:
        log_warning(
            f"Session {sid} ({name}) may not be fully stopped — "
            "manual verification recommended",
            "stop",
        )
        log_session(sid, "WARNING", "Session stop may be incomplete")

    return final_check

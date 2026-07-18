# ==============================================================================
# MODULE      : socat_manager/watchdog.py
# ==============================================================================
# Synopsis    : Watchdog auto-restart monitor for socat sessions
# Description : Implements a background monitor that watches an already-running
#               socat process and automatically restarts it on unexpected exit.
#
#               CRITICAL DESIGN: The watchdog does NOT launch the initial
#               process. launch_socat_session() handles that. The watchdog
#               MONITORS the existing PID and only launches new processes
#               on restart after confirmed death.
#
#               Bash equivalent: watchdog_loop() -- lines 1703-1756
#
#               Behavior:
#                 1. Monitor existing process (initial_pid) via
#                    process_is_running(), which polls the retained child
#                    handle and reports an exited child truthfully
#                 2. On death: check for .stop file → if present, exit
#                 3. Check restart count vs max
#                 4. Sleep with exponential backoff (configurable initial,
#                    doubles each restart, capped at 60s)
#                 5. Re-launch socat with same parameters via Popen
#                 6. Rewrite the session record with the replacement PID/PGID
#                 7. Monitor the re-launched process until it exits
#                 8. On max restarts exceeded, log error and unregister
#
# Notes       : - Runs as a daemon thread (daemon=True)
#               - First iteration monitors existing PID (no duplicate launch)
#               - Subsequent iterations launch new processes
#               - Every replacement is written back to the session file, so
#                 liveness checks and the stop sequence act on the process
#                 that currently owns the port
#               - .stop file coordination prevents restart on deliberate stop
#               - Exponential backoff prevents rapid restart loops
#               - Both max_restarts and backoff_initial are configurable
#               - Launched processes are children of the management process.
#                 Their exit status is collected when they terminate, so no
#                 zombie entries accumulate and death is detected truthfully
#
# Version     : 1.0.2
# ==============================================================================

"""Watchdog auto-restart monitor for socat sessions.

Monitors an already-running process and re-launches on unexpected death.
Does NOT launch the initial process -- that is done by launch_socat_session().
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

from socat_manager import audit
from socat_manager.config import CORRELATION_ID, DEFAULTS
from socat_manager.logging_setup import (
    get_paths,
    log_error,
    log_info,
    log_session,
    log_warning,
)
from socat_manager.process import process_is_running, reap_child, register_child
from socat_manager.session import session_unregister, session_update_process

# ==============================================================================
# WATCHDOG THREAD FUNCTION
# ==============================================================================

def watchdog_loop(
    session_id: str,
    session_name: str,
    cmd: list[str],
    initial_pid: int,
    max_restarts: int = 0,
    backoff_initial: int = 1,
    stderr_redirect: str = "",
) -> None:
    """Background watchdog that monitors a process and auto-restarts on crash.

    IMPORTANT: This function does NOT launch the initial socat process.
    It monitors the already-running process identified by initial_pid.
    Only after that process dies does it enter the restart loop.

    On each restart, exponential backoff is applied starting from
    backoff_initial seconds, doubling each time, capped at 60 seconds.

    After every successful restart the session record is rewritten with the
    replacement PID and PGID. The session file is the authoritative source
    of process identity, so this keeps liveness reporting and the stop
    sequence aligned with the process that currently owns the port.

    The .stop signal file tells the watchdog "this was a deliberate
    stop -- do NOT restart."

    Args:
        session_id: Session ID being monitored.
        session_name: Human-readable session name.
        cmd: Socat command as argument list (used for restarts).
        initial_pid: PID of the already-running process to monitor.
        max_restarts: Maximum restart attempts (0 = use default).
        backoff_initial: Initial backoff delay in seconds (default: 1).
        stderr_redirect: Path for stderr redirection (capture mode).
    """
    if max_restarts <= 0:
        max_restarts = DEFAULTS.watchdog_max_restarts

    paths = get_paths()
    restart_count: int = 0
    backoff: int = max(backoff_initial, 1)

    log_info(
        f"Watchdog started for '{session_name}' [{session_id}] "
        f"(max {max_restarts} restarts, backoff {backoff_initial}s)",
        "watchdog",
    )
    log_session(
        session_id, "INFO",
        f"Watchdog monitoring PID {initial_pid} (max {max_restarts} restarts)",
    )

    # ── Phase 1: Monitor the initial (already-running) process ──
    # Wait for the process to die, evaluating liveness through
    # process_is_running() so an exited child is not mistaken for a live
    # zombie. This avoids the duplicate-launch bug where the watchdog tried to
    # bind a port that was already in use by the primary launch.
    _wait_for_pid_death(initial_pid, session_id, paths)

    # Check if stop was requested during initial monitoring
    stop_file: Path = paths.session_dir / f"{session_id}.stop"
    if stop_file.exists():
        _handle_stop_signal(stop_file, session_id, session_name)
        return

    # ── Phase 2: Restart loop ──
    # The initial process is dead. Now enter the restart cycle.
    while restart_count < max_restarts:
        restart_count += 1

        # The monitored process has died (initial death or a prior replacement).
        audit.record_event(
            audit.EVENT_CRASH,
            correlation_id=CORRELATION_ID,
            session_id=session_id, name=session_name,
            detail=f"process died; restart attempt {restart_count}/{max_restarts}",
        )

        log_warning(
            f"Process died. Restarting in {backoff}s... "
            f"({restart_count}/{max_restarts})",
            "watchdog",
        )
        time.sleep(backoff)

        # Check stop signal before restart
        if stop_file.exists():
            _handle_stop_signal(stop_file, session_id, session_name)
            return

        # Launch replacement process
        pid: int = _launch_replacement(
            cmd, session_id, session_name, restart_count, stderr_redirect,
        )

        if pid <= 0:
            # Launch failed -- exit watchdog
            break

        # Rewrite the session record to point at the replacement process.
        # The session file is the authoritative source of process identity
        # for liveness checks and for the stop sequence. Without this update
        # both would act on the terminated predecessor, reporting the session
        # as dead while the replacement continued to hold the port.
        # Under setsid the replacement is a session leader, so PGID == PID.
        session_update_process(session_id, pid=pid, pgid=pid)

        audit.record_event(
            audit.EVENT_RESTART,
            correlation_id=CORRELATION_ID,
            session_id=session_id, name=session_name, pid=pid, pgid=pid,
            detail=f"restart {restart_count}/{max_restarts}",
        )
        audit.record_restart(session_id)

        # Monitor the replacement process (blocking wait)
        _wait_for_pid_death(pid, session_id, paths)

        # Check stop signal after process death
        if stop_file.exists():
            _handle_stop_signal(stop_file, session_id, session_name)
            return

        # Exponential backoff: doubles each restart, capped at 60 seconds
        backoff = min(backoff * 2, 60)

    # Max restarts reached or launch failure
    if restart_count >= max_restarts:
        log_error(
            f"Watchdog: max restarts ({max_restarts}) reached for "
            f"'{session_name}' [{session_id}]",
            "watchdog",
        )
        audit.record_session_end(session_id, "watchdog_exhausted")

    # Cleanup: unregister session
    session_unregister(session_id)
    log_info(f"Watchdog exiting for '{session_name}' [{session_id}]", "watchdog")


# ==============================================================================
# INTERNAL HELPERS
# ==============================================================================

def _wait_for_pid_death(pid: int, session_id: str, paths: object) -> None:
    """Block until a process dies, then collect it if it is our child.

    Liveness is evaluated through process.process_is_running(), which is
    authoritative for children of this process. A socat process launched by
    this framework is such a child, and an exited child remains in the process
    table as a zombie until its exit status is collected. A zombie still
    answers signal 0, so a poll based on signal 0 alone would report an exited
    process as alive indefinitely and this function would never return.

    Once death is observed the child is reaped, which removes its process
    table entry.

    Also checks for the .stop signal file to allow early exit on deliberate
    stop.

    Args:
        pid: Process ID to monitor.
        session_id: Session ID (for .stop file check).
        paths: RuntimePaths instance.
    """
    while True:
        if not process_is_running(pid):
            # Collect the exit status so the child does not linger as a zombie.
            reap_child(pid)
            return

        # Check if stop was requested
        stop_file: Path = getattr(paths, "session_dir") / f"{session_id}.stop"
        if stop_file.exists():
            # A deliberate stop is collecting the process on the stop path.
            # Collect here too in case the process has already exited when the
            # signal is observed; reap_child() is idempotent and a no-op while
            # the process is still running.
            reap_child(pid)
            return

        time.sleep(DEFAULTS.watchdog_poll_interval)


def _launch_replacement(
    cmd: list[str],
    session_id: str,
    session_name: str,
    restart_count: int,
    stderr_redirect: str,
) -> int:
    """Launch a replacement socat process for the watchdog.

    Args:
        cmd: Socat command as argument list.
        session_id: Session ID for logging.
        session_name: Session name for logging.
        restart_count: Current restart attempt number.
        stderr_redirect: Path for stderr redirection.

    Returns:
        PID of the launched process, or 0 on failure.
    """
    stderr_target = subprocess.DEVNULL
    stderr_fh = None

    if stderr_redirect:
        try:
            stderr_fh = open(stderr_redirect, "a")
            stderr_target = stderr_fh  # type: ignore[assignment]
        except OSError:
            stderr_target = subprocess.DEVNULL

    try:
        process: subprocess.Popen[bytes] = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=stderr_target,
            stdin=subprocess.DEVNULL,
            preexec_fn=os.setsid,
            close_fds=True,
        )
    except (FileNotFoundError, OSError) as exc:
        log_error(
            f"Watchdog: failed to launch process for '{session_name}': {exc}",
            "watchdog",
        )
        if stderr_fh:
            stderr_fh.close()
        return 0

    if stderr_fh:
        stderr_fh.close()

    pid: int = process.pid

    # Retain the handle so the replacement's exit status can be collected when
    # it terminates. An uncollected child remains a zombie, and a zombie still
    # answers signal 0 -- death would never be observed and the watchdog would
    # stop restarting.
    register_child(process)

    log_info(f"Process re-launched: PID {pid} (restart #{restart_count})", "watchdog")
    log_session(
        session_id, "INFO",
        f"Watchdog re-launched socat PID {pid} (restart #{restart_count})",
    )

    return pid


def _handle_stop_signal(stop_file: Path, session_id: str, session_name: str) -> None:
    """Handle a .stop signal file -- graceful watchdog exit.

    Args:
        stop_file: Path to the .stop signal file.
        session_id: Session ID.
        session_name: Session name.
    """
    try:
        stop_file.unlink(missing_ok=True)
    except OSError:
        pass  # the stop file is already removed; the watchdog is exiting either way

    log_info(
        f"Watchdog: graceful stop requested for '{session_name}' [{session_id}]",
        "watchdog",
    )
    session_unregister(session_id)
    log_info(f"Watchdog exiting for '{session_name}' [{session_id}]", "watchdog")


# ==============================================================================
# WATCHDOG LAUNCHER
# ==============================================================================

def start_watchdog(
    session_id: str,
    session_name: str,
    cmd: list[str],
    initial_pid: int,
    max_restarts: int = 0,
    backoff_initial: int = 1,
    stderr_redirect: str = "",
) -> threading.Thread:
    """Start a watchdog monitor as a daemon thread.

    The watchdog monitors the already-running process (initial_pid)
    and only re-launches on death. It does NOT launch the initial process.

    Args:
        session_id: Session ID to monitor.
        session_name: Human-readable session name.
        cmd: Socat command as argument list (used for restarts).
        initial_pid: PID of the already-running process.
        max_restarts: Maximum restart attempts (0 = use default).
        backoff_initial: Initial backoff seconds between restarts (default: 1).
        stderr_redirect: Path for stderr redirection (capture mode).

    Returns:
        The started daemon Thread object.
    """
    thread: threading.Thread = threading.Thread(
        target=watchdog_loop,
        args=(
            session_id, session_name, cmd, initial_pid,
            max_restarts, backoff_initial, stderr_redirect,
        ),
        name=f"watchdog-{session_id}",
        daemon=True,
    )
    thread.start()
    return thread

# ==============================================================================
# FILE        : tests/conftest.py
# ==============================================================================
# Synopsis    : Shared pytest fixtures for socat-manager tests
# Description : Provides temporary directory management, base dir override,
#               mock session creation, and common test utilities.
# Version     : 1.0.1
# ==============================================================================

"""Shared pytest fixtures for socat-manager tests."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest

import socat_manager.logging_setup as logging_mod
from socat_manager.logging_setup import _ensure_dirs, get_paths, set_base_dir
from socat_manager.session import session_register


@pytest.fixture(autouse=True)
def isolated_base_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Override the base directory for every test to use a temp directory.

    This ensures tests never write to the real filesystem and each
    test gets a completely clean session/log/cert directory.

    Yields:
        Path to the temporary base directory.
    """
    # Reset the dirs-ensured guard so _ensure_dirs runs fresh
    logging_mod._dirs_ensured = False

    # Override base dir
    set_base_dir(tmp_path)
    _ensure_dirs()

    yield tmp_path

    # Reset for next test
    logging_mod._dirs_ensured = False


@pytest.fixture
def paths(isolated_base_dir: Path):
    """Provide the RuntimePaths instance pointing to the temp directory."""
    return get_paths()


@pytest.fixture
def sample_session(paths) -> str:
    """Register a sample session and return its session ID.

    Creates a session file matching the bash fixture format:
        SESSION_ID=abcd1234, PID=99999, proto=tcp4, port=8443, etc.
    """
    sid = "abcd1234"
    session_register(
        sid=sid,
        name="redir-tcp4-8443-example.com-443",
        pid=99999,
        pgid=99999,
        mode="redirect",
        proto="tcp4",
        lport=8443,
        socat_cmd="socat -v TCP4-LISTEN:8443,reuseaddr,fork,backlog=128 TCP4:example.com:443",
        rhost="example.com",
        rport="443",
    )
    return sid


@pytest.fixture
def dual_stack_sessions(paths) -> tuple[str, str]:
    """Register two sessions on the same port with different protocols.

    Returns:
        Tuple of (tcp_sid, udp_sid).
    """
    tcp_sid = "tcp11111"
    udp_sid = "udp22222"

    session_register(
        sid=tcp_sid,
        name="tcp4-8080",
        pid=11111,
        pgid=11111,
        mode="listen",
        proto="tcp4",
        lport=8080,
        socat_cmd="socat -u TCP4-LISTEN:8080,reuseaddr,fork OPEN:/tmp/log,creat,append",
    )

    session_register(
        sid=udp_sid,
        name="udp4-8080",
        pid=22222,
        pgid=22222,
        mode="listen",
        proto="udp4",
        lport=8080,
        socat_cmd="socat -u UDP4-LISTEN:8080,reuseaddr,fork OPEN:/tmp/log,creat,append",
    )

    return tcp_sid, udp_sid

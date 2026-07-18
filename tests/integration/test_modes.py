# ==============================================================================
# FILE        : tests/integration/test_modes.py
# ==============================================================================
# Synopsis    : Integration tests for status and stop mode handlers
# Description : Tests mode_status() and mode_stop() with real session fixtures.
#               These modes don't require socat — they only read session files
#               and call the stop sequence.
# Version     : 1.0.2
# ==============================================================================

"""Integration tests for status and stop mode handlers."""

from __future__ import annotations

from argparse import Namespace
from unittest.mock import patch

import pytest

from socat_manager.modes.status import mode_status
from socat_manager.modes.stop import mode_stop
from socat_manager.session import session_count


class TestModeStatus:
    """Tests for mode_status() handler."""

    def test_status_no_sessions(self, paths):
        """Status with no sessions should not crash."""
        args = Namespace(target=None, cleanup=False, verbose=False)
        mode_status(args)

    def test_status_lists_sessions(self, sample_session, paths):
        """Status should list the sample session."""
        args = Namespace(target=None, cleanup=False, verbose=False)
        mode_status(args)  # Should not raise

    def test_status_by_session_id(self, sample_session, paths):
        """Status with specific session ID should show details."""
        args = Namespace(target=sample_session, cleanup=False, verbose=False)
        mode_status(args)  # Should not raise

    def test_status_by_session_name(self, sample_session, paths):
        """Status with session name should show details."""
        args = Namespace(target="redir-tcp4-8443-example.com-443", cleanup=False, verbose=False)
        mode_status(args)

    def test_status_by_port(self, sample_session, paths):
        """Status with port number should show details."""
        args = Namespace(target="8443", cleanup=False, verbose=False)
        mode_status(args)

    def test_status_not_found_exits(self, paths):
        """Status with nonexistent session should exit 1."""
        args = Namespace(target="ffffffff", cleanup=False, verbose=False)
        with pytest.raises(SystemExit) as exc_info:
            mode_status(args)
        assert exc_info.value.code == 1

    def test_status_cleanup(self, sample_session, paths):
        """Status --cleanup should remove dead sessions."""
        assert session_count() == 1
        args = Namespace(target=None, cleanup=True, verbose=False)
        mode_status(args)
        # PID 99999 is dead, so session should be cleaned
        assert session_count() == 0

    def test_status_dual_stack_by_port(self, dual_stack_sessions, paths):
        """Status by port should show both TCP and UDP sessions."""
        args = Namespace(target="8080", cleanup=False, verbose=False)
        mode_status(args)  # Should show both


class TestModeStop:
    """Tests for mode_stop() handler."""

    def test_stop_no_selector_exits(self, paths):
        """Stop with no selector should exit 1."""
        args = Namespace(target=None, all=False, name=None, port=None, pid=None, verbose=False)
        with pytest.raises(SystemExit) as exc_info:
            mode_stop(args)
        assert exc_info.value.code == 1

    @patch("socat_manager.modes.stop.stop_session", return_value=True)
    def test_stop_by_session_id(self, mock_stop, sample_session, paths):
        """Stop by session ID should call stop_session."""
        args = Namespace(target=sample_session, all=False, name=None, port=None, pid=None, verbose=False)
        mode_stop(args)
        mock_stop.assert_called_once_with(sample_session)

    @patch("socat_manager.modes.stop.stop_session", return_value=True)
    def test_stop_by_name(self, mock_stop, sample_session, paths):
        """Stop by session name should find and stop the session."""
        args = Namespace(
            target=None, all=False,
            name="redir-tcp4-8443-example.com-443",
            port=None, pid=None, verbose=False,
        )
        mode_stop(args)
        mock_stop.assert_called_once_with(sample_session)

    @patch("socat_manager.modes.stop.stop_session", return_value=True)
    def test_stop_by_port(self, mock_stop, sample_session, paths):
        """Stop by port should find and stop session on that port."""
        args = Namespace(target=None, all=False, name=None, port="8443", pid=None, verbose=False)
        mode_stop(args)
        mock_stop.assert_called_once_with(sample_session)

    @patch("socat_manager.modes.stop.stop_session", return_value=True)
    def test_stop_by_pid(self, mock_stop, sample_session, paths):
        """Stop by PID should find and stop session with that PID."""
        args = Namespace(target=None, all=False, name=None, port=None, pid="99999", verbose=False)
        mode_stop(args)
        mock_stop.assert_called_once_with(sample_session)

    def test_stop_invalid_pid_exits(self, paths):
        """Stop with non-numeric PID should exit 1."""
        args = Namespace(target=None, all=False, name=None, port=None, pid="abc", verbose=False)
        with pytest.raises(SystemExit) as exc_info:
            mode_stop(args)
        assert exc_info.value.code == 1

    @patch("socat_manager.modes.stop.stop_session", return_value=True)
    def test_stop_all(self, mock_stop, sample_session, paths):
        """Stop --all should stop all sessions."""
        args = Namespace(target=None, all=True, name=None, port=None, pid=None, verbose=False)
        mode_stop(args)
        mock_stop.assert_called()

    @patch("socat_manager.modes.stop.stop_session", return_value=True)
    def test_stop_dual_stack_by_port(self, mock_stop, dual_stack_sessions, paths):
        """Stop by port should stop both TCP and UDP sessions."""
        tcp_sid, udp_sid = dual_stack_sessions
        args = Namespace(target=None, all=False, name=None, port="8080", pid=None, verbose=False)
        mode_stop(args)
        assert mock_stop.call_count == 2

    def test_stop_nonexistent_name(self, paths):
        """Stop by nonexistent name should warn but not crash."""
        args = Namespace(target=None, all=False, name="ghost", port=None, pid=None, verbose=False)
        mode_stop(args)  # Should not raise

    def test_stop_nonexistent_port(self, paths):
        """Stop by nonexistent port should warn but not crash."""
        args = Namespace(target=None, all=False, name=None, port="9999", pid=None, verbose=False)
        mode_stop(args)  # Should not raise (valid port, no sessions on it)

    @patch("socat_manager.modes.stop.stop_session", return_value=True)
    def test_stop_by_positional_name(self, mock_stop, sample_session, paths):
        """Stop with positional argument matching a name should work."""
        args = Namespace(
            target="redir-tcp4-8443-example.com-443",
            all=False, name=None, port=None, pid=None, verbose=False,
        )
        mode_stop(args)
        mock_stop.assert_called_once_with(sample_session)

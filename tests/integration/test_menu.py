# ==============================================================================
# FILE        : tests/integration/test_menu.py
# ==============================================================================
# Synopsis    : Integration tests for interactive menu system
# Description : Tests the menu prompt helpers, cancel detection, input
#               validation in prompts, and submenu dispatch logic.
#               Uses monkeypatched builtins.input to simulate user input.
# Version     : 1.0.1
# ==============================================================================

"""Integration tests for the interactive menu system."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from socat_manager.menu import (
    _is_cancel,
    _menu_forward,
    _menu_listen,
    _menu_status,
    _menu_stop,
    _MenuCancel,
    _prompt,
    _prompt_choice,
    _prompt_host,
    _prompt_name,
    _prompt_port,
    _prompt_protocol,
    _prompt_yn,
)

# ==============================================================================
# CANCEL DETECTION
# ==============================================================================

class TestCancelDetection:
    """Tests for _is_cancel() keyword recognition."""

    @pytest.mark.parametrize("keyword", ["q", "quit", "cancel", "back", "exit"])
    def test_cancel_keywords(self, keyword):
        assert _is_cancel(keyword) is True

    @pytest.mark.parametrize("keyword", ["Q", "QUIT", "Cancel", "BACK", "EXIT"])
    def test_cancel_case_insensitive(self, keyword):
        assert _is_cancel(keyword) is True

    def test_cancel_with_spaces(self):
        assert _is_cancel("  q  ") is True
        assert _is_cancel(" quit ") is True

    @pytest.mark.parametrize("text", ["yes", "no", "8080", "tcp4", "listen", ""])
    def test_non_cancel_inputs(self, text):
        assert _is_cancel(text) is False


# ==============================================================================
# PROMPT HELPERS
# ==============================================================================

class TestPrompt:
    """Tests for _prompt() with simulated input."""

    @patch("builtins.input", return_value="hello")
    def test_returns_input(self, mock_input):
        assert _prompt("Test") == "hello"

    @patch("builtins.input", return_value="")
    def test_returns_default_on_empty(self, mock_input):
        assert _prompt("Test", default="fallback") == "fallback"

    @patch("builtins.input", return_value="  spaced  ")
    def test_strips_whitespace(self, mock_input):
        assert _prompt("Test") == "spaced"

    @patch("builtins.input", return_value="q")
    def test_cancel_raises(self, mock_input):
        with pytest.raises(_MenuCancel):
            _prompt("Test")

    @patch("builtins.input", return_value="quit")
    def test_cancel_quit(self, mock_input):
        with pytest.raises(_MenuCancel):
            _prompt("Test")

    @patch("builtins.input", return_value="cancel")
    def test_cancel_cancel(self, mock_input):
        with pytest.raises(_MenuCancel):
            _prompt("Test")

    @patch("builtins.input", side_effect=EOFError)
    def test_eof_raises_cancel(self, mock_input):
        with pytest.raises(_MenuCancel):
            _prompt("Test")

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_ctrl_c_raises_cancel(self, mock_input):
        with pytest.raises(_MenuCancel):
            _prompt("Test")


class TestPromptYn:
    """Tests for _prompt_yn() yes/no prompts."""

    @patch("builtins.input", return_value="y")
    def test_yes(self, mock_input):
        assert _prompt_yn("Continue?") is True

    @patch("builtins.input", return_value="yes")
    def test_yes_full(self, mock_input):
        assert _prompt_yn("Continue?") is True

    @patch("builtins.input", return_value="n")
    def test_no(self, mock_input):
        assert _prompt_yn("Continue?") is False

    @patch("builtins.input", return_value="no")
    def test_no_full(self, mock_input):
        assert _prompt_yn("Continue?") is False

    @patch("builtins.input", return_value="")
    def test_default_no(self, mock_input):
        assert _prompt_yn("Continue?", default="n") is False

    @patch("builtins.input", return_value="")
    def test_default_yes(self, mock_input):
        assert _prompt_yn("Continue?", default="y") is True

    @patch("builtins.input", return_value="Y")
    def test_case_insensitive(self, mock_input):
        assert _prompt_yn("Continue?") is True

    @patch("builtins.input", return_value="q")
    def test_cancel(self, mock_input):
        with pytest.raises(_MenuCancel):
            _prompt_yn("Continue?")


class TestPromptChoice:
    """Tests for _prompt_choice() numbered selection."""

    @patch("builtins.input", return_value="3")
    def test_valid_choice(self, mock_input):
        assert _prompt_choice("Select", 5) == 3

    @patch("builtins.input", return_value="0")
    def test_zero_choice(self, mock_input):
        assert _prompt_choice("Select", 5) == 0

    @patch("builtins.input", return_value="")
    def test_default_choice(self, mock_input):
        assert _prompt_choice("Select", 5, default="2") == 2

    @patch("builtins.input", return_value="q")
    def test_cancel(self, mock_input):
        with pytest.raises(_MenuCancel):
            _prompt_choice("Select", 5)


class TestPromptPort:
    """Tests for _prompt_port() validated port input."""

    @patch("builtins.input", return_value="8080")
    def test_valid_port(self, mock_input):
        assert _prompt_port() == 8080

    @patch("builtins.input", return_value="443")
    def test_common_port(self, mock_input):
        assert _prompt_port() == 443

    @patch("builtins.input", return_value="q")
    def test_cancel(self, mock_input):
        with pytest.raises(_MenuCancel):
            _prompt_port()


class TestPromptHost:
    """Tests for _prompt_host() validated hostname input."""

    @patch("builtins.input", return_value="10.0.0.1")
    def test_ipv4(self, mock_input):
        assert _prompt_host() == "10.0.0.1"

    @patch("builtins.input", return_value="example.com")
    def test_hostname(self, mock_input):
        assert _prompt_host() == "example.com"

    @patch("builtins.input", return_value="q")
    def test_cancel(self, mock_input):
        with pytest.raises(_MenuCancel):
            _prompt_host()


class TestPromptProtocol:
    """Tests for _prompt_protocol() validated protocol input."""

    @patch("builtins.input", return_value="tcp")
    def test_tcp_normalizes(self, mock_input):
        assert _prompt_protocol() == "tcp4"

    @patch("builtins.input", return_value="udp4")
    def test_udp4(self, mock_input):
        assert _prompt_protocol() == "udp4"

    @patch("builtins.input", return_value="")
    def test_default(self, mock_input):
        assert _prompt_protocol(default="tcp4") == "tcp4"

    @patch("builtins.input", return_value="q")
    def test_cancel(self, mock_input):
        with pytest.raises(_MenuCancel):
            _prompt_protocol()


class TestPromptName:
    """Tests for _prompt_name() validated session name input."""

    @patch("builtins.input", return_value="my-session")
    def test_valid_name(self, mock_input):
        assert _prompt_name() == "my-session"

    @patch("builtins.input", return_value="")
    def test_empty_returns_default(self, mock_input):
        assert _prompt_name(default="auto-name") == "auto-name"

    @patch("builtins.input", return_value="q")
    def test_cancel(self, mock_input):
        with pytest.raises(_MenuCancel):
            _prompt_name()


# ==============================================================================
# SUBMENU INTEGRATION
# ==============================================================================

class TestMenuSubmenus:
    """Tests for per-mode submenus returning correct argument lists."""

    @patch("builtins.input", side_effect=[
        "8080",      # port
        "",          # protocol (default tcp4)
        "n",         # dual-stack
        "n",         # capture
        "n",         # watchdog
        "",          # session name (default)
        "n",         # restrict source range?
        "n",         # tcp wrappers?
        "n",         # bind address
        "n",         # socat opts
    ])
    def test_listen_submenu(self, mock_input):
        result = _menu_listen()
        assert result is not None
        assert "listen" in result
        assert "--port" in result
        assert "8080" in result

    @patch("builtins.input", side_effect=[
        "8080",      # lport
        "10.0.0.1",  # rhost
        "80",        # rport
        "",          # protocol (default tcp4)
        "n",         # dual-stack
        "n",         # capture
        "n",         # watchdog
        "",          # session name
        "n",         # restrict source range?
        "n",         # tcp wrappers?
        "n",         # remote-proto
    ])
    def test_forward_submenu(self, mock_input):
        result = _menu_forward()
        assert result is not None
        assert "forward" in result
        assert "--lport" in result
        assert "--rhost" in result
        assert "10.0.0.1" in result

    @patch("builtins.input", side_effect=["1"])  # option 1: show all
    def test_status_submenu(self, mock_input):
        result = _menu_status()
        assert result == ["status"]

    @patch("builtins.input", side_effect=["2", "abcd1234"])  # option 2: specific session
    def test_status_specific_session(self, mock_input):
        result = _menu_status()
        assert result is not None
        assert "status" in result
        assert "abcd1234" in result

    @patch("builtins.input", side_effect=["5", "y"])  # option 5: stop all, confirm
    def test_stop_all_submenu(self, mock_input):
        result = _menu_stop()
        assert result is not None
        assert "--all" in result

    @patch("builtins.input", side_effect=["1", "abcd1234"])  # option 1: by session ID
    def test_stop_by_id_submenu(self, mock_input):
        result = _menu_stop()
        assert result is not None
        assert "stop" in result
        assert "abcd1234" in result

    @patch("builtins.input", side_effect=["q"])  # cancel immediately
    def test_cancel_at_first_prompt(self, mock_input):
        with pytest.raises(_MenuCancel):
            _menu_listen()

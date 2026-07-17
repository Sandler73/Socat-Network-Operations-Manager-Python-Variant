# ==============================================================================
# FILE        : tests/unit/test_menu_prompts.py
# ==============================================================================
# Synopsis    : Unit tests for the interactive menu input primitives
# Description : The per-mode submenus are built on a small set of prompt helpers
#               that read a line, honor cancel keywords and end-of-input, apply
#               defaults, and validate through the shared validators with retry
#               on bad input. These tests drive those helpers with a mocked
#               input stream — covering the accept, default, cancel, and
#               retry-on-invalid paths — and exercise the common-flag collector
#               that assembles CLI arguments from menu answers.
# Version     : 1.0.1
# ==============================================================================

"""Unit tests for the interactive menu input primitives."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from socat_manager import menu
from socat_manager.menu import (
    _collect_common_flags,
    _collect_filter_flags,
    _is_cancel,
    _MenuCancel,
    _prompt,
    _prompt_choice,
    _prompt_host,
    _prompt_port,
    _prompt_protocol,
    _prompt_yn,
)


def _inputs(*values):
    """Patch builtins.input to yield the given values in order."""
    return patch("builtins.input", side_effect=list(values))


class TestIsCancel:
    @pytest.mark.parametrize("word", ["q", "quit", "cancel", "back", "exit"])
    def test_cancel_keywords(self, word):
        assert _is_cancel(word) is True
        assert _is_cancel(f"  {word.upper()}  ") is True  # trimmed, case-folded

    @pytest.mark.parametrize("word", ["8080", "yes", "quitter", ""])
    def test_non_cancel_values(self, word):
        assert _is_cancel(word) is False


class TestPrompt:
    def test_returns_entered_value(self):
        with _inputs("hello"):
            assert _prompt("Name") == "hello"

    def test_returns_default_on_empty(self):
        with _inputs(""):
            assert _prompt("Name", "fallback") == "fallback"

    def test_strips_surrounding_whitespace(self):
        with _inputs("  spaced  "):
            assert _prompt("Name") == "spaced"

    def test_cancel_keyword_raises(self):
        with _inputs("cancel"), pytest.raises(_MenuCancel):
            _prompt("Name")

    def test_eof_raises_cancel(self):
        with patch("builtins.input", side_effect=EOFError):
            with pytest.raises(_MenuCancel):
                _prompt("Name")

    def test_keyboard_interrupt_raises_cancel(self):
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            with pytest.raises(_MenuCancel):
                _prompt("Name")


class TestPromptYesNo:
    def test_yes_variants(self):
        for token in ("y", "yes", "Y", "YES"):
            with _inputs(token):
                assert _prompt_yn("Go?") is True

    def test_no_variants(self):
        for token in ("n", "no", "N", "NO"):
            with _inputs(token):
                assert _prompt_yn("Go?") is False

    def test_default_applied_on_empty(self):
        with _inputs(""):
            assert _prompt_yn("Go?", default="y") is True
        with _inputs(""):
            assert _prompt_yn("Go?", default="n") is False

    def test_retries_on_invalid_then_accepts(self):
        with _inputs("maybe", "sure", "y"):
            assert _prompt_yn("Go?") is True

    def test_cancel_raises(self):
        with _inputs("back"), pytest.raises(_MenuCancel):
            _prompt_yn("Go?")


class TestPromptChoice:
    def test_accepts_in_range(self):
        with _inputs("3"):
            assert _prompt_choice("Pick", 5) == 3

    def test_accepts_zero_boundary(self):
        with _inputs("0"):
            assert _prompt_choice("Pick", 5) == 0

    def test_retries_out_of_range_then_accepts(self):
        with _inputs("9", "2"):
            assert _prompt_choice("Pick", 5) == 2

    def test_retries_non_numeric_then_accepts(self):
        with _inputs("x", "1"):
            assert _prompt_choice("Pick", 5) == 1


class TestPromptPort:
    def test_accepts_valid_port(self):
        with _inputs("8080"):
            assert _prompt_port() == 8080

    def test_retries_invalid_then_accepts(self):
        with _inputs("70000", "0", "443"):
            assert _prompt_port() == 443


class TestPromptHostAndProtocol:
    def test_host_accepts_ip(self):
        with _inputs("192.168.1.1"):
            assert _prompt_host() == "192.168.1.1"

    def test_protocol_default_and_normalize(self):
        with _inputs(""):
            assert _prompt_protocol("Protocol", "tcp4") == "tcp4"
        with _inputs("udp"):
            assert _prompt_protocol() == "udp4"

    def test_protocol_retries_invalid_then_accepts(self):
        with _inputs("sctp", "tcp6"):
            assert _prompt_protocol() == "tcp6"


class TestCollectCommonFlags:
    def test_minimal_answers_produce_no_flags(self):
        # protocol default (tcp4), no dual-stack, no capture, no watchdog, no
        # name, no source range, no tcpwrap.
        with _inputs("tcp4", "n", "n", "n", "", "n", "n"):
            args: list[str] = []
            _collect_common_flags(args)
            assert args == []

    def test_full_answers_assemble_expected_flags(self):
        # protocol udp4, dual-stack yes, capture yes, watchdog yes with custom
        # max-restarts and backoff, a session name, then decline filtering.
        with _inputs("udp4", "y", "y", "y", "5", "3", "relay", "n", "n"):
            args: list[str] = []
            _collect_common_flags(args)
            assert args == [
                "--proto", "udp4",
                "--dual-stack",
                "--capture",
                "--watchdog",
                "--max-restarts", "5",
                "--backoff", "3",
                "--name", "relay",
            ]

    def test_watchdog_defaults_are_not_emitted(self):
        # Watchdog enabled but max-restarts/backoff left at defaults (10/1):
        # the flags are omitted because the CLI defaults already match.
        with _inputs("tcp4", "n", "n", "y", "10", "1", "", "n", "n"):
            args: list[str] = []
            _collect_common_flags(args)
            assert args == ["--watchdog"]

    def test_source_filtering_flags_are_collected(self):
        # Decline everything up to filtering, then accept a source range and
        # TCP wrappers with a custom daemon name.
        with _inputs("tcp4", "n", "n", "n", "", "y", "10.0.0.0/8", "y", "myd"):
            args: list[str] = []
            _collect_common_flags(args)
            assert args == ["--allow", "10.0.0.0/8", "--tcpwrap", "myd"]

    def test_cancel_propagates(self):
        with _inputs("tcp4", "cancel"):
            with pytest.raises(_MenuCancel):
                _collect_common_flags([])

    def test_offer_toggles_skip_prompts(self):
        # With protocol and dual-stack suppressed, prompts are: capture,
        # watchdog, name, source-range?, tcpwrap? Decline all → no flags,
        # five reads.
        with _inputs("n", "n", "", "n", "n") as mock_input:
            args: list[str] = []
            _collect_common_flags(args, offer_protocol=False, offer_dualstack=False)
            assert args == []
            assert mock_input.call_count == 5


class TestCollectFilterFlags:
    def test_decline_both_adds_nothing(self):
        with _inputs("n", "n"):
            args: list[str] = []
            _collect_filter_flags(args)
            assert args == []

    def test_source_range_accepted(self):
        with _inputs("y", "192.168.1.0/24", "n"):
            args: list[str] = []
            _collect_filter_flags(args)
            assert args == ["--allow", "192.168.1.0/24"]

    def test_source_range_retries_invalid_then_accepts(self):
        with _inputs("y", "not-a-cidr", "10.0.0.0/8", "n"):
            args: list[str] = []
            _collect_filter_flags(args)
            assert args == ["--allow", "10.0.0.0/8"]

    def test_empty_cidr_skips_allow(self):
        with _inputs("y", "", "n"):
            args: list[str] = []
            _collect_filter_flags(args)
            assert args == []

    def test_tcpwrap_default_name(self):
        with _inputs("n", "y", ""):
            args: list[str] = []
            _collect_filter_flags(args)
            assert args == ["--tcpwrap", "socat"]

    def test_ipv6_range_accepted(self):
        with _inputs("y", "2001:db8::/32", "n"):
            args: list[str] = []
            _collect_filter_flags(args)
            assert args == ["--allow", "2001:db8::/32"]


def test_menu_module_exposes_cancel_keywords():
    # Guard the contract the primitives rely on.
    assert menu._CANCEL_KEYWORDS >= {"q", "quit", "cancel", "back", "exit"}

# ==============================================================================
# FILE        : tests/unit/test_log_level.py
# ==============================================================================
# Synopsis    : Unit tests for console log-level selection
# Description : Verifies resolve_log_level() precedence (explicit --log-level
#               over --verbose over --quiet over the INFO default), its
#               case-insensitive acceptance and rejection of unknown names, and
#               that the CLI exposes --log-level and --quiet on the operational
#               subcommands without disturbing the pre-existing --verbose flag
#               or the status -v listener-info toggle.
# Version     : 1.0.2
# ==============================================================================

"""Unit tests for console log-level selection."""

from __future__ import annotations

import logging

import pytest

from socat_manager.cli import build_parser
from socat_manager.logging_setup import LOG_LEVEL_NAMES, resolve_log_level


class TestResolveLogLevel:
    """Precedence and validation for resolve_log_level()."""

    def test_default_is_info(self):
        assert resolve_log_level() == logging.INFO

    def test_verbose_maps_to_debug(self):
        assert resolve_log_level(verbose=True) == logging.DEBUG

    def test_quiet_maps_to_warning(self):
        assert resolve_log_level(quiet=True) == logging.WARNING

    def test_verbose_wins_over_quiet(self):
        # Surfacing more detail is the safer resolution when both are supplied.
        assert resolve_log_level(verbose=True, quiet=True) == logging.DEBUG

    def test_explicit_level_overrides_verbose(self):
        assert resolve_log_level(log_level="ERROR", verbose=True) == logging.ERROR

    def test_explicit_level_overrides_quiet(self):
        assert resolve_log_level(log_level="DEBUG", quiet=True) == logging.DEBUG

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("DEBUG", logging.DEBUG),
            ("INFO", logging.INFO),
            ("WARNING", logging.WARNING),
            ("ERROR", logging.ERROR),
            ("CRITICAL", logging.CRITICAL),
        ],
    )
    def test_each_named_level(self, name, expected):
        assert resolve_log_level(log_level=name) == expected

    def test_level_name_is_case_insensitive(self):
        assert resolve_log_level(log_level="warning") == logging.WARNING
        assert resolve_log_level(log_level="Debug") == logging.DEBUG

    def test_surrounding_whitespace_is_tolerated(self):
        assert resolve_log_level(log_level="  info  ") == logging.INFO

    def test_unknown_level_raises(self):
        with pytest.raises(ValueError):
            resolve_log_level(log_level="LOUD")

    def test_non_level_logging_attribute_is_rejected(self):
        # 'NOTSET' resolves to 0 but is not an offered level; a bare getattr
        # would have accepted it, so guard against that.
        with pytest.raises(ValueError):
            resolve_log_level(log_level="NOTSET")

    def test_exposed_level_names_match_logging(self):
        for name in LOG_LEVEL_NAMES:
            assert isinstance(getattr(logging, name), int)


class TestCliLoggingControls:
    """The parser exposes the controls on operational subcommands."""

    def _parse(self, argv):
        return build_parser().parse_args(argv)

    def test_log_level_accepted_on_listen(self):
        ns = self._parse(["listen", "--port", "8080", "--log-level", "WARNING"])
        assert ns.log_level == "WARNING"

    def test_log_level_is_uppercased_by_parser(self):
        ns = self._parse(["listen", "--port", "8080", "--log-level", "debug"])
        assert ns.log_level == "DEBUG"

    def test_quiet_flag_on_status(self):
        ns = self._parse(["status", "-q"])
        assert ns.quiet is True

    def test_log_level_on_stop(self):
        ns = self._parse(["stop", "--all", "--log-level", "ERROR"])
        assert ns.log_level == "ERROR"

    def test_verbose_still_works_and_defaults_are_clean(self):
        ns = self._parse(["listen", "--port", "8080", "-v"])
        assert ns.verbose is True
        assert ns.log_level is None
        assert ns.quiet is False

    def test_status_dash_v_remains_listener_info_not_a_level(self):
        # status -v predates this feature and means "show listener info"; it must
        # still set verbose and must not be repurposed into --log-level.
        ns = self._parse(["status", "-v"])
        assert ns.verbose is True
        assert ns.log_level is None

    def test_invalid_level_is_rejected_by_parser(self):
        with pytest.raises(SystemExit):
            self._parse(["listen", "--port", "8080", "--log-level", "LOUD"])

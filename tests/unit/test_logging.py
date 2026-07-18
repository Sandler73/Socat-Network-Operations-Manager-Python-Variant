# ==============================================================================
# FILE        : tests/unit/test_logging.py
# ==============================================================================
# Synopsis    : Unit tests for logging infrastructure
# Description : Tests structured logging setup, display helpers, session logging,
#               and convenience log functions.
# Version     : 1.0.2
# ==============================================================================

"""Unit tests for logging infrastructure."""

from __future__ import annotations

import logging

from socat_manager.logging_setup import (
    StructuredFormatter,
    _ensure_dirs,
    get_logger,
    log_critical,
    log_debug,
    log_error,
    log_info,
    log_session,
    log_success,
    log_warning,
    print_banner,
    print_kv,
    print_section,
    setup_logging,
)


class TestEnsureDirs:
    """Tests for _ensure_dirs()."""

    def test_creates_log_dir(self, paths):
        assert paths.log_dir.is_dir()

    def test_creates_session_dir(self, paths):
        assert paths.session_dir.is_dir()

    def test_creates_cert_dir(self, paths):
        assert paths.cert_dir.is_dir()

    def test_creates_conf_dir(self, paths):
        assert paths.conf_dir.is_dir()

    def test_idempotent(self, paths):
        """Calling _ensure_dirs multiple times should not error."""
        _ensure_dirs()
        _ensure_dirs()
        assert paths.log_dir.is_dir()


class TestSetupLogging:
    """Tests for setup_logging()."""

    def test_returns_logger(self):
        logger = setup_logging()
        assert isinstance(logger, logging.Logger)
        assert logger.name == "socat_manager"

    def test_has_handlers(self):
        logger = setup_logging()
        assert len(logger.handlers) > 0

    def test_idempotent(self):
        """Multiple calls should not add duplicate handlers."""
        l1 = setup_logging()
        count1 = len(l1.handlers)
        l2 = setup_logging()
        count2 = len(l2.handlers)
        assert count1 == count2


class TestGetLogger:
    """Tests for get_logger()."""

    def test_returns_logger(self):
        logger = get_logger()
        assert isinstance(logger, logging.Logger)

    def test_initializes_if_needed(self):
        logger = get_logger()
        assert len(logger.handlers) > 0


class TestStructuredFormatter:
    """Tests for StructuredFormatter."""

    def test_format_no_color(self):
        formatter = StructuredFormatter(use_color=False)
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="test message",
            args=None, exc_info=None,
        )
        record.component = "testcomp"
        result = formatter.format(record)
        assert "INFO" in result
        assert "testcomp" in result
        assert "test message" in result
        assert "corr:" in result

    def test_format_with_color(self):
        formatter = StructuredFormatter(use_color=True)
        record = logging.LogRecord(
            name="test", level=logging.ERROR,
            pathname="", lineno=0, msg="error msg",
            args=None, exc_info=None,
        )
        record.component = "test"
        result = formatter.format(record)
        assert "\033[" in result  # Contains ANSI escape
        assert "error msg" in result

    def test_default_component(self):
        formatter = StructuredFormatter(use_color=False)
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg="msg",
            args=None, exc_info=None,
        )
        # No component attribute set — should default to "main"
        result = formatter.format(record)
        assert "main" in result


class TestConvenienceLogFunctions:
    """Tests for log_debug, log_info, etc."""

    def test_log_debug_no_crash(self):
        log_debug("debug message", "test")

    def test_log_info_no_crash(self):
        log_info("info message", "test")

    def test_log_warning_no_crash(self):
        log_warning("warning message", "test")

    def test_log_error_no_crash(self):
        log_error("error message", "test")

    def test_log_critical_no_crash(self):
        log_critical("critical message", "test")

    def test_log_success_no_crash(self):
        log_success("success message", "test")


class TestSessionLogging:
    """Tests for log_session()."""

    def test_creates_session_log_file(self, paths):
        log_session("abcd1234", "INFO", "test session message")
        session_log = paths.log_dir / "session-abcd1234.log"
        assert session_log.is_file()

    def test_session_log_format(self, paths):
        log_session("abcd1234", "INFO", "test message")
        content = (paths.log_dir / "session-abcd1234.log").read_text()
        assert "[INFO" in content
        assert "session:abcd1234" in content
        assert "test message" in content

    def test_session_log_appends(self, paths):
        log_session("abcd1234", "INFO", "first")
        log_session("abcd1234", "WARNING", "second")
        content = (paths.log_dir / "session-abcd1234.log").read_text()
        assert "first" in content
        assert "second" in content
        lines = [line for line in content.strip().splitlines() if line.strip()]
        assert len(lines) == 2


class TestDisplayHelpers:
    """Tests for print_banner, print_section, print_kv."""

    def test_print_banner_no_crash(self):
        print_banner()

    def test_print_banner_with_subtitle(self):
        print_banner("Listener")

    def test_print_section_no_crash(self):
        print_section("Test Section")

    def test_print_kv_no_crash(self):
        print_kv("Key", "Value")

    def test_print_kv_with_int(self):
        print_kv("Port", 8080)

    def test_print_kv_with_bool(self):
        print_kv("Capture", True)

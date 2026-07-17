# ==============================================================================
# FILE        : tests/unit/test_main.py
# ==============================================================================
# Synopsis    : Unit tests for the entry point module
# Description : Tests dispatch_mode routing, check_socat dependency check,
#               signal handler installation, and main() control flow.
# Version     : 1.0.1
# ==============================================================================

"""Unit tests for the entry point module."""

from __future__ import annotations

import signal
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from socat_manager.__main__ import (
    _handle_sighup,
    _handle_sigint,
    _handle_sigterm,
    check_socat,
    dispatch_mode,
    initialize_logging,
    main,
)


class TestCheckSocat:
    """Tests for check_socat() dependency verification."""

    @patch("socat_manager.__main__.shutil.which", return_value=None)
    def test_exits_if_socat_missing(self, mock_which):
        with pytest.raises(SystemExit) as exc_info:
            check_socat()
        assert exc_info.value.code == 1

    @patch("subprocess.run")
    @patch("socat_manager.__main__.shutil.which", return_value="/usr/bin/socat")
    def test_passes_if_socat_found(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(
            stdout="socat by Gerhard Rieger\nsocat version 1.8.0.0\n"
        )
        # Should not raise
        check_socat()

    @patch("subprocess.run", side_effect=OSError)
    @patch("socat_manager.__main__.shutil.which", return_value="/usr/bin/socat")
    def test_handles_version_check_failure(self, mock_which, mock_run):
        # socat found but -V fails — should still pass
        check_socat()


class TestDispatchMode:
    """Tests for dispatch_mode() routing."""

    @patch("socat_manager.__main__.setup_logging")
    @patch("socat_manager.modes.listen.mode_listen")
    def test_dispatch_listen(self, mock_listen, mock_logging):
        args = Namespace(mode="listen", verbose=False)
        dispatch_mode(args)
        mock_listen.assert_called_once_with(args)

    @patch("socat_manager.__main__.setup_logging")
    @patch("socat_manager.modes.batch.mode_batch")
    def test_dispatch_batch(self, mock_batch, mock_logging):
        args = Namespace(mode="batch", verbose=False)
        dispatch_mode(args)
        mock_batch.assert_called_once_with(args)

    @patch("socat_manager.__main__.setup_logging")
    @patch("socat_manager.modes.forward.mode_forward")
    def test_dispatch_forward(self, mock_forward, mock_logging):
        args = Namespace(mode="forward", verbose=False)
        dispatch_mode(args)
        mock_forward.assert_called_once_with(args)

    @patch("socat_manager.__main__.setup_logging")
    @patch("socat_manager.modes.tunnel.mode_tunnel")
    def test_dispatch_tunnel(self, mock_tunnel, mock_logging):
        args = Namespace(mode="tunnel", verbose=False)
        dispatch_mode(args)
        mock_tunnel.assert_called_once_with(args)

    @patch("socat_manager.__main__.setup_logging")
    @patch("socat_manager.modes.redirect.mode_redirect")
    def test_dispatch_redirect(self, mock_redirect, mock_logging):
        args = Namespace(mode="redirect", verbose=False)
        dispatch_mode(args)
        mock_redirect.assert_called_once_with(args)

    @patch("socat_manager.__main__.setup_logging")
    @patch("socat_manager.modes.status.mode_status")
    def test_dispatch_status(self, mock_status, mock_logging):
        args = Namespace(mode="status", verbose=False)
        dispatch_mode(args)
        mock_status.assert_called_once_with(args)

    @patch("socat_manager.__main__.setup_logging")
    @patch("socat_manager.modes.stop.mode_stop")
    def test_dispatch_stop(self, mock_stop, mock_logging):
        args = Namespace(mode="stop", verbose=False)
        dispatch_mode(args)
        mock_stop.assert_called_once_with(args)

    @patch("socat_manager.__main__.setup_logging")
    def test_dispatch_unknown_exits(self, mock_logging):
        args = Namespace(mode="nonexistent", verbose=False)
        with pytest.raises(SystemExit) as exc_info:
            dispatch_mode(args)
        assert exc_info.value.code == 1

    @patch("socat_manager.modes.listen.mode_listen")
    def test_dispatch_does_not_configure_logging(self, mock_listen):
        """Dispatch is routing only; it does not configure logging.

        Logging is configured once per invocation by initialize_logging(),
        which runs before any dispatch. Dispatch must not repeat that work.
        """
        with patch("socat_manager.__main__.setup_logging") as mock_setup:
            dispatch_mode(Namespace(mode="listen", verbose=True))

        mock_setup.assert_not_called()
        mock_listen.assert_called_once()


class TestInitializeLogging:
    """Tests for initialize_logging(), the single logging initialization site."""

    @patch("socat_manager.__main__.setup_logging")
    def test_verbose_sets_flag(self, mock_setup):
        """The verbose flag is applied before the logger is configured."""
        import socat_manager.logging_setup as ls
        original = ls.verbose_mode
        try:
            initialize_logging(Namespace(mode="listen", verbose=True))
            assert ls.verbose_mode is True
            mock_setup.assert_called_once()
        finally:
            ls.verbose_mode = original

    @patch("socat_manager.__main__.setup_logging")
    def test_absent_verbose_leaves_flag_untouched(self, mock_setup):
        """An invocation without a verbose flag does not enable verbose mode."""
        import socat_manager.logging_setup as ls
        original = ls.verbose_mode
        try:
            ls.verbose_mode = False
            initialize_logging(Namespace(mode="status"))
            assert ls.verbose_mode is False
            mock_setup.assert_called_once()
        finally:
            ls.verbose_mode = original

    @patch("socat_manager.__main__.setup_logging")
    def test_logging_configured_once_per_invocation(self, mock_setup):
        """main() configures logging exactly once, covering every path."""
        with patch("socat_manager.__main__.dispatch_mode"), \
             patch("socat_manager.__main__.check_socat"), \
             patch("socat_manager.__main__.migrate_legacy_sessions", create=True), \
             patch("sys.argv", ["socat-manager", "status"]):
            main()

        assert mock_setup.call_count == 1


class TestSignalHandlers:
    """Tests for signal handler functions."""

    def test_sigterm_handler_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            _handle_sigterm(signal.SIGTERM, None)
        assert exc_info.value.code == 0

    def test_sigint_handler_exits_130(self):
        with pytest.raises(SystemExit) as exc_info:
            _handle_sigint(signal.SIGINT, None)
        assert exc_info.value.code == 130

    def test_sighup_handler_exits_0(self):
        with pytest.raises(SystemExit) as exc_info:
            _handle_sighup(signal.SIGHUP, None)
        assert exc_info.value.code == 0


class TestMain:
    """Tests for main() entry point."""

    @patch("socat_manager.__main__.build_parser")
    @patch("socat_manager.menu.interactive_menu")
    def test_no_args_launches_menu(self, mock_menu, mock_build):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = Namespace(mode=None)
        mock_build.return_value = mock_parser
        main()
        mock_menu.assert_called_once()

    @patch("socat_manager.__main__.build_parser")
    @patch("socat_manager.menu.interactive_menu")
    def test_menu_mode_launches_menu(self, mock_menu, mock_build):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = Namespace(mode="menu")
        mock_build.return_value = mock_parser
        main()
        mock_menu.assert_called_once()

    @patch("socat_manager.__main__.dispatch_mode")
    @patch("socat_manager.__main__.check_socat")
    @patch("socat_manager.__main__.setup_logging")
    @patch("socat_manager.__main__.build_parser")
    def test_status_mode_skips_socat_check(self, mock_build, mock_logging, mock_check, mock_dispatch):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = Namespace(mode="status", verbose=False)
        mock_build.return_value = mock_parser
        main()
        mock_check.assert_not_called()
        mock_dispatch.assert_called_once()

    @patch("socat_manager.__main__.dispatch_mode")
    @patch("socat_manager.__main__.check_socat")
    @patch("socat_manager.__main__.setup_logging")
    @patch("socat_manager.__main__.build_parser")
    def test_stop_mode_skips_socat_check(self, mock_build, mock_logging, mock_check, mock_dispatch):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = Namespace(mode="stop", verbose=False)
        mock_build.return_value = mock_parser
        main()
        mock_check.assert_not_called()

    @patch("socat_manager.__main__.dispatch_mode")
    @patch("socat_manager.__main__.check_socat")
    @patch("socat_manager.__main__.setup_logging")
    @patch("socat_manager.__main__.build_parser")
    def test_listen_mode_checks_socat(self, mock_build, mock_logging, mock_check, mock_dispatch):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = Namespace(mode="listen", verbose=False)
        mock_build.return_value = mock_parser
        main()
        mock_check.assert_called_once()

    @patch("socat_manager.__main__.build_parser")
    def test_help_mode_prints_help(self, mock_build):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = Namespace(mode="help")
        mock_build.return_value = mock_parser
        main()
        mock_parser.print_help.assert_called_once()

    @patch("socat_manager.__main__.build_parser")
    def test_version_mode_prints_version(self, mock_build, capsys):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = Namespace(mode="version")
        mock_build.return_value = mock_parser
        main()
        captured = capsys.readouterr()
        assert "socat-manager v" in captured.out

    @patch("socat_manager.__main__.dispatch_mode")
    @patch("socat_manager.__main__.check_socat")
    @patch("socat_manager.__main__.setup_logging")
    @patch("socat_manager.__main__.build_parser")
    def test_help_mode_skips_socat_check(self, mock_build, mock_logging, mock_check, mock_dispatch):
        mock_parser = MagicMock()
        mock_parser.parse_args.return_value = Namespace(mode="help")
        mock_build.return_value = mock_parser
        main()
        mock_check.assert_not_called()
        mock_dispatch.assert_not_called()

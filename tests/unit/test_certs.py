# ==============================================================================
# FILE        : tests/unit/test_certs.py
# ==============================================================================
# Synopsis    : Unit tests for TLS certificate generation
# Description : Tests generate_self_signed_cert() with mocked openssl subprocess.
# Version     : 1.0.1
# ==============================================================================

"""Unit tests for TLS certificate generation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from socat_manager.certs import generate_self_signed_cert


class TestGenerateSelfSignedCert:
    """Tests for generate_self_signed_cert()."""

    @patch("socat_manager.certs.subprocess.run")
    def test_returns_cert_and_key_paths(self, mock_run, paths):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        # Create dummy files that the mock would have created
        cert_path, key_path = generate_self_signed_cert("localhost")
        assert cert_path.endswith(".pem")
        assert key_path.endswith(".pem")
        assert "cert" in cert_path
        assert "key" in key_path

    @patch("socat_manager.certs.subprocess.run")
    def test_calls_openssl_with_correct_args(self, mock_run, paths):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        generate_self_signed_cert("myhost.local")

        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert cmd[0] == "openssl"
        assert "req" in cmd
        assert "-x509" in cmd
        assert "-newkey" in cmd
        assert "rsa:2048" in cmd
        assert "-nodes" in cmd
        assert "-days" in cmd
        assert "365" in cmd
        assert "/CN=myhost.local" in cmd

    @patch("socat_manager.certs.subprocess.run")
    def test_default_cn_localhost(self, mock_run, paths):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        generate_self_signed_cert()
        cmd = mock_run.call_args.args[0]
        assert "/CN=localhost" in cmd

    @patch("socat_manager.certs.subprocess.run", side_effect=FileNotFoundError)
    def test_raises_if_openssl_not_found(self, mock_run, paths):
        with pytest.raises(RuntimeError, match="openssl not found"):
            generate_self_signed_cert()

    @patch("socat_manager.certs.subprocess.run")
    def test_raises_on_nonzero_exit(self, mock_run, paths):
        mock_run.return_value = MagicMock(returncode=1, stderr="error generating cert")
        with pytest.raises(RuntimeError, match="Certificate generation failed"):
            generate_self_signed_cert()

    @patch("socat_manager.certs.subprocess.run")
    def test_raises_on_timeout(self, mock_run, paths):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="openssl", timeout=30)
        with pytest.raises(RuntimeError, match="timed out"):
            generate_self_signed_cert()

    @patch("socat_manager.certs.subprocess.run")
    def test_key_path_in_cert_dir(self, mock_run, paths):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        cert_path, key_path = generate_self_signed_cert()
        assert str(paths.cert_dir) in cert_path
        assert str(paths.cert_dir) in key_path

    @patch("socat_manager.certs.subprocess.run")
    def test_never_uses_shell(self, mock_run, paths):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        generate_self_signed_cert()
        call_kwargs = mock_run.call_args
        # shell should not be in kwargs or must be False
        assert call_kwargs.kwargs.get("shell", False) is False

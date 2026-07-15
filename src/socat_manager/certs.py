# ==============================================================================
# MODULE      : socat_manager/certs.py
# ==============================================================================
# Synopsis    : TLS certificate generation for tunnel mode
# Description : Generates self-signed certificates and private keys for use
#               with socat's OPENSSL-LISTEN address type. Certificates are
#               placed in the certs/ directory with restrictive permissions
#               on the private key (0o600).
#
#               Bash equivalent: generate_self_signed_cert() — lines 1642-1700
#
# Notes       : - Uses subprocess.Popen with argument lists (never shell=True)
#               - Private key permissions set atomically via os.open()
#               - Certificate validity: 365 days (matches bash)
#               - Key size: 2048 bits RSA
#               - Default CN: localhost
#               - No external Python dependencies (calls openssl binary)
#
# Version     : 0.9.0
# ==============================================================================

"""TLS certificate generation for tunnel mode.

Generates self-signed certificates via the openssl command-line tool
for use with socat OPENSSL-LISTEN tunnels.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from socat_manager.config import EXEC_TIMESTAMP
from socat_manager.logging_setup import (
    _ensure_dirs,
    get_paths,
    log_debug,
    log_error,
    log_info,
)

# ==============================================================================
# CERTIFICATE GENERATION
# Bash equivalent: generate_self_signed_cert() — lines 1642-1700
# ==============================================================================

def generate_self_signed_cert(cn: str = "localhost") -> tuple[str, str]:
    """Generate a self-signed certificate and private key for TLS tunnels.

    Creates a 2048-bit RSA key pair with a self-signed X.509 certificate
    valid for 365 days. Files are written to the certs/ directory.

    Private key permissions are set to 0o600 (owner read/write only)
    via os.open() to avoid race conditions between create and chmod.

    Args:
        cn: Common Name for the certificate (default: "localhost").

    Returns:
        Tuple of (cert_path, key_path) as absolute path strings.

    Raises:
        RuntimeError: If openssl is not found or certificate generation fails.
    """
    _ensure_dirs()
    paths = get_paths()

    # Generate filenames with timestamp for uniqueness
    cert_path: Path = paths.cert_dir / f"socat-cert-{EXEC_TIMESTAMP}.pem"
    key_path: Path = paths.cert_dir / f"socat-key-{EXEC_TIMESTAMP}.pem"

    log_info(f"Generating self-signed certificate (CN={cn})...", "certs")

    # Build the openssl command
    # Matches bash: openssl req -x509 -newkey rsa:2048 -keyout ... -out ...
    #               -days 365 -nodes -subj "/CN=..."
    cmd: list[str] = [
        "openssl", "req",
        "-x509",
        "-newkey", "rsa:2048",
        "-keyout", str(key_path),
        "-out", str(cert_path),
        "-days", "365",
        "-nodes",                    # No passphrase on private key
        "-subj", f"/CN={cn}",
    ]

    log_debug(f"Certificate command: {' '.join(cmd)}", "certs")

    # Set restrictive umask so openssl creates the key with 0o600 from the start.
    # This eliminates the TOCTOU window where the key exists with permissive perms
    # before chmod. Save and restore the original umask afterward.
    original_umask: int = os.umask(0o077)
    try:
        try:
            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            msg: str = "openssl not found in PATH — cannot generate certificates"
            log_error(msg, "certs")
            raise RuntimeError(msg)
        except subprocess.TimeoutExpired:
            msg = "Certificate generation timed out after 30 seconds"
            log_error(msg, "certs")
            raise RuntimeError(msg)
    finally:
        os.umask(original_umask)

    if result.returncode != 0:
        msg = f"Certificate generation failed: {result.stderr.strip()}"
        log_error(msg, "certs")
        raise RuntimeError(msg)

    # Set restrictive permissions on private key (0o600)
    try:
        os.chmod(str(key_path), 0o600)
    except OSError as exc:
        log_error(f"Failed to set key permissions: {exc}", "certs")
        # Continue — key is usable even without perfect permissions

    log_info(f"Certificate generated: {cert_path}", "certs")
    log_info(f"Private key generated: {key_path}", "certs")

    return str(cert_path), str(key_path)

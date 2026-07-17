#!/usr/bin/env bash
# ==============================================================================
# FILE        : generate-example-cert.sh
# ==============================================================================
# Synopsis    : Generate the labeled throwaway example certificate and key.
# Description : Produces a self-signed certificate/key pair using the same
#               parameters as the built-in generator (RSA 2048, SHA-256,
#               365-day validity, unencrypted key), extended with the Subject
#               Alternative Names from example-san.cnf. The private key is
#               created under a restrictive umask so it lands with 0o600
#               permissions and never exists world-readable, mirroring the
#               time-of-check/time-of-use protection in certs.py.
#
#               Output:
#                 example-do-not-use.crt   self-signed certificate
#                 example-do-not-use.key   unencrypted private key (0o600)
#
#               Run from within the certs/ directory:
#                 ./generate-example-cert.sh
# Notes       : The generated pair is a DISPOSABLE EXAMPLE. It is self-signed,
#               its private key is committed to the repository, and its subject
#               is deliberately marked as an example. It must NEVER be used to
#               protect real traffic. Generate a fresh pair per deployment with
#               the built-in tunnel-mode generator or with openssl directly.
# Execution   : ./generate-example-cert.sh
# Version     : 1.0.1
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${SCRIPT_DIR}/example-san.cnf"
CERT_OUT="${SCRIPT_DIR}/example-do-not-use.crt"
KEY_OUT="${SCRIPT_DIR}/example-do-not-use.key"
SUBJECT="/CN=example.invalid/O=Socat Network Operations Manager Example (DO NOT USE)"

if ! command -v openssl >/dev/null 2>&1; then
    echo "error: openssl not found in PATH" >&2
    exit 1
fi

if [ ! -f "${CONFIG}" ]; then
    echo "error: SAN config not found: ${CONFIG}" >&2
    exit 1
fi

echo "Generating disposable example certificate (DO NOT USE for real traffic)..."

# Restrictive umask so the private key is created 0o600 from the start,
# eliminating the window where it would exist with permissive permissions.
old_umask="$(umask)"
umask 0077
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
    -keyout "${KEY_OUT}" \
    -out "${CERT_OUT}" \
    -subj "${SUBJECT}" \
    -config "${CONFIG}" \
    -extensions v3_req
umask "${old_umask}"

chmod 0600 "${KEY_OUT}"

echo "  Certificate: ${CERT_OUT}"
echo "  Private key: ${KEY_OUT} (0600)"
echo "Done. Remember: this pair is an example only and must not protect real traffic."

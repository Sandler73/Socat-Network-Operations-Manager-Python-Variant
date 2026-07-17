# Certificates

This directory holds TLS certificates for `tunnel` mode. In normal operation it
is populated at runtime, and those runtime certificates are never committed. The
files checked in here are examples and helpers only.

## What lives here

| File | Committed | Purpose |
|------|-----------|---------|
| `README.md` | yes | This file. |
| `example-san.cnf` | yes | OpenSSL configuration adding Subject Alternative Names. |
| `generate-example-cert.sh` | yes | Produces the disposable example pair below. |
| `example-do-not-use.crt` | yes | Disposable self-signed example certificate. |
| `example-do-not-use.key` | yes | Disposable example private key — **never use for real traffic**. |
| `*.crt`, `*.key`, `*.pem` (any other) | no | Runtime-generated certificates, ignored by `.gitignore`. |

## The example pair is disposable

`example-do-not-use.crt` and `example-do-not-use.key` exist so the documentation
and tests have a certificate to point at. The pair is self-signed, its private
key is committed in the clear, and its subject is deliberately marked
`example.invalid` / `DO NOT USE`. It must never protect real traffic. Treat it
as public.

## Generating a real certificate

### Built-in (recommended)

`tunnel` mode generates a certificate automatically when one is not supplied. The
generator produces a 2048-bit RSA key and a 365-day self-signed certificate with
an unencrypted key at `0600` permissions:

```bash
socat-manager tunnel --lport 8443 --rhost 10.0.0.5 --rport 443
```

### Manual, with Subject Alternative Names

Modern TLS clients validate the hostname against the certificate's SAN list
rather than its Common Name. Use `example-san.cnf` as a starting point — edit the
`[alt_names]` section to the names and addresses the endpoint will be reached by
— and generate the pair:

```bash
./generate-example-cert.sh          # writes the example-do-not-use.* pair
```

or invoke openssl directly for your own output names:

```bash
umask 0077
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
  -keyout server.key -out server.crt \
  -config example-san.cnf -extensions v3_req
chmod 0600 server.key
```

## Handling private keys

- Keep private keys at `0600` (owner read/write only). The built-in generator and
  the example script both set this from the start under a restrictive umask.
- Never commit a real private key. `.gitignore` ignores `certs/*.key`,
  `certs/*.pem`, and `certs/*.crt`; only the explicitly named example files are
  re-included.
- Generate a fresh key per deployment. Do not reuse the example pair, and do not
  reuse one deployment's key in another.
- For anything exposed to an untrusted network, use a certificate issued by a
  trusted certificate authority rather than a self-signed one.

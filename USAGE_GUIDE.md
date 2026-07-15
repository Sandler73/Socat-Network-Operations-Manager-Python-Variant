# Socat Network Operations Manager — Usage Guide

**Python Variant v0.9.0**

This guide provides complete instructions for installing, configuring, and executing
`socat-manager` across three deployment models: standalone script execution, pip
installation, and isolated virtual environment setup. It covers all operational modes,
protocol configurations, traffic capture capabilities, session lifecycle management,
watchdog auto-restart, and operational scenarios with step-by-step examples.

---

## Table of Contents

- [1. Installation](#1-installation)
  - [1.1 Prerequisites](#11-prerequisites)
  - [1.2 Installing Dependencies](#12-installing-dependencies)
  - [1.3 Getting the Code](#13-getting-the-code)
  - [1.4 Verifying the Installation](#14-verifying-the-installation)
- [2. Execution Methods](#2-execution-methods)
  - [2.1 Standalone Script Execution](#21-standalone-script-execution)
  - [2.2 System-Wide pip Installation](#22-system-wide-pip-installation)
  - [2.3 Isolated Virtual Environment Setup](#23-isolated-virtual-environment-setup)
- [3. Mode Reference](#3-mode-reference)
  - [3.1 listen — Single Port Listener](#31-listen--single-port-listener)
  - [3.2 batch — Multi-Port Listeners](#32-batch--multi-port-listeners)
  - [3.3 forward — Port Forwarding](#33-forward--port-forwarding)
  - [3.4 tunnel — Encrypted TLS Tunnel](#34-tunnel--encrypted-tls-tunnel)
  - [3.5 redirect — Traffic Redirection](#35-redirect--traffic-redirection)
  - [3.6 status — Session Status](#36-status--session-status)
  - [3.7 stop — Session Shutdown](#37-stop--session-shutdown)
- [4. Protocol Configuration](#4-protocol-configuration)
  - [4.1 Individual Protocol Selection (--proto)](#41-individual-protocol-selection---proto)
  - [4.2 Dual-Stack Operation (--dual-stack)](#42-dual-stack-operation---dual-stack)
  - [4.3 Protocol Interaction with Modes](#43-protocol-interaction-with-modes)
- [5. Traffic Capture](#5-traffic-capture)
  - [5.1 Enabling Capture](#51-enabling-capture)
  - [5.2 Capture Log Format](#52-capture-log-format)
  - [5.3 Capture with Dual-Stack](#53-capture-with-dual-stack)
  - [5.4 Analyzing Capture Logs](#54-analyzing-capture-logs)
- [6. Session Lifecycle](#6-session-lifecycle)
  - [6.1 Launch and Registration](#61-launch-and-registration)
  - [6.2 Monitoring](#62-monitoring)
  - [6.3 Stopping Sessions](#63-stopping-sessions)
  - [6.4 Cleanup and Maintenance](#64-cleanup-and-maintenance)
- [7. Watchdog Auto-Restart](#7-watchdog-auto-restart)
- [8. Interactive Menu](#8-interactive-menu)
- [9. Operational Scenarios](#9-operational-scenarios)
  - [9.1 Honeypot Deployment](#91-honeypot-deployment)
  - [9.2 Traffic Interception and Analysis](#92-traffic-interception-and-analysis)
  - [9.3 Encrypted Relay](#93-encrypted-relay)
  - [9.4 DNS Proxy](#94-dns-proxy)
  - [9.5 Multi-Service Lab Environment](#95-multi-service-lab-environment)
- [10. Log Management](#10-log-management)
- [11. Troubleshooting](#11-troubleshooting)

---

## 1. Installation

### 1.1 Prerequisites

#### Required Packages

| Package | Purpose | Install Command |
|---------|---------|----------------|
| **Python 3.12+** | Framework runtime | Pre-installed on Ubuntu 24.04+; `sudo apt-get install python3` |
| **socat** | Core network operations | `sudo apt-get install -y socat` |

#### Optional Packages

| Package | Purpose | Install Command |
|---------|---------|----------------|
| **openssl** | TLS certificate generation (tunnel mode) | `sudo apt-get install -y openssl` |
| **iproute2** (ss) | Port status checking and session verification | `sudo apt-get install -y iproute2` |
| **psmisc** (pstree) | Process tree display in session detail | `sudo apt-get install -y psmisc` |
| **util-linux** (flock) | Advisory file locking | Pre-installed on most Linux |

#### Full Installation (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y socat openssl iproute2 psmisc
```

#### Full Installation (Rocky/Alma/RHEL)

```bash
sudo dnf install -y socat openssl iproute psmisc
```

#### Full Installation (Arch Linux)

```bash
sudo pacman -S socat openssl iproute2 psmisc
```

### 1.2 Installing Dependencies

Verify Python version:

```bash
python3 --version
# Must show 3.12 or higher
```

If Python 3.12+ is not available, install it:

```bash
# Ubuntu/Debian:
sudo apt-get install -y python3.12

# Or use pyenv for version management:
curl https://pyenv.run | bash
pyenv install 3.12
pyenv global 3.12
```

### 1.3 Getting the Code

```bash
git clone https://github.com/Sandler73/Socat-Network-Operations-Manager.git
cd Socat-Network-Operations-Manager
```

### 1.4 Verifying the Installation

**Quick verification:**

```bash
python3 socat-manager.py help
python3 socat-manager.py version
```

**Full dependency check:**

```bash
make check-deps
```

This displays the status of every required and optional dependency with paths and versions.

---

## 2. Execution Methods

### 2.1 Standalone Script Execution

The simplest method — no installation, no virtual environment, no system modification:

```bash
python3 socat-manager.py                          # Interactive menu
python3 socat-manager.py listen --port 8080        # CLI mode
python3 socat-manager.py help                      # Full help
python3 socat-manager.py version                   # Version info
```

The standalone runner (`socat-manager.py`) automatically:
- Adds `src/` to the Python path
- Sets `SOCAT_MANAGER_BASE` to the script directory
- Delegates to `socat_manager.__main__:main()`

**Advantages**: Zero setup, works immediately after `git clone`, no system modification.
**Disadvantages**: Must use `python3 socat-manager.py` instead of `socat-manager`.

### 2.2 System-Wide pip Installation

Install the `socat-manager` command in your PATH:

```bash
pip install -e .
# Or with --break-system-packages on Ubuntu 24.04+:
pip install --break-system-packages -e .
```

After installation:

```bash
socat-manager                    # Interactive menu
socat-manager listen --port 8080 # CLI mode
socat-manager help               # Full help
socat-manager version            # Version info
```

**Uninstall:**

```bash
pip uninstall socat-manager
# Or: make uninstall
```

**Advantages**: `socat-manager` command available system-wide, tab completion.
**Disadvantages**: Modifies system Python packages.

### 2.3 Isolated Virtual Environment Setup

The recommended method for development:

```bash
make venv
source socat-manager-venv/bin/activate
socat-manager --help
```

Or manually:

```bash
python3 -m venv socat-manager-venv
source socat-manager-venv/bin/activate
pip install -e .
pip install pytest pytest-cov ruff  # Development dependencies
socat-manager --help
```

**Custom venv location:**

```bash
make venv VENV_DIR=/opt/engagements/alpha/env
source /opt/engagements/alpha/env/bin/activate
```

**Deactivate:**

```bash
deactivate
```

**Advantages**: Isolated from system Python, reproducible, includes dev dependencies.
**Disadvantages**: Requires activation before use.

---

## 3. Mode Reference

### 3.1 listen — Single Port Listener

Start a single TCP or UDP listener that captures incoming data to a log file. The listener uses socat's `fork` option to handle concurrent connections — each client gets its own forked handler process. Data flows unidirectionally from the network to the log file (socat `-u` flag).

**Synopsis:**

```
socat-manager listen --port <PORT>
                     [--proto <PROTO>] [--bind <ADDR>] [--name <n>]
                     [--logfile <PATH>] [--socat-opts <OPTS>]
                     [--capture] [--watchdog] [--max-restarts <N>] [--backoff <N>]
                     [--dual-stack] [-v]
```

**Examples:**

```bash
# Basic TCP listener on port 8080
socat-manager listen --port 8080

# UDP-only listener
socat-manager listen --port 5353 --proto udp4

# TCP + UDP simultaneously (dual-stack)
socat-manager listen --port 8080 --dual-stack

# With traffic capture (verbose hex dump)
socat-manager listen --port 8080 --capture

# Bind to a specific interface
socat-manager listen --port 8080 --bind 192.168.1.100

# With watchdog auto-restart (custom parameters)
socat-manager listen --port 8080 --watchdog --max-restarts 20 --backoff 2

# With extra socat address options
socat-manager listen --port 8080 --socat-opts "nodelay"

# Full combination: dual-stack, capture, watchdog, custom name
socat-manager listen --port 8080 --dual-stack --capture --watchdog --name my-listener
```

**Options:**

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `-p, --port <PORT>` | int | Yes | — | Port number (1-65535). Ports below 1024 require root. |
| `--proto <PROTO>` | str | No | `tcp4` | Protocol: tcp, tcp4, tcp6, udp, udp4, udp6. Generic `tcp`/`udp` normalize to `tcp4`/`udp4`. |
| `--bind <ADDR>` | str | No | (all interfaces) | Bind to specific IP address. Validated as hostname/IPv4/IPv6. Prepended to socat options as `bind=<ADDR>`. An IPv6 literal is bracketed automatically (`bind=[2001:db8::1]`); supply the literal unbracketed on the command line. |
| `--name <n>` | str | No | `{proto}-{port}` | Custom session name. Auto-generated as e.g. `tcp4-8080` if omitted. |
| `--logfile <PATH>` | str | No | `logs/listener-{proto}-{port}.log` | Custom data log file path. Validated for path traversal and shell metacharacters before reaching socat. |
| `--socat-opts <OPTS>` | str | No | — | Extra socat address options. Appended to listener address. Must match whitelist `[a-zA-Z0-9=,.:/_-]`. |
| `--capture` | flag | No | false | Enable traffic capture. Adds socat `-v` flag. Creates capture log at `logs/capture-{proto}-{port}-{timestamp}.log` with 0o600 permissions. |
| `--watchdog` | flag | No | false | Enable auto-restart monitoring via daemon thread. |
| `--max-restarts <N>` | int | No | 10 | Maximum watchdog restart attempts before giving up. |
| `--backoff <N>` | int | No | 1 | Initial watchdog backoff delay in seconds. Doubles each restart (1→2→4→8→16→32→60→60...). |
| `--dual-stack` | flag | No | false | Also start listener on alternate protocol (tcp4↔udp4, tcp6↔udp6). Each gets independent session ID. |
| `-v, --verbose` | flag | No | false | Enable DEBUG-level logging. |

**Generated socat commands** (actual output from command builders):

```bash
# TCP4 listener — note backlog=128,keepalive (TCP-specific options)
socat -u TCP4-LISTEN:8080,reuseaddr,fork,backlog=128,keepalive OPEN:logs/listener-tcp4-8080.log,creat,append

# UDP4 listener — simpler options (no backlog/keepalive for UDP)
socat -u UDP4-LISTEN:5353,reuseaddr,fork OPEN:logs/listener-udp4-5353.log,creat,append

# With capture — adds -v before -u
socat -v -u TCP4-LISTEN:8080,reuseaddr,fork,backlog=128,keepalive OPEN:logs/listener-tcp4-8080.log,creat,append

# With bind and extra opts — bind prepended to user opts
socat -u TCP4-LISTEN:8080,reuseaddr,fork,backlog=128,keepalive,bind=10.0.0.1,nodelay OPEN:logs/listener-tcp4-8080.log,creat,append
```

**Behavioral notes:**

- The `-u` flag makes the listener unidirectional: data flows from the network (left/listener) to the file (right). No data flows back to the client.
- TCP listeners include `backlog=128,keepalive` in the socat address options. UDP listeners include only `reuseaddr,fork` (backlog and keepalive are TCP-only concepts).
- Port availability is checked via `ss` before launching. If the port is already in use on the specified protocol, the command exits with an error.
- The stability check (a 0.3s delay followed by a liveness check on the retained child handle) verifies the process survived startup. If it died immediately (e.g., port binding failure), the launch is reported as failed.
- When `--dual-stack` is used, the alternate protocol listener is independently launched. If it fails (port busy), a warning is logged but the primary listener remains active.
- The data log file receives raw incoming data from clients. The capture log (if enabled) receives socat's `-v` hex dump output from stderr.

### 3.2 batch — Multi-Port Listeners

Launch listeners on multiple ports simultaneously from a comma-separated list, a port range, or a config file. Each port receives its own independent session with a unique session ID, log file, and lifecycle.

**Synopsis:**

```
socat-manager batch --ports <LIST> | --range <START-END> | --file <PATH>
                    [--proto <PROTO>] [--socat-opts <OPTS>]
                    [--capture] [--watchdog] [--max-restarts <N>] [--backoff <N>]
                    [--dual-stack] [-v]
```

**Examples:**

```bash
# Port list
socat-manager batch --ports "21,22,23,25,80,443"

# Port range
socat-manager batch --range 8000-8010

# Port range with dual-stack and capture
socat-manager batch --range 8000-8005 --dual-stack --capture

# UDP-only batch
socat-manager batch --ports "5353,5354,5355" --proto udp4

# From config file with watchdog
socat-manager batch --file conf/ports.conf --watchdog
```

**Config file format** (`conf/ports.conf`):

```
# One port per line. Comments and blank lines are ignored.
8080
8443
9090
# 9999  ← commented out, skipped
```

**Options:**

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `--ports <LIST>` | str | One of three | — | Comma-separated port list. Semicolons are also accepted. Each port validated individually. |
| `--range <START-END>` | str | One of three | — | Port range (e.g., `8000-8010`). Maximum span of 1000 ports. START must be ≤ END. |
| `--file <FILE>` | str | One of three | — | Config file path. One port per line. Lines starting with `#` are comments. Empty lines skipped. Path validated for existence, readability, and no shell metacharacters. |
| `--proto <PROTO>` | str | No | `tcp4` | Protocol for all listeners. |
| `--socat-opts <OPTS>` | str | No | — | Extra socat address options for all listeners. |
| `--capture` | flag | No | false | Enable traffic capture for all listeners. |
| `--watchdog` | flag | No | false | Enable auto-restart for all listeners. |
| `--max-restarts <N>` | int | No | 10 | Max restart attempts per listener. |
| `--backoff <N>` | int | No | 1 | Initial backoff seconds per listener. |
| `--dual-stack` | flag | No | false | Start both TCP and UDP per port. |
| `-v, --verbose` | flag | No | false | Debug logging. |

**Behavioral notes:**

- Exactly one of `--ports`, `--range`, or `--file` must be provided.
- Ports are deduplicated and sorted before launching.
- Unavailable ports are skipped with a warning (not a fatal error). The remaining ports are launched.
- Each port gets a session name of `{proto}-{port}` (e.g., `tcp4-8080`).
- The mode string stored in session files is `batch-listen` (not `listen`), distinguishing batch-launched sessions from single-listen sessions.
- A summary is printed after all launches: total launched, skipped, failed.
- With `--dual-stack`, each port launches two sessions. 10 ports × dual-stack = 20 sessions.

### 3.3 forward — Port Forwarding

Bidirectional traffic relay between a local listener and a remote target. Data flows in both directions — this is a full-duplex proxy. No `-u` flag (unlike listen mode).

**Synopsis:**

```
socat-manager forward --lport <PORT> --rhost <HOST> --rport <PORT>
                      [--proto <PROTO>] [--remote-proto <PROTO>] [--name <n>]
                      [--capture] [--watchdog] [--max-restarts <N>] [--backoff <N>]
                      [--dual-stack] [-v]
```

**Examples:**

```bash
# TCP forwarder
socat-manager forward --lport 8080 --rhost 192.168.1.10 --rport 80

# UDP forwarder (DNS relay)
socat-manager forward --lport 5353 --rhost 10.0.0.1 --rport 53 --proto udp4

# Dual-stack forwarder
socat-manager forward --lport 8080 --rhost 192.168.1.10 --rport 80 --dual-stack

# Cross-protocol (TCP listen → UDP remote)
socat-manager forward --lport 8080 --rhost 10.0.0.5 --rport 53 --proto tcp4 --remote-proto udp4

# With traffic capture
socat-manager forward --lport 8080 --rhost 192.168.1.10 --rport 80 --capture

# Forward to an IPv6 remote target
socat-manager forward --lport 8080 --rhost 2001:db8::1 --rport 80 --proto tcp6
```

**Options:**

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `--lport <PORT>` | int | Yes | — | Local port to listen on. |
| `--rhost <HOST>` | str | Yes | — | Remote host to forward to. Validated as IPv4/IPv6/hostname with shell metacharacter rejection. An IPv6 literal is bracketed automatically in the socat address (`2001:db8::1` becomes `TCP6:[2001:db8::1]:<PORT>`); supply the literal unbracketed on the command line. |
| `--rport <PORT>` | int | Yes | — | Remote port to forward to. |
| `--proto <PROTO>` | str | No | `tcp4` | Listen protocol. |
| `--remote-proto <PROTO>` | str | No | (same as `--proto`) | Remote connection protocol. Enables cross-protocol forwarding (e.g., TCP listen → UDP remote). |
| `--name <n>` | str | No | `fwd-{lport}-{rhost}-{rport}` | Custom session name. |
| `--capture` | flag | No | false | Enable traffic capture. Capture log: `logs/capture-{proto}-{lport}-{rhost}-{rport}-{timestamp}.log`. |
| `--watchdog` | flag | No | false | Enable auto-restart. |
| `--max-restarts <N>` | int | No | 10 | Max restart attempts. |
| `--backoff <N>` | int | No | 1 | Initial backoff seconds. |
| `--dual-stack` | flag | No | false | Also start forwarder on alternate protocol. |
| `-v, --verbose` | flag | No | false | Debug logging. |

**Generated socat commands** (actual output):

```bash
# TCP4 forwarder — note: no -u flag (bidirectional)
socat TCP4-LISTEN:8080,reuseaddr,fork,backlog=128,keepalive TCP4:10.0.0.5:80

# UDP4 forwarder — no backlog option
socat UDP4-LISTEN:5353,reuseaddr,fork UDP4:8.8.8.8:53

# Cross-protocol: TCP listen side, UDP connect side
socat TCP4-LISTEN:8080,reuseaddr,fork,backlog=128,keepalive UDP4:10.0.0.1:53

# With capture
socat -v TCP4-LISTEN:8080,reuseaddr,fork,backlog=128,keepalive TCP4:10.0.0.5:80
```

**Behavioral notes:**

- Forward mode does NOT include the `-u` flag — traffic flows bidirectionally.
- TCP listeners include `backlog=128` (no `keepalive` — that's listen-mode only). UDP listeners include only `reuseaddr,fork`.
- The `--remote-proto` flag allows cross-protocol forwarding. If omitted, the remote protocol matches the listen protocol.
- Forward mode does NOT have `--logfile`, `--socat-opts`, or `--bind` flags (unlike listen mode).

### 3.4 tunnel — Encrypted TLS Tunnel

Accept TLS/SSL connections on a local port and forward plaintext traffic to a remote target. Auto-generates self-signed certificates if `--cert` and `--key` are not provided. TLS tunnels are TCP-only by definition. The remote target may be a hostname, an IPv4 literal, or an IPv6 literal; an IPv6 target is reached over an IPv6 connector, so supply the literal unbracketed and it is bracketed automatically in the socat address.

**Synopsis:**

```
socat-manager tunnel --port <PORT> --rhost <HOST> --rport <PORT>
                     [--cert <PATH>] [--key <PATH>] [--cn <CN>]
                     [--proto <PROTO>] [--name <n>]
                     [--capture] [--watchdog] [--max-restarts <N>] [--backoff <N>]
                     [--dual-stack] [-v]
```

**Examples:**

```bash
# Basic tunnel (auto-generates self-signed cert)
socat-manager tunnel --port 4443 --rhost 10.0.0.5 --rport 22

# With custom certificate
socat-manager tunnel --port 8443 --rhost db.internal --rport 5432 \
    --cert /etc/ssl/cert.pem --key /etc/ssl/key.pem

# Custom Common Name for self-signed cert
socat-manager tunnel --port 4443 --rhost 10.0.0.5 --rport 22 --cn myhost.local

# Tunnel with plaintext UDP forwarder on same port (dual-stack)
socat-manager tunnel --port 4443 --rhost 10.0.0.5 --rport 22 --dual-stack

# With capture (logs decrypted traffic)
socat-manager tunnel --port 4443 --rhost 10.0.0.5 --rport 22 --capture
```

**Options:**

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `-p, --port <PORT>` | int | Yes | — | Local TLS listen port. |
| `--rhost <HOST>` | str | Yes | — | Remote plaintext target host. |
| `--rport <PORT>` | int | Yes | — | Remote plaintext target port. |
| `--cert <PATH>` | str | No | auto-generated | Path to TLS certificate PEM file. Validated for existence and readability. |
| `--key <PATH>` | str | No | auto-generated | Path to private key PEM file. Validated for existence and readability. |
| `--cn <CN>` | str | No | `localhost` | Common Name for auto-generated self-signed certificate. |
| `--proto <PROTO>` | str | No | — | Only validates protocol. `udp`, `udp4`, `udp6` are rejected with a clear error and guidance to use `forward --proto udp4`. `tcp6` triggers a warning and falls back to TCP4. |
| `--name <n>` | str | No | `tunnel-{lport}-{rhost}-{rport}` | Custom session name. |
| `--capture` | flag | No | false | Enable capture of decrypted traffic. Capture log: `logs/capture-tls-{lport}-{rhost}-{rport}-{timestamp}.log`. |
| `--watchdog` | flag | No | false | Enable auto-restart. |
| `--max-restarts <N>` | int | No | 10 | Max restart attempts. |
| `--backoff <N>` | int | No | 1 | Initial backoff seconds. |
| `--dual-stack` | flag | No | false | Add a plaintext UDP forwarder alongside the TLS tunnel (with warning that UDP traffic is NOT encrypted). |
| `-v, --verbose` | flag | No | false | Debug logging. |

**Generated socat commands** (actual output):

```bash
# TLS tunnel — OPENSSL-LISTEN with auto-cert
socat OPENSSL-LISTEN:4443,cert=/path/certs/cert.pem,key=/path/certs/key.pem,verify=0,reuseaddr,fork TCP4:10.0.0.5:22

# With capture
socat -v OPENSSL-LISTEN:4443,cert=/path/certs/cert.pem,key=/path/certs/key.pem,verify=0,reuseaddr,fork TCP4:10.0.0.5:22
```

**Connecting to the tunnel from a client:**

```bash
socat - OPENSSL:localhost:4443,verify=0
```

**Behavioral notes:**

- The protocol stored in the session file for the TLS tunnel is `tls` (not `tcp4`). This affects the stop sequence: `check_port_freed` uses TCP-scoped checks for `tls` protocol sessions.
- The mode string stored in the session file is `tunnel`.
- If `--dual-stack` is enabled, the framework launches a plaintext UDP forwarder (using `build_socat_forward_cmd`, NOT `build_socat_tunnel_cmd`). The mode string for this UDP session is `tunnel-udp`. The protocol is `udp4`. A warning is logged that UDP traffic is NOT encrypted.
- Auto-generated certificates are created by `generate_self_signed_cert()` which runs `openssl req -x509 -newkey rsa:2048 -nodes -days 365`. The private key is created with 0o600 permissions.
- `--cert` and `--key` should be provided together. Providing one without the other triggers a warning: the provided file is ignored and a new self-signed pair is generated. The warning identifies which file was provided and advises providing both.
- Tunnel mode does NOT have `--logfile`, `--socat-opts`, or `--bind` flags.

### 3.5 redirect — Traffic Redirection

Bidirectional transparent proxy between a local port and a remote target with optional traffic capture. Functionally similar to forward mode but uses a different naming convention and does not support cross-protocol (`--remote-proto`).

**Synopsis:**

```
socat-manager redirect --lport <PORT> --rhost <HOST> --rport <PORT>
                       [--proto <PROTO>] [--name <n>]
                       [--capture] [--watchdog] [--max-restarts <N>] [--backoff <N>]
                       [--dual-stack] [-v]
```

**Examples:**

```bash
# TCP redirect
socat-manager redirect --lport 8443 --rhost example.com --rport 443

# UDP redirect (DNS proxy)
socat-manager redirect --lport 5353 --rhost 8.8.8.8 --rport 53 --proto udp4

# Full dual-stack with capture
socat-manager redirect --lport 8443 --rhost example.com --rport 443 --dual-stack --capture
```

**Options:**

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `--lport <PORT>` | int | Yes | — | Local listen port. |
| `--rhost <HOST>` | str | Yes | — | Remote target host. |
| `--rport <PORT>` | int | Yes | — | Remote target port. |
| `--proto <PROTO>` | str | No | `tcp4` | Protocol (both listen and connect sides use the same protocol). |
| `--name <n>` | str | No | `redir-{proto}-{lport}-{rhost}-{rport}` | Custom session name. |
| `--capture` | flag | No | false | Enable traffic capture. Capture log: `logs/capture-{proto}-{lport}-{rhost}-{rport}-{timestamp}.log`. |
| `--watchdog` | flag | No | false | Enable auto-restart. |
| `--max-restarts <N>` | int | No | 10 | Max restart attempts. |
| `--backoff <N>` | int | No | 1 | Initial backoff seconds. |
| `--dual-stack` | flag | No | false | Also start redirector on alternate protocol. |
| `-v, --verbose` | flag | No | false | Debug logging. |

**Generated socat commands** (actual output):

```bash
# TCP4 redirect — same structure as forward but listen and connect use same protocol
socat TCP4-LISTEN:8443,reuseaddr,fork,backlog=128,keepalive TCP4:example.com:443

# UDP4 redirect
socat UDP4-LISTEN:5353,reuseaddr,fork UDP4:8.8.8.8:53

# With capture
socat -v TCP4-LISTEN:8443,reuseaddr,fork,backlog=128,keepalive TCP4:example.com:443
```

**Behavioral notes:**

- Redirect uses `build_socat_redirect_cmd()` which always uses the same protocol for both listen and connect sides (unlike forward mode which supports `--remote-proto`).
- Redirect mode does NOT have `--logfile`, `--socat-opts`, `--bind`, or `--remote-proto` flags.
- The mode string stored in session files is `redirect`.

### 3.6 status — Session Status

Display all active managed sessions or detailed information for a specific session.

**Synopsis:**

```
socat-manager status [<TARGET>] [--cleanup] [-v]
```

Where `<TARGET>` is an 8-character hex session ID, a session name, or a port number.

**Examples:**

```bash
# List all sessions (table format)
socat-manager status

# Detail by Session ID
socat-manager status a1b2c3d4

# Detail by session name (exact match, returns first found)
socat-manager status redir-tcp4-8443-example.com-443

# Detail by port (shows all sessions on that port, all protocols)
socat-manager status 8443

# Verbose output
socat-manager status -v

# Clean up dead session files
socat-manager status --cleanup
```

**Options:**

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `<TARGET>` | positional | No | — | Session ID (8 hex chars), session name (exact match), or port number. If omitted, lists all sessions. |
| `--cleanup` | flag | No | false | Remove session files for dead processes. Acquires advisory lock before cleanup. Both PID AND PGID must be confirmed dead before removal. |
| `-v, --verbose` | flag | No | false | Debug logging. |

**List output format:**

Each session is displayed as one line:

```
  ► a1b2c3d4  redir-tcp4-8443-example.com-443  PID:12345    PGID:12345    tcp4  :8443   → example.com:443  [✓ ALIVE]
  ► e5f67890  redir-udp4-8443-example.com-443  PID:12346    PGID:12346    udp4  :8443   → example.com:443  [✗ DEAD]
```

Mode-specific symbols: `►` for listen/batch, `⇄` for forward, `🔒` for tunnel, `►` for redirect.

**Detail view** (5 sections when a target is specified):

1. **Session Metadata**: Session ID, name, mode, protocol, local port, remote host/port, PID, PGID, started timestamp, correlation ID, launcher PID.
2. **Process Status + Tree**: ALIVE or DEAD indicator. If alive: process tree via `pstree -p <pid>`, with fallback to `ps --forest` (then `ps -o pid,ppid,comm`).
3. **Port Status**: An `ss` query scoped to the session's own protocol — its transport and its address family — filtered by port. A `tcp4` session is reported against the TCP/IPv4 socket only, so a listener of another protocol on the same port number is never mistaken for this session's listener. Shows LISTENING or NOT LISTENING, labelled with the scope, alongside the raw `ss` output line.
4. **Socat Command**: Full socat command string as recorded in the session file.
5. **Associated Logs**: All matching log files found via glob patterns: `session-{sid}*.log`, `session-{sid}-error.log`, `capture-*{port}*.log`.

**Target resolution logic:**

When a target is provided, status mode resolves it in this order:
1. If it looks like an 8-character hex string → treat as session ID
2. If a `.session` file exists for it → display detail
3. If not found by ID → try as session name via `session_find_by_name()`
4. If numeric → try as port number via `session_find_by_port()`

### 3.7 stop — Session Shutdown

Stop one or more sessions using the 9-step protocol-scoped stop sequence.

**Synopsis:**

```
socat-manager stop <TARGET>
socat-manager stop --all | --name <n> | --port <PORT> | --pid <PID>
```

**Examples:**

```bash
# By Session ID (most precise)
socat-manager stop a1b2c3d4

# By session name
socat-manager stop --name redir-tcp4-8443-example.com-443

# All sessions on a port (all protocols)
socat-manager stop --port 8443

# By PID
socat-manager stop --pid 12345

# Everything
socat-manager stop --all
```

**Options:**

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `<TARGET>` | positional | No | — | Session ID or session name. Resolved the same way as `status`: tries session ID first, then session name via `session_find_by_name()`. |
| `--all` | flag | No | false | Stop all managed sessions. |
| `--name <n>` | str | No | — | Stop by exact session name match. |
| `--port <PORT>` | int | No | — | Stop all sessions on a port (all protocols). Port is validated via `validate_port()`. |
| `--pid <PID>` | int | No | — | Stop by socat process PID. Found via `session_find_by_pid()`. |
| `-v, --verbose` | flag | No | false | Debug logging. |

**The 9-step stop sequence** (executed by `stop_session()` in `process.py`):

1. **Read session metadata**: PID, PGID, PROTOCOL, LOCAL_PORT from the `.session` file.
2. **Touch `.stop` signal file**: Creates `sessions/{sid}.stop`. This tells the watchdog daemon thread "this is a deliberate stop — do NOT restart the process."
3. **SIGTERM process group**: `os.killpg(pgid, SIGTERM)`. Signals the socat process and ALL its fork children simultaneously.
4. **SIGTERM PID + direct children**: `os.kill(pid, SIGTERM)` followed by `pkill -TERM -P {pid}`. Belt-and-suspenders for any child that escaped the process group.
5. **Wait grace period**: Polls `os.kill(pid, 0)` and `os.killpg(pgid, 0)` every 0.5 seconds for up to 5 seconds (10 polls total). If both PID and PGID are dead, skip to step 9.
6. **Force SIGKILL if still alive**: `os.killpg(pgid, SIGKILL)` + `os.kill(pid, SIGKILL)` + `pkill -KILL -P {pid}`. SIGKILL cannot be caught or ignored.
7. **Protocol-scoped port cleanup**: If the port is still occupied, `kill_by_port(port, proto)` queries `ss` for the specific protocol and port, verifies each found PID is a socat process via `/proc/{pid}/comm`, and sends SIGKILL only to confirmed socat processes.
8. **Verify port freed**: `check_port_freed(port, proto, retries=DEFAULTS.stop_verify_retries)` polls `check_port_available()` up to 5 times with 0.5-second intervals. Logs a warning if the port remains occupied (may be in TIME_WAIT state).
9. **Unregister session**: Removes the session file (`{sid}.session`), the stop signal file (`{sid}.stop`), and the launching flag file (`{sid}.launching`).

> **Protocol isolation:** Stopping a TCP session on port 8443 does **not** affect a UDP session on the same port. The stop sequence reads the `PROTOCOL` field from the session file and scopes all port operations to that specific protocol. The `--port` flag is the exception — it finds ALL sessions on that port (via `session_find_by_port()`) and stops each one individually.

---

## 4. Protocol Configuration

### 4.1 Individual Protocol Selection (`--proto`)

```bash
socat-manager listen --port 8080 --proto tcp4    # TCP4 (default)
socat-manager listen --port 5353 --proto udp4    # UDP4
socat-manager listen --port 8080 --proto tcp6    # TCP6 (IPv6)
socat-manager listen --port 5353 --proto udp6    # UDP6 (IPv6)
```

Generic protocol names are normalized: `tcp` → `tcp4`, `udp` → `udp4`.

### 4.2 Dual-Stack Operation (`--dual-stack`)

Launch both TCP and UDP on the same port:

```bash
socat-manager redirect --lport 8443 --rhost example.com --rport 443 --dual-stack
# Output:
#   [✓] Redirector active: tcp4:8443 → example.com:443 (SID a1b2c3d4)
#   [✓] Redirector active: udp4:8443 → example.com:443 (SID e5f67890)
```

Stop operations are protocol-aware:

```bash
socat-manager stop a1b2c3d4       # Stop only TCP (UDP remains)
socat-manager stop --port 8443    # Stop both (all protocols on port)
```

### 4.3 Protocol Interaction with Modes

| Mode | `--proto tcp4` | `--proto udp4` | `--dual-stack` |
|------|---------------|---------------|----------------|
| listen | TCP4 listener | UDP4 listener | TCP4 + UDP4 listeners |
| batch | TCP4 per port | UDP4 per port | Both per port |
| forward | TCP4→TCP4 relay | UDP4→UDP4 relay | TCP4 + UDP4 relays |
| tunnel | TLS tunnel over TCP (IPv4 or IPv6 remote) | ❌ Error (TLS requires TCP) | TLS + plaintext UDP |
| redirect | TCP4 redirect | UDP4 redirect | TCP4 + UDP4 redirects |

---

## 5. Traffic Capture

### 5.1 Enabling Capture

```bash
socat-manager listen --port 8080 --capture
socat-manager forward --lport 8080 --rhost 10.0.0.1 --rport 80 --capture
socat-manager tunnel --port 4443 --rhost 10.0.0.5 --rport 22 --capture
socat-manager redirect --lport 8443 --rhost example.com --rport 443 --capture
socat-manager batch --ports "8080,8443" --capture
```

The `--capture` flag adds socat's `-v` flag, producing hex dump output of all traffic. Stderr is redirected to a per-session capture log file.

### 5.2 Capture Log Format

Capture logs contain socat's verbose hex dump output. Each data transfer shows direction, byte count, and hex/ASCII representation:

```
> 2026/03/30 14:30:00.123456  length=44 from=0 to=43
 47 45 54 20 2f 20 48 54 54 50 2f 31 2e 31 0d 0a  GET / HTTP/1.1..
 48 6f 73 74 3a 20 65 78 61 6d 70 6c 65 2e 63 6f  Host: example.co
 6d 0d 0a 0d 0a                                     m....
< 2026/03/30 14:30:00.234567  length=283 from=0 to=282
 48 54 54 50 2f 31 2e 31 20 32 30 30 20 4f 4b 0d  HTTP/1.1 200 OK.
 ...
```

`>` indicates data flowing from the client to the remote target. `<` indicates data flowing from the remote target back to the client.

**Capture log paths:**

| Mode | Path Pattern |
|------|-------------|
| listen | `logs/capture-<proto>-<port>-<timestamp>.log` |
| batch | `logs/capture-<proto>-<port>-<timestamp>.log` (per port) |
| forward | `logs/capture-<proto>-<lport>-<rhost>-<rport>-<timestamp>.log` |
| tunnel | `logs/capture-tls-<lport>-<rhost>-<rport>-<timestamp>.log` |
| redirect | `logs/capture-<proto>-<lport>-<rhost>-<rport>-<timestamp>.log` |

All capture logs are created with 0o600 permissions (owner read/write only).

For tunnel mode, capture logs contain **decrypted** traffic between the TLS termination point and the remote target.

### 5.3 Capture with Dual-Stack

Each protocol gets its own capture log:

```bash
socat-manager listen --port 8080 --dual-stack --capture
# Creates:
#   logs/capture-tcp4-8080-20260330-120000.log
#   logs/capture-udp4-8080-20260330-120000.log
```

### 5.4 Analyzing Capture Logs

```bash
# View capture log in real-time
tail -f logs/capture-tcp4-8080-*.log

# Search for specific patterns (credentials, cookies, auth)
grep -i "password\|auth\|cookie\|token\|bearer" logs/capture-*.log

# Count connections (inbound data transfers)
grep -c "^>" logs/capture-*.log

# Extract just the ASCII representation
awk '/^[<>]/{getline; print}' logs/capture-*.log

# Filter by direction (client → server only)
grep "^>" logs/capture-tcp4-8080-*.log

# Count bytes transferred
grep "length=" logs/capture-*.log | awk -F'length=' '{sum += $2} END {print sum " bytes total"}'
```

---

## 6. Session Lifecycle

### 6.1 Launch and Registration

When a session is launched, the following sequence occurs:

1. **Input validation**: All user-supplied values pass through whitelist validators
2. **Port availability check**: `ss` query confirms the port and protocol are free
3. **Session ID generation**: 8-char hex string from `uuid.uuid4().hex[:8]` — the first 8 characters of a UUID4 hex string, with collision checking against existing session files (up to 100 attempts)
4. **Command construction**: `commands.py` builds the socat argument list (never a shell string)
5. **Process launch**: `subprocess.Popen(cmd, preexec_fn=os.setsid, close_fds=True)` creates the socat process in its own process group
6. **Stability check**: 0.3-second delay followed by a liveness check on the retained child handle — if the process died during startup (e.g., port already bound), the launch is reported as failed
7. **Session registration**: `.session` file written with full metadata (PID, PGID, mode, protocol, port, timestamps, command, correlation ID)
8. **Watchdog start** (optional): A daemon thread begins monitoring the PID
9. **Return to caller**: `launch_socat_session()` returns `(session_id, pid)` — the process runs independently

Under `os.setsid()`, the socat process becomes the session leader. Its PID equals its PGID. This means the process is fully detached from the management script — closing the terminal, killing the script, or sending Ctrl+C does NOT affect the socat process.

### 6.2 Monitoring

```bash
# Quick overview of all sessions
socat-manager status

# Detailed view of a specific session (by SID, name, or port)
socat-manager status a1b2c3d4
socat-manager status tcp4-8080
socat-manager status 8080

# System-level verification (direct tools)
ss -t -l -n -p | grep socat        # TCP listeners
ss -u -l -n -p | grep socat        # UDP listeners
ps aux | grep socat           # Process list
pstree -p $(cat sessions/*.session | grep PID= | head -1 | cut -d= -f2)  # Process tree
```

**Detail view** (when querying by SID, name, or port) displays five sections:

1. **Session Metadata**: All fields from the `.session` file
2. **Process Status + Tree**: ALIVE/DEAD status, `pstree -p <pid>` output (with `ps --forest` and `ps -o pid,ppid,comm` fallbacks)
3. **Port Status**: Protocol-scoped `ss` query showing binding state
4. **Socat Command**: The full command as recorded in the session file
5. **Associated Logs**: All matching log files (session, error, listener, capture)

### 6.3 Stopping Sessions

```bash
# By Session ID (recommended — most precise)
socat-manager stop a1b2c3d4

# By session name
socat-manager stop --name redir-tcp4-8443-example.com-443

# By port (stops all protocols on that port)
socat-manager stop --port 8443

# By PID
socat-manager stop --pid 12345

# All sessions
socat-manager stop --all
```

The stop sequence is protocol-aware and verifies complete shutdown before removing the session file. See the README for the full 9-step stop sequence.

### 6.4 Cleanup and Maintenance

```bash
# Remove session files for dead processes
socat-manager status --cleanup

# This acquires an advisory lock (fcntl.flock), iterates all session files,
# and removes any where BOTH PID AND PGID are confirmed dead. The dual check
# prevents premature removal of dual-stack sessions.

# Manual log cleanup (no built-in rotation)
find logs/ -name "*.log" -mtime +30 -delete

# Archive old logs before deletion
tar czf logs-archive-$(date +%Y%m%d).tar.gz logs/
rm -f logs/*.log

# Use logrotate for automated rotation
cat > /etc/logrotate.d/socat-manager << 'EOF'
/opt/socat-manager/logs/*.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
    create 640 root root
    shred
    shredcycles 3
}
EOF
```

---

## 7. Watchdog Auto-Restart

The `--watchdog` flag enables automatic restart if the socat process crashes unexpectedly:

```bash
socat-manager listen --port 8080 --watchdog
socat-manager redirect --lport 8443 --rhost example.com --rport 443 --watchdog
socat-manager listen --port 8080 --watchdog --max-restarts 20 --backoff 5
```

**Behavior:**

| Parameter | Default | CLI Flag | Description |
|-----------|---------|----------|-------------|
| Initial restart delay | 1 second | `--backoff` | Configurable per session |
| Backoff pattern | Exponential | — | 1s, 2s, 4s, 8s, 16s, 32s, 60s |
| Maximum backoff | 60 seconds | — | Capped to prevent excessive delay |
| Maximum restarts | 10 | `--max-restarts` | Configurable per session |
| Graceful stop | `.stop` file | — | Watchdog checks after each process death |

**Monitor-first design**: The watchdog receives the PID of the already-running socat process and monitors it at a 1-second interval, evaluating liveness through a check that polls the retained child handle so an exited child is reported truthfully rather than as a live zombie. It does NOT launch its own socat — only re-launches after confirmed process death. This eliminates the duplicate-launch bug class where the watchdog would bind an already-occupied port.

**Checking watchdog status**: The watchdog runs as a daemon thread. Check the session log for restart events:

```bash
grep -i "watchdog\|restart\|backoff" logs/session-<SID>.log
```

**Interactive menu**: When enabling watchdog in the menu, you are prompted for both max restart attempts and initial backoff delay (with defaults shown).

---

## 8. Interactive Menu

Run with no arguments for the full interactive menu:

```bash
python3 socat-manager.py
# Or: socat-manager
# Or: socat-manager menu
```

**Menu structure:**

```
Main Menu
├── 1. Listen     → Port, protocol, dual-stack, capture, watchdog, bind, socat-opts
│                   → [After execution] "Configure a paired forward for this listener?"
├── 2. Batch      → Port source (list/range/file), protocol, dual-stack, capture, watchdog
├── 3. Forward    → Local port, remote host, remote port, protocol, dual-stack, capture, watchdog
├── 4. Tunnel     → Port, remote host, remote port, cert/key/CN, capture, watchdog
├── 5. Redirect   → Local port, remote host, remote port, protocol, dual-stack, capture, watchdog
├── 6. Status     → Target (optional), cleanup option
├── 7. Stop       → Target selector (ID/name/port/PID/all)
├── 8. Check Deps → Shows required and optional dependencies with paths and versions
├── 9. Help       → Full help with session management, protocol guide, examples
└── 0. Exit
```

**Cancel support**: Type `q`, `quit`, `cancel`, `back`, or `exit` at any prompt to return to the parent menu. Ctrl+C during a submenu returns to the main menu. Ctrl+C at the main menu prompt exits gracefully.

**Paired forward**: After listener execution, the menu asks "Configure a paired forward for this listener?" — if yes, it enters the forward submenu with the listener's port pre-filled.

**Socat options examples**: When configuring extra socat address options, the menu shows examples:

```
  Examples:
    reuseaddr,fork       — reuse port, fork per connection
    bind=10.0.0.1        — bind to specific interface
    keepalive,nodelay     — enable TCP keepalive + no-delay
```

**Error recovery**: Invalid input redisplays the prompt with an error message. Mode execution failures (including `sys.exit(1)`) are caught — the menu always returns to the main loop.

---

## 9. Operational Scenarios

### 9.1 Honeypot Deployment

Deploy listeners on common service ports to detect scanning and connection attempts:

```bash
# Deploy honeypot listeners with traffic capture and auto-restart
sudo socat-manager batch --ports "21,22,23,25,80,110,143,443,445,993,995,3389,5900" \
    --dual-stack --capture --watchdog --max-restarts 20

# Monitor in real-time
tail -f logs/capture-*.log

# Check which ports are receiving connections
ls -la logs/listener-*.log

# Status overview
socat-manager status
```

### 9.2 Traffic Interception and Analysis

Redirect traffic through a capture point for inspection:

```bash
# Redirect HTTPS traffic with capture
socat-manager redirect --lport 8443 --rhost target-server.internal --rport 443 --capture

# Redirect DNS traffic (UDP) with capture
socat-manager redirect --lport 5353 --rhost 8.8.8.8 --rport 53 --proto udp4 --capture

# Monitor capture logs
tail -f logs/capture-*.log

# Search for credentials
grep -i "password\|auth\|cookie" logs/capture-*.log
```

### 9.3 Encrypted Relay

Create a TLS-encrypted relay with traffic capture for analysis:

```bash
# TLS tunnel with decrypted traffic capture
socat-manager tunnel --port 4443 --rhost internal-db.local --rport 5432 --capture --watchdog

# Connect from client
socat - OPENSSL:relay-host:4443,verify=0
```

### 9.4 DNS Proxy

Proxy DNS traffic through a local relay for monitoring or redirection:

```bash
# UDP DNS proxy with capture
sudo socat-manager redirect --lport 53 --rhost 8.8.8.8 --rport 53 --proto udp4 --capture

# Or dual-stack (TCP + UDP) for full DNS coverage
sudo socat-manager redirect --lport 53 --rhost 8.8.8.8 --rport 53 --dual-stack --capture

# Test
dig @localhost example.com
```

### 9.5 Multi-Service Lab Environment

Set up a lab with multiple forwarding services:

```bash
# Web server relay
socat-manager forward --lport 8080 --rhost web-server.lab --rport 80 --name web --capture

# Database relay with TLS
socat-manager tunnel --port 5433 --rhost db-server.lab --rport 5432 --name db --capture

# SSH relay
socat-manager forward --lport 2222 --rhost ssh-server.lab --rport 22 --name ssh

# All running simultaneously with independent session IDs
socat-manager status
```

---

## 10. Log Management

### Log Directory Contents

| File Pattern | Description |
|-------------|-------------|
| `socat-manager-<YYYYMMDD-HHMMSS>.log` | Master execution log for each script invocation |
| `session-<SID>.log` | Per-session audit trail |
| `listener-<proto>-<port>.log` | Raw captured data (listen/batch modes) |
| `capture-<proto>-<details>-<YYYYMMDD-HHMMSS>.log` | Verbose hex dump (when `--capture` enabled) |

### Log Format

Structured format with correlation IDs for traceability:

```
<Timestamp> [<LEVEL>] [corr:<Correlation-ID>] [<Component>] <Message>
```

Example:

```
2026-03-30 14:30:00 [INFO    ] [corr:a1b2c3d4] [session] Session active: PID=12345 PGID=12345
2026-03-30 14:30:01 [INFO    ] [corr:a1b2c3d4] [watchdog] Watchdog started for 'tcp4-8080' [a1b2c3d4] (max 10 restarts, backoff 1s)
2026-03-30 14:30:02 [WARNING ] [corr:a1b2c3d4] [process] Port 8080 still bound after stop — attempting fallback
```

Every execution generates a unique 8-character correlation ID. All log entries within that execution share the same ID, enabling log aggregation across components.

### Retention and Rotation

The framework does not implement automatic log rotation. Recommended practices:

```bash
# Delete logs older than 30 days
find logs/ -name "*.log" -mtime +30 -delete

# Archive before deletion
tar czf logs-$(date +%Y%m%d).tar.gz logs/

# Use logrotate for production deployments
cat > /etc/logrotate.d/socat-manager << 'EOF'
/opt/socat-manager/logs/*.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
    create 640 root root
    shred
    shredcycles 3
}
EOF
```

---

## 11. Running Tests

### Prerequisites

Install testing tools:

```bash
# Development dependencies
pip install --break-system-packages pytest pytest-cov ruff

# Or via virtual environment (recommended)
make venv
source socat-manager-venv/bin/activate

# Verify
make check-deps
```

### Running the Full Suite

```bash
make test
```

This runs three stages: ruff lint → unit tests → integration tests. All 510 tests must pass. Output:

```
  Linting source and tests...
  All checks passed!
  Running unit tests...
  355 passed in 3.12s
  Running integration tests...
  155 passed in 5.85s

  ✓ Full test suite passed
```

### Running Specific Test Groups

```bash
# Unit tests only (fast, ~3 seconds, no I/O)
make test-unit

# Integration tests only
make test-integration

# Linting only
make lint

# Tests with coverage report
make test-coverage

# Quick smoke test (import, help, version)
make test-smoke
```

### Running Individual Tests

```bash
# Single test file
PYTHONPATH=src python3 -m pytest tests/unit/test_validation.py -v

# Specific test class
PYTHONPATH=src python3 -m pytest tests/unit/test_session.py::TestSessionReadAllFields -v

# Test by name pattern
PYTHONPATH=src python3 -m pytest tests/ -k "test_dual_stack" -v

# With verbose output and short traceback
PYTHONPATH=src python3 -m pytest tests/unit/test_validation.py -v --tb=short
```

### Test Architecture

Tests use mock stubs instead of real socat, ss, and openssl. This means:

- **No network operations** — no ports are actually bound or traffic forwarded
- **No root required** — tests run entirely in user space
- **No external dependencies** — socat doesn't need to be installed to run tests
- **Full isolation** — each test gets its own temporary directory via the `paths` fixture; no test affects another

The mock socat stub (`tests/stubs/socat`) is an executable Python script that logs its arguments and sleeps — so tests have a real PID to track and stop. The mock ss stub reads a state file to report which ports are "listening."

**Test fixtures** (in `conftest.py`):
- `paths` — isolated temporary base directory with sessions/, logs/, certs/, conf/ subdirectories
- `sample_session` — pre-registered redirect session (PID 99999, port 8443, tcp4)
- `dual_stack_sessions` — TCP + UDP sessions on port 8080

### Continuous Integration

Every push and pull request triggers the GitHub Actions CI workflow which runs:

1. **ruff** lint on `src/` and `tests/`
2. **pytest** full suite (355 unit + 155 integration)
3. Matrix across Ubuntu 22.04 and 24.04

Releases are automated via tag-triggered workflow: push a `v*` tag to trigger test → build → publish with tarballs and SHA256 checksums.

---

## 12. Troubleshooting

### "socat is not installed or not in PATH"

Install socat:

```bash
sudo apt-get install -y socat        # Debian/Ubuntu
sudo dnf install -y socat            # RHEL/Rocky/Alma
sudo pacman -S socat                 # Arch
```

### "Port <PORT> is already in use"

Another process is bound to the port:

```bash
# Identify what's using the port
ss -t -4 -l -n -p | grep :<PORT>    # TCP, IPv4
ss -t -6 -l -n -p | grep :<PORT>    # TCP, IPv6
ss -u -4 -l -n -p | grep :<PORT>    # UDP, IPv4
ss -u -6 -l -n -p | grep :<PORT>    # UDP, IPv6

# If it's a stale socat-manager session
socat-manager status --cleanup
socat-manager status -v
```

### Session shows DEAD in status but port is still bound

The socat process was killed externally (not through `socat-manager stop`). Clean up:

```bash
socat-manager status --cleanup
# Then identify and kill the orphaned process
ss -t -4 -l -n -p | grep :<PORT>
kill <PID>
```

### Stop falls through to SIGKILL

This is expected behavior when socat child processes don't respond to SIGTERM within the 5-second grace period. The session is still stopped correctly. Verify:

```bash
socat-manager status <SID>    # Should show DEAD or not found
ss -t -4 -l -n -p | grep :<PORT>       # Should show no binding
```

### Capture log is empty

Verify that `--capture` was specified at launch time (it cannot be added to a running session). Check the session detail:

```bash
socat-manager status <SID>
# Look for the SOCAT_CMD field — it should contain "-v"
```

### Dual-stack: stopping one protocol leaves the other running

This is the intended behavior. A dual-stack launch registers an independent session per protocol, each with its own session ID. Every step of the stop sequence is scoped to the session's transport and address family, so stopping the TCP session has no effect on the UDP session on the same port, and stopping the IPv4 session has no effect on the IPv6 session.

Stop them individually by session ID, or together by port:

```bash
socat-manager status               # Lists both sessions and their protocols
socat-manager stop <SESSION_ID>    # Stops one protocol
socat-manager stop --port 8080     # Stops every session registered on the port
```

### Watchdog keeps restarting

The socat process is crashing immediately. Check the session log for the root cause:

```bash
socat-manager status <SID>
cat logs/session-<SID>.log
```

Common causes: invalid remote host (DNS resolution failure), connection refused on remote port, certificate errors (tunnel mode), port already bound by another process.

### Permission denied on privileged ports

Ports below 1024 require root/sudo:

```bash
sudo socat-manager listen --port 443
sudo python3 socat-manager.py listen --port 80
```

### Python version too old

```bash
python3 --version
# Must show 3.12 or higher

# Install Python 3.12:
sudo apt-get install python3.12
# Or use pyenv
```

### ImportError or ModuleNotFoundError

If running without pip install, set the Python path:

```bash
PYTHONPATH=src python3 -m socat_manager status
# Or use the standalone runner:
python3 socat-manager.py status
```

# Setup Guide

## System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.12+ | 3.12+ |
| OS | Linux (any distro) | Ubuntu 22.04+, Debian 12+, Rocky 9+, Arch |
| socat | 1.7.x | 1.8.0+ |
| OpenSSL | 1.1.x (tunnel mode) | 3.0+ |
| RAM | 64 MB | 256 MB |
| Disk | 10 MB | 50 MB (including logs) |

## Installation Methods

### Method 1: Standalone (No Installation)

The simplest approach — no pip, no venv, no system modification:

```bash
git clone https://github.com/Sandler73/Socat-Network-Operations-Manager.git
cd Socat-Network-Operations-Manager
python3 socat-manager.py
```

### Method 2: pip Install (Editable)

Creates the `socat-manager` command in your PATH:

```bash
git clone https://github.com/Sandler73/Socat-Network-Operations-Manager.git
cd Socat-Network-Operations-Manager
pip install -e .
socat-manager --help
```

### Method 3: Virtual Environment (Recommended for Development)

```bash
git clone https://github.com/Sandler73/Socat-Network-Operations-Manager.git
cd Socat-Network-Operations-Manager
make venv
source socat-manager-venv/bin/activate
socat-manager --help
```

### Method 4: System-Wide Install

```bash
sudo make install
socat-manager --help
```

## Dependency Installation

### Ubuntu / Debian

```bash
sudo apt-get update
sudo apt-get install -y socat openssl iproute2 psmisc
```

### Rocky / Alma / RHEL

```bash
sudo dnf install -y socat openssl iproute psmisc
```

### Arch Linux

```bash
sudo pacman -S socat openssl iproute2 psmisc
```

### Verify Dependencies

```bash
make check-deps
# Or standalone:
python3 socat-manager.py help
```

## Directory Structure

The framework creates these directories automatically on first run:

| Directory | Purpose | Permissions |
|-----------|---------|-------------|
| `sessions/` | Session metadata files (.session) | 0o700 |
| `logs/` | Master, session, capture logs | 0o700 |
| `certs/` | Auto-generated TLS certificates | 0o700 |
| `conf/` | Configuration files | 0o755 |

### Custom Base Directory

Set `SOCAT_MANAGER_BASE` to control where runtime directories are created:

```bash
export SOCAT_MANAGER_BASE=/opt/engagements/alpha
python3 socat-manager.py listen --port 8080
# Creates: /opt/engagements/alpha/sessions/, logs/, certs/
```

## Post-Installation Verification

```bash
# Quick smoke test:
make test-smoke

# Or manually:
socat-manager version           # Should print version
socat-manager help              # Should print full help
socat-manager status            # Should list sessions (empty initially)
```

## Uninstallation

```bash
# pip installation:
make uninstall
# Or: pip uninstall socat-manager

# System-wide:
sudo make uninstall

# Clean up runtime data:
make clean-all
```

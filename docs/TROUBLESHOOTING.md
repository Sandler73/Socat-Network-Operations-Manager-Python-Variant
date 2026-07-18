# Troubleshooting Guide

## Common Issues

### "socat not found"

**Symptom**: `socat not found in PATH — cannot launch session`

**Cause**: socat is not installed or not in the system PATH.

**Fix**:
```bash
# Ubuntu/Debian
sudo apt-get install -y socat

# Rocky/Alma/RHEL
sudo dnf install -y socat

# Arch
sudo pacman -S socat

# Verify:
which socat && socat -V | head -2
```

### Port Already in Use

**Symptom**: `Port 8080 (tcp4) already in use` or socat exits immediately with code 1.

**Cause**: Another process is already bound to that port.

**Fix**:
```bash
# Find what's using the port, in the same scope the launch check uses.
# A protocol is a transport plus an address family, so query the one that
# matches the session you are launching:
ss -t -4 -l -n -p | grep :8080    # TCP, IPv4
ss -t -6 -l -n -p | grep :8080    # TCP, IPv6

# If it's a stale socat-manager session:
socat-manager stop --port 8080

# If it's another process:
sudo kill $(lsof -t -i:8080)
```

### Watchdog Restart Loop (FIXED in v0.1.0)

**Symptom**: Watchdog launches duplicate socat on same port, gets exit code 1, restarts repeatedly.

**Cause**: This was a critical bug in early versions where the watchdog launched its own socat instead of monitoring the existing process.

**Fix**: Update to v0.1.0+. The watchdog now monitors the existing PID and only re-launches after confirmed death.

### Dual-Stack Creates Two of Same Protocol

**Symptom**: Enabling dual-stack creates two UDP (or two TCP) instead of TCP+UDP.

**Cause**: Related to the watchdog bug above — watchdog re-launching created the appearance of a duplicate protocol.

**Fix**: Update to v0.1.0+. With the watchdog fix, dual-stack correctly launches one TCP + one UDP listener.

### "Permission denied" on Port Below 1024

**Symptom**: `Address already in use` or permission error when listening on ports 1-1023.

**Cause**: Privileged ports require root access on Linux.

**Fix**: Run with sudo or use `setcap`:
```bash
sudo socat-manager listen --port 80
# Or grant capability to socat:
sudo setcap 'cap_net_bind_service=+ep' $(which socat)
```

### Ctrl+C Doesn't Stop Sessions

**Symptom**: After Ctrl+C, socat processes continue running.

**Cause**: By design — socat processes run in isolated process groups (setsid) and survive management script termination.

**Fix**: Use the stop command to terminate sessions:
```bash
socat-manager stop --all
# Or by specific session:
socat-manager status
socat-manager stop <session-id>
```

### "Max sessions (256) reached"

**Symptom**: `Maximum session count (256) reached` error.

**Cause**: 256 session files exist in the sessions directory.

**Fix**:
```bash
# Clean up dead sessions:
socat-manager status --cleanup

# If sessions are still alive but unneeded:
socat-manager stop --all
```

### No Color Output

**Symptom**: Output appears without ANSI colors.

**Cause**: TTY detection found stderr is not a terminal (piped or redirected).

**Fix**: This is by design. Color output only appears when stderr is a TTY. Force color by running in a real terminal.

### Session File Says ALIVE But Process Is Dead

**Symptom**: `socat-manager status` shows ALIVE for a session whose process has exited.

**Cause**: Stale session file combined with PID reuse. For a session adopted from an earlier invocation, liveness falls back to `os.kill(pid, 0)` qualified by a zombie-state check. An exited process that has not been collected is correctly read as dead, so the remaining edge case is a genuine PID reuse: the original process has exited and the kernel has assigned its PID to an unrelated, still-running process, which answers the liveness probe.

**Fix**:
```bash
socat-manager status --cleanup
```

### OpenSSL Errors in Tunnel Mode

**Symptom**: `openssl not found` or certificate generation failure.

**Cause**: OpenSSL not installed or not in PATH.

**Fix**:
```bash
sudo apt-get install -y openssl
# Verify:
openssl version
```

### Python Version Too Old

**Symptom**: `SyntaxError` or `ModuleNotFoundError` on import.

**Cause**: Python version is below 3.12. The framework uses `match/case`, `slots=True`, and `from __future__ import annotations`.

**Fix**:
```bash
python3 --version  # Must be 3.12+
# Install Python 3.12+ if needed:
sudo apt-get install python3.12
```

## Debug Mode

Enable verbose debug logging for any command:

```bash
socat-manager listen --port 8080 -v
socat-manager status -v
```

Debug output includes: correlation IDs, PID/PGID tracking, session file operations, port availability checks, and signal handling.

## Log Analysis

### Finding Relevant Logs

```bash
# Master log (all operations for this execution):
ls -lt logs/socat-manager-*.log | head -1

# Session-specific log:
socat-manager status <sid>  # Shows "Associated Logs" section

# Search logs for errors:
grep -r "ERROR\|CRITICAL" logs/
```

## Getting Help

1. Check this troubleshooting guide
2. Check the [FAQ](Frequently_Asked_Questions_(FAQ).md)
3. Run with `-v` for debug output
4. Open a GitHub issue with: Python version, OS, socat version, full error output

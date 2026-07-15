# Frequently Asked Questions (FAQ)

## General

### What is socat-manager?

socat-manager is a session-managed wrapper around socat that provides organized network operations across seven modes (listen, batch, forward, tunnel, redirect, status, stop). It handles process lifecycle, session tracking, and protocol management so you don't have to manage raw socat processes manually.

### How does this differ from the bash version?

Functionally identical — same 7 modes, same session file format, same CLI flags. Key Python advantages: direct PID access via Popen.pid (no setsid wrapper PID problem), native threading for watchdog (no background subshell), structured logging via Python's logging module, and type-hinted codebase with full pytest suite.

### Do I need to install anything?

Only socat is required. Python 3.12+ must be available. No PyPI packages are needed at runtime — the framework uses only the Python standard library.

### Can I use this alongside the bash version?

Yes. Session files use the same KEY=VALUE format and are interoperable. Both variants can read each other's session files. However, running both simultaneously on the same session directory is not recommended.

## Installation

### How do I run without installing?

```bash
python3 socat-manager.py
```

The standalone runner script sets up the Python path automatically. No pip install, no venv, no system modification.

### How do I install system-wide?

```bash
pip install -e .
# Or:
make install
```

### What Python version do I need?

Python 3.12 or newer. The framework uses match/case statements, slots=True on dataclasses, and other 3.12+ features.

## Operations

### How do sessions survive terminal disconnect?

Each socat process is launched in its own process group via os.setsid(). This means killing the management script (or closing the terminal) does NOT kill the socat processes. They continue running independently.

### How do I stop all sessions?

```bash
socat-manager stop --all
```

### How does dual-stack work?

The --dual-stack flag launches two independent sessions on the same port — one TCP and one UDP. Each gets its own session ID. Stopping the TCP session does NOT affect the UDP session, and vice versa.

### What does the watchdog do?

When enabled with --watchdog, a background daemon thread monitors the socat process. If it dies unexpectedly, the watchdog re-launches it with exponential backoff (1s, 2s, 4s... up to 60s cap). Deliberate stops (via socat-manager stop) set a .stop signal file that tells the watchdog not to restart.

### Can I customize the watchdog behavior?

Yes. Use --max-restarts N to set the maximum restart attempts (default: 10) and --backoff N to set the initial delay between restarts in seconds (default: 1). In the interactive menu, you're prompted for both values when enabling watchdog.

### How does traffic capture work?

The --capture flag adds socat's -v flag, which produces a hex dump of all traffic. Captured data is written to logs/capture-<proto>-<port>-<timestamp>.log with 0o600 permissions (owner-only read/write).

### What does the paired forward prompt do?

After configuring and launching a listener, the menu asks "Configure a paired forward for this listener?" If you say yes, it walks you through setting up a forward with the listener's port pre-filled, simplifying the common listen-then-forward workflow.

## Security

### Is this safe to use?

The framework implements defense-in-depth security: whitelist input validation on all user inputs, no eval/exec/shell=True anywhere, restrictive file permissions, process verification before kill-by-port, and exact-key session field matching. However, it creates network listeners and relays traffic — always ensure you have authorization before deployment.

### What permissions are set on files?

Session files: 0o600. Directories: 0o700. Private keys: 0o600. Capture logs: 0o600. These are set explicitly via os.open() with mode flags.

### Can someone hijack a session?

Session IDs are 8-character random hex strings (2^32 keyspace). Session files are 0o600 (owner-only). Advisory file locking prevents concurrent manipulation. The framework verifies /proc/{pid}/comm before killing processes by port.

## Troubleshooting

### See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for detailed issue resolution.

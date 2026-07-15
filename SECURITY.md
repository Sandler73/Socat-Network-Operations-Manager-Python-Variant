# Security Policy and Threat Analysis

## Socat Network Operations Manager v0.9.0

This document provides the complete security analysis for the Socat Network Operations Manager Python variant. It covers the security architecture, threat model, input validation matrix, attack surface analysis, secure coding practices, and vulnerability management process.

---

## 1. Vulnerability Reporting

### Reporting Process

1. **Do NOT** open a public GitHub issue for security vulnerabilities
2. Use the GitHub Security Advisory feature or contact the maintainer directly
3. Include: affected version, component, description, reproduction steps, impact assessment, and suggested severity (CVSS if possible)

### Response Timeline

| Phase | Timeline | Action |
|-------|----------|--------|
| Acknowledgment | Within 48 hours | Confirm receipt, assign tracking ID |
| Triage | Within 7 days | Severity assessment, root cause analysis |
| Fix (Critical/High) | Within 30 days | Patch, test, release |
| Fix (Medium) | Within 60 days | Patch, test, release |
| Fix (Low) | Within 90 days | Batch with next release |
| Disclosure | After fix deployed | Coordinated disclosure with reporter |

### Severity Classification

| Level | Criteria | Example |
|-------|----------|---------|
| Critical | Remote code execution, arbitrary command injection | shell=True with user input (eliminated by design) |
| High | Privilege escalation, session hijacking, data exfiltration | Cross-session field confusion, PID file manipulation |
| Medium | Denial of service, information disclosure | Session file enumeration, log file permissions |
| Low | Hardening gaps, best-practice deviations | Advisory lock bypass, non-security-critical validation gap |

---

## 2. Security Architecture

### 2.1 Defense-in-Depth Layers

The framework implements seven distinct security layers. A failure in any single layer does not compromise the system because the remaining layers provide independent protection.

**Layer 1 — Input Validation (Trust Boundary)**

Every user-controlled string passes through a whitelist validator before reaching any command builder, file operation, or system call. There are 9 validators covering ports, hostnames, protocols, file paths, socat options, session names, session IDs, port ranges, and port lists. Each validator uses explicit character whitelists — only known-good characters are permitted. All validators raise `ValidationError` on invalid input; they never silently correct or sanitize.

The validation layer sits between user input and the command construction layer. No path exists from user input to `subprocess.Popen` that bypasses validation.

**Layer 2 — Command Construction (Injection Prevention)**

All socat commands are constructed as Python `list[str]` argument lists, never as shell strings. The `subprocess.Popen` call uses the argument list directly with `shell=False` (the default). The pattern `shell=True` does not appear anywhere in the 6,779-line codebase. `eval()`, `exec()`, `compile()`, and `__import__()` are similarly absent. This eliminates command injection, shell expansion, and arbitrary code execution as vulnerability classes.

The command builders in `commands.py` are the only place where socat command strings are assembled. They perform no validation (trusting the input has been sanitized by Layer 1) and produce no side effects — they are pure functions that transform validated parameters into argument lists.

**Layer 3 — Process Isolation (Privilege Separation)**

Each socat process is launched in its own session and process group via `os.setsid()` as the `preexec_fn` parameter to `Popen`. This creates a hard boundary between the management script and the managed processes:
- Killing the management script (Ctrl+C, SIGTERM, terminal close) does NOT kill managed sessions
- `os.killpg(pgid, signal)` targets only the specific process tree, not other sessions
- Process group isolation prevents signal leakage between independent sessions
- `close_fds=True` prevents file descriptor leakage from management script to socat

**Layer 4 — File Permissions (Access Control)**

All security-sensitive files are created with restrictive permissions set explicitly via `os.open()` with mode flags:

| Asset | Permission | Mode | Rationale |
|-------|-----------|------|-----------|
| Session files (.session) | Owner read/write | 0o600 | Contain PIDs, PGIDs, commands |
| Session directory | Owner only | 0o700 | Prevent enumeration |
| Log directory | Owner only | 0o700 | Contain operational data |
| Certificate directory | Owner only | 0o700 | Contains private keys |
| Private keys (.pem) | Owner read/write | 0o600 | Cryptographic material |
| Capture logs | Owner read/write | 0o600 | Contain intercepted traffic |
| Lock files | Owner read/write | 0o600 | Prevent manipulation |

**Layer 5 — Protocol Scoping (Operational Isolation)**

All operations are protocol-aware. The stop sequence reads the `PROTOCOL` field from the session file and only operates on that specific protocol:
- `kill_by_port()` scopes its listing to one transport and one address family, derived from the session's own protocol — never both transports and never both families
- Stopping a TCP session on port 8080 does NOT affect a UDP session on port 8080
- Dual-stack sessions have independent session IDs and independent lifecycles
- The `ALT_PROTOCOL` map ensures TCP↔UDP pairing is correct (tcp4→udp4, not tcp4→udp6)

**Layer 6 — Session Integrity (Field Protection)**

Session field reading uses exact-key matching via `line.split("=", 1)` where the left side must exactly match the requested field name. This prevents field confusion attacks:
- Searching for `PID` will NOT match `LAUNCHER_PID=67890` (the key is `LAUNCHER_PID`, not `PID`)
- Searching for `PORT` will NOT match `LOCAL_PORT=8080` (different exact key)
- First occurrence wins: if a file contains `PID=111\nPID=222`, only `111` is returned

This is a deliberate security control against an attack where an adversary appends crafted lines to a session file (e.g., via a symlink or race condition) to confuse the stop sequence into killing wrong processes.

**Layer 7 — Process Verification (Kill Safety)**

`kill_by_port()` — the fallback kill mechanism in the stop sequence — does NOT blindly kill processes occupying a port. It:
1. Queries `ss` for PIDs listening on the specific port and protocol
2. For each PID found, reads `/proc/{pid}/comm` to verify the process name is `socat`
3. Only sends SIGKILL to confirmed socat processes
4. Non-socat processes (e.g., nginx, apache) on the same port are left untouched

This prevents the scenario where a race condition (socat dies, port is reused by another service) causes the stop sequence to kill an unrelated production service.

### 2.2 STRIDE Threat Model

**Spoofing**

| Threat | Attack | Control | Residual Risk |
|--------|--------|---------|---------------|
| Session impersonation | Attacker guesses session ID to stop/query sessions | Session IDs are 8-char random hex (2^32 keyspace). Generated via `uuid.uuid4().hex[:8]` with collision checking. | Low — 1 in 4 billion chance of guessing a valid ID |
| Lock file spoofing | Attacker creates lock file to prevent operations | Advisory locks via `fcntl.flock` — file ownership verified. If lock acquisition fails, operations proceed with warning (matching bash behavior). | Low — DOS only, not privilege escalation |

**Tampering**

| Threat | Attack | Control | Residual Risk |
|--------|--------|---------|---------------|
| Session file modification | Attacker modifies PID/PGID to redirect stop | Files are 0o600 (owner only). Exact-key matching prevents field injection. | Low — requires same-user access |
| Log tampering | Attacker modifies logs to hide activity | Log directory 0o700, log files written via Python logging with timestamps and correlation IDs | Medium — same-user can modify; no cryptographic log integrity |

**Repudiation**

| Threat | Attack | Control | Residual Risk |
|--------|--------|---------|---------------|
| Action denial | Operator denies launching a session | Structured logging with correlation IDs, execution timestamps, launcher PID, and full socat command recorded in session files | Low — complete audit trail |
| Session attribution | Cannot determine who launched a session | `LAUNCHER_PID` and `USER` environment variable logged at startup. Per-session log files with timestamps. | Low |

**Information Disclosure**

| Threat | Attack | Control | Residual Risk |
|--------|--------|---------|---------------|
| Key leakage | Private keys exposed in logs or session files | Keys stored in 0o600 files. Session files record the key PATH (not content). Keys in 0o700 directory. | Low |
| Traffic capture leakage | Captured traffic exposed | Capture logs 0o600. Directory 0o700. No network-accessible log viewer. | Medium — local access exposes captured data |
| Session enumeration | Attacker lists all sessions | Session directory 0o700. Session files 0o600. | Low — requires same-user access |

**Denial of Service**

| Threat | Attack | Control | Residual Risk |
|--------|--------|---------|---------------|
| Session exhaustion | Attacker launches 256+ sessions | `MAX_SESSIONS=256` enforced in `launch_socat_session()` before every launch | Low |
| Port exhaustion | All ports consumed | Port availability checked before launch. Validation rejects invalid ports. | Medium — legitimate port exhaustion is an OS-level concern |
| Watchdog abuse | Watchdog consumes CPU/memory with restarts | Exponential backoff (1s→2s→4s→...→60s cap). Max restarts configurable (default 10). Monitor-first design prevents duplicate launch. | Low |

**Elevation of Privilege**

| Threat | Attack | Control | Residual Risk |
|--------|--------|---------|---------------|
| Command injection | Attacker injects shell commands via input | No shell=True anywhere. Argument lists only. 9 whitelist validators at trust boundary. | Negligible — attack surface eliminated by design |
| Privilege escalation via socat | Attacker exploits socat vulnerability | Out of scope — socat vulnerabilities are upstream. Framework does not add setuid/setgid. | Depends on socat version |
| Path traversal | Attacker uses `../` in file paths or names | `validate_file_path()` rejects shell metacharacters. `validate_session_name()` allows only `[a-zA-Z0-9._-]`. | Low |

---

## 3. Secure Coding Practices

### 3.1 Subprocess Handling

Every subprocess call in the codebase follows these rules:
- Argument lists only (`list[str]`): `subprocess.Popen(["socat", "-u", "TCP4-LISTEN:8080,..."])` — NEVER `subprocess.Popen("socat -u TCP4-LISTEN:8080,...", shell=True)`
- `shell=False` (the default) is never overridden
- `close_fds=True` prevents file descriptor inheritance
- All subprocess calls use explicit timeout values where applicable
- `subprocess.run` for short-lived commands (ss, pkill, pstree, openssl)
- `subprocess.Popen` for long-lived socat processes

### 3.2 Forbidden Patterns

The following patterns are prohibited in the entire codebase and verified by code review:
- `shell=True` on any subprocess call
- `eval()`, `exec()`, `compile()` on any user-influenced data
- `__import__()` with dynamic strings
- `os.system()` or `os.popen()`
- String formatting of shell commands (f-strings into subprocess)
- `pickle.loads()` or `yaml.load()` without SafeLoader
- `input()` used outside of menu.py (all other input is via argparse)

### 3.3 Error Handling

- `ValidationError` for all input validation failures — caught at mode handler level
- `RuntimeError` for launch failures — caught by menu's `_confirm_and_execute()`
- `OSError` for filesystem and process signal failures — caught and logged, never propagated to crash the framework
- `SystemExit` caught by menu to prevent mode handler `sys.exit(1)` from killing the interactive session
- `KeyboardInterrupt` caught by menu at both the main prompt level and the execution level

### 3.4 Memory Safety

- All configuration dataclasses use `frozen=True, slots=True` — immutable after construction, memory-efficient
- No global mutable state except `verbose_mode` flag and logging handler list
- Session data is read from disk on each access, not cached in memory (prevents stale data bugs)
- Context managers for file handles (no resource leaks)
- Daemon threads for watchdog (automatically cleaned up on process exit)

---

## 4. Dependency Analysis

### Runtime Dependencies

| Dependency | Type | License | Purpose | Risk |
|-----------|------|---------|---------|------|
| Python 3.12+ | Runtime | PSF | Interpreter | Low — widely audited |
| Python stdlib | Runtime | PSF | All functionality | Low — no third-party PyPI packages |

### External Tool Dependencies

| Tool | Required | License | Purpose | Risk |
|------|----------|---------|---------|------|
| socat | Yes (operational modes) | GPLv2 | Network operations | Medium — complex C tool, history of CVEs |
| openssl | Yes (tunnel mode) | Apache 2.0 | TLS certificate generation | Low — widely audited |
| ss (iproute2) | Optional (status) | GPL | Port status queries | Low |
| pstree (psmisc) | Optional (detail) | GPL | Process tree display | Low |
| flock (util-linux) | Optional (locking) | GPL | Advisory file locking | Low |

### Development Dependencies

| Package | Purpose | Used In |
|---------|---------|---------|
| pytest | Test framework | tests/ |
| pytest-cov | Coverage reporting | CI |
| ruff | Linting | CI, `make lint` |

---

## 5. Attack Surface Analysis

### External Attack Surface

| Surface | Protocol | Authentication | Authorization |
|---------|----------|----------------|---------------|
| socat listeners | TCP/UDP | None (by default) | Network-level (firewall) |
| TLS tunnel endpoint | TLS/TCP | Certificate-based (self-signed) | None |

The management script itself has NO network-facing attack surface. All network-facing components are socat processes managed by the framework.

### Local Attack Surface

| Surface | Access Required | Threat |
|---------|----------------|--------|
| Session files | Same-user filesystem access | Session enumeration, PID confusion |
| Log files | Same-user filesystem access | Information disclosure |
| Private keys | Same-user filesystem access | Key theft |
| Lock file | Same-user filesystem access | Advisory lock denial |
| CLI arguments | Process listing (ps) | Operational parameter disclosure |

### Supply Chain

Zero external PyPI dependencies at runtime. The only supply chain risk is the Python interpreter itself and the socat/openssl binaries. Development dependencies (pytest, ruff) are not shipped.

---

## 1b. Vulnerability Disclosure Policy

### Disclosure Timeline

| Phase | Timeframe | Action |
|-------|-----------|--------|
| T+0 | Report received | Logged, assigned tracking ID |
| T+48h | Acknowledgment | Reporter notified with tracking ID |
| T+7d | Triage complete | Severity, root cause, affected components identified |
| T+14d | Fix developed | Patch created and tested (Critical/High) |
| T+30d | Fix released | New version published with advisory |
| T+45d | Public disclosure | Full details published (coordinated with reporter) |

Medium and Low severity issues follow the same process with extended timelines (60d and 90d respectively).

## 1c. Security Response Process

### Step 1: Triage

- Confirm the vulnerability is genuine (not a false positive or expected behavior)
- Identify affected components and code paths
- Determine exploitability (requires local access? network access? authentication?)
- Assign initial severity based on CVSS v3.1 base metrics

### Step 2: Classification

| Severity | CVSS Score | Examples |
|----------|-----------|---------|
| Critical | 9.0-10.0 | Remote code execution via user input reaching subprocess with shell=True |
| High | 7.0-8.9 | Session hijacking via PID confusion, privilege escalation via setuid |
| Medium | 4.0-6.9 | Information disclosure via capture logs, DoS via resource exhaustion |
| Low | 0.1-3.9 | Hardening gaps, advisory lock bypass, non-security-critical validation |

### Step 3: Remediation

- Develop fix on a private branch
- Write regression tests that verify the fix and prevent recurrence
- Review fix for regression potential (lesson from bash audit: remediations introduced 2 critical regressions)
- Update documentation if the fix changes security properties

### Step 4: Release and Disclosure

- Publish new version with fix
- Publish security advisory on GitHub
- Notify reporter with details
- Update CHANGELOG.md with security fix details

---

## 6. Implemented Security Controls (CWE Mapping)

### Input Validation — CWE-20 (Improper Input Validation)

Every user-controlled string passes through a whitelist validator before reaching any command builder, file operation, or system call. The 9 validators use explicit character whitelists — only known-good patterns are permitted.

| Validator | CWE | Input | Protection |
|-----------|-----|-------|-----------|
| `validate_port()` | CWE-20 | Port number | Numeric only, range 1-65535 |
| `validate_hostname()` | CWE-20, CWE-78 | Hostname/IP | RFC 1123 + IPv4/IPv6, shell metachar rejection |
| `validate_protocol()` | CWE-20 | Protocol string | Exact set match only |
| `validate_file_path()` | CWE-20, CWE-22 | File path | Exists, readable, no shell metacharacters, no traversal |
| `validate_socat_opts()` | CWE-20, CWE-78 | Socat options | Character whitelist: `[a-zA-Z0-9=,.:/_-]` |
| `validate_session_name()` | CWE-20 | Session name | Character whitelist: `[a-zA-Z0-9._-]`, max 64 chars |
| `validate_session_id()` | CWE-20 | Session ID | Exact regex: `^[a-f0-9]{8}$` |
| `validate_port_range()` | CWE-20 | Port range | Two valid ports, START ≤ END, span ≤ 1000 |
| `validate_port_list()` | CWE-20 | Port list | Comma-separated valid ports |

### Command Injection Prevention — CWE-78 (OS Command Injection)

- `subprocess.Popen` with `list[str]` argument lists only — never `shell=True`
- No `eval()`, `exec()`, `compile()`, `__import__()` on any data
- No `os.system()` or `os.popen()` anywhere in codebase
- No string formatting of shell commands (f-strings into subprocess)

This eliminates CWE-78 as a vulnerability class by design. Even if a validator has a bypass, the argument-list subprocess model prevents shell interpretation of injected characters.

### Path Traversal Prevention — CWE-22 (Path Traversal)

- `validate_file_path()` checks file existence and readability
- Shell metacharacters blocked in file paths
- `validate_session_name()` restricts to `[a-zA-Z0-9._-]` — no `/`, `\`, or `..`
- Session files stored in a fixed directory (`sessions/`) with no user-controlled path components

### Process Management Safety

- `os.setsid()` creates isolated process groups (CWE-250 prevention)
- `close_fds=True` prevents file descriptor leakage
- `kill_by_port()` verifies `/proc/{pid}/comm == "socat"` before killing (prevents CWE-362 race)
- Advisory file locking via `fcntl.flock` prevents TOCTOU on session operations (CWE-367)

---

## 7. Known Limitations and Accepted Risks

### 1. Same-User Access

An attacker with filesystem access as the same user can read session files (0o600), capture logs (0o600), and private keys (0o600). This is inherent to the Unix permission model — no application-level encryption is applied to these files.

**Mitigation**: Run the framework under a dedicated service account. Use filesystem encryption (LUKS, ecryptfs) for the base directory in high-security environments.

### 2. Capture Logs Contain Sensitive Data

Traffic capture logs contain raw hex dumps of all traffic, which may include credentials, tokens, or other sensitive data transmitted in plaintext.

**Mitigation**: Capture logs are created with 0o600 permissions. Establish operational procedures for capture log rotation and secure deletion.

### 3. Self-Signed Certificates

Auto-generated TLS certificates in tunnel mode are self-signed and will trigger certificate warnings in clients. They do not provide authentication — only encryption.

**Mitigation**: Use `--cert` and `--key` to provide CA-signed certificates for production use.

### 4. No Connection Authentication

The framework does not authenticate incoming connections to listeners, forwarders, or redirectors. Any client that can reach the port can connect.

**Mitigation**: Use firewall rules (iptables, nftables) to restrict access to authorized source IPs.

### 5. PID Reuse Window

Between process death and session cleanup, the OS may reuse the PID. The stop sequence mitigates this via PGID-based kill and `/proc/{pid}/comm` verification, but a theoretical race window exists.

**Mitigation**: The 9-step stop sequence with process group isolation and comm verification reduces this window to microseconds.

### 6. Watchdog Does Not Update Session File PID

After a watchdog restart, the session file still contains the original PID. The watchdog tracks the new PID internally but does not update the session file. This matches the bash variant behavior.

**Impact**: `status` may show a stale PID. `stop` still works because it uses the `.stop` signal file mechanism.

---

## 8. Secure Deployment Guidelines

### 8.1 Principle of Least Privilege

Run socat-manager with the minimum necessary privileges:

```bash
# For unprivileged ports (≥1024): run as a regular user
socat-manager listen --port 8080

# For privileged ports (<1024): use sudo only when needed
sudo socat-manager listen --port 443

# Consider a dedicated service account for production deployments
sudo -u socat_service socat-manager listen --port 8080
```

### 8.2 File System Hardening

```bash
# Restrict the project directory
chmod 750 /opt/socat-manager/
chown root:socat_group /opt/socat-manager/

# Ensure runtime directories have correct permissions (auto-set by framework)
# sessions/ → 0o700, session files → 0o600, private keys → 0o600
```

### 8.3 Network Segmentation

- Deploy listeners and redirectors behind a firewall
- Restrict source addresses that can connect to forwarded/redirected ports
- Use network namespaces or VLANs to isolate socat sessions from production traffic
- Consider iptables rules to limit connections per source IP

### 8.4 Log Protection

```bash
# Restrict log directory
chmod 750 /opt/socat-manager/logs/

# Encrypt at rest (if filesystem supports it)
# Use encrypted directories via fscrypt, eCryptfs, or LUKS

# Implement log rotation with secure deletion
cat > /etc/logrotate.d/socat-manager << 'EOF'
/opt/socat-manager/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 640 root socat_group
    shred
    shredcycles 3
}
EOF
```

### 8.5 Monitoring and Alerting

- Monitor for unexpected socat processes: `pgrep -a socat`
- Monitor for unexpected listening ports: `ss -t -l -n -p` and `ss -u -l -n -p`
- Set up file integrity monitoring on the framework and session directory
- Alert on session files created outside expected operational windows

### 8.6 Mandatory Access Control

For high-security environments, consider SELinux or AppArmor profiles:

```bash
# Example AppArmor profile skeleton (customize for your deployment)
# /etc/apparmor.d/usr.bin.socat
/usr/bin/socat {
    # Network access
    network tcp,
    network udp,

    # File access (restrict to socat-manager directories)
    /opt/socat-manager/logs/** rw,
    /opt/socat-manager/certs/** r,

    # Deny everything else
    deny /etc/** w,
    deny /home/** rwx,
}
```

---

## 9. Dependency Security

### socat

socat is the core dependency. Security considerations:

- **Keep socat updated**: Security fixes are released periodically. Monitor your distribution's security advisories.
- **Verify package integrity**: Use your package manager's signature verification (`apt-get` and `dnf` do this automatically).
- **Check version**: `socat -V | head -5`

Known socat CVEs should be tracked via:
- [NVD search for socat](https://nvd.nist.gov/vuln/search/results?query=socat)
- Your distribution's security tracker (Debian Security Tracker, Ubuntu CVE Tracker, Red Hat CVE Database)

### OpenSSL

OpenSSL is used for certificate generation in tunnel mode:

- **Keep OpenSSL updated**: OpenSSL vulnerabilities can affect tunnel mode security
- **Verify version**: `openssl version`
- **Monitor advisories**: [OpenSSL Security Advisories](https://www.openssl.org/news/secadv/)

### Python

Python 3.12+ is the runtime interpreter:

- **Keep Python updated**: Security patches are released regularly
- **Verify version**: `python3 --version`
- **No third-party PyPI packages**: The framework uses only the standard library, eliminating PyPI supply chain risk entirely

---

## 10. Security-Related Configuration

### Configurable Constants

The following constants in `config.py` can be adjusted for security tuning:

| Constant | Default | Description | Security Relevance |
|----------|---------|-------------|-------------------|
| `stop_grace_seconds` | 5.0 | Seconds after SIGTERM before SIGKILL | Longer grace allows clean shutdown but delays forced termination |
| `stop_verify_interval` | 0.5 | Seconds between port-freed checks | Shorter intervals provide faster verification |
| `launch_stability_delay` | 0.3 | Seconds wait after Popen for stability check | Shorter delays may miss immediate crashes |
| `max_sessions` | 256 | Maximum concurrent sessions | Limits resource consumption from session exhaustion |
| `watchdog_max_restarts` | 10 | Maximum auto-restarts | Limits resource consumption from crash loops |

### Environment Hardening

```bash
# Restrict umask for the socat-manager process
umask 0077
socat-manager listen --port 8080

# Limit resource usage via ulimits
ulimit -n 1024    # Max open file descriptors
ulimit -u 256     # Max user processes
socat-manager batch --range 8000-8010

# Use a custom base directory with restrictive permissions
export SOCAT_MANAGER_BASE=/opt/engagements/alpha
chmod 700 /opt/engagements/alpha
socat-manager listen --port 8080
```

---

## 11. Security Changelog

Security-relevant changes across versions:

| Version | Change | Security Impact |
|---------|--------|-----------------|
| 0.1.0 | Monitor-first watchdog design | Eliminates duplicate-launch bug class (port exhaustion, crash loops) |
| 0.1.0 | `subprocess.Popen` with argument lists only | Eliminates CWE-78 (OS Command Injection) by design |
| 0.1.0 | No `eval()`, `exec()`, `compile()` anywhere | Prevents arbitrary code execution via user input |
| 0.1.0 | 9 whitelist validators at trust boundary | Prevents CWE-20 (Improper Input Validation) |
| 0.1.0 | Exact-key session field matching | Prevents PID/LAUNCHER_PID confusion attacks |
| 0.1.0 | `/proc/{pid}/comm` verification in kill_by_port | Prevents killing non-socat processes (CWE-362) |
| 0.1.0 | Advisory file locking on session operations | Prevents TOCTOU races (CWE-367) |
| 0.1.0 | Session file permissions 0o600 | Restricts session metadata to owner only |
| 0.1.0 | Session directory permissions 0o700 | Restricts session directory to owner only |
| 0.1.0 | Private key permissions 0o600 | Restricts TLS private keys to owner only |
| 0.1.0 | Capture log permissions 0o600 | Restricts captured traffic data to owner only |
| 0.1.0 | Protocol-scoped stop sequence | Prevents cross-protocol interference |
| 0.1.0 | `pkill -P` child kill in stop steps 4 and 6 | Ensures complete process tree termination |
| 0.1.0 | Shell metacharacter rejection on all inputs | Prevents injection via hostnames, paths, options |
| 0.1.0 | `close_fds=True` on Popen | Prevents file descriptor leakage to child processes |
| 0.1.0 | `os.setsid()` process group isolation | Prevents signal leakage between management and managed processes |
| 0.1.0 | `MAX_SESSIONS=256` enforcement | Prevents resource exhaustion via session flooding |
| 0.1.0 | Structured logging with correlation IDs | Enables forensic reconstruction of operations |
| 0.2.0 | `validate_file_path()` adds existence/readability checks | Prevents operations on non-existent or unreadable files |
| 0.2.0 | `--cn` parameter validated via `validate_session_name()` | Prevents unvalidated user input reaching openssl subprocess |
| 0.2.0 | `_ensure_dirs()` sets 0o700 on log_dir and cert_dir | Protects captured traffic and private keys from other users |
| 0.2.0 | `generate_self_signed_cert()` uses umask(0o077) | Eliminates TOCTOU window on private key creation |
| 0.2.0 | `stop_session()` uses DEFAULTS.stop_verify_retries | Consistent use of configuration constants |
| 0.2.0 | `_wait_for_pid_death()` uses DEFAULTS.watchdog_poll_interval | Eliminates magic number, centralizes timing constant |
| 0.3.0 | Removed `setsid` binary from REQUIRED_COMMANDS | Python uses `os.setsid()` — eliminates false dependency failure |
| 0.3.0 | `session_list()` refactored to bulk field reader | Eliminates N+1 I/O (9× reduction per session) |
| 0.3.0 | Batch mode deduplicates ports before launch | Prevents redundant launch attempts on duplicate ports |
| 0.3.0 | `import re` moved to module level in process.py | Eliminates per-call import overhead in hot path |
| 0.4.0 | Validation patterns derived from config constants | Single source of truth — eliminates drift between config and validation |
| 0.4.0 | IPv6 hex group validation (1–4 chars per group) | Rejects malformed IPv6 like `ffff:12345::` before reaching socat |
| 0.4.0 | Path traversal upgraded to component-based check | Allows legal filenames with `..` substring; catches actual traversal |
| 0.4.0 | TCP keepalive on forward and redirect builders | Consistent connection health monitoring across all bidirectional modes |
| 0.4.0 | dispatch_mode handles mode='menu' explicitly | Eliminates uncovered code path in menu → dispatch chain |
| 0.6.0 | Error log files created with 0o600 permissions | Consistent permission model across all file types |
| 0.6.0 | `stop_session()` validates sid against path traversal | Defense-in-depth on path construction from user input |
| 0.6.0 | `session_register()` strips newlines from all values | Prevents KEY=VALUE injection in session files |
| 0.6.0 | Standalone runner checks Python >= 3.12 before import | Clear error instead of raw SyntaxError traceback |
| 0.6.0 | Standalone runner handles ImportError with message | Clear error instead of raw ImportError traceback |
| 0.7.0 | `--logfile` validated for path traversal and metacharacters | Prevents write to arbitrary filesystem paths via socat OPEN: |
| 0.7.0 | Tunnel mode warns on cert/key mismatch (one without the other) | Prevents silent use of auto-generated cert when user expects custom |

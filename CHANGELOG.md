# Changelog

All notable changes to the Socat Network Operations Manager (Python variant) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.2] — 2026-07-17

### Fixed

- **CI workflows now run against the published repository layout.** `test.yml`, `lint.yml`, and `release.yml` previously changed into a `socat-manager-python/` subdirectory that exists only in the development tree; every job failed at that step once the project was published at the repository root. The workflows now run at the root, where `src/` and `tests/` live.
- **The test matrix now pins the Python interpreter.** The previous matrix relied on each distribution's system Python, but Debian 12, Rocky 9, and Alma 9 ship Python older than 3.12, so a Python-3.12+ project could never pass on them. Testing now runs on GitHub-hosted Ubuntu 22.04 and 24.04 across Python 3.12 and 3.13, plus Debian 11 and 12 container images that pin the same versions. Container jobs install `git` before checkout.

### Changed

- `codeql.yml` sets `build-mode: none` for the Python analysis (the current recommended setting for interpreted languages).
- Documentation now distinguishes runtime platform support (any Linux distribution with Python 3.12+ and socat) from the pinned CI test matrix.

### Notes

- CodeQL and Dependency Review also depend on repository settings: CodeQL's advanced workflow requires GitHub's "Default setup" to be disabled for the repository (otherwise the two conflict), and Dependency Review runs only on pull requests and requires the repository's Dependency Graph to be enabled.

---

## [1.0.1] — 2026-07-15

### Fixed

- **Documentation accuracy sweep** (principal-level audit remediation):
  - Corrected stale test-count references (was 510/355/155) to the current 757 tests (599 unit across 22 files, 158 integration across 6) across the README, guides, and wiki.
  - Corrected stale codebase metrics (source module, line, and function counts, and the `menu.py` size) across eight sites.
  - Resynchronized the developer guide's 48 constant `(line N)` annotations, whose line numbers had drifted and whose values (for example `__version__`) had gone stale.
- **Stale/missing version headers** brought current across `certs/`, `conf/`, `templates/`, `.github/workflows/`, `.github/ISSUE_TEMPLATE/`, and the test stub executables; `conf/ports.conf.example` gained a missing version line.

### Added

- Full header blocks on the GitHub issue-form templates (`bug_report`, `documentation`, `feature_request`) and a standardized header on `config.yml`; the bug-report form gained `audit` and source-filtering components.
- Wiki parity documentation for `certs/` (TLS certificates) and `conf/` (batch configuration files) in the Configuration Reference, plus the audit environment variables and the `audit/` runtime directory in the environment-variable reference.

### Changed

- Expanded the `socat-manager.py` launcher header (Description, Notes, Execution parameters, Examples) and enriched the top-level `--help` epilog to document source filtering, log-level control, and auditing, and to describe the mode set accurately.
- Enriched all five CI workflow headers with accurate triggers and notes.

### Tooling

- `bump_version.sh` now covers every version-bearing file (example configs, certificate helpers, deployment templates, CI workflows, issue templates, test stubs, and the maintenance scripts) via directory globs rather than a hand-maintained list.
- `resync_devguide_lines.py` now maintains constant `(line N)` annotations (line numbers and values) in addition to function spans and module line counts.
- Added the `audit-prune` Makefile target to `.PHONY`.

---

## [1.0.0] — 2026-07-14

### Milestone

- **v1.0.0.** First stable release of the Python variant, marking full functional parity with the bash original plus the audit, source-filtering, logging, and CI work of the 0.9.x series.

### Added

- **Persistent SQLite audit store** (`audit.py`) — a durable, after-action record of framework activity that survives removal of the real-time session files. It supplements, and never replaces, the KEY=VALUE session files that remain the source of truth for live state. `sqlite3` is standard-library, so no external runtime dependency is added.
  - **On by default**, with opt-out via the `--no-audit` flag (per invocation) or `SOCAT_MANAGER_AUDIT=0` (globally).
  - **Full detail by default**; opt-in redaction via `SOCAT_MANAGER_AUDIT_REDACT=1` masks the remote host in both the `rhost` column and the recorded command.
  - **Keep-forever by default**; `SOCAT_MANAGER_AUDIT_RETENTION_DAYS>0` enables age-based pruning (at most one prune per process, plus `socat-manager audit --prune` and `make audit-prune`).
  - Two tables: `events` (append-only log with timestamp, correlation ID, type, and session identity) and `sessions_history` (one lifecycle row per session with restart count and final state). WAL journaling allows concurrent invocations and watchdog threads to write without blocking. The audit directory is `0o700` and the database `0o600`.
  - **Failure-isolated**: every audit operation catches and logs errors and returns, so a failed audit write can never break an operation.
  - Emission points: `launch` and session start from `launch_socat_session`; `stop`/`stop_failed` and session end from `stop_session`; `crash`, `restart`, and the `watchdog_exhausted` end state from the watchdog.
- **`audit` subcommand** — read-only review of the history with `--session`, `--type`, `--since`, `--limit`, `--history`, `--json`, and `--prune`.
- **`--no-audit`** global flag on all operational subcommands, and `audit_dir`/`audit_db` runtime paths.
- **`make audit-prune`** target.

### Testing

- Added `tests/unit/test_audit.py` (37 tests): enablement resolution, event and history writes, redaction, retention pruning, query filters, schema/permissions, concurrency under WAL, and failure isolation.
- Test count: 718 to 755.

### Documentation

- Usage guide "Auditing" section; developer guide entries for `audit.py` and `modes/audit_view.py` plus the new config paths; wiki Configuration-Reference, Usage-Guide, and Architecture-and-Design; SECURITY.md audit-store layer; README structure updated.

---

## [0.9.9] — 2026-07-14

### Added

- **Source filtering** on the listener modes (listen, batch, forward, tunnel, redirect):
  - `--allow <CIDR>` restricts a listener to a source address range, mapping to socat's `range=` option. Accepts IPv4 or IPv6 CIDR notation, masks host bits, brackets IPv6 automatically, and rejects a range whose address family does not match the listener protocol (family checking is skipped for the tunnel TLS listener, whose family socat selects at bind time).
  - `--tcpwrap [NAME]` enforces TCP wrappers via `/etc/hosts.allow` and `/etc/hosts.deny`, mapping to socat's `tcpwrap=` option with a default daemon name of `socat`.
  - New validators `validate_source_range()` and `validate_tcpwrap_name()` in `validation.py`, and a `build_filter_opts()` assembler in `commands.py`. All four command builders gained a `filter_opts` parameter that appends the options to the listener side of the command. The interactive menu offers both controls as opt-in prompts.

### Testing

- Added `tests/unit/test_source_filtering.py` (31 tests) covering the validators, the assembler (IPv6 bracketing, family checking), and the placement of `range=`/`tcpwrap=` on each builder's listener address; extended the menu prompt tests with source-filter collection cases.
- Test count: 680 to 718.

---

## [0.9.8] — 2026-07-14

### Added

- **CI workflows**: A `lint.yml` quality gate (ruff lint, ruff flake8-bandit security scan with S603/S607 excluded by design, and a non-blocking mypy check), a `codeql.yml` security-and-quality analysis (push, pull request, weekly), and a `dependency-review.yml` gate on pull requests. All workflows declare least-privilege `permissions` and cancel superseded in-progress runs.
- **Test coverage**: `tests/unit/test_child_registry_concurrency.py` (3 tests) exercises the child handle registry from many threads at once — concurrent registration with no lost updates, concurrent register/kill/reap leaving no handle or zombie, and safe reaping of unknown PIDs under contention. `tests/unit/test_menu_prompts.py` (35 tests) covers the interactive menu input primitives (cancel handling, defaults, validation with retry) and the common-flag collector, raising `menu.py` line coverage from 31.5% to 37.1%.

### Changed

- **test.yml**: added least-privilege `permissions`, concurrency cancellation, a coverage XML report, and a `coverage.xml` artifact upload from the Ubuntu 24.04 job. Corrected the stale workflow header versions.
- **release.yml**: added an explicit `contents: write` permission scope and corrected the header version.

### Documentation

- Documented the full workflow suite in the development guide and its wiki page, and updated the README directory diagram (test counts 524 unit across 20 files; workflows enumerated).

### Testing

- Test count: 642 to 680.

---

## [0.9.7] — 2026-07-14

### Added

- **Deployment templates** in `templates/` with a `templates/README.md` install and usage guide:
  - `systemd/socat-manager@.service` — a templated per-port listener unit (`socat-manager@8080`), `Type=oneshot` with `RemainAfterExit=yes` to match the launch-and-return model, with hardening directives and documented `CHANGE-ME` placeholders.
  - `logrotate/socat-manager` — a logrotate configuration for the master, session, error, and capture logs, using `copytruncate` and a path placeholder.
  - `socat-profiles/profiles.conf` — named, copy-paste `--socat-opts` option strings (address reuse, TCP keepalive, large buffers, low latency, source restriction, TCP wrappers), each validated against the option validator.

### Documentation

- Expanded the README directory diagram to enumerate the `templates/` subtree.

---

## [0.9.6] — 2026-07-14

### Added

- **conf/ examples**: Added a `conf/README.md` documenting the batch config format (one port per line, `#` comments, no inline comments) and three themed example port lists — `web-services.conf.example`, `database-services.conf.example`, and `high-ports.conf.example` — alongside the existing `ports.conf.example`. Every example was validated against the actual batch parser.
- **certs/ examples**: Added a `certs/README.md` (built-in and manual generation, Subject Alternative Names, private-key handling), an `example-san.cnf` OpenSSL configuration, a `generate-example-cert.sh` generator that mirrors the built-in generator's parameters under a restrictive umask, and a clearly-labeled disposable self-signed pair (`example-do-not-use.crt` / `example-do-not-use.key`) for documentation and tests. The example key is expendable and must never protect real traffic.

### Documentation

- Updated the README directory diagram to enumerate the `conf/` and `certs/` example material.

---

## [0.9.5] — 2026-07-14

### Added

- **Makefile targets**: `lint-fix` (ruff autofix), `security` (ruff flake8-bandit S-rule scan, with the by-design subprocess rules S603/S607 excluded and rationale documented), `type-check` (mypy when installed), `resync-docs` (regenerate developer-guide line annotations), `wiki-export` (stage wiki pages into `build/wiki/`), and an aggregate `check` gate (lint + security + tests + docs).
- **SECURITY.md**: a Supported Versions table and a direct "Report a vulnerability" advisory link in the reporting process; mirrored in the Security-Policy wiki page.
- **LICENSE**: an `SPDX-License-Identifier: MIT` declaration and a License Notice and Attribution section codifying the collective copyright holder, the `Sandler73` maintainer identity, and the no-personal-names attribution rule.

### Changed

- **.gitignore**: added SQLite database and write-ahead sidecar patterns (`*.db`, `*.db-wal`, `*.db-shm`, `*.sqlite`, `*.sqlite3`). Reworked the `certs/` rules so the directory is no longer wholesale-ignored — runtime-generated `*.pem`/`*.key`/`*.crt` remain ignored, while committed example material (generator script, openssl config, README, and a clearly-labeled throwaway pair) is re-included by trailing negation rules that override the broad key patterns.
- Added a targeted `# noqa: S104` with rationale on the interactive bind-address default (`0.0.0.0`), so the security scan still flags any new unintended bind-all.

---

## [0.9.4] — 2026-07-14

### Added

- **Issue and pull request templates**: Added structured GitHub issue forms under
  `.github/ISSUE_TEMPLATE/` — a bug report, a feature request, and a documentation
  form — plus a chooser `config.yml` that disables blank issues and routes security
  reports to a private advisory and usage questions to Discussions. Added
  `.github/PULL_REQUEST_TEMPLATE.md` with the project's change-type, testing-evidence,
  documentation, and security and quality gates.

### Documentation

- Reworked the "Reporting Bugs" section of `CONTRIBUTING.md` to describe the issue
  forms and added a "Submitting Pull Requests" section describing the PR template's
  expectations (regression test for bug fixes, present-tense docs, changelog in both files).

---

## [0.9.3] — 2026-07-14

### Added

- **Console log-level selection**: All operational subcommands now accept `--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}` (case-insensitive) to set console verbosity explicitly, and `-q`/`--quiet` as a shortcut for `--log-level WARNING`. The pre-existing `-v`/`--verbose` remains as a shortcut for `--log-level DEBUG`. A new `resolve_log_level()` in `logging_setup.py` centralizes the precedence: an explicit `--log-level` overrides both shortcuts, and `--verbose` beats `--quiet` when both are supplied. The `status -v` listener-info toggle is unchanged; use `--log-level DEBUG` there to raise console verbosity.

### Testing

- Added `tests/unit/test_log_level.py` (23 tests) covering the resolution precedence, case-insensitive parsing, rejection of unknown and non-offered level names, and the CLI surface across subcommands including the preserved `status -v` behavior.
- Test count: 619 to 642.

---

## [0.9.2] — 2026-07-14

### Changed

- **Author metadata**: The package author is now recorded as `Sandler73` in `src/socat_manager/__init__.py` and `pyproject.toml`, with the project's collective identity, "Socat Network Operations Manager Contributors," retained for the copyright notice in `LICENSE`. The developer guide's record of the `__author__` constant was updated to match.

### Documentation

- Rewrote the README "Directory Structure" diagram to depict the published repository layout: community-health files (`SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`) at the repository root, long-form guides under `docs/`, and no `wiki/` directory, since the wiki pages are extracted to the GitHub Wiki rather than shipped as a subdirectory. Corrected the counts in the diagram to match the source: 463 unit tests across 17 files, 158 integration tests across 6 files, 11 whitelist validators, 7 operational mode handlers, and updated stale descriptions. The `templates/` and `certs/` entries now describe their intended contents (deployment templates and TLS certificate examples with a generation helper).

---

## [0.9.1] — 2026-07-14

### Fixed

- **process.py / watchdog.py**: The stop sequence now evaluates process death with the zombie-aware liveness check and collects the terminated child, rather than probing with a bare `os.kill(pid, 0)`. A socat process is a direct child of whatever process launched it, so when a session is launched and stopped within one process — as it is from the interactive menu — the killed child remained in the process table as a zombie. Because a zombie still answers signal 0, the grace-period wait (step 5) ran for its full duration on every stop, the death verification (step 6b) read the dead process as still alive and returned `False` with a spurious "may not be fully stopped" warning, and the child and its retained handle leaked. `stop_session()` now checks liveness through `process_is_running()` in both step 5 and step 6b and calls `reap_child()` once death is confirmed; the watchdog's deliberate-stop exit path also collects the child. The one-shot CLI path was unaffected because a re-parented process is collected by init.

- **session.py**: `session_update_process()` no longer overwrites the `STARTED` field. `STARTED` records when a session was created; a watchdog restart changes which process the session owns, not when the session began, so rewriting it silently discarded the original creation time. The function now updates only `PID` and `PGID` and preserves `STARTED`.

### Documentation

- Corrected the stop-sequence descriptions in the usage guide, developer guide, and architecture wiki (steps 5 and 6b) to describe zombie-aware death detection and child collection, and corrected the `launch_stability_delay` note and the "session says ALIVE but process is dead" troubleshooting entry accordingly.
- Corrected the `session_update_process()` description across the developer guide and wiki to state that `STARTED` is preserved.
- Made the developer-guide line-number resynchronization utility module-scoped so a helper defined in several modules resolves to the correct per-module span, and added the missing developer-guide entries for the child-handle and protocol-scope functions.

### Testing

- Added `tests/unit/test_stop_reaping.py` (4 tests) covering a real in-process child: the stop reports success for a killed child, leaves no zombie, drops the retained handle, and completes without consuming the full grace period.
- Added a `session_update_process()` test asserting the original `STARTED` timestamp survives a process-identity update.
- Test count: 614 to 619.

---

## [0.9.0] — 2026-07-14

### Summary

Watchdog and launch descriptions match the code. Comments and documentation that described death detection as a bare signal-0 poll now describe the handle-based liveness check the code performs.

### Fixed

- **watchdog.py**: The module header and the Phase 1 comment described monitoring as "os.kill polling". Liveness is evaluated through `process_is_running()`, which polls the retained child handle so an exited child is reported truthfully rather than as a live zombie. Both descriptions now state that.
- **docs**: The developer guide, usage guide, and architecture wiki described the watchdog monitor and the launch stability check as `os.kill(pid, 0)` polls. These now describe the handle-based liveness check. The stop sequence's grace-period wait, which does signal the PID and PGID directly, is described accurately and left unchanged.

### Changed

- Version bumped from 0.8.9 to 0.9.0.

---

## [0.8.9] — 2026-07-14

### Summary

Write-target path validation is centralized. The listen mode's inline logfile validation is replaced by a shared validator that draws its forbidden-character set from configuration.

### Fixed

- **modes/listen.py**: The `--logfile` path was validated inline with a literal shell-metacharacter pattern and a hand-written traversal check, duplicating the forbidden-character set that configuration already defines. If that set were changed in one place the inline copy would drift. The inline block is replaced by a call to the shared validator, and the now-unused `re` import is removed.

### Added

- **validation.py**: `validate_writable_path(path)` validates a path that will be written to — a non-empty path, no parent-directory traversal component, and none of the characters in `config.FILEPATH_FORBIDDEN_CHARS` — without requiring the path to exist, since a write target is created at launch. `validate_file_path()` now builds on it and adds the existence and readability checks specific to input files, so both validators reject the same character set from a single definition.
- **tests**: `tests/unit/test_validation.py` — write-target acceptance of a nonexistent path, whitespace stripping, rejection of empty paths, traversal components, and each forbidden character, allowance of a double dot within a name, and a consistency check that both path validators reject exactly the config-defined character set (16 tests).

### Changed

- Version bumped from 0.8.8 to 0.8.9.
- Test count: 598 to 614.

---

## [0.8.8] — 2026-07-14

### Summary

Encrypted tunnels reach IPv6 remote targets. The tunnel's remote leg selects its address family from the target rather than always using IPv4.

### Fixed

- **commands.py / modes/tunnel.py**: The tunnel builder hardcoded a `TCP4` connector for the remote leg, so an IPv6 remote target could not be reached even once the address was correctly bracketed. The builder now takes a `remote_proto` selector and emits a `TCP6` connector for an IPv6 target, and the tunnel mode derives the selector from the remote host — `tcp6` for an IPv6 literal, `tcp4` otherwise (which also serves hostnames, since socat resolves them itself). The TLS listener remains TCP, as TLS tunnels are TCP-only by definition.

### Added

- **validation.py**: `is_ipv6_literal(host)` reports whether a validated host is an IPv6 literal, using the same shape check the hostname validator uses to route a value into IPv6 handling. This selects the connector's address family for the remote target.
- **tests**: `tests/unit/test_ipv6_addressing.py` — the builder's remote family selection across IPv4, IPv6, default, and unknown selectors, and the IPv6 literal predicate across literals, hostnames, and IPv4 (10 tests). `tests/integration/test_mode_handlers.py` — the tunnel mode producing a bracketed TCP6 connector for an IPv6 remote and a TCP4 connector for an IPv4 remote (2 tests).

### Changed

- The tunnel configuration display now labels the remote target with its address family.
- Version bumped from 0.8.7 to 0.8.8.
- Test count: 590 to 598.

---

## [0.8.7] — 2026-07-14

### Summary

Session lookups recover the session ID from the file name. A matched session file is no longer opened a second time to read its SESSION_ID field.

### Fixed

- **session.py**: `session_find_by_name()`, `session_find_by_port()`, `session_find_by_pid()`, and `session_get_all_ids()` read the `SESSION_ID` field back from each matching file to recover the ID. Session files are named `{sid}.session`, so the ID is the file stem and is identical to that field by construction. Reading it back opened the file a second time for no new information. The ID is now taken from the file name.

### Added

- **session.py**: `_sid_from_file()` derives the session ID from a session file's stem and skips a name containing characters that would be unsafe in a constructed path — the same defensive check the stop path applies before turning a session ID into a file path.
- **tests**: `tests/unit/test_session_lookup.py` — ID derivation from the file name, rejection of an unsafe stem, acceptance of both hex and readable stems, correct IDs from all three lookups and enumeration, empty results on no match, and a read-count check proving a name lookup opens each candidate file exactly once (10 tests).

### Changed

- Version bumped from 0.8.6 to 0.8.7.
- Test count: 581 to 590.

---

## [0.8.6] — 2026-07-14

### Summary

Session liveness is evaluated from fields already read. The listing and detail views no longer re-open each session file to check whether its process is alive.

### Fixed

- **session.py**: `session_list()` read every field of a session file in one pass and then called `session_is_alive()`, which re-opened the same file to read the PID and PGID again. Across a listing this doubled the file reads for the liveness column. `session_detail()` had the same pattern. Both now evaluate liveness from the fields they have already loaded, so each session file is read once.

### Added

- **session.py**: `process_alive(pid_str, pgid_str)` decides liveness from a recorded PID and PGID supplied by the caller, checking the PID first and falling back to the process group. `session_is_alive()` is now a thin wrapper that reads a session's fields once and delegates to it. The primary check routes through `process.process_is_running()`, so a socat process launched by this framework that has exited but not yet been collected is reported as dead rather than as a live zombie.
- **tests**: `tests/unit/test_session_liveness.py` — the field-based helper across live, dead, empty, malformed, and group-only cases; the exited-child case reporting dead rather than zombie-alive; `session_is_alive()` end to end; and a read-count check proving the listing opens each session file exactly once (11 tests).

### Changed

- Version bumped from 0.8.5 to 0.8.6.
- Test count: 570 to 581.

---

## [0.8.5] — 2026-07-14

### Summary

Single logging initialization site. Logging is configured once per invocation rather than once per invocation and again per dispatch.

### Fixed

- **__main__.py**: `main()` applied the verbose flag and called `setup_logging()`, and `dispatch_mode()` then repeated both. The duplication was harmless in effect but left ownership of initialization ambiguous and made the interactive menu depend on dispatch to configure its logging, since the menu path returns from `main()` before the initialization block it contained.

### Added

- **__main__.py**: `initialize_logging(args)` applies the verbose flag and configures the logger. `main()` calls it once, immediately after argument parsing, so every path — interactive menu, mode dispatch, and the startup banner — runs against a configured logger. `dispatch_mode()` is now routing only.
- **tests**: `tests/unit/test_main.py` — verbose flag application, an invocation without a verbose flag leaving the flag untouched, logging configured exactly once per invocation, and dispatch performing no initialization of its own (4 tests).

### Changed

- Version bumped from 0.8.4 to 0.8.5.
- Test count: 567 to 570.

---

## [0.8.4] — 2026-07-14

### Summary

Child process collection. Processes launched by the framework are children of the management process, and their exit status is now collected when they terminate. This makes death detection truthful and prevents zombie process table entries from accumulating.

### Fixed

- **watchdog.py**: `_wait_for_pid_death()` polled `os.kill(pid, 0)` and treated a successful signal as proof the process was alive. The monitored socat process is a child of the management process, so when it exited it remained in the process table as a zombie until its exit status was collected — and a zombie still answers signal 0. The poll therefore never observed the death: the watchdog blocked on its first terminated process and stopped restarting altogether, so auto-restart failed silently rather than merely leaking process table entries. Liveness is now evaluated through `process_is_running()`, and the child is collected once death is observed.
- **watchdog.py**: `_launch_replacement()` discarded the `Popen` handle of every replacement it started, so no replacement could ever be collected. The handle is now retained through `register_child()`.
- **process.py**: `launch_socat_session()` discarded the `Popen` handle of the initial process and verified startup with `os.kill(pid, 0)`, which cannot distinguish a running process from one that exited immediately and has not been collected. The handle is retained and the stability check consults it.

### Added

- **process.py**: A lock-guarded registry of child process handles keyed by PID, with `register_child()`, `reap_child()`, and `process_is_running()`. `reap_child()` collects a terminated child's exit status and drops its handle, so the registry only ever holds running processes and cannot grow without bound. `process_is_running()` consults the handle for children and falls back to signal 0 qualified by a zombie check for processes the current instance did not launch, such as sessions adopted from a previous invocation.
- **tests**: `tests/unit/test_child_reaping.py` — zombie state detection, liveness for running, exited, unregistered, and invalid PIDs, exit status collection and handle removal, running children left uncollected, and an end-to-end check that the watchdog's death poll observes a real child's exit and leaves no zombie behind (14 tests, exercised against real child processes rather than mocks).

### Changed

- **tests**: Mocked `Popen` handles in `test_lifecycle.py` and `test_capture.py` now model process state through `poll()`, since the launch path consults the retained handle to distinguish a running process from one that has exited.
- Version bumped from 0.8.3 to 0.8.4.
- Test count: 553 to 567.

---

## [0.8.3] — 2026-07-14

### Summary

IPv6 addressing correction. Hosts embedded in socat addresses are now formatted for the colon-delimited address grammar, so IPv6 remote targets and IPv6 bind addresses produce valid socat commands.

### Fixed

- **commands.py**: The forward, redirect, and tunnel builders interpolated the remote host directly, emitting addresses such as `TCP6:2001:db8::1:443`. socat address fields are colon-delimited, so an IPv6 literal's own colons were read as field separators and the boundary between address and port could not be determined. socat rejects such an address, so every forward, redirect, or tunnel to an IPv6 literal failed at launch: the process exited immediately and the stability check reported the session as dead. Remote targets are now formatted through `format_socat_endpoint()`, which brackets IPv6 literals — `TCP6:[2001:db8::1]:443`. Hostnames that resolve to IPv6 addresses were never affected, since socat performs that resolution itself.
- **modes/listen.py**: The `--bind` address was interpolated into the `bind=` socat option with the same ambiguity. An IPv6 bind address is now bracketed — `bind=[2001:db8::1]`.

### Added

- **commands.py**: `format_socat_host()` brackets IPv6 literals for use in socat addresses and returns hostnames, IPv4 literals, and already bracketed literals unchanged. `format_socat_endpoint()` composes a host and port into an endpoint, keeping the port as the final colon-delimited field.
- **tests**: `tests/unit/test_ipv6_addressing.py` — host formatting across hostnames, IPv4 literals, and IPv6 literals in compressed and full form, idempotence on already bracketed input, endpoint parseability, and bracketed IPv6 remote targets from the forward, redirect, and tunnel builders including UDP (19 tests).

### Changed

- Version bumped from 0.8.2 to 0.8.3.
- Test count: 530 to 553.

---

## [0.8.2] — 2026-07-14

### Summary

Protocol scoping correction. A protocol is a transport and an address family. Every socket query in the framework now preserves both dimensions, so `tcp4`, `tcp6`, `udp4`, and `udp6` are never collapsed onto one another.

### Fixed

- **process.py**: `check_port_available()`, `check_port_freed()`, and `kill_by_port()` derived their scope as TCP-versus-UDP only and queried `ss -tln` / `-uln`, which lists both address families. Two failures followed. A `tcp6` listener made the same `tcp4` port report as occupied, so a legitimate launch was refused. More seriously, the port-based cleanup step of the stop sequence enumerated the other family's socat process and could terminate it, so stopping one session could take down an unrelated one holding the same port number in the other family. All three functions now scope the listing to one transport and one address family.
- **process.py**: The `lsof` fallback in `kill_by_port()` now carries the address family through the `-i4` / `-i6` selector rather than querying both families.
- **session.py**: The port status section of `session_detail()` queried `ss -tlnp` or `ss -ulnp` and reported any listener on the port number regardless of address family. It now queries the session's own protocol scope and labels the result with that scope (for example `TCP/IPv4`).

### Added

- **config.py**: `protocol_transport()`, `protocol_family()`, and `socket_scope_flags()`. Scope derivation lives with the protocol model, which makes config the single source of truth consumed by both `process.py` and `session.py` without a circular import.
- **tests**: `tests/unit/test_port_scoping.py` — scope derivation for all four protocols, distinct scopes per protocol, family and transport flags on availability queries, an IPv6 listener not occupying the IPv4 port, a TCP listener not occupying the UDP port, and the cleanup path not reaching across address families (10 tests).
- **tests**: `tests/unit/test_config.py` — protocol scope derivation against the full `VALID_PROTOCOLS` set (4 tests).

### Changed

- **tests**: `test_process.py` and `test_lifecycle.py` flag assertions updated from the collapsed single-flag form to the scoped transport-plus-family contract.
- Version bumped from 0.8.1 to 0.8.2.
- Test count: 520 to 530.

---

## [0.8.1] — 2026-07-14

### Summary

Session control correction. The watchdog now writes the replacement process identity back to the session file after every restart, so the durable session record always names the process that currently owns the port.

### Fixed

- **watchdog.py**: A restart re-launched socat with a new PID but never updated the session file. The record continued to name the terminated predecessor, so `session_is_alive()` reported the session dead while the replacement was serving traffic, and `stop_session()` signalled a PID that no longer existed — leaving the live replacement running and reachable only through the port-based fallback in step 7 of the stop sequence. After `stop --all` the survivor appeared only as an orphaned socat process in the closing report. The restart path now calls `session_update_process()` with the replacement PID and PGID before it begins monitoring the new process. A failed replacement launch leaves the record untouched.

### Added

- **session.py**: `session_update_process(sid, pid, pgid) -> bool` rewrites the `PID`, `PGID`, and `STARTED` fields of an existing session file while preserving every other field and the file header. The read-modify-write cycle runs under the advisory session lock. The new record is written to a temporary file with 0o600 permissions and renamed over the original, so a concurrent reader never observes a partially written session record.
- **tests**: `tests/unit/test_session_update.py` — field replacement, field preservation, 0o600 permissions after rewrite, no temporary artifact left behind, missing-session handling, and liveness tracking the updated process (6 tests).
- **tests**: `tests/unit/test_watchdog.py` — the session record names the final replacement after a restart cycle, the record is updated exactly once per successful restart, and a failed launch does not rewrite the record (3 tests).

### Changed

- Version bumped from 0.8.0 to 0.8.1.
- Test count: 511 to 520.

---

## [Unreleased]

### Planned

- GitHub Actions CI for Python variant (8-distro matrix matching bash CI)
- Real socat integration tests (requires socat binary in CI runners)
- Additional operational mode options based on field operator feedback
- PyPI package publication

---

## [0.8.0] — 2026-04-12

### Summary

Technical code documentation audit release. Line-by-line cross-reference of every documentation claim against actual source code. Eight discrepancies identified between documentation and v0.6.0/v0.7.0 code changes — all corrected.

### Fixed

- **DEVELOPER_GUIDE**: `session_register()` security annotations now document newline stripping (`\n`, `\r` removed from all string values before writing KEY=VALUE pairs).
- **DEVELOPER_GUIDE**: `process.py` Security Properties updated to include error log 0o600 permissions and `stop_session` path traversal defense.
- **DEVELOPER_GUIDE**: `stop_session()` security annotations now document SID validation against path traversal characters (`/`, `\`, `..`, `\0`) and `DEFAULTS.stop_verify_retries` usage.
- **DEVELOPER_GUIDE**: `mode_listen()` security annotations now document `--logfile` path validation for traversal and metacharacters before reaching socat `OPEN:` address.
- **DEVELOPER_GUIDE**: `mode_tunnel()` security annotations now document `--cn` validation and cert/key mismatch detection with warning and forced regeneration.
- **DEVELOPER_GUIDE**: `__main__.py` architecture role now documents standalone runner Python version check (`sys.version_info >= (3, 12)`) and `ImportError` handling.
- **USAGE_GUIDE**: `--logfile` option description now notes path traversal and shell metacharacter validation.
- **USAGE_GUIDE**: Tunnel mode behavioral notes corrected — `--cert` without `--key` (or vice versa) triggers a warning and regeneration, not an error.

### Changed

- Version bumped from 0.7.0 to 0.8.0.

---

## [0.7.0] — 2026-04-11

### Summary

SAST and static code analysis release. Manual taint analysis traced all user input from CLI and menu entry points through validation to subprocess and file sinks. Two findings identified and remediated: a write-path injection vector via `--logfile` and a silent cert/key mismatch in tunnel mode.

### Security

- **SAST-001 MEDIUM — logfile write-path injection**: `--logfile` value in listen mode flowed directly to socat's `OPEN:` address without path traversal or metacharacter validation. A crafted path (e.g., `--logfile /etc/cron.d/payload`) could direct socat to write captured data to arbitrary filesystem locations. Fixed: listen mode now validates user-provided `--logfile` for path traversal components (`..` in path segments) and shell metacharacters (`;|&$\``) before constructing the socat command. Auto-generated logfile paths (when `--logfile` is omitted) are constructed from controlled constants and do not require validation.

### Fixed

- **SAST-002 LOW — Silent cert/key mismatch in tunnel mode**: Providing `--cert` without `--key` (or vice versa) silently ignored the provided file and generated a new self-signed pair. Users had no indication their certificate was not being used. Fixed: tunnel mode now detects the mismatch, logs a clear warning identifying which file was provided and which was missing, forces generation of a new pair, and advises the user to provide both `--cert` and `--key` together.

### Changed

- Version bumped from 0.6.0 to 0.7.0 across all source modules, test files, and pyproject.toml.

### SAST Audit Verification

The following security properties were confirmed through manual taint analysis:

- Zero `shell=True`, `eval()`, `exec()`, `compile()`, `pickle.load()`, `yaml.load()` in codebase
- All `subprocess.Popen` calls use argument lists with `preexec_fn=os.setsid` and `close_fds=True`
- All `subprocess.run` calls have explicit `timeout=` parameters
- All PID values from session files are validated via `isdigit()` before `int()` conversion and `os.kill()`
- All session file writes use `os.open(0o600)` with `os.fdopen()` for atomic permission setting
- All error log, capture log, and session files use 0o600 permissions
- All security-sensitive directories (sessions/, logs/, certs/) use 0o700 permissions
- `stop_session()` validates SID against path traversal before constructing file paths
- `session_register()` strips newlines from all string values before writing KEY=VALUE pairs
- `generate_self_signed_cert()` sets `umask(0o077)` before openssl execution with `finally` restore
- Standalone runner checks Python version and handles import errors before execution
- `--cn` parameter validated via `validate_session_name()` before reaching openssl subprocess

---

## [0.6.0] — 2026-04-11

### Summary

Secure code audit release. Line-by-line review of all 20 source modules with focus on file permission consistency, path traversal defense, session file injection prevention, and standalone runner hardening. Five findings identified, all remediated.

### Security

- **S-01 MEDIUM — Error log permissions hardened**: `launch_socat_session()` now creates error log files (`session-{sid}-error.log`) with 0o600 permissions via `os.open(O_APPEND, 0o600)`. Previously created with umask-default permissions. Aligns error logs with session files (0o600) and capture logs (0o600) — all three file types now have consistent restrictive permissions.
- **S-02 LOW — stop_session path traversal defense**: `stop_session()` now validates the `sid` parameter against path traversal characters (`/`, `\`, `..`, `\0`) before constructing file paths. All callers already provide validated SIDs, but the function now defends itself as a trust boundary.
- **S-03 LOW — Session register newline injection prevention**: `session_register()` now strips `\n` and `\r` from all string values (`sid`, `name`, `mode`, `proto`, `socat_cmd`, `rhost`, `rport`) before writing to the session file. Prevents theoretical KEY=VALUE injection via crafted inputs. All callers already validate inputs, but the register function is the last line of defense.
- **S-04 MEDIUM — Standalone runner Python version check**: `socat-manager.py` now checks `sys.version_info >= (3, 12)` before importing the package. Python versions below 3.12 now produce a clear error message instead of a raw `SyntaxError` traceback from 3.12+ syntax (union type hints, `match` statements).
- **S-05 LOW — Standalone runner import error handling**: `socat-manager.py` now wraps the package import in `try/except ImportError` with a user-facing error message showing the expected package location. Missing or misconfigured installations no longer produce raw tracebacks.

### Changed

- Version bumped from 0.5.0 to 0.6.0 across all source modules, test files, and pyproject.toml.
- All three build variants (pip install, `python3 -m socat_manager`, `python3 socat-manager.py`) now have equivalent error handling and startup validation.

---

## [0.5.0] — 2026-04-01

### Summary

Code quality audit completion release. Full line-by-line review of all 20 source modules, 20 test files, Makefile, pyproject.toml, socat-manager.py, and .gitignore. All mode handler headers completed with Notes sections. DEVELOPER_GUIDE updated to reflect all v0.2.0–v0.4.0 changes. sync_function.md expanded with complete function cross-reference table and critical call chain documentation.

### Changed

- All 7 mode handler files (`listen.py`, `batch.py`, `forward.py`, `tunnel.py`, `redirect.py`, `status.py`, `modes/__init__.py`) now have `# Notes` sections in their headers documenting key behavioral characteristics.
- Test `__init__.py` marker files (`tests/`, `tests/unit/`, `tests/integration/`) now have header comments.
- DEVELOPER_GUIDE.md updated:
  - `validate_file_path()`: documents component-based traversal, existence check, readability check
  - `validate_hostname()`: documents IPv6 hex group 1-4 char validation
  - `build_socat_redirect_cmd()`: documents keepalive in TCP options
  - `dispatch_mode()`: documents menu case handling
  - `mode_batch()`: documents port deduplication via `sorted(set())`
  - `mode_tunnel()`: documents CN validation via `validate_session_name()`
- `sync_function.md` expanded from 50 to 129 lines with complete function cross-reference table (42 key functions mapped), module dependency graph, and 4 critical call chain diagrams (launch, stop, watchdog, session I/O).
- Version bumped from 0.4.0 to 0.5.0.

---

## [0.4.0] — 2026-04-01

### Summary

Code quality audit remediation release. All previously-noted LOW findings from the v0.3.0 audit are now fully remediated. Validation patterns are now derived from centralized config constants (single source of truth), IPv6 hex group validation enforces RFC-compliant 1–4 character groups, path traversal detection upgraded from substring to path-component analysis, TCP keepalive applied consistently to all bidirectional mode builders, and dispatch_mode handles all mode values.

### Fixed

- **Q-02 to Q-05 — Config-derived validation patterns**: `validation.py` now imports `HOSTNAME_FORBIDDEN_CHARS`, `FILEPATH_FORBIDDEN_CHARS`, `SOCAT_OPTS_WHITELIST`, and `SESSION_NAME_WHITELIST` from `config.py` and derives all regex patterns from them at compile time. Config is the single source of truth for allowed/forbidden character sets. Previously, `validation.py` hardcoded equivalent regex patterns while the config constants sat unused.
- **Q-06 — IPv6 hex group validation**: `validate_hostname()` now validates each non-empty hex group in IPv6 addresses is 1–4 characters via `_IPV6_GROUP_PATTERN`. Addresses like `ffff:12345::` (5-char group) are now correctly rejected. Empty groups from `::` zero-compression remain valid.
- **Q-07 — Path traversal detection upgrade**: `validate_file_path()` changed from substring check (`".." in path`) to path-component check (`".." in path.replace("\\", "/").split("/")"`). Legal filenames containing `..` as a substring (e.g., `file..ext`, `data..backup.log`) are no longer falsely rejected. Only actual path traversal components (`../`, `foo/../../bar`) are caught.
- **Q-12 — TCP keepalive consistency**: `build_socat_forward_cmd()` and `build_socat_redirect_cmd()` now include `keepalive` in TCP listener options, matching `build_socat_listen_cmd()`. All three TCP-capable bidirectional builders consistently produce `reuseaddr,fork,backlog=128,keepalive`. UDP builders remain `reuseaddr,fork` only (keepalive is a TCP concept).
- **Q-14 — dispatch_mode menu handling**: `dispatch_mode()` now explicitly handles `mode='menu'` by importing and calling `interactive_menu()`, instead of falling through to the "Unknown mode" error path. While main() handles menu before reaching dispatch, the menu's `_confirm_and_execute()` calls `dispatch_mode()` directly — this case is now covered.

### Changed

- Version bumped from 0.3.0 to 0.4.0 across all source modules, test files, and pyproject.toml.
- Generated socat commands for TCP forward and redirect now include `keepalive`:
  - Forward: `socat TCP4-LISTEN:8080,reuseaddr,fork,backlog=128,keepalive TCP4:host:port`
  - Redirect: `socat TCP4-LISTEN:8443,reuseaddr,fork,backlog=128,keepalive TCP4:host:port`
- `_SESSION_ID_PATTERN` now uses `SESSION_ID_LENGTH` from config via f-string: `rf"^[a-f0-9]{{{SESSION_ID_LENGTH}}}$"`.
- `_HOSTNAME_FORBIDDEN_PATTERN` and `_FILEPATH_FORBIDDEN_PATTERN` now use `re.escape()` on their config constant values for correct regex character class construction.
- New compiled regex `_IPV6_GROUP_PATTERN` for per-group hex validation.

---

## [0.3.0] — 2026-03-31

### Summary

Technical code quality audit release. Complete line-by-line review of all 20 source modules, 16 test files, Makefile, pyproject.toml, and .gitignore. 14 findings identified: 3 MEDIUM (false dependency, N+1 I/O performance, missing port deduplication), 11 LOW (dead code, minor edge cases, micro-optimization). All MEDIUM findings remediated.

### Fixed

- **Q-01 MEDIUM — False dependency**: Removed `setsid` binary from `REQUIRED_COMMANDS`. The Python variant uses `os.setsid()` via `preexec_fn` — the setsid binary is a bash-only requirement. Dependency check in interactive menu no longer reports a false failure on systems without the setsid binary installed.
- **Q-11 MEDIUM — N+1 I/O in session_list()**: Refactored from 9 individual `session_read_field()` calls per session file to a single `session_read_all_fields()` bulk read. For 20 active sessions, this reduces file I/O operations from 180 to 20 (9× reduction). session_detail() already used the bulk reader; session_list() now matches.
- **Q-13 MEDIUM — Batch port deduplication**: `mode_batch()` now deduplicates and sorts ports before launching. Previously, duplicate ports in `--ports "80,80,443"` would attempt two launches on port 80 (second failing on availability check). Now logs the deduplication count and proceeds with unique sorted ports.

### Changed

- **Q-10**: Moved `import re` from inside `_extract_pids_from_line()` function body to `process.py` module-level import. Eliminates per-call import overhead when processing multiple ss output lines.
- `REQUIRED_COMMANDS` reduced from 4 to 3 entries: `("socat", "openssl", "ss")`. Added inline comment explaining Python's `os.setsid()` usage.
- Version bumped from 0.2.0 to 0.3.0 across all 20 source modules, 16 test files, socat-manager.py, and pyproject.toml.
- Test updated: `test_required_commands` now asserts setsid is NOT in REQUIRED_COMMANDS.

### Noted (not remediated — design decisions or low-impact edge cases)

- **Q-02–05**: Config constants `HOSTNAME_FORBIDDEN_CHARS`, `FILEPATH_FORBIDDEN_CHARS`, `SOCAT_OPTS_WHITELIST`, `SESSION_NAME_WHITELIST` are defined but never imported by `validation.py` (which hardcodes equivalent regex patterns). Retained for documentation value and potential future use.
- **Q-06**: IPv6 validation does not check hex group size (e.g., `ffff:12345::` would pass). Operational impact: none — socat itself rejects malformed IPv6 addresses.
- **Q-07**: Path traversal `".."` check is substring-based, which rejects rare legal filenames like `"file..ext"`. Operational impact: negligible — such filenames are uncommon in operational contexts.
- **Q-08/Q-09**: `setup_logging()` and `verbose_mode` are set in both `main()` and `dispatch_mode()`. Confirmed NOT redundant: `dispatch_mode()` is also called from `menu._confirm_and_execute()` which bypasses `main()`'s logging setup. The `setup_logging()` guard (`if logger.handlers: return`) makes the CLI-path double-call harmless.
- **Q-12**: TCP forward mode does not include `keepalive` socat option (listen mode does). Design decision: listen mode is typically long-lived and benefits from keepalive; forward connections are typically shorter-lived.
- **Q-14**: `dispatch_mode()` does not handle `mode='menu'` — falls to "Unknown mode" error. Menu is handled before dispatch in `main()`. The only other call site (`menu._confirm_and_execute`) only sends operational modes, never "menu". Theoretical edge case only.

---

## [0.2.0] — 2026-03-31

### Summary

Security audit release. Complete line-by-line code audit identified and remediated 9 findings across 7 source modules. Includes behavioral fixes (stop sequence retries, directory permissions), configuration consistency improvements, input validation hardening, and a cryptographic TOCTOU fix.

### Security — Audit Remediations

- **F-01/F-06 MEDIUM**: `stop_session()` now uses `DEFAULTS.stop_verify_retries` (5) instead of hardcoded `retries=3`. The config constant existed but was ignored, creating inconsistency between documented and actual behavior.
- **F-02 MEDIUM**: Renamed `DEFAULTS.watchdog_interval` (value 5, never referenced) to `DEFAULTS.watchdog_poll_interval` (value 1, matching actual `_wait_for_pid_death()` behavior). `_wait_for_pid_death()` now references the constant instead of hardcoding `time.sleep(1)`.
- **F-03 LOW**: `generate_self_signed_cert()` now sets `umask(0o077)` before calling `openssl`, eliminating the TOCTOU window where the private key existed briefly with umask-default permissions before `os.chmod(0o600)`. Original umask is restored in a `finally` block.
- **F-04 MEDIUM**: `validate_file_path()` now verifies file existence (`os.path.isfile()`) and readability (`os.access(R_OK)`) in addition to path traversal and metacharacter checks. Documentation previously claimed these checks existed; now they actually do.
- **F-07/F-08 MEDIUM**: `_ensure_dirs()` now sets `0o700` on `log_dir` and `cert_dir` in addition to `session_dir`. Previously only `session_dir` was hardened despite `cert_dir` containing private keys and `log_dir` containing captured traffic.
- **F-09 HIGH**: `--cn` parameter in tunnel mode is now validated via `validate_session_name()` before reaching `openssl -subj "/CN=..."`. While subprocess argument lists prevent shell injection, unvalidated characters could break openssl X.509 subject parsing. Default CN `localhost` bypasses validation.

### Fixed

- **BUG-04**: `mode_listen()` passed invalid kwargs (`max_restarts`, `backoff_initial`) to `launch_socat_session()` which doesn't accept them. Would cause `TypeError` in real execution. Tests didn't catch it because they mock the function. Removed invalid kwargs — they are correctly used only in `start_watchdog()`.
- `.gitignore` now includes `*.pyc` and `*.pyo` patterns (were covered only by `__pycache__/` directory exclusion).

### Changed

- Version bumped from 0.1.0 to 0.2.0 across all 20 source modules, all 16 test files, and `pyproject.toml`.
- `DEFAULTS.watchdog_interval` (unused, value 5) renamed to `DEFAULTS.watchdog_poll_interval` (value 1) to match actual watchdog behavior.
- `validate_file_path()` now rejects non-existent files and unreadable files (previously only checked path traversal and metacharacters).
- 3 new tests added: `test_nonexistent_rejected`, `test_not_readable_rejected` for `validate_file_path()`, `test_watchdog_poll_interval` replacing `test_watchdog_interval`.
- Test count: 511 passed, 2 skipped (up from 510 passed, 1 skipped).

---

## [0.1.0] — 2026-03-30

### Summary

Initial release of the Python 3.12+ variant. Complete reimplementation of `socat_manager.sh` v2.3.0 (4,470 lines of bash, 91 functions) with full functional parity across all 7 operational modes and 91 functions. Zero external runtime dependencies — Python standard library only.

### Added — Operational Modes

- **`listen` mode**: Start a single TCP/UDP listener with unidirectional data capture to log file. Options: `--port`, `--proto`, `--bind`, `--name`, `--logfile`, `--capture`, `--watchdog`, `--max-restarts`, `--backoff`, `--dual-stack`, `--socat-opts`. TCP listeners include `backlog=128,keepalive`; UDP listeners include `reuseaddr,fork` only.
- **`batch` mode**: Launch multiple listeners from comma-separated port lists (`--ports`), port ranges (`--range START-END`, max 1000 span), or config files (`--file`, one port per line, `#` comments). Ports deduplicated and sorted before launch. Unavailable ports skipped with warning. Each port gets independent session ID. Mode string: `batch-listen`.
- **`forward` mode**: Bidirectional port forwarding between local listener and remote target. Full-duplex (no `-u` flag). Cross-protocol support via `--remote-proto` (e.g., TCP listen → UDP connect). Session name auto-generated as `fwd-{lport}-{rhost}-{rport}`.
- **`tunnel` mode**: TLS-encrypted tunnel via socat OPENSSL-LISTEN. Auto-generates self-signed certificate via `openssl req -x509 -newkey rsa:2048 -nodes -days 365` if `--cert`/`--key` not provided. Rejects `--proto udp` with clear error and guidance. `--proto tcp6` triggers warning, falls back to TCP4. Protocol stored as `tls` in session file. Dual-stack adds plaintext UDP forwarder (mode `tunnel-udp`) with warning that UDP is NOT encrypted.
- **`redirect` mode**: Transparent bidirectional port redirection. Uses `build_socat_redirect_cmd()` which always uses same protocol for both listen and connect sides (no `--remote-proto`). Session name auto-generated as `redir-{proto}-{lport}-{rhost}-{rport}`.
- **`status` mode**: Session list (table format) and detail view (5 sections: metadata, process tree via pstree/ps, port binding via protocol-scoped ss, socat command, associated logs). Target resolution: session ID → session name → port number. `--cleanup` removes dead sessions with advisory lock.
- **`stop` mode**: Session termination via 9-step protocol-scoped stop sequence. Selectors: positional session ID/name, `--all`, `--name`, `--port` (all protocols), `--pid`. Reports orphaned socat processes not tracked by sessions.

### Added — Session Management

- **Session IDs**: 8-character hex strings generated via `uuid.uuid4().hex[:8]` with collision checking against existing session files (up to 100 attempts). Session file format: KEY=VALUE text (version v2.3), cross-variant interoperable with bash.
- **Session fields**: SESSION_ID, SESSION_NAME, PID, PGID, MODE, PROTOCOL, LOCAL_PORT, REMOTE_HOST, REMOTE_PORT, STARTED (ISO 8601), SOCAT_CMD, CORRELATION, LAUNCHER_PID.
- **Exact-key field matching**: `session_read_field()` uses `line.split("=", 1)[0] == field` to prevent PID matching LAUNCHER_PID.
- **Bulk field reader**: `session_read_all_fields()` reads entire session file in single pass, eliminating N+1 I/O problem in `session_detail()`.
- **Advisory file locking**: `session_lock()` context manager using `fcntl.flock` on session directory. If lock acquisition fails, operations proceed with warning (matching bash behavior).
- **Legacy migration**: `migrate_legacy_sessions()` converts v1 `.pid` files to v2.3 `.session` format, deriving PGID from running process via `ps -o pgid=`. Dead legacy sessions removed.
- **Dead session cleanup**: `session_cleanup_dead()` acquires advisory lock, iterates all sessions, removes any where BOTH PID AND PGID are confirmed dead.

### Added — Process Management

- **Process launch**: `launch_socat_session()` uses `subprocess.Popen(cmd, preexec_fn=os.setsid, close_fds=True, stdout=DEVNULL, stderr=<redirect>)`. Returns `(session_id, pid)` tuple. PID accessed directly via `Popen.pid` — no PID-file handoff needed (unlike bash).
- **Stability check**: 0.3-second delay after launch followed by `os.kill(pid, 0)` verification. Reports immediate process death (e.g., port already bound).
- **9-step stop sequence**: (1) Read metadata, (2) Touch `.stop` signal, (3) `os.killpg(pgid, SIGTERM)`, (4) `os.kill(pid, SIGTERM)` + `pkill -TERM -P pid`, (5) Grace period 5s (10 polls at 0.5s), (6) SIGKILL if alive, (7) Protocol-scoped `kill_by_port()` fallback, (8) `check_port_freed(retries=DEFAULTS.stop_verify_retries)`, (9) Session unregister.
- **Process verification**: `kill_by_port()` reads `/proc/{pid}/comm` to verify process name is `socat` before sending SIGKILL. Prevents killing non-socat processes on shared ports.
- **MAX_SESSIONS enforcement**: `session_count()` checked before every launch. Hard limit: 256 concurrent sessions.

### Added — Watchdog

- **Monitor-first design**: Watchdog receives PID of already-running process and monitors via `os.kill(pid, 0)` every 1 second. Never launches the initial process — only re-launches after confirmed death. Eliminates duplicate-launch bug class.
- **Exponential backoff**: Initial delay configurable via `--backoff` (default 1s). Doubles each restart: 1→2→4→8→16→32→60→60... Cap at 60 seconds.
- **Configurable max restarts**: Via `--max-restarts` (default 10). On max restarts reached or launch failure: calls `session_unregister()` and exits thread.
- **Stop coordination**: `.stop` signal file checked after every process death AND before every restart attempt. Prevents restart on deliberate stop.
- **Daemon thread**: Runs as `threading.Thread(daemon=True)`. Automatically cleaned up on main process exit.

### Added — Input Validation and Security

- **9 whitelist validators** at trust boundary: `validate_port()` (numeric, 1-65535, privileged warning), `validate_port_range()` (START-END, max 1000 span), `validate_port_list()` (comma/semicolon separated), `validate_hostname()` (IPv4, IPv6 full/compressed/mixed, RFC 1123, shell metacharacter rejection), `validate_protocol()` (exact set with normalization), `validate_file_path()` (exists, readable, no metacharacters), `validate_socat_opts()` (whitelist `[a-zA-Z0-9=,.:/_-]`), `validate_session_name()` (whitelist `[a-zA-Z0-9._-]`, max 64 chars), `validate_session_id()` (exact `^[a-f0-9]{8}$`).
- **`ValidationError`** exception class (subclass of `ValueError`) with `field` and `value` attributes for structured error reporting.
- **Subprocess security**: `subprocess.Popen` with argument lists only — `shell=True` never appears in codebase. No `eval()`, `exec()`, `compile()`, `__import__()` anywhere.
- **File permissions**: Sessions 0o600, directories 0o700, private keys 0o600, capture logs 0o600. Set explicitly via `os.open()` with mode flags.

### Added — CLI and Interactive Menu

- **10 CLI subcommands** via argparse: listen, batch, forward, tunnel, redirect, status, stop, menu, help, version. `RawDescriptionHelpFormatter` with rich epilog examples on all subcommands.
- **Interactive menu**: 10-option main menu with ASCII banner, per-mode submenus, guided validated input, cancel support (`q`/`quit`/`cancel`/`back`/`exit`) at every prompt, Ctrl+C handling at all levels.
- **Paired forward prompt**: After listener execution, menu asks "Configure a paired forward for this listener?" with listener port pre-filled.
- **Configurable watchdog prompts**: When enabling watchdog in menu, prompted for max restart attempts and initial backoff delay.
- **Socat options examples**: Menu displays examples (`reuseaddr,fork`, `bind=10.0.0.1`, `keepalive,nodelay`) when prompting for extra socat address options.
- **Graceful menu return**: `_confirm_and_execute()` wraps `dispatch_mode()` in try/except catching `SystemExit`, `KeyboardInterrupt`, and generic `Exception`. Menu always returns to main loop after execution.
- **Standalone runner**: `socat-manager.py` — run directly without pip install, venv, or system modification.

### Added — Logging

- **Structured dual-output logging**: File + console via Python's `logging` module. `StructuredFormatter` with correlation IDs, timestamps, levels, component tags.
- **Per-session audit logs**: `logs/session-{sid}.log` for independent audit trails.
- **Capture logs**: `logs/capture-{proto}-{port}-{timestamp}.log` with 0o600 permissions. Contains socat `-v` hex dump output from stderr.
- **Correlation IDs**: 8-character hex string via `uuid.uuid4().hex[:8]` (with SHA-256 timestamp+PID hash as fallback). All log entries within one execution share the same ID.
- **Terminal-aware colors**: ANSI color codes gated on `sys.stderr.isatty()`.

### Added — Testing

- **510 pytest tests** (355 unit + 155 integration), 0 failures, 1 skipped.
- **68% overall coverage** (core modules 85-100%; menu.py lower due to interactive TTY requirement).
- **18 test files** across `tests/unit/` (12 files) and `tests/integration/` (6 files).
- **Test stubs**: Executable mock binaries for socat, ss, and openssl in `tests/stubs/`.
- **Shared fixtures** in `conftest.py`: `paths` (isolated temp dirs), `sample_session` (pre-registered redirect), `dual_stack_sessions` (TCP+UDP on port 8080).

### Added — Build and Documentation

- **Makefile v2.0.0** with 14+ targets: help, check-deps, lint, test, test-unit, test-integration, test-smoke (9 checks), test-coverage, install, uninstall, verify (6-point check), venv, dist, clean, clean-all, docs.
- **26 documentation files**: 11 in `docs/`, 15 in `docs/wiki/`. Source-verified against actual code.
- **DEVELOPER_GUIDE.md** (2,447 lines): AST-generated exhaustive API reference with behavioral narratives for every module, function, class, and constant.
- **pyproject.toml**: setuptools build backend, ruff configuration, pytest options.

### Fixed — Critical Bugs (from Real-World Testing)

- **BUG-01 CRITICAL: Watchdog crash loop**. Watchdog launched duplicate socat on already-bound port causing immediate exit code 1 and restart loop through all 10 attempts. Root cause: watchdog launched its own Popen instead of monitoring the existing PID. Fix: Complete watchdog rewrite to monitor-first architecture — accepts `initial_pid`, polls with `os.kill(pid, 0)`, only re-launches after confirmed death.
- **BUG-02: Dual-stack spawning 2×UDP instead of TCP+UDP**. Root cause was BUG-01 — watchdog re-launching on bound port produced second UDP session instead of TCP. Resolved by watchdog fix.
- **BUG-03: No graceful menu return**. Mode handlers calling `sys.exit(1)` on validation failure killed the entire interactive session. Fix: `_confirm_and_execute()` wraps `dispatch_mode()` in try/except catching `SystemExit`, `KeyboardInterrupt`, and generic `Exception`.
- **BUG-04: Invalid kwargs to launch_socat_session**. `mode_listen()` passed `max_restarts` and `backoff_initial` kwargs to `launch_socat_session()` which doesn't accept them. Would cause TypeError in real execution. Fix: Removed invalid kwargs — they are correctly used only in `start_watchdog()` call.
- **pyproject.toml build-backend**: Was `setuptools.backends._legacy:_Backend` (non-existent). Fixed to `setuptools.build_meta`.

### Known Limitations

- Menu.py coverage is low (32%) because it requires interactive TTY input.
- Watchdog does not update the session file PID after a restart (tracks new PID internally only). Matches bash behavior.
- Self-signed certificates are not trusted by default — clients must use `verify=0`.
- No log rotation — external `logrotate` recommended for production.
- `--bind` flag only available on `listen` mode (not forward/tunnel/redirect).
- `--socat-opts` flag only available on `listen` and `batch` modes.
- `--logfile` flag only available on `listen` mode.
- `--remote-proto` flag only available on `forward` mode.

---

## Python vs Bash Comparison

| Capability | Bash v2.3.0 | Python v0.1.0 |
|-----------|-------------|---------------|
| Session ID generation | `/proc/sys/kernel/random/uuid` first 8 chars | `uuid.uuid4().hex[:8]` |
| Process launch | `setsid bash -c 'echo $$ > pidfile; exec socat'` | `subprocess.Popen(preexec_fn=os.setsid)` |
| PID access | PID-file handoff (poll staging file) | `Popen.pid` (direct access) |
| Watchdog design | `wait $pid` (blocking) then restart | `os.kill(pid, 0)` poll (monitor-first) |
| Watchdog config | Max restarts hardcoded | `--max-restarts`, `--backoff` CLI flags |
| Session return | Global variable `LAUNCH_SID` | Return tuple `(sid, pid)` |
| Threading | Background subshell `&` | `threading.Thread(daemon=True)` |
| Logging | Printf-based structured format | Python `logging` module with `StructuredFormatter` |
| Validation | Bash regex + case statements | Python regex + set membership |
| Field matching | `awk` exact-match | `line.split("=", 1)[0] == field` |
| Interactive menu | Bash `read` + case | Python `input()` + `_MenuCancel` exception |
| Test framework | BATS (220 tests) | pytest (510 tests) |
| Linting | ShellCheck | ruff |
| Runtime dependencies | bash 4.4+, coreutils | Python 3.12+ (stdlib only) |
| External PyPI packages | N/A | 0 at runtime |
| Session file format | KEY=VALUE (v2.3) | KEY=VALUE (v2.3) — interoperable |

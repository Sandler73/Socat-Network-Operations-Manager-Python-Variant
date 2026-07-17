# Development Guide

## Development Environment Setup

```bash
git clone https://github.com/Sandler73/Socat-Network-Operations-Manager.git
cd Socat-Network-Operations-Manager
make venv
source socat-manager-venv/bin/activate
make check-deps
make test
```

## Project Layout

```
src/socat_manager/          # Production source code (21 files, ~6,800 lines)
tests/unit/                 # Unit tests (599 tests) — fast, no I/O
tests/integration/          # Integration tests (158 tests) — cross-module behavior
tests/stubs/                # Mock binaries (socat, ss, openssl)
tests/conftest.py           # Shared fixtures (isolated_base_dir, sample_session)
docs/                       # Documentation (12 files)
docs/wiki/                  # GitHub wiki pages (15 files)
tasks/                      # Project tracking (todo, lessons, bug reports, gap analysis)
```

## Build System

The Makefile provides all build, test, and distribution targets:

```bash
make help              # Show all targets
make lint              # Ruff linter
make test              # Full suite: lint + unit + integration
make test-unit         # Unit tests only (fast)
make test-integration  # Integration tests only
make test-smoke        # Quick import/help/version check
make test-coverage     # Tests with coverage report
make dist              # Build release tarballs
make clean             # Remove build artifacts
```

## Testing

### Test Organization

| Directory | Count | Focus |
|-----------|-------|-------|
| tests/unit/test_validation.py | 70 | 9 whitelist validators, injection attempts |
| tests/unit/test_session.py | 49 | CRUD, exact-key matching, bulk reader, migration |
| tests/unit/test_commands.py | 28 | 4 command builders, protocol variants |
| tests/unit/test_config.py | 44 | Constants, frozen dataclasses, protocol maps |
| tests/unit/test_cli.py | 43 | All subcommands, flags, defaults, help/version |
| tests/unit/test_main.py | 24 | Dispatch, signal handlers, check_socat |
| tests/unit/test_certs.py | 8 | OpenSSL subprocess, error handling |
| tests/unit/test_logging.py | 28 | Formatter, display helpers, session logging |
| tests/unit/test_process.py | 15 | kill_by_port, _is_socat_process, check_port_freed |
| tests/unit/test_watchdog.py | 10 | Backoff, stop signal, max restarts, monitor-first |
| tests/integration/test_lifecycle.py | 22 | Launch→find→stop, max sessions |
| tests/integration/test_dual_stack.py | 14 | Protocol independence, symmetric stop |
| tests/integration/test_capture.py | 15 | -v flag propagation, log permissions |
| tests/integration/test_menu.py | 57 | Cancel detection, prompt validation, submenus |
| tests/integration/test_modes.py | 19 | mode_status, mode_stop (all selectors) |
| tests/integration/test_mode_handlers.py | 31 | All 5 mode handlers end-to-end |

### Test Fixtures (conftest.py)

- **paths**: Creates an isolated temporary base directory with all subdirs (sessions/, logs/, certs/, conf/). Automatically cleaned up after each test.
- **sample_session**: Registers a sample redirect session (PID 99999, port 8443, tcp4).
- **dual_stack_sessions**: Registers TCP + UDP sessions on port 8080.

### Running Tests

```bash
# Full suite with lint:
make test

# Quick unit tests only:
make test-unit

# With coverage:
make test-coverage

# Specific test file:
PYTHONPATH=src python3 -m pytest tests/unit/test_validation.py -v

# Specific test:
PYTHONPATH=src python3 -m pytest tests/unit/test_session.py::TestSessionReadAllFields -v
```

### Writing New Tests

1. Unit tests go in tests/unit/test_<module>.py
2. Integration tests go in tests/integration/test_<feature>.py
3. Use the `paths` fixture for any test that touches the filesystem
4. Mock subprocess.Popen for launch tests, os.kill for stop tests
5. launch_socat_session() returns (sid, pid) tuple — unpack in tests
6. Mock subprocess.run when testing stop_session() (pkill calls)

## CI Pipeline

GitHub Actions runs several workflows on pushes and pull requests:

- **Tests** (`test.yml`): the full suite across 8 Linux platforms — Ubuntu 22.04, Ubuntu 24.04 (Python 3.12 and 3.13), Debian 12, Kali Rolling, Rocky 9, Alma 9, and Arch Linux. Each job installs socat and the optional tools, runs the unit and integration suites, produces a coverage report, and uploads `coverage.xml` as an artifact from the Ubuntu 24.04 job.
- **Lint** (`lint.yml`): the ruff linter (E, W, F, I), the ruff flake8-bandit security scan (S-rules, with the by-design subprocess rules S603/S607 excluded), and a non-blocking mypy type check. Mirrors the `lint`, `security`, and `type-check` Makefile targets.
- **CodeQL** (`codeql.yml`): GitHub's security-and-quality analysis over the Python source, on push, pull request, and a weekly schedule.
- **Dependency Review** (`dependency-review.yml`): inspects dependency changes on pull requests and fails on a high-severity or disallowed-license introduction.
- **Release** (`release.yml`): builds the distributions and publishes a GitHub release when a `v*` tag is pushed.

Each workflow declares least-privilege `permissions` and cancels superseded in-progress runs for the same ref.

## Code Quality

### Linting
```bash
make lint          # ruff E, W, F, I (line length 120, E501 ignored)
make security      # ruff flake8-bandit S-rules (S603/S607 excluded by design)
make type-check    # mypy, if installed
make check         # aggregate gate: lint + security + tests + docs
```

### Type Hints
All functions have complete type annotations. Use `from __future__ import annotations` for forward references.

### Docstrings
Google-style docstrings on all public functions with Args, Returns, Raises sections.

## Release Process

```bash
# 1. Update version in src/socat_manager/__init__.py
# 2. Update docs/CHANGELOG.md
# 3. Run full test suite:
make test
# 4. Build distribution:
make dist
# 5. Tag and push:
git tag -a v1.0.1 -m "Release v1.0.1"
git push origin v1.0.1
```

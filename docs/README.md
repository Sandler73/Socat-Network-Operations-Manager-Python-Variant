# Socat Network Operations Manager — Documentation

## Python Variant v1.0.2

Production-grade Python 3.12+ reimplementation of socat_manager.sh v2.3.0 with full functional parity across all 91 bash functions, 7 operational modes, and full session management.

### Architecture Overview

The framework is organized as a layered architecture:

```
┌─────────────────────────────────────────────────────────┐
│                    Entry Points                         │
│    __main__.py (CLI dispatch)  |  menu.py (TUI)         │
│    socat-manager.py (standalone runner)                 │
├─────────────────────────────────────────────────────────┤
│                    Mode Handlers                        │
│  listen | batch | forward | tunnel | redirect           │
│  status | stop                                          │
├─────────────────────────────────────────────────────────┤
│                    Core Services                        │
│  process.py    - Launch, stop, port checks              │
│  session.py    - CRUD, lookup, locking, migration       │
│  watchdog.py   - Monitor + auto-restart                 │
│  commands.py   - Socat command string builders          │
│  certs.py      - TLS certificate generation             │
├─────────────────────────────────────────────────────────┤
│                    Foundation                           │
│  config.py       - Constants, dataclasses, protocol maps│
│  validation.py   - 9 whitelist input validators         │
│  logging_setup.py- Structured dual-output logging       │
└─────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Zero external runtime dependencies** — Python standard library only
2. **Defense-in-depth security** — whitelist validators, no eval/exec/shell=True
3. **Process group isolation** — each socat in its own setsid group
4. **Protocol-scoped operations** — stopping TCP never affects UDP
5. **Session interoperability** — KEY=VALUE files readable by bash variant
6. **Graceful degradation** — optional tools (pstree, ss) improve output but aren't required

### Documentation Index

| File | Purpose |
|------|---------|
| [USAGE_GUIDE.md](USAGE_GUIDE.md) | All operational modes with examples |
| [SETUP_GUIDE.md](SETUP_GUIDE.md) | Installation, configuration, environment |
| [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) | Exhaustive code reference (every function, class, variable) |
| [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) | Development workflow, testing, CI pipelines |
| [SECURITY.md](SECURITY.md) | Security policy, threat model, vulnerability reporting |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute (issues, PRs, coding standards) |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues, error codes, resolution steps |
| [Frequently_Asked_Questions_(FAQ).md](Frequently_Asked_Questions_(FAQ).md) | FAQ |
| [CHANGELOG.md](CHANGELOG.md) | Version history with all changes |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Community behavior standards |
| [LICENSE](../LICENSE) | MIT License with supplemental sections |

### Wiki

The [docs/wiki/](wiki/) directory contains GitHub Wiki-compatible pages:

| Page | Purpose |
|------|---------|
| [Home](wiki/Home.md) | Wiki landing page |
| [Architecture-and-Design](wiki/Architecture-and-Design.md) | Detailed Mermaid diagrams |
| [Quick-Start-Guide](wiki/Quick-Start-Guide.md) | 5-minute getting started |
| [Usage-Guide](wiki/Usage-Guide.md) | Full operational reference |
| [Configuration-Reference](wiki/Configuration-Reference.md) | All config constants |
| [Operational-Scenarios](wiki/Operational-Scenarios.md) | Real-world deployment examples |
| [Security-Policy](wiki/Security-Policy.md) | STRIDE threat model |
| [Developer-Guide](wiki/Developer-Guide.md) | API reference |
| [Development-Guide](wiki/Development-Guide.md) | Build and test workflow |
| [Troubleshooting-Guide](wiki/Troubleshooting-Guide.md) | Problem resolution |
| [FAQ](wiki/Frequently-Asked-Questions-(FAQ).md) | Common questions |
| [Contributing](wiki/Contributing.md) | Contribution process |
| [Changelog](wiki/Changelog.md) | Release notes |

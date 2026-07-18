#!/usr/bin/env python3
# ==============================================================================
# SCRIPT      : socat-manager.py
# ==============================================================================
# Synopsis    : Standalone launcher for the Socat Network Operations Manager
#               (Python variant) — run the tool without installing it.
# Description : A thin, dependency-free bootstrap around the socat_manager
#               package. It verifies the interpreter meets the minimum version,
#               prepends the bundled src/ directory to sys.path so
#               `import socat_manager` resolves against the in-tree source
#               rather than any installed copy, defaults the runtime base
#               directory (SOCAT_MANAGER_BASE) to the project root so logs,
#               sessions, certificates, and the audit store are created
#               alongside the code, and then delegates to
#               socat_manager.__main__.main(). All argument parsing, dispatch,
#               logging, and mode handling live in the package; this launcher
#               adds no behavior of its own beyond environment setup.
# Notes       : - No pip install required; the package is imported from src/.
#               - Resolves paths relative to this script, so it works from any
#                 working directory.
#               - Honors a pre-set SOCAT_MANAGER_BASE; only defaults it when the
#                 variable is absent.
#               - Requires Python 3.12+ (matches requires-python in
#                 pyproject.toml); exits with a clear message on older runtimes.
#               - Exits non-zero with a diagnostic if the package cannot be
#                 imported (for example, a moved or incomplete src/ tree).
#               - The installed console entry point (`socat-manager`, via
#                 pyproject.toml) is the packaged equivalent of this launcher.
# Execution   : python3 socat-manager.py [MODE] [OPTIONS]
#   Parameters:
#     MODE      One of: listen, batch, forward, tunnel, redirect, status, stop,
#               audit, menu, help, version. Omit MODE to open the interactive
#               menu. Each mode's options are shown by `<MODE> --help`.
#     OPTIONS   Mode-specific flags (see `--help`), plus the common controls
#               --log-level/-q, --no-audit, and (on listener modes) --allow and
#               --tcpwrap.
# Examples    :
#   python3 socat-manager.py                                  # interactive menu
#   python3 socat-manager.py --help                           # top-level help
#   python3 socat-manager.py listen --port 8080               # TCP listener
#   python3 socat-manager.py listen --port 5353 --proto udp4  # UDP listener
#   python3 socat-manager.py listen --port 8080 --allow 10.0.0.0/8
#   python3 socat-manager.py forward --lport 8080 --rhost 10.0.0.5 --rport 80
#   python3 socat-manager.py tunnel --port 4443 --rhost 10.0.0.5 --rport 22
#   python3 socat-manager.py status
#   python3 socat-manager.py stop --all
#   python3 socat-manager.py audit --history
#   SOCAT_MANAGER_BASE=/var/lib/socat-mgr python3 socat-manager.py status
# Version     : 1.0.2
# ==============================================================================

"""Standalone launcher for socat-manager — no pip install required."""

import os
import sys
from pathlib import Path

# Minimum Python version required (matches pyproject.toml requires-python)
_MIN_PYTHON: tuple[int, int] = (3, 12)


def main() -> None:
    """Set up paths and launch socat-manager."""
    # Check Python version before attempting any imports that use 3.12+ syntax
    if sys.version_info < _MIN_PYTHON:
        print(
            f"Error: socat-manager requires Python {_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}+, "
            f"found {sys.version_info.major}.{sys.version_info.minor}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve script location
    script_dir: Path = Path(__file__).resolve().parent

    # Add src/ to Python path so 'import socat_manager' works
    src_dir: Path = script_dir / "src"
    if src_dir.is_dir():
        sys.path.insert(0, str(src_dir))

    # Set SOCAT_MANAGER_BASE to the script directory if not already set
    # This ensures logs/, sessions/, certs/ are created relative to the project
    if "SOCAT_MANAGER_BASE" not in os.environ:
        os.environ["SOCAT_MANAGER_BASE"] = str(script_dir)

    # Import and run — wrapped in try/except for clear error on missing package
    try:
        from socat_manager.__main__ import main as app_main
    except ImportError as exc:
        print(
            f"Error: Cannot import socat_manager package: {exc}\n"
            f"Verify the src/socat_manager/ directory exists at: {src_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    app_main()


if __name__ == "__main__":
    main()

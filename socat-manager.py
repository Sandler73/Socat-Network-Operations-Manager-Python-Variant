#!/usr/bin/env python3
# ==============================================================================
# SCRIPT      : socat-manager.py
# ==============================================================================
# Synopsis    : Standalone launcher for Socat Network Operations Manager
# Description : Allows running socat-manager directly without pip install.
#               Sets up the Python path to find the src/socat_manager package
#               and delegates to __main__.main().
#
# Execution   : python3 socat-manager.py [MODE] [OPTIONS]
#               python3 socat-manager.py                    (interactive menu)
#               python3 socat-manager.py listen --port 8080
#               python3 socat-manager.py --help
#               python3 socat-manager.py help
#               python3 socat-manager.py version
#
# Notes       : - No pip install required
#               - Automatically adds src/ to sys.path
#               - Works from any directory (resolves paths relative to script)
#               - Set SOCAT_MANAGER_BASE env var to override the working directory
#
# Version     : 0.9.0
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

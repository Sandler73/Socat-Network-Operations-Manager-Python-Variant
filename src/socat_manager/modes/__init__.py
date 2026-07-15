# ==============================================================================
# MODULE      : socat_manager/modes/__init__.py
# ==============================================================================
# Synopsis    : Operational mode handlers for the Socat Network Operations Manager
# Description : Subpackage containing one module per operational mode:
#               listen, batch, forward, tunnel, redirect, status, stop.
#               Each module exposes a single entry-point function that
#               handles argument parsing and mode execution.
#
# Notes       : - Mode handlers are imported lazily in dispatch_mode()
#               - Each handler accepts an argparse Namespace
#
# Version     : 0.9.0
# ==============================================================================

"""Operational mode handlers for socat-manager."""

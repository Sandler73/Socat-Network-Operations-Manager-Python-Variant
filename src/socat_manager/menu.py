# ==============================================================================
# MODULE      : socat_manager/menu.py
# ==============================================================================
# Synopsis    : Interactive menu system for socat-manager
# Description : Full-featured interactive menu with ASCII art SOCAT banner,
#               numbered mode selection, per-mode submenus collecting every
#               parameter with validation, cancel support (q/quit/cancel/back),
#               and confirmation before execution. Exact parity with bash
#               interactive_menu() and all _menu_* functions (lines 3567-4390).
#
# Notes       : - All prompts write to stderr (matches bash)
#               - Cancel at any prompt returns to root menu
#               - Input validated inline before acceptance
#               - Confirmation shows constructed command before execution
#               - Dependency check shows all required/optional commands
#
# Version     : 0.9.0
# ==============================================================================

"""Interactive menu system for socat-manager."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from socat_manager import __version__
from socat_manager.config import (
    COLORS,
    OPTIONAL_COMMANDS,
    REQUIRED_COMMANDS,
    SCRIPT_NAME,
)
from socat_manager.logging_setup import (
    USE_COLOR,
    _ensure_dirs,
)
from socat_manager.validation import (
    ValidationError,
    validate_hostname,
    validate_port,
    validate_protocol,
    validate_session_name,
    validate_socat_opts,
)

# ==============================================================================
# CANCEL SENTINEL
# ==============================================================================

class _MenuCancel(Exception):
    """Raised when user enters a cancel keyword at any menu prompt."""
    pass


_CANCEL_KEYWORDS: frozenset[str] = frozenset({"q", "quit", "cancel", "back", "exit"})


def _is_cancel(text: str) -> bool:
    """Check if user input is a cancel keyword."""
    return text.strip().lower() in _CANCEL_KEYWORDS


# ==============================================================================
# PROMPT HELPERS
# ==============================================================================

def _prompt(text: str, default: str = "") -> str:
    """Display a prompt and read input. Raises _MenuCancel on cancel keywords.

    Args:
        text: Prompt text to display.
        default: Default value if user presses Enter.

    Returns:
        User input or default value.

    Raises:
        _MenuCancel: If user enters a cancel keyword.
    """
    if default:
        if USE_COLOR:
            prompt_str = f"  {COLORS.bold}{text}{COLORS.reset} [{COLORS.dim}{default}{COLORS.reset}]: "
        else:
            prompt_str = f"  {text} [{default}]: "
    else:
        if USE_COLOR:
            prompt_str = f"  {COLORS.bold}{text}{COLORS.reset}: "
        else:
            prompt_str = f"  {text}: "

    try:
        value: str = input(prompt_str)
    except (EOFError, KeyboardInterrupt):
        print("", file=sys.stderr)
        raise _MenuCancel()

    if _is_cancel(value):
        raise _MenuCancel()

    return value.strip() if value.strip() else default


def _prompt_yn(text: str, default: str = "n") -> bool:
    """Prompt for a yes/no answer. Raises _MenuCancel on cancel.

    Args:
        text: Prompt text.
        default: Default answer ('y' or 'n').

    Returns:
        True for yes, False for no.

    Raises:
        _MenuCancel: On cancel keyword.
    """
    hint: str = "Y/n" if default == "y" else "y/N"

    while True:
        if USE_COLOR:
            prompt_str = f"  {COLORS.bold}{text}{COLORS.reset} [{hint}]: "
        else:
            prompt_str = f"  {text} [{hint}]: "

        try:
            value: str = input(prompt_str)
        except (EOFError, KeyboardInterrupt):
            print("", file=sys.stderr)
            raise _MenuCancel()

        if _is_cancel(value):
            raise _MenuCancel()

        answer: str = (value.strip() or default).lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False

        _print_error("Please enter y or n")


def _prompt_choice(text: str, max_val: int, default: str = "") -> int:
    """Prompt for a numbered choice. Raises _MenuCancel on cancel.

    Args:
        text: Prompt text.
        max_val: Maximum valid selection number.
        default: Default selection.

    Returns:
        Selected number.
    """
    while True:
        value: str = _prompt(text, default)
        if value.isdigit():
            num: int = int(value)
            if 0 <= num <= max_val:
                return num
        _print_error(f"Invalid selection '{value}'. Enter 0-{max_val}.")


def _prompt_port(text: str = "Port", default: str = "") -> int:
    """Prompt for a validated port number."""
    while True:
        value: str = _prompt(text, default)
        try:
            return validate_port(value)
        except ValidationError:
            _print_error(f"Invalid port '{value}'. Must be 1-65535.")


def _prompt_host(text: str = "Host", default: str = "") -> str:
    """Prompt for a validated hostname/IP."""
    while True:
        value: str = _prompt(text, default)
        try:
            return validate_hostname(value)
        except ValidationError:
            _print_error(f"Invalid hostname/IP: '{value}'")


def _prompt_protocol(text: str = "Protocol", default: str = "tcp4") -> str:
    """Prompt for a validated protocol."""
    while True:
        value: str = _prompt(text, default)
        try:
            return validate_protocol(value)
        except ValidationError:
            _print_error("Valid: tcp, tcp4, tcp6, udp, udp4, udp6")


def _prompt_name(text: str = "Session name", default: str = "") -> str:
    """Prompt for a validated session name (optional — empty returns default)."""
    value: str = _prompt(text, default)
    if not value:
        return default
    try:
        return validate_session_name(value)
    except ValidationError:
        _print_error(f"Invalid name '{value}'. Allowed: alphanumeric, . _ -")
        return _prompt_name(text, default)


# ==============================================================================
# DISPLAY HELPERS
# ==============================================================================

def _print_error(msg: str) -> None:
    """Print an error message to stderr."""
    if USE_COLOR:
        print(f"  {COLORS.red}{msg}{COLORS.reset}", file=sys.stderr)
    else:
        print(f"  {msg}", file=sys.stderr)


def _menu_header(title: str) -> None:
    """Print a boxed submenu header."""
    width: int = 56
    bar: str = "═" * width
    if USE_COLOR:
        c, r = COLORS.bold + COLORS.cyan, COLORS.reset
        print(f"\n  {c}╔{bar}╗{r}", file=sys.stderr)
        print(f"  {c}║{r}  {title:<{width - 2}s}{c}║{r}", file=sys.stderr)
        print(f"  {c}╚{bar}╝{r}\n", file=sys.stderr)
    else:
        print(f"\n  ╔{bar}╗", file=sys.stderr)
        print(f"  ║  {title:<{width - 2}s}║", file=sys.stderr)
        print(f"  ╚{bar}╝\n", file=sys.stderr)


def _cancel_hint() -> None:
    """Print the cancel hint line."""
    if USE_COLOR:
        print(f"  {COLORS.dim}(Type 'q' at any prompt to cancel and return to menu){COLORS.reset}\n", file=sys.stderr)
    else:
        print("  (Type 'q' at any prompt to cancel and return to menu)\n", file=sys.stderr)


def _cancelled() -> None:
    """Print the cancelled message."""
    if USE_COLOR:
        print(f"\n  {COLORS.yellow}Cancelled — returning to menu.{COLORS.reset}\n", file=sys.stderr)
    else:
        print("\n  Cancelled — returning to menu.\n", file=sys.stderr)


def _pause() -> None:
    """Wait for user to press Enter."""
    try:
        input("\n  Press Enter to continue...")
    except (EOFError, KeyboardInterrupt):
        pass


def _menu_banner() -> None:
    """Display the ASCII art SOCAT banner."""
    if USE_COLOR:
        c, r, d = COLORS.cyan + COLORS.bold, COLORS.reset, COLORS.dim
    else:
        c, r, d = "", "", ""

    print(f"\n  {c}", file=sys.stderr)
    print("    ╔═══════════════════════════════════════════════════════════╗", file=sys.stderr)
    print("    ║                                                           ║", file=sys.stderr)
    print("    ║   ███████  ██████   ██████  █████  ████████               ║", file=sys.stderr)
    print("    ║   ██      ██    ██ ██      ██   ██    ██                  ║", file=sys.stderr)
    print("    ║   ███████ ██    ██ ██      ███████    ██                  ║", file=sys.stderr)
    print("    ║        ██ ██    ██ ██      ██   ██    ██                  ║", file=sys.stderr)
    print("    ║   ███████  ██████   ██████ ██   ██    ██                  ║", file=sys.stderr)
    print("    ║                                                           ║", file=sys.stderr)
    print("    ║     N E T W O R K   O P E R A T I O N S   M A N A G E R  ║", file=sys.stderr)
    print("    ║                                                           ║", file=sys.stderr)
    print(f"    ╚═══════════════════════════════════════════════════════════╝{r}", file=sys.stderr)

    now_str: str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    user: str = os.environ.get("USER", os.environ.get("LOGNAME", "unknown"))
    print(f"  {d}  Version {__version__}  •  {now_str}  •  User: {user}{r}", file=sys.stderr)


# ==============================================================================
# COMMON FLAG COLLECTION
# ==============================================================================

def _collect_common_flags(
    args: list[str],
    offer_protocol: bool = True,
    offer_dualstack: bool = True,
) -> None:
    """Collect common flags shared across operational modes.

    Mutates the args list in place by appending collected flags.
    When watchdog is enabled, prompts for max restart attempts and
    backoff delay interval.

    Args:
        args: Command argument list to append to.
        offer_protocol: Whether to offer protocol selection.
        offer_dualstack: Whether to offer dual-stack option.

    Raises:
        _MenuCancel: On cancel at any prompt.
    """
    # Protocol selection
    if offer_protocol:
        proto: str = _prompt_protocol("Protocol", "tcp4")
        if proto != "tcp4":
            args.extend(["--proto", proto])

    # Dual-stack
    if offer_dualstack:
        if _prompt_yn("Enable dual-stack (TCP + UDP)?"):
            args.append("--dual-stack")

    # Capture
    if _prompt_yn("Enable traffic capture?"):
        args.append("--capture")

    # Watchdog with configurable parameters
    if _prompt_yn("Enable watchdog auto-restart?"):
        args.append("--watchdog")

        # Max restart attempts
        max_str: str = _prompt("Max restart attempts", "10")
        if max_str and max_str.isdigit() and max_str != "10":
            args.extend(["--max-restarts", max_str])

        # Backoff delay
        backoff_str: str = _prompt("Initial backoff delay (seconds)", "1")
        if backoff_str and backoff_str.isdigit() and backoff_str != "1":
            args.extend(["--backoff", backoff_str])

    # Session name
    name: str = _prompt_name("Session name (Enter for default)")
    if name:
        args.extend(["--name", name])


# ==============================================================================
# PER-MODE SUBMENUS
# ==============================================================================

def _menu_listen() -> list[str] | None:
    """Listen mode submenu. Returns args list or None on cancel.

    After listener configuration, offers to configure a paired forward
    to simplify operational setup.
    """
    _menu_header("Listen Mode — Single TCP/UDP Listener")
    _cancel_hint()

    port: int = _prompt_port("Listen port")
    args: list[str] = ["listen", "--port", str(port)]

    _collect_common_flags(args, offer_protocol=True, offer_dualstack=True)

    # Bind address
    if _prompt_yn("Bind to a specific address?"):
        bind_addr: str = _prompt_host("Bind address", "0.0.0.0")
        args.extend(["--bind", bind_addr])

    # Socat opts with examples
    if _prompt_yn("Provide extra socat address options?"):
        print("", file=sys.stderr)
        if USE_COLOR:
            d = COLORS.dim
            r = COLORS.reset
            print(f"  {d}Examples:{r}", file=sys.stderr)
            print(f"  {d}  reuseaddr,fork       — reuse port, fork per connection{r}", file=sys.stderr)
            print(f"  {d}  bind=10.0.0.1        — bind to specific interface{r}", file=sys.stderr)
            print(f"  {d}  keepalive,nodelay     — enable TCP keepalive + no-delay{r}", file=sys.stderr)
        else:
            print("  Examples:", file=sys.stderr)
            print("    reuseaddr,fork       — reuse port, fork per connection", file=sys.stderr)
            print("    bind=10.0.0.1        — bind to specific interface", file=sys.stderr)
            print("    keepalive,nodelay     — enable TCP keepalive + no-delay", file=sys.stderr)
        print("", file=sys.stderr)

        while True:
            sopts: str = _prompt("Socat options")
            try:
                validate_socat_opts(sopts)
                args.extend(["--socat-opts", sopts])
                break
            except ValidationError:
                _print_error("Invalid characters. Allowed: alphanumeric, = , . : / _ -")

    return args


def _menu_batch() -> list[str] | None:
    """Batch mode submenu."""
    _menu_header("Batch Mode — Multiple Listeners")
    _cancel_hint()

    print("  Port source:", file=sys.stderr)
    print("    1) Comma-separated list", file=sys.stderr)
    print("    2) Port range (START-END)", file=sys.stderr)
    print("    3) Config file", file=sys.stderr)

    source: int = _prompt_choice("Select source", 3, "1")

    args: list[str] = ["batch"]

    if source == 1:
        ports_str: str = _prompt("Port list (e.g., 21,22,80,443)")
        args.extend(["--ports", ports_str])
    elif source == 2:
        range_str: str = _prompt("Port range (e.g., 8000-8010)")
        args.extend(["--range", range_str])
    elif source == 3:
        file_path: str = _prompt("Config file path")
        args.extend(["--file", file_path])

    _collect_common_flags(args, offer_protocol=True, offer_dualstack=True)
    return args


def _menu_forward() -> list[str] | None:
    """Forward mode submenu."""
    _menu_header("Forward Mode — Bidirectional Relay")
    _cancel_hint()

    lport: int = _prompt_port("Local port")
    rhost: str = _prompt_host("Remote host")
    rport: int = _prompt_port("Remote port")

    args: list[str] = ["forward", "--lport", str(lport), "--rhost", rhost, "--rport", str(rport)]

    _collect_common_flags(args, offer_protocol=True, offer_dualstack=True)

    # Remote protocol
    if _prompt_yn("Use different protocol for remote connection?"):
        rp: str = _prompt_protocol("Remote protocol")
        args.extend(["--remote-proto", rp])

    return args


def _menu_tunnel() -> list[str] | None:
    """Tunnel mode submenu."""
    _menu_header("Tunnel Mode — TLS Encrypted Tunnel")
    _cancel_hint()

    lport: int = _prompt_port("Local TLS port")
    rhost: str = _prompt_host("Remote host")
    rport: int = _prompt_port("Remote port")

    args: list[str] = ["tunnel", "--port", str(lport), "--rhost", rhost, "--rport", str(rport)]

    # Certificate
    if _prompt_yn("Provide your own certificate?"):
        cert: str = _prompt("Certificate PEM path")
        key: str = _prompt("Private key PEM path")
        args.extend(["--cert", cert, "--key", key])
    else:
        cn: str = _prompt("Certificate CN", "localhost")
        if cn != "localhost":
            args.extend(["--cn", cn])

    # Capture and watchdog (no protocol/dual-stack for tunnel primary)
    if _prompt_yn("Enable traffic capture?"):
        args.append("--capture")
    if _prompt_yn("Enable watchdog auto-restart?"):
        args.append("--watchdog")
    if _prompt_yn("Add plaintext UDP forwarder (dual-stack)?"):
        args.append("--dual-stack")

    name: str = _prompt_name("Session name (Enter for default)")
    if name:
        args.extend(["--name", name])

    return args


def _menu_redirect() -> list[str] | None:
    """Redirect mode submenu."""
    _menu_header("Redirect Mode — Transparent Redirection")
    _cancel_hint()

    lport: int = _prompt_port("Local port")
    rhost: str = _prompt_host("Remote host")
    rport: int = _prompt_port("Remote port")

    args: list[str] = ["redirect", "--lport", str(lport), "--rhost", rhost, "--rport", str(rport)]

    _collect_common_flags(args, offer_protocol=True, offer_dualstack=True)
    return args


def _menu_status() -> list[str] | None:
    """Status mode submenu."""
    _menu_header("Session Status")
    _cancel_hint()

    print("  Options:", file=sys.stderr)
    print("    1) Show all sessions", file=sys.stderr)
    print("    2) Show specific session", file=sys.stderr)
    print("    3) Cleanup dead sessions", file=sys.stderr)

    choice: int = _prompt_choice("Select", 3, "1")

    if choice == 1:
        return ["status"]
    elif choice == 2:
        target: str = _prompt("Session ID, name, or port")
        return ["status", target]
    elif choice == 3:
        return ["status", "--cleanup"]

    return ["status"]


def _menu_stop() -> list[str] | None:
    """Stop mode submenu."""
    _menu_header("Stop Sessions")
    _cancel_hint()

    print("  Stop by:", file=sys.stderr)
    print("    1) Session ID", file=sys.stderr)
    print("    2) Session name", file=sys.stderr)
    print("    3) Port number", file=sys.stderr)
    print("    4) PID", file=sys.stderr)
    print("    5) Stop ALL sessions", file=sys.stderr)

    choice: int = _prompt_choice("Select", 5, "1")

    if choice == 1:
        sid: str = _prompt("Session ID")
        return ["stop", sid]
    elif choice == 2:
        name: str = _prompt("Session name")
        return ["stop", "--name", name]
    elif choice == 3:
        port: str = _prompt("Port number")
        return ["stop", "--port", port]
    elif choice == 4:
        pid: str = _prompt("PID")
        return ["stop", "--pid", pid]
    elif choice == 5:
        if _prompt_yn("Stop ALL sessions?"):
            return ["stop", "--all"]
        return None

    return None


def _menu_check_deps() -> None:
    """Display dependency check results."""
    _menu_header("Dependency Check")

    print("  Required:", file=sys.stderr)
    for cmd_name in REQUIRED_COMMANDS:
        path: str | None = shutil.which(cmd_name)
        if path:
            # Try to get version info
            version: str = ""
            try:
                if cmd_name == "socat":
                    result = subprocess.run(
                        ["socat", "-V"], capture_output=True, text=True, timeout=5,
                    )
                    lines = result.stdout.strip().splitlines()
                    if len(lines) >= 2:
                        version = lines[1].strip()
                else:
                    result = subprocess.run(
                        [cmd_name, "--version"], capture_output=True, text=True, timeout=5,
                    )
                    if result.stdout.strip():
                        version = result.stdout.strip().splitlines()[0]
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass

            status_str: str = f"✓ {path}"
            if version:
                status_str += f" ({version})"
            if USE_COLOR:
                print(f"    {COLORS.green}{status_str}{COLORS.reset}", file=sys.stderr)
            else:
                print(f"    {status_str}", file=sys.stderr)
        else:
            if USE_COLOR:
                print(f"    {COLORS.red}✗ {cmd_name} — NOT FOUND{COLORS.reset}", file=sys.stderr)
            else:
                print(f"    ✗ {cmd_name} — NOT FOUND", file=sys.stderr)

    print("\n  Optional:", file=sys.stderr)
    for cmd_name in OPTIONAL_COMMANDS:
        path = shutil.which(cmd_name)
        if path:
            if USE_COLOR:
                print(f"    {COLORS.green}✓ {path}{COLORS.reset}", file=sys.stderr)
            else:
                print(f"    ✓ {path}", file=sys.stderr)
        else:
            if USE_COLOR:
                print(f"    {COLORS.dim}- {cmd_name} (optional, not found){COLORS.reset}", file=sys.stderr)
            else:
                print(f"    - {cmd_name} (optional, not found)", file=sys.stderr)

    _pause()


# ==============================================================================
# CONFIRMATION AND EXECUTION
# ==============================================================================

def _confirm_and_execute(args: list[str], dispatch_fn: object) -> None:
    """Show the constructed command, confirm, and execute.

    Wraps execution in try/except to ensure graceful return to menu
    on any error including SystemExit and KeyboardInterrupt. Watchdog
    threads are daemon=True so they continue in background without
    blocking the menu return.

    After executing a listener, offers to configure a paired forward.

    Args:
        args: The command arguments (mode + flags).
        dispatch_fn: Unused (kept for API compatibility).
    """
    cmd_display: str = f"{SCRIPT_NAME} {' '.join(args)}"

    if USE_COLOR:
        print(f"\n  {COLORS.bold}Command:{COLORS.reset} {cmd_display}\n", file=sys.stderr)
    else:
        print(f"\n  Command: {cmd_display}\n", file=sys.stderr)

    if _prompt_yn("Execute?"):
        # Import here to avoid circular imports
        from socat_manager.__main__ import dispatch_mode
        from socat_manager.cli import build_parser

        parser = build_parser()
        parsed = parser.parse_args(args)

        try:
            dispatch_mode(parsed)
        except SystemExit:
            # Mode handler called sys.exit() on error — catch and return to menu
            pass
        except KeyboardInterrupt:
            print("", file=sys.stderr)
        except Exception as exc:
            _print_error(f"Execution error: {exc}")

        # Offer paired forward after listener execution
        is_listen: bool = len(args) > 0 and args[0] == "listen"
        if is_listen:
            _offer_paired_forward(args)
    else:
        if USE_COLOR:
            print(f"  {COLORS.yellow}Cancelled.{COLORS.reset}", file=sys.stderr)
        else:
            print("  Cancelled.", file=sys.stderr)

    _pause()


def _offer_paired_forward(listener_args: list[str]) -> None:
    """Offer to configure a paired forward after a listener is launched.

    Pre-fills the local port from the listener configuration to
    simplify operational setup.

    Args:
        listener_args: The listener command arguments that were just executed.
    """
    try:
        if not _prompt_yn("\n  Configure a paired forward for this listener?"):
            return
    except _MenuCancel:
        return

    # Extract port from listener args
    listen_port: str = ""
    for i, arg in enumerate(listener_args):
        if arg in ("--port", "-p") and i + 1 < len(listener_args):
            listen_port = listener_args[i + 1]
            break

    try:
        _menu_header("Paired Forward Configuration")
        _cancel_hint()

        if listen_port:
            print(f"  Local port pre-filled from listener: {listen_port}", file=sys.stderr)
            lport: int = int(listen_port)
        else:
            lport = _prompt_port("Local port")

        rhost: str = _prompt_host("Remote host (forward destination)")
        rport: int = _prompt_port("Remote port")

        fwd_args: list[str] = [
            "forward", "--lport", str(lport),
            "--rhost", rhost, "--rport", str(rport),
        ]
        _collect_common_flags(fwd_args, offer_protocol=True, offer_dualstack=False)

        _confirm_and_execute(fwd_args, None)
    except _MenuCancel:
        _cancelled()


# ==============================================================================
# HELP DISPLAY
# ==============================================================================

def _menu_show_help() -> None:
    """Display full help with narrative sections.

    Matches the bash show_main_help() output with full operational
    details, session management explanation, protocol selection guide,
    reliability features, logging paths, and CLI usage examples.
    """
    from socat_manager import __version__

    _menu_header("Socat Network Operations Manager — Help")

    help_text: str = f"""
  VERSION
    socat-manager v{__version__}

  DESCRIPTION
    Session-managed socat network operations across seven modes.
    All sessions are tracked, independently manageable, and survive
    terminal disconnects via process group isolation (setsid).

  OPERATIONAL MODES
    listen      Start a single TCP/UDP listener on a port
    batch       Start multiple listeners (port list, range, or config)
    forward     Forward local port to remote host:port (bidirectional)
    tunnel      Create encrypted (TLS/SSL) tunnel via socat + OpenSSL
    redirect    Redirect/proxy traffic with optional capture
    status      Display all active managed sessions
    stop        Stop sessions (by ID, name, port, PID, or all)

  SESSION MANAGEMENT
    Each socat process is assigned a unique 8-character hex Session ID.
    Sessions are tracked via .session metadata files in the sessions/
    directory. Each file records: Session ID, PID, PGID, mode, protocol,
    ports, full socat command, start time, and correlation ID.

    Processes are launched in isolated process groups (via setsid) for
    reliable cross-invocation tracking. The management script returns
    to the prompt immediately after launching — sessions persist in
    the background.

  PROTOCOL SELECTION
    --proto <PROTOCOL>   Select a single protocol:
                         tcp, tcp4, tcp6, udp, udp4, udp6
                         Default: tcp4

    --dual-stack         Launch sessions on BOTH TCP and UDP.
                         Each protocol gets its own session ID for
                         independent management. Stopping TCP does
                         NOT affect UDP on the same port.

  RELIABILITY
    --watchdog           Enable auto-restart with exponential backoff.
    --max-restarts N     Set max restart attempts (default: 10).
    --backoff N          Set initial backoff delay in seconds (default: 1).
                         Backoff doubles each restart: 1s, 2s, 4s... 60s cap.

  LOGGING
    Master execution log:  logs/socat-manager-<timestamp>.log
    Per-listener data:     logs/listener-<proto>-<port>.log
    Session-specific:      logs/session-<sid>.log
    Traffic capture:       logs/capture-<proto>-<port>-<timestamp>.log

  CLI EXAMPLES
    socat-manager listen --port 8080
    socat-manager listen --port 5353 --proto udp4
    socat-manager listen --port 8080 --dual-stack --capture
    socat-manager batch --ports 21,22,80,443
    socat-manager batch --range 8000-8010 --watchdog
    socat-manager forward --lport 8080 --rhost 10.0.0.5 --rport 80
    socat-manager tunnel --port 4443 --rhost 10.0.0.5 --rport 22
    socat-manager redirect --lport 8443 --rhost example.com --rport 443
    socat-manager status
    socat-manager status abcd1234
    socat-manager stop --all
    socat-manager stop --port 8080
    socat-manager help
    socat-manager version

  DEPENDENCIES
    Required:     socat
    Optional:     openssl (tunnel mode), ss (status), pstree (detail)
    Install:      sudo apt-get install -y socat openssl iproute2
"""
    print(help_text, file=sys.stderr)
    _pause()


# ==============================================================================
# MAIN MENU LOOP
# ==============================================================================

def interactive_menu() -> None:
    """Main interactive menu loop.

    Displays the root menu, dispatches to submenus, and loops
    until the user exits (option 0).
    """
    _ensure_dirs()

    while True:
        _menu_banner()

        print("", file=sys.stderr)
        if USE_COLOR:
            c, r = COLORS.cyan, COLORS.reset
            b = COLORS.bold
            print(f"  {b}Operational Modes:{r}", file=sys.stderr)
            print(f"    {c}1){r}  Listen     — Start a TCP/UDP listener", file=sys.stderr)
            print(f"    {c}2){r}  Batch      — Launch multiple listeners", file=sys.stderr)
            print(f"    {c}3){r}  Forward    — Relay traffic to a remote host", file=sys.stderr)
            print(f"    {c}4){r}  Tunnel     — Create a TLS-encrypted tunnel", file=sys.stderr)
            print(f"    {c}5){r}  Redirect   — Transparent port redirection", file=sys.stderr)
            print("", file=sys.stderr)
            print(f"  {b}Status & Management:{r}", file=sys.stderr)
            print(f"    {c}6){r}  Session Status", file=sys.stderr)
            print(f"    {c}7){r}  Stop Sessions", file=sys.stderr)
            print("", file=sys.stderr)
            print(f"  {b}System:{r}", file=sys.stderr)
            print(f"    {c}8){r}  Check Dependencies", file=sys.stderr)
            print(f"    {c}9){r}  Help / CLI Usage", file=sys.stderr)
            print(f"    {c}0){r}  Exit", file=sys.stderr)
        else:
            print("  Operational Modes:", file=sys.stderr)
            print("    1)  Listen     — Start a TCP/UDP listener", file=sys.stderr)
            print("    2)  Batch      — Launch multiple listeners", file=sys.stderr)
            print("    3)  Forward    — Relay traffic to a remote host", file=sys.stderr)
            print("    4)  Tunnel     — Create a TLS-encrypted tunnel", file=sys.stderr)
            print("    5)  Redirect   — Transparent port redirection", file=sys.stderr)
            print("", file=sys.stderr)
            print("  Status & Management:", file=sys.stderr)
            print("    6)  Session Status", file=sys.stderr)
            print("    7)  Stop Sessions", file=sys.stderr)
            print("", file=sys.stderr)
            print("  System:", file=sys.stderr)
            print("    8)  Check Dependencies", file=sys.stderr)
            print("    9)  Help / CLI Usage", file=sys.stderr)
            print("    0)  Exit", file=sys.stderr)

        try:
            choice: int = _prompt_choice("Select", 9)
        except _MenuCancel:
            continue
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C or Ctrl+D at main menu prompt — exit gracefully
            if USE_COLOR:
                print(f"\n\n  {COLORS.dim}Goodbye.{COLORS.reset}\n", file=sys.stderr)
            else:
                print("\n\n  Goodbye.\n", file=sys.stderr)
            return

        # Submenu dispatch map
        submenu_map: dict[int, object] = {
            1: _menu_listen,
            2: _menu_batch,
            3: _menu_forward,
            4: _menu_tunnel,
            5: _menu_redirect,
            6: _menu_status,
            7: _menu_stop,
        }

        if choice == 0:
            if USE_COLOR:
                print(f"\n  {COLORS.dim}Goodbye.{COLORS.reset}\n", file=sys.stderr)
            else:
                print("\n  Goodbye.\n", file=sys.stderr)
            return

        if choice == 8:
            _menu_check_deps()
            continue

        if choice == 9:
            _menu_show_help()
            continue

        submenu = submenu_map.get(choice)
        if submenu:
            try:
                result = submenu()  # type: ignore[operator]
                if result:
                    _confirm_and_execute(result, None)
            except _MenuCancel:
                _cancelled()
            except KeyboardInterrupt:
                # Ctrl+C during submenu or execution — return to menu
                print("", file=sys.stderr)

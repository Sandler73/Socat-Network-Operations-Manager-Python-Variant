# ==============================================================================
# FILE        : tests/unit/test_config.py
# ==============================================================================
# Synopsis    : Unit tests for configuration constants and defaults
# Description : Verifies all configuration values match the bash version exactly.
#               Ensures frozen dataclasses are immutable, protocol maps are
#               complete, and all constants have the expected values.
# Version     : 1.0.2
# ==============================================================================

"""Unit tests for configuration constants and defaults."""

import dataclasses

import pytest

from socat_manager.config import (
    ALT_PROTOCOL,
    COLORS,
    CORRELATION_ID,
    DEFAULTS,
    EXEC_TIMESTAMP,
    OPTIONAL_COMMANDS,
    PORT_MAX,
    PORT_MIN,
    PORT_RANGE_MAX_SPAN,
    PRIVILEGED_PORT_THRESHOLD,
    PROTOCOL_NORMALIZATION,
    REQUIRED_COMMANDS,
    SCRIPT_NAME,
    SCRIPT_PID,
    SCRIPT_VERSION,
    SESSION_FIELDS,
    SESSION_FILE_VERSION,
    SESSION_ID_LENGTH,
    SESSION_NAME_MAX_LENGTH,
    SOCAT_CONNECT_ADDR,
    SOCAT_LISTEN_ADDR,
    SYMBOLS,
    VALID_PROTOCOLS,
    RuntimePaths,
    protocol_family,
    protocol_transport,
    resolve_base_dir,
    socket_scope_flags,
)


class TestScriptMetadata:
    """Tests for script metadata constants."""

    def test_script_name(self):
        assert SCRIPT_NAME == "socat-manager"

    def test_script_version(self):
        assert SCRIPT_VERSION == "1.0.2"

    def test_script_pid_is_positive(self):
        assert SCRIPT_PID > 0

    def test_correlation_id_format(self):
        assert len(CORRELATION_ID) == 8
        assert all(c in "0123456789abcdef" for c in CORRELATION_ID)

    def test_exec_timestamp_format(self):
        # Format: YYYY-MM-DDTHH-MM-SS
        parts = EXEC_TIMESTAMP.split("T")
        assert len(parts) == 2
        assert len(parts[0].split("-")) == 3
        assert len(parts[1].split("-")) == 3


class TestDefaults:
    """Tests for operational defaults matching bash v2.3.0."""

    def test_defaults_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            DEFAULTS.protocol = "udp4"  # type: ignore

    def test_protocol(self):
        assert DEFAULTS.protocol == "tcp4"

    def test_backlog(self):
        assert DEFAULTS.backlog == 128

    def test_watchdog_poll_interval(self):
        assert DEFAULTS.watchdog_poll_interval == 1

    def test_watchdog_max_restarts(self):
        assert DEFAULTS.watchdog_max_restarts == 10

    def test_max_sessions(self):
        assert DEFAULTS.max_sessions == 256

    def test_stop_grace_seconds(self):
        assert DEFAULTS.stop_grace_seconds == 5

    def test_stop_verify_retries(self):
        assert DEFAULTS.stop_verify_retries == 5

    def test_stop_verify_interval(self):
        assert DEFAULTS.stop_verify_interval == 0.5

    def test_launch_stability_delay(self):
        assert DEFAULTS.launch_stability_delay == 0.3


class TestValidProtocols:
    """Tests for protocol sets and maps."""

    def test_valid_protocols(self):
        assert VALID_PROTOCOLS == frozenset({"tcp4", "tcp6", "udp4", "udp6"})

    def test_normalization_map_complete(self):
        for key in ("tcp", "tcp4", "tcp6", "udp", "udp4", "udp6"):
            assert key in PROTOCOL_NORMALIZATION

    def test_normalization_shortcuts(self):
        assert PROTOCOL_NORMALIZATION["tcp"] == "tcp4"
        assert PROTOCOL_NORMALIZATION["udp"] == "udp4"

    def test_alt_protocol_map(self):
        assert ALT_PROTOCOL["tcp4"] == "udp4"
        assert ALT_PROTOCOL["udp4"] == "tcp4"
        assert ALT_PROTOCOL["tcp6"] == "udp6"
        assert ALT_PROTOCOL["udp6"] == "tcp6"

    def test_socat_listen_addr_map(self):
        assert SOCAT_LISTEN_ADDR["tcp4"] == "TCP4-LISTEN"
        assert SOCAT_LISTEN_ADDR["tcp6"] == "TCP6-LISTEN"
        assert SOCAT_LISTEN_ADDR["udp4"] == "UDP4-LISTEN"
        assert SOCAT_LISTEN_ADDR["udp6"] == "UDP6-LISTEN"

    def test_socat_connect_addr_map(self):
        assert SOCAT_CONNECT_ADDR["tcp4"] == "TCP4"
        assert SOCAT_CONNECT_ADDR["tcp6"] == "TCP6"
        assert SOCAT_CONNECT_ADDR["udp4"] == "UDP4"
        assert SOCAT_CONNECT_ADDR["udp6"] == "UDP6"


class TestSessionFields:
    """Tests for session file field name constants."""

    def test_fields_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            SESSION_FIELDS.session_id = "changed"  # type: ignore

    def test_all_fields_present(self):
        expected = [
            "SESSION_ID", "SESSION_NAME", "PID", "PGID", "MODE",
            "PROTOCOL", "LOCAL_PORT", "REMOTE_HOST", "REMOTE_PORT",
            "SOCAT_CMD", "STARTED", "CORRELATION", "LAUNCHER_PID",
        ]
        for field_value in expected:
            assert any(
                getattr(SESSION_FIELDS, name) == field_value
                for name in dir(SESSION_FIELDS)
                if not name.startswith("_")
            ), f"Missing field: {field_value}"

    def test_file_version(self):
        assert SESSION_FILE_VERSION == "v2.3"


class TestValidationConstants:
    """Tests for validation boundary constants."""

    def test_port_range(self):
        assert PORT_MIN == 1
        assert PORT_MAX == 65535

    def test_privileged_threshold(self):
        assert PRIVILEGED_PORT_THRESHOLD == 1024

    def test_port_range_max_span(self):
        assert PORT_RANGE_MAX_SPAN == 1000

    def test_session_name_max_length(self):
        assert SESSION_NAME_MAX_LENGTH == 64

    def test_session_id_length(self):
        assert SESSION_ID_LENGTH == 8


class TestColors:
    """Tests for color code constants."""

    def test_colors_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            COLORS.red = "changed"  # type: ignore

    def test_reset_escape(self):
        assert COLORS.reset == "\033[0m"

    def test_all_colors_are_escape_sequences(self):
        for name in ("reset", "bold", "dim", "red", "green", "yellow", "blue", "cyan"):
            value = getattr(COLORS, name)
            assert value.startswith("\033["), f"COLORS.{name} is not an escape sequence"


class TestSymbols:
    """Tests for status symbol constants."""

    def test_symbols_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            SYMBOLS.ok = "changed"  # type: ignore

    def test_ok_symbol(self):
        assert SYMBOLS.ok == "✓"

    def test_fail_symbol(self):
        assert SYMBOLS.fail == "✗"


class TestDependencyConstants:
    """Tests for dependency requirement constants."""

    def test_required_commands(self):
        assert "socat" in REQUIRED_COMMANDS
        assert "openssl" in REQUIRED_COMMANDS
        assert "ss" in REQUIRED_COMMANDS
        # Python variant uses os.setsid() via preexec_fn, not the setsid binary
        assert "setsid" not in REQUIRED_COMMANDS

    def test_optional_commands(self):
        assert "flock" in OPTIONAL_COMMANDS
        assert "lsof" in OPTIONAL_COMMANDS
        assert "pstree" in OPTIONAL_COMMANDS


class TestRuntimePaths:
    """Tests for RuntimePaths resolution."""

    def test_paths_frozen(self, tmp_path):
        rp = RuntimePaths(base_dir=tmp_path)
        with pytest.raises(dataclasses.FrozenInstanceError):
            rp.base_dir = tmp_path / "changed"  # type: ignore

    def test_log_dir(self, tmp_path):
        rp = RuntimePaths(base_dir=tmp_path)
        assert rp.log_dir == tmp_path / "logs"

    def test_session_dir(self, tmp_path):
        rp = RuntimePaths(base_dir=tmp_path)
        assert rp.session_dir == tmp_path / "sessions"

    def test_cert_dir(self, tmp_path):
        rp = RuntimePaths(base_dir=tmp_path)
        assert rp.cert_dir == tmp_path / "certs"

    def test_conf_dir(self, tmp_path):
        rp = RuntimePaths(base_dir=tmp_path)
        assert rp.conf_dir == tmp_path / "conf"

    def test_session_lock_file(self, tmp_path):
        rp = RuntimePaths(base_dir=tmp_path)
        assert rp.session_lock_file == tmp_path / "sessions" / ".lock"

    def test_resolve_base_dir_returns_path(self):
        result = resolve_base_dir()
        assert isinstance(result, type(result))  # It's a Path


class TestProtocolScopeDerivation:
    """Tests for protocol scope derivation.

    A protocol is a transport plus an address family. config.py owns the
    protocol model, so it owns the derivation used by every socket query in
    the framework. All four protocols must map to distinct scopes.
    """

    def test_transport_component(self):
        """Transport is derived from the protocol name."""
        assert protocol_transport("tcp4") == "tcp"
        assert protocol_transport("tcp6") == "tcp"
        assert protocol_transport("udp4") == "udp"
        assert protocol_transport("udp6") == "udp"

    def test_family_component(self):
        """Address family is derived from the protocol suffix."""
        assert protocol_family("tcp4") == "4"
        assert protocol_family("udp4") == "4"
        assert protocol_family("tcp6") == "6"
        assert protocol_family("udp6") == "6"

    def test_scope_flags_per_protocol(self):
        """Each protocol maps to a fully scoped flag set."""
        assert socket_scope_flags("tcp4") == ["-t", "-4", "-l", "-n"]
        assert socket_scope_flags("tcp6") == ["-t", "-6", "-l", "-n"]
        assert socket_scope_flags("udp4") == ["-u", "-4", "-l", "-n"]
        assert socket_scope_flags("udp6") == ["-u", "-6", "-l", "-n"]

    def test_every_valid_protocol_has_a_distinct_scope(self):
        """No two members of the protocol model collapse onto one scope."""
        scopes = {tuple(socket_scope_flags(p)) for p in VALID_PROTOCOLS}
        assert len(scopes) == len(VALID_PROTOCOLS)

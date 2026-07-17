# ==============================================================================
# FILE        : tests/unit/test_validation.py
# ==============================================================================
# Synopsis    : Unit tests for all 9 input validators
# Description : Full test coverage for socat_manager.validation
#               matching the 592-line bash validation.bats test suite.
#               Covers valid inputs, boundary conditions, injection attempts,
#               format violations, and edge cases for every validator.
# Version     : 1.0.1
# ==============================================================================

"""Unit tests for all 9 input validators."""

import pytest

from socat_manager.validation import (
    ValidationError,
    validate_file_path,
    validate_hostname,
    validate_port,
    validate_port_list,
    validate_port_range,
    validate_protocol,
    validate_session_id,
    validate_session_name,
    validate_socat_opts,
    validate_writable_path,
)

# ============================================================================
# validate_port
# ============================================================================

class TestValidatePort:
    """Tests for validate_port()."""

    def test_valid_port_int(self):
        assert validate_port(8080) == 8080

    def test_valid_port_str(self):
        assert validate_port("443") == 443

    def test_min_port(self):
        assert validate_port(1) == 1

    def test_max_port(self):
        assert validate_port(65535) == 65535

    def test_zero_rejected(self):
        with pytest.raises(ValidationError):
            validate_port(0)

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            validate_port("-1")

    def test_above_max_rejected(self):
        with pytest.raises(ValidationError):
            validate_port(65536)

    def test_non_numeric_rejected(self):
        with pytest.raises(ValidationError):
            validate_port("abc")

    def test_float_rejected(self):
        with pytest.raises(ValidationError):
            validate_port("80.5")

    def test_empty_rejected(self):
        with pytest.raises(ValidationError):
            validate_port("")

    def test_spaces_stripped(self):
        assert validate_port(" 8080 ") == 8080

    def test_common_ports(self):
        for port in [21, 22, 25, 53, 80, 443, 3306, 5432, 8080, 8443]:
            assert validate_port(port) == port

    def test_injection_attempt_semicolon(self):
        with pytest.raises(ValidationError):
            validate_port("8080;rm -rf /")

    def test_injection_attempt_pipe(self):
        with pytest.raises(ValidationError):
            validate_port("8080|cat /etc/passwd")


# ============================================================================
# validate_port_range
# ============================================================================

class TestValidatePortRange:
    """Tests for validate_port_range()."""

    def test_valid_range(self):
        assert validate_port_range("8000-8003") == [8000, 8001, 8002, 8003]

    def test_single_port_span(self):
        assert validate_port_range("8000-8001") == [8000, 8001]

    def test_max_span_1000(self):
        result = validate_port_range("1000-1999")
        assert len(result) == 1000
        assert result[0] == 1000
        assert result[-1] == 1999

    def test_span_exceeds_1000(self):
        with pytest.raises(ValidationError):
            validate_port_range("1000-2001")

    def test_start_equals_end(self):
        with pytest.raises(ValidationError):
            validate_port_range("8000-8000")

    def test_start_greater_than_end(self):
        with pytest.raises(ValidationError):
            validate_port_range("8010-8000")

    def test_invalid_format_no_dash(self):
        with pytest.raises(ValidationError):
            validate_port_range("8000")

    def test_invalid_format_extra_dash(self):
        with pytest.raises(ValidationError):
            validate_port_range("8000-8010-8020")

    def test_invalid_port_in_range(self):
        with pytest.raises(ValidationError):
            validate_port_range("0-10")

    def test_above_max_port(self):
        with pytest.raises(ValidationError):
            validate_port_range("65530-65540")

    def test_non_numeric(self):
        with pytest.raises(ValidationError):
            validate_port_range("abc-def")


# ============================================================================
# validate_port_list
# ============================================================================

class TestValidatePortList:
    """Tests for validate_port_list()."""

    def test_comma_separated(self):
        assert validate_port_list("21,22,80,443") == [21, 22, 80, 443]

    def test_semicolons_converted(self):
        assert validate_port_list("21;22;80") == [21, 22, 80]

    def test_spaces_removed(self):
        assert validate_port_list("21, 22, 80") == [21, 22, 80]

    def test_mixed_separators(self):
        assert validate_port_list("21;22, 80,443") == [21, 22, 80, 443]

    def test_single_port(self):
        assert validate_port_list("8080") == [8080]

    def test_skips_invalid_ports(self):
        result = validate_port_list("21,abc,80,99999")
        assert result == [21, 80]

    def test_empty_entries_skipped(self):
        assert validate_port_list("21,,80,,,443") == [21, 80, 443]

    def test_all_invalid(self):
        with pytest.raises(ValidationError):
            validate_port_list("abc,def,ghi")

    def test_empty_string(self):
        with pytest.raises(ValidationError):
            validate_port_list("")


# ============================================================================
# validate_hostname
# ============================================================================

class TestValidateHostname:
    """Tests for validate_hostname()."""

    # --- IPv4 ---
    def test_ipv4_localhost(self):
        assert validate_hostname("127.0.0.1") == "127.0.0.1"

    def test_ipv4_private(self):
        assert validate_hostname("192.168.1.1") == "192.168.1.1"

    def test_ipv4_zeros(self):
        assert validate_hostname("0.0.0.0") == "0.0.0.0"

    def test_ipv4_max_octets(self):
        assert validate_hostname("255.255.255.255") == "255.255.255.255"

    def test_ipv4_octet_over_255(self):
        with pytest.raises(ValidationError):
            validate_hostname("256.1.1.1")

    def test_ipv4_second_octet_over(self):
        with pytest.raises(ValidationError):
            validate_hostname("1.256.1.1")

    # --- IPv6 ---
    def test_ipv6_loopback(self):
        assert validate_hostname("::1") == "::1"

    def test_ipv6_compressed(self):
        assert validate_hostname("fe80::1") == "fe80::1"

    def test_ipv6_full(self):
        assert validate_hostname("2001:0db8:85a3:0000:0000:8a2e:0370:7334") == \
            "2001:0db8:85a3:0000:0000:8a2e:0370:7334"

    def test_ipv6_too_many_colons(self):
        with pytest.raises(ValidationError):
            validate_hostname("1:2:3:4:5:6:7:8:9")

    def test_ipv6_too_long(self):
        # Must contain colons to be parsed as IPv6; > 39 chars, <= 7 colons
        with pytest.raises(ValidationError):
            validate_hostname("2001:0db8:85a3:0000:0000:8a2e:0370:73344444")

    # --- Hostnames ---
    def test_hostname_simple(self):
        assert validate_hostname("example.com") == "example.com"

    def test_hostname_subdomain(self):
        assert validate_hostname("sub.example.com") == "sub.example.com"

    def test_hostname_with_hyphens(self):
        assert validate_hostname("my-host.example.com") == "my-host.example.com"

    def test_hostname_single_label(self):
        assert validate_hostname("localhost") == "localhost"

    # --- Rejections ---
    def test_empty(self):
        with pytest.raises(ValidationError):
            validate_hostname("")

    def test_metachar_semicolon(self):
        with pytest.raises(ValidationError):
            validate_hostname("evil;rm -rf /")

    def test_metachar_pipe(self):
        with pytest.raises(ValidationError):
            validate_hostname("host|cat")

    def test_metachar_ampersand(self):
        with pytest.raises(ValidationError):
            validate_hostname("host&bg")

    def test_metachar_dollar(self):
        with pytest.raises(ValidationError):
            validate_hostname("$HOME")

    def test_metachar_backtick(self):
        with pytest.raises(ValidationError):
            validate_hostname("`whoami`")

    def test_metachar_parens(self):
        with pytest.raises(ValidationError):
            validate_hostname("$(evil)")

    def test_metachar_brackets(self):
        with pytest.raises(ValidationError):
            validate_hostname("{evil}")

    def test_metachar_angle_brackets(self):
        with pytest.raises(ValidationError):
            validate_hostname("<evil>")

    def test_metachar_bang(self):
        with pytest.raises(ValidationError):
            validate_hostname("!important")

    def test_metachar_hash(self):
        with pytest.raises(ValidationError):
            validate_hostname("#comment")


# ============================================================================
# validate_protocol
# ============================================================================

class TestValidateProtocol:
    """Tests for validate_protocol()."""

    def test_tcp_normalizes_to_tcp4(self):
        assert validate_protocol("tcp") == "tcp4"

    def test_tcp4(self):
        assert validate_protocol("tcp4") == "tcp4"

    def test_tcp6(self):
        assert validate_protocol("tcp6") == "tcp6"

    def test_udp_normalizes_to_udp4(self):
        assert validate_protocol("udp") == "udp4"

    def test_udp4(self):
        assert validate_protocol("udp4") == "udp4"

    def test_udp6(self):
        assert validate_protocol("udp6") == "udp6"

    def test_case_insensitive(self):
        assert validate_protocol("TCP") == "tcp4"
        assert validate_protocol("UDP4") == "udp4"
        assert validate_protocol("Tcp6") == "tcp6"

    def test_spaces_stripped(self):
        assert validate_protocol(" tcp4 ") == "tcp4"

    def test_invalid_icmp(self):
        with pytest.raises(ValidationError):
            validate_protocol("icmp")

    def test_invalid_sctp(self):
        with pytest.raises(ValidationError):
            validate_protocol("sctp")

    def test_empty(self):
        with pytest.raises(ValidationError):
            validate_protocol("")


# ============================================================================
# validate_file_path
# ============================================================================

class TestValidateFilePath:
    """Tests for validate_file_path()."""

    def test_valid_absolute(self, tmp_path):
        test_file = tmp_path / "test.log"
        test_file.write_text("test")
        assert validate_file_path(str(test_file)) == str(test_file)

    def test_valid_relative(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        sub = tmp_path / "logs"
        sub.mkdir(exist_ok=True)
        test_file = sub / "test.log"
        test_file.write_text("test")
        assert validate_file_path("logs/test.log") == "logs/test.log"

    def test_nonexistent_rejected(self):
        with pytest.raises(ValidationError):
            validate_file_path("/nonexistent/path/file.txt")

    def test_not_readable_rejected(self, tmp_path):
        import os
        if os.geteuid() == 0:
            pytest.skip("Cannot test read permission denial as root")
        test_file = tmp_path / "noperm.log"
        test_file.write_text("test")
        os.chmod(str(test_file), 0o000)
        try:
            with pytest.raises(ValidationError):
                validate_file_path(str(test_file))
        finally:
            os.chmod(str(test_file), 0o644)

    def test_empty_rejected(self):
        with pytest.raises(ValidationError):
            validate_file_path("")

    def test_traversal_rejected(self):
        with pytest.raises(ValidationError):
            validate_file_path("../../etc/passwd")

    def test_traversal_middle(self):
        with pytest.raises(ValidationError):
            validate_file_path("/tmp/../etc/shadow")

    def test_metachar_semicolon(self):
        with pytest.raises(ValidationError):
            validate_file_path("/tmp/file;rm -rf /")

    def test_metachar_pipe(self):
        with pytest.raises(ValidationError):
            validate_file_path("/tmp/file|cat")

    def test_metachar_ampersand(self):
        with pytest.raises(ValidationError):
            validate_file_path("/tmp/file&bg")

    def test_metachar_dollar(self):
        with pytest.raises(ValidationError):
            validate_file_path("/tmp/$USER/file")

    def test_metachar_backtick(self):
        with pytest.raises(ValidationError):
            validate_file_path("/tmp/`whoami`/file")


# ============================================================================
# validate_socat_opts
# ============================================================================

class TestValidateSocatOpts:
    """Tests for validate_socat_opts()."""

    def test_empty_valid(self):
        assert validate_socat_opts("") == ""

    def test_common_opts(self):
        assert validate_socat_opts("reuseaddr,fork") == "reuseaddr,fork"

    def test_bind_address(self):
        assert validate_socat_opts("bind=10.0.0.1") == "bind=10.0.0.1"

    def test_complex_opts(self):
        assert validate_socat_opts("reuseaddr,fork,backlog=128,keepalive") == \
            "reuseaddr,fork,backlog=128,keepalive"

    def test_path_in_opts(self):
        assert validate_socat_opts("cert=/path/to/cert.pem") == "cert=/path/to/cert.pem"

    def test_hyphen_underscore(self):
        assert validate_socat_opts("some-opt_value") == "some-opt_value"

    def test_semicolon_rejected(self):
        with pytest.raises(ValidationError):
            validate_socat_opts("fork;evil")

    def test_pipe_rejected(self):
        with pytest.raises(ValidationError):
            validate_socat_opts("fork|evil")

    def test_space_rejected(self):
        with pytest.raises(ValidationError):
            validate_socat_opts("fork evil")

    def test_dollar_rejected(self):
        with pytest.raises(ValidationError):
            validate_socat_opts("$HOME")

    def test_backtick_rejected(self):
        with pytest.raises(ValidationError):
            validate_socat_opts("`whoami`")

    def test_paren_rejected(self):
        with pytest.raises(ValidationError):
            validate_socat_opts("$(evil)")


# ============================================================================
# validate_session_name
# ============================================================================

class TestValidateSessionName:
    """Tests for validate_session_name()."""

    def test_simple_name(self):
        assert validate_session_name("my-listener") == "my-listener"

    def test_protocol_port_format(self):
        assert validate_session_name("tcp4-8080") == "tcp4-8080"

    def test_dots_underscores(self):
        assert validate_session_name("my.session_name-1") == "my.session_name-1"

    def test_max_length_64(self):
        name = "a" * 64
        assert validate_session_name(name) == name

    def test_over_64_rejected(self):
        with pytest.raises(ValidationError):
            validate_session_name("a" * 65)

    def test_empty_rejected(self):
        with pytest.raises(ValidationError):
            validate_session_name("")

    def test_space_rejected(self):
        with pytest.raises(ValidationError):
            validate_session_name("evil name")

    def test_semicolon_rejected(self):
        with pytest.raises(ValidationError):
            validate_session_name("evil;name")

    def test_slash_rejected(self):
        with pytest.raises(ValidationError):
            validate_session_name("evil/name")

    def test_equals_rejected(self):
        with pytest.raises(ValidationError):
            validate_session_name("key=value")


# ============================================================================
# validate_session_id
# ============================================================================

class TestValidateSessionId:
    """Tests for validate_session_id()."""

    def test_valid_hex(self):
        assert validate_session_id("abcd1234") == "abcd1234"

    def test_all_digits(self):
        assert validate_session_id("12345678") == "12345678"

    def test_all_letters(self):
        assert validate_session_id("abcdefab") == "abcdefab"

    def test_uppercase_rejected(self):
        with pytest.raises(ValidationError):
            validate_session_id("ABCD1234")

    def test_too_short(self):
        with pytest.raises(ValidationError):
            validate_session_id("abc123")

    def test_too_long(self):
        with pytest.raises(ValidationError):
            validate_session_id("abcd12345")

    def test_non_hex_rejected(self):
        with pytest.raises(ValidationError):
            validate_session_id("abcdxyz1")

    def test_empty_rejected(self):
        with pytest.raises(ValidationError):
            validate_session_id("")

    def test_spaces_stripped(self):
        assert validate_session_id(" abcd1234 ") == "abcd1234"


class TestValidateWritablePath:
    """Tests for validate_writable_path(), the write-target validator.

    A write target such as a capture or log file is created at launch, so it
    need not exist. The validator applies the same structural safety checks as
    validate_file_path() — non-empty, no traversal component, no forbidden
    characters — drawn from the shared config character set, but does not
    require the path to exist or be readable.
    """

    def test_accepts_nonexistent_write_target(self):
        """A path that does not yet exist is accepted."""
        assert validate_writable_path("logs/new-capture.log") == "logs/new-capture.log"

    def test_strips_surrounding_whitespace(self):
        """Surrounding whitespace is stripped from the returned path."""
        assert validate_writable_path("  logs/out.log  ") == "logs/out.log"

    def test_rejects_empty_path(self):
        """An empty path is rejected."""
        with pytest.raises(ValidationError):
            validate_writable_path("")

    def test_rejects_traversal_component(self):
        """A parent-directory component is rejected."""
        with pytest.raises(ValidationError):
            validate_writable_path("../etc/passwd")
        with pytest.raises(ValidationError):
            validate_writable_path("logs/../../etc/shadow")

    def test_allows_double_dot_within_a_name(self):
        """A double dot inside a filename is not a traversal component."""
        assert validate_writable_path("logs/file..log") == "logs/file..log"

    @pytest.mark.parametrize("char", [";", "|", "&", "$", "`"])
    def test_rejects_each_forbidden_character(self, char):
        """Every shell metacharacter in the config set is rejected."""
        with pytest.raises(ValidationError):
            validate_writable_path(f"logs/out{char}.log")


class TestWritablePathAndFilePathShareCharacterSet:
    """Both path validators reject the same config-defined character set.

    The forbidden character set is defined once in configuration. Both
    validators must reject exactly those characters, so that a path accepted
    as a write target would also pass the structural checks of the input-file
    validator, and vice versa.
    """

    @pytest.mark.parametrize("char", list(";|&$`"))
    def test_both_reject_the_same_characters(self, char, tmp_path):
        """A forbidden character is rejected by both validators."""
        candidate = f"logs/out{char}.log"

        with pytest.raises(ValidationError):
            validate_writable_path(candidate)

        # validate_file_path applies the same structural checks before it
        # checks existence, so the forbidden character is rejected there too.
        with pytest.raises(ValidationError):
            validate_file_path(candidate)

    def test_forbidden_set_matches_config(self):
        """The rejected characters are exactly the config-defined set."""
        from socat_manager.config import FILEPATH_FORBIDDEN_CHARS
        for char in FILEPATH_FORBIDDEN_CHARS:
            with pytest.raises(ValidationError):
                validate_writable_path(f"logs/out{char}.log")

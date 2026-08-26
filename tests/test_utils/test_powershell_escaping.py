"""Escaping at the substitution boundary (SEC-20 / SEC-17 regression).

``substitute_placeholders`` used to be a raw ``str.replace``: a request-derived
value containing ``'`` broke out of the single-quoted PowerShell literal it was
substituted into (``$newVal = '%value%'``) and ran arbitrary elevated code.
These tests pin that every value is escaped for the quoting context its
placeholder sits in, and that an unquoted placeholder only ever accepts a
plain keyword/number token.
"""

from __future__ import annotations

import pytest

from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.utils.powershell import substitute_placeholders


class TestSingleQuotedContext:
    """Values landing inside '...' must stay inside, whatever they contain."""

    def test_plain_value_is_substituted_verbatim(self):
        out = substitute_placeholders("$action = '%value%'", value="enable")
        assert out == "$action = 'enable'"

    def test_single_quote_cannot_close_the_literal(self):
        """The original breakout: '; <attacker code>; ' ran as code before the fix."""
        hostile = "x'; Remove-Item -Recurse C:\\Users; '"
        out = substitute_placeholders("$newVal = '%value%'", value=hostile)
        assert out == "$newVal = 'x''; Remove-Item -Recurse C:\\Users; '''"

    def test_subexpression_stays_inert_text(self):
        """$() does not evaluate in single quotes, so it must be left as-is."""
        out = substitute_placeholders("$key = '%key%'", key="$(Start-Process calc)")
        assert out == "$key = '$(Start-Process calc)'"

    def test_backtick_and_semicolon_are_left_alone(self):
        out = substitute_placeholders("$v = '%value%'", value="a`; b")
        assert out == "$v = 'a`; b'"

    def test_newline_stays_inside_the_literal(self):
        out = substitute_placeholders("$v = '%value%'", value="line1\nline2")
        assert out == "$v = 'line1\nline2'"

    def test_unicode_value_passes_through(self):
        out = substitute_placeholders("$v = '%value%'", value="Straße-日本語設定")
        assert out == "$v = 'Straße-日本語設定'"

    def test_empty_value_yields_empty_literal(self):
        out = substitute_placeholders("$v = '%value%'", value="")
        assert out == "$v = ''"

    def test_very_long_value_is_escaped_in_full(self):
        hostile = ("It's " * 2000).strip()
        out = substitute_placeholders("$v = '%value%'", value=hostile)
        assert out == "$v = '" + hostile.replace("'", "''") + "'"

    def test_two_placeholders_in_one_statement(self):
        """The exact ACTION_COMMANDS shape: $key = '%key%'; $newVal = '%value%'."""
        out = substitute_placeholders(
            "$key = '%key%'; $newVal = '%value%'",
            key="WorldStreamingQuality:0.0",
            value="0'; Set-Content -Path C:\\boot.ini; '",
        )
        assert out == (
            "$key = 'WorldStreamingQuality:0.0'; "
            "$newVal = '0''; Set-Content -Path C:\\boot.ini; '''"
        )

    def test_comment_apostrophe_does_not_corrupt_state(self):
        """Shipped scripts hold apostrophes in # comments (mw3_options_toggle);
        counting them as string delimiters would flip the context of every
        placeholder after the comment."""
        template = "# fpstune's own comment\n$v = '%value%'"
        out = substitute_placeholders(template, value="it's")
        assert out == "# fpstune's own comment\n$v = 'it''s'"

    def test_int_value_still_substitutes(self):
        out = substitute_placeholders("$v = '%value%'", value=5000)
        assert out == "$v = '5000'"


class TestDoubleQuotedContext:
    """A value in "..." must not terminate the string or expand as code."""

    def test_dollar_and_quote_are_backtick_escaped(self):
        out = substitute_placeholders('Write-Output "%value%"', value='a"$(calc)"b')
        assert out == 'Write-Output "a`"`$(calc)`"b"'

    def test_backtick_is_doubled_first(self):
        out = substitute_placeholders('Write-Output "%value%"', value="a`b")
        assert out == 'Write-Output "a``b"'


class TestBareContext:
    """An unquoted placeholder becomes its own command token: allowlist only."""

    @pytest.mark.parametrize("value", ["enabled", "CTCP", "1500", "19", "normal", "1.5", "a:b"])
    def test_token_values_pass(self, value):
        out = substitute_placeholders(
            "interface tcp set global autotuninglevel=%value%", value=value
        )
        assert out.endswith(f"autotuninglevel={value}")

    @pytest.mark.parametrize(
        "value",
        [
            "normal & del C:\\Windows",
            "on; bcdedit /set testsigning on",
            "a b",
            "'quoted'",
            '"quoted"',
            "$(calc)",
            "line\nbreak",
            "",
            "-ExtraSwitch",
        ],
    )
    def test_non_token_values_are_rejected(self, value):
        """A space, quote, ';' or '$(' here would append attacker tokens to an
        elevated netsh/PowerShell command line."""
        with pytest.raises(ValueError, match="outside any quotes"):
            substitute_placeholders("Set-NetTCPSetting -Timestamps %value%", value=value)

    def test_int_cast_operand_is_bare_context(self):
        out = substitute_placeholders("-RegistryValue ([int]%value%)", value=600)
        assert out == "-RegistryValue ([int]600)"
        with pytest.raises(ValueError, match="outside any quotes"):
            substitute_placeholders("-RegistryValue ([int]%value%)", value="0); calc; (1")


class TestUnmatchedPlaceholders:
    """Placeholders with no kwarg stay literal — the contract tests catch them."""

    def test_unknown_placeholder_survives(self):
        out = substitute_placeholders("$v = '%value%'", other="x")
        assert out == "$v = '%value%'"


class TestRealActionCommands:
    """The shipped templates the finding named, rendered with a hostile value."""

    @pytest.mark.parametrize(
        "action_key",
        [
            "mw3_options_toggle",
            "hots_variable_set",
            "steam_config_vdf_toggle",
            "steam_localconfig_vdf_toggle",
        ],
    )
    def test_breakout_value_stays_inside_the_literal(self, action_key):
        hostile = "x'; Start-Process calc; '"
        rendered = substitute_placeholders(
            ACTION_COMMANDS[action_key], key="SomeKey", value=hostile
        )
        # The doubled quotes keep the payload inside the string literal; the
        # pre-fix render closed the literal at "$newVal = 'x';" and ran the rest.
        assert "$newVal = 'x''; Start-Process calc; '''" in rendered
        assert "$newVal = 'x';" not in rendered

    def test_bnet_json_toggle_section_key_value_all_escaped(self):
        rendered = substitute_placeholders(
            ACTION_COMMANDS["bnet_json_toggle"],
            section="Client'; calc; '",
            key="HardwareAcceleration",
            value="false",
        )
        assert "$section = 'Client''; calc; '''" in rendered

    def test_mw3_pause_rendering_toggle_value_escaped(self):
        rendered = substitute_placeholders(
            ACTION_COMMANDS["mw3_pause_rendering_toggle"], value="0'; calc; '"
        )
        assert "$newVal = '0''; calc; '''" in rendered

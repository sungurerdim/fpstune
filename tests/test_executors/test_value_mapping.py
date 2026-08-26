"""Tests for the shared raw→display value mapper.

Before this existed, each executor had its own lookup and definitions had to
carry both int and str keys (``{1: "on", "1": "on"}``) to cover REG_DWORD and
REG_SZ. A definition that carried only one form left the raw value in place,
which then failed every comparison against the display value — silently, since
verification was skipped for those settings anyway.
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import MASK, UNMAPPED
from fpstune.settings.executors import map_raw_to_display


class TestMapRawToDisplay:
    def test_exact_key_wins(self):
        assert map_raw_to_display({1: "enabled", 0: "disabled"}, 1) == "enabled"

    def test_int_reading_matches_string_key(self):
        """REG_DWORD returns int; a map keyed by REG_SZ strings must still hit."""
        assert map_raw_to_display({"1": "enabled", "0": "disabled"}, 1) == "enabled"

    def test_string_reading_matches_int_key(self):
        """REG_SZ / netsh return text; a map keyed by ints must still hit."""
        assert map_raw_to_display({1: "enabled", 0: "disabled"}, "1") == "enabled"

    def test_whitespace_is_tolerated(self):
        assert map_raw_to_display({2: "medium"}, " 2\r\n") == "medium"

    def test_hex_reading_matches_int_key(self):
        """powercfg reports indexes in hex."""
        assert map_raw_to_display({16: "high"}, "0x10") == "high"

    def test_zero_is_not_confused_with_missing(self):
        """0 is falsy — it must still map rather than fall through."""
        assert map_raw_to_display({0: "off", 1: "on"}, "0") == "off"

    def test_unmapped_value_is_returned_unchanged(self):
        assert map_raw_to_display({1: "enabled"}, 7) == 7

    def test_empty_map_returns_raw(self):
        assert map_raw_to_display({}, "anything") == "anything"

    def test_none_reading_is_not_coerced(self):
        """A None reading means 'not set'; callers handle it via the None key."""
        assert map_raw_to_display({1: "enabled"}, None) is None

    def test_non_numeric_text_is_returned_unchanged(self):
        assert map_raw_to_display({1: "enabled"}, "enabled") == "enabled"

    @pytest.mark.parametrize("unhashable", [["a"], {"k": "v"}])
    def test_unhashable_reading_does_not_raise(self, unhashable):
        assert map_raw_to_display({1: "enabled"}, unhashable) == unhashable


class TestMaskedReadings:
    """A value that packs several flags into one number is not an enum.

    `perf:numlock_default` reads InitialKeyboardIndicators, where 0x2 is Num Lock
    and 0x80000000 means "restore the previous state". The map used to list the
    two combinations someone had seen (2 and 2147483650) and nothing else, so
    2147483648 — an ordinary state, the high bit with Num Lock off — surfaced as
    a bare number outside `choices` and the setting could never verify. That is
    the CI failure this class pins.
    """

    NUMLOCK = {MASK: 0x2, 2: "on", 0: "off", None: "off"}

    @pytest.mark.parametrize(
        ("reading", "expected", "why"),
        [
            (0, "off", "nothing set"),
            (2, "on", "Num Lock alone"),
            ("2147483648", "off", "the CI reading: restore-previous with Num Lock off"),
            ("2147483650", "on", "restore-previous with Num Lock on"),
            (2147483651, "on", "Num Lock and Caps Lock together with the high bit"),
            (3, "on", "Caps Lock must not change the answer about Num Lock"),
            (1, "off", "Caps Lock alone is not Num Lock"),
            (4, "off", "Scroll Lock alone is not Num Lock"),
        ],
    )
    def test_only_the_masked_bit_decides(self, reading, expected, why):
        assert map_raw_to_display(self.NUMLOCK, reading) == expected, why

    def test_absent_reading_is_not_masked_into_a_value(self):
        """Masking a sentinel would turn "no such feature" into a plausible 0."""
        assert map_raw_to_display(self.NUMLOCK, "not_supported") == "not_supported"

    def test_none_still_uses_the_none_key(self):
        assert map_raw_to_display(self.NUMLOCK, None) == "off"


class TestUnmappedFallback:
    """A threshold is not an enum either.

    `perf:svchost_split_threshold` reads SvcHostSplitThresholdInKB. 0xFFFFFFFF
    means "combine everything"; every other number is the RAM-sized default
    Windows wrote at install. The map listed only 0xFFFFFFFF, so the CI runner's
    real 3774873 reached the UI as itself.
    """

    SVCHOST = {4294967295: "combined", None: "split", UNMAPPED: "split"}

    def test_the_listed_value_still_wins(self):
        assert map_raw_to_display(self.SVCHOST, 4294967295) == "combined"
        assert map_raw_to_display(self.SVCHOST, "4294967295") == "combined"

    @pytest.mark.parametrize("reading", [3774873, 380000, 0, "1048576"])
    def test_any_other_number_falls_back(self, reading):
        assert map_raw_to_display(self.SVCHOST, reading) == "split"

    def test_non_numeric_text_falls_back_too(self):
        """An unmapped reading is unmapped whatever shape it has."""
        assert map_raw_to_display(self.SVCHOST, "whatever") == "split"

    def test_none_still_uses_the_none_key(self):
        assert map_raw_to_display(self.SVCHOST, None) == "split"

    @pytest.mark.parametrize(
        "sentinel", ["not_supported", "not_found", "not_available", "not_installed"]
    )
    def test_an_absent_reading_is_never_swallowed(self, sentinel):
        """Absence is not an unmapped value.

        If the fallback took these, a NIC with no such keyword would report the
        setting's ordinary default, detection would call it applicable, and the
        UI would offer to change something that does not exist.
        """
        assert map_raw_to_display(self.SVCHOST, sentinel) == sentinel

    def test_without_the_key_an_unmapped_reading_is_still_returned_raw(self):
        """The fallback is opt-in; every other setting keeps its old behaviour."""
        assert map_raw_to_display({4294967295: "combined"}, 3774873) == 3774873


class TestRegistryExecutorUsesSharedMapper:
    """The registry executor is the biggest consumer — 108 settings route
    through it with an empty apply_command."""

    def test_dword_reading_maps_via_string_keyed_map(self, monkeypatch):
        import sys

        if sys.platform != "win32":
            pytest.skip("winreg semantics are Windows-only")

        from fpstune.settings.base import (
            DetectType,
            SettingCategory,
            SettingExecutor,
            SettingValueType,
        )
        from fpstune.settings.executors.registry import RegistryExecutor

        setting = SettingExecutor(
            id="test:dword_string_map",
            category=SettingCategory.CORE,
            display_name="Mapped",
            description="Setting whose value_map only carries string keys.",
            value_type=SettingValueType.CHOICE,
            choices=("enabled", "disabled"),
            default_value="enabled",
            recommended_value="disabled",
            detect_type=DetectType.REGISTRY,
            detect_command="",
            detect_args={"path": "Software\\FpstuneTest", "name": "Flag", "hive": "HKCU"},
            value_map={"0": "disabled", "1": "enabled"},
            apply_type=DetectType.REGISTRY,
            apply_command="",
            apply_args={"path": "Software\\FpstuneTest", "name": "Flag", "hive": "HKCU"},
        )

        import winreg

        class _FakeKey:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

        monkeypatch.setattr(winreg, "OpenKey", lambda *_args, **_kwargs: _FakeKey())
        # REG_DWORD → int reading, while the map only has string keys.
        monkeypatch.setattr(winreg, "QueryValueEx", lambda *_args: (0, winreg.REG_DWORD))

        value, error = RegistryExecutor().detect(setting)

        assert error is None
        assert value == "disabled"


class TestRegistryAccessMaskPinsSixtyFourBitView:
    """Without KEY_WOW64_64KEY a 32-bit build silently reads and writes
    Wow6432Node, so verification passes while the real key never changes."""

    def test_access_mask_includes_wow64_64key(self):
        import sys

        if sys.platform != "win32":
            pytest.skip("winreg constants are Windows-only")

        import winreg

        from fpstune.settings.executors.registry import _access

        assert _access(winreg.KEY_READ) & winreg.KEY_WOW64_64KEY
        assert _access(winreg.KEY_WRITE) & winreg.KEY_WOW64_64KEY
        # The base rights must survive.
        assert _access(winreg.KEY_READ) & winreg.KEY_READ == winreg.KEY_READ

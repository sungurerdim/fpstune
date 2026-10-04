"""Tests for the NVAPI driver settings layer.

A fake DRS stands in for nvapi64.dll: it keeps a loaded copy and a saved copy,
like the driver, so a write that is never saved is visibly lost and two values
written in one session land together.
"""

from __future__ import annotations

import ctypes
from typing import Any

import pytest

from fpstune.core import nvapi


class TestStructLayout:
    """The struct must match nvapi.h; a mismatch makes the driver reject the
    call with NVAPI_INCOMPATIBLE_STRUCT_VERSION (-9)."""

    def test_version_encodes_size_and_version_number(self):
        size = ctypes.sizeof(nvapi.NvdrsSetting)
        assert size | (1 << 16) == nvapi.NVDRS_SETTING_VER
        # Low 16 bits carry the size, so it must fit.
        assert size < (1 << 16)

    def test_setting_name_and_value_unions_are_sized_from_nvapi_limits(self):
        fields = dict(nvapi.NvdrsSetting._fields_)
        assert ctypes.sizeof(fields["settingName"]) == 2048 * 2
        # Both value unions must be large enough for the binary variant.
        assert ctypes.sizeof(fields["currentValue"]) >= 4096

    def test_field_order_matches_header(self):
        names = [name for name, _ in nvapi.NvdrsSetting._fields_]
        assert names == [
            "version",
            "settingName",
            "settingId",
            "settingType",
            "settingLocation",
            "isCurrentPredefined",
            "isPredefinedValid",
            "predefinedValue",
            "currentValue",
        ]


class FakeDrs:
    """The DRS calls nvapi.py makes, over a dict instead of the driver."""

    def __init__(self, saved: dict[int, int] | None = None, refuse: set[int] | None = None):
        self.saved = dict(saved or {})
        self.working: dict[int, int] = {}
        self.refuse = refuse or set()
        self.profiles = {"fpstune_gaming"}
        self.saves = 0

    def initialize(self) -> int:
        return 0

    def create_session(self, ref: Any) -> int:
        ref._obj.value = 1
        return 0

    def destroy_session(self, _handle: Any) -> int:
        return 0

    def load_settings(self, _handle: Any) -> int:
        self.working = dict(self.saved)
        return 0

    def save_settings(self, _handle: Any) -> int:
        self.saved = dict(self.working)
        self.saves += 1
        return 0

    def get_current_global_profile(self, _handle: Any, ref: Any) -> int:
        ref._obj.value = 2
        return 0

    def get_setting(self, _h: Any, _p: Any, setting_id: Any, ref: Any) -> int:
        if setting_id.value not in self.working:
            return nvapi.NVAPI_SETTING_NOT_FOUND
        setting = ref._obj
        setting.settingId = setting_id.value
        setting.settingType = 0
        setting.currentValue.u32Value = self.working[setting_id.value]
        return 0

    def set_setting(self, _h: Any, _p: Any, ref: Any) -> int:
        setting = ref._obj
        if setting.settingId in self.refuse:
            return nvapi.NVAPI_INVALID_USER_PRIVILEGE
        self.working[setting.settingId] = setting.currentValue.u32Value
        return 0

    def delete_profile_setting(self, _h: Any, _p: Any, setting_id: Any) -> int:
        if setting_id.value not in self.working:
            return nvapi.NVAPI_SETTING_NOT_FOUND
        del self.working[setting_id.value]
        return 0

    def enum_settings(self, _h: Any, _p: Any, start: Any, count: Any, buffer: Any) -> int:
        items = list(self.working.items())[start.value :][: count._obj.value]
        if not items:
            return nvapi.NVAPI_END_ENUMERATION
        for slot, (setting_id, value) in zip(buffer, items, strict=False):
            slot.settingId = setting_id
            slot.settingType = 0
            slot.settingLocation = 1
            slot.currentValue.u32Value = value
        count._obj.value = len(items)
        return 0

    def find_profile_by_name(self, _h: Any, name: Any, ref: Any) -> int:
        text = "".join(chr(c) for c in name._obj if c)
        if text not in self.profiles:
            return nvapi.NVAPI_PROFILE_NOT_FOUND
        ref._obj.value = 3
        return 0

    def delete_profile(self, _h: Any, _profile: Any) -> int:
        self.profiles.clear()
        return 0


@pytest.fixture
def drs(monkeypatch: pytest.MonkeyPatch) -> FakeDrs:
    fake = FakeDrs()
    monkeypatch.setattr(nvapi._Nvapi, "get", staticmethod(lambda: fake))
    return fake


class TestWrites:
    def test_a_value_is_written_and_saved(self, drs: FakeDrs) -> None:
        nvapi.write_driver_settings({0x00A879CF: 0x08416747})

        assert drs.saved[0x00A879CF] == 0x08416747
        assert drs.saves == 1

    def test_none_deletes_so_the_driver_default_applies(self, drs: FakeDrs) -> None:
        drs.saved = {0x007BA09E: 1}

        nvapi.write_driver_settings({0x007BA09E: None})

        assert 0x007BA09E not in drs.saved

    def test_deleting_an_absent_setting_is_not_an_error(self, drs: FakeDrs) -> None:
        nvapi.write_driver_settings({0x007BA09E: None})

        assert drs.saves == 1

    def test_a_refused_write_saves_nothing(self, drs: FakeDrs) -> None:
        drs.refuse = {0x10835000}

        with pytest.raises(nvapi.NvapiError, match="administrator rights"):
            nvapi.write_driver_settings({0x007BA09E: 1, 0x10835000: 1})

        assert drs.saved == {}
        assert drs.saves == 0

    def test_the_orphan_profile_of_the_previous_release_is_removed(self, drs: FakeDrs) -> None:
        nvapi.write_driver_settings({0x00A879CF: 0x08416747})

        assert drs.profiles == set()

    def test_values_above_31_bits_are_written_unsigned(self, drs: FakeDrs) -> None:
        nvapi.write_driver_settings({0x00CE2691: 0xFFFFFFF6})

        assert drs.saved[0x00CE2691] == 0xFFFFFFF6


class TestReads:
    def test_present_values_are_returned_and_absent_ones_omitted(self, drs: FakeDrs) -> None:
        drs.saved = {0x1057EB71: 5}

        assert nvapi.read_driver_settings([0x1057EB71, 0x007BA09E]) == {0x1057EB71: 5}

    def test_dump_lists_every_setting_on_the_global_profile(self, drs: FakeDrs) -> None:
        drs.saved = {0x1057EB71: 5, 0x10835002: 141}

        dumped = {(d.setting_id, d.value, d.location) for d in nvapi.dump_driver_settings()}

        assert dumped == {(0x1057EB71, 5, "global"), (0x10835002, 141, "global")}


class TestDegradation:
    """A read that cannot reach the driver returns None, never a guess."""

    def test_empty_request_returns_empty_mapping(self):
        assert nvapi.read_driver_settings([]) == {}

    def test_unavailable_nvapi_returns_none(self, monkeypatch):
        def boom():
            raise nvapi.NvapiUnavailable("no driver")

        monkeypatch.setattr(nvapi._Nvapi, "get", staticmethod(boom))
        assert nvapi.read_driver_settings([0x007BA09E]) is None

    def test_driver_fault_returns_none_instead_of_raising(self, monkeypatch):
        def boom():
            raise OSError("access violation")

        monkeypatch.setattr(nvapi._Nvapi, "get", staticmethod(boom))
        assert nvapi.read_driver_settings([0x007BA09E]) is None

    def test_availability_probe_never_raises(self, monkeypatch):
        def boom():
            raise OSError("access violation")

        monkeypatch.setattr(nvapi._Nvapi, "get", staticmethod(boom))
        assert nvapi.nvapi_available() is False

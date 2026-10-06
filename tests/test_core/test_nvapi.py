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

    def __init__(
        self,
        saved: dict[int, int] | None = None,
        refuse: set[int] | None = None,
        unknown: set[int] | None = None,
        unnamed: set[int] | None = None,
    ):
        # `unnamed` are keys missing from the driver's naming table that it
        # nonetheless recognises: writing one answers a privilege error, not -160.
        self.unnamed = unnamed or set()
        # `unknown` are keys this driver version does not define at all: it
        # answers NVAPI_SETTING_NOT_FOUND to naming, reading and writing them.
        self.unknown = unknown or set()
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

    def get_setting_name_from_id(self, setting_id: Any, _name: Any) -> int:
        if setting_id.value in self.unknown | self.unnamed:
            return nvapi.NVAPI_SETTING_NOT_FOUND
        return 0

    def set_setting(self, _h: Any, _p: Any, ref: Any) -> int:
        setting = ref._obj
        if setting.settingId in self.unknown:
            return nvapi.NVAPI_SETTING_NOT_FOUND
        if setting.settingId in self.unnamed:
            return nvapi.NVAPI_INVALID_USER_PRIVILEGE
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


class TestStatusWords:
    """A status the module can return must say what it means. -160 once read
    "the NVIDIA driver refused the request" for a key the driver simply lacks."""

    def test_every_status_constant_has_its_own_words(self) -> None:
        statuses = {
            name: value
            for name, value in vars(nvapi).items()
            if name.startswith("NVAPI_") and isinstance(value, int) and value != nvapi.NVAPI_OK
        }
        assert statuses, "no status constants found: the guard would pass over nothing"

        unnamed = {name for name, value in statuses.items() if value not in nvapi._STATUS_MESSAGES}

        assert unnamed == set()

    def test_status_constants_are_distinct_negative_codes(self) -> None:
        values = [v for k, v in vars(nvapi).items() if k.startswith("NVAPI_") and k != "NVAPI_OK"]
        assert len(values) == len(set(values))
        assert all(isinstance(v, int) and v < 0 for v in values)

    def test_setting_not_found_says_the_driver_lacks_the_setting(self) -> None:
        error = nvapi.NvapiError("NvAPI_DRS_SetSetting(0x10835000)", nvapi.NVAPI_SETTING_NOT_FOUND)

        assert "this driver does not have this setting" in str(error)
        assert "refused" not in str(error)
        assert "-160" in str(error)

    def test_an_unknown_status_is_said_to_be_unnamed_not_refused(self) -> None:
        assert "does not name" in nvapi._describe(-9999)


class TestCapabilityProbe:
    def test_keys_the_driver_lacks_are_left_out(self, drs: FakeDrs) -> None:
        drs.unknown = {0x10835000}

        assert nvapi.known_setting_ids([0x007BA09E, 0x10835000]) == {0x007BA09E}

    def test_a_key_the_driver_recognises_without_naming_is_not_called_absent(
        self, drs: FakeDrs
    ) -> None:
        drs.unnamed = {0x50166C5E}  # CUDA Force P2: unnamed, write answers -137

        assert nvapi.known_setting_ids([0x50166C5E]) == {0x50166C5E}

    def test_the_confirming_write_is_never_saved(self, drs: FakeDrs) -> None:
        drs.unknown = {0x10835000}

        nvapi.known_setting_ids([0x10835000, 0x007BA09E])

        assert drs.saves == 0
        assert drs.saved == {}

    def test_an_unreachable_driver_is_unknown_not_empty(self, monkeypatch) -> None:
        def boom():
            raise nvapi.NvapiUnavailable("no driver")

        monkeypatch.setattr(nvapi._Nvapi, "get", staticmethod(boom))

        assert nvapi.known_setting_ids([0x007BA09E]) is None

    def test_a_driver_without_the_probe_is_unknown_not_empty(self, drs: FakeDrs) -> None:
        drs.get_setting_name_from_id = None  # type: ignore[assignment]

        assert nvapi.known_setting_ids([0x007BA09E]) is None

    def test_a_status_other_than_found_or_not_found_is_unknown(
        self, drs: FakeDrs, monkeypatch
    ) -> None:
        monkeypatch.setattr(drs, "get_setting_name_from_id", lambda *_: nvapi.NVAPI_ERROR)

        assert nvapi.known_setting_ids([0x007BA09E]) is None


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


class TestKeysTheDriverLacks:
    """Driver 617.14 does not define 0x10835000 (ULL_ENABLED). Applying Low
    Latency used to fail with "refused (status -160)" for every tier."""

    ULL_ENABLED = 0x10835000
    ULL_CPL_STATE = 0x0005F543
    PRERENDERLIMIT = 0x007BA09E

    @pytest.fixture
    def executor(self):
        from fpstune.settings.executors.nvprofile import NvProfileExecutor

        return NvProfileExecutor()

    @pytest.fixture
    def low_latency(self):
        from fpstune.settings.definitions.gpu import NVIDIA_LOW_LATENCY

        return NVIDIA_LOW_LATENCY

    def test_on_applies_without_the_key_it_never_needed(self, drs, executor, low_latency):
        drs.unknown = {self.ULL_ENABLED}

        ok, error = executor.apply(low_latency, "on")

        assert (ok, error) == (True, None)
        assert drs.saved == {self.PRERENDERLIMIT: 1, self.ULL_CPL_STATE: 1}

    def test_ultra_is_refused_in_words_because_its_meaning_lived_in_the_key(
        self, drs, executor, low_latency
    ):
        drs.unknown = {self.ULL_ENABLED}

        ok, error = executor.apply(low_latency, "ultra")

        assert ok is False
        assert error is not None
        assert "not available on this driver" in error
        assert "refused" not in error
        assert drs.saves == 0

    def test_ultra_is_written_whole_when_the_driver_has_every_key(self, drs, executor, low_latency):
        ok, error = executor.apply(low_latency, "ultra")

        assert (ok, error) == (True, None)
        assert drs.saved == {self.PRERENDERLIMIT: 1, self.ULL_ENABLED: 1, self.ULL_CPL_STATE: 2}

    def test_detect_still_reads_the_tier_without_the_key(self, drs, executor, low_latency):
        drs.unknown = {self.ULL_ENABLED}
        drs.saved = {self.PRERENDERLIMIT: 1}

        assert executor.detect(low_latency) == ("on", None)

    def test_a_setting_whose_every_key_is_missing_is_not_supported(
        self, drs, executor, low_latency
    ):
        drs.unknown = {self.PRERENDERLIMIT, self.ULL_ENABLED, self.ULL_CPL_STATE}

        value, error = executor.detect(low_latency)

        assert error is None
        assert value == "not_supported"

    def test_a_number_setting_on_a_driver_without_its_key_is_not_supported(self, drs, executor):
        from fpstune.core.nv_drs import FRL_FPS
        from fpstune.settings.definitions.gpu import NVIDIA_FPS_LIMITER

        drs.unknown = {FRL_FPS}

        value, error = executor.detect(NVIDIA_FPS_LIMITER)
        ok, apply_error = executor.apply(NVIDIA_FPS_LIMITER, 141)

        assert (value, error) == ("not_supported", None)
        assert ok is False
        assert apply_error is not None
        assert "does not have the NVIDIA setting" in apply_error

    def test_an_unaskable_driver_changes_nothing_about_apply(self, drs, executor, low_latency):
        drs.get_setting_name_from_id = None  # type: ignore[assignment]

        ok, error = executor.apply(low_latency, "ultra")

        assert (ok, error) == (True, None)

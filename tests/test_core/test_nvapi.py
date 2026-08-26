"""Tests for the NVAPI driver read-back.

These cover the layer's contract rather than the driver itself: the point is
that a failure degrades to "no observation" so callers fall back to the cache,
instead of surfacing a wrong value or crashing detection.
"""

from __future__ import annotations

import ctypes

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


class TestDegradation:
    """Any failure must return None so the caller falls back to the cache."""

    def test_empty_request_returns_empty_mapping(self):
        assert nvapi.read_driver_settings([]) == {}

    def test_unavailable_nvapi_returns_none(self, monkeypatch):
        def boom():
            raise nvapi.NvapiUnavailable("no driver")

        monkeypatch.setattr(nvapi._Nvapi, "get", staticmethod(boom))
        assert nvapi.read_driver_settings([0x00707011]) is None

    def test_driver_fault_returns_none_instead_of_raising(self, monkeypatch):
        def boom():
            raise OSError("access violation")

        monkeypatch.setattr(nvapi._Nvapi, "get", staticmethod(boom))
        assert nvapi.read_driver_settings([0x00707011]) is None

    def test_availability_probe_never_raises(self, monkeypatch):
        def boom():
            raise OSError("access violation")

        monkeypatch.setattr(nvapi._Nvapi, "get", staticmethod(boom))
        assert nvapi.nvapi_available() is False


class TestReverseValueMaps:
    """Raw->display maps are derived from NvidiaProfile so they cannot drift
    from the values fpstune actually writes."""

    def test_maps_are_derived_not_hand_written(self):
        from fpstune.settings.executors import nvprofile

        nvprofile._build_driver_maps()

        from fpstune.core.nv_profile import NvApiSettings, NvidiaProfile

        assert nvprofile._DRIVER_READABLE["low_latency"] == NvApiSettings.LOW_LATENCY_MODE

        # Every derived entry must round-trip through the apply-side mapping.
        for key, reverse in nvprofile._REVERSE_VALUE_MAPS.items():
            setting_id = nvprofile._DRIVER_READABLE[key]
            for raw, display in reverse.items():
                emitted = NvidiaProfile(**{key: display}).to_settings_dict()
                assert emitted[setting_id] == raw, f"{key}={display} should emit {raw}"

    @pytest.mark.parametrize(
        ("key", "display", "raw"),
        [
            ("low_latency", "off", 0),
            ("low_latency", "ultra", 2),
            ("vsync", "on", 1),
            ("shader_cache", "off", 0),
        ],
    )
    def test_known_values(self, key, display, raw):
        from fpstune.settings.executors import nvprofile

        nvprofile._build_driver_maps()
        assert nvprofile._REVERSE_VALUE_MAPS[key][raw] == display

    def test_unreadable_key_returns_none(self):
        from fpstune.settings.executors.nvprofile import read_setting_from_driver

        # fps_limit is not exposed as a plain DWORD read here.
        assert read_setting_from_driver("no_such_setting") is None

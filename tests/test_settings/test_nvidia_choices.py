"""A row offers only the NVIDIA choices the installed driver can hold.

Driver 617.14 has no ``ULL_ENABLED`` (0x10835000): Low Latency "ultra" is listed
by the definition, accepted by the UI, and refused by the driver. These tests pin
the discovery pass that removes it, and the three limits on it: a recommendation
is never remapped, an unaskable driver changes nothing, and the pass can only
ever remove declared choices.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from fpstune.core import nvapi
from fpstune.core.nv_drs import KEYS, ULL_ENABLED, EnumKey, lookup
from fpstune.settings.applicability import NOT_SUPPORTED
from fpstune.settings.base import DetectType, SettingExecutor
from fpstune.settings.definitions import get_all_static_settings
from fpstune.settings.definitions.gpu import NVIDIA_LOW_LATENCY
from fpstune.settings.discovery import all_discoverers
from fpstune.settings.discovery.nvidia import narrow_nvidia_choices
from fpstune.settings.executors.nvprofile import NvProfileExecutor, holdable_choices


class FakeRegistry:
    """The three methods a discoverer is allowed, over a plain dict."""

    def __init__(self, settings: list[SettingExecutor]) -> None:
        self.settings = {s.id: s for s in settings}

    def register(self, setting: SettingExecutor) -> None:
        self.settings[setting.id] = setting

    def get(self, setting_id: str) -> SettingExecutor | None:
        return self.settings.get(setting_id)

    def get_all(self) -> list[SettingExecutor]:
        return list(self.settings.values())


def nvprofile_settings() -> list[SettingExecutor]:
    return [
        s
        for s in get_all_static_settings()
        if s.detect_type == DetectType.NVPROFILE and s.apply_type == DetectType.NVPROFILE
    ]


def driver_without(monkeypatch: pytest.MonkeyPatch, *missing: int) -> None:
    """A driver that defines every key a row uses except ``missing``."""

    def known(ids):
        return frozenset(ids) - set(missing)

    monkeypatch.setattr(nvapi, "known_setting_ids", known)


class TestNarrowing:
    def test_ultra_is_dropped_when_the_driver_lacks_the_key_it_needs(self, monkeypatch) -> None:
        driver_without(monkeypatch, ULL_ENABLED)
        registry = FakeRegistry([NVIDIA_LOW_LATENCY])

        narrowed = narrow_nvidia_choices(registry, None)  # type: ignore[arg-type]

        row = registry.settings["gpu-nvidia:low_latency"]
        assert narrowed == 1
        assert row.choices == ("off", "on")
        assert (row.default_value, row.recommended_value) == ("off", "on")

    def test_the_shared_definition_is_not_mutated(self, monkeypatch) -> None:
        driver_without(monkeypatch, ULL_ENABLED)

        narrow_nvidia_choices(FakeRegistry([NVIDIA_LOW_LATENCY]), None)  # type: ignore[arg-type]

        assert NVIDIA_LOW_LATENCY.choices == ("off", "on", "ultra")

    def test_a_driver_that_holds_every_choice_changes_nothing(self, monkeypatch) -> None:
        driver_without(monkeypatch)
        rows = nvprofile_settings()
        registry = FakeRegistry(rows)

        assert narrow_nvidia_choices(registry, None) == 0  # type: ignore[arg-type]
        assert registry.get_all() == rows

    def test_an_unaskable_driver_narrows_nothing(self, monkeypatch) -> None:
        monkeypatch.setattr(nvapi, "known_setting_ids", lambda _ids: None)
        rows = nvprofile_settings()
        registry = FakeRegistry(rows)

        assert narrow_nvidia_choices(registry, None) == 0  # type: ignore[arg-type]
        assert registry.get_all() == rows

    def test_a_row_that_is_not_an_nvidia_enum_is_left_alone(self, monkeypatch) -> None:
        driver_without(monkeypatch, ULL_ENABLED)
        other = replace(NVIDIA_LOW_LATENCY, id="gpu-nvidia:other", detect_type=DetectType.REGISTRY)

        assert narrow_nvidia_choices(FakeRegistry([other]), None) == 0  # type: ignore[arg-type]


class TestRecommendationIsNeverRemapped:
    def ultra_recommended(self) -> SettingExecutor:
        return replace(NVIDIA_LOW_LATENCY, recommended_value="ultra")

    def test_choices_stay_as_declared_when_the_recommendation_would_fall_out(
        self, monkeypatch
    ) -> None:
        driver_without(monkeypatch, ULL_ENABLED)
        registry = FakeRegistry([self.ultra_recommended()])

        narrowed = narrow_nvidia_choices(registry, None)  # type: ignore[arg-type]

        row = registry.settings["gpu-nvidia:low_latency"]
        assert narrowed == 0
        assert row.choices == ("off", "on", "ultra")
        assert row.recommended_value == "ultra"

    def test_such_a_row_is_not_supported_rather_than_offered(self, monkeypatch) -> None:
        driver_without(monkeypatch, ULL_ENABLED)
        monkeypatch.setattr(nvapi, "read_driver_settings", lambda _ids: {})

        value, error = NvProfileExecutor().detect(self.ultra_recommended())

        assert (value, error) == (NOT_SUPPORTED, None)

    def test_a_row_whose_answers_fit_the_driver_is_still_detected(self, monkeypatch) -> None:
        driver_without(monkeypatch, ULL_ENABLED)
        monkeypatch.setattr(nvapi, "read_driver_settings", lambda _ids: {})

        value, error = NvProfileExecutor().detect(NVIDIA_LOW_LATENCY)

        assert (value, error) == ("off", None)


class TestEveryNvidiaRow:
    @pytest.mark.parametrize("setting", nvprofile_settings(), ids=lambda s: s.id)
    def test_declared_choices_are_all_values_of_the_key(self, setting: SettingExecutor) -> None:
        drs = lookup(str(setting.detect_args["setting"]))
        assert drs is not None
        if isinstance(drs, EnumKey):
            assert set(setting.choices) <= set(drs.values)

    def test_narrowed_choices_are_a_subset_of_the_declared_ones(self, monkeypatch) -> None:
        all_ids = {i for key in KEYS.values() for i in key.ids}
        # Every single missing key, then every key missing at once.
        scenarios = [{i} for i in sorted(all_ids)] + [all_ids]
        for setting in nvprofile_settings():
            for missing in scenarios:
                held = holdable_choices(setting, missing)
                if held is None:
                    continue
                assert set(held) <= set(setting.choices), (setting.id, missing)

                driver_without(monkeypatch, *missing)
                registry = FakeRegistry([setting])
                narrowed = narrow_nvidia_choices(registry, None)  # type: ignore[arg-type]
                row = registry.settings[setting.id]
                assert set(row.choices) <= set(setting.choices), (setting.id, missing)
                if narrowed:
                    assert str(row.default_value) in row.choices
                    assert str(row.recommended_value) in row.choices

    def test_the_pass_runs_after_every_other_one(self) -> None:
        assert all_discoverers()[-1] is narrow_nvidia_choices

"""A row offers only the NVIDIA choices the installed driver can hold.

Driver 617.14 has no ``ULL_ENABLED`` (0x10835000): Low Latency "ultra" is listed
by the definition, accepted by the UI, and refused by the driver. These tests pin
the discovery pass that removes it, and the three limits on it: a recommendation
is never remapped, an unaskable driver changes nothing, and the pass can only
ever remove declared choices.
"""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from pathlib import Path

import pytest

from fpstune.core import nvapi
from fpstune.core.nv_drs import (
    KEYS,
    PRERENDERLIMIT,
    ULL_CPL_STATE,
    ULL_ENABLED,
    EnumKey,
    lookup,
    mapped_ids,
)
from fpstune.settings.applicability import NOT_SUPPORTED
from fpstune.settings.base import DetectType, SettingExecutor
from fpstune.settings.definitions import get_all_static_settings
from fpstune.settings.definitions.gpu import NVIDIA_LOW_LATENCY
from fpstune.settings.discovery import all_discoverers
from fpstune.settings.discovery import nvidia as nvidia_discovery
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


@pytest.fixture(autouse=True)
def no_host_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    """The drift report lists the host's own profile unless a test says otherwise."""
    monkeypatch.setattr(nvapi, "dump_driver_settings", lambda: [])
    monkeypatch.setattr(nvidia_discovery, "_reported_unmapped", frozenset())


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
        # Nothing is dropped; the rows only gain the names this driver gives them.
        assert [r.choices for r in registry.get_all()] == [r.choices for r in rows]
        assert [r.recommended_value for r in registry.get_all()] == [
            r.recommended_value for r in rows
        ]

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


APP_ERA = (ULL_ENABLED, ULL_CPL_STATE)  # driver 617.14: neither Ultra key is defined


def low_latency_after_discovery(monkeypatch: pytest.MonkeyPatch, *missing: int) -> SettingExecutor:
    driver_without(monkeypatch, *missing)
    registry = FakeRegistry([NVIDIA_LOW_LATENCY])
    narrow_nvidia_choices(registry, None)  # type: ignore[arg-type]
    return registry.settings["gpu-nvidia:low_latency"]


class TestTierNamesFollowTheDriversCapability:
    """One tier, two vendor names: the keys the driver defines say which."""

    def test_a_driver_with_the_legacy_keys_names_the_tiers_off_on_ultra(self, monkeypatch) -> None:
        row = low_latency_after_discovery(monkeypatch)

        assert row.choices == ("off", "on", "ultra")
        assert row.choice_labels == {
            "off": "tier.off",
            "on": "tier.on",
            "ultra": "tier.ultra",
        }

    def test_a_driver_without_them_calls_the_one_queued_frame_tier_ultra(self, monkeypatch) -> None:
        row = low_latency_after_discovery(monkeypatch, *APP_ERA)

        assert row.choices == ("off", "on")
        assert row.choice_labels == {"off": "tier.off", "on": "tier.ultra"}

    def test_the_era_is_read_from_the_switch_not_the_panel_state_key(self, monkeypatch) -> None:
        # ULL_ENABLED carries the "ultra" meaning; ULL_CPL_STATE is write-only
        # bookkeeping for the control panel's radio button.
        only_state = low_latency_after_discovery(monkeypatch, ULL_CPL_STATE)
        only_switch = low_latency_after_discovery(monkeypatch, ULL_ENABLED)

        assert only_state.choice_labels["on"] == "tier.on"
        assert only_switch.choice_labels["on"] == "tier.ultra"

    def test_an_unaskable_driver_names_nothing(self, monkeypatch) -> None:
        monkeypatch.setattr(nvapi, "known_setting_ids", lambda _ids: None)
        registry = FakeRegistry([NVIDIA_LOW_LATENCY])

        narrow_nvidia_choices(registry, None)  # type: ignore[arg-type]

        assert registry.settings["gpu-nvidia:low_latency"].choice_labels == {}

    def test_the_shared_definition_gets_no_names(self, monkeypatch) -> None:
        low_latency_after_discovery(monkeypatch, *APP_ERA)

        assert NVIDIA_LOW_LATENCY.choice_labels == {}

    @pytest.mark.parametrize("missing", [(), APP_ERA], ids=["control-panel-era", "app-era"])
    def test_the_recommendation_stays_among_the_offered_choices(
        self, monkeypatch, missing: tuple[int, ...]
    ) -> None:
        row = low_latency_after_discovery(monkeypatch, *missing)

        assert row.recommended_value == "on"
        assert row.recommended_value in row.choices
        assert row.default_value in row.choices
        # Every offered tier has a name, and no name is given to a tier not offered.
        assert set(row.choice_labels) == set(row.choices)

    @pytest.mark.parametrize("missing", [(), APP_ERA], ids=["control-panel-era", "app-era"])
    def test_off_restores_a_zero_pre_render_limit_in_both_eras(
        self, missing: tuple[int, ...]
    ) -> None:
        drs = lookup("low_latency")
        assert isinstance(drs, EnumKey)

        changes = drs.changes_for("off", frozenset(missing))

        # Stock is deleted, never written: the driver's own value is 0, which is
        # what the NVIDIA App's "Off" writes explicitly (measured on 617.14).
        assert changes[PRERENDERLIMIT] is None
        assert drs.decode({PRERENDERLIMIT: 0}) == "off"
        assert drs.decode({}) == "off"

    def test_on_writes_the_pre_render_limit_alone_when_the_ultra_keys_are_absent(self) -> None:
        drs = lookup("low_latency")
        assert isinstance(drs, EnumKey)

        assert drs.changes_for("on", frozenset(APP_ERA)) == {PRERENDERLIMIT: 1}
        # What the NVIDIA App writes for its "Ultra" reads back as "on".
        assert drs.decode({PRERENDERLIMIT: 1}) == "on"

    def test_on_also_records_the_panel_state_when_the_driver_has_it(self) -> None:
        drs = lookup("low_latency")
        assert isinstance(drs, EnumKey)

        assert drs.changes_for("on", frozenset()) == {
            PRERENDERLIMIT: 1,
            ULL_ENABLED: 0,
            ULL_CPL_STATE: 1,
        }


def _label_keys(key: EnumKey) -> set[str]:
    named = [*key.labels.values(), *(v for m in key.labels_without.values() for v in m.values())]
    return set(named)


class TestEveryEnumKeyThatCanLoseAKeyNamesItsTiers:
    @pytest.mark.parametrize(
        "key",
        [k for k in KEYS.values() if isinstance(k, EnumKey) and not k.published],
        ids=lambda k: k.key,
    )
    def test_names_by_capability_or_says_why_not(self, key: EnumKey) -> None:
        # An unpublished key is one a driver generation may not define, which is
        # how a tier ends up carrying another vendor name. Either the key names
        # its tiers per capability, or it states why no absence can rename one.
        assert key.labels or key.label_reason, key.key
        if key.labels:
            assert set(key.labels) <= set(key.values), key.key
            for replacement in key.labels_without.values():
                assert set(replacement) <= set(key.values), key.key
            assert set(key.labels_without) <= set(key.ids), key.key

    def test_every_label_key_exists_in_both_catalogues(self) -> None:
        i18n = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n"
        used = {
            label for key in KEYS.values() if isinstance(key, EnumKey) for label in _label_keys(key)
        }
        assert used
        for name in ("en", "tr"):
            text = (i18n / f"{name}.ts").read_text(encoding="utf-8")
            for label in used:
                assert re.search(rf'^\s*"{re.escape(label)}":', text, re.M), (name, label)


class TestDriftVisibility:
    def fake_profile(self, monkeypatch: pytest.MonkeyPatch, *held: tuple[int, int]) -> None:
        monkeypatch.setattr(
            nvapi,
            "dump_driver_settings",
            lambda: [nvapi.DriverSetting(i, v, "Global", False) for i, v in held],
        )

    def run_discovery(self, monkeypatch: pytest.MonkeyPatch) -> None:
        driver_without(monkeypatch)
        narrow_nvidia_choices(FakeRegistry([NVIDIA_LOW_LATENCY]), None)  # type: ignore[arg-type]

    def test_settings_the_table_does_not_know_are_logged_with_their_values(
        self, monkeypatch, caplog
    ) -> None:
        self.fake_profile(monkeypatch, (PRERENDERLIMIT, 1), (0x10E41DF3, 0x5), (0x20C12225, 0x0))
        caplog.set_level(logging.INFO, logger=nvidia_discovery.logger.name)

        self.run_discovery(monkeypatch)

        lines = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
        assert lines == [
            "NVIDIA driver holds settings fpstune does not map: 0x10e41df3=0x5, 0x20c12225=0x0"
        ]

    def test_a_profile_holding_only_mapped_settings_logs_nothing(self, monkeypatch, caplog) -> None:
        self.fake_profile(monkeypatch, *((i, 0) for i in sorted(mapped_ids())))
        caplog.set_level(logging.INFO, logger=nvidia_discovery.logger.name)

        self.run_discovery(monkeypatch)

        assert not [r for r in caplog.records if r.levelno == logging.INFO]

    def test_the_same_finding_is_logged_once_not_per_registry(self, monkeypatch, caplog) -> None:
        self.fake_profile(monkeypatch, (0x10E41DF3, 0x5))
        caplog.set_level(logging.INFO, logger=nvidia_discovery.logger.name)

        self.run_discovery(monkeypatch)
        self.run_discovery(monkeypatch)

        assert len([r for r in caplog.records if r.levelno == logging.INFO]) == 1

    def test_a_listing_that_fails_does_not_stop_the_pass(self, monkeypatch) -> None:
        def refuse() -> list[nvapi.DriverSetting]:
            raise nvapi.NvapiError("NvAPI_DRS_EnumSettings", -1)

        monkeypatch.setattr(nvapi, "dump_driver_settings", refuse)
        driver_without(monkeypatch, *APP_ERA)
        registry = FakeRegistry([NVIDIA_LOW_LATENCY])

        assert narrow_nvidia_choices(registry, None) == 1  # type: ignore[arg-type]
        assert registry.settings["gpu-nvidia:low_latency"].choices == ("off", "on")

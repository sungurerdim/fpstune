"""The packet-burst report must name causes it can prove, and admit the rest.

The whole point is that CoD's warning is ambiguous: the engine reports a
client-side stall as a network fault. A diagnostic that guesses would repeat the
original defect in a new place, so "could not read" has to stay distinct from
"fine".
"""

from __future__ import annotations

import pytest

from fpstune.diagnostics.packet_burst import build_report
from fpstune.settings.applicability import ABSENT_READINGS
from fpstune.settings.registry import SettingsRegistry


@pytest.fixture(scope="module")
def registry() -> SettingsRegistry:
    """A registry that holds every setting the report links to, on any host.

    Two of the remedies are derived from hardware and are registered only when
    that hardware can be read: the VRAM target needs the card's size, the frame
    cap needs the panel's refresh. A plain `SettingsRegistry()` therefore holds
    them on a developer's machine and not on a bare CI runner, which made these
    tests quietly assertions about the machine rather than about the report —
    they passed here and failed there.

    Supplying the hardware explicitly keeps the subject the report's logic. What
    the report does when a remedy genuinely is not registered is a separate
    behaviour, asserted in TestAMissingRemedy below.
    """
    from fpstune.settings.definitions.game_configs import (
        create_mw3_fps_cap_setting,
        create_mw3_vram_scale_setting,
    )

    built = SettingsRegistry()
    if built.get("game_config:mw3:vram_scale") is None:
        built.register(create_mw3_vram_scale_setting(8 * 1024))
    if built.get("game_config:mw3:fps_cap_ingame") is None:
        built.register(create_mw3_fps_cap_setting(240))
    return built


class TestReportShape:
    def test_every_check_names_the_setting_that_fixes_it(self, registry: SettingsRegistry) -> None:
        # A finding with no remedy is a complaint.
        report = build_report(registry)
        assert report.checks
        for c in report.checks:
            assert c.remedy_setting_id, c.id

    def test_every_remedy_is_a_setting_that_actually_exists(
        self, registry: SettingsRegistry
    ) -> None:
        for c in build_report(registry).checks:
            assert registry.get(c.remedy_setting_id) is not None, c.remedy_setting_id

    def test_the_first_check_is_the_one_the_sources_name_first(
        self, registry: SettingsRegistry
    ) -> None:
        assert build_report(registry).checks[0].id == "texture_streaming"


class TestUnknownIsNotOk:
    def test_no_detected_values_reports_unknown_not_clear(self, registry: SettingsRegistry) -> None:
        # Reporting "no cause present" from an empty scan would be the same
        # self-confirming answer the read-only lock used to produce.
        report = build_report(registry)
        assert all(c.status == "unknown" for c in report.checks)
        assert not report.at_risk
        assert "could not be read" in report.summary

    def test_a_not_installed_value_is_unknown_not_at_risk(self, registry: SettingsRegistry) -> None:
        report = build_report(registry, {"game_config:mw3:texture_streaming": "not_installed"})
        check = next(c for c in report.checks if c.id == "texture_streaming")
        assert check.status == "unknown"

    def test_a_none_value_is_unknown(self, registry: SettingsRegistry) -> None:
        report = build_report(registry, {"game_config:mw3:texture_streaming": None})
        check = next(c for c in report.checks if c.id == "texture_streaming")
        assert check.status == "unknown"

    @pytest.mark.parametrize("sentinel", sorted(ABSENT_READINGS))
    def test_every_absence_sentinel_is_unknown(
        self, registry: SettingsRegistry, sentinel: str
    ) -> None:
        """This module re-spelled the sentinel set as a local two-string tuple,
        so ``not_supported`` and ``not_found`` were compared against the wanted
        value and reported as a present cause of the packet-burst warning —
        telling the player to change a setting the machine does not have."""
        report = build_report(registry, {"game_config:mw3:texture_streaming": sentinel})
        check = next(c for c in report.checks if c.id == "texture_streaming")
        assert check.status == "unknown"

    def test_an_empty_reading_is_unknown(self, registry: SettingsRegistry) -> None:
        """The empty string is not an absence sentinel — a detector that
        answered with nothing has not said the feature is missing, only that it
        could not read it — but it must still not be compared as a value."""
        report = build_report(registry, {"game_config:mw3:texture_streaming": "   "})
        check = next(c for c in report.checks if c.id == "texture_streaming")
        assert check.status == "unknown"


class TestCauseEvaluation:
    def test_streaming_left_on_is_reported_at_risk(self, registry: SettingsRegistry) -> None:
        report = build_report(registry, {"game_config:mw3:texture_streaming": "default"})
        check = next(c for c in report.checks if c.id == "texture_streaming")
        assert check.status == "at_risk"
        assert check in report.at_risk

    def test_streaming_capped_is_reported_ok(self, registry: SettingsRegistry) -> None:
        report = build_report(registry, {"game_config:mw3:texture_streaming": "minimal"})
        check = next(c for c in report.checks if c.id == "texture_streaming")
        assert check.status == "ok"

    def test_per_machine_targets_come_from_the_settings_own_recommendation(
        self, registry: SettingsRegistry
    ) -> None:
        # VRAM headroom and the frame cap are derived from the card and the
        # monitor; a literal target here would be wrong on most machines and
        # would contradict the setting it links to.
        vram = registry.get("game_config:mw3:vram_scale")
        cap = registry.get("game_config:mw3:fps_cap_ingame")
        assert vram is not None and cap is not None

        report = build_report(
            registry,
            {
                "game_config:mw3:vram_scale": vram.recommended_value,
                "game_config:mw3:fps_cap_ingame": cap.recommended_value,
            },
        )
        assert next(c for c in report.checks if c.id == "vram_headroom").status == "ok"
        assert next(c for c in report.checks if c.id == "frame_cap").status == "ok"

    def test_a_wrong_frame_cap_is_flagged(self, registry: SettingsRegistry) -> None:
        report = build_report(registry, {"game_config:mw3:fps_cap_ingame": 30})
        assert next(c for c in report.checks if c.id == "frame_cap").status == "at_risk"


class TestSummary:
    def test_summary_counts_the_causes_found(self, registry: SettingsRegistry) -> None:
        report = build_report(
            registry,
            {
                "game_config:mw3:texture_streaming": "default",
                "game_config:mw3:world_streaming_quality": "High",
            },
        )
        assert len(report.at_risk) == 2
        assert "2 likely cause" in report.summary

    def test_summary_is_clear_only_when_everything_was_actually_read(
        self, registry: SettingsRegistry
    ) -> None:
        values = {}
        for c in build_report(registry).checks:
            setting = registry.get(c.remedy_setting_id)
            assert setting is not None
            values[c.remedy_setting_id] = setting.recommended_value

        report = build_report(registry, values)
        assert not report.at_risk
        assert not report.unknown
        assert report.summary == "No known cause present on this machine"


class TestAMissingRemedy:
    """A remedy the machine cannot have is reported, never silently dropped.

    `game_config:mw3:vram_scale` is registered only when the card's VRAM can be
    read, because the right share of VRAM is a fact about the card and there is
    no honest number without one. A machine whose GPU cannot be read therefore
    reaches this report with one of its remedies absent — a bare CI runner is
    exactly that machine — and the answer must be "could not check", never "fine".
    """

    def test_an_unregistered_remedy_is_unknown_rather_than_clear(self) -> None:
        bare = SettingsRegistry()
        for setting_id in ("game_config:mw3:vram_scale", "game_config:mw3:fps_cap_ingame"):
            bare._settings.pop(setting_id, None)

        report = build_report(bare)
        missing = [c for c in report.checks if c.id in ("vram_headroom", "frame_cap")]
        assert missing, "the report no longer covers the derived settings"
        for check in missing:
            assert check.status == "unknown"
            assert "not registered on this machine" in check.detail

    def test_it_still_names_the_setting_that_would_fix_it(self) -> None:
        """The id is how the UI offers the button, so it survives the setting's absence."""
        bare = SettingsRegistry()
        bare._settings.pop("game_config:mw3:vram_scale", None)

        check = next(c for c in build_report(bare).checks if c.id == "vram_headroom")
        assert check.remedy_setting_id == "game_config:mw3:vram_scale"

    def test_a_machine_missing_a_remedy_is_never_summarised_as_clear(self) -> None:
        """ "No known cause present" must require having actually checked."""
        bare = SettingsRegistry()
        bare._settings.pop("game_config:mw3:vram_scale", None)

        values = {
            c.remedy_setting_id: s.recommended_value
            for c in build_report(bare).checks
            if (s := bare.get(c.remedy_setting_id)) is not None
        }
        report = build_report(bare, values)
        assert report.unknown, "an unread cause must keep the report from claiming a clean machine"
        assert report.summary != "No known cause present on this machine"

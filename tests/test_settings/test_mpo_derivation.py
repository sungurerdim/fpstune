"""Which registry value disables MPO is a property of the Windows build.

The concrete defect: fpstune wrote GraphicsDrivers\\DisableOverlays on every
machine. On 23H2 that value is not the one Windows honours, so the tweak did
nothing — and because detection reads back the value fpstune itself wrote, it
reported success. From 24H2 on, builds have honoured either value depending on
the servicing update, so both are written there.
"""

from __future__ import annotations

import pytest

from fpstune.settings.definitions.display import _mpo_values, create_mpo_setting

DWM = (r"SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode", 5)
GFX = (r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "DisableOverlays", 1)


class TestKeyFollowsTheBuild:
    @pytest.mark.parametrize(
        ("build", "values"),
        [
            (22631, (DWM,)),  # 23H2
            (26100, (DWM, GFX)),  # 24H2
            (26200, (DWM, GFX)),  # 25H2
            (27000, (DWM, GFX)),  # later
        ],
    )
    def test_writes_every_value_that_build_may_honour(
        self, build: int, values: tuple[tuple[str, str, int], ...]
    ) -> None:
        assert _mpo_values(build) == values

    @pytest.mark.parametrize("build", [22631, 26100, 26200])
    def test_detect_and_apply_cover_the_same_values(self, build: int) -> None:
        # Reading one value and writing another is how a tweak reports a state
        # it did not set.
        s = create_mpo_setting(build)
        for path, name, on in _mpo_values(build):
            entry = f",@('HKLM:\\{path}', '{name}', {on})"
            assert entry in s.detect_command, (build, name)
            assert entry in s.apply_command, (build, name)

    def test_23h2_never_touches_the_graphicsdrivers_value(self) -> None:
        s = create_mpo_setting(22631)
        assert "DisableOverlays" not in s.detect_command
        assert "DisableOverlays" not in s.apply_command

    def test_disabled_only_when_every_value_is_in_place(self) -> None:
        # One value of two is still MPO on, on a build that reads the other.
        assert "$set -eq $targets.Count" in create_mpo_setting(26200).detect_command


class TestRevertRemovesTheOverride:
    def test_reverting_deletes_rather_than_zeroes(self) -> None:
        # A 0 is still an override; deleting the value is what hands the
        # decision back to Windows.
        apply = create_mpo_setting(26200).apply_command
        assert "Remove-ItemProperty" in apply
        assert "-Value 0" not in apply


class TestNotOfferedUnderVrr:
    def test_a_vrr_panel_makes_it_not_applicable(self) -> None:
        from fpstune.settings.applicability import ApplicabilityChecker, HardwareContext

        s = create_mpo_setting(26200)
        vrr = ApplicabilityChecker(HardwareContext(has_vrr_monitor=True)).is_applicable(s)
        fixed = ApplicabilityChecker(HardwareContext(has_vrr_monitor=False)).is_applicable(s)
        assert vrr[0] is False
        assert fixed == (True, "")


class TestEvidenceMatchesReality:
    def test_it_is_experimental_not_proven(self) -> None:
        # Undocumented by Microsoft, absent from NVIDIA's current instructions,
        # and it moves between Windows builds.
        assert create_mpo_setting(26200).evidence_level == "experimental"

    def test_experimental_carries_the_required_risk_level_and_warning(self) -> None:
        s = create_mpo_setting(26200)
        assert s.risk_level == "advanced"
        assert s.risk_warning is not None

    def test_the_warning_names_the_vrr_interaction(self) -> None:
        # This machine's whole latency setup rests on VRR; a reported
        # interaction with it has to reach the user rather than a comment.
        warning = create_mpo_setting(26200).risk_warning
        assert warning is not None
        assert "refresh" in warning.lower() or "vrr" in warning.lower()

    def test_no_invented_percentage_is_claimed(self) -> None:
        # The old "+0-15%" and "-1.5 ms" came from a single blog post. This
        # fixes a defect when the defect is present and does nothing otherwise.
        scores = create_mpo_setting(26200).impact_scores
        assert scores.get("latency_ms") == 0.0
        assert "fps_1_percent_low" not in scores

    def test_the_description_says_which_values_it_writes(self) -> None:
        assert "DisableOverlays" in create_mpo_setting(26200).description
        assert "OverlayTestMode" in create_mpo_setting(26200).description
        assert "DisableOverlays" not in create_mpo_setting(22631).description

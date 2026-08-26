"""Which registry value disables MPO is a property of the Windows build.

The concrete defect: fpstune wrote GraphicsDrivers\\DisableOverlays on every
machine. On 23H2 and 24H2 that value is not the one Windows honours, so the
tweak did nothing — and because detection reads back the value fpstune itself
wrote, it reported success. Same silent-no-op shape as the MW3 config keys.
"""

from __future__ import annotations

import pytest

from fpstune.settings.definitions.display import create_mpo_setting

DWM_PATH = r"SOFTWARE\Microsoft\Windows\Dwm"
GFX_PATH = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"


class TestKeyFollowsTheBuild:
    @pytest.mark.parametrize(
        ("build", "path", "name", "on_value"),
        [
            (22631, DWM_PATH, "OverlayTestMode", 5),  # 23H2
            (26100, DWM_PATH, "OverlayTestMode", 5),  # 24H2
            (26200, GFX_PATH, "DisableOverlays", 1),  # 25H2
            (27000, GFX_PATH, "DisableOverlays", 1),  # later
        ],
    )
    def test_writes_the_value_that_build_honours(
        self, build: int, path: str, name: str, on_value: int
    ) -> None:
        s = create_mpo_setting(build)
        assert s.detect_args["path"] == path
        assert s.detect_args["name"] == name
        assert s.apply_args["path"] == path
        assert s.apply_value_map["disabled"] == on_value

    def test_detect_and_apply_never_point_at_different_values(self) -> None:
        # Reading one value and writing another is how a tweak reports a state
        # it did not set.
        for build in (22631, 26100, 26200, 27000):
            s = create_mpo_setting(build)
            assert s.detect_args["path"] == s.apply_args["path"], build
            assert s.detect_args["name"] == s.apply_args["name"], build

    def test_the_written_value_is_the_one_detection_maps_to_disabled(self) -> None:
        for build in (22631, 26200):
            s = create_mpo_setting(build)
            written = s.apply_value_map["disabled"]
            assert s.value_map[written] == "disabled", build

    def test_the_build_where_the_key_changes_is_named_once(self) -> None:
        from fpstune.settings.definitions.display import _MPO_GRAPHICSDRIVERS_BUILD

        assert create_mpo_setting(_MPO_GRAPHICSDRIVERS_BUILD - 1).detect_args["path"] == DWM_PATH
        assert create_mpo_setting(_MPO_GRAPHICSDRIVERS_BUILD).detect_args["path"] == GFX_PATH


class TestRevertRemovesTheOverride:
    def test_reverting_deletes_rather_than_zeroes(self) -> None:
        # A 0 is still an override; deleting the value is what hands the
        # decision back to Windows.
        for build in (22631, 26200):
            assert create_mpo_setting(build).apply_value_map["enabled"] is None, build

    def test_absent_value_reads_as_enabled(self) -> None:
        # Which is Windows' own default — MPO on.
        assert create_mpo_setting(26200).value_map[None] == "enabled"


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

    def test_the_description_says_which_value_it_writes(self) -> None:
        assert "DisableOverlays" in create_mpo_setting(26200).description
        assert "OverlayTestMode" in create_mpo_setting(22631).description

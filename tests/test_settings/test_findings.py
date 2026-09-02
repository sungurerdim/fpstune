"""The numbers behind an advisory's word reach the API as a ``finding``.

``network:*:link_capability`` used to write "linked at 100 Mbps but the adapter
supports 2500 Mbps" into the log and hand the UI the word ``below_capability``.
The user saw the word. These tests hold the whole path: a detector returns a
``Reading``, the PowerShell path lifts a ``FPSTUNE_FINDING:`` line out of the
script's output, the engine splits value from finding so every comparison sees
the plain value, and the finding lands on the ``DetectionResult``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fpstune.settings.base import DetectionResult, Reading
from fpstune.settings.definitions.network import create_link_capability_setting
from fpstune.settings.detection import DetectionEngine
from fpstune.settings.executors.powershell import PowerShellExecutor
from fpstune.settings.executors.ps_batch import command_is_batchable


def _setting(setting_id: str = "network:7:link_capability") -> MagicMock:
    setting = MagicMock()
    setting.id = setting_id
    setting.recommended_value = "at_capability"
    setting.is_action = False
    setting.is_service = False
    setting.category = MagicMock()
    setting.category.value = "network"
    setting.applicable_conditions = {}
    return setting


class TestTheEngineSplitsTheReading:
    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_value_is_compared_and_finding_is_carried(self, mock_detect: MagicMock) -> None:
        finding = {"kind": "link_speed", "linked_mbps": 100, "ceiling_mbps": 2500}
        mock_detect.return_value = (Reading("below_capability", finding), None)

        result = DetectionEngine(max_workers=1).detect_all([_setting()])[
            "network:7:link_capability"
        ]

        assert result.value == "below_capability"
        assert result.is_optimized is False
        assert result.finding == finding

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_a_reading_at_the_ceiling_is_optimized_with_its_numbers(
        self, mock_detect: MagicMock
    ) -> None:
        """A clear check still shows what it measured — evidence the check ran."""
        finding = {"kind": "link_speed", "linked_mbps": 2500, "ceiling_mbps": 2500}
        mock_detect.return_value = (Reading("at_capability", finding), None)

        result = DetectionEngine(max_workers=1).detect_all([_setting()])[
            "network:7:link_capability"
        ]

        assert result.is_optimized is True
        assert result.finding == finding

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_a_plain_value_has_no_finding(self, mock_detect: MagicMock) -> None:
        mock_detect.return_value = ("at_capability", None)
        result = DetectionEngine(max_workers=1).detect_all([_setting()])[
            "network:7:link_capability"
        ]
        assert result.finding is None

    def test_the_finding_is_part_of_the_dict_form(self) -> None:
        result = DetectionResult("a:b", "x", None, 1, finding={"kind": "k"})
        assert result.to_dict()["finding"] == {"kind": "k"}


class TestThePowerShellPathLiftsTheFindingLine:
    def _detect(self, output: str, monkeypatch) -> tuple[object, str | None]:
        setting = create_link_capability_setting(7, "Ethernet")
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr(PowerShellExecutor, "_run", lambda *_a, **_k: (True, output))
        monkeypatch.setattr(
            "fpstune.settings.executors.powershell.get_batched_detect", lambda _id: None
        )
        return PowerShellExecutor().detect(setting)

    def test_the_json_line_becomes_the_finding_and_the_last_line_the_value(
        self, monkeypatch
    ) -> None:
        output = (
            'FPSTUNE_FINDING: {"kind":"link_speed","linked_mbps":100,"ceiling_mbps":2500}\n'
            "below_capability\n"
        )
        reading, error = self._detect(output, monkeypatch)
        assert error is None
        assert isinstance(reading, Reading)
        assert reading.value == "below_capability"
        assert reading.finding == {"kind": "link_speed", "linked_mbps": 100, "ceiling_mbps": 2500}

    def test_a_warn_line_is_still_only_for_the_log(self, monkeypatch) -> None:
        reading, error = self._detect("FPSTUNE_WARN: something odd\nat_capability\n", monkeypatch)
        assert (reading, error) == ("at_capability", None)

    def test_a_broken_finding_line_is_dropped_not_shown(self, monkeypatch) -> None:
        """Half a JSON object must never reach a screen as a finding."""
        reading, error = self._detect("FPSTUNE_FINDING: {not json\nat_capability\n", monkeypatch)
        assert (reading, error) == ("at_capability", None)

    def test_a_finding_without_a_kind_is_dropped(self, monkeypatch) -> None:
        reading, error = self._detect('FPSTUNE_FINDING: {"linked_mbps": 100}\nx\n', monkeypatch)
        assert (reading, error) == ("x", None)


class TestTheLinkSpeedScript:
    def test_it_writes_the_numbers_as_a_finding_in_both_outcomes(self) -> None:
        cmd = create_link_capability_setting(7, "Ethernet").detect_command
        assert "FPSTUNE_FINDING: " in cmd
        assert "kind='link_speed'" in cmd
        assert "linked_mbps=$linked" in cmd and "ceiling_mbps=$ceiling" in cmd
        # The finding is written before the branch, so a clear link reports too.
        assert cmd.index("FPSTUNE_FINDING") < cmd.index("'at_capability'")

    def test_it_stays_batchable(self) -> None:
        """Write-Output keeps the finding inside the pipeline a batch group captures."""
        assert command_is_batchable(create_link_capability_setting(7, "Ethernet").detect_command)

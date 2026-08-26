"""Tests for DetectionEngine — parallel setting detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import fpstune.settings.detection as detection_module
from fpstune.settings.applicability import HardwareContext
from fpstune.settings.base import DetectionResult
from fpstune.settings.detection import DetectionEngine


def _make_setting(
    setting_id: str = "test:setting",
    recommended_value: str | None = "disabled",
    is_action: bool = False,
    category: str = "core",
    applicable_conditions: dict | None = None,
) -> MagicMock:
    """Create a mock SettingExecutor for testing."""
    setting = MagicMock()
    setting.id = setting_id
    setting.recommended_value = recommended_value
    setting.is_action = is_action
    setting.category = MagicMock()
    setting.category.value = category
    setting.applicable_conditions = applicable_conditions or {}
    # A bare MagicMock answers truthy to every attribute, so without this every
    # mock setting looked like a Windows service and got the service wording for
    # "not applicable" regardless of its ID. Mirror the real rule.
    setting.is_service = setting_id.startswith("services:")
    return setting


class TestDetectionEngineInit:
    """Tests for DetectionEngine initialization."""

    def test_default_parameters(self) -> None:
        """Engine should have sensible defaults."""
        engine = DetectionEngine()
        assert engine.max_workers == 16
        assert engine.timeout == 5.0
        assert engine.context is None
        assert engine.checker is None

    def test_custom_parameters(self) -> None:
        """Engine should accept custom parameters."""
        ctx = HardwareContext(gpu_vendor="nvidia")
        engine = DetectionEngine(max_workers=4, timeout_per_setting=10.0, hardware_context=ctx)
        assert engine.max_workers == 4
        assert engine.timeout == 10.0
        assert engine.context is ctx
        assert engine.checker is not None


class TestDetectAll:
    """Tests for detect_all parallel detection."""

    def test_empty_settings_returns_empty(self) -> None:
        """detect_all with empty list should return empty dict."""
        engine = DetectionEngine()
        result = engine.detect_all([])
        assert result == {}

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_single_setting_detected(self, mock_detect: MagicMock) -> None:
        """detect_all should detect a single setting correctly."""
        mock_detect.return_value = ("disabled", None)

        engine = DetectionEngine(max_workers=1)
        setting = _make_setting(setting_id="timer:hpet", recommended_value="disabled")

        results = engine.detect_all([setting])

        assert "timer:hpet" in results
        result = results["timer:hpet"]
        assert result.value == "disabled"
        assert result.error is None
        assert result.is_optimized is True

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_non_optimized_value(self, mock_detect: MagicMock) -> None:
        """Setting with value != recommended should be marked not optimized."""
        mock_detect.return_value = ("enabled", None)

        engine = DetectionEngine(max_workers=1)
        setting = _make_setting(setting_id="timer:hpet", recommended_value="disabled")

        results = engine.detect_all([setting])
        assert results["timer:hpet"].is_optimized is False

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_multiple_settings_parallel(self, mock_detect: MagicMock) -> None:
        """detect_all should handle multiple settings concurrently."""
        mock_detect.return_value = ("value", None)

        engine = DetectionEngine(max_workers=4)
        settings = [_make_setting(setting_id=f"test:s{i}") for i in range(5)]

        results = engine.detect_all(settings)
        assert len(results) == 5
        for i in range(5):
            assert f"test:s{i}" in results

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_detection_error_captured(self, mock_detect: MagicMock) -> None:
        """Detection errors should be captured per-setting, not crash the engine."""
        mock_detect.side_effect = RuntimeError("PowerShell failed")

        engine = DetectionEngine(max_workers=1)
        setting = _make_setting(setting_id="broken:setting")

        results = engine.detect_all([setting])
        result = results["broken:setting"]
        assert result.value is None
        assert result.error is not None
        assert "PowerShell failed" in result.error

    def test_non_applicable_settings_skipped(self) -> None:
        """Non-applicable settings should get result without running detection."""
        ctx = HardwareContext(gpu_vendor="nvidia")
        engine = DetectionEngine(hardware_context=ctx)

        amd_setting = _make_setting(
            setting_id="gpu:amd_only",
            applicable_conditions={"gpu_vendor": "amd"},
        )

        results = engine.detect_all([amd_setting])
        assert "gpu:amd_only" in results
        result = results["gpu:amd_only"]
        assert result.is_applicable is False
        assert result.value is None
        assert result.time_ms == 0

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_not_available_value_marks_not_applicable(self, mock_detect: MagicMock) -> None:
        """Detection returning 'not_available' should mark setting as not applicable."""
        mock_detect.return_value = ("not_available", None)

        engine = DetectionEngine(max_workers=1)
        setting = _make_setting(setting_id="feature:missing")

        results = engine.detect_all([setting])
        result = results["feature:missing"]
        assert result.is_applicable is False
        assert result.value is None

    @pytest.mark.parametrize(
        "sentinel", ["not_supported", "not_found", "not_available", "not_installed"]
    )
    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_every_absent_reading_marks_not_applicable(
        self, mock_detect: MagicMock, sentinel: str
    ) -> None:
        """All four spellings mean the same thing, and detection must know all four.

        This used to be a tuple written by hand here, and it listed three. The
        one it missed was `not_installed`, which every game setting emits on a
        machine without the game — 18 settings on the CI runner surfaced the
        literal string as their value, outside their own `choices`, so their
        verification could never succeed. The frontend then patched the same
        rule back in three separate places.
        """
        mock_detect.return_value = (sentinel, None)

        engine = DetectionEngine(max_workers=1)
        setting = _make_setting(setting_id="game_config:mw3:vsync")

        result = engine.detect_all([setting])["game_config:mw3:vsync"]
        assert result.is_applicable is False, f"{sentinel} must not read as a value"
        assert result.value is None
        assert result.is_optimized is False

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_an_absent_reading_survives_shell_whitespace(self, mock_detect: MagicMock) -> None:
        """These arrive from PowerShell stdout as often as from a constant.

        An exact-match tuple would let a trailing CRLF turn "this does not exist"
        back into an ordinary value — the same cross-type gap `values_equal`
        exists to close for comparisons.
        """
        mock_detect.return_value = ("Not_Installed\r\n", None)

        engine = DetectionEngine(max_workers=1)
        setting = _make_setting(setting_id="game_config:cs2:fps_max")

        result = engine.detect_all([setting])["game_config:cs2:fps_max"]
        assert result.is_applicable is False
        assert result.value is None

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_a_plain_value_is_still_a_value(self, mock_detect: MagicMock) -> None:
        """The guard has to reject something to be worth having."""
        mock_detect.return_value = ("disabled", None)

        engine = DetectionEngine(max_workers=1)
        setting = _make_setting(setting_id="game_config:mw3:vsync")

        result = engine.detect_all([setting])["game_config:mw3:vsync"]
        assert result.is_applicable is True
        assert result.value == "disabled"

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_service_not_found_marks_not_applicable(self, mock_detect: MagicMock) -> None:
        """Service settings returning None should be marked not applicable."""
        mock_detect.return_value = (None, None)

        engine = DetectionEngine(max_workers=1)
        setting = _make_setting(setting_id="services:NonExistentService")

        results = engine.detect_all([setting])
        result = results["services:NonExistentService"]
        assert result.is_applicable is False
        assert "not installed" in result.applicable_reason.lower()

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_null_value_with_error_is_applicable(self, mock_detect: MagicMock) -> None:
        """None value WITH error should remain applicable (detection failure, not N/A)."""
        mock_detect.return_value = (None, "timeout")

        engine = DetectionEngine(max_workers=1)
        setting = _make_setting(setting_id="test:errored")

        results = engine.detect_all([setting])
        result = results["test:errored"]
        assert result.is_applicable is True
        assert result.error == "timeout"
        assert result.is_optimized is False

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_unknown_value_not_treated_as_optimized(self, mock_detect: MagicMock) -> None:
        """Value 'unknown' should never be considered optimized."""
        mock_detect.return_value = ("unknown", None)

        engine = DetectionEngine(max_workers=1)
        setting = _make_setting(setting_id="test:unknown_val", recommended_value="unknown")

        results = engine.detect_all([setting])
        assert results["test:unknown_val"].is_optimized is False


class TestWholeRunTimeout:
    """The scan-wide deadline must produce results, not an exception (#22).

    ``as_completed(futures, timeout=total_timeout)`` raises ``TimeoutError`` and
    nothing caught it. It escaped ``detect_all``, so the settings that had not
    finished got no entry at all — a caller reading ``results[id]`` hit a
    KeyError instead of a timed-out reading — and the enclosing
    ``with ThreadPoolExecutor`` then blocked in ``shutdown(wait=True)`` on the
    very work the deadline had just given up on.
    """

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_unfinished_settings_get_a_timeout_result(self, mock_detect: MagicMock) -> None:
        mock_detect.return_value = ("enabled", None)
        settings = [_make_setting(setting_id=f"test:slow_{i}") for i in range(3)]

        def _deadline_expired(_futures, timeout=None):  # noqa: ARG001
            raise TimeoutError("scan deadline")

        engine = DetectionEngine(max_workers=2)
        with patch("fpstune.settings.detection.as_completed", _deadline_expired):
            results = engine.detect_all(settings)

        assert set(results) == {s.id for s in settings}
        for setting in settings:
            result = results[setting.id]
            assert result.value is None
            assert result.error is not None
            assert "timed out" in result.error
            assert result.is_optimized is False
            assert result.is_applicable is True

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_results_already_collected_survive_the_deadline(self, mock_detect: MagicMock) -> None:
        """A deadline must not overwrite readings that did arrive."""
        mock_detect.return_value = ("enabled", None)
        settings = [_make_setting(setting_id=f"test:mixed_{i}") for i in range(3)]
        real_as_completed = detection_module.as_completed

        def _one_then_deadline(futures, timeout=None):  # noqa: ARG001
            iterator = real_as_completed(futures)
            yield next(iterator)
            raise TimeoutError("scan deadline")

        engine = DetectionEngine(max_workers=2)
        with patch("fpstune.settings.detection.as_completed", _one_then_deadline):
            results = engine.detect_all(settings)

        assert set(results) == {s.id for s in settings}
        completed = [r for r in results.values() if r.value == "enabled"]
        timed_out = [r for r in results.values() if r.error and "timed out" in r.error]
        assert len(completed) == 1
        assert len(timed_out) == 2


class TestDetectOne:
    """Tests for detect_one (single-setting detection)."""

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_detect_one_returns_result(self, mock_detect: MagicMock) -> None:
        """detect_one should return a DetectionResult."""
        mock_detect.return_value = ("enabled", None)

        engine = DetectionEngine()
        setting = _make_setting()

        result = engine.detect_one(setting)
        assert isinstance(result, DetectionResult)
        assert result.value == "enabled"
        assert result.time_ms >= 0


class TestPrefetchReachesTheScanCache:
    """The prefetch pool must write into the scan the workers read.

    This is guarding a defect that shipped with the whole suite green: the
    prefetch pool ran ``lambda fn: copy_context().run(fn)``, so the context was
    copied inside the worker thread — whose context is empty — instead of in the
    submitting thread. Every prefetch then ran its multi-second query outside the
    scan and threw the snapshot away, and the batches they exist to fill were
    silently dead in production while every assertion about them passed.
    """

    def _batched_setting(self, setting_id: str, detect_args: dict) -> MagicMock:
        setting = _make_setting(setting_id=setting_id)
        setting.detect_args = detect_args
        setting.detect_type = MagicMock()  # never equals DetectType.POWERSHELL
        setting.detect_command = ""
        return setting

    def test_each_snapshot_is_fetched_exactly_once_per_scan(self) -> None:
        """A snapshot fetched more than once means a worker missed the cache."""
        from fpstune.settings.executors import ps_batch

        calls = {"services": 0, "adapters": 0}

        def fake_services() -> dict:
            calls["services"] += 1
            return {"spooler": {"start_type": 2}}

        def fake_adapters() -> dict:
            calls["adapters"] += 1
            return {"7|*flowcontrol": "0"}

        def worker(setting: MagicMock) -> tuple[str, None]:
            # Mirror what the real executors do: read through the batch helpers,
            # which re-fetch on a miss. A discarded prefetch shows up as a count
            # above one; the pre-fix code fetched services eleven times here.
            if "batch_service" in setting.detect_args:
                return ps_batch.get_service_start_type("spooler"), None
            return str(ps_batch.get_adapter_property(7, "*FlowControl")), None

        settings = [
            self._batched_setting(f"services:s{i}", {"batch_service": "spooler"}) for i in range(5)
        ] + [
            self._batched_setting(f"network:7:n{i}", {"batch_adapter_keyword": "*FlowControl"})
            for i in range(5)
        ]

        with (
            patch.object(ps_batch, "_fetch_services_snapshot", fake_services),
            patch.object(ps_batch, "_fetch_adapter_properties_snapshot", fake_adapters),
            patch("fpstune.settings.detection.CommandExecutor.detect", side_effect=worker),
        ):
            results = DetectionEngine(max_workers=8).detect_all(settings)

        assert calls == {"services": 1, "adapters": 1}
        assert len(results) == 10

    def test_the_powershell_batch_actually_runs(self) -> None:
        """With no scan cache, prefetch_powershell_detects returns {} and runs nothing."""
        from fpstune.settings.base import DetectType
        from fpstune.settings.executors import ps_batch

        seen: list[list[tuple[str, str]]] = []

        def fake_group(specs: list[tuple[str, str]]) -> dict[str, str]:
            seen.append(specs)
            return {sid: "batched" for sid, _ in specs}

        batched: list[str | None] = []

        def worker(setting: MagicMock) -> tuple[str, None]:
            if setting.id.startswith("system:"):
                batched.append(ps_batch.get_batched_detect(setting.id))
            return "value", None

        settings = []
        for i in range(3):
            setting = _make_setting(setting_id=f"system:s{i}")
            setting.detect_args = {}
            setting.detect_type = DetectType.POWERSHELL
            setting.detect_command = f"Write-Output {i}"
            settings.append(setting)
        # A second prefetcher is required, not incidental: with only one the
        # engine runs it inline on the calling thread, where the cache is
        # visible either way, and the defect this test guards cannot appear.
        settings.append(self._batched_setting("services:spooler", {"batch_service": "spooler"}))

        with (
            patch.object(ps_batch, "_run_detect_group", fake_group),
            patch.object(ps_batch, "_fetch_services_snapshot", lambda: {}),
            patch("fpstune.settings.detection.CommandExecutor.detect", side_effect=worker),
        ):
            DetectionEngine(max_workers=4).detect_all(settings)

        assert seen, "the batch never ran — the workers had no scan cache to read"
        assert batched == ["batched"] * 3


class TestDetectByCategory:
    """Tests for detect_by_category filtering."""

    @patch("fpstune.settings.detection.CommandExecutor.detect")
    def test_filters_by_category(self, mock_detect: MagicMock) -> None:
        """detect_by_category should only detect settings in the target category."""
        mock_detect.return_value = ("value", None)

        engine = DetectionEngine(max_workers=2)
        core_setting = _make_setting(setting_id="core:a", category="core")
        net_setting = _make_setting(setting_id="network:b", category="network")

        results = engine.detect_by_category([core_setting, net_setting], "core")
        assert "core:a" in results
        assert "network:b" not in results

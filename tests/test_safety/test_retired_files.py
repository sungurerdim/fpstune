"""fpstune keeps no history and no previous values (#103, #107).

A reset is an apply of the setting's own default; nothing remembers what a
setting held before, on disk or in memory, and there is no History tab. What
earlier releases left behind (`originals.json`, `history.json`) is deleted at
start-up, and nothing writes either file again.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from fpstune.api.main import create_app, lifespan
from fpstune.safety.retired_files import remove_retired_files
from fpstune.settings.base import DefaultSource, DetectionResult
from fpstune.utils.config import get_config_dir
from tests.conftest import neutral_hardware_context


def _stored_state_files(root: Path) -> list[str]:
    """Any file under `root` that would be a stored previous value or history."""
    return sorted(
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and ("originals" in p.name or "history" in p.name)
    )


class TestThereIsNoHistoryToAskFor:
    """The in-memory change journal, its module and its endpoint are gone."""

    def test_the_history_endpoint_is_gone(self) -> None:
        client = TestClient(create_app(), raise_server_exceptions=False)

        assert client.get("/api/history").status_code == 404

    def test_the_journal_module_is_gone(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("fpstune.safety.history")

    def test_no_route_in_the_schema_mentions_history(self) -> None:
        paths = create_app().openapi()["paths"]

        assert [p for p in paths if "history" in p] == []


class TestRetiredFilesAreDeleted:
    def test_both_files_an_earlier_release_wrote_are_removed(self) -> None:
        config = get_config_dir()
        originals = config / "originals.json"
        journal = config / "history.json"
        originals.write_text('{"version": 1, "values": {}}', encoding="utf-8")
        journal.write_text('{"version": 1, "entries": []}', encoding="utf-8")

        removed = remove_retired_files()

        assert sorted(p.name for p in removed) == ["history.json", "originals.json"]
        assert not originals.exists() and not journal.exists()

    def test_the_interrupted_write_and_set_aside_leftovers_go_too(self, tmp_path: Path) -> None:
        for name in (
            "originals.json.tmp",
            "history.json.tmp",
            "history.unreadable-1700000000.json",
        ):
            (tmp_path / name).write_text("x", encoding="utf-8")
        keeper = tmp_path / "headroom.json"
        keeper.write_text("{}", encoding="utf-8")

        remove_retired_files(tmp_path)

        assert [p.name for p in tmp_path.iterdir()] == ["headroom.json"]

    def test_an_empty_directory_is_not_an_error(self, tmp_path: Path) -> None:
        assert remove_retired_files(tmp_path) == []

    def test_a_file_that_cannot_be_deleted_does_not_stop_the_rest(self, tmp_path: Path) -> None:
        stuck = tmp_path / "originals.json"
        other = tmp_path / "history.json"
        stuck.write_text("x", encoding="utf-8")
        other.write_text("x", encoding="utf-8")
        real_unlink = Path.unlink

        def _unlink(self: Path, *args: object, **kwargs: object) -> None:
            if self.name == "originals.json":
                raise PermissionError(5, "Access is denied")
            real_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

        with patch.object(Path, "unlink", _unlink):
            removed = remove_retired_files(tmp_path)

        assert [p.name for p in removed] == ["history.json"]
        assert stuck.exists() and not other.exists()

    @pytest.mark.asyncio
    async def test_start_up_deletes_them_from_the_users_config_directory(self) -> None:
        config = get_config_dir()
        (config / "originals.json").write_text("{}", encoding="utf-8")
        (config / "history.json").write_text("{}", encoding="utf-8")

        with (
            patch("fpstune.utils.hardware_manager.hardware_manager", MagicMock()),
            patch("fpstune.api.main.start_gpu_detection_async"),
            patch("fpstune.api.main.threading.Thread"),
            patch("fpstune.benchmark.scheduler.start_bench_scheduler"),
            patch("fpstune.benchmark.scheduler.stop_bench_scheduler"),
            patch("fpstune.utils.detect.is_gpu_detecting", return_value=False),
        ):
            async with lifespan(MagicMock()):
                assert _stored_state_files(config) == []


class TestNothingWritesThemAgain:
    """The regression: a scan and a write through the API leave no stored state."""

    @staticmethod
    def _fake_setting() -> MagicMock:
        s = MagicMock()
        s.id = "core:fake"
        s.display_name = "Fake"
        s.default_value = "stock"
        s.recommended_value = "tuned"
        s.choices = ("stock", "tuned")
        s.default_source = DefaultSource.WINDOWS_STOCK
        s.requires_reboot = False
        s.is_action = False
        s.is_readonly = False
        s.apply_type = MagicMock()
        s.apply_type.value = "registry"
        s.apply_args = {}
        # A real setting always carries this dict; a MagicMock attribute would
        # answer `.get()` with a truthy mock and read as an unmet condition.
        s.applicable_conditions = {}
        return s

    @staticmethod
    def _reading(value: str) -> DetectionResult:
        return DetectionResult(
            setting_id="core:fake",
            value=value,
            error=None,
            time_ms=1,
            is_optimized=False,
            is_applicable=True,
        )

    def test_a_full_scan_then_a_reset_leave_no_originals_and_no_history_file(self) -> None:
        setting = self._fake_setting()
        registry = MagicMock()
        registry.get.return_value = setting
        registry.get_all.return_value = [setting]
        engine = MagicMock()
        engine.detect_all.return_value = {"core:fake": self._reading("tuned")}
        engine.detect_one.return_value = self._reading("stock")
        client = TestClient(create_app(), raise_server_exceptions=False)

        with (
            patch("fpstune.api.routes.settings._get_registry", return_value=registry),
            patch(
                "fpstune.api.routes.settings._get_hardware_context",
                return_value=neutral_hardware_context(),
            ),
            patch("fpstune.api.routes.settings.DetectionEngine", return_value=engine),
            patch("fpstune.api.routes.settings.sys.platform", "linux"),
            patch(
                "fpstune.api.routes.settings_apply.CommandExecutor.apply",
                return_value=(True, None),
            ),
            patch("fpstune.api.routes.settings_apply.is_free", return_value=True),
            patch("fpstune.utils.self_check.ensure_checked_before_first_apply"),
        ):
            scan = client.post("/api/settings/detect", json={})
            reset = client.post("/api/settings/core:fake/apply", json={"value": "stock"})

        assert scan.status_code == 200
        assert reset.status_code == 200 and reset.json()["success"] is True
        assert _stored_state_files(get_config_dir()) == []
        assert "original_value" not in scan.json()["results"]["core:fake"]

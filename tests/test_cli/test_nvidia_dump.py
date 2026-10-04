"""`fpstune nvidia-dump` writes the driver's global settings to a file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from fpstune.commands.gpu import nvidia_dump
from fpstune.core.nvapi import DriverSetting, NvapiUnavailable


def test_the_dump_is_saved_with_fpstune_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("fpstune.utils.config.get_config_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "fpstune.core.nvapi.dump_driver_settings",
        lambda: [
            DriverSetting(0x10835002, 141, "global", False),
            DriverSetting(0x12345678, 1, "base", True),
        ],
    )

    result = CliRunner().invoke(nvidia_dump)

    assert result.exit_code == 0
    [saved] = list((tmp_path / "diagnostics").glob("nvidia-dump-*.json"))
    rows = json.loads(saved.read_text(encoding="utf-8"))
    assert rows[0] == {
        "id": "0x10835002",
        "value": "0x0000008d",
        "location": "global",
        "predefined": False,
        "fpstune_key": "fps_limit",
    }
    assert rows[1]["fpstune_key"] is None


def test_no_driver_says_so_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("fpstune.utils.config.get_config_dir", lambda: tmp_path)

    def unavailable() -> list[DriverSetting]:
        raise NvapiUnavailable("nvapi64.dll not loadable")

    monkeypatch.setattr("fpstune.core.nvapi.dump_driver_settings", unavailable)

    result = CliRunner().invoke(nvidia_dump)

    assert result.exit_code == 0
    assert "nvapi64.dll" in result.output
    assert not (tmp_path / "diagnostics").exists()

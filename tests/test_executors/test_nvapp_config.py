"""One switch in the NVIDIA App's own config.xml, changed without touching the rest.

The file belongs to NVIDIA, so the contract these tests pin is narrowness: the
value of one element changes, and every other byte — the other settings, the
attribute quoting, the scan-path list, the trailing newline — is the same bytes
after the write as before it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpstune.settings.applicability import NOT_AVAILABLE
from fpstune.settings.executors import nvapp_config

SAMPLE = (
    "<BackendConfiguration version='1.0'>\n"
    "  <Setting name='EnableUpdateTypeOPS' value='1' />\n"
    "  <Setting name='EnableAutomaticApplicationScan' value='1' />\n"
    "  <Setting name='EnableAutomaticApplyOPS' value='1' />\n"
    "  <Setting name='OOTBStatus' value='2' />\n"
    "  <Setting name='ApplicationScanPaths'>\n"
    "    <String>C:\\Program Files</String>\n"
    "  </Setting>\n"
    "</BackendConfiguration>\n"
)


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "config.xml"
    path.write_text(SAMPLE, encoding="utf-8", newline="")
    return path


def test_the_switch_reads_its_own_value(config: Path) -> None:
    assert nvapp_config.read_setting(nvapp_config.AUTO_APPLY_SETTING, config) == "1"


def test_only_the_named_switch_changes(config: Path) -> None:
    ok, error = nvapp_config.write_setting(nvapp_config.AUTO_APPLY_SETTING, "0", config)
    assert (ok, error) == (True, None)
    after = config.read_text(encoding="utf-8")
    assert after == SAMPLE.replace(
        "<Setting name='EnableAutomaticApplyOPS' value='1' />",
        "<Setting name='EnableAutomaticApplyOPS' value='0' />",
    )


def test_a_double_quoted_element_is_written_the_same_way(config: Path) -> None:
    """NVIDIA's file uses single quotes; another build's may not, and neither may be mangled."""
    double = config.read_text(encoding="utf-8").replace(
        "name='EnableAutomaticApplyOPS' value='1'", 'name="EnableAutomaticApplyOPS" value="1"'
    )
    config.write_text(double, encoding="utf-8", newline="")
    ok, _ = nvapp_config.write_setting(nvapp_config.AUTO_APPLY_SETTING, "0", config)
    assert ok is True
    assert "name=\"EnableAutomaticApplyOPS\" value='0'" in config.read_text(encoding="utf-8")


def test_an_absent_element_is_an_absence_not_off(config: Path) -> None:
    without = config.read_text(encoding="utf-8").replace(
        "  <Setting name='EnableAutomaticApplyOPS' value='1' />\n", ""
    )
    config.write_text(without, encoding="utf-8", newline="")
    assert nvapp_config.read_setting(nvapp_config.AUTO_APPLY_SETTING, config) is None
    ok, error = nvapp_config.write_setting(nvapp_config.AUTO_APPLY_SETTING, "0", config)
    assert ok is False
    assert error is not None and "no EnableAutomaticApplyOPS switch" in error
    assert config.read_text(encoding="utf-8") == without


def test_a_missing_file_changes_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "config.xml"
    ok, error = nvapp_config.write_setting(nvapp_config.AUTO_APPLY_SETTING, "0", missing)
    assert ok is False
    assert error is not None and "was not found" in error
    assert not missing.exists()


def test_a_non_numeric_value_is_refused(config: Path) -> None:
    ok, error = nvapp_config.write_setting(nvapp_config.AUTO_APPLY_SETTING, "off", config)
    assert ok is False
    assert error is not None and "not a number" in error
    assert config.read_text(encoding="utf-8") == SAMPLE


def test_the_detector_maps_zero_to_disabled(config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nvapp_config, "config_path", lambda: config)
    assert nvapp_config.auto_apply_state() == "enabled"
    nvapp_config.write_setting(nvapp_config.AUTO_APPLY_SETTING, "0", config)
    assert nvapp_config.auto_apply_state() == "disabled"


def test_the_detector_answers_not_available_without_the_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(nvapp_config, "config_path", lambda: tmp_path / "absent.xml")
    assert nvapp_config.auto_apply_state() in (NOT_AVAILABLE, "disabled")


def test_the_action_refuses_a_reading(config: Path) -> None:
    ok, error = nvapp_config.nvapp_auto_apply_write({"value": "not_available", "path": str(config)})
    assert ok is False
    assert error is not None and "reading" in error


def test_the_action_writes_the_off_state(config: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nvapp_config, "config_path", lambda: config)
    ok, message = nvapp_config.nvapp_auto_apply_write({"value": "disabled"})
    assert ok is True
    assert message is not None and "no longer applies" in message
    assert nvapp_config.read_setting(nvapp_config.AUTO_APPLY_SETTING, config) == "0"

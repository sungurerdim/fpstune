"""Battle.net.config is the client's own file; a toggle must change one value.

The PowerShell writer this replaces re-serialised the whole document through
ConvertTo-Json and wrote it back with a byte-order mark, and the keys it wrote
(Application.BrowserHardwareAcceleration, Client.P2PEnabled) are not ones the
client reads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpstune.settings.applicability import NOT_INSTALLED
from fpstune.settings.definitions.launchers import BNET_DOWNLOAD_LIMIT, BNET_HARDWARE_ACCEL
from fpstune.settings.executors import bnet_config
from fpstune.settings.executors.python_actions import PYTHON_ACTIONS, PYTHON_DETECTORS

CLIENT_FILE = {
    "Client": {
        "AutoLogin": "true",
        "HardwareAcceleration": "true",
        "Install": {"DownloadLimitNextPatchInBps": "5242880"},
    },
    "Games": {"s2": {"AdditionalLaunchArguments": "-Displaymode 1 <ü>"}},
}


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "Battle.net.config"
    path.write_text(json.dumps(CLIENT_FILE, indent=4), encoding="utf-8")
    return path


def test_reads_nested_values_as_text(config: Path) -> None:
    assert bnet_config.read_value("Client.HardwareAcceleration", config) == "true"
    assert bnet_config.read_value("Client.Install.DownloadLimitNextPatchInBps", config) == "5242880"


def test_an_absent_key_is_the_clients_default_not_an_error(config: Path) -> None:
    assert bnet_config.read_value("Client.Streaming.StreamingEnabled", config) == bnet_config.ABSENT


def test_no_file_is_not_installed(tmp_path: Path) -> None:
    assert bnet_config.read_value("Client.HardwareAcceleration", tmp_path / "x") == NOT_INSTALLED


def test_a_write_changes_one_value_and_nothing_else(config: Path) -> None:
    ok, message = bnet_config.write_value("Client.HardwareAcceleration", "false", config)
    assert ok, message
    raw = config.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "a BOM the client did not write"
    after = json.loads(raw.decode("utf-8"))
    expected = json.loads(json.dumps(CLIENT_FILE))
    expected["Client"]["HardwareAcceleration"] = "false"
    assert after == expected


def test_a_missing_section_is_created(config: Path) -> None:
    config.write_text(json.dumps({"Client": {}}), encoding="utf-8")
    ok, _ = bnet_config.write_value("Client.Install.DownloadLimitNextPatchInBps", "0", config)
    assert ok
    assert bnet_config.read_value("Client.Install.DownloadLimitNextPatchInBps", config) == "0"


def test_an_unparseable_file_is_left_untouched(config: Path) -> None:
    config.write_text("{ not json", encoding="utf-8")
    ok, message = bnet_config.write_value("Client.HardwareAcceleration", "false", config)
    assert not ok and message is not None
    assert config.read_text(encoding="utf-8") == "{ not json"


def test_a_reading_with_no_raw_form_is_refused() -> None:
    # The guard's "limited" reading reaches the action unmapped.
    ok, message = bnet_config.bnet_config_write(
        {"key": "Client.Install.DownloadLimitNextPatchInBps", "allowed": "0", "value": "limited"}
    )
    assert not ok and message is not None


def test_the_definitions_use_the_keys_the_client_reads() -> None:
    assert BNET_HARDWARE_ACCEL.detect_args["key"] == "Client.HardwareAcceleration"
    assert BNET_DOWNLOAD_LIMIT.detect_args["key"] == "Client.Install.DownloadLimitNextPatchInBps"
    for setting in (BNET_HARDWARE_ACCEL, BNET_DOWNLOAD_LIMIT):
        assert setting.detect_command in PYTHON_DETECTORS
        assert setting.apply_command in PYTHON_ACTIONS


def test_the_download_cap_is_a_guard_on_no_cap() -> None:
    assert BNET_DOWNLOAD_LIMIT.default_value == BNET_DOWNLOAD_LIMIT.recommended_value == "unlimited"
    assert BNET_DOWNLOAD_LIMIT.apply_value_map == {"unlimited": "0"}

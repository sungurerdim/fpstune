"""A TCP snapshot that could not be read answers "could not read", never "not_available".

Issue #104 class B, the netsh executor's share. ``_fetch_tcp_snapshot`` returned
``{}`` for every failure (PowerShell failed, malformed JSON, no object), and
``get_tcp_property`` answered ``not_available`` for a property missing from that
map -- an ABSENT_READINGS spelling, so a failed ``Get-NetTCPSetting`` made
``network:tcp_timestamps`` and ``network:tcp_ecn`` read as "feature not on this
machine". Same convention as ps_batch (commit 620f6b9): ``None`` is the failed
read, an empty map is a real answer, and the executor turns ``None`` into a
detection error (value None + reason).
"""

from __future__ import annotations

import json
import sys
from contextlib import AbstractContextManager
from unittest.mock import patch

import pytest

from fpstune.settings.applicability import is_absent_reading
from fpstune.settings.executors import netsh as netsh_mod
from fpstune.settings.executors.netsh import (
    TCP_PROPERTY_MISSING,
    NetshExecutor,
    _fetch_tcp_snapshot,
    get_tcp_property,
)
from fpstune.settings.executors.powershell import PowerShellExecutor
from fpstune.settings.executors.ps_batch import init_scan_cache, reset_scan_cache
from fpstune.settings.registry import SettingsRegistry

pytestmark = pytest.mark.usefixtures("_on_windows")


@pytest.fixture
def _on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    # The fetcher and the executor stand down off Windows; the PowerShell they
    # would run is scripted here, so the paths run on any host.
    monkeypatch.setattr(sys, "platform", "win32")


def _run(output: str, ok: bool = True) -> AbstractContextManager[object]:
    return patch.object(netsh_mod, "run_powershell", lambda *_a, **_k: (ok, output))


class TestTheSnapshotSaysWhenItFailed:
    @pytest.mark.parametrize(
        "output",
        ["", "   ", "{ not json", "[1, 2]", '"text"'],
        ids=["empty", "blank", "malformed-json", "list", "string"],
    )
    def test_an_unusable_answer_is_an_unread_snapshot(self, output: str) -> None:
        with _run(output):
            assert _fetch_tcp_snapshot() is None

    def test_a_powershell_failure_is_an_unread_snapshot(self) -> None:
        with _run("Get-NetTCPSetting : access denied", ok=False):
            assert _fetch_tcp_snapshot() is None

    def test_a_readable_object_with_none_of_the_properties_is_an_empty_map(self) -> None:
        blank = json.dumps({"Timestamps": "", "EcnCapability": ""})
        with _run(blank):
            assert _fetch_tcp_snapshot() == {}

    def test_the_query_ends_on_error_instead_of_answering_nothing(self) -> None:
        seen: list[str] = []

        def capture(command: str, **_k: object) -> tuple[bool, str]:
            seen.append(command)
            return True, "{}"

        with patch.object(netsh_mod, "run_powershell", capture):
            _fetch_tcp_snapshot()
        assert "-ErrorAction Stop" in seen[0]
        assert "SilentlyContinue" not in seen[0]

    def test_a_failed_read_is_not_cached_as_an_empty_answer(self) -> None:
        cache, token = init_scan_cache()
        try:
            with _run("", ok=False):
                assert get_tcp_property("Timestamps") is None
        finally:
            reset_scan_cache(token)
        assert cache["tcp_settings"] is None


class TestAPropertyIsAbsentOnlyWhenTheObjectWasRead:
    def test_a_failed_read_is_not_not_available(self) -> None:
        with _run("", ok=False):
            value = get_tcp_property("Timestamps")
        assert value is None
        assert not is_absent_reading(value)

    def test_a_read_object_without_the_property_still_says_not_available(self) -> None:
        with _run(json.dumps({"EcnCapability": "disabled"})):
            assert get_tcp_property("Timestamps") == TCP_PROPERTY_MISSING

    def test_a_read_property_is_returned(self) -> None:
        with _run(json.dumps({"Timestamps": "Disabled"})):
            assert get_tcp_property("timestamps") == "disabled"


class TestExecutors:
    @pytest.mark.parametrize("setting_id", ["network:tcp_timestamps", "network:tcp_ecn"])
    def test_the_powershell_executor_reports_a_detection_error(self, setting_id: str) -> None:
        setting = SettingsRegistry().get(setting_id)
        assert setting is not None
        assert setting.detect_args.get("batch_tcp")
        with _run("", ok=False):
            value, error = PowerShellExecutor().detect(setting)
        assert value is None
        assert error
        assert not is_absent_reading(value)

    @pytest.mark.parametrize("setting_id", ["network:tcp_timestamps", "network:tcp_ecn"])
    def test_the_powershell_executor_returns_the_state_when_it_was_read(
        self, setting_id: str
    ) -> None:
        setting = SettingsRegistry().get(setting_id)
        assert setting is not None
        prop = str(setting.detect_args["batch_tcp"])
        with _run(json.dumps({prop: "enabled"})):
            value, error = PowerShellExecutor().detect(setting)
        assert error is None
        assert value is not None
        assert not is_absent_reading(value)

    def test_the_netsh_path_falls_through_to_netsh_when_the_snapshot_is_unread(self) -> None:
        # An unread snapshot has no answer to give; netsh's own output is an
        # independent read of the same state, and the executor must ask it.
        args = {"parse_key": "receive window auto-tuning level"}
        with _run("", ok=False):
            assert NetshExecutor()._detect_tcp_via_powershell(args) is None
        with _run(json.dumps({"AutoTuningLevelLocal": "normal"})):
            assert NetshExecutor()._detect_tcp_via_powershell(args) == "normal"


@pytest.mark.skipif(
    __import__("platform").system() != "Windows",
    reason="runs the shipped PowerShell text; there is none elsewhere",
)
class TestTheSingleSettingFallbackScript:
    """The fallback command of tcp_timestamps / tcp_ecn, run for real with the cmdlets stubbed.

    Its catch used to answer ``not_available`` for any failure, on the guess that
    the NetTCPIP module "may be unavailable". Only the cmdlet not existing is
    absence, and PowerShell is asked whether it exists.
    """

    _FAILS = "function Get-NetTCPSetting { [CmdletBinding()] param($SettingName) throw 'boom' }; "
    _NO_SUCH_COMMAND = "function Get-Command { [CmdletBinding()] param($Name) }; "

    @pytest.fixture
    def command(self) -> str:
        setting = SettingsRegistry().get("network:tcp_timestamps")
        assert setting is not None
        return setting.detect_command

    def test_a_failed_read_ends_the_script_and_is_not_an_absent_reading(self, command: str) -> None:
        from fpstune.utils.powershell import run_powershell

        ok, output = run_powershell(self._FAILS + command)
        assert not ok, output
        assert "not_available" not in output

    def test_a_missing_cmdlet_is_the_absent_reading(self, command: str) -> None:
        from fpstune.utils.powershell import run_powershell

        ok, output = run_powershell(self._FAILS + self._NO_SUCH_COMMAND + command)
        assert ok, output
        assert output.strip().splitlines()[-1] == "not_available"

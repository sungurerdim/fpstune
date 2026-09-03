"""The one PowerShell runner sends every `HKCU:` path to the console user's hive.

Twenty-odd shipped scripts — Steam's launch options, Game DVR, the accessibility
keys, WSL's distribution list, Docker's per-user uninstall entry — write or read
``HKCU:``. Rewriting the drive in ``run_powershell`` rather than in each script is
what keeps them from disagreeing with the winreg executor about whose hive that
is; a script that bypassed the runner would be the defect these tests would miss,
which is why ``TestHkcuGoesThroughTheRunner`` in the quality gates fails any
module that spawns powershell.exe itself and names ``HKCU:``.
"""

from __future__ import annotations

import sys

import pytest

from fpstune.utils import powershell
from fpstune.utils.winapi import session
from fpstune.utils.winapi.session import UserHive

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the runner is Windows only")

PLAYER = "S-1-5-21-1000-2000-3000-1001"
STEAM = "(Get-ItemProperty -Path 'HKCU:\\Software\\Valve\\Steam' -Name 'StartupMode').StartupMode"


class _FakeProcess:
    """Stands in for the PowerShell the runner starts, answering "0"."""

    def __init__(self, argv: list[str]) -> None:
        self.args = argv
        self.returncode = 0

    # Named `timeout` because the runner passes it by keyword; nothing here waits.
    def communicate(self, timeout: float | None = None) -> tuple[str, str]:  # noqa: ARG002
        return "0\n", ""

    def kill(self) -> None:  # pragma: no cover - nothing here ever times out
        pass


def _capture_argv(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    seen: list[list[str]] = []

    def fake_popen(argv: list[str], **_kwargs: object) -> _FakeProcess:
        seen.append(argv)
        return _FakeProcess(argv)

    # The runner drives the process itself rather than through `subprocess.run`,
    # because that call reaps a timed-out child with a wait it cannot bound —
    # see utils.powershell._reap_in_background.
    monkeypatch.setattr(powershell.subprocess, "Popen", fake_popen)
    return seen


def test_another_console_user_is_addressed_through_hkey_users(monkeypatch) -> None:
    monkeypatch.setattr(session, "user_hive", lambda: UserHive("HKU", f"{PLAYER}\\"))
    seen = _capture_argv(monkeypatch)

    ok, out = powershell.run_powershell(STEAM)

    assert (ok, out) == (True, "0")
    command = seen[0][-1]
    assert f"Registry::HKEY_USERS\\{PLAYER}\\Software\\Valve\\Steam" in command
    assert "HKCU:" not in command


def test_the_players_own_session_runs_the_script_as_written(monkeypatch) -> None:
    monkeypatch.setattr(session, "user_hive", lambda: UserHive("HKCU", ""))
    seen = _capture_argv(monkeypatch)

    powershell.run_powershell(STEAM)

    assert seen[0][-1].endswith(STEAM)

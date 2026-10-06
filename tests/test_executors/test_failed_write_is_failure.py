r"""A write that failed is a failure with a reason, never "ok".

Seven fixes shipped one shape at a time (``60f67cf`` MSI mode printed ``ok`` over a
refused registry write, ``73706c2`` a refused write told an administrator to run as
one, ...). Each was found by a person on a real machine, after the apply reported
success. This file is the class-wide gate: it does not test one executor, it asks
every executor, and every shipped script, the same question.

Three layers, because the failure hides in three places:

1. **The seam of each executor type.** The lowest call each one makes (``winreg``,
   the PowerShell runner, ``process_watch.run``, the NVIDIA driver, ``os.replace``)
   is forced to fail in the ways Windows fails, and ``apply`` must answer
   ``(False, <readable reason>)``. Every case has a control run where the seam
   succeeds, so a test that is red for the wrong reason cannot pass as a guard.
2. **Every registered setting** with every seam failing at once: nothing may answer
   success, because nothing could have written.
3. **Every shipped PowerShell script.** A script that exits 0 and prints ``ok`` hides
   a failed write from layers 1 and 2 — the runner only sees the exit code. A write
   cmdlet must stop on error, or be best-effort *by name* in ``BEST_EFFORT``.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from fpstune.core.nvapi import NvapiError, NvapiUnavailable
from fpstune.settings import display_mode
from fpstune.settings.base import DetectType, SettingExecutor
from fpstune.settings.executors import (
    CommandExecutor,
    bnet_config,
    game_config_writer,
    game_ini,
    game_processes,
    msi_mode,
    mw3_profile,
    mw4_config,
    nvprofile,
    python_actions,
    steam_config,
)
from fpstune.settings.executors import powercfg as powercfg_module
from fpstune.settings.executors.powercfg import PowerCfgExecutor
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.settings.executors.python_actions import PYTHON_ACTIONS
from fpstune.settings.registry import SettingsRegistry
from fpstune.utils import process_watch
from fpstune.utils.process_watch import RunResult
from fpstune.utils.winapi.memory import PurgeOutcome

_SETTINGS_DIR = Path(__file__).resolve().parents[2] / "src" / "fpstune" / "settings"

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="Every executor below answers 'not available' off Windows"
)


def _denied(*_args: Any, **_kwargs: Any) -> Any:
    raise PermissionError(5, "Access is denied")


def _readable(error: str | None) -> bool:
    """A reason a person can act on: more than a bare ``prefix:`` or an unfilled field."""
    text = (error or "").strip()
    # "Windows error None": a field the message was built from had nothing in it.
    return bool(text) and not text.endswith(":") and " None" not in text


# ---------------------------------------------------------------------------
# Layer 1: the lowest seam of every executor type
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def registered() -> list[SettingExecutor]:
    return list(SettingsRegistry(discover_dynamic=False)._settings.values())


@pytest.fixture(autouse=True)
def _no_running_game(monkeypatch: pytest.MonkeyPatch) -> None:
    """A game on the runner's desktop would refuse every config write before the seam."""
    monkeypatch.setattr(game_processes, "refuse_if_game_is_running", lambda _setting_id: None)


def _by_id(registered: list[SettingExecutor], setting_id: str) -> SettingExecutor:
    return next(s for s in registered if s.id == setting_id)


def _by_apply_type(registered: list[SettingExecutor], apply_type: DetectType) -> SettingExecutor:
    return next(s for s in registered if s.apply_type == apply_type)


def _by_action(registered: list[SettingExecutor], action: str) -> SettingExecutor:
    return next(s for s in registered if s.apply_command.strip() == action)


def _run_result(
    returncode: int | None, stdout: str = "", stderr: str = "", **kwargs: Any
) -> RunResult:
    return RunResult(returncode=returncode, stdout=stdout, stderr=stderr, **kwargs)


def _fake_runner(result: RunResult | BaseException) -> Callable[..., RunResult]:
    """A ``run_watched`` that answers ``result``; streams its stdout when asked to."""

    def run_watched(
        _argv: list[str], _policy: Any, *, on_text: Any = None, **_kw: Any
    ) -> RunResult:
        if isinstance(result, BaseException):
            raise result
        if on_text is not None and result.stdout:
            on_text(result.stdout + "\n")
        return result

    return run_watched


@dataclass(frozen=True)
class Case:
    """One executor type: a setting to apply, and the ways its seam can go wrong.

    ``refusals`` install a failure of the seam; ``control`` installs a success of it.
    Every refusal must answer failure with a reason, and the control must answer
    success — otherwise a refusal that merely broke the setting up would pass.
    """

    pick: Callable[[list[SettingExecutor]], SettingExecutor]
    value: Any
    refusals: dict[str, Callable[[ExitStack, Path], None]]
    control: Callable[[ExitStack, Path], None]
    arguments: dict[str, Any] | None = None
    streamed: bool = False


def _winreg_write(stack: ExitStack, *, set_value: Any = None, create: Any = None) -> None:
    key = MagicMock()
    stack.enter_context(
        patch(
            "winreg.CreateKeyEx", side_effect=create, return_value=key if create is None else None
        )
    )
    stack.enter_context(patch("winreg.SetValueEx", side_effect=set_value))


def _winreg_delete(stack: ExitStack, *, open_key: Any = None, delete: Any = None) -> None:
    stack.enter_context(patch("winreg.OpenKey", side_effect=open_key, return_value=MagicMock()))
    stack.enter_context(patch("winreg.DeleteValue", side_effect=delete))


def _powershell(stack: ExitStack, outcome: RunResult | BaseException) -> None:
    stack.enter_context(patch("fpstune.utils.powershell.run_watched", _fake_runner(outcome)))


def _process(stack: ExitStack, outcome: subprocess.CompletedProcess[str] | BaseException) -> None:
    def run(*_a: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    stack.enter_context(patch.object(process_watch, "run", run))


def _completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _powercfg(stack: ExitStack, *, schemes: list[str], answer: tuple[bool, str]) -> None:
    stack.enter_context(patch.object(PowerCfgExecutor, "_target_schemes", lambda _s: schemes))
    stack.enter_context(patch.object(powercfg_module, "windows_default_index", lambda *_a: None))
    stack.enter_context(patch.object(PowerCfgExecutor, "_run", lambda _s, _args: answer))


def _nvidia(stack: ExitStack, *, writes: Any) -> None:
    stack.enter_context(patch.object(nvprofile, "missing_driver_ids", lambda _drs: frozenset()))
    stack.enter_context(patch("fpstune.core.nvapi.write_driver_settings", writes))


def _raises(exc: BaseException) -> Callable[..., Any]:
    def fail(*_a: Any, **_kw: Any) -> Any:
        raise exc

    return fail


def _config_file(tmp: Path, name: str, text: str) -> Path:
    path = tmp / name
    path.write_bytes(text.encode("utf-8"))
    return path


def _mw4(stack: ExitStack, tmp: Path, *, replace: Any = None, lock: Any = None) -> None:
    path = _config_file(tmp, "s.1.1.bt.cod26.txt", "TextureQuality@0;1;2 = 3 // 0 to 3\n")
    stack.enter_context(patch.object(mw4_config, "_path_for", lambda _source: path))
    stack.enter_context(patch.object(mw4_config, "get_mw4_metadata", lambda _k, _s: {}))
    stack.enter_context(patch.object(mw4_config, "refresh_cached_config", lambda *_a: None))
    _file_seams(stack, replace=replace, lock=lock)


def _mw3(stack: ExitStack, tmp: Path, *, replace: Any = None, lock: Any = None) -> None:
    path = _config_file(
        tmp, "gamerprofile.0.BASE.cst", "Sprint Assist Delay KBM@0 = 400 // 0 to 9\n"
    )
    stack.enter_context(patch.object(mw3_profile, "mw3_profile_path", lambda: path))
    stack.enter_context(patch.object(mw3_profile, "get_mw3_profile_metadata", lambda _k: {}))
    stack.enter_context(patch.object(mw3_profile, "refresh_cached_config", lambda *_a: None))
    _file_seams(stack, replace=replace, lock=lock)


def _file_seams(stack: ExitStack, *, replace: Any, lock: Any) -> None:
    """The two calls every config write ends in: the lock, and the atomic replace."""
    stack.enter_context(patch.object(time, "sleep", lambda _s: None))
    if replace is not None:
        stack.enter_context(patch.object(os, "replace", replace))
    if lock is not None:
        stack.enter_context(patch.object(game_config_writer, "_take_system_mutex", lock))
    else:
        stack.enter_context(patch.object(game_config_writer, "_take_system_mutex", lambda _n: None))


def _bnet(stack: ExitStack, tmp: Path, *, replace: Any = None, text: str | None = None) -> None:
    path = _config_file(tmp, "Battle.net.config", text or '{"Client": {"Flag": "true"}}')
    stack.enter_context(patch.object(bnet_config, "config_path", lambda: path))
    if replace is not None:
        stack.enter_context(patch.object(os, "replace", replace))


def _steam(stack: ExitStack, tmp: Path, *, replace: Any = None, present: bool = True) -> None:
    (tmp / "config").mkdir()
    if present:
        _config_file(
            tmp / "config", "config.vdf", '"InstallConfigStore"\n{\n\t"Steam"\n\t{\n\t}\n}\n'
        )
    stack.enter_context(patch.object(steam_config, "steam_root", lambda: tmp))
    if replace is not None:
        stack.enter_context(patch.object(os, "replace", replace))


def _ini(stack: ExitStack, tmp: Path, *, replace: Any = None, lock: Any = None) -> None:
    path = _config_file(tmp, "GameUserSettings.ini", "FrameRateLimit=144.000000\n")
    spec = game_ini.GameConfigFile("fortnite", lambda: path, "ini")
    stack.enter_context(patch.dict(game_ini.FILES, {"fortnite": spec}))
    _file_seams(stack, replace=replace, lock=lock)


def _msi(stack: ExitStack, *, write: Any = None) -> None:
    stack.enter_context(patch.object(msi_mode, "resolve_instance_id", lambda _a: r"PCI\VEN_1\1"))
    stack.enter_context(
        patch.object(
            msi_mode,
            "interrupt_defaults",
            lambda _i: SimpleNamespace(msi_supported=0, message_number_limit=None),
        )
    )
    stack.enter_context(patch.object(msi_mode, "_delete_value", lambda *_a: None))
    stack.enter_context(
        patch.object(msi_mode, "_write_dword", write if write is not None else lambda *_a: None)
    )


def _user_input(stack: ExitStack, *, write: Any = None, live: bool = True) -> None:
    stack.enter_context(
        patch.object(python_actions, "_write_user_strings", write or (lambda *_a: None))
    )
    spi = "fpstune.utils.winapi.spi"
    for name in ("set_mouse", "set_access_flags", "set_animations"):
        stack.enter_context(patch(f"{spi}.{name}", lambda *_a, _live=live: _live))


def _purge(stack: ExitStack, *, status: int) -> None:
    outcome = PurgeOutcome(status=status, before=None, after=None)
    stack.enter_context(patch.object(python_actions, "purge_standby_list", lambda: outcome))


def _display(stack: ExitStack, *, kind: str) -> None:
    monitor = SimpleNamespace()
    stack.enter_context(patch.object(display_mode, "find_monitor", lambda _m: monitor))
    stack.enter_context(patch.object(display_mode, "is_readable", lambda _m: True))
    outcome = display_mode.WriteOutcome(kind, "" if kind == "written" else "the driver said no")
    stack.enter_context(patch.object(display_mode, "write_native", lambda _m, _s=None: outcome))


_ACCESS_DENIED = PermissionError(5, "Access is denied")
_DISK_FULL = OSError(112, "There is not enough space on the disk")

CASES: dict[str, Case] = {
    # -- the five executor types the dispatcher knows ------------------------------
    "registry write": Case(
        pick=lambda r: _by_id(r, "system:widgets"),
        value="disabled",
        refusals={
            "key refused": lambda s, _t: _winreg_write(s, create=_ACCESS_DENIED),
            "value refused": lambda s, _t: _winreg_write(s, set_value=_DISK_FULL),
            "error with no text": lambda s, _t: _winreg_write(s, set_value=OSError()),
            "not an OSError": lambda s, _t: _winreg_write(s, set_value=ValueError()),
        },
        control=lambda s, _t: _winreg_write(s),
    ),
    "registry delete": Case(
        pick=lambda r: _by_id(r, "system:widgets"),
        value="enabled",
        refusals={
            "key refused": lambda s, _t: _winreg_delete(s, open_key=_ACCESS_DENIED),
            "value refused": lambda s, _t: _winreg_delete(s, delete=_DISK_FULL),
            "error with no text": lambda s, _t: _winreg_delete(s, delete=OSError()),
        },
        control=lambda s, _t: _winreg_delete(s),
    ),
    "powershell": Case(
        pick=lambda r: _by_id(r, "game:game_bar"),
        value="disabled",
        refusals={
            "non-zero exit with text": lambda s, _t: _powershell(
                s, _run_result(1, stderr="Set-ItemProperty : Access is denied")
            ),
            "non-zero exit, nothing said": lambda s, _t: _powershell(s, _run_result(1)),
            "script's own error line": lambda s, _t: _powershell(
                s, _run_result(0, stdout="working\nerror: could not write 1 endpoint")
            ),
            "stalled": lambda s, _t: _powershell(
                s, _run_result(None, timed_out=True, reason="no progress for 30 s")
            ),
            "will not start": lambda s, _t: _powershell(s, FileNotFoundError()),
        },
        control=lambda s, _t: _powershell(s, _run_result(0, stdout="ok")),
    ),
    "powershell, streamed": Case(
        pick=lambda r: _by_id(r, "game:game_bar"),
        value="disabled",
        refusals={
            "non-zero exit with text": lambda s, _t: _powershell(
                s, _run_result(1, stdout="Set-ItemProperty : Access is denied")
            ),
            "non-zero exit, nothing said": lambda s, _t: _powershell(s, _run_result(1)),
            "script's own error line": lambda s, _t: _powershell(
                s, _run_result(0, stdout="error: could not write 1 endpoint")
            ),
        },
        control=lambda s, _t: _powershell(s, _run_result(0, stdout="ok")),
        streamed=True,
    ),
    "netsh": Case(
        pick=lambda r: _by_apply_type(r, DetectType.NETSH),
        value=None,
        refusals={
            "non-zero exit with text": lambda s, _t: _process(
                s, _completed(1, stdout="The requested operation requires elevation.")
            ),
            "non-zero exit, nothing said": lambda s, _t: _process(s, _completed(1)),
            "stalled": lambda s, _t: _process(s, subprocess.TimeoutExpired(["netsh"], 30)),
            "cannot be started": lambda s, _t: _process(s, FileNotFoundError("netsh.exe")),
        },
        control=lambda s, _t: _process(s, _completed(0, stdout="Ok.")),
    ),
    "powercfg": Case(
        pick=lambda r: _by_apply_type(r, DetectType.POWERCFG),
        value=None,
        refusals={
            "the active plan refuses": lambda s, _t: _powercfg(
                s, schemes=["scheme-a"], answer=(False, "Access is denied.")
            ),
            "the active plan refuses without a word": lambda s, _t: _powercfg(
                s, schemes=["scheme-a"], answer=(False, "")
            ),
            "no plan can be listed": lambda s, _t: _powercfg(s, schemes=[], answer=(True, "")),
        },
        control=lambda s, _t: _powercfg(s, schemes=["scheme-a"], answer=(True, "")),
    ),
    "nvprofile": Case(
        pick=lambda r: _by_apply_type(r, DetectType.NVPROFILE),
        value=None,
        refusals={
            "driver rejects the write": lambda s, _t: _nvidia(
                s, writes=_raises(NvapiError("NvAPI_DRS_SetSetting", -5))
            ),
            "no driver interface": lambda s, _t: _nvidia(
                s, writes=_raises(NvapiUnavailable("nvapi64.dll is not present"))
            ),
            "settings store unwritable": lambda s, _t: _nvidia(s, writes=_raises(_ACCESS_DENIED)),
        },
        control=lambda s, _t: _nvidia(s, writes=lambda _changes: None),
    ),
    # -- game config files, written in Python rather than through a script ---------
    "mw4 config line": Case(
        pick=lambda r: _by_id(r, "game_config:mw4:texture_quality"),
        value="1",
        refusals={
            "file held open": lambda s, t: _mw4(s, t, replace=_raises(_ACCESS_DENIED)),
            "disk refuses": lambda s, t: _mw4(s, t, replace=_raises(_DISK_FULL)),
            "another writer keeps the lock": lambda s, t: _mw4(
                s, t, lock=_raises(TimeoutError("another writer held the file for over 15s"))
            ),
        },
        control=lambda s, t: _mw4(s, t),
    ),
    "mw3 gamerprofile line": Case(
        pick=lambda r: _by_id(r, "game_config:mw3:sprint_assist_delay_kbm"),
        value="0",
        refusals={
            "file held open": lambda s, t: _mw3(s, t, replace=_raises(_ACCESS_DENIED)),
            "disk refuses": lambda s, t: _mw3(s, t, replace=_raises(_DISK_FULL)),
            "another writer keeps the lock": lambda s, t: _mw3(
                s, t, lock=_raises(TimeoutError("another writer held the file for over 15s"))
            ),
        },
        control=lambda s, t: _mw3(s, t),
    ),
    "bnet_config_write": Case(
        pick=lambda r: _by_action(r, "bnet_config_write"),
        value="false",
        arguments={"key": "Client.Flag", "allowed": "true,false"},
        refusals={
            "file held open": lambda s, t: _bnet(s, t, replace=_raises(_ACCESS_DENIED)),
            "file is not JSON": lambda s, t: _bnet(s, t, text="{not json"),
        },
        control=lambda s, t: _bnet(s, t),
    ),
    "steam_vdf_write": Case(
        pick=lambda r: _by_action(r, "steam_vdf_write"),
        value="1",
        arguments={"scope": "config", "key": "BrowserFlags"},
        refusals={
            "file held open": lambda s, t: _steam(s, t, replace=_raises(_ACCESS_DENIED)),
            "file is gone": lambda s, t: _steam(s, t, present=False),
        },
        control=lambda s, t: _steam(s, t),
    ),
    "game_ini_write": Case(
        pick=lambda r: _by_action(r, "game_ini_write"),
        value="60",
        arguments={"game": "fortnite", "key": "FrameRateLimit"},
        refusals={
            "file held open": lambda s, t: _ini(s, t, replace=_raises(_ACCESS_DENIED)),
            "another writer keeps the lock": lambda s, t: _ini(
                s, t, lock=_raises(TimeoutError("another writer held the file for over 15s"))
            ),
        },
        control=lambda s, t: _ini(s, t),
    ),
    # -- registry and system calls made from Python -------------------------------
    "msi_mode_write": Case(
        pick=lambda r: _by_action(r, "msi_mode_write"),
        value="enabled",
        arguments={"device": "gpu"},
        refusals={
            "key refused": lambda s, _t: _msi(s, write=_raises(_ACCESS_DENIED)),
            "disk refuses": lambda s, _t: _msi(s, write=_raises(OSError(112, "disk full"))),
            "error from no Windows call": lambda s, _t: _msi(s, write=_raises(OSError("odd"))),
            "error with no text": lambda s, _t: _msi(s, write=_raises(OSError())),
        },
        control=lambda s, _t: _msi(s),
    ),
    "mouse_acceleration_toggle": Case(
        pick=lambda r: _by_action(r, "mouse_acceleration_toggle"),
        value="disable",
        refusals={
            "profile refuses": lambda s, _t: _user_input(s, write=_raises(_ACCESS_DENIED)),
            "error with no text": lambda s, _t: _user_input(s, write=_raises(OSError())),
        },
        control=lambda s, _t: _user_input(s),
    ),
    "accessibility_popups_toggle": Case(
        pick=lambda r: _by_action(r, "accessibility_popups_toggle"),
        value="disable",
        refusals={"profile refuses": lambda s, _t: _user_input(s, write=_raises(_ACCESS_DENIED))},
        control=lambda s, _t: _user_input(s),
    ),
    "animations_toggle": Case(
        pick=lambda r: _by_action(r, "animations_toggle"),
        value="disable",
        refusals={
            "profile refuses": lambda s, _t: _user_input(s, write=_raises(_ACCESS_DENIED)),
            "live change refused": lambda s, _t: _user_input(s, live=False),
        },
        control=lambda s, _t: _user_input(s),
    ),
    "purge_standby": Case(
        pick=lambda r: _by_action(r, "purge_standby"),
        value=True,
        refusals={"kernel refuses": lambda s, _t: _purge(s, status=0xC0000061)},
        control=lambda s, _t: _purge(s, status=0),
    ),
    "display_mode_native": Case(
        # One row per monitor, found at run time, so none is registered statically.
        pick=lambda r: replace(
            _by_id(r, "game:game_bar"), id="display:mode:test", apply_command="display_mode_native"
        ),
        value=display_mode.NATIVE,
        arguments={"monitor": "m", "setting_id": "x"},
        refusals={
            "driver rejects the mode": lambda s, _t: _display(s, kind="testfail"),
            "change fails": lambda s, _t: _display(s, kind="error"),
        },
        control=lambda s, _t: _display(s, kind="written"),
    ),
}


def _apply(case: Case, registered: list[SettingExecutor]) -> tuple[bool, str | None]:
    setting = case.pick(registered)
    if case.arguments is not None:
        setting = replace(setting, apply_args=dict(case.arguments))
    value = setting.recommended_value if case.value is None else case.value
    on_line = (lambda _text, _redraw: None) if case.streamed else None
    return CommandExecutor.apply(setting, value, on_line)


def _refusal_params() -> list[Any]:
    params = []
    for name, case in CASES.items():
        for mode in case.refusals:
            params.append(pytest.param(name, mode, id=f"{name} | {mode}"))
    return params


@windows_only
class TestEveryExecutorAnswersFailureWhenItsWriteFails:
    @pytest.mark.parametrize(("name", "mode"), _refusal_params())
    def test_a_refused_write_is_a_failure_with_a_reason(
        self, name: str, mode: str, registered: list[SettingExecutor], tmp_path: Path
    ) -> None:
        case = CASES[name]
        with ExitStack() as stack:
            case.refusals[mode](stack, tmp_path)
            ok, error = _apply(case, registered)

        assert ok is False, f"{name} reported success after: {mode}"
        assert _readable(error), f"{name} gave no usable reason after: {mode} (got {error!r})"

    @pytest.mark.parametrize("name", list(CASES))
    def test_the_same_setting_succeeds_when_the_seam_does(
        self, name: str, registered: list[SettingExecutor], tmp_path: Path
    ) -> None:
        """The control: without it a refusal could be red for a reason of its own."""
        case = CASES[name]
        with ExitStack() as stack:
            case.control(stack, tmp_path)
            ok, error = _apply(case, registered)

        assert ok is True, f"{name} failed with nothing wrong with its seam: {error!r}"

    def test_every_python_action_has_a_case(self) -> None:
        missing = sorted(set(PYTHON_ACTIONS) - set(CASES))
        assert not missing, (
            "a Python action with no failure case: add it to CASES so its refusal is proven "
            f"to come back as (False, reason): {missing}"
        )

    def test_every_executor_type_has_a_case(self) -> None:
        shipped = {
            executor_type
            for executor_type in ("registry", "powershell", "netsh", "powercfg", "nvprofile")
            if CommandExecutor._get_executor(executor_type) is not None
        }
        assert shipped == {"registry", "powershell", "netsh", "powercfg", "nvprofile"}
        covered = {CASES[n].pick(_registry_cache()).apply_type.value for n in CASES}
        assert shipped <= covered, (
            f"executor types with no failure case: {sorted(shipped - covered)}"
        )

    def test_a_write_to_an_inactive_plan_is_reported_not_hidden(
        self, registered: list[SettingExecutor]
    ) -> None:
        """The one deliberate partial success: the active plan took it, another did not."""
        setting = _by_apply_type(registered, DetectType.POWERCFG)
        answers = iter([(True, ""), (False, "Access is denied.")] * 8)
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(PowerCfgExecutor, "_target_schemes", lambda _s: ["a", "b"])
            )
            stack.enter_context(
                patch.object(powercfg_module, "windows_default_index", lambda *_a: None)
            )
            stack.enter_context(
                patch.object(PowerCfgExecutor, "_run", lambda _s, _a: next(answers))
            )
            ok, error = CommandExecutor.apply(setting, setting.recommended_value)

        assert ok is True
        assert error is not None and "failed" in error and "Access is denied" in error


@lru_cache(maxsize=1)
def _registry_cache() -> list[SettingExecutor]:
    return list(SettingsRegistry(discover_dynamic=False)._settings.values())


# ---------------------------------------------------------------------------
# Layer 2: every registered setting, every seam refusing at once
# ---------------------------------------------------------------------------


def _swept(registered: list[SettingExecutor]) -> list[SettingExecutor]:
    """Settings whose whole write goes through a process or the registry.

    The Python-written ones (game config lines, the actions in ``PYTHON_ACTIONS``)
    are asked above, against files of their own: sweeping them here would write the
    runner's real configs.
    """

    def in_python(setting: SettingExecutor) -> bool:
        return setting.apply_type == DetectType.POWERSHELL and (
            setting.apply_command.strip() in PYTHON_ACTIONS
            or setting.apply_args.get("batch_config") in ("mw4", "mw3_profile")
        )

    return [s for s in registered if not in_python(s)]


@windows_only
class TestNoRegisteredSettingCanSucceedWhenNothingCanBeWritten:
    def test_every_setting_fails_with_a_reason(self, registered: list[SettingExecutor]) -> None:
        swept = _swept(registered)
        wrong: list[str] = []
        with ExitStack() as stack:
            stack.enter_context(
                patch("fpstune.utils.powershell.run_watched", _fake_runner(_run_result(1)))
            )
            stack.enter_context(patch.object(process_watch, "run", _raises(_ACCESS_DENIED)))
            stack.enter_context(patch("winreg.CreateKeyEx", _raises(_ACCESS_DENIED)))
            stack.enter_context(patch("winreg.OpenKey", _raises(_ACCESS_DENIED)))
            stack.enter_context(
                patch.object(nvprofile, "missing_driver_ids", lambda _d: frozenset())
            )
            stack.enter_context(
                patch("fpstune.core.nvapi.write_driver_settings", _raises(NvapiError("call", -1)))
            )
            for setting in swept:
                # An action's value is permission to run, so the sweep gives it.
                value = True if setting.is_action else setting.recommended_value
                try:
                    ok, error = CommandExecutor.apply(setting, value)
                except Exception as exc:
                    wrong.append(f"{setting.id}: raised {type(exc).__name__}: {exc}")
                    continue
                if ok:
                    wrong.append(f"{setting.id}: reported success ({error!r})")
                elif not _readable(error):
                    wrong.append(f"{setting.id}: failed without a reason ({error!r})")

        assert not wrong, "\n".join(wrong)
        assert len(swept) > 150, "the sweep lost most of the registry; has the selection changed?"
        assert {s.apply_type.value for s in swept} >= {
            "registry",
            "powershell",
            "netsh",
            "powercfg",
            "nvprofile",
        }


# ---------------------------------------------------------------------------
# Layer 3: the shipped scripts
# ---------------------------------------------------------------------------

# Cmdlet verbs that change the machine. Anything else (Get-, Where-, Select-, Test-)
# cannot write, so it is not asked.
_WRITE_VERBS = (
    "Set|New|Remove|Add|Enable|Disable|Reset|Start|Stop|Restart|Register|Unregister|Clear"
    "|Rename|Move|Copy|Import|Install|Uninstall|Update"
)
_CMDLET = re.compile(rf"(?<![\w$-])((?:{_WRITE_VERBS})-[A-Z][A-Za-z]+)\b")
# Verb-noun pairs that name something other than the machine's state.
_NOT_A_WRITE = frozenset(
    {
        "Set-Variable",
        "New-Variable",
        "Remove-Variable",
        "Clear-Variable",
        "Set-Location",
        "Set-StrictMode",
        "Set-Alias",
        "New-Object",
        "New-TimeSpan",
        "New-Guid",
        "Add-Type",
        "Add-Member",
        "Start-Sleep",
        "Start-Process",
        "Stop-Process",
        "Clear-Host",
        "New-PSDrive",
        "Remove-PSDrive",
        "Start-Transcript",
        "Stop-Transcript",
    }
)
_SILENT = re.compile(
    r"-(?:ErrorAction|EA)\s*[:=]?\s*['\"]?(?:SilentlyContinue|Ignore|0)['\"]?(?![\w])", re.I
)
_STOPS = re.compile(r"-(?:ErrorAction|EA)\s*[:=]?\s*['\"]?Stop['\"]?(?![\w])", re.I)
_ANY_EA = re.compile(r"-(?:ErrorAction|EA)\b", re.I)
_PREFERENCE_STOP = re.compile(r"\$ErrorActionPreference\s*=\s*['\"]Stop['\"]", re.I)
_OWN_FUNCTION = re.compile(r"\bfunction\s+([A-Za-z][\w-]*)", re.I)


def _own_arguments(script: str, start: int) -> str:
    """The arguments of the cmdlet that ends at ``start``, up to its statement's end.

    Nested brackets are dropped: ``Remove-Item (Get-Item x -EA 0)`` carries the
    silence on the *read*, which is the right place for it. A line continuation
    (a trailing backtick) does not end the statement; a newline, ``;`` or ``|`` at
    depth zero does.
    """
    depth, i, quote, out = 0, start, None, []
    while i < len(script):
        c = script[i]
        if quote:
            if quote == "'" and c == "'":
                if script[i + 1 : i + 2] == "'":
                    i += 2
                    continue
                quote = None
            elif quote == '"' and c == "`":
                i += 2
                continue
            elif quote == '"' and c == '"':
                quote = None
            i += 1
            continue
        if c in "'\"":
            quote = c
        elif c == "`":
            out.append(" ")
            i += 2
            continue
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and c in "\n;|":
            break
        elif depth == 0:
            out.append(c)
        i += 1
    return "".join(out)


def _in_comment(script: str, at: int) -> bool:
    """Whether ``at`` sits after a ``#`` on its line (a quoted ``#`` does not count)."""
    prefix = script[script.rfind("\n", 0, at) + 1 : at]
    return "#" in re.sub(r"'[^']*'|\"[^\"]*\"", "", prefix)


def _consumed(script: str, at: int) -> bool:
    """Whether the write's outcome is used: ``$x = Set-...`` or ``if (-not (Set-...``."""
    start = max(script.rfind("\n", 0, at), script.rfind(";", 0, at), script.rfind("{", 0, at)) + 1
    before = script[start:at].rstrip()
    return bool(before) and (before[-1] in "=(!" or before.endswith("-not"))


def defined_functions(*scripts: str) -> frozenset[str]:
    """Names the scripts define for themselves: ``Set-Foo`` there is not a cmdlet."""
    return frozenset(n.lower() for s in scripts for n in _OWN_FUNCTION.findall(s))


def unreported_writes(
    script: str, functions: frozenset[str] = frozenset()
) -> list[tuple[str, str, str]]:
    """Every write in ``script`` whose failure the script itself would swallow.

    Returns ``(cmdlet, kind, statement)``. ``kind`` is ``silenced`` (an explicit
    ``-ErrorAction SilentlyContinue``/``Ignore``/``0`` on the write, with nothing
    reading its result) or ``unstopped`` (no ``-ErrorAction`` at all in a script
    that does not set ``$ErrorActionPreference = 'Stop'``: the error is
    non-terminating, so the script goes on and prints its success line — the
    ``60f67cf`` shape).
    """
    own = functions | defined_functions(script)
    preference_stops = bool(_PREFERENCE_STOP.search(script))
    found: list[tuple[str, str, str]] = []
    for match in _CMDLET.finditer(script):
        name = match.group(1)
        if name in _NOT_A_WRITE or name.lower() in own or _in_comment(script, match.start()):
            continue
        arguments = _own_arguments(script, match.end())
        statement = " ".join(script[match.start() : match.end() + len(arguments)].split())
        if _STOPS.search(arguments):
            continue
        if _SILENT.search(arguments):
            if not _consumed(script, match.start()):
                found.append((name, "silenced", statement))
        elif not _ANY_EA.search(arguments) and not preference_stops:
            found.append((name, "unstopped", statement))
    return found


def _string_constants(path: Path) -> Iterator[str]:
    """Every string literal in ``path``, an f-string as its literal parts joined.

    A literal that is only a piece of an f-string is not a script of its own; yielding
    it would cut a statement short at the placeholder.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pieces = {
        id(part)
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr)
        for part in node.values
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in pieces:
                yield node.value
        elif isinstance(node, ast.JoinedStr):
            yield "".join(
                part.value
                for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )


def _shipped_scripts() -> dict[str, list[str]]:
    """Where each script lives: ``action:<key>`` or the definitions file's own name."""
    scripts: dict[str, list[str]] = {f"action:{k}": [v] for k, v in ACTION_COMMANDS.items()}
    for path in sorted((_SETTINGS_DIR / "definitions").glob("*.py")):
        # Strings are scanned for write cmdlets only; a docstring that names one has
        # no argument list and so cannot carry a silenced flag.
        scripts[f"definitions/{path.name}"] = [
            s for s in _string_constants(path) if _CMDLET.search(s)
        ]
    return scripts


def _violations() -> dict[tuple[str, str, str, str], None]:
    """(source, cmdlet, kind, statement head) for every unreported write, unique."""
    found: dict[tuple[str, str, str, str], None] = {}
    for source, texts in _shipped_scripts().items():
        # A helper is often defined in one literal and called from another of the
        # same file; it is the file's own function either way.
        functions = defined_functions(*texts)
        for text in texts:
            for cmdlet, kind, statement in unreported_writes(text, functions):
                found[(source, cmdlet, kind, statement[:70])] = None
    return found


# A write that is best-effort *on purpose*. Each entry: (source pattern, cmdlet,
# statement pattern, the reason). An entry that matches nothing fails the test, so
# this list only shrinks as scripts change.
BEST_EFFORT: tuple[tuple[str, str, str, str], ...] = (
    (
        r"^action:.*(?:_cleanup|docker_prune(?:_all)?|wsl_compact)$",
        "Remove-Item",
        r".",
        "A cache cleanup is measured, not asserted: the freed bytes come from sizing the "
        "target either side of the command (C11), and a file another program holds open "
        "is expected to stay.",
    ),
    (
        r"^action:(?:windows_update_cache|delivery_optimization)_cleanup$",
        r"(?:Stop|Start)-Service",
        r"-Name (?:wuauserv|dosvc)",
        "The service is stopped so its cache can be deleted and started again after; a "
        "service that will not stop shows as a smaller freed-bytes figure, and one that "
        "will not restart is the same state the machine was in when it was idle.",
    ),
    (
        r"^action:service_toggle$",
        "Start-Service",
        r"-Name \$service",
        "After the start type is set (and read back through sc.exe's exit code) the "
        "service is started best-effort: dependencies or trigger-start may defer it, and "
        "the start type is what the setting is.",
    ),
    (
        r"^action:(?:docker_prune|docker_prune_all|wsl_compact)$",
        "Set-Content",
        r".",
        "The diskpart script is a temp file for a compaction that is measured by the vhdx "
        "size either side of it.",
    ),
    (
        r"^definitions/network\.py$",
        r"(?:Clear|Register)-DnsClient(?:Cache)?",
        r".",
        "A DNS cache flush and a DHCP re-registration run after the resolver list is "
        "written; the setting is what detect reads back from the adapters, so a flush "
        "that is refused leaves the state reached and only a stale cache entry to expire.",
    ),
)


class TestTheScannerSeesTheShape:
    """Without these, a scanner that finds nothing would read as a clean tree."""

    def test_flags_the_60f67cf_shape(self) -> None:
        script = (
            "New-Item -Path $p -Force | Out-Null\n"
            "Set-ItemProperty -Path $p -Name MSISupported -Value 1 -Type DWord\n"
            "'ok'"
        )
        assert [(n, k) for n, k, _ in unreported_writes(script)] == [
            ("New-Item", "unstopped"),
            ("Set-ItemProperty", "unstopped"),
        ]

    def test_flags_a_silenced_write_in_either_spelling(self) -> None:
        for flag in (
            "-ErrorAction SilentlyContinue",
            "-EA SilentlyContinue",
            "-EA 0",
            "-ea:Ignore",
        ):
            script = f"Set-ItemProperty -Path $p -Name N -Value 1 {flag}\n'ok'"
            assert [k for _, k, _ in unreported_writes(script)] == ["silenced"], flag

    def test_a_write_that_stops_is_clean(self) -> None:
        script = "Set-ItemProperty -Path $p -Name N -Value 1 -ErrorAction Stop; 'ok'"
        assert unreported_writes(script) == []

    def test_a_script_that_stops_by_preference_is_clean(self) -> None:
        script = "$ErrorActionPreference = 'Stop'\nSet-ItemProperty -Path $p -Name N -Value 1\n'ok'"
        assert unreported_writes(script) == []

    def test_a_silenced_write_whose_result_is_read_is_clean(self) -> None:
        script = "$r = New-NetQosPolicy -Name x -EA SilentlyContinue; if (-not $r) { 'error:x' }"
        assert unreported_writes(script) == []

    def test_silence_on_the_read_in_front_of_a_stopping_write_is_clean(self) -> None:
        script = (
            "if (Get-ItemProperty -Path $p -Name N -ErrorAction SilentlyContinue) "
            "{ Remove-ItemProperty -Path $p -Name N -ErrorAction Stop }"
        )
        assert unreported_writes(script) == []

    def test_a_continued_line_is_one_statement(self) -> None:
        script = (
            "New-NetFirewallRule -DisplayName x `\n  -Action Allow -EA SilentlyContinue | Out-Null"
        )
        assert [k for _, k, _ in unreported_writes(script)] == ["silenced"]

    def test_a_script_own_function_is_not_a_cmdlet(self) -> None:
        script = "function Set-FpsEndpointValue($a) { return $true }\nSet-FpsEndpointValue 1"
        assert unreported_writes(script) == []

    def test_a_helper_defined_in_another_literal_of_the_file_is_not_a_cmdlet(self) -> None:
        assert (
            unreported_writes("Set-FpsEndpointValue 1", frozenset({"set-fpsendpointvalue"})) == []
        )

    def test_a_cmdlet_named_in_a_comment_is_not_a_call(self) -> None:
        assert unreported_writes("# Remove-Item per file: Temp held 12719 files\n'ok'") == []


class TestEveryShippedWriteStopsOrIsBestEffortByName:
    def test_no_unlisted_write_swallows_its_failure(self) -> None:
        unlisted = []
        for source, cmdlet, kind, head in _violations():
            if any(
                re.search(src, source) and re.fullmatch(cmd, cmdlet) and re.search(stmt, head)
                for src, cmd, stmt, _reason in BEST_EFFORT
            ):
                continue
            unlisted.append(f"{source}: {cmdlet} ({kind}): {head}")
        assert not unlisted, (
            "a write cmdlet that does not stop on error reports success over a failed write; "
            "add -ErrorAction Stop (and read any 'absent is fine' case first), or name it "
            "in BEST_EFFORT with the reason:\n  " + "\n  ".join(unlisted)
        )

    def test_every_best_effort_entry_still_matches_something(self) -> None:
        found = list(_violations())
        stale = [
            f"{src} / {cmd} / {stmt}"
            for src, cmd, stmt, _reason in BEST_EFFORT
            if not any(
                re.search(src, s) and re.fullmatch(cmd, c) and re.search(stmt, h)
                for s, c, _k, h in found
            )
        ]
        assert not stale, "BEST_EFFORT entries that no script needs any more:\n  " + "\n  ".join(
            stale
        )

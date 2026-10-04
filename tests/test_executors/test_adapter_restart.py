"""A burst of per-adapter writes ends in one adapter restart, not one per write.

Every ``Set-NetAdapterAdvancedProperty`` without ``-NoRestart`` restarts the
adapter, so a bulk apply of a dozen properties dropped the link a dozen times.
"""

from __future__ import annotations

import re
import threading
from unittest.mock import patch

from fpstune.settings.definitions import network
from fpstune.settings.executors.adapter_restart import schedule_adapter_restart

_WRITERS = re.compile(
    r"(Set-NetAdapterAdvancedProperty|(Enable|Disable)-NetAdapter(Lso|ChecksumOffload)|Set-NetAdapterRSS)\b"
)


def _restarts(writes: int, adapters: tuple[int, ...] = (7,)) -> list[int]:
    done: list[int] = []
    finished = threading.Event()

    def restart(index: int) -> None:
        done.append(index)
        if len(done) == len(adapters):
            finished.set()

    for _ in range(writes):
        for index in adapters:
            assert schedule_adapter_restart(index, quiet_seconds=0.2, restart=restart)
    finished.wait(2.0)
    # Give a wrongly-uncancelled extra timer the chance to fire too.
    threading.Event().wait(0.3)
    return done


def test_ten_writes_to_one_adapter_restart_it_once() -> None:
    assert _restarts(10) == [7]


def test_each_adapter_gets_its_own_single_restart() -> None:
    assert sorted(_restarts(5, adapters=(7, 12))) == [7, 12]


def test_a_non_index_is_refused() -> None:
    for bad in (None, "", "abc", 0, -3):
        assert schedule_adapter_restart(bad, restart=lambda _i: None) is False


def _factories() -> list:
    names = [n for n in dir(network) if n.startswith("create_") and n.endswith("_setting")]
    built = []
    for name in names:
        factory = getattr(network, name)
        try:
            built.append(factory(5, "Ethernet"))
        except TypeError:
            continue
    return built


def test_every_adapter_property_write_defers_its_restart_and_asks_for_one() -> None:
    """The gate: a writer without -NoRestart restarts per write; one without the
    flag never restarts, so its value would not load until the next reboot."""
    checked = 0
    for setting in _factories():
        command = setting.apply_command
        if not _WRITERS.search(command):
            continue
        checked += 1
        for call in re.findall(r"(?:Set|Enable|Disable)-NetAdapter\w+[^;{}]*", command):
            if _WRITERS.match(call):
                assert "-NoRestart" in call, (setting.id, call)
        assert setting.apply_args.get("restart_adapter") is True, setting.id
    assert checked >= 10


def test_the_executor_schedules_the_restart_after_a_successful_write() -> None:
    from fpstune.settings.executors.powershell import PowerShellExecutor

    setting = network.create_eee_setting(9, "Ethernet")
    with (
        patch("sys.platform", "win32"),
        patch(
            "fpstune.settings.executors.game_processes.refuse_if_game_is_running",
            return_value=None,
        ),
        patch("fpstune.settings.executors.powershell.run_powershell", return_value=(True, "ok")),
        patch("fpstune.settings.executors.adapter_restart.schedule_adapter_restart") as schedule,
    ):
        assert PowerShellExecutor().apply(setting, "Disabled") == (True, None)
    schedule.assert_called_once_with(9)


def test_a_failed_write_schedules_nothing() -> None:
    from fpstune.settings.executors.powershell import PowerShellExecutor

    setting = network.create_eee_setting(9, "Ethernet")
    with (
        patch("sys.platform", "win32"),
        patch(
            "fpstune.settings.executors.game_processes.refuse_if_game_is_running",
            return_value=None,
        ),
        patch(
            "fpstune.settings.executors.powershell.run_powershell",
            return_value=(True, "error:Access is denied."),
        ),
        patch("fpstune.settings.executors.adapter_restart.schedule_adapter_restart") as schedule,
    ):
        assert PowerShellExecutor().apply(setting, "Disabled") == (False, "Access is denied.")
    schedule.assert_not_called()


def test_shutdown_runs_a_restart_still_waiting_and_only_once() -> None:
    """A change made seconds before exit would otherwise never reach the driver."""
    from fpstune.settings.executors.adapter_restart import flush_pending

    flush_pending(restart=lambda _index: None)  # timers earlier tests left behind
    late: list[int] = []
    flushed: list[int] = []
    assert schedule_adapter_restart(9, quiet_seconds=30.0, restart=late.append)
    assert flush_pending(restart=flushed.append) == [9]
    assert flushed == [9]
    assert flush_pending(restart=flushed.append) == []
    assert late == []

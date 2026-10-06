"""A burst of per-adapter writes ends in one adapter restart, not one per write.

Every ``Set-NetAdapterAdvancedProperty`` without ``-NoRestart`` restarts the
adapter, so a bulk apply of a dozen properties dropped the link a dozen times.
"""

from __future__ import annotations

import re
import threading
from unittest.mock import MagicMock, patch

from fpstune.settings.definitions import network
from fpstune.settings.executors import adapter_restart
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


# ---------------------------------------------------------------------------
# A restart is over when the adapter is back, and nothing reads in between.
# ---------------------------------------------------------------------------


class _Clock:
    """A clock the wait loop advances by sleeping, so the timeout path is instant."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_the_wait_returns_at_once_when_the_adapter_is_up() -> None:
    clock = _Clock()
    back, reason = adapter_restart.wait_until_back(
        7, status=lambda _i: "Up", sleep=clock.sleep, clock=clock
    )
    assert (back, reason) == (True, "")
    assert clock.now == 0.0


def test_the_wait_accepts_a_disconnected_adapter_because_the_driver_is_loaded() -> None:
    clock = _Clock()
    assert adapter_restart.wait_until_back(
        7, status=lambda _i: "Disconnected", sleep=clock.sleep, clock=clock
    ) == (True, "")


def test_the_wait_polls_through_the_mid_restart_states_until_the_adapter_is_back() -> None:
    clock = _Clock()
    seen = iter([None, "Disabled", "Not Present", "Up"])
    back, _ = adapter_restart.wait_until_back(
        7, poll=0.5, status=lambda _i: next(seen), sleep=clock.sleep, clock=clock
    )
    assert back is True
    assert clock.now == 1.5


def test_the_wait_times_out_with_a_reason_naming_the_adapter_and_its_last_status() -> None:
    clock = _Clock()
    back, reason = adapter_restart.wait_until_back(
        7, timeout=3.0, poll=1.0, status=lambda _i: "Disabled", sleep=clock.sleep, clock=clock
    )
    assert back is False
    assert "adapter 7" in reason
    assert "3 s" in reason
    assert "last status: Disabled" in reason


def test_the_wait_says_so_when_the_status_could_never_be_read() -> None:
    clock = _Clock()
    back, reason = adapter_restart.wait_until_back(
        7, timeout=2.0, poll=1.0, status=lambda _i: None, sleep=clock.sleep, clock=clock
    )
    assert back is False
    assert "could not be read" in reason


def test_a_status_probe_that_fails_is_unread_not_a_status() -> None:
    for ok, output in ((False, "boom"), (True, ""), (True, "error:not found")):
        with patch("fpstune.utils.powershell.run_powershell", return_value=(ok, output)):
            assert adapter_restart.adapter_status(7) is None
    with patch("fpstune.utils.powershell.run_powershell", return_value=(True, "Up\r\n")):
        assert adapter_restart.adapter_status(7) == "Up"


def _run_restart_and_probe(wait_result: tuple[bool, str]) -> tuple[list[bool], MagicMock]:
    """Run ``_restart_now`` with the adapter mid-restart, probing the in-flight mark."""
    running: list[bool] = []

    def fake_run(*_a: object, **_k: object) -> tuple[bool, str]:
        running.append(not adapter_restart.wait_for_restarts(timeout=0.05))
        return True, "ok"

    logger = MagicMock()
    with (
        patch("fpstune.utils.powershell.run_powershell", fake_run),
        patch.object(adapter_restart, "wait_until_back", return_value=wait_result),
        patch.object(adapter_restart, "logger", logger),
    ):
        adapter_restart._restart_now(7)
    return running, logger


def test_a_read_sees_the_restart_as_running_until_the_adapter_is_back() -> None:
    running, logger = _run_restart_and_probe((True, ""))
    assert running == [True], "a read during the restart must be made to wait"
    assert adapter_restart.wait_for_restarts(timeout=0.05) is True, "mark left behind"
    logger.warning.assert_not_called()


def test_a_restart_that_outlasts_the_wait_logs_the_reason_and_still_ends() -> None:
    reason = "network adapter 7 was not back within 30 s (last status: Disabled)"
    _, logger = _run_restart_and_probe((False, reason))
    logger.warning.assert_called_once()
    assert reason in logger.warning.call_args.args[-1]
    assert adapter_restart.wait_for_restarts(timeout=0.05) is True


def test_a_failed_restart_command_skips_the_wait_and_still_clears_the_mark() -> None:
    logger = MagicMock()
    with (
        patch(
            "fpstune.utils.powershell.run_powershell",
            return_value=(True, "error:Access is denied."),
        ),
        patch.object(adapter_restart, "wait_until_back") as wait,
        patch.object(adapter_restart, "logger", logger),
    ):
        adapter_restart._restart_now(7)
    wait.assert_not_called()
    logger.warning.assert_called_once()
    assert adapter_restart.wait_for_restarts(timeout=0.05) is True


def test_a_reader_blocks_while_a_restart_runs_and_is_released_when_it_ends() -> None:
    started, release = threading.Event(), threading.Event()

    def slow_run(*_a: object, **_k: object) -> tuple[bool, str]:
        started.set()
        release.wait(2.0)
        return True, "ok"

    with (
        patch("fpstune.utils.powershell.run_powershell", slow_run),
        patch.object(adapter_restart, "wait_until_back", return_value=(True, "")),
    ):
        worker = threading.Thread(target=adapter_restart._restart_now, args=(7,))
        worker.start()
        assert started.wait(2.0)
        assert adapter_restart.wait_for_restarts(timeout=0.05) is False
        release.set()
        worker.join(2.0)
    assert adapter_restart.wait_for_restarts(timeout=0.05) is True

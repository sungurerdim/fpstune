"""Every NVIDIA driver write is checked against the driver's own list of values.

The key table carries values copied from NVIDIA's header. A driver generation can
change what it takes, and a value it refuses used to be written and answered with a
generic "did not accept the change". The executor now asks the driver what it lists
for the setting first and refuses an out-of-list value in words, quoting the list,
before anything is sent. Where the driver gives no list (or cannot be asked) nothing
contradicts the write and it goes ahead.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from fpstune.core import nv_drs, nvapi
from fpstune.core.nvapi import AvailableValues
from fpstune.settings.definitions.gpu import (
    NVIDIA_FPS_LIMITER,
    NVIDIA_LOW_LATENCY,
    NVIDIA_THREADED_OPT,
    NVIDIA_VSYNC,
)
from fpstune.settings.executors import nvprofile
from fpstune.settings.executors.nvprofile import NvProfileExecutor

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="NVAPI is Windows-only")


class Driver:
    """A driver that records what reaches it, and answers a list per id."""

    def __init__(self, lists: dict[int, AvailableValues] | None) -> None:
        self.lists = lists
        self.asked: list[list[int]] = []
        self.writes: list[dict[int, int | None]] = []

    def available(self, ids: Any) -> dict[int, AvailableValues] | None:
        self.asked.append(list(ids))
        if self.lists is None:
            return None
        return {i: self.lists[i] for i in ids if i in self.lists}

    def write(self, changes: dict[int, int | None]) -> None:
        self.writes.append(dict(changes))


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch) -> Driver:
    fake = Driver({})
    monkeypatch.setattr(nvprofile, "missing_driver_ids", lambda _drs: frozenset())
    monkeypatch.setattr(nvapi, "available_setting_values", fake.available)
    monkeypatch.setattr(nvapi, "write_driver_settings", fake.write)
    return fake


# Threaded optimization as a real driver prints it: 1 and 2, default 0.
THREADED = AvailableValues((1, 2), 0)


class TestAnOutOfListValueNeverReachesTheDriver:
    def test_it_is_refused_and_nothing_is_written(self, driver: Driver) -> None:
        driver.lists = {nv_drs.OGL_THREAD_CONTROL: AvailableValues((2,), 0)}

        ok, error = NvProfileExecutor().apply(NVIDIA_THREADED_OPT, "on")  # writes 1

        assert ok is False
        assert driver.writes == []
        assert error is not None
        assert "does not accept 0x1" in error
        assert "its own values are 0x2 (default 0x0)" in error
        assert NVIDIA_THREADED_OPT.id in error

    def test_a_listed_value_is_written(self, driver: Driver) -> None:
        driver.lists = {nv_drs.OGL_THREAD_CONTROL: THREADED}

        ok, error = NvProfileExecutor().apply(NVIDIA_THREADED_OPT, "off")  # writes 2

        assert (ok, error) == (True, None)
        assert driver.writes == [{nv_drs.OGL_THREAD_CONTROL: 2}]

    def test_the_frame_cap_is_held_to_the_drivers_own_maximum(self, driver: Driver) -> None:
        # The header's 1023 is the table's ceiling; this driver says 240.
        driver.lists = {nv_drs.FRL_FPS: AvailableValues((0, 0, 240), 0)}

        refused = NvProfileExecutor().apply(NVIDIA_FPS_LIMITER, 360)
        allowed = NvProfileExecutor().apply(NVIDIA_FPS_LIMITER, 141)

        assert refused[0] is False
        assert refused[1] is not None
        assert "0 to 240" in refused[1]
        assert allowed == (True, None)
        assert driver.writes == [{nv_drs.FRL_FPS: 141}]

    def test_one_key_of_a_multi_key_choice_is_enough_to_refuse_the_whole_choice(
        self, driver: Driver
    ) -> None:
        """Low Latency "on" writes three ids; none of them may be half-written."""
        driver.lists = {
            nv_drs.PRERENDERLIMIT: AvailableValues((0, 0xFF, 0), 0),
            nv_drs.ULL_CPL_STATE: AvailableValues((0,), 0),  # 1 is not on this driver's list
        }

        ok, error = NvProfileExecutor().apply(NVIDIA_LOW_LATENCY, "on")

        assert ok is False
        assert driver.writes == []
        assert error is not None
        assert "setting 0x0005f543" in error

    def test_a_range_accepts_what_lies_between_its_ends(self, driver: Driver) -> None:
        driver.lists = {nv_drs.PRERENDERLIMIT: AvailableValues((0, 0xFF, 0), 0)}

        ok, error = NvProfileExecutor().apply(NVIDIA_LOW_LATENCY, "on")  # PRERENDERLIMIT 1

        assert (ok, error) == (True, None)
        assert driver.writes[0][nv_drs.PRERENDERLIMIT] == 1


class TestWhatTheDriverDoesNotContradictGoesAhead:
    def test_a_driver_that_lists_nothing_for_the_setting(self, driver: Driver) -> None:
        driver.lists = {}

        ok, error = NvProfileExecutor().apply(NVIDIA_THREADED_OPT, "on")

        assert (ok, error) == (True, None)
        assert driver.writes == [{nv_drs.OGL_THREAD_CONTROL: 1}]

    def test_a_driver_that_cannot_be_asked(self, driver: Driver) -> None:
        driver.lists = None

        ok, error = NvProfileExecutor().apply(NVIDIA_THREADED_OPT, "on")

        assert (ok, error) == (True, None)
        assert driver.writes == [{nv_drs.OGL_THREAD_CONTROL: 1}]

    def test_choosing_stock_deletes_the_key_and_asks_the_driver_nothing(
        self, driver: Driver
    ) -> None:
        """Stock is never written, so there is no value to check."""
        driver.lists = {nv_drs.OGL_THREAD_CONTROL: AvailableValues((7,), 7)}

        ok, error = NvProfileExecutor().apply(NVIDIA_THREADED_OPT, "auto")

        assert (ok, error) == (True, None)
        assert driver.writes == [{nv_drs.OGL_THREAD_CONTROL: None}]
        assert driver.asked == []

    def test_only_the_ids_about_to_be_written_are_asked_about(self, driver: Driver) -> None:
        driver.lists = {}

        NvProfileExecutor().apply(NVIDIA_VSYNC, "off")

        assert driver.asked == [[nv_drs.VSYNCMODE]]


class TestTheTableIsStillCheckedFirst:
    def test_a_value_the_table_itself_forbids_is_refused_without_asking_the_driver(
        self, driver: Driver
    ) -> None:
        ok, error = NvProfileExecutor().apply(NVIDIA_FPS_LIMITER, 5000)

        assert ok is False
        assert error is not None
        assert "outside 0-" in error
        assert driver.asked == []
        assert driver.writes == []

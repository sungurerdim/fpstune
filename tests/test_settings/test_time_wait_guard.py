"""``network:time_wait_delay`` puts the stock TIME_WAIT wait back (Product Goal consequence 6).

fpstune 0.1.x wrote TcpTimedWaitDelay = 30 against Windows' stock 120 s (value
absent). Windows 11 honours the key, so a machine that ran that release carries
the 30 until something removes it. The row is a guard: its recommendation IS the
stock state, it reads an explicit 120 as stock too, and applying it deletes the value.
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import DefaultSource
from fpstune.settings.definitions.network import NETWORK_SETTINGS, TCP_TIME_WAIT_DELAY
from fpstune.settings.executors import map_raw_to_display


def test_the_row_is_registered_and_recommends_the_stock_state() -> None:
    assert TCP_TIME_WAIT_DELAY in NETWORK_SETTINGS
    row = TCP_TIME_WAIT_DELAY
    assert row.recommended_value == row.default_value == "standard"
    assert row.default_source is DefaultSource.WINDOWS_STOCK


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        (None, "standard"),  # the value is absent on a stock machine
        (120, "standard"),  # an explicit 120 behaves like stock
        ("120", "standard"),
        (30, "changed"),  # what fpstune 0.1.x wrote
        (60, "changed"),
        (300, "changed"),
    ],
)
def test_detection_tells_stock_from_a_changed_wait(raw: object, shown: str) -> None:
    assert map_raw_to_display(TCP_TIME_WAIT_DELAY.value_map, raw) == shown
    assert shown in TCP_TIME_WAIT_DELAY.choices


def test_applying_the_stock_state_deletes_the_value() -> None:
    """None is the registry executor's "delete"; writing 120 would leave a value behind."""
    assert TCP_TIME_WAIT_DELAY.apply_value_map == {"standard": None}
    assert TCP_TIME_WAIT_DELAY.apply_args["name"] == "TcpTimedWaitDelay"

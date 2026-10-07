"""Edge Background Mode: its own row (C8), and it round-trips to Windows' own state.

Failures these tests guard against:

- Startup Boost and Background Mode bundled into one row (C8): the first preloads Edge at
  sign-in, the second keeps it alive after close, and a player may want one without the other;
- a reset that leaves the policy value behind instead of removing it;
- writing one switch changing what the other one reads.
"""

from __future__ import annotations

import sys

import pytest

from fpstune.settings.applicability import values_equal
from fpstune.settings.definitions.system import PERF_EDGE_BACKGROUND_MODE, PERF_EDGE_STARTUP_BOOST
from fpstune.settings.executors import CommandExecutor
from tests.test_settings.fake_registry import FakeRegistry

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the executor reads winreg")

EDGE_POLICY = r"SOFTWARE\Policies\Microsoft\Edge"
ROW = PERF_EDGE_BACKGROUND_MODE


def test_detect_apply_reset_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = FakeRegistry(monkeypatch)
    # A policy another setting of ours owns must survive both writes.
    registry.put(EDGE_POLICY, "DiagnosticData", 0)

    stock, error = CommandExecutor.detect(ROW)
    assert (stock, error) == ("enabled", None)
    assert values_equal(stock, ROW.default_value)

    ok, error = CommandExecutor.apply(ROW, ROW.recommended_value)
    assert (ok, error) == (True, None)
    assert registry.get(EDGE_POLICY, "BackgroundModeEnabled") == 0
    optimized, error = CommandExecutor.detect(ROW)
    assert (optimized, error) == ("disabled", None)
    assert values_equal(optimized, ROW.recommended_value)

    ok, error = CommandExecutor.apply(ROW, ROW.default_value)
    assert (ok, error) == (True, None)
    assert (
        registry.get(EDGE_POLICY, "BackgroundModeEnabled") is None
    )  # stock is "no policy", not "1"
    back, error = CommandExecutor.detect(ROW)
    assert (back, error) == ("enabled", None)
    assert values_equal(back, ROW.default_value)

    assert registry.get(EDGE_POLICY, "DiagnosticData") == 0


def test_it_is_not_the_same_policy_as_startup_boost() -> None:
    assert ROW.id != PERF_EDGE_STARTUP_BOOST.id
    assert ROW.apply_args["name"] != PERF_EDGE_STARTUP_BOOST.apply_args["name"]


def test_turning_it_off_leaves_startup_boost_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeRegistry(monkeypatch)

    assert CommandExecutor.apply(ROW, "disabled") == (True, None)

    assert CommandExecutor.detect(PERF_EDGE_STARTUP_BOOST) == ("enabled", None)

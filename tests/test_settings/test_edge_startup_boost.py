"""Edge Startup Boost: detect, apply and reset round-trip to Windows' own state.

Failures these tests guard against:

- a reset that leaves a policy value behind (``0`` written back as ``1``) instead of
  removing it, so the browser stays "managed" and the row never returns to Windows stock;
- the recommendation read back as "enabled" because the policy value was written to a
  different key than the one detect reads;
- the write clobbering another Edge policy fpstune owns (``DiagnosticData``).
"""

from __future__ import annotations

import sys

import pytest

from fpstune.settings.applicability import values_equal
from fpstune.settings.definitions.system import PERF_EDGE_STARTUP_BOOST
from fpstune.settings.executors import CommandExecutor
from tests.test_settings.fake_registry import FakeRegistry

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the executor reads winreg")

EDGE_POLICY = r"SOFTWARE\Policies\Microsoft\Edge"
ROW = PERF_EDGE_STARTUP_BOOST


def test_detect_apply_reset_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = FakeRegistry(monkeypatch)
    # A policy another setting of ours owns must survive both writes.
    registry.put(EDGE_POLICY, "DiagnosticData", 0)

    stock, error = CommandExecutor.detect(ROW)
    assert (stock, error) == ("enabled", None)
    assert values_equal(stock, ROW.default_value)

    ok, error = CommandExecutor.apply(ROW, ROW.recommended_value)
    assert (ok, error) == (True, None)
    assert registry.get(EDGE_POLICY, "StartupBoostEnabled") == 0
    optimized, error = CommandExecutor.detect(ROW)
    assert (optimized, error) == ("disabled", None)
    assert values_equal(optimized, ROW.recommended_value)

    ok, error = CommandExecutor.apply(ROW, ROW.default_value)
    assert (ok, error) == (True, None)
    assert registry.get(EDGE_POLICY, "StartupBoostEnabled") is None  # stock is "no policy", not "1"
    back, error = CommandExecutor.detect(ROW)
    assert (back, error) == ("enabled", None)
    assert values_equal(back, ROW.default_value)

    assert registry.get(EDGE_POLICY, "DiagnosticData") == 0

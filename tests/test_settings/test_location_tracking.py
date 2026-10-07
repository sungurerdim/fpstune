"""Location service: detect, apply and reset round-trip to Windows' own state.

Failures these tests guard against:

- a reset that writes the policy back as ``0`` instead of removing it, so the Settings
  page keeps showing "some settings are managed by your organization" and the row never
  returns to Windows stock;
- the recommendation written to a key detect does not read, so the row reports
  "enabled" right after a successful apply;
- the write touching another value under the same policy key.
"""

from __future__ import annotations

import sys

import pytest

from fpstune.settings.applicability import values_equal
from fpstune.settings.definitions.system import PRIVACY_LOCATION as ROW
from fpstune.settings.executors import CommandExecutor
from tests.test_settings.fake_registry import FakeRegistry

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="the executor reads winreg")

POLICY = r"SOFTWARE\Policies\Microsoft\Windows\LocationAndSensors"


def test_detect_apply_reset_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = FakeRegistry(monkeypatch)
    registry.put(POLICY, "DisableSensors", 0)  # a neighbour in the same key

    stock, error = CommandExecutor.detect(ROW)
    assert (stock, error) == ("enabled", None)
    assert values_equal(stock, ROW.default_value)

    ok, error = CommandExecutor.apply(ROW, ROW.recommended_value)
    assert (ok, error) == (True, None)
    assert registry.get(POLICY, "DisableLocation") == 1
    optimized, error = CommandExecutor.detect(ROW)
    assert (optimized, error) == ("disabled", None)
    assert values_equal(optimized, ROW.recommended_value)

    ok, error = CommandExecutor.apply(ROW, ROW.default_value)
    assert (ok, error) == (True, None)
    assert registry.get(POLICY, "DisableLocation") is None  # stock is "no policy", not 0
    back, error = CommandExecutor.detect(ROW)
    assert (back, error) == ("enabled", None)
    assert values_equal(back, ROW.default_value)

    assert registry.get(POLICY, "DisableSensors") == 0


def test_a_policy_set_to_zero_reads_as_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Another tool may write ``0`` explicitly; that is location on, not an unknown."""
    FakeRegistry(monkeypatch).put(POLICY, "DisableLocation", 0)

    assert CommandExecutor.detect(ROW) == ("enabled", None)

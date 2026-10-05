"""Creating FPS Balanced writes to FPS Balanced and nothing else.

The executor's default target is the active plan plus every custom plan, which
is right for applying a setting and wrong for creating a plan: creation used to
rewrite the user's current plan and every Bitsum/AMD/OEM plan on the machine.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

from fpstune.core import power_profile
from fpstune.core.power_profile import PowerProfileManager

NEW_GUID = "0f9d8a6b-1c2d-4e5f-8a9b-0c1d2e3f4a5b"


def _run(returncodes: dict[str, int]):
    calls: list[list[str]] = []

    def run(args, *_args, **_kwargs):
        calls.append(list(args))
        verb = args[1]
        out = f"Power Scheme GUID: {NEW_GUID}  (Balanced)" if verb == "/duplicatescheme" else ""
        return SimpleNamespace(returncode=returncodes.get(verb, 0), stdout=out, stderr="")

    return run, calls


def test_settings_are_written_to_the_new_plan_only() -> None:
    setting = SimpleNamespace(effect="x", recommended_value=5)
    applied: list[dict] = []
    run, _ = _run({})

    with (
        patch.object(sys, "platform", "win32"),
        patch.object(PowerProfileManager, "find_fps_balanced", return_value=None),
        patch.object(power_profile.process_watch, "run", side_effect=run),
        patch.object(power_profile, "_registry_powercfg_settings", return_value=[setting]),
        patch.object(
            power_profile.PowerCfgExecutor,
            "apply",
            side_effect=lambda _self, _s, _v, **kw: (applied.append(kw), (True, None))[1],
            autospec=True,
        ),
    ):
        result = PowerProfileManager().create()

    assert result.success, result.message
    assert applied == [{"schemes": [NEW_GUID]}]


def test_a_plan_that_cannot_be_named_is_removed() -> None:
    run, calls = _run({"/changename": 1})

    with (
        patch.object(sys, "platform", "win32"),
        patch.object(PowerProfileManager, "find_fps_balanced", return_value=None),
        patch.object(power_profile.process_watch, "run", side_effect=run),
    ):
        result = PowerProfileManager().create()

    assert result.success is False
    assert [c[1:] for c in calls if c[1] == "/delete"] == [["/delete", NEW_GUID]]

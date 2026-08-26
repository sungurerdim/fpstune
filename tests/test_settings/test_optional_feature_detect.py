""" "Could not read it" is not "it is turned off".

`system:hyper_v` and `system:vm_platform` read Windows optional features with
`Get-WindowsOptionalFeature -Online`, which requires elevation. The shipped
command swallowed the elevation failure with `-ErrorAction SilentlyContinue`,
left `$f` null, and fell through to the else branch — so it answered
**'disabled'** for a machine it had not managed to read.

That is the defect this codebase keeps paying for, in a new place: a failure
reported as a value. A user whose Hyper-V is on and costing them frames was told
it was off, and fpstune called the setting already optimal.

There is a second cost. The raise also travelled out of the shared detect
session's scriptblock, so both settings lost their batched result and fell back
to a process each — two of the twenty-five a cold scan spawned.
"""

from __future__ import annotations

import re

import pytest

from fpstune.settings.applicability import is_absent_reading
from fpstune.settings.executors.ps_batch import command_is_batchable
from fpstune.settings.registry import SettingsRegistry

FEATURE_SETTINGS = ("system:hyper_v", "system:vm_platform")


@pytest.fixture(scope="module")
def registry() -> SettingsRegistry:
    return SettingsRegistry(discover_dynamic=False)


@pytest.mark.parametrize("setting_id", FEATURE_SETTINGS)
class TestItSaysWhenItCouldNotRead:
    def test_an_unreadable_feature_is_not_reported_as_disabled(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        setting = registry.get(setting_id)
        assert setting is not None
        command = setting.detect_command

        # The failure path must produce an absent reading, which detection turns
        # into is_applicable=False, rather than one of the two real states.
        catch = re.search(r"catch\s*\{\s*'([^']+)'\s*\}", command)
        assert catch, f"{setting_id} has no catch clause, so a failure becomes a value again"
        assert is_absent_reading(catch.group(1)), (
            f"{setting_id} answers {catch.group(1)!r} when it cannot read the feature; "
            "only an absent reading keeps that distinct from 'disabled'"
        )

    def test_it_does_not_swallow_the_error_into_a_null(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        """`-ErrorAction SilentlyContinue` is exactly how the null got there."""
        setting = registry.get(setting_id)
        assert setting is not None
        assert "SilentlyContinue" not in setting.detect_command
        assert "-ErrorAction Stop" in setting.detect_command

    def test_both_real_states_are_still_reachable(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        """Refusing to guess must not cost the answers it can actually give."""
        setting = registry.get(setting_id)
        assert setting is not None
        assert "'enabled'" in setting.detect_command
        assert "'disabled'" in setting.detect_command
        assert set(setting.choices) >= {"enabled", "disabled"}

    def test_it_can_share_a_batched_session(
        self, registry: SettingsRegistry, setting_id: str
    ) -> None:
        """A command that raises costs itself its batched result.

        Nothing is wrong with the value when it falls back — it just pays for a
        process to get the same answer the session already had a slot for.
        """
        setting = registry.get(setting_id)
        assert setting is not None
        assert command_is_batchable(setting.detect_command.strip())
        assert not any(key.startswith("batch_") for key in setting.detect_args)

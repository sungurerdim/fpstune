"""A value the escaping layer will not place must be refused, not raised.

``substitute_placeholders`` raises ``ValueError`` for a value it cannot escape
safely — an unquoted placeholder holding anything but a plain token. The netsh
and PowerShell executors already turn that into their own failure shape; these
two call sites did not, so the same input reached the action stream as an
unexplained error and the batch prefetch as an exception that took the whole
scan's grouping with it.

Neither substitutes a request value today (both read setting-declared
``apply_args``/``detect_args``), so nothing a user can send arrives here. The
guard is against the next setting to declare a wide argument: without it that
setting turns a refusal into a 500 and, in the prefetch, costs every unrelated
setting in the scan its batch.
"""

from __future__ import annotations

import pytest

from fpstune.settings.base import (
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingValueType,
)

# An unquoted placeholder: the escaping layer allows only a plain keyword or
# number there, so a value carrying a statement separator has no safe rendering
# and is refused rather than quoted into something that would run.
_UNPLACEABLE = "svc; Remove-Item C:\\"


def _powershell_action(command: str, args: dict[str, str]) -> SettingExecutor:
    return SettingExecutor(
        id="maintenance:refusal_probe",
        category=SettingCategory.MAINTENANCE,
        display_name="Refusal Probe",
        description="A stand-in action whose declared argument cannot be escaped. "
        "It exists to prove the refusal path, never to run.",
        value_type=SettingValueType.BOOL,
        default_value=False,
        recommended_value=True,
        current_impact="Not run: nothing has happened",
        recommended_impact="Refused: the command was never built",
        is_action=True,
        detect_type=DetectType.POWERSHELL,
        detect_command=command,
        detect_args=args,
        apply_type=DetectType.POWERSHELL,
        apply_command=command,
        apply_args=args,
    )


def test_the_layer_really_refuses_this_value() -> None:
    """Pins the premise. If the escaping layer ever starts accepting this, the
    two tests below would pass while guarding nothing."""
    from fpstune.utils.powershell import substitute_placeholders

    with pytest.raises(ValueError):
        substitute_placeholders("Get-Service -Name %name%", name=_UNPLACEABLE)


class TestBatchPrefetchDropsOnlyTheRefusedSetting:
    """One setting the escaping layer refuses used to raise out of
    ``_prefetch_powershell_group``, so every *other* setting in the scan lost
    its shared PowerShell session and paid for its own process."""

    def _batchable(self, setting_id: str, args: dict[str, str]) -> SettingExecutor:
        return SettingExecutor(
            id=setting_id,
            category=SettingCategory.NETWORK,
            display_name="Batchable Probe",
            description="A stand-in detect that the prefetch groups. It exists to "
            "prove one refusal does not cost the others their batch.",
            value_type=SettingValueType.CHOICE,
            choices=("enabled", "disabled"),
            default_value="enabled",
            recommended_value="disabled",
            current_impact="Enabled: the probe reports its own value",
            recommended_impact="Disabled: the probe reports its own value",
            detect_type=DetectType.POWERSHELL,
            detect_command="Get-Service -Name %name%",
            detect_args=args,
            apply_type=DetectType.POWERSHELL,
            apply_command="",
            apply_args={},
        )

    def test_the_good_setting_is_still_batched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from fpstune.settings import detection

        captured: list[list[tuple[str, str]]] = []
        monkeypatch.setattr(
            detection, "prefetch_powershell_detects", lambda specs: captured.append(specs)
        )

        detection._prefetch_powershell_group(
            [
                self._batchable("network:refused_probe", {"name": _UNPLACEABLE}),
                self._batchable("network:good_probe", {"name": "Spooler"}),
            ]
        )

        assert len(captured) == 1
        assert [setting_id for setting_id, _ in captured[0]] == ["network:good_probe"]

    def test_a_refusal_alone_prefetches_nothing_rather_than_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from fpstune.settings import detection

        captured: list[list[tuple[str, str]]] = []
        monkeypatch.setattr(
            detection, "prefetch_powershell_detects", lambda specs: captured.append(specs)
        )

        detection._prefetch_powershell_group(
            [self._batchable("network:refused_probe", {"name": _UNPLACEABLE})]
        )

        assert captured == []

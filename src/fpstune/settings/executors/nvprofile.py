"""NVIDIA driver settings: detect and apply through NVAPI's settings database.

Every read comes from the driver itself and every write goes to it directly —
nothing is cached, so verifying a setting is an observation, never fpstune
comparing a value with its own record of it. Which DRS keys a setting touches
lives in ``core/nv_drs.py``; the session handling in ``core/nvapi.py``.
"""

from __future__ import annotations

import sys
from collections.abc import Collection, Iterable
from typing import TYPE_CHECKING, Any

from fpstune.core.nv_drs import EnumKey, NumberKey, lookup
from fpstune.settings.applicability import NOT_AVAILABLE, NOT_SUPPORTED
from fpstune.settings.executors import BaseExecutor
from fpstune.utils.logger import get_logger

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor

logger = get_logger()


def missing_ids(ids: Iterable[int]) -> frozenset[int] | None:
    """The given DRS keys the installed driver does not define.

    None when the driver could not be asked: absence is only ever reported from
    the driver's own answer, never inferred from a failed probe.
    """
    from fpstune.core.nvapi import known_setting_ids

    wanted = frozenset(ids)
    known = known_setting_ids(wanted)
    return None if known is None else wanted - known


def missing_driver_ids(drs: EnumKey | NumberKey) -> frozenset[int]:
    """The setting's DRS keys the installed driver does not define.

    Empty when the driver could not be asked (see :func:`missing_ids`).
    """
    return missing_ids(drs.ids) or frozenset()


def holdable_choices(setting: SettingExecutor, missing: Collection[int]) -> tuple[str, ...] | None:
    """The setting's declared choices this driver can hold, in declared order.

    None when the setting is not a choice over an NVIDIA enum key, so there is
    nothing to narrow. A declared choice the key table does not know is kept:
    narrowing only ever removes what the driver's own answer rules out.
    """
    drs = lookup(str(setting.detect_args.get("setting", "")))
    if not isinstance(drs, EnumKey):
        return None
    held = drs.choices(missing)
    return tuple(c for c in setting.choices if c in held or c not in drs.values)


def answers_are_holdable(setting: SettingExecutor, drs: EnumKey, missing: Collection[int]) -> bool:
    """Whether the setting's default and recommendation both fit this driver.

    A recommendation the driver cannot hold is never remapped to another value:
    the row is not applicable here instead (C10).
    """
    held = drs.choices(missing)
    return all(
        str(value) in held or str(value) not in drs.values
        for value in (setting.default_value, setting.recommended_value)
    )


def read_setting_from_driver(setting_key: str) -> Any | None:
    """The setting's current value as the driver reports it, or None.

    None means no observation: the key is unknown, NVAPI is unusable here, or
    the driver holds a state none of the setting's choices describes.
    """
    drs = lookup(setting_key)
    if drs is None:
        return None

    from fpstune.core.nvapi import read_driver_settings

    raw = read_driver_settings(list(drs.read_ids))
    if raw is None:
        return None
    return drs.decode(raw)


class NvProfileExecutor(BaseExecutor):
    """Executor for NVIDIA Control Panel global settings."""

    def detect(self, setting: SettingExecutor) -> tuple[Any | None, str | None]:
        if sys.platform != "win32":
            return None, "Not available on this platform"

        setting_key = str(setting.detect_args.get("setting", ""))
        drs = lookup(setting_key)
        if drs is None:
            return None, f"No NVIDIA driver key is defined for '{setting_key}'"

        from fpstune.core.nvapi import read_driver_settings

        raw = read_driver_settings(list(drs.read_ids))
        if raw is None:
            # No NVIDIA driver answering here: the setting does not apply.
            return NOT_AVAILABLE, None

        missing = missing_driver_ids(drs)
        if not drs.supports(missing) or (
            isinstance(drs, EnumKey) and not answers_are_holdable(setting, drs, missing)
        ):
            # The driver does not define the keys this setting lives in, or cannot
            # hold the value the row recommends or resets to (C10: not-applicable
            # is an answer, not an apply failure waiting to happen).
            return NOT_SUPPORTED, None

        value = drs.decode(raw)
        if value is None:
            readings = ", ".join(f"{i:#010x}={raw.get(i, 'default')}" for i in drs.read_ids)
            return None, (
                f"The NVIDIA driver holds a {setting_key} state none of this "
                f"setting's choices describes ({readings}); applying a choice replaces it."
            )
        return value, None

    def apply(self, setting: SettingExecutor, value: Any) -> tuple[bool, str | None]:
        if sys.platform != "win32":
            return False, "Not available on this platform"

        setting_key = str(setting.apply_args.get("setting", ""))
        drs = lookup(setting_key)
        if drs is None:
            return False, f"No NVIDIA driver key is defined for '{setting_key}'"

        missing = missing_driver_ids(drs)
        try:
            if isinstance(drs, NumberKey):
                changes = drs.changes_for(int(value), missing)
            else:
                assert isinstance(drs, EnumKey)
                changes = drs.changes_for(str(value), missing)
        except (TypeError, ValueError) as exc:
            return False, f"Invalid value for {setting.id}: {exc}"

        from fpstune.core.nv_drs import refused_writes
        from fpstune.core.nvapi import (
            NvapiError,
            NvapiUnavailable,
            available_setting_values,
            write_driver_settings,
        )

        # Every write is checked against the values the driver itself lists for the
        # setting before it is sent. A driver that gives no list (or cannot be asked)
        # contradicts nothing; one that does refuses a value outside it, in words.
        written = [setting_id for setting_id, value in changes.items() if value is not None]
        available = available_setting_values(written) if written else None
        refusals = refused_writes(drs, changes, available or {})
        if refusals:
            reasons = "; ".join(refusal.message for refusal in refusals)
            return False, f"Invalid value for {setting.id}: {reasons}"

        try:
            write_driver_settings(changes)
        except NvapiUnavailable as exc:
            return False, f"The NVIDIA driver settings interface is not available: {exc}"
        except (NvapiError, OSError) as exc:
            return False, f"The NVIDIA driver did not accept the change: {exc}"
        return True, None

"""The NVIDIA driver settings this driver can actually hold, and what it calls them.

``core/nv_drs.py`` declares every value a setting may take; the installed driver
decides which of them it can express (driver 617.14 has no ``ULL_ENABLED``, so
Low Latency "ultra" would run exactly as "on"). This pass narrows each row's
``choices`` to what the driver says it can hold, the same way ``adopt_mw4_ranges``
adopts the installed game's own ranges: the machine is the authority and the
declared list is the fallback. It also names each offered choice the way that
capability set does (``EnumKey.choice_labels``), so the one-queued-frame tier
reads "Ultra" where the vendor's own app calls it that and "On" where the vendor's
control panel does — decided by which keys the driver defines, never by a driver
version. It runs once per registry, so the driver is asked once per session (C7).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fpstune.settings.discovery import Registrar
    from fpstune.settings.discovery.probes import HardwareProbes

logger = logging.getLogger(__name__)

# What the last drift report said, so building a second registry in one process
# does not repeat a line that has not changed.
_reported_unmapped: frozenset[tuple[int, int]] = frozenset()


def report_unmapped_settings() -> None:
    """Log, once, the global-profile settings the key table does not map.

    Diagnostic only: a driver that grows a setting (or an older tool that wrote
    one) shows up here with its value, so a table that has fallen behind the
    driver is visible instead of silent. Nothing is read from the answer.
    """
    global _reported_unmapped
    from fpstune.core.nv_drs import mapped_ids
    from fpstune.core.nvapi import NvapiError, NvapiUnavailable, dump_driver_settings

    try:
        present = dump_driver_settings()
    except (NvapiUnavailable, NvapiError, OSError) as exc:
        logger.debug("NVIDIA driver settings could not be listed: %s", exc)
        return

    mapped = mapped_ids()
    unmapped = frozenset((s.setting_id, s.value) for s in present if s.setting_id not in mapped)
    if not unmapped or unmapped == _reported_unmapped:
        return
    _reported_unmapped = unmapped
    listing = ", ".join(f"{i:#010x}={v:#x}" for i, v in sorted(unmapped))
    logger.info("NVIDIA driver holds settings fpstune does not map: %s", listing)


def narrow_nvidia_choices(registry: Registrar, probes: HardwareProbes) -> int:  # noqa: ARG001
    """Drop the choices the installed NVIDIA driver cannot express, and name the rest.

    Nothing is narrowed or renamed when the driver cannot be asked: absence is
    only ever read from the driver's own answer. A narrowed list is adopted only
    while it still holds the setting's default and recommended values; otherwise
    the declared list stays and the executor reports the row as not supported, so
    a recommendation is never silently remapped to a different value.

    The result is written onto a **copy**: the definitions are module-level
    singletons shared by every registry built in the process.

    Returns:
        Number of settings whose choices were narrowed. Zero when the driver
        holds every choice, cannot be asked, or is not there.
    """
    from dataclasses import replace

    from fpstune.core.nv_drs import EnumKey, lookup
    from fpstune.settings.base import DetectType
    from fpstune.settings.executors.nvprofile import holdable_choices, missing_ids

    rows = [
        s
        for s in registry.get_all()
        if s.detect_type == DetectType.NVPROFILE and s.apply_type == DetectType.NVPROFILE
    ]
    ids: set[int] = set()
    for row in rows:
        drs = lookup(str(row.detect_args.get("setting", "")))
        if drs is not None:
            ids.update(drs.ids)
    if not ids:
        return 0

    missing = missing_ids(ids)
    if missing is None:  # unaskable: no era can be told, so nothing is narrowed or renamed
        return 0
    report_unmapped_settings()

    narrowed = 0
    for row in rows:
        held = holdable_choices(row, missing)
        if held is None:
            continue
        drs = lookup(str(row.detect_args.get("setting", "")))
        labels = drs.choice_labels(missing) if isinstance(drs, EnumKey) else {}
        if held == row.choices and labels == row.choice_labels:
            continue
        required = {str(row.default_value), str(row.recommended_value)}
        if not required.issubset(held):
            logger.debug(
                "NVIDIA %s: this driver holds %s, which is missing %s — row not supported here",
                row.id,
                held,
                sorted(required - set(held)),
            )
            continue
        registry.register(replace(row, choices=held, choice_labels=labels))
        if held != row.choices:
            narrowed += 1

    if narrowed:
        logger.debug("NVIDIA: %d settings narrowed to what the installed driver can hold", narrowed)
    return narrowed

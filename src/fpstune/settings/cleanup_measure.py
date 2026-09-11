"""What a cleanup's target measures now, and what a command freed.

Two things live here because they are the same question asked twice. Reading a
``ready|<size>`` line is one parse — the background scan, the batch and the
apply-time measurement all come through it, so none of them can disagree about
what "unavailable" or "1234 MB" means for the same output. And a *pair* of those
readings, taken immediately either side of a cleanup command, is the only thing
in this codebase entitled to say how much space a cleanup freed.

What it replaces was not a measurement: a cached size up to five minutes old,
rounded out of a display string, minus whatever a background re-scan reported
some seconds after the run. Nothing bracketed the command (C11 rules 1 and 2).
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor
    from fpstune.settings.cleanup_targets import SizeReading

logger = logging.getLogger(__name__)


class CleanupSize(NamedTuple):
    """One cleanup target's reclaimable size, as one measurement reported it.

    ``size_bytes`` is a number for a ``ready`` reading and for a
    ``not_estimated`` one; "unavailable" and "not_installed" carry the word and
    no number, because a 0 there reads in the UI as "nothing to clean" and would
    be a figure no instrument produced (C11 rule 3).

    ``not_estimated`` is the fourth answer and the least obvious one: bytes that
    were really measured, of a thing whose size is not a promise of what the
    command frees. A WSL virtual disk is the case it exists for — its file is
    96 MB and compacting it returns the slack inside, which nothing outside the
    VM can read. The row therefore advertises no reclaimable size, while a
    before/after pair of these readings still measures what the run reclaimed.
    """

    status: str  # "ready" | "not_estimated" | "unavailable" | "not_installed"
    size_bytes: int | None
    reading: str  # the ``ready|...`` text a row shows, so the cache stores that


def _parse_cleanup_reading(reading: str) -> CleanupSize | None:
    """The last ``ready|<size>`` line in `reading`, or None if there is none.

    The one parse of a cleanup reading: the cache store and the apply-time
    measurement both come through here, so the two cannot disagree about what
    "unavailable", "not_installed" or "1234 MB" means for the same output.
    """
    for line in reversed(reading.splitlines()):
        s = line.strip()
        if not s.startswith("ready|"):
            continue
        size_part = s[6:].strip()
        # Service/daemon not running (e.g. Docker engine down): surface as
        # unavailable so the UI shows that, not "0 MB".
        if size_part.lower() == "unavailable":
            return CleanupSize("unavailable", None, s)
        # Target software/dirs absent → not applicable (hidden, uncounted).
        if size_part.lower() == "not_installed":
            return CleanupSize("not_installed", None, s)
        if size_part and "?" not in size_part and "MB" in size_part:
            try:
                mb = int(size_part.split()[0])
            except (ValueError, IndexError):
                continue
            return CleanupSize("ready", mb * 1024 * 1024, s)
    return None


def store_measurement(setting_id: str, measured: CleanupSize) -> None:
    """Put one measurement into the cleanup size cache, in bytes.

    The one write. Exact bytes, never the rounded figure out of the display
    string: `/cleanup-sizes` serves this number straight to the UI, and rounding
    to megabytes on the way in makes a 512 KB cache "0 MB" and a freed figure the
    subtraction of two roundings.
    """
    from fpstune.settings.cleanup_cache import cleanup_size_cache

    if measured.status == "not_installed":
        cleanup_size_cache.set_not_installed(setting_id)
    elif measured.status == "ready":
        cleanup_size_cache.set_result(setting_id, measured.size_bytes or 0)
    else:
        # "unavailable" and "not_estimated" both mean the row must not show a
        # reclaimable size: one because nothing could be read, the other because
        # what was read is not a promise the command can keep.
        cleanup_size_cache.set_unavailable(setting_id)


def store_cleanup_reading(setting_id: str, reading: str) -> bool:
    """Turn one ``ready|<size>`` line into a cache entry. False if unparseable.

    The text door into the same store, for the readings that still come back as
    PowerShell output — DISM's component store estimate, docker's own accounting,
    the shadow storage allocation, the event log record counts.
    """
    parsed = _parse_cleanup_reading(reading)
    if parsed is None:
        return False
    store_measurement(setting_id, parsed)
    return True


def cleanup_type_of(setting: SettingExecutor) -> str | None:
    """Which cleanup target this setting sizes, or None if it sizes none.

    A cleanup is named by its detect side — ``cleanup_status`` plus the type its
    script is asked about — and never by the module or the id, neither of which
    says anything about what a setting cleans.
    """
    if sys.platform != "win32":
        return None
    if setting.detect_command.strip() != "cleanup_status":
        return None
    cleanup_type = str(setting.detect_args.get("type", "")).strip()
    return cleanup_type or None


def measure_cleanup_size(setting: SettingExecutor, *, remember: bool = False) -> CleanupSize | None:
    """Size this cleanup's target right now, or None when nothing was measured.

    The instrument is the one the scan uses, whichever of the two that is: a
    walk of this target's own path list in this process where the target is a
    folder, and the shipped ``Get-CleanupStatus`` script where the answer needs a
    component store, a docker daemon or the event log service. Either way a
    before/after pair around a cleanup command is two readings on one axis, and
    their difference is what the command actually freed rather than a claim about
    it (C11 rules 1 and 2). Anything that did not come back readable is None,
    never a 0: "we could not measure it" and "it freed nothing" are different
    answers and only one of them would be true (C11 rule 3).

    ``remember`` writes the reading into the cleanup size cache, which is what
    the after-measurement is for: the post-apply detect then reports the size the
    command left behind instead of the pre-cleanup figure, with no re-scan. A
    measurement that came back unreadable drops the entry instead, so nothing
    serves a number the run has just made wrong.
    """
    cleanup_type = cleanup_type_of(setting)
    if cleanup_type is None:
        return None

    parsed = measure_cleanup_type(cleanup_type)
    if remember:
        from fpstune.settings.cleanup_cache import cleanup_size_cache

        if parsed is None:
            cleanup_size_cache.invalidate(setting.id)
        else:
            store_measurement(setting.id, parsed)
    return parsed


def as_reading(measured: SizeReading) -> CleanupSize:
    """One in-process measurement in the shape every reader already understands.

    The wire text stays ``ready|<n> MB`` because that is what a row displays, and
    the exact byte count travels beside it — the display is rounded, the
    measurement is not.
    """
    if measured.status == "not_installed":
        return CleanupSize("not_installed", None, "ready|not_installed")
    if measured.status == "unavailable":
        return CleanupSize("unavailable", None, "ready|unavailable")
    size = measured.size_bytes or 0
    if measured.status == "not_estimated":
        # Real bytes, and not a reclaimable size: the row says so, the pair of
        # readings around the run still measures what it reclaimed.
        return CleanupSize("not_estimated", size, "ready|unavailable")
    return CleanupSize("ready", size, f"ready|{round(size / (1024 * 1024))} MB")


def measure_cleanup_type(cleanup_type: str) -> CleanupSize | None:
    """Measure one cleanup target by the instrument that owns it."""
    from fpstune.settings.cleanup_targets import CLEANUP_TARGETS, size_target

    target = CLEANUP_TARGETS.get(cleanup_type)
    if target is not None:
        try:
            return as_reading(size_target(target))
        except OSError as exc:  # pragma: no cover - environment dependent
            logger.debug("cleanup size walk for %s failed: %s", cleanup_type, exc)
            return None

    from fpstune.settings.executors.ps_batch import _fetch_cleanup_sizes

    try:
        reading = _fetch_cleanup_sizes((cleanup_type,)).get(cleanup_type, "")
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("cleanup size measurement for %s failed: %s", cleanup_type, exc)
        return None
    return _parse_cleanup_reading(reading) if reading else None


class FreedSpace(NamedTuple):
    """What a run reclaimed, as far as this machine's own instrument saw it.

    Both fields are None wherever there was no pair of readings to compare: a
    setting that cleans nothing, a command that did not run, a target that could
    not be sized. Never a 0 standing in for a missing reading — "we could not
    measure it" and "it freed nothing" are different answers (C11 rule 3).
    """

    freed_bytes: int | None
    size_after_bytes: int | None


NOTHING_MEASURED = FreedSpace(None, None)

# docker_prune and docker_prune_all read the same `docker df` reclaimable, so
# running one changes what the other has to offer. The sibling is dropped rather
# than re-measured: nothing sized it around this command, and a figure nobody
# took is exactly what must not be shown. Its next detect scans.
_DOCKER_SIBLINGS = {
    "cleanup:docker_prune": "cleanup:docker_prune_all",
    "cleanup:docker_prune_all": "cleanup:docker_prune",
}


def _measured_bytes(reading: CleanupSize | None) -> int | None:
    """The byte count in a reading, or None where the reading holds none."""
    if reading is None or reading.status not in ("ready", "not_estimated"):
        return None
    return reading.size_bytes


def freed_after_cleanup(setting: SettingExecutor, before: CleanupSize | None) -> FreedSpace:
    """Size the target again and report the difference from `before`.

    Called immediately after the command returns success, with the reading taken
    immediately before it started. The after reading is remembered, so the row
    shows what the command left behind without waiting for a background re-scan.

    A difference is reported only where both halves are a size: a subtraction
    with a missing operand is not a measurement, and a target that grew while a
    process wrote into it freed nothing rather than a negative amount.
    """
    after = measure_cleanup_size(setting, remember=True)

    sibling = _DOCKER_SIBLINGS.get(setting.id)
    if sibling:
        from fpstune.settings.cleanup_cache import cleanup_size_cache

        cleanup_size_cache.invalidate(sibling)

    # `not_estimated` counts here and not on the row: its bytes were measured,
    # they are simply not a promise of what the command can free. A pair of them
    # is exactly the measurement a WSL compact has and a pre-estimate has not.
    size_after = _measured_bytes(after)
    size_before = _measured_bytes(before)
    if size_before is None or size_after is None:
        return FreedSpace(None, size_after)
    return FreedSpace(max(0, size_before - size_after), size_after)

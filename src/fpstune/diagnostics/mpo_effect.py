"""Read whether MPO was actually in use, from a PresentMon capture.

The MPO setting can only verify itself by reading back the registry value it
just wrote, which proves the intent landed and nothing about the effect — and
the value that takes effect changes between Windows builds, so intent and effect
genuinely diverge. The one observable that separates them is PresentMon's
``PresentMode``: a swapchain going through the display engine's plane compositor
is reported as "Hardware Composed: Independent Flip", and the same swapchain with
MPO off is reported as a plain composed or independent flip.

This needs a capture from a running game, so it is a diagnostic rather than a
verify step. It answers "did that reboot actually change anything?", which the
registry cannot.

Source for the distinction:
https://forums.guru3d.com/threads/disabling-mpo-multiplane-overlay-in-2025.455222/
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from fpstune.utils.logger import get_logger

logger = get_logger()

# PresentMon reports the plane compositor with this phrase. Matched on the
# normalised string rather than an exact value because the column's spelling has
# changed across PresentMon versions ("Hardware Composed: Independent Flip").
_MPO_MARKER = "hardware composed"

_PRESENT_MODE_COLUMNS = ("PresentMode", "presentMode", "Present Mode")


@dataclass(frozen=True)
class MpoObservation:
    """What a capture says about MPO, including when it says nothing."""

    # None means "the capture could not answer", which is distinct from False.
    mpo_active: bool | None
    frames: int
    modes: dict[str, int]
    note: str

    @property
    def summary(self) -> str:
        if self.mpo_active is None:
            return f"Not observable: {self.note}"
        if self.mpo_active:
            share = self.modes_share(_MPO_MARKER)
            return f"MPO was in use for {share:.0%} of {self.frames} frames"
        return f"MPO was not in use across {self.frames} frames"

    def modes_share(self, needle: str) -> float:
        if not self.frames:
            return 0.0
        hit = sum(n for m, n in self.modes.items() if needle in m.lower())
        return hit / self.frames


def _unreadable(note: str) -> MpoObservation:
    return MpoObservation(mpo_active=None, frames=0, modes={}, note=note)


def read_capture(capture_file: Path) -> MpoObservation:
    """Report MPO usage from one PresentMon CSV.

    Returns an observation whose ``mpo_active`` is None whenever the capture
    cannot answer — no file, no ``PresentMode`` column, or no frames. Reporting
    False for those would repeat the defect this exists to catch: an answer that
    describes fpstune's own assumption rather than the machine.
    """
    if not capture_file.exists():
        return _unreadable(f"no capture at {capture_file}")

    modes: Counter[str] = Counter()
    try:
        with open(capture_file, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            column = next(
                (c for c in _PRESENT_MODE_COLUMNS if reader.fieldnames and c in reader.fieldnames),
                None,
            )
            if column is None:
                return _unreadable(
                    "capture has no PresentMode column (PresentMon was run without it)"
                )
            for row in reader:
                value = (row.get(column) or "").strip()
                if value:
                    modes[value] += 1
    except OSError as exc:
        return _unreadable(f"capture unreadable: {exc}")

    frames = sum(modes.values())
    if not frames:
        return _unreadable("capture contains no frames")

    active = any(_MPO_MARKER in mode.lower() for mode in modes)
    return MpoObservation(
        mpo_active=active,
        frames=frames,
        modes=dict(modes),
        note="read from PresentMode",
    )


def read_latest(captures_dir: Path) -> MpoObservation:
    """Report MPO usage from the most recent capture in a directory."""
    if not captures_dir.is_dir():
        return _unreadable(f"no captures directory at {captures_dir}")
    captures = sorted(captures_dir.glob("*.csv"), reverse=True)
    if not captures:
        return _unreadable("no captures recorded yet — run a benchmark while in a match")
    return read_capture(captures[0])

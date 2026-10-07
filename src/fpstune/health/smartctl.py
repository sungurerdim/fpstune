"""SATA SSDs and hard drives: temperature and the operating limit the drive specifies.

Windows exposes no in-box API for an ATA drive's SMART data that an unprivileged
process can reach, and fpstune will not write a SATA pass-through of its own: this
reads smartmontools' `smartctl.exe`, which uses Windows' own ATA pass-through (no
kernel driver) and is GPL-2.0, so it is only ever run as a separate program and never
linked or bundled.

**It runs only if it is already on the machine.** Looked for where fpstune would keep a
tool it downloaded (`~/.fpstune/tools/smartmontools/bin`) and where smartmontools'
own installer puts it (`%PROGRAMFILES%\\smartmontools\\bin`). There is no
download here: fpstune's one downloader (`gpu_scene`) is a hash-checked, resumable,
installer-driving mechanism, which is a unit of its own. Until then a machine with SATA
drives and no smartctl gets a gap that says exactly that, and an NVMe-only machine like
this one never needs it.

**The limit is the drive's specified maximum operating temperature** — the SCT status
`Specified Max Operating Temperature`, which `smartctl -j -l scttempsts` publishes as
`temperature.op_limit_max` (read from `smartmontools/ataprint.cpp`: emitted only when
the drive reports a value greater than zero). A drive that does not report one is not
judged: attribute 194's threshold is a normalised score, not a temperature, and is
never used as one.

smartctl needs administrator on Windows; without it the drives are named as unread and
no temperature is guessed. Its exit status is a bit mask that is non-zero for a
healthy drive with an old error in its log, so it is not what decides whether the JSON
is used — the JSON is.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path

from fpstune.health.inventory import Disk
from fpstune.health.model import Gap
from fpstune.health.thermal import ThermalReading, ThermalSnapshot
from fpstune.utils import process_watch
from fpstune.utils.admin import is_admin
from fpstune.utils.config import get_config_dir
from fpstune.utils.logger import get_logger

logger = get_logger()

SOURCE = "smartctl"
ATA_BUSES = frozenset({"SATA", "ATA"})
"""Bus types whose drives answer through the ATA SMART path this reads."""

NOT_INSTALLED = (
    "SATA drives are present but smartctl (smartmontools) is not installed, so their "
    "temperature and operating limit cannot be read"
)
NEEDS_ADMIN = "needs administrator: smartctl cannot open a physical drive without it"
UNREADABLE = "smartctl did not return a temperature for this drive"

Runner = Callable[[Path, str], dict[str, object] | None]


def candidates() -> list[Path]:
    """Where a smartctl that is already here would be."""
    found = [get_config_dir() / "tools" / "smartmontools" / "bin" / "smartctl.exe"]
    program_files = os.environ.get("PROGRAMFILES")
    if program_files:
        found.append(Path(program_files) / "smartmontools" / "bin" / "smartctl.exe")
    return found


def find(paths: Iterable[Path] | None = None) -> Path | None:
    return next((p for p in (candidates() if paths is None else paths) if p.is_file()), None)


def device_name(disk_number: int) -> str | None:
    """smartctl's name for `\\\\.\\PhysicalDriveN`: `/dev/sda` is drive 0, `/dev/sdb` drive 1."""
    return f"/dev/sd{chr(ord('a') + disk_number)}" if 0 <= disk_number < 26 else None


def run_smartctl(exe: Path, device: str) -> dict[str, object] | None:
    """`smartctl -j -A -l scttempsts <device>` parsed, or None if nothing parseable came back."""
    try:
        result = process_watch.run(
            [str(exe), "-j", "-A", "-l", "scttempsts", device], process_watch.QUERY
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("smartctl failed on %s: %s", device, exc)
        return None
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def reading_from(disk: Disk, document: dict[str, object]) -> ThermalReading | None:
    """A reading from one drive's smartctl JSON, or None when it carried no temperature."""
    temperature = document.get("temperature")
    if not isinstance(temperature, dict):
        return None
    current = _number(temperature.get("current"))
    if current is None:
        return None
    limit = _number(temperature.get("op_limit_max"))
    return ThermalReading(
        component="storage",
        device_id=disk.unique_id or None,
        name=disk.name,
        temperature_c=current,
        limit_c=limit if limit and limit > 0 else None,
        limit_source="SCT specified maximum operating temperature",
        source=SOURCE,
    )


def read(
    disks: Iterable[Disk],
    *,
    exe: Path | None = None,
    run: Runner = run_smartctl,
    admin: bool | None = None,
) -> ThermalSnapshot:
    """Each SATA drive's temperature against the maximum operating temperature it specifies."""
    ata = [d for d in disks if d.bus_type in ATA_BUSES]
    if not ata:
        return ThermalSnapshot()
    program = exe if exe is not None else find()
    if program is None:
        return ThermalSnapshot(gaps=(Gap(SOURCE, NOT_INSTALLED),))
    if not (is_admin() if admin is None else admin):
        return ThermalSnapshot(gaps=(Gap(SOURCE, NEEDS_ADMIN),))

    readings = []
    gaps = []
    for disk in ata:
        device = device_name(disk.number)
        document = run(program, device) if device else None
        reading = reading_from(disk, document) if document else None
        if reading is None:
            gaps.append(Gap(SOURCE, f"{disk.name or 'A SATA drive'}: {UNREADABLE}"))
        else:
            readings.append(reading)
    return ThermalSnapshot(readings=tuple(readings), gaps=tuple(gaps))

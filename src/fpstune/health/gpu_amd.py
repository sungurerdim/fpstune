"""AMD: why a Radeon's heat is not judged, said plainly.

AMD's user-mode library for this, ADLX (`amdadlx64.dll`, installed with Adrenalin), reads a
GPU's temperature and hotspot temperature. What it does not publish is a **limit**
to read them against: the only temperature bounds in the interfaces fpstune would use
(`IADLXGPUMetricsSupport::GetGPUTemperatureRange`, `GetGPUHotspotTemperatureRange`) are
documented as the minimum and maximum the metric *reports* ("read only"), and the
manual fan tuning interface's temperature range is the span of a fan curve — neither
is a point at which the card slows itself down. Reading the temperature and then
inventing the limit from the maximum would be exactly the guessed `TjMax` this package
refuses (C11 rule 3), so for an AMD adapter the reader reports the gap and reads
nothing.

That is also the decision about the binding itself. ADLX is a table of function
pointers reached through COM-style interfaces; a ctypes binding to it is a few dozen
slot offsets that cannot be checked here (no AMD hardware or driver on the development
machine), and a wrong slot calls the wrong driver function. A binding that can only
produce a temperature fpstune then may not judge is risk with no finding at the end of
it. It becomes worth writing the day ADLX documents a throttle threshold.

Only an adapter that is actually present is reported (C10: a question that does not
apply is not a gap), so this reader runs for machines with an AMD adapter and says
nothing on the rest.
"""

from __future__ import annotations

import os
import sys

from fpstune.health.model import Gap
from fpstune.health.thermal import ThermalSnapshot

SOURCE = "amd_adlx"
LIBRARY = "amdadlx64.dll"

NO_LIBRARY = (
    "an AMD adapter is present but AMD's ADLX library (amdadlx64.dll) is not installed, "
    "so its temperature cannot be read"
)
NO_PUBLISHED_LIMIT = (
    "AMD's ADLX library reports a GPU's temperature but publishes no throttle limit to "
    "judge it against (its temperature ranges are what the sensor can report, not where "
    "the card slows down), so an AMD GPU's heat is not assessed and no limit is guessed"
)


def _installed() -> bool:
    if sys.platform != "win32":
        return False
    from fpstune.utils.system_tools import system32

    return os.path.isfile(os.path.join(system32(), LIBRARY))


def read(installed: bool | None = None) -> ThermalSnapshot:
    """The gap for an AMD adapter: which of the two reasons applies to this machine."""
    present = _installed() if installed is None else installed
    return ThermalSnapshot(gaps=(Gap(SOURCE, NO_PUBLISHED_LIMIT if present else NO_LIBRARY),))

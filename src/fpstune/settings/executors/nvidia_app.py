"""What the NVIDIA App itself says about the frame caps it can impose.

Two of its features exist purely to cap frame rate on a portable machine:
Battery Boost, which holds a game near 30 fps on battery, and Whisper Mode,
which holds it between 40 and 60 for quiet running. Both are consequence-3
cases — a ceiling the player did not ask for — and nothing shipped could see
either one.

The App writes its Battery Boost criteria to a file under its own backend
directory, and this reads that file rather than inferring anything from the
machine being a laptop. Read on this machine on 2026-08-23, the whole file is:

    {"criteria": {
        "overallState": false,
        "featureTile": "BatteryBoost2.0",
        "header": "Battery Boost 2.0",
        "message": "...",
        "states": [
            {"name": "gpu",      "message": "RTX laptop GPU, 3050 or above", "state": true},
            {"name": "os",       "message": "Windows 10 or above",           "state": true},
            {"name": "drvrVrsn", "message": "GeForce 510.59 driver or above","state": true},
            {"name": "bb2",      "message": "supported per nvAPI and JPAC platform",
                                 "state": false}
        ]}}

Two things follow, and the first cost a wrong answer before the file was read.
``bb2`` is an entry in ``states``, not a key — looking it up as a key finds
nothing, and falling back to ``overallState`` then reported "the user has it
switched off" for a machine that cannot run the feature at all. And
``overallState`` is the AND of those criteria: it says whether the cap is
*possible* here, never whether it is currently on.

So this module answers supportability and stops there. The on/off toggle lives
in the NVIDIA App's UI; the whole NvBackend directory was searched on
2026-08-23 and nothing in it records the state. Reporting supportability as
though it were the state is precisely the failure the sentinel contract exists
to prevent, so it is not done.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from fpstune.settings.applicability import NOT_AVAILABLE

logger = logging.getLogger(__name__)

_RELATIVE_PATH = Path("NVIDIA Corporation/NVIDIA App/NvBackend/batteryboost2.json")

CAP_POSSIBLE = "cap_possible"
"""Every criterion passes, so this machine can hold a game at ~30 fps on battery."""

NO_CAP_POSSIBLE = "no_cap_possible"
"""At least one criterion fails, so the feature is inert here whatever its toggle says."""

# Read once per process. The file changes when the App re-evaluates its
# criteria — a driver update, not a per-request event — so re-reading it on
# every detect would put a file open on the scan's critical path for no new
# information.
_cache: dict[str, Any] | None = None
_cache_loaded = False


def _config_path() -> Path | None:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None
    return Path(local_appdata) / _RELATIVE_PATH


def _load() -> dict[str, Any] | None:
    path = _config_path()
    if path is None or not path.is_file():
        return None
    try:
        # utf-8-sig: the App writes this file with a BOM often enough that a
        # plain utf-8 read is a coin flip, and a decode error here would read
        # as "no NVIDIA App" on a machine that has one.
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        # A file written in a shape this does not understand is an absence, not
        # a state. Answering "off" here would tell a user with the cap in force
        # that they do not have it.
        logger.debug("battery boost criteria unreadable at %s: %s", path, exc)
        return None
    return parsed if isinstance(parsed, dict) else None


def _snapshot() -> dict[str, Any] | None:
    global _cache, _cache_loaded
    if not _cache_loaded:
        _cache = _load()
        _cache_loaded = True
    return _cache


def reset_cache() -> None:
    """Forget the cached read. For tests, and after the App rewrites the file."""
    global _cache, _cache_loaded
    _cache = None
    _cache_loaded = False


def _criteria(data: dict[str, Any]) -> dict[str, Any]:
    criteria = data.get("criteria")
    return criteria if isinstance(criteria, dict) else data


def unmet_criteria() -> list[str]:
    """The App's own names for the criteria this machine fails.

    Its messages are localised — the file read here was written in Turkish on an
    English-language product — so the stable half is the name, and that is what
    is returned. `["bb2"]` on this machine.
    """
    data = _snapshot()
    if data is None:
        return []
    states = _criteria(data).get("states")
    if not isinstance(states, list):
        return []
    return [
        str(entry.get("name"))
        for entry in states
        if isinstance(entry, dict) and entry.get("state") is False and entry.get("name")
    ]


def battery_boost_exposure() -> str:
    """Whether this machine can impose NVIDIA's battery frame cap at all.

    Deliberately *not* whether it currently is — see the module docstring. This
    is a condition to report, in the same shape as the fan-curve advisory, and
    it has three answers:

    ``cap_possible``     every criterion passes, so the cap is one toggle away
                         in the NVIDIA App and worth telling the user about.
    ``no_cap_possible``  at least one criterion fails, so the feature is inert
                         here however its toggle is set. The answer on the
                         machine this was written against, where ``bb2`` — the
                         platform criterion — is false.
    ``not_available``    no criteria file, so nothing is known. Not the same as
                         "no cap", and never reported as it.
    """
    data = _snapshot()
    if data is None:
        return NOT_AVAILABLE

    overall = _criteria(data).get("overallState")
    if not isinstance(overall, bool):
        return NOT_AVAILABLE
    return CAP_POSSIBLE if overall else NO_CAP_POSSIBLE

"""P-SSOT and P-DRY, run rather than promised.

CLAUDE.md's key invariants name a set of concepts that must have exactly one
home: one comparison truth, one absence sentinel set, one user-path resolver,
one registry, one console, one scheduling planner. Those sentences are worth
nothing the first time a second copy lands somewhere else, because the copy
does not announce itself — it just drifts.

This file is the binding for the named list. ``.jscpd.json`` (wired through
``scripts/quality.sh``) is the general copy detector with a percentage
threshold; it cannot express "there is exactly one ``values_equal``", because a
second definition small enough to stay under the threshold is still two homes.
The two checks are deliberately different shapes, not duplicates.

Every entry is a claim that can go stale, so the table is checked in both
directions: a concept whose home moved fails, and a home that no longer matches
its pattern fails. That is the catalogue's "kaçınılmaz kopyanın kayma testi"
(the drift test on an unavoidable copy) applied to the copies this project has
decided it will keep exactly one of.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "fpstune"

# concept -> (owning module relative to src/fpstune, definition pattern)
#
# Only concepts the project has already declared single-homed in CLAUDE.md's key
# invariants are listed. Adding a row here is a decision that a second copy is a
# bug, not a style preference (P-RULE3: three real repetitions earn an
# abstraction; this table is for the ones the project has already made).
SINGLE_SOURCES: dict[str, tuple[str, str]] = {
    "values_equal": ("settings/applicability.py", r"^def values_equal\("),
    "is_absent_reading": ("settings/applicability.py", r"^def is_absent_reading\("),
    "ABSENT_READINGS": ("settings/applicability.py", r"^ABSENT_READINGS\s*:"),
    "hardware_manager": (
        "utils/hardware_manager.py",
        r"^hardware_manager\s*=\s*HardwareManager\(\)",
    ),
    "console": ("utils/console.py", r"^console\s*=\s*_make_console\(\)"),
    "get_registry": ("settings/registry_cache.py", r"^def get_registry\("),
    "get_all_static_settings": (
        "settings/definitions/__init__.py",
        r"^def get_all_static_settings\(",
    ),
    "plan_lanes": ("settings/bulk_plan.py", r"^def plan_lanes[\[(]"),
    "build_hardware_context": ("settings/hardware_context.py", r"^def build_hardware_context\("),
    "frame_cap_for_refresh": ("settings/performance_headroom.py", r"^def frame_cap_for_refresh\("),
    "record_headroom_band": ("benchmark/scheduler.py", r"^def record_headroom_band\("),
}

# Root names a shipped module may not read directly: `utils/user_paths.py` is the
# one resolver (C9). Reading the environment variable elsewhere is how a second,
# subtly different home appears — the #104 sweep wrote the real profile because
# one writer bypassed the resolver.
_PROFILE_ROOTS = ("USERPROFILE", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA")
_PROFILE_READ = re.compile(
    r"os\.environ(?:\.get)?\(\s*[\"'](?:" + "|".join(_PROFILE_ROOTS) + r")[\"']"
    r"|os\.environ\[\s*[\"'](?:" + "|".join(_PROFILE_ROOTS) + r")[\"']"
)

# `__pycache__` holds compiled copies of modules this table has already checked.
_SKIP_PARTS = {"__pycache__"}


def _modules() -> list[Path]:
    return [
        path
        for path in SRC.rglob("*.py")
        if not _SKIP_PARTS.intersection(path.relative_to(SRC).parts)
    ]


def _relative(path: Path) -> str:
    return path.relative_to(SRC).as_posix()


def _definitions(pattern: str) -> list[str]:
    """Modules whose text matches ``pattern`` at the start of a line."""
    matcher = re.compile(pattern, re.MULTILINE)
    return sorted(_relative(path) for path in _modules() if matcher.search(path.read_text("utf-8")))


def test_each_named_concept_has_exactly_one_home() -> None:
    """A second definition of a single-source concept is the drift this forbids."""
    duplicated = {
        concept: homes
        for concept, (_owner, pattern) in SINGLE_SOURCES.items()
        if len(homes := _definitions(pattern)) > 1
    }

    assert not duplicated, (
        "these concepts are declared single-homed in CLAUDE.md but have more than "
        f"one definition: {duplicated}"
    )


def test_each_named_concept_lives_where_the_table_says() -> None:
    """The table is a claim; a moved home must move the table with it."""
    stale = {
        concept: (owner, homes)
        for concept, (owner, pattern) in SINGLE_SOURCES.items()
        if (homes := _definitions(pattern)) != [owner]
    }

    assert not stale, (
        "SINGLE_SOURCES no longer matches the tree (concept: (declared owner, "
        f"observed homes)): {stale}"
    )


def test_the_user_profile_is_read_only_through_the_one_resolver() -> None:
    """C9's resolver is the only place a profile root is read from the environment."""
    offenders = [
        f"{_relative(path)}:{line_number}: {line.strip()}"
        for path in _modules()
        for line_number, line in enumerate(path.read_text("utf-8").splitlines(), start=1)
        if _PROFILE_READ.search(line) and _relative(path) != "utils/user_paths.py"
    ]

    assert not offenders, (
        "a shipped module reads a user-profile root directly instead of asking "
        "utils/user_paths.py: " + ", ".join(offenders)
    )

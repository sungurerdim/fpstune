"""Per-module coverage floors for the modules where a missed branch is dangerous (P-RISKTEST).

The catalogue's P-RISKTEST says test effort follows risk, and P-MUTATION's
violation example is the pair that makes this gate necessary: "%95 coverage,
mutation score %20". A repository-wide `fail_under` cannot see that shape — the
generated definitions modules carry thousands of statements and cover themselves
by existing, so a critical pure module can lose half its branches while the
total stays above the floor.

    uv run --extra dev pytest --cov=src/fpstune --cov-report=json:coverage.json
    python scripts/risk_coverage.py --json coverage.json

The floors are measured, not chosen. They were taken on 2026-10-25 from a full
`pytest -n 8` run of this suite (the same command `scripts/quality.sh` runs),
each floor set five points under what the module actually reached, so ordinary
work has room and a module that stops being exercised lands under its floor.
Raise a floor when a module's coverage improves; never lower one to make a change
pass — the module is on this list because a wrong branch in it can restore a
setting the user did not ask for, delete the wrong file, or report a measurement
nobody took.

This reads a coverage report and prints; it never runs the suite and never
rewrites the report.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Repo-relative POSIX paths, exactly as coverage.py writes them from the repo
# root. The floor is the minimum `percent_covered` the module may report, and the
# comment beside each one is the measurement it came from.
FLOORS: dict[str, float] = {
    # measured 91.54 on 2026-10-26 (full suite, Windows); the earlier 58.09 was a
    # slice where the Windows-only detection paths did not run. Raised with the
    # branch/message tests that also took the mutation score from 50% to 87%.
    "src/fpstune/settings/applicability.py": 85.0,
    # measured 100.00 — pure planning, one test file, no host dependency.
    "src/fpstune/settings/bulk_plan.py": 95.0,
    # measured 96.43 — the registry is the SSOT; a lost setting disappears from
    # every surface.
    "src/fpstune/settings/registry.py": 90.0,
    # measured 84.11 — the restore point is what makes a reset recoverable.
    "src/fpstune/safety/restore.py": 80.0,
    # measured 82.98 — the one mutex an apply, a cleanup and a bench share.
    "src/fpstune/benchmark/operation_lock.py": 78.0,
    # measured 98.94 — the one comparison path a claim is judged by (C11 rule 2).
    "src/fpstune/benchmark/verify_round.py": 90.0,
    # measured 92.73 — every write into the user's profile resolves a root here (C9).
    "src/fpstune/utils/user_paths.py": 88.0,
    # measured 88.43 — the cleanup targets delete files; a wrong root deletes the
    # wrong ones.
    "src/fpstune/settings/cleanup_targets.py": 83.0,
    # measured 91.03 — one Name@scope line rewrite shared by two games; a wrong
    # byte is data loss.
    "src/fpstune/settings/executors/game_config_writer.py": 86.0,
    # measured 100.00 — the one place a setting's command runs for apply and
    # reset (C6).
    "src/fpstune/api/routes/settings_apply.py": 95.0,
}


@dataclass(frozen=True)
class ModuleCoverage:
    """One module's measured coverage, as coverage.py reported it."""

    path: str
    percent: float
    covered: int
    statements: int


def _percent(summary: dict[str, object], path: str) -> ModuleCoverage:
    percent = summary.get("percent_covered")
    covered = summary.get("covered_lines")
    statements = summary.get("num_statements")
    if (
        not isinstance(percent, int | float)
        or not isinstance(covered, int)
        or not isinstance(statements, int)
    ):
        raise ValueError(f"{path}: the report's summary is missing percent_covered/covered_lines")
    return ModuleCoverage(path=path, percent=float(percent), covered=covered, statements=statements)


def _normalise(path: str) -> str:
    """A report path as repo-relative POSIX, however coverage.py spelled it."""
    normal = path.replace("\\", "/")
    if Path(normal).is_absolute():
        try:
            return Path(normal).resolve().relative_to(ROOT).as_posix()
        except ValueError:
            return normal
    return normal.removeprefix("./")


def load_report(path: Path) -> dict[str, ModuleCoverage]:
    """Parse a `coverage json` report into per-module coverage."""
    data = json.loads(path.read_text(encoding="utf-8"))
    files = data.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"{path}: not a coverage JSON report (no 'files' object)")
    measured: dict[str, ModuleCoverage] = {}
    for raw_path, entry in files.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("summary"), dict):
            continue
        measured[_normalise(raw_path)] = _percent(entry["summary"], _normalise(raw_path))
    return measured


def evaluate(measured: dict[str, ModuleCoverage], floors: dict[str, float] = FLOORS) -> list[str]:
    """Every floor the report misses, plus every floor module the report never measured."""
    problems: list[str] = []
    for module, floor in sorted(floors.items()):
        coverage = measured.get(module)
        if coverage is None:
            problems.append(
                f"{module}: not in the coverage report (floor {floor:.0f}%) — "
                "either it was not measured, or the module moved and the floor is stale"
            )
        elif coverage.percent < floor:
            problems.append(
                f"{module}: {coverage.percent:.1f}% < floor {floor:.0f}% "
                f"({coverage.covered}/{coverage.statements} statements)"
            )
    return problems


def report(measured: dict[str, ModuleCoverage], floors: dict[str, float] = FLOORS) -> str:
    """The floors, the measured numbers and which side of each one the module is on."""
    lines = ["risk coverage: module, floor, measured"]
    for module, floor in sorted(floors.items()):
        coverage = measured.get(module)
        if coverage is None:
            lines.append(f"  {module:<58} {floor:>5.0f}%  not measured")
            continue
        verdict = "ok" if coverage.percent >= floor else "UNDER"
        lines.append(f"  {module:<58} {floor:>5.0f}%  {coverage.percent:>6.1f}%  {verdict}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--json",
        type=Path,
        default=ROOT / "coverage.json",
        help="a `coverage json` report (default: coverage.json at the repo root)",
    )
    args = parser.parse_args(argv)

    try:
        measured = load_report(args.json)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"risk coverage: could not read {args.json}: {exc}", file=sys.stderr)
        return 2

    problems = evaluate(measured)
    print(report(measured))
    if problems:
        print("risk coverage: RED", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"risk coverage: green — {len(FLOORS)} critical module(s) at or above their floor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

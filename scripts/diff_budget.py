"""A budget for the size of a change, so a small fix stays reviewable (P-SMALLBATCH, P-BOYSCOUT).

The catalogue's P-SMALLBATCH asks for small, single-purpose changes and its
violation example is a three-week branch; P-BOYSCOUT adds that out-of-scope
cleanup belongs in its own task, not in the diff that fixes a bug. Both need a
number, or they are advice. This script is that number: it counts the files a
change touches and the lines it adds and deletes, prints them, and fails when
either passes its budget.

    python scripts/diff_budget.py                  the uncommitted diff against HEAD
    python scripts/diff_budget.py --staged         what lefthook would commit
    python scripts/diff_budget.py --base origin/main   a whole branch, from its merge base
    python scripts/diff_budget.py --max-files 5 --max-lines 200

The defaults are measured from this repository's own history, not chosen:

    git log --numstat --format=@@@%H -60     (2026-10-25, 60 commits)
    files per commit: median 6, p75 9, p90 23
    lines per commit: median 149, p75 562, p90 2867

The default budget is 12 files and 800 lines — the p75 commit plus a little
headroom. A p90 budget would have passed the 20-file / 2,867-line commit, which
is the shape this rule exists to refuse; the median commit passes with room to
spare, so the budget only ever fires on the multi-purpose tail.

Generated files are exempt. `uv.lock` and `frontend/package-lock.json` together
account for most of this repository's largest diffs, and their line count
describes a tool's output rather than the scope of the change; charging them to
the author would make every dependency bump fail a budget that is about review.

It reads git and prints; it never stages, resets or rewrites anything.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_MAX_FILES = 12
DEFAULT_MAX_LINES = 800

# Paths whose size says nothing about the change. Lockfiles are generated from
# a manifest that is itself a few lines; a minified bundle is a build artifact.
EXEMPT_SUFFIXES = (".lock", ".min.js", ".min.css")
EXEMPT_NAMES = frozenset({"uv.lock", "package-lock.json", "poetry.lock", "Pipfile.lock"})
EXEMPT_PREFIXES = ("frontend/dist/", "dist/", "htmlcov/", "node_modules/")


@dataclass(frozen=True)
class FileChange:
    """One line of `git diff --numstat`: what happened to one file."""

    path: str
    added: int
    deleted: int

    @property
    def lines(self) -> int:
        return self.added + self.deleted


@dataclass(frozen=True)
class DiffStat:
    """The diff's size, and the per-file detail behind it."""

    changes: tuple[FileChange, ...]

    @property
    def files(self) -> int:
        return len(self.changes)

    @property
    def lines(self) -> int:
        return sum(change.lines for change in self.changes)

    def largest(self, limit: int = 5) -> list[FileChange]:
        return sorted(self.changes, key=lambda change: change.lines, reverse=True)[:limit]


def is_generated(path: str) -> bool:
    """True for a path whose line count is a tool's output, not the author's work."""
    normal = path.replace("\\", "/")
    name = normal.rsplit("/", 1)[-1]
    return (
        name in EXEMPT_NAMES
        or name.endswith(EXEMPT_SUFFIXES)
        or any(normal.startswith(prefix) for prefix in EXEMPT_PREFIXES)
    )


def parse_numstat(text: str) -> DiffStat:
    """Turn `git diff --numstat` into a diff size.

    A binary file answers `-` for both counts; it is still a file changed, so it
    is counted as a file with zero lines. A rename can carry its path as
    ``old => new``; the new path is the one a reviewer opens, so that is kept.
    """
    changes: list[FileChange] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, path = parts[0], parts[1], "\t".join(parts[2:])
        path = path.split(" => ")[-1]
        if is_generated(path):
            continue
        changes.append(
            FileChange(
                path=path,
                added=0 if added == "-" else int(added),
                deleted=0 if deleted == "-" else int(deleted),
            )
        )
    return DiffStat(tuple(changes))


def diff_command(staged: bool, base: str | None) -> list[str]:
    """The git invocation a mode means. `...` compares from the merge base."""
    if staged:
        return ["git", "diff", "--cached", "--numstat"]
    if base:
        return ["git", "diff", "--numstat", f"{base}...HEAD"]
    return ["git", "diff", "--numstat", "HEAD"]


def read_diff(staged: bool, base: str | None, root: Path = ROOT) -> DiffStat:
    """Run git for the requested comparison; a git failure is the caller's to report."""
    result = subprocess.run(
        diff_command(staged, base),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return parse_numstat(result.stdout)


def evaluate(diff: DiffStat, max_files: int, max_lines: int) -> list[str]:
    """Every budget line the diff crossed, as sentences. Empty means inside budget."""
    problems: list[str] = []
    if diff.files > max_files:
        problems.append(f"{diff.files} files changed (budget {max_files})")
    if diff.lines > max_lines:
        problems.append(f"{diff.lines} lines added+deleted (budget {max_lines})")
    return problems


def report(diff: DiffStat, max_files: int, max_lines: int, problems: list[str]) -> str:
    """The diff's size, the budget and the files that used it, for a human."""
    lines = [
        f"diff budget: {diff.files} file(s), {diff.lines} line(s) "
        f"(budget {max_files} file(s) / {max_lines} line(s))"
    ]
    for change in diff.largest():
        lines.append(f"  +{change.added:>4} -{change.deleted:<4} {change.path}")
    if problems:
        lines.append("diff budget: RED — " + "; ".join(problems))
        lines.append(
            "  Split the change: one purpose per commit, and send out-of-scope cleanup "
            "to its own task (P-BOYSCOUT). Generated files are already exempt."
        )
    else:
        lines.append("diff budget: green")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--staged", action="store_true", help="the staged diff, for pre-commit")
    parser.add_argument("--base", metavar="REF", help="compare a branch from its merge base")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    args = parser.parse_args(argv)

    if args.staged and args.base:
        parser.error("--staged and --base describe different diffs; pick one")

    try:
        diff = read_diff(args.staged, args.base)
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        print(f"diff budget: could not read the diff: {exc}", file=sys.stderr)
        return 2

    problems = evaluate(diff, args.max_files, args.max_lines)
    print(report(diff, args.max_files, args.max_lines, problems))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

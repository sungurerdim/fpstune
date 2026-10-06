"""Select the tests a change can break, so its own check sees the red.

In #104 every unit ran only its own tests, and `tests/test_windows_contract/*`
(real PowerShell contract tests over `definitions/network.py` and `system.py`)
was first seen red in the last full gate: 11 failures the unit that touched
those files could have caught. This selector maps changed files to the tests
that depend on them, deterministically — AST and text search, no model.

    python scripts/affected_tests.py --base HEAD~3          what a branch touched
    python scripts/affected_tests.py --base origin/main --run
    python scripts/affected_tests.py --staged --run         what lefthook runs

A changed file selects a test when:

* the test imports the file's module (`import a.b`, `from a import b`,
  relative imports resolved), found by AST over `tests/`;
* the test's text names the module dotted (`fpstune.settings.definitions.network`),
  the file's repo path, or the file name (`network.py`);
* the test's text names a setting id the changed file defines (an `id="x:y"`
  keyword, found by AST), quoted or not;
* the test file itself changed;
* a `conftest.py` changed: every test beneath its directory.

Every selected test prints with the reason; an empty selection prints
"nothing selected" — a skipped test is never silent. This narrows the commit
check only; the full gate stays on pre-push (`scripts/quality.sh`).
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

TESTS_DIR = "tests"
SRC_DIR = "src"
# File names that exist in every package or directory: matching them by name
# would select tests for reasons that say nothing about the change.
NAME_TOO_COMMON = frozenset({"__init__.py", "conftest.py", "__main__.py"})


@dataclass(frozen=True)
class TestSource:
    """One test file, read once: its text and the modules its AST imports."""

    # Not a test class, whatever pytest's collection heuristic thinks of the name.
    __test__ = False

    path: str
    text: str
    imports: frozenset[str]


def parse(text: str) -> ast.AST:
    """`ast.parse` without the compiler's warnings: a selector reads, it does not lint."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ast.parse(text)


def dotted_name(path: str) -> str:
    """The module a repo-relative path imports as: `src/` is the import root."""
    parts = path.removesuffix(".py").split("/")
    if parts[0] == SRC_DIR:
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def imported_modules(tree: ast.AST, own_module: str, is_package: bool) -> frozenset[str]:
    """Every module an import statement in `tree` can name, relative ones resolved."""
    found: set[str] = set()
    package = own_module if is_package else own_module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.split(".") if package else []
                anchor = anchor[: len(anchor) - (node.level - 1)] if node.level > 1 else anchor
                base = ".".join([*anchor, *([base] if base else [])])
            if base:
                found.add(base)
            # `from pkg import mod` imports the module `pkg.mod` too.
            found.update(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
    return frozenset(found)


def load_tests(root: Path) -> list[TestSource]:
    tests: list[TestSource] = []
    tests_root = root / TESTS_DIR
    if not tests_root.is_dir():
        return tests
    for file in sorted(tests_root.rglob("test_*.py")):
        rel = file.relative_to(root).as_posix()
        text = file.read_text(encoding="utf-8", errors="replace")
        try:
            tree = parse(text)
        except SyntaxError:
            # Unparseable is not unrelated: keep it selectable by text.
            imports: frozenset[str] = frozenset()
        else:
            imports = imported_modules(tree, dotted_name(rel), is_package=False)
        tests.append(TestSource(rel, text, imports))
    return tests


def setting_ids(source: str) -> list[str]:
    """Literal `id="ns:name"` keyword values — the setting ids a file defines."""
    try:
        tree = parse(source)
    except SyntaxError:
        return []
    ids = {
        kw.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "id"
        and isinstance(kw.value, ast.Constant)
        and isinstance(kw.value.value, str)
        and ":" in kw.value.value
    }
    return sorted(ids)


def _word_regex(literals: list[str], *, trailing: str) -> re.Pattern[str] | None:
    if not literals:
        return None
    body = "|".join(re.escape(item) for item in sorted(literals, key=len, reverse=True))
    return re.compile(rf"(?<![\w.:/-])(?:{body}){trailing}")


def select(root: Path, changed: list[str]) -> dict[str, list[str]]:
    """Map each affected test path to the reasons it was selected."""
    tests = load_tests(root)
    reasons: dict[str, list[str]] = defaultdict(list)

    def add(test: str, reason: str) -> None:
        if reason not in reasons[test]:
            reasons[test].append(reason)

    existing_tests = {t.path for t in tests}
    for path in sorted(set(changed)):
        if not path.endswith(".py"):
            continue
        name = path.rsplit("/", 1)[-1]
        if path in existing_tests:
            add(path, f"{path} changed itself")
        if name == "conftest.py":
            directory = path.rsplit("/", 1)[0] + "/" if "/" in path else ""
            for test in tests:
                if test.path.startswith(directory):
                    add(
                        test.path,
                        f"{path} changed: fixtures for everything beneath {directory or './'}",
                    )

        module = dotted_name(path)
        is_package = name == "__init__.py"
        # A package matches only as the whole name: `pkg.sub.mod` must not
        # select a test for every module of `pkg` just because `pkg` changed.
        dotted_tail = r"(?![\w.])" if is_package else r"(?!\w)"
        dotted = _word_regex([module], trailing=dotted_tail) if module else None
        by_path = _word_regex([path, path.removeprefix(SRC_DIR + "/")], trailing=r"(?!\w)")
        by_name = None if name in NAME_TOO_COMMON else _word_regex([name], trailing=r"(?!\w)")
        file = root / path
        ids = (
            setting_ids(file.read_text(encoding="utf-8", errors="replace"))
            if file.is_file() and not path.startswith(TESTS_DIR + "/")
            else []
        )
        by_id = _word_regex(ids, trailing=r"(?![\w])")

        for test in tests:
            if module and module in test.imports:
                add(test.path, f"imports {module} ({path})")
            if dotted and (hit := dotted.search(test.text)):
                add(test.path, f"names module {hit.group(0)} ({path})")
            if by_path and (hit := by_path.search(test.text)):
                add(test.path, f"names path {hit.group(0)}")
            elif by_name and (hit := by_name.search(test.text)):
                add(test.path, f"names file {hit.group(0)} ({path})")
            if by_id and (hit := by_id.search(test.text)):
                add(test.path, f"names setting id {hit.group(0)} (defined in {path})")
    return dict(sorted(reasons.items()))


def _git(root: Path, *args: str) -> list[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"affected_tests: `git {' '.join(args)}` failed: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line]


def changed_files(root: Path, base: str | None, staged: bool) -> list[str]:
    """Repo paths changed against `base`, or staged; untracked files count when not staged."""
    if staged:
        return _git(root, "diff", "--name-only", "--cached", "--diff-filter=d")
    changed = _git(root, "diff", "--name-only", base or "HEAD", "--")
    return [*changed, *_git(root, "ls-files", "--others", "--exclude-standard")]


def worker_count(selected: int, cores: int | None = None) -> int:
    """Half the measured cores (the other half is the commit's own lint), at most one per file."""
    measured = cores if cores is not None else (os.cpu_count() or 2)
    return max(1, min(measured // 2, selected))


def report(selection: dict[str, list[str]], changed: list[str]) -> None:
    py = [p for p in changed if p.endswith(".py")]
    print(f"affected_tests: {len(changed)} changed file(s), {len(py)} Python")
    if not selection:
        print("affected_tests: nothing selected" + ("" if py else " (no Python file changed)"))
        return
    print(f"affected_tests: {len(selection)} test file(s) selected")
    for test, why in selection.items():
        print(f"  {test}")
        for reason in why:
            print(f"      <- {reason}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Select the tests a change can break.")
    parser.add_argument("--base", help="git ref to diff the working tree against (default HEAD)")
    parser.add_argument(
        "--staged", action="store_true", help="the staged files, as a pre-commit hook sees them"
    )
    parser.add_argument(
        "--files", nargs="+", metavar="PATH", help="explicit repo paths instead of git"
    )
    parser.add_argument("--run", action="store_true", help="run the selected tests with pytest")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)

    root: Path = args.root
    changed = (
        [f.replace("\\", "/") for f in args.files]
        if args.files
        else changed_files(root, args.base, args.staged)
    )
    selection = select(root, changed)
    report(selection, changed)
    if not args.run or not selection:
        return 0

    workers = worker_count(len(selection))
    # The wall-clock marker is the one the full gate runs alone; beside workers it reads late.
    command = ["uv", "run", "pytest", "--no-cov", "-q", "-m", "not timing"]
    if workers > 1:
        command += ["-n", str(workers)]
    command += list(selection)
    print(f"affected_tests: {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=root, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())

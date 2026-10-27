"""One registry of every quality control, and the stage that runs it (P-SSOT, P-SHIFTLEFT).

The repository runs its checks from three files: `lefthook.yml` (pre-commit),
`scripts/quality.sh` (pre-push and the local whole contract) and
`.github/workflows/ci.yml`. Each grew independently, and nothing compared them.
That is the shape the catalogue's P-SHIFTLEFT names: a control that exists in CI
but not at the stage where the author would have seen it has moved the red as far
from its cause as it can go, and a control that quietly disappeared from
`quality.sh` still looks enforced because CI runs it. P-SSOT is the other half —
one place says what the controls are, so the three files cannot disagree about
the list without something failing.

    python scripts/controls.py            print the registry
    python scripts/controls.py --check    fail when the files and the registry disagree

`--check` fails when

* a wired control is missing from the earliest stage that declares it;
* a wired control is declared at a stage whose file does not run it;
* the same control runs twice in one stage (the second copy is a check nobody
  reads, and it makes the stage slower without catching anything new);
* a stage runs a check no control owns, so the registry is not the SSOT;
* a control is marked `proposed` and the stage files already run it (the
  proposal landed: flip it to `wired` so the check starts enforcing it);
* a `manual` control's script is gone.

Stages after the earliest are deliberate: pre-push and CI re-run lint and tests
so a bypassed hook is still caught. The registry records them so the redundancy
is a decision rather than an accident.

`proposed` is the honest state of the gates this change adds: `scripts/diff_budget.py`,
`scripts/risk_coverage.py` and this checker's own `--check` are not wired into the
hooks yet, because `lefthook.yml`, `scripts/quality.sh` and `.github/workflows/ci.yml`
are owned by the Lead. The exact lines to add are in the change report.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Earliest first. `manual` is a human-run gate: no stage file invokes it.
STAGES = ("pre-commit", "pre-push", "ci", "manual")

# The file that owns each stage. `pre-commit` includes lefthook's `commit-msg`
# hook: both fire before the commit exists, and both are read from lefthook.yml.
STAGE_FILES = {
    "pre-commit": "lefthook.yml",
    "pre-push": "scripts/quality.sh",
    "ci": ".github/workflows/ci.yml",
}

# What makes a command a *check* rather than setup. The list is explicit because
# "every command is a control" would flag `cd frontend`, `npm ci` and a pwsh
# one-liner, and an exclusion list long enough to hold those is a worse SSOT than
# a short inclusion list. A command starting with one of these must be owned by a
# control in the registry below.
CHECK_PREFIXES = (
    "uv run --extra dev ruff ",
    "uv run --extra dev mypy ",
    "uv run --extra dev pytest",
    "uv run --extra dev python scripts/",
    "uv run --extra dev python -c",
    "uv run --extra dev lint-imports",
    "uv run --extra dev vulture",
    "uv run --extra dev zizmor",
    "npm run lint",
    "npm run test:run",
    "npm run test:a11y",
    "npm run knip",
    "npm run deps:check",
    "npx tsc",
    "jscpd",
    "gitleaks ",
    # The guard, not the diagnostic line printed after it fails: `npm ls --depth=0
    # 2>&1 | grep ...` in quality.sh explains a red, it does not decide one.
    "npm ls --depth=0 >/dev/null 2>&1",
    "grep -qE '^(feat",
    "bash scripts/",
    "python scripts/",
)

_SCRIPT_PATH = re.compile(r"(scripts/[\w./-]+\.(?:py|sh))")


@dataclass(frozen=True)
class Control:
    """One check, where it runs, and the failure it exists to prevent.

    ``stages`` is ordered as it appears in `STAGES`; ``status`` is ``wired`` when
    a stage file runs it today and ``proposed`` while its wiring is still a change
    the Lead has to make.
    """

    id: str
    command: str
    stages: tuple[str, ...]
    prevents: str
    status: str = "wired"


CONTROLS: tuple[Control, ...] = (
    Control(
        id="py-lint",
        command="ruff check src tests scripts",
        stages=("pre-commit", "pre-push", "ci"),
        prevents="an undefined name, unused import or bugbear violation reaching a reviewer",
    ),
    Control(
        id="py-format",
        command="ruff format --check src tests scripts",
        stages=("pre-commit", "pre-push", "ci"),
        prevents="a formatting diff unrelated to the change landing in the next commit",
    ),
    Control(
        id="py-affected-tests",
        command="python scripts/affected_tests.py --staged --run",
        stages=("pre-commit",),
        prevents="a commit whose own change breaks a contract test it never ran (#104)",
    ),
    Control(
        id="py-types",
        command="mypy src",
        stages=("pre-push", "ci"),
        prevents="a type error in the shipped package reaching a release build",
    ),
    Control(
        id="py-tests",
        command="--cov=src/fpstune",
        stages=("pre-push", "ci"),
        prevents="a behavioural regression reaching a tag or a user",
    ),
    Control(
        id="py-timing-tests",
        command="pytest -q -m timing",
        stages=("pre-push",),
        prevents="the wall-clock contract tests reading late beside parallel workers (the PowerShell stall contract)",
    ),
    Control(
        id="py-interpreter",
        command="import sys, pytest; print",
        stages=("pre-push", "ci"),
        prevents="the gate falling through to a global pytest from PATH (46 collection errors once)",
    ),
    Control(
        id="fe-lint",
        command="npm run lint",
        stages=("pre-commit", "pre-push", "ci"),
        prevents="an ESLint violation, including a stale disable directive, reaching a reviewer",
    ),
    Control(
        id="fe-types",
        command="npx tsc --noEmit",
        stages=("pre-push",),
        prevents="a TypeScript error the build would hit only after the UI is bundled",
    ),
    Control(
        id="fe-tests",
        command="npm run test:run",
        stages=("pre-push", "ci"),
        prevents="a UI regression reaching a release without a failing unit test",
    ),
    Control(
        id="fe-a11y",
        command="npm run test:a11y",
        stages=("ci",),
        prevents="a WCAG regression that only a real browser's computed styles reveal",
    ),
    Control(
        id="commit-message",
        command="grep -qE '^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)",
        stages=("pre-commit",),
        prevents="a commit message the changelog and release notes cannot be generated from",
    ),
    Control(
        id="npm-lock-state",
        command="npm ls --depth=0 >/dev/null 2>&1",
        stages=("pre-push",),
        prevents="a green run against node_modules that no longer matches package-lock.json",
    ),
    # The gates the principle catalogue (docs/PRINCIPLES.md) adds. Their
    # commands are the ones the stage files actually run; the registry is the
    # SSOT, so a command that drifts from it is a red `--check` rather than a
    # quietly weakened gate. `py-duplication` is pre-push, not pre-commit,
    # because the scanner lives in frontend/node_modules and a Python-only
    # contributor must not need a Node install to commit; the same reasoning
    # keeps real gitleaks in CI and the dependency-free scan at pre-commit.
    Control(
        id="py-imports",
        command="uv run --extra dev lint-imports",
        stages=("pre-push", "ci"),
        prevents="a module importing up the layers, which erases the architecture in one line (P-DIP/P-SOC)",
    ),
    Control(
        id="py-deadcode",
        command="uv run --extra dev vulture src/fpstune vulture_whitelist.py --min-confidence 80",
        stages=("pre-push", "ci"),
        prevents="dead code and unused flags surviving as a liability (P-YAGNI/P-DELETE)",
    ),
    Control(
        id="py-duplication",
        command="jscpd",
        stages=("pre-push", "ci"),
        prevents="a copy-pasted block growing past the recorded clone threshold (P-DRY)",
    ),
    Control(
        id="fe-deadcode",
        command="npm run knip",
        stages=("pre-push", "ci"),
        prevents="an unused export, file or dependency surviving in the UI (P-YAGNI/P-DELETE)",
    ),
    Control(
        id="fe-deps",
        command="npm run deps:check",
        stages=("pre-push", "ci"),
        prevents="a frontend import that points the wrong way across layers (P-DIP/P-SOC)",
    ),
    Control(
        id="workflow-security",
        command="uv run --extra dev zizmor .github/workflows",
        stages=("pre-push", "ci"),
        prevents="an unpinned action or an over-broad workflow token (P-LEASTPRIV)",
    ),
    Control(
        id="secrets-scan",
        command="pytest -q --no-cov tests/test_principles_security.py",
        stages=("pre-commit",),
        prevents="a credential entering the repository in the commit that adds it (P-SECRETS), with no binary to install",
    ),
    Control(
        id="secrets-history",
        command="gitleaks.exe git",
        stages=("ci",),
        prevents="a secret the dependency-free scan cannot see (the real gitleaks ruleset) shipping with a release (P-SECRETS)",
    ),
    Control(
        id="diff-budget",
        command="python scripts/diff_budget.py --staged",
        stages=("pre-commit",),
        prevents="a small fix arriving as a three-hundred-file diff nobody can review (P-SMALLBATCH/P-BOYSCOUT)",
    ),
    Control(
        id="control-registry",
        command="python scripts/controls.py --check",
        stages=("pre-commit", "pre-push", "ci"),
        prevents="a control disappearing from a stage while the others keep looking enforced (P-SSOT/P-SHIFTLEFT)",
    ),
    Control(
        id="risk-coverage",
        command="python scripts/risk_coverage.py",
        stages=("pre-push", "ci"),
        prevents="a critical module losing the tests that make its coverage real (P-RISKTEST)",
    ),
    Control(
        id="mutation",
        command="bash scripts/mutation.sh",
        stages=("manual",),
        prevents="a critical pure module whose tests pass without ever failing (P-MUTATION)",
    ),
)


def _normalise(text: str) -> str:
    return " ".join(text.split())


def _shell_commands(text: str) -> list[str]:
    """Executable lines of a shell script: comments dropped, continuations joined."""
    commands: list[str] = []
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not pending and (not line or line.startswith("#")):
            continue
        if line.endswith("\\"):
            pending = f"{pending} {line[:-1]}".strip()
            continue
        if pending:
            line = f"{pending} {line}".strip()
            pending = ""
        if not line or line.startswith("#"):
            continue
        commands.append(_normalise(line))
    if pending:
        commands.append(_normalise(pending))
    return commands


def _runs(node: Any) -> list[str]:
    """Every `run:` value under a YAML node, one command per line of the script."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "run" and isinstance(value, str):
                found.extend(
                    _normalise(line)
                    for line in value.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                )
            else:
                found.extend(_runs(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_runs(item))
    return found


def _lefthook_commands(text: str) -> list[str]:
    """The commands of the two hooks that run before a commit exists."""
    data = yaml.safe_load(text) or {}
    commands: list[str] = []
    for hook in ("pre-commit", "commit-msg"):
        commands.extend(_runs(data.get(hook)))
    return commands


def stage_commands(stage: str, root: Path = ROOT) -> list[str]:
    """The commands a stage actually runs, as normalised single lines."""
    if stage not in STAGE_FILES:
        raise ValueError(f"unknown stage {stage!r}; known: {', '.join(STAGE_FILES)}")
    text = (root / STAGE_FILES[stage]).read_text(encoding="utf-8")
    if stage == "pre-commit":
        return _lefthook_commands(text)
    if stage == "pre-push":
        return _shell_commands(text)
    return _runs(yaml.safe_load(text) or {})


def _stage_order(stage: str) -> int:
    return STAGES.index(stage)


def _manual_script(control: Control, root: Path) -> Path | None:
    match = _SCRIPT_PATH.search(control.command)
    return root / match.group(1) if match else None


def _manual_problems(control: Control, counts: dict[str, int], root: Path) -> list[str]:
    problems = []
    script = _manual_script(control, root)
    if script is not None and not script.exists():
        problems.append(f"{control.id}: manual script {script.relative_to(root)} is gone")
    if any(counts.values()):
        problems.append(
            f"{control.id}: marked manual but a stage file runs it; wire it or fix the entry"
        )
    return problems


def _wired_problems(control: Control, counts: dict[str, int]) -> list[str]:
    """A wired control runs where it says, once per stage, earliest first."""
    problems = []
    earliest = min(control.stages, key=_stage_order)
    if not counts.get(earliest, 0):
        problems.append(
            f"{control.id}: missing from its earliest stage {earliest} "
            f"({STAGE_FILES[earliest]}) — that is where it can catch the defect first"
        )
    for stage in control.stages:
        if not counts.get(stage, 0):
            problems.append(
                f"{control.id}: declared at {stage}, but {STAGE_FILES[stage]} "
                f"does not run {control.command!r}"
            )
    for stage, count in counts.items():
        if count > 1:
            problems.append(
                f"{control.id}: runs {count} times at {stage} — one run per stage; "
                "the second copy catches nothing new"
            )
        if count and _stage_order(stage) < _stage_order(earliest):
            problems.append(
                f"{control.id}: runs at {stage}, earlier than its declared earliest {earliest}"
            )
    return problems


def _control_problems(control: Control, commands: dict[str, list[str]], root: Path) -> list[str]:
    problems = []
    if not control.prevents.strip():
        problems.append(f"{control.id}: no `prevents` sentence — a control nobody can justify")
    unknown = [stage for stage in control.stages if stage not in STAGES]
    if unknown:
        problems.append(f"{control.id}: unknown stage(s) {unknown}")
        return problems
    if not control.stages:
        problems.append(f"{control.id}: runs nowhere")
        return problems

    counts = {
        stage: sum(1 for command in stage_commands if control.command in command)
        for stage, stage_commands in commands.items()
    }
    if "manual" in control.stages:
        problems.extend(_manual_problems(control, counts, root))
        return problems
    if control.status == "proposed":
        wired = sorted(stage for stage, count in counts.items() if count)
        if wired:
            problems.append(
                f"{control.id}: proposed, but already runs at {wired} — set status='wired' "
                "so the check starts enforcing it"
            )
        return problems
    if control.status != "wired":
        problems.append(f"{control.id}: unknown status {control.status!r}")
        return problems
    problems.extend(_wired_problems(control, counts))
    return problems


def _unregistered_problems(
    commands: dict[str, list[str]], controls: Sequence[Control]
) -> list[str]:
    """A check a stage runs that no control owns.

    Without this, deleting a control from the registry would leave the stage
    looking enforced and the registry silently shorter.
    """
    problems = []
    for stage, stage_commands in commands.items():
        for command in stage_commands:
            if not command.startswith(CHECK_PREFIXES):
                continue
            if any(control.command in command for control in controls):
                continue
            problems.append(f"{stage}: {command!r} is not in the control registry")
    return problems


def check(root: Path = ROOT, controls: Sequence[Control] = CONTROLS) -> list[str]:
    """Every disagreement between the registry and the stage files, as sentences.

    ``root`` and ``controls`` are parameters so the gate's own tests can drive the
    checker over a fixture tree and a small registry instead of the repository.
    """
    try:
        commands = {stage: stage_commands(stage, root) for stage in STAGE_FILES}
    except (OSError, yaml.YAMLError) as exc:
        return [f"a stage file could not be read: {exc}"]

    problems: list[str] = []
    for control in controls:
        problems.extend(_control_problems(control, commands, root))
    problems.extend(_unregistered_problems(commands, controls))
    return problems


def describe() -> str:
    """The registry as one line per control, for a reader deciding where a check goes."""
    lines = []
    for control in CONTROLS:
        stages = ", ".join(control.stages) if control.stages else "nowhere"
        marker = "" if control.status == "wired" else f" [{control.status}]"
        lines.append(
            f"{control.id}{marker}: {control.command}\n    stages: {stages}\n    prevents: {control.prevents}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when the stage files and the registry disagree",
    )
    args = parser.parse_args(argv)

    if not args.check:
        print(describe())
        return 0

    problems = check()
    if problems:
        print("control registry: RED", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    wired = sum(1 for control in CONTROLS if control.status == "wired")
    proposed = len(CONTROLS) - wired
    print(
        f"control registry: green — {wired} wired control(s), {proposed} proposed, "
        "every one at the earliest stage that runs it"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

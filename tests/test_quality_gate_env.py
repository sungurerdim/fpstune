"""The local gate must use the project's dev extra, never whichever pytest is on PATH.

A clean checkout in this repository reproduced the fall-through: `uv run pytest`
resolved a global Python 3.13/pytest beside the project's 3.12 env, and the gate
reported 46 collection errors that looked like product failures. These tests hold
the command surface that prevents it.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_every_dev_tool_uses_the_dev_extra() -> None:
    for relative in (
        "scripts/quality.sh",
        "Taskfile.yml",
        "lefthook.yml",
        "scripts/affected_tests.py",
    ):
        text = _read(relative)
        assert "uv run --extra dev" in text or '"--extra", "dev"' in text, relative


def test_a_bare_uv_pytest_is_not_the_gate() -> None:
    for relative in ("scripts/quality.sh", "Taskfile.yml", "lefthook.yml"):
        text = _read(relative)
        commands = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        assert "uv run pytest" not in commands, f"{relative} still has a bare uv run pytest"


def test_quality_prints_which_interpreter_and_pytest_ran() -> None:
    text = _read("scripts/quality.sh")
    assert "sys.executable" in text
    assert "pytest.__version__" in text


def test_quality_keeps_local_coverage() -> None:
    text = _read("scripts/quality.sh")
    assert "--cov=src/fpstune" in text
    assert "--cov-report=term-missing" in text

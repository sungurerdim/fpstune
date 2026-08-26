"""Setting values are compared with `values_equal`, never with `==`.

CLAUDE.md states this as an invariant, and it is not a style preference. The same
setting's value arrives as `int` from a REG_DWORD, `str` from a REG_SZ, text with
a trailing CRLF from PowerShell, and hex from powercfg. `==` says those differ.
Everything downstream — "is this optimized", "did the write land", "do these
power plans agree" — is a comparison, so a bare `==` turns a correct machine into
a reported problem or the reverse.

The rule had one violation when this guard was written: `powercfg.py` compared a
plan's reading against `recommended_value` with `!=`, and readings across plans
with `==`. A plan holding an override yields the integer index its `value_map`
translates, while a plan holding none yields the curated `default_value` — 100
and "100" for a free-form setting — so two plans holding the same value were
reported as disagreeing and the UI called a fully-tuned machine half-tuned.

A grep cannot tell `setting.category.value == "network"` (an enum's own string,
which is fine) from `detected_value == expected` (which is not), so this walks
the AST and names the operands it cares about.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "fpstune"

# Locals that hold a setting's value somewhere in this codebase.
VALUE_NAMES = frozenset(
    {
        "current_value",
        "detected_value",
        "expected_value",
        "raw_value",
        "requested_value",
        "reading",
        "observed",
        "target_value",
    }
)

# Attributes that are a setting's value.
VALUE_ATTRS = frozenset({"recommended_value", "default_value", "current_value", "detected_value"})

# `.value` is overwhelmingly an enum's own string in this codebase
# (`category.value`, `apply_type.value`), which is exactly what `==` is for.
# Only these owners make `.value` a *setting* value.
RESULT_OWNERS = frozenset({"result", "detection", "detected"})


def _is_setting_value(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id in VALUE_NAMES
    if isinstance(node, ast.Attribute):
        if node.attr in VALUE_ATTRS:
            return True
        if node.attr == "value" and isinstance(node.value, ast.Name):
            return node.value.id in RESULT_OWNERS
    return False


# A comparison that genuinely wants identity rather than equivalence says so at
# the site, with a reason. There is one in the codebase: `CommandExecutor.detect`
# asks whether type coercion changed the representation, which is the single
# question `values_equal` exists to answer "no" to.
EXEMPTION = "values-differ-by-design:"


def _exempt_lines(source: str) -> set[int]:
    """Line numbers covered by an exemption marker and the lines just after it.

    The marker sits on its own comment line above the comparison, so the block of
    comment lines and the statement they introduce are all covered.
    """
    covered: set[int] = set()
    lines = source.splitlines()
    for index, line in enumerate(lines, start=1):
        if EXEMPTION not in line:
            continue
        assert line.split(EXEMPTION, 1)[1].strip(), (
            f"line {index}: the exemption marker carries no reason. An unexplained "
            "exemption is indistinguishable from a forgotten one."
        )
        # Cover this comment, any comment lines continuing it, and the first
        # statement after them.
        cursor = index
        while cursor <= len(lines) and lines[cursor - 1].lstrip().startswith("#"):
            covered.add(cursor)
            cursor += 1
        covered.add(cursor)
    return covered


def _violations(source: str, label: str) -> list[str]:
    found = []
    exempt = _exempt_lines(source)
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
            continue
        if node.lineno in exempt:
            continue
        operands = [node.left, *node.comparators]
        if any(_is_setting_value(operand) for operand in operands):
            found.append(f"{label}:{node.lineno}: {ast.unparse(node)}")
    return found


def test_no_setting_value_is_compared_with_a_bare_equals() -> None:
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        offenders.extend(
            _violations(path.read_text(encoding="utf-8"), str(path.relative_to(SRC.parent.parent)))
        )

    assert offenders == [], (
        "Setting values must be compared with values_equal(), which coerces the "
        "int/str/CRLF/hex forms the same value arrives in. A bare == reports a "
        "correct machine as wrong:\n  " + "\n  ".join(offenders)
    )


def test_the_guard_catches_the_violation_it_was_written_for() -> None:
    """The exact powercfg line, so this cannot quietly stop checking."""
    offenders = _violations("if reading != setting.recommended_value:\n    pass\n", "sample.py")
    assert offenders == ["sample.py:1: reading != setting.recommended_value"]


def test_the_guard_leaves_enum_comparisons_alone() -> None:
    """`category.value == "network"` compares an enum's own string and is correct.

    A guard that flagged these would be turned off within a week, which is the
    same as not having one.
    """
    assert _violations('if setting.category.value == "network":\n    pass\n', "s.py") == []
    assert _violations('if setting.apply_type.value == "powershell":\n    pass\n', "s.py") == []


def test_the_guard_reads_both_operand_positions() -> None:
    """A violation written the other way round is the same violation."""
    assert _violations("if setting.default_value == raw:\n    pass\n", "s.py")
    assert _violations("if raw == setting.default_value:\n    pass\n", "s.py")


def test_an_explained_exemption_is_honoured() -> None:
    """Some comparisons do want identity — and must say why at the site."""
    source = (
        "# values-differ-by-design: asks whether coercion changed the shape\n"
        "if value != raw_value:\n"
        "    pass\n"
    )
    assert _violations(source, "s.py") == []


def test_an_exemption_with_no_reason_is_refused() -> None:
    """Otherwise the marker becomes a way to silence the guard without thinking."""
    import pytest

    with pytest.raises(AssertionError, match="carries no reason"):
        _violations("# values-differ-by-design:\nif value != raw_value:\n    pass\n", "s.py")


def test_the_exemption_does_not_cover_the_rest_of_the_file() -> None:
    """A marker must silence its own comparison, not everything below it."""
    source = (
        "# values-differ-by-design: only this one\n"
        "if value != raw_value:\n"
        "    pass\n"
        "if reading != setting.recommended_value:\n"
        "    pass\n"
    )
    assert _violations(source, "s.py") == ["s.py:4: reading != setting.recommended_value"]

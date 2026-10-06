"""Hygiene gates over the test suite itself.

A stub is a claim about what production can return. `_get_hardware_context` is
typed `-> HardwareContext` and wraps `build_hardware_context`; neither ever
returns None. A test that stubs it with None puts the code under test in a state
production cannot reach, and it stays green only until the code reads the
context unconditionally (commit 49380e1 did, and 16 tests went red at once with
`'NoneType' object has no attribute 'ucpd_guard_up'`).
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent

# Functions that return a HardwareContext and never None.
CONTEXT_PROVIDERS = frozenset(
    {"_get_hardware_context", "_get_hardware_context_async", "build_hardware_context"}
)


def _is_patch(func: ast.expr) -> tuple[bool, bool]:
    """(is a patch call, is patch.object)."""
    if isinstance(func, ast.Name) and func.id == "patch":
        return True, False
    if isinstance(func, ast.Attribute):
        if func.attr == "patch":
            return True, False
        if (
            func.attr == "object"
            and isinstance(func.value, (ast.Name, ast.Attribute))
            and (
                getattr(func.value, "id", None) == "patch"
                or getattr(func.value, "attr", None) == "patch"
            )
        ):
            return True, True
    return False, False


def _is_none(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _names_provider(call: ast.Call, is_object: bool) -> bool:
    """Does the patch target one of the context providers?"""
    if is_object:
        target = call.args[1] if len(call.args) > 1 else None
        return (
            isinstance(target, ast.Constant)
            and isinstance(target.value, str)
            and target.value in CONTEXT_PROVIDERS
        )
    target = call.args[0] if call.args else None
    return (
        isinstance(target, ast.Constant)
        and isinstance(target.value, str)
        and target.value.rsplit(".", 1)[-1] in CONTEXT_PROVIDERS
    )


def _returns_none(keyword: ast.keyword) -> bool:
    """`return_value=None`, `side_effect=lambda ...: None`, or a factory handed a bare None."""
    value = keyword.value
    if keyword.arg == "return_value":
        return _is_none(value)
    if keyword.arg == "side_effect":
        if isinstance(value, ast.Lambda):
            return _is_none(value.body)
        if isinstance(value, ast.Call):
            return any(_is_none(arg) for arg in value.args)
    return False


def none_context_stubs(source: str) -> list[int]:
    """Line numbers of every patch that makes a context provider return None."""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        is_patch, is_object = _is_patch(node.func)
        if not is_patch or not _names_provider(node, is_object):
            continue
        if any(_returns_none(kw) for kw in node.keywords):
            lines.append(node.lineno)
    return sorted(lines)


def test_no_test_stubs_the_hardware_context_with_none() -> None:
    """Stub with `neutral_hardware_context()` (tests/conftest.py), never None."""
    offenders: list[str] = []
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if path == Path(__file__).resolve():
            continue
        for line in none_context_stubs(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(TESTS_ROOT.parent).as_posix()}:{line}")
    assert not offenders, (
        "These patches make a HardwareContext provider return None, a state production "
        "cannot reach; use tests.conftest.neutral_hardware_context():\n  " + "\n  ".join(offenders)
    )


class TestGuardSeesTheShapes:
    """The scan itself: each way of writing the mistake is caught, neutral stubs are not."""

    def test_return_value_none_on_a_string_target(self) -> None:
        source = 'with patch("fpstune.api.routes.settings._get_hardware_context", return_value=None):\n    pass\n'
        assert none_context_stubs(source) == [1]

    def test_patch_object_target(self) -> None:
        source = 'x = patch.object(route, "_get_hardware_context_async", return_value=None)\n'
        assert none_context_stubs(source) == [1]

    def test_build_hardware_context_target(self) -> None:
        source = (
            'x = patch("fpstune.core.power_profile.build_hardware_context", return_value=None)\n'
        )
        assert none_context_stubs(source) == [1]

    def test_side_effect_lambda_returning_none(self) -> None:
        source = 'x = patch("a._get_hardware_context", side_effect=lambda *a, **k: None)\n'
        assert none_context_stubs(source) == [1]

    def test_side_effect_factory_handed_none(self) -> None:
        source = 'x = patch("a._get_hardware_context", side_effect=_loop_recorder(record, None))\n'
        assert none_context_stubs(source) == [1]

    def test_neutral_context_is_not_flagged(self) -> None:
        source = (
            'x = patch("a._get_hardware_context", return_value=neutral_hardware_context())\n'
            'y = patch("a._get_hardware_context", side_effect=_loop_recorder(record, ctx))\n'
        )
        assert none_context_stubs(source) == []

    def test_none_on_an_unrelated_target_is_not_flagged(self) -> None:
        source = 'x = patch("a._ensure_restore_point", return_value=None)\n'
        assert none_context_stubs(source) == []

"""Section D of the principle catalogue, bound to this repository.

`D:/GitHub/ideal-sistem-tasarimi/ilke-katalogu.md` lists ten testing principles
between P-PYRAMID and P-SHIFTLEFT. Nine of them are judgements until something
runs: a suite can be a pyramid in prose, a test can assert nothing while passing,
and a risk-based allocation can be a table nobody checks. This module turns each
into a scan with a verdict, and says where the line stays a judgement.

*P-GOODHART* — a test that asserts nothing is green for the same reason a test
that was never collected is: nothing distinguishes it from success. The scan reads
the AST of every `test_*` function and accepts `assert`, `pytest.raises`/`fail`/
`warns`, a mock's `assert_called*`, and a helper whose name starts with `assert`.
The eight tests that assert through a property ("must not raise") or through a
patched side effect are frozen in `_ASSERTION_BY_PROPERTY`, each with its reason,
and the list may only shrink.

*P-PYRAMID* — many unit modules, few integration, least end-to-end. "Unit" here is
the catalogue's own definition: a module that imports no `TestClient`, no
`subprocess`, no real `socket` and no `uvicorn`. The thresholds are measured from
the tree, not aspirational: 2026-10-25 gave 242 unit / 53 integration modules and
2 Playwright specs. A floor below the measurement and a ceiling above it leave
ordinary growth room and still refuse a suite that turns into E2E.

*P-BEHAVIOR* — the catalogue's violation is a test that counts a private method's
calls. Zero such assertions exist today, so the baseline is empty and may never
grow. The second half is a cap on patches per test: six is the p99 of a measured
distribution (2026-10-25: 4,167 test functions, max 8, p99 5), and the four tests
above it are frozen with the reason each needs that many seams.

*P-RISKTEST* — the modules where a wrong branch restores a setting nobody asked
for, deletes the wrong file or reports a measurement nobody took are mapped to the
test files that must cover them, with a floor on the test count. Effort follows
risk; this is where the list lives.

*P-HERMETIC* — bound in `tests/conftest.py` (`NetworkWatch` + the autouse
`_no_network` fixture): a test that resolves or connects to anything but the
loopback interface fails. The tests here prove the guard sees the shapes, is
armed during a test, and that the allowlist cannot rot.

*P-MEASURE* — the binding already exists (C11's measurement path); this module
only pins the files and functions it names, so a rename cannot leave the rule
reading as enforced. P-REPRO has its own home in `tests/test_principles_ops.py`
(ops-security-gates owns it), so it is deliberately not asserted twice here.

Deliberately not asserted: what the catalogue *says*. Prose is for humans, and
pinning it would turn every wording improvement into a failure.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import sys
from collections import Counter
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
SCRIPTS = ROOT / "scripts"

_SKIP_NAMES = frozenset({"__init__.py", "conftest.py"})


# --------------------------------------------------------------------------- #
# Shared scans
# --------------------------------------------------------------------------- #


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_fixture(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
            return True
        if isinstance(decorator, ast.Name) and decorator.id == "fixture":
            return True
    return False


@cache
def _parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


@cache
def _test_functions(path: Path) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef, ...]:
    """The test functions a module defines, fixtures excluded.

    `tests/conftest.py` has a fixture called `test_client`; a fixture is setup,
    not a test, and it is not expected to assert anything.
    """
    return tuple(
        node
        for node in ast.walk(_parsed(path))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
        and not _is_fixture(node)
    )


@cache
def _test_modules() -> tuple[Path, ...]:
    """Every module that defines at least one test."""
    return tuple(
        path
        for path in sorted(TESTS.rglob("*.py"))
        if "__pycache__" not in path.parts
        and path.name not in _SKIP_NAMES
        and _test_functions(path)
    )


@cache
def _all_test_functions() -> tuple[tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef], ...]:
    return tuple((path, function) for path in _test_modules() for function in _test_functions(path))


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return getattr(func, "id", "")


# --------------------------------------------------------------------------- #
# P-GOODHART — every test asserts something
# --------------------------------------------------------------------------- #

_ASSERTION_CALLS = frozenset({"raises", "fail", "warns", "deprecated_call"})


def _has_assertion(function: ast.AST) -> bool:
    """True when the function contains an assertion pytest can fail on.

    `assert` statements, `pytest.raises`/`pytest.fail`/`pytest.warns`, a mock's
    `assert_called*`, and a helper whose name starts with `assert`
    (`probe.assert_clean()`) all count. `pytest.skip` does not: it is the way to
    leave a test without a verdict.
    """
    for node in ast.walk(function):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in _ASSERTION_CALLS or name.startswith("assert"):
                return True
    return False


# Tests whose verdict is a property rather than an `assert`. Each entry is
# shrink-only: when the test gains an assertion (or is deleted) the stale check
# fails and the entry must go in the same change.
_ASSERTION_BY_PROPERTY: dict[tuple[str, str], str] = {
    (
        "tests/test_api/test_registry_warmup.py",
        "test_a_failing_warm_up_does_not_raise",
    ): "the property is 'must not raise': an exception fails the test, so an "
    "assert would only restate the absence",
    (
        "tests/test_benchmark/test_verify_round.py",
        "test_every_shipped_claim_parses_without_raising",
    ): "every shipped claim is parsed; the parser raising is the failure",
    (
        "tests/test_release_contract.py",
        "test_every_manifest_parses",
    ): "yaml.safe_load raises on an unparseable manifest, which fails the test",
    (
        "tests/test_release_contract.py",
        "test_it_parses",
    ): "ast.parse raises on invalid spec source, which fails the test",
    (
        "tests/test_settings/test_bulk_plan.py",
        "test_a_valid_chain_passes",
    ): "validate_declarations raises BulkPlanError on an invalid chain; a pass is "
    "the absence of that raise",
    (
        "tests/test_settings/test_bulk_plan.py",
        "test_the_shipped_definitions_validate",
    ): "the shipped registry is validated by the same raising call",
    (
        "tests/test_settings/test_discovery_warmup.py",
        "test_a_failing_probe_does_not_break_discovery",
    ): "the property is 'a failing probe must not raise out of warm()'",
    (
        "tests/test_utils/test_updates.py",
        "test_nothing_checks_for_updates_on_import",
    ): "the assertion is the patched urlopen's side_effect: any request raises "
    "AssertionError, which is the point of the test",
}


class TestPGoodhartEveryTestAsserts:
    """A test with no assertion cannot fail, and P-GOODHART's example is exactly it."""

    def test_every_test_function_asserts(self) -> None:
        observed = {
            (_rel(path), function.name)
            for path, function in _all_test_functions()
            if not _has_assertion(function)
        }
        unexpected = sorted(observed - set(_ASSERTION_BY_PROPERTY))

        assert not unexpected, (
            f"{len(unexpected)} test function(s) contain no assertion, so they pass "
            "whether or not the code works (P-GOODHART). Assert the observable "
            "result; if the verdict is 'must not raise', add the entry to "
            "_ASSERTION_BY_PROPERTY with the reason:\n  "
            + "\n  ".join(f"{module}::{name}" for module, name in unexpected)
        )

    def test_the_baseline_is_not_stale(self) -> None:
        observed = {
            (_rel(path), function.name)
            for path, function in _all_test_functions()
            if not _has_assertion(function)
        }
        stale = sorted(set(_ASSERTION_BY_PROPERTY) - observed)

        assert not stale, (
            "these entries no longer describe an assertion-free test — the test "
            "gained an assertion or was deleted. Delete the entry so the shrink is "
            "on the record:\n  " + "\n  ".join(f"{m}::{n}" for m, n in stale)
        )

    def test_the_scan_sees_the_shapes(self) -> None:
        """Each way an assertion is written is recognised; a skip is not one."""
        cases = {
            "def test_x():\n    assert value == 1\n": True,
            "def test_x():\n    with pytest.raises(OSError):\n        run()\n": True,
            "def test_x():\n    pytest.fail('nope')\n": True,
            "def test_x():\n    mock.assert_called_once_with(1)\n": True,
            "def test_x():\n    probe.assert_clean()\n": True,
            "def test_x():\n    pytest.skip('not here')\n": False,
            "def test_x():\n    run()\n": False,
        }
        for source, expected in cases.items():
            function = ast.parse(source).body[0]
            assert _has_assertion(function) is expected, source


# --------------------------------------------------------------------------- #
# P-PYRAMID — many unit modules, few integration, least end-to-end
# --------------------------------------------------------------------------- #

_INTEGRATION_IMPORTS = frozenset({"subprocess", "socket", "uvicorn"})
_INTEGRATION_CALLS = frozenset({"TestClient", "run_api"})

# Measured 2026-10-25 over the tree: 243 unit, 56 integration, 2 Playwright
# specs (unit/integration ratio 4.34). The floor sits under the measurement and
# the ceilings above it: ordinary growth passes, a suite that turns into E2E does
# not. A number nobody measured is the aspirational threshold P-GOODHART warns
# about.
_UNIT_FLOOR = 230
_INTEGRATION_CEILING = 65
_E2E_CEILING = 3
_RATIO_FLOOR = 3.5


def _module_kind(path: Path) -> str:
    """`unit` unless the module drives a real client, process, socket or server."""
    for node in ast.walk(_parsed(path)):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] in _INTEGRATION_IMPORTS for alias in node.names):
                return "integration"
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in _INTEGRATION_IMPORTS:
                return "integration"
            if node.module.endswith("testclient"):
                return "integration"
        elif isinstance(node, ast.Call) and _call_name(node) in _INTEGRATION_CALLS:
            return "integration"
    return "unit"


def _e2e_specs() -> tuple[Path, ...]:
    return tuple(sorted((ROOT / "frontend" / "e2e").glob("*.spec.ts")))


def _pyramid_counts() -> dict[str, int]:
    kinds = Counter(_module_kind(path) for path in _test_modules())
    return {"unit": kinds["unit"], "integration": kinds["integration"], "e2e": len(_e2e_specs())}


class TestPPyramid:
    """The catalogue's test pyramid, counted from the tree rather than assumed."""

    def test_the_suite_is_a_pyramid(self) -> None:
        counts = _pyramid_counts()
        ratio = counts["unit"] / max(counts["integration"], 1)
        problems: list[str] = []
        if counts["unit"] < _UNIT_FLOOR:
            problems.append(f"unit modules {counts['unit']} < floor {_UNIT_FLOOR}")
        if counts["integration"] > _INTEGRATION_CEILING:
            problems.append(
                f"integration modules {counts['integration']} > ceiling {_INTEGRATION_CEILING}"
            )
        if counts["e2e"] > _E2E_CEILING:
            problems.append(f"e2e specs {counts['e2e']} > ceiling {_E2E_CEILING}")
        if ratio < _RATIO_FLOOR:
            problems.append(f"unit/integration ratio {ratio:.2f} < floor {_RATIO_FLOOR}")
        if not counts["unit"] > counts["integration"] > counts["e2e"]:
            problems.append("the shape is not 'many unit, few integration, least e2e'")

        assert not problems, (
            f"counts: {counts} (unit/integration ratio {ratio:.2f}). "
            "A new test belongs at the cheapest level that can catch its defect; an "
            "integration module that could be a unit module is the pyramid tipping.\n"
            + "\n".join(problems)
        )

    def test_the_classification_rule_itself(self, tmp_path: Path) -> None:
        """The rule is the catalogue's definition, so pin it against fixtures."""
        unit = tmp_path / "test_pure.py"
        unit.write_text("def test_x():\n    assert 1 + 1 == 2\n", encoding="utf-8")
        integration = tmp_path / "test_client.py"
        integration.write_text(
            "from fastapi.testclient import TestClient\n\ndef test_x():\n    assert TestClient\n",
            encoding="utf-8",
        )
        process = tmp_path / "test_process.py"
        process.write_text(
            "import subprocess\n\ndef test_x():\n    assert subprocess\n", encoding="utf-8"
        )
        socket_user = tmp_path / "test_socket.py"
        socket_user.write_text(
            "import socket\n\ndef test_x():\n    assert socket\n", encoding="utf-8"
        )

        assert _module_kind(unit) == "unit"
        assert _module_kind(integration) == "integration"
        assert _module_kind(process) == "integration"
        assert _module_kind(socket_user) == "integration"

    def test_the_e2e_specs_are_playwright(self) -> None:
        """The end-to-end layer is the frontend's Playwright suite and nothing else."""
        specs = _e2e_specs()
        assert specs, "frontend/e2e has no spec files, so the e2e layer is unmeasured"
        for spec in specs:
            assert "@playwright/test" in spec.read_text(encoding="utf-8"), _rel(spec)


# --------------------------------------------------------------------------- #
# P-BEHAVIOR — the observable behaviour, not the implementation
# --------------------------------------------------------------------------- #

_CALL_COUNT_ATTRS = frozenset(
    {
        "assert_called",
        "assert_called_once",
        "assert_called_with",
        "assert_called_once_with",
        "assert_any_call",
        "assert_not_called",
        "assert_has_calls",
        "call_count",
        "call_args",
        "call_args_list",
        "mock_calls",
    }
)

# (module, private target) -> reason. Zero entries today; the check below may
# never grow, only stay empty or shrink.
_PRIVATE_CALL_COUNT_ALLOWLIST: dict[tuple[str, str], str] = {}

# Patches per test function. Measured 2026-10-25 over 4,167 test functions:
# median 0, p99 5, max 8. Six is one above the p99: a new test may patch up to
# six collaborators, and the four existing tests that patch more are frozen with
# the reason each needs its seams.
_PATCH_CAP = 6
_PATCH_ALLOWLIST: dict[tuple[str, str], tuple[int, str]] = {
    (
        "tests/test_api/test_reset_safety.py",
        "test_applying_the_default_creates_a_restore_point",
    ): (
        8,
        "the restore-point decision reads the registry, hardware context, finalize "
        "path, command, self-check, platform and operation lock; each patch replaces "
        "one seam of that single decision",
    ),
    (
        "tests/test_safety/test_retired_files.py",
        "test_a_full_scan_then_a_reset_leave_no_originals_and_no_history_file",
    ): (
        7,
        "one process is driven through start-up, a scan and a reset; each patch "
        "replaces one seam of that sequence and the test asserts nothing is left behind",
    ),
    (
        "tests/test_executors/test_failed_write_is_failure.py",
        "test_every_setting_fails_with_a_reason",
    ): (
        7,
        "the sweep makes every writer family fail — PowerShell, process watch, "
        "winreg, NVAPI profile and NVAPI driver settings — one patch per family",
    ),
    (
        "tests/test_api/test_setting_state.py",
        "test_a_failed_command_has_no_state",
    ): (
        7,
        "the route's state needs the registry, hardware context, detection engine, "
        "restore point, self-check, operation lock and the command itself",
    ),
}

_PATCH_FUNCTIONS = frozenset({"patch"})
_PATCH_METHODS = frozenset({"object", "dict", "multiple", "context"})
_MONKEYPATCH_METHODS = frozenset({"setattr", "setenv", "delenv", "setitem", "delitem"})


def _attribute_root(node: ast.Attribute) -> str:
    value = node.value
    if isinstance(value, ast.Attribute):
        return value.attr
    return getattr(value, "id", "")


def _patch_calls(function: ast.AST) -> int:
    """How many seams a test replaces: `patch`, `patch.object`, `monkeypatch.setattr`.

    Decorators count too: `@patch("a.b")` above a test is the same seam as a
    `with patch("a.b")` inside it. The attribute forms are matched by their root
    (`patch.object`, `monkeypatch.setattr`) so a call to an unrelated `.object()`
    is not mistaken for one.
    """
    count = 0
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _PATCH_FUNCTIONS:
            count += 1
        elif isinstance(func, ast.Attribute):
            root = _attribute_root(func)
            if (
                func.attr in _PATCH_METHODS
                and "patch" in root
                or func.attr in _MONKEYPATCH_METHODS
                and ("monkeypatch" in root or root in {"mp", "patch"})
            ):
                count += 1
    return count


def _private_call_count_assertions(path: Path) -> set[str]:
    """Private targets whose call count this module asserts on."""
    found: set[str] = set()
    for node in ast.walk(_parsed(path)):
        if isinstance(node, ast.Attribute) and node.attr in _CALL_COUNT_ATTRS:
            inner = node.value
            if isinstance(inner, ast.Attribute) and inner.attr.startswith("_"):
                found.add(inner.attr)
    return found


class TestPBehaviorObservableBehaviour:
    """Tests assert what a caller can see, not how a private helper was called."""

    def test_no_test_asserts_on_a_private_functions_call_count(self) -> None:
        observed = {
            (_rel(path), target)
            for path in _test_modules()
            for target in _private_call_count_assertions(path)
        }
        unexpected = sorted(observed - set(_PRIVATE_CALL_COUNT_ALLOWLIST))

        assert not unexpected, (
            "these tests assert on the call count of a private function, which pins "
            "the implementation instead of the behaviour (P-BEHAVIOR). Assert the "
            "observable result; if the seam really is the contract, add the entry to "
            "_PRIVATE_CALL_COUNT_ALLOWLIST with the reason:\n  "
            + "\n  ".join(f"{module}::{target}" for module, target in unexpected)
        )

    def test_the_private_call_count_baseline_is_not_stale(self) -> None:
        observed = {
            (_rel(path), target)
            for path in _test_modules()
            for target in _private_call_count_assertions(path)
        }
        stale = sorted(set(_PRIVATE_CALL_COUNT_ALLOWLIST) - observed)

        assert not stale, (
            "these entries no longer describe a private call-count assertion — delete "
            "them so the list cannot grow back silently:\n  "
            + "\n  ".join(f"{m}::{n}" for m, n in stale)
        )

    def test_no_test_patches_more_than_the_cap(self) -> None:
        observed = {
            (_rel(path), function.name): _patch_calls(function)
            for path, function in _all_test_functions()
        }
        problems: list[str] = []
        for key, count in sorted(observed.items()):
            if count <= _PATCH_CAP:
                continue
            allowed = _PATCH_ALLOWLIST.get(key)
            if allowed is None:
                problems.append(f"{key[0]}::{key[1]} patches {count} seams (cap {_PATCH_CAP})")
            elif count > allowed[0]:
                problems.append(
                    f"{key[0]}::{key[1]} patches {count} seams, baseline allows {allowed[0]}"
                )
        assert not problems, (
            "a test that replaces more than six collaborators is describing the "
            "implementation (P-BEHAVIOR). Split it along behaviour, or freeze the "
            "count with the reason the seams are the contract:\n  " + "\n  ".join(problems)
        )

    def test_the_patch_baseline_is_not_stale(self) -> None:
        observed = {
            (_rel(path), function.name): _patch_calls(function)
            for path, function in _all_test_functions()
        }
        stale = [
            f"{module}::{name} (baseline {allowed[0]}, now {observed.get((module, name), 0)})"
            for (module, name), allowed in sorted(_PATCH_ALLOWLIST.items())
            if observed.get((module, name), 0) < allowed[0]
        ]
        assert not stale, (
            "these tests patch fewer seams than their frozen count — the cleanup "
            "landed, delete the entry so the baseline shrinks:\n  " + "\n  ".join(stale)
        )

    def test_the_scan_sees_the_shapes(self) -> None:
        """A private target is caught, a public one is not, and patches are counted."""
        source = (
            "def test_x():\n"
            "    client._send.assert_called_once()\n"
            "    client.send.assert_called_once()\n"
            "    mock.call_count\n"
        )
        tree = ast.parse(source)
        private = {
            node.value.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr in _CALL_COUNT_ATTRS
            and isinstance(node.value, ast.Attribute)
            and node.value.attr.startswith("_")
        }
        assert private == {"_send"}

        counted = ast.parse(
            "def test_x():\n"
            "    with patch('a.b'):\n"
            "        pass\n"
            "    with patch.object(mod, 'c'):\n"
            "        pass\n"
            "    monkeypatch.setattr(mod, 'd', 1)\n"
            "    logger.object()\n"
        ).body[0]
        assert _patch_calls(counted) == 3


# --------------------------------------------------------------------------- #
# P-RISKTEST — effort follows risk
# --------------------------------------------------------------------------- #

# (module, test files, minimum test functions across them, why a wrong branch here
# is dangerous). The floors are measured minus headroom (2026-10-25), so a module
# that loses its tests is red while ordinary growth is not.
_RISK_MODULES: tuple[tuple[str, tuple[str, ...], int, str], ...] = (
    (
        "src/fpstune/safety/restore.py",
        ("tests/test_safety/test_restore.py",),
        10,
        "a reset with no restore point is unrecoverable, and the description is "
        "caller-supplied (C1/C6)",
    ),
    (
        "src/fpstune/settings/applicability.py",
        ("tests/test_settings/test_applicability.py",),
        30,
        "values_equal is the single comparison truth: a wrong answer marks an "
        "unapplied value verified (C6)",
    ),
    (
        "src/fpstune/settings/bulk_plan.py",
        ("tests/test_settings/test_bulk_plan.py",),
        12,
        "a wrong lane lets two writers lose one setting while both report success (C6)",
    ),
    (
        "src/fpstune/settings/registry.py",
        ("tests/test_settings/test_registry.py",),
        8,
        "the registry is the SSOT: a lost or duplicated setting disappears from every "
        "surface that shows it",
    ),
    (
        "src/fpstune/benchmark/operation_lock.py",
        ("tests/test_api/test_shutdown_route.py", "tests/test_benchmark/test_scheduler.py"),
        10,
        "the one mutex an apply, a cleanup and a bench share; without it a measurement "
        "describes neither the before nor the after (C11)",
    ),
    (
        "src/fpstune/benchmark/verify_round.py",
        ("tests/test_benchmark/test_verify_round.py",),
        20,
        "the one comparison path a claim is judged by; a wrong judge publishes a "
        "number no instrument produced (C11 rule 2)",
    ),
    (
        "src/fpstune/utils/user_paths.py",
        ("tests/test_user_paths.py",),
        25,
        "every write into the user's profile resolves a root here; a wrong root "
        "writes the developer's real profile (C9)",
    ),
    (
        "src/fpstune/settings/cleanup_targets.py",
        (
            "tests/test_settings/test_cleanup_targets.py",
            "tests/test_executors/test_cleanup_delete_paths.py",
        ),
        15,
        "these targets delete files; a wrong path deletes something the user wanted",
    ),
    (
        "src/fpstune/settings/executors/game_config_writer.py",
        (
            "tests/test_executors/test_mw4_write_retry.py",
            "tests/test_executors/test_mw4_config.py",
        ),
        20,
        "the one Name@scope line rewrite shared by two games; a wrong byte is data loss",
    ),
    (
        "src/fpstune/api/routes/settings_apply.py",
        (
            "tests/test_api/test_apply_bench_guard.py",
            "tests/test_api/test_settings_apply_guards.py",
        ),
        12,
        "the one place a setting's command runs for apply and reset; a bypass breaks "
        "the C6 single write path",
    ),
)


def _import_name(module: str) -> str:
    """`src/fpstune/a/b.py` -> `fpstune.a.b`."""
    parts = module.removesuffix(".py").split("/")
    if parts and parts[0] == "src":
        parts = parts[1:]
    return ".".join(parts)


def _names_module(source: str, module: str) -> bool:
    """Does this test source name the module it is supposed to cover?"""
    dotted = _import_name(module)
    stem = dotted.rsplit(".", 1)[-1]
    return dotted in source or re.search(rf"\b{re.escape(stem)}\b", source) is not None


class TestPRiskBasedTestAllocation:
    """The riskiest modules have tests, and the list says why each is risky."""

    def test_every_critical_module_has_its_tests(self) -> None:
        problems: list[str] = []
        for module, test_files, floor, _why in _RISK_MODULES:
            module_path = ROOT / module
            if not module_path.exists():
                problems.append(f"{module}: the module is gone — update the risk list")
                continue
            missing = [test for test in test_files if not (ROOT / test).exists()]
            if missing:
                problems.append(f"{module}: missing test file(s) {missing}")
                continue
            primary = (ROOT / test_files[0]).read_text(encoding="utf-8")
            if not _names_module(primary, module):
                problems.append(
                    f"{module}: {test_files[0]} never names it, so nothing ties the "
                    "tests to the module"
                )
            count = sum(len(_test_functions(ROOT / test)) for test in test_files)
            if count < floor:
                problems.append(f"{module}: {count} tests < risk floor {floor}")
        assert not problems, (
            "P-RISKTEST: the modules where a wrong branch is expensive lost their "
            "cover, or the list no longer describes the tree:\n  " + "\n  ".join(problems)
        )

    def test_every_entry_explains_the_risk(self) -> None:
        for module, _tests, _floor, why in _RISK_MODULES:
            assert len(why.split()) >= 6, (
                f"{module}: the risk list needs a sentence saying what a wrong branch does"
            )

    def test_the_naming_rule_itself(self) -> None:
        assert _names_module(
            "from fpstune.safety import restore\n", "src/fpstune/safety/restore.py"
        )
        assert _names_module("# the restore module\n", "src/fpstune/safety/restore.py")
        assert not _names_module(
            "from fpstune.safety import history\n", "src/fpstune/safety/restore.py"
        )


# --------------------------------------------------------------------------- #
# P-HERMETIC — the guard in tests/conftest.py, proved rather than assumed
# --------------------------------------------------------------------------- #


def _conftest() -> ModuleType:
    import tests.conftest as conftest

    return conftest


class TestPHermeticNoNetwork:
    """A test reaches the network only through a documented allowlist entry."""

    def test_the_guard_allows_loopback_and_refuses_a_remote_host(self) -> None:
        watch = _conftest().NetworkWatch({"example.com": "the test is about DNS"})
        watch.armed = True

        watch("socket.getaddrinfo", ("localhost", 80, 0, 0, 0))
        watch("socket.getaddrinfo", (None, 80, 0, 0, 0))
        watch("socket.getaddrinfo", ("127.0.0.1", 80, 0, 0, 0))
        watch("socket.connect", (object(), ("127.0.0.1", 8080)))
        watch("socket.connect", (object(), ("::1", 8080, 0, 0)))
        watch("socket.connect", (object(), "C:\\socket.sock"))
        watch("socket.getaddrinfo", ("example.com", 443, 0, 0, 0))
        watch.assert_clean()

        watch("socket.getaddrinfo", ("pypi.org", 443, 0, 0, 0))
        with pytest.raises(AssertionError, match="pypi.org"):
            watch.assert_clean()

    def test_the_hook_is_armed_while_a_test_runs(self) -> None:
        """The autouse fixture arms it before every test; this test is a test."""
        assert _conftest()._NETWORK_WATCH.armed is True

    def test_the_guard_is_wired_as_an_autouse_fixture(self) -> None:
        conftest = (TESTS / "conftest.py").read_text(encoding="utf-8")
        fixture = next(
            node
            for node in ast.walk(ast.parse(conftest))
            if isinstance(node, ast.FunctionDef) and node.name == "_no_network"
        )
        decorator = ast.unparse(fixture.decorator_list[0])
        assert "autouse=True" in decorator, decorator
        assert "_NETWORK_WATCH.assert_clean()" in conftest

    def test_the_allowlist_cannot_rot(self) -> None:
        """Every allowed host has a reason, and a test still names it."""
        allowlist = _conftest().NETWORK_ALLOWLIST
        test_sources = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(TESTS.rglob("*.py"))
        )
        for host, reason in allowlist.items():
            assert reason.strip(), f"NETWORK_ALLOWLIST[{host!r}] has no reason"
            assert host in test_sources, (
                f"NETWORK_ALLOWLIST[{host!r}] is stale: no test names that host any "
                "more, so the exception outlived the reason"
            )


# --------------------------------------------------------------------------- #
# P-MEASURE — the bindings that already exist
# --------------------------------------------------------------------------- #


def _defined_names(path: Path) -> set[str]:
    return {
        node.name
        for node in ast.walk(_parsed(path))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


class TestPMeasureTheInstrumentIsBound:
    """C11's measurement path, and the tests that keep it honest, are still there."""

    def test_the_measurement_path_exists(self) -> None:
        verify_round = ROOT / "src" / "fpstune" / "benchmark" / "verify_round.py"
        sources = ROOT / "src" / "fpstune" / "benchmark" / "sources.py"
        assert verify_round.exists() and sources.exists()

        defined = _defined_names(verify_round)
        for name in ("judge", "measure_pair", "noise_floor"):
            assert name in defined, f"verify_round.{name} is gone; C11 rule 2 cites it"

        tests = (ROOT / "tests" / "test_benchmark" / "test_verify_round.py").read_text(
            encoding="utf-8"
        )
        for name in ("judge", "measure_pair", "noise_floor"):
            assert name in tests, f"nothing in test_verify_round.py names {name}"

    def test_the_unanswered_claims_have_a_place_to_say_so(self) -> None:
        sources = (ROOT / "src" / "fpstune" / "benchmark" / "sources.py").read_text(
            encoding="utf-8"
        )
        assert "NO_INSTRUMENT" in sources
        assert "SOURCES" in sources
        assert (ROOT / "tests" / "test_benchmark" / "test_sources.py").exists()


# --------------------------------------------------------------------------- #
# P-SHIFTLEFT — one registry, earliest stage (scripts/controls.py)
# --------------------------------------------------------------------------- #


def _load_script(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


controls = _load_script("controls", "controls.py")


@pytest.fixture
def stage_tree(tmp_path: Path) -> Path:
    """A minimal three-stage tree the checker can be driven over."""

    def write(relative: str, text: str) -> None:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    write(
        "lefthook.yml",
        "pre-commit:\n  jobs:\n    - run: npm run lint\n",
    )
    write("scripts/quality.sh", "#!/usr/bin/env bash\nnpm run lint\n")
    write(
        ".github/workflows/ci.yml",
        "jobs:\n  frontend:\n    steps:\n      - run: npm run lint\n",
    )
    return tmp_path


def _lint_control(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "id": "fe-lint",
        "command": "npm run lint",
        "stages": ("pre-commit", "pre-push", "ci"),
        "prevents": "an ESLint violation reaching a reviewer",
        "status": "wired",
    }
    values.update(overrides)
    return controls.Control(**values)


class TestPShiftLeftControlRegistry:
    """The registry and the three stage files agree; the checker proves it."""

    def test_the_registry_and_the_stage_files_agree(self) -> None:
        problems = controls.check()
        assert not problems, (
            "P-SSOT/P-SHIFTLEFT: the control registry and the files that run the "
            "controls disagree:\n  " + "\n  ".join(problems)
        )

    def test_every_control_names_what_it_prevents(self) -> None:
        for control in controls.CONTROLS:
            assert control.prevents.strip(), f"{control.id}: no `prevents` sentence"
            assert len(control.prevents.split()) >= 4, (
                f"{control.id}: `prevents` is too short to say anything"
            )

    def test_every_control_names_a_stage_the_checker_knows(self) -> None:
        for control in controls.CONTROLS:
            assert control.stages, f"{control.id}: runs nowhere"
            for stage in control.stages:
                assert stage in controls.STAGES, f"{control.id}: unknown stage {stage!r}"

    def test_a_control_missing_from_its_earliest_stage_is_red(self, stage_tree: Path) -> None:
        (stage_tree / "lefthook.yml").write_text("pre-commit:\n  jobs: []\n", encoding="utf-8")
        problems = controls.check(stage_tree, (_lint_control(),))
        assert any(
            "missing from its earliest stage pre-commit" in problem for problem in problems
        ), problems

    def test_a_duplicate_command_in_one_stage_is_red(self, stage_tree: Path) -> None:
        (stage_tree / "lefthook.yml").write_text(
            "pre-commit:\n  jobs:\n    - run: npm run lint\n    - run: npm run lint\n",
            encoding="utf-8",
        )
        problems = controls.check(stage_tree, (_lint_control(),))
        assert any("runs 2 times at pre-commit" in problem for problem in problems), problems

    def test_a_check_no_control_owns_is_red(self, stage_tree: Path) -> None:
        with (stage_tree / "scripts/quality.sh").open("a", encoding="utf-8") as handle:
            handle.write("python scripts/unregistered.py --check\n")
        problems = controls.check(stage_tree, (_lint_control(),))
        assert any("is not in the control registry" in problem for problem in problems), problems

    def test_a_proposed_control_that_already_runs_is_stale(self, stage_tree: Path) -> None:
        problems = controls.check(stage_tree, (_lint_control(status="proposed"),))
        assert any("set status='wired'" in problem for problem in problems), problems

    def test_a_declared_stage_that_does_not_run_it_is_red(self, stage_tree: Path) -> None:
        (stage_tree / ".github/workflows/ci.yml").write_text(
            "jobs:\n  frontend:\n    steps: []\n", encoding="utf-8"
        )
        problems = controls.check(stage_tree, (_lint_control(),))
        assert any("declared at ci" in problem for problem in problems), problems

    def test_the_clean_fixture_is_green(self, stage_tree: Path) -> None:
        """The negative tests above are only meaningful if the fixture can pass."""
        assert controls.check(stage_tree, (_lint_control(),)) == []


# --------------------------------------------------------------------------- #
# P-SMALLBATCH / P-BOYSCOUT — scripts/diff_budget.py
# --------------------------------------------------------------------------- #

diff_budget = _load_script("diff_budget", "diff_budget.py")


class TestPSmallBatchDiffBudget:
    """A change has a size, and the budget is what makes 'small' reviewable."""

    def test_parsing_a_numstat_line(self) -> None:
        diff = diff_budget.parse_numstat("3\t1\tsrc/fpstune/a.py\n")
        assert diff.files == 1
        assert diff.lines == 4
        assert diff.changes[0] == diff_budget.FileChange(
            path="src/fpstune/a.py", added=3, deleted=1
        )

    def test_a_rename_keeps_the_path_a_reviewer_opens(self) -> None:
        diff = diff_budget.parse_numstat("2\t2\tsrc/old.py => src/new.py\n")
        assert [change.path for change in diff.changes] == ["src/new.py"]

    def test_a_binary_file_counts_as_a_file_with_no_lines(self) -> None:
        diff = diff_budget.parse_numstat("-\t-\tfrontend/public/icon.png\n")
        assert diff.files == 1
        assert diff.lines == 0

    def test_generated_files_are_not_charged_to_the_author(self) -> None:
        """A lockfile's line count is a tool's output, not the change's scope."""
        text = (
            "1000\t0\tuv.lock\n"
            "1000\t0\tfrontend/package-lock.json\n"
            "5\t0\tfrontend/dist/app.js\n"
            "1\t0\tsrc/fpstune/cli.py\n"
        )
        diff = diff_budget.parse_numstat(text)
        assert [change.path for change in diff.changes] == ["src/fpstune/cli.py"]

    def test_the_budget_boundary(self) -> None:
        at_budget = diff_budget.parse_numstat("10\t10\tsrc/fpstune/a.py\n")
        assert diff_budget.evaluate(at_budget, max_files=1, max_lines=20) == []

        one_over = diff_budget.parse_numstat("10\t11\tsrc/fpstune/a.py\n")
        problems = diff_budget.evaluate(one_over, max_files=1, max_lines=20)
        assert problems == ["21 lines added+deleted (budget 20)"]

        too_many = diff_budget.parse_numstat("1\t0\ta.py\n1\t0\tb.py\n")
        assert diff_budget.evaluate(too_many, max_files=1, max_lines=20) == [
            "2 files changed (budget 1)"
        ]

    def test_the_git_command_each_mode_means(self) -> None:
        assert diff_budget.diff_command(staged=True, base=None) == [
            "git",
            "diff",
            "--cached",
            "--numstat",
        ]
        assert diff_budget.diff_command(staged=False, base="origin/main") == [
            "git",
            "diff",
            "--numstat",
            "origin/main...HEAD",
        ]
        assert diff_budget.diff_command(staged=False, base=None) == [
            "git",
            "diff",
            "--numstat",
            "HEAD",
        ]

    def test_the_report_names_the_budget_and_the_biggest_files(self) -> None:
        diff = diff_budget.parse_numstat("8\t2\tsrc/fpstune/a.py\n1\t0\tsrc/fpstune/b.py\n")
        report = diff_budget.report(diff, max_files=12, max_lines=800, problems=[])
        assert "2 file(s), 11 line(s)" in report
        assert "budget 12 file(s) / 800 line(s)" in report
        assert "src/fpstune/a.py" in report

    def test_the_defaults_are_measured_from_history(self) -> None:
        """The docstring records the measurement; the defaults stay near its p75."""
        assert 5 <= diff_budget.DEFAULT_MAX_FILES <= 25
        assert 100 <= diff_budget.DEFAULT_MAX_LINES <= 1500


# --------------------------------------------------------------------------- #
# P-RISKTEST — scripts/risk_coverage.py
# --------------------------------------------------------------------------- #

risk_coverage = _load_script("risk_coverage", "risk_coverage.py")


def _coverage_report(tmp_path: Path, files: dict[str, dict[str, object]]) -> Path:
    import json

    path = tmp_path / "coverage.json"
    path.write_text(json.dumps({"files": files}), encoding="utf-8")
    return path


class TestPRiskCoverageFloors:
    """A repository-wide percentage cannot see a critical module losing its tests."""

    def test_parsing_a_report(self, tmp_path: Path) -> None:
        path = _coverage_report(
            tmp_path,
            {
                "src/fpstune/settings/bulk_plan.py": {
                    "summary": {
                        "percent_covered": 91.5,
                        "covered_lines": 91,
                        "num_statements": 100,
                    }
                }
            },
        )
        measured = risk_coverage.load_report(path)
        assert measured["src/fpstune/settings/bulk_plan.py"].percent == 91.5
        assert measured["src/fpstune/settings/bulk_plan.py"].covered == 91

    def test_absolute_paths_are_normalised(self, tmp_path: Path) -> None:
        absolute = str(ROOT / "src" / "fpstune" / "settings" / "bulk_plan.py")
        path = _coverage_report(
            tmp_path,
            {
                absolute: {
                    "summary": {"percent_covered": 90.0, "covered_lines": 9, "num_statements": 10}
                }
            },
        )
        measured = risk_coverage.load_report(path)
        assert "src/fpstune/settings/bulk_plan.py" in measured

    def test_the_floor_boundary(self) -> None:
        floors = {"src/fpstune/a.py": 80.0}
        at_floor = {
            "src/fpstune/a.py": risk_coverage.ModuleCoverage(
                path="src/fpstune/a.py", percent=80.0, covered=8, statements=10
            )
        }
        assert risk_coverage.evaluate(at_floor, floors) == []

        below = {
            "src/fpstune/a.py": risk_coverage.ModuleCoverage(
                path="src/fpstune/a.py", percent=79.9, covered=7, statements=10
            )
        }
        problems = risk_coverage.evaluate(below, floors)
        assert problems and "79.9% < floor 80%" in problems[0]

    def test_a_module_the_report_never_measured_is_red(self) -> None:
        problems = risk_coverage.evaluate({}, {"src/fpstune/a.py": 80.0})
        assert problems and "not in the coverage report" in problems[0]

    def test_a_malformed_report_is_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "coverage.json"
        path.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError):
            risk_coverage.load_report(path)

    def test_the_floors_are_measured_not_aspirational(self) -> None:
        """Every floor is a percentage a suite can reach; the script documents how."""
        for module, floor in risk_coverage.FLOORS.items():
            assert 0 < floor <= 100, module
            assert module.startswith("src/fpstune/"), module

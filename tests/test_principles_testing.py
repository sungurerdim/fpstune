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
from collections import Counter
from functools import cache
from pathlib import Path

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

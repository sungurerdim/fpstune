"""The change-to-tests selector must put a contract test in front of the change that breaks it.

#104 shipped eleven red `tests/test_windows_contract/*` results to the last gate
because the unit that touched `definitions/network.py` ran only its own tests.
These tests pin each edge the selector follows, and the case where nothing is
selected, over a fixture tree — plus the one acceptance from the issue on the
real repository.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "affected_tests.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("affected_tests", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


affected = _load()


def _write(root: Path, rel: str, text: str = "") -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    _write(tmp_path, "src/pkg/__init__.py")
    _write(tmp_path, "src/pkg/definitions/__init__.py")
    _write(
        tmp_path,
        "src/pkg/definitions/network.py",
        'DOH = Executor(\n    id="network:dns_over_https",\n    name="DoH",\n)\n'
        'PLAIN = Executor(id="network:tcp_auto_tuning")\n',
    )
    _write(tmp_path, "src/pkg/definitions/audio.py", 'A = Executor(id="audio:sample_rate")\n')
    _write(tmp_path, "src/pkg/unrelated.py", "VALUE = 1\n")
    _write(tmp_path, "tests/__init__.py")
    _write(tmp_path, "tests/test_imports.py", "from pkg.definitions.network import DOH\n")
    _write(tmp_path, "tests/test_from_package.py", "from pkg.definitions import network\n")
    _write(
        tmp_path,
        "tests/test_setting_id.py",
        'def test_x():\n    assert get("network:dns_over_https")\n',
    )
    _write(tmp_path, "tests/test_dotted.py", 'PATCH = "pkg.definitions.network.run"\n')
    _write(tmp_path, "tests/test_filename.py", "# reads pkg/definitions/network.py as text\n")
    _write(tmp_path, "tests/test_barename.py", "# network.py is read as text\n")
    _write(tmp_path, "tests/test_audio.py", "from pkg.definitions.audio import A\n")
    _write(tmp_path, "tests/test_nothing.py", "def test_ok():\n    assert True\n")
    _write(tmp_path, "tests/contract/__init__.py")
    _write(tmp_path, "tests/contract/conftest.py", "FIXTURE = 1\n")
    _write(tmp_path, "tests/contract/test_a.py", "from .conftest import FIXTURE\n")
    _write(tmp_path, "tests/contract/test_b.py", "def test_b():\n    assert True\n")
    return tmp_path


def test_import_edge_selects_the_importing_test(tree: Path) -> None:
    selected = affected.select(tree, ["src/pkg/definitions/network.py"])
    assert (
        "imports pkg.definitions.network (src/pkg/definitions/network.py)"
        in selected["tests/test_imports.py"]
    )
    # `from package import module` imports the module too.
    assert any(
        "imports pkg.definitions.network" in r for r in selected["tests/test_from_package.py"]
    )


def test_setting_id_edge_selects_a_test_that_only_names_the_id(tree: Path) -> None:
    selected = affected.select(tree, ["src/pkg/definitions/network.py"])
    reasons = selected["tests/test_setting_id.py"]
    assert reasons == [
        "names setting id network:dns_over_https (defined in src/pkg/definitions/network.py)"
    ]


def test_dotted_name_and_file_name_edges(tree: Path) -> None:
    selected = affected.select(tree, ["src/pkg/definitions/network.py"])
    assert "names module pkg.definitions.network" in selected["tests/test_dotted.py"][0]
    assert "names path pkg/definitions/network.py" in selected["tests/test_filename.py"][0]
    assert "names file network.py" in selected["tests/test_barename.py"][0]


def test_unrelated_tests_are_left_out(tree: Path) -> None:
    selected = affected.select(tree, ["src/pkg/definitions/network.py"])
    assert "tests/test_audio.py" not in selected
    assert "tests/test_nothing.py" not in selected


def test_package_change_does_not_select_every_submodule_user(tree: Path) -> None:
    # Only the whole name `pkg.definitions` matters for a package; a test that
    # names `pkg.definitions.network` is not a test of `definitions/__init__`.
    selected = affected.select(tree, ["src/pkg/definitions/__init__.py"])
    assert "tests/test_dotted.py" not in selected
    assert "tests/test_imports.py" not in selected
    # It does import the package itself, as `from pkg.definitions import network`.
    assert "tests/test_from_package.py" in selected


def test_conftest_change_selects_its_directory_only(tree: Path) -> None:
    selected = affected.select(tree, ["tests/contract/conftest.py"])
    assert {"tests/contract/test_a.py", "tests/contract/test_b.py"} <= selected.keys()
    assert "tests/test_nothing.py" not in selected
    assert (
        "changed: fixtures for everything beneath tests/contract/"
        in selected["tests/contract/test_b.py"][0]
    )
    # test_a also reaches the conftest through its relative import.
    assert any("imports tests.contract.conftest" in r for r in selected["tests/contract/test_a.py"])


def test_changed_test_file_selects_itself(tree: Path) -> None:
    selected = affected.select(tree, ["tests/test_nothing.py"])
    assert selected == {"tests/test_nothing.py": ["tests/test_nothing.py changed itself"]}


def test_unrelated_source_file_selects_nothing(tree: Path) -> None:
    assert affected.select(tree, ["src/pkg/unrelated.py"]) == {}


def test_non_python_change_selects_nothing(tree: Path) -> None:
    assert affected.select(tree, ["README.md", "frontend/src/App.tsx"]) == {}


def test_nothing_selected_is_printed_not_silent(capsys: pytest.CaptureFixture[str]) -> None:
    affected.report({}, ["src/pkg/unrelated.py"])
    assert "affected_tests: nothing selected" in capsys.readouterr().out
    affected.report({}, ["README.md"])
    assert "nothing selected (no Python file changed)" in capsys.readouterr().out


def test_report_names_every_test_and_its_reason(capsys: pytest.CaptureFixture[str]) -> None:
    affected.report({"tests/test_a.py": ["imports pkg.a (src/pkg/a.py)"]}, ["src/pkg/a.py"])
    out = capsys.readouterr().out
    assert "tests/test_a.py" in out and "<- imports pkg.a (src/pkg/a.py)" in out


def test_setting_ids_are_read_from_keyword_literals_only(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "defs.py",
        'A = X(id="net:one")\nB = X(id=f"net:{k}:two")\nC = X(name="net:three")\nD = X(id="noColon")\n',
    )
    assert affected.setting_ids((tmp_path / "defs.py").read_text(encoding="utf-8")) == ["net:one"]


def test_worker_count_halves_the_cores_and_never_exceeds_the_files() -> None:
    assert affected.worker_count(40, cores=16) == 8
    assert affected.worker_count(3, cores=16) == 3
    assert affected.worker_count(5, cores=1) == 1


def test_git_diff_collects_modified_and_untracked_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Under a git hook GIT_DIR / GIT_INDEX_FILE point at the real repository:
    # without this the fixture's `git add .` stages into the committer's index
    # and the commit dies on an object that is not there (seen on the first try).
    for name in [n for n in os.environ if n.startswith("GIT_")]:
        monkeypatch.delenv(name)

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    _write(tmp_path, "src/pkg/a.py", "A = 1\n")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    _write(tmp_path, "src/pkg/a.py", "A = 2\n")
    _write(tmp_path, "tests/test_new.py", "")
    assert sorted(affected.changed_files(tmp_path, "HEAD", staged=False)) == [
        "src/pkg/a.py",
        "tests/test_new.py",
    ]
    git("add", "src/pkg/a.py")
    assert affected.changed_files(tmp_path, None, staged=True) == ["src/pkg/a.py"]


def test_real_repo_network_definitions_select_the_doh_contract_test() -> None:
    """The issue's acceptance: touching definitions/network.py runs the DoH contract test."""
    selected = affected.select(REPO, ["src/fpstune/settings/definitions/network.py"])
    reasons = selected["tests/test_windows_contract/test_dns_over_https.py"]
    assert any(r.startswith("imports fpstune.settings.definitions.network") for r in reasons)

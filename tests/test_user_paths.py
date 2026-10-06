"""Where a user-profile root is resolved: one module, redirected in every test.

Incident (2026-10-06, #104): an ad-hoc sweep applied every setting's
recommended value with the PowerShell, registry, netsh, powercfg and NVIDIA
seams patched but not the Python file writers, and rewrote the developer's real
Call of Duty options file and Battle.net.config. The suite redirected only
``USERPROFILE``; ``%LOCALAPPDATA%`` and ``%APPDATA%`` stayed real, and every
discovery function that read them wrote through to the real files.

Three bindings, one per way the class comes back:

* the source — no module outside ``utils/user_paths.py`` reads a profile root,
  so there is one place to redirect (AST scan below);
* the redirect — ``conftest.py`` points every root at a per-test tree;
* the characterization — each discovery function still answers what it did.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.conftest import ProfileWriteWatch

SRC = Path(__file__).resolve().parents[1] / "src" / "fpstune"
HELPER = SRC / "utils" / "user_paths.py"

# The variables that name a user-profile root. Machine-wide ones (ProgramData,
# SystemRoot, ProgramFiles) are not a user's profile.
PROFILE_VARIABLES = frozenset({"LOCALAPPDATA", "APPDATA", "USERPROFILE", "HOME"})


def _violations(tree: ast.AST) -> list[tuple[int, str]]:
    """(line, what) for each direct profile-root resolution in one module."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = ast.unparse(func)
            first = node.args[0] if node.args else None
            literal = (
                first.value.upper()
                if isinstance(first, ast.Constant) and isinstance(first.value, str)
                else None
            )
            if name in {"os.environ.get", "os.getenv", "os.environ.setdefault"}:
                if literal in PROFILE_VARIABLES:
                    found.append((node.lineno, f"{name}({literal})"))
            elif name in {"Path.home", "pathlib.Path.home", "os.path.expanduser"}:
                found.append((node.lineno, name))
            elif isinstance(func, ast.Attribute) and func.attr == "expanduser":
                found.append((node.lineno, "expanduser()"))
        elif isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
            key = node.slice
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value.upper() in PROFILE_VARIABLES
            ):
                found.append((node.lineno, f"os.environ[{key.value}]"))
        elif isinstance(node, ast.Constant) and node.value == ".fpstune":
            found.append((node.lineno, "the '.fpstune' directory name"))
    return found


def test_no_source_file_resolves_a_profile_root_outside_the_helper() -> None:
    """Guards the scattered resolution that let a test reach the real profile."""
    offences: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path == HELPER:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(SRC.parent.parent).as_posix()
        offences.extend(f"{rel}:{line}: {what}" for line, what in _violations(tree))
    assert not offences, (
        "profile roots must come from fpstune.utils.user_paths, found:\n  " + "\n  ".join(offences)
    )


def test_the_scan_sees_each_form_it_claims_to_forbid() -> None:
    """The scanner is itself checked: a form it misses is a hole in the guard."""
    sample = ast.parse(
        "import os\n"
        "from pathlib import Path\n"
        "a = os.environ.get('LocalAppData')\n"
        "b = os.getenv('APPDATA')\n"
        "c = os.environ['USERPROFILE']\n"
        "d = Path.home()\n"
        "e = Path('~').expanduser()\n"
        "f = base / '.fpstune'\n"
        "g = os.environ.get('SYSTEMROOT')\n"
    )
    assert [line for line, _ in _violations(sample)] == [3, 4, 5, 6, 7, 8]


# ---------------------------------------------------------------------------
# The redirect: no discovery function answers with a real root inside a test.
# ---------------------------------------------------------------------------


def _real(name: str) -> Path | None:
    from tests.conftest import REAL_PROFILE_ROOTS

    value = REAL_PROFILE_ROOTS.get(name)
    return Path(value) if value else None


@pytest.mark.skipif(sys.platform != "win32", reason="the roots are Windows variables")
def test_every_profile_root_is_redirected_away_from_the_real_one() -> None:
    """Guards the incident: only USERPROFILE was redirected, the writers read the others."""
    for name in ("LOCALAPPDATA", "APPDATA", "USERPROFILE"):
        real = _real(name)
        current = os.environ.get(name)
        assert current, f"{name} is unset inside a test"
        assert real is None or os.path.normcase(current) != os.path.normcase(str(real)), (
            f"{name} still names the real profile: {current}"
        )


@pytest.mark.skipif(sys.platform != "win32", reason="config path is Windows-only")
def test_the_battle_net_writer_cannot_resolve_the_real_file() -> None:
    from fpstune.settings.executors import bnet_config

    path = bnet_config.config_path()
    real = _real("APPDATA")
    assert path is not None
    assert real is None or not str(path).lower().startswith(str(real).lower() + os.sep)


@pytest.mark.skipif(sys.platform != "win32", reason="MW4 lives under a Windows profile")
def test_the_mw4_discovery_root_cannot_resolve_the_real_profile() -> None:
    from fpstune.settings.executors import game_config_cache

    root = game_config_cache._local_app_data_dir()
    real = _real("LOCALAPPDATA")
    assert root is not None
    assert real is None or os.path.normcase(str(root)) != os.path.normcase(str(real))


def test_a_real_root_handed_back_by_the_helper_fails_the_test(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The backstop: a test that un-redirects a root is refused at the helper."""
    from fpstune.utils import user_paths

    real = _real("USERPROFILE")
    if real is None:
        pytest.skip("this runner has no USERPROFILE to protect")
    monkeypatch.setenv("USERPROFILE", str(real))
    with pytest.raises(AssertionError, match="real user profile"):
        user_paths.home()


# ---------------------------------------------------------------------------
# The backstop is process-local: it counts what THIS process writes under a real
# root, and nothing another process does. The real profile is never touched here;
# a fake "real root" under tmp_path is what the hook is told to watch.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def probe() -> ProfileWriteWatch:
    """One installed hook for the module (an audit hook cannot be removed again)."""
    watch = ProfileWriteWatch()
    sys.addaudithook(watch)
    return watch


@pytest.fixture
def watched(probe: ProfileWriteWatch, tmp_path: Path) -> Iterator[tuple[ProfileWriteWatch, Path]]:
    """The probe watching ``tmp_path / "real"``, armed, and inert again afterwards."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "Battle.net.config").write_text("{}", encoding="utf-8")
    probe.watch([str(real)])
    probe.offenders.clear()
    probe.armed = True
    try:
        yield probe, real
    finally:
        probe.armed = False
        probe.watch([])
        probe.offenders.clear()


def _write(path: Path, mode: str) -> None:
    with open(path, mode) as handle:
        handle.write("x" if "b" not in mode else b"x")


def _create_with_os_open(path: Path) -> None:
    os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))


def _replace_onto(path: Path) -> None:
    # The source sits outside the watched root on purpose: the target alone is the offence.
    outside = path.parents[1] / "incoming.tmp"
    outside.write_text("x", encoding="utf-8")
    os.replace(outside, path)


def _rename_away(path: Path) -> None:
    os.rename(path, path.parents[1] / "moved-out.cfg")


def _remove(path: Path) -> None:
    os.remove(path)


def _copy_onto(path: Path) -> None:
    shutil.copyfile(path.parents[1] / "elsewhere.cfg", path)


def _move_onto(path: Path) -> None:
    shutil.move(str(path.parents[1] / "elsewhere.cfg"), str(path))


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path.parent)


@pytest.mark.parametrize(
    "act",
    [
        pytest.param(lambda p: _write(p, "w"), id="open-w"),
        pytest.param(lambda p: _write(p, "a"), id="open-a"),
        pytest.param(lambda p: _write(p, "r+"), id="open-r+"),
        pytest.param(lambda p: _write(p, "wb"), id="open-wb"),
        pytest.param(lambda p: p.write_text("x", encoding="utf-8"), id="path-write_text"),
        pytest.param(_create_with_os_open, id="os.open-create"),
        pytest.param(_replace_onto, id="os.replace-target"),
        pytest.param(_rename_away, id="os.rename-source"),
        pytest.param(_remove, id="os.remove"),
        pytest.param(_copy_onto, id="shutil.copyfile"),
        pytest.param(_move_onto, id="shutil.move"),
        pytest.param(_remove_tree, id="shutil.rmtree"),
    ],
)
def test_a_write_under_the_real_root_fails_the_test(watched, act) -> None:
    """Guards the incident: this process rewrote a real file and nothing said so."""
    probe, real = watched
    (real.parent / "elsewhere.cfg").write_text("x", encoding="utf-8")
    target = real / "Battle.net.config"
    if act is _create_with_os_open:
        target = real / "created.cfg"

    act(target)

    with pytest.raises(AssertionError, match="real user profile") as caught:
        probe.assert_clean()
    assert real.name in str(caught.value)


def test_reading_under_the_real_root_is_not_a_write(watched) -> None:
    probe, real = watched
    target = real / "Battle.net.config"

    target.read_text(encoding="utf-8")
    target.read_bytes()
    target.stat()
    list(real.iterdir())
    os.close(os.open(target, os.O_RDONLY))

    probe.assert_clean()


def test_a_write_outside_the_real_root_is_not_counted(watched, tmp_path: Path) -> None:
    probe, real = watched

    (tmp_path / "somewhere-else.cfg").write_text("x", encoding="utf-8")
    sibling = tmp_path / "real-but-not-under-it"
    sibling.mkdir()
    (sibling / "a.cfg").write_text("x", encoding="utf-8")

    probe.assert_clean()


def test_another_process_writing_the_watched_file_is_not_counted(watched) -> None:
    """The false positive that retired the modification-time check.

    The developer's running Battle.net client rewrites its own config while the
    suite runs. The file changes; this process did not change it.
    """
    probe, real = watched
    target = real / "Battle.net.config"

    subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; open(sys.argv[1], 'w').write('rewritten')",
            str(target),
        ],
        check=True,
        timeout=60,
    )

    assert target.read_text(encoding="utf-8") == "rewritten", "precondition: the file did change"
    probe.assert_clean()


def test_a_write_while_disarmed_is_not_counted(watched) -> None:
    """Between tests (collection, session fixtures) nothing is judged."""
    probe, real = watched
    probe.armed = False

    (real / "Battle.net.config").write_text("x", encoding="utf-8")

    probe.assert_clean()


def test_the_interpreters_bytecode_cache_under_a_root_is_not_the_profile(watched) -> None:
    probe, real = watched
    cache = real / "pkg" / "__pycache__"
    probe.armed = False  # building the directory is the setup, not the act under test
    cache.mkdir(parents=True)
    probe.armed = True

    (cache / "mod.cpython-312.pyc").write_bytes(b"x")

    probe.assert_clean()


def test_the_suites_hook_watches_the_real_roots_captured_before_the_redirect() -> None:
    """Not the redirected tree: that one is where every test is meant to write."""
    from tests.conftest import _WATCH, REAL_PROFILE_ROOTS

    expected = {os.path.normcase(os.path.abspath(v)) for v in REAL_PROFILE_ROOTS.values()}
    assert set(_WATCH.roots) == expected
    assert os.path.normcase(os.path.abspath(os.environ.get("APPDATA", "."))) not in _WATCH.roots


def test_the_temporary_directory_is_not_the_profile(tmp_path: Path) -> None:
    """pytest's own ``tmp_path`` sits under the real %LOCALAPPDATA%; every test writes there."""
    from tests.conftest import _WATCH

    _WATCH.offenders.clear()

    (tmp_path / "scratch.txt").write_text("x", encoding="utf-8")

    assert _WATCH.offenders == []


# ---------------------------------------------------------------------------
# Characterization: each discovery function answers what it answered before.
# ---------------------------------------------------------------------------


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    home = tmp_path / "user"
    local = home / "AppData" / "Local"
    roaming = home / "AppData" / "Roaming"
    for folder in (local, roaming):
        folder.mkdir(parents=True)
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))
    return {"home": home, "local": local, "roaming": roaming}


def test_fpstune_home_is_dot_fpstune_under_the_profile_and_exists(
    roots: dict[str, Path],
) -> None:
    from fpstune.utils.config import get_config_dir

    folder = get_config_dir()
    assert folder == roots["home"] / ".fpstune"
    assert folder.is_dir()


def test_the_engine_log_sits_under_the_profile(roots: dict[str, Path]) -> None:
    from fpstune.benchmark.gpu_scene import engine_log_path

    assert engine_log_path() == roots["home"] / "Superposition" / "log.html"


@pytest.mark.skipif(sys.platform != "win32", reason="config path is Windows-only")
def test_battle_net_config_sits_under_roaming_appdata(roots: dict[str, Path]) -> None:
    from fpstune.settings.executors import bnet_config

    assert bnet_config.config_path() == roots["roaming"] / "Battle.net" / "Battle.net.config"


@pytest.mark.skipif(sys.platform != "win32", reason="MW4 lives under a Windows profile")
def test_mw4_local_appdata_falls_back_to_the_variable(roots: dict[str, Path]) -> None:
    from fpstune.settings.executors import game_config_cache

    assert game_config_cache._local_app_data_dir() == roots["local"]


@pytest.mark.skipif(sys.platform != "win32", reason="Documents lookup is Windows-only")
def test_documents_fall_back_to_the_profile_when_it_exists(
    roots: dict[str, Path],
) -> None:
    from fpstune.settings.executors import game_config_cache

    assert game_config_cache._documents_dir() is None
    (roots["home"] / "Documents").mkdir()
    assert game_config_cache._documents_dir() == roots["home"] / "Documents"


def test_nvidia_app_config_is_under_local_appdata(roots: dict[str, Path]) -> None:
    from fpstune.settings.executors import nvidia_app

    path = nvidia_app._config_path()
    assert path is not None
    assert path.parts[: len(roots["local"].parts)] == roots["local"].parts


@pytest.mark.usefixtures("roots")
def test_nvidia_app_config_is_absent_without_the_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    from fpstune.settings.executors import nvidia_app

    monkeypatch.delenv("LOCALAPPDATA")
    assert nvidia_app._config_path() is None


def test_the_headroom_file_is_in_the_state_directory() -> None:
    from fpstune.settings import performance_headroom

    assert performance_headroom.HEADROOM_PATH.name == "headroom.json"
    assert performance_headroom.HEADROOM_PATH.parent.name == ".fpstune"


def test_the_powershell_module_cache_is_pinned_under_local_appdata(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from fpstune.utils import system_tools

    monkeypatch.delenv(system_tools.MODULE_CACHE_VARIABLE, raising=False)
    system_tools.pin_powershell_module_cache()
    pinned = os.environ[system_tools.MODULE_CACHE_VARIABLE]
    assert pinned == str(
        roots["local"] / "Microsoft" / "Windows" / "PowerShell" / "ModuleAnalysisCache"
    )


def test_cleanup_roots_read_the_profile_variables_and_strip_blanks(
    roots: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from fpstune.settings import cleanup_targets

    assert cleanup_targets._env("LOCALAPPDATA") == str(roots["local"])
    assert cleanup_targets._env("APPDATA") == str(roots["roaming"])
    assert cleanup_targets._env("USERPROFILE") == str(roots["home"])
    monkeypatch.setenv("APPDATA", "   ")
    assert cleanup_targets._env("APPDATA") is None


@pytest.mark.skipif(sys.platform != "win32", reason="WSA probe is Windows-only")
def test_wsa_probe_looks_under_local_appdata_packages(roots: dict[str, Path]) -> None:
    from fpstune.settings import virtualization

    assert virtualization._windows_subsystem_for_android() is None
    package = roots["local"] / "Packages" / f"{virtualization._WSA_PACKAGE_PREFIX}_8wekyb3d8bbwe"
    package.mkdir(parents=True)
    found = virtualization._windows_subsystem_for_android()
    assert found is not None
    assert found.key == "wsa"

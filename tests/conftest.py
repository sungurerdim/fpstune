"""Pytest configuration and fixtures for fpstune tests."""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import sys
import tempfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# --- User-profile roots: nothing in a test may reach the real profile (#104) ---
#
# On 2026-10-06 a sweep applying every setting rewrote the developer's real Call
# of Duty options file and Battle.net.config, because only USERPROFILE was
# redirected and the writers read %LOCALAPPDATA% and %APPDATA%. This block runs
# before any fpstune import, so module-level constants that resolve a root at
# import (headroom.json) land in a throwaway tree too. Each test then gets its
# own tree (`_isolated_profile`), and an audit hook is the backstop
# (`_real_profile_untouched`): it sees only what THIS process opens for writing,
# renames or removes under a real root. A file's modification time cannot tell
# who wrote it, and the developer's own Battle.net client rewrites its config
# while the suite runs.
_REAL_PROFILE_MARK = "FPSTUNE_TEST_REAL_PROFILE"
# ProgramData is machine-wide, not a user's profile, but the cleanups delete under it
# and the audit hook has to see a write to it all the same (#106).
_ROOT_VARIABLES = ("LOCALAPPDATA", "APPDATA", "USERPROFILE", "PROGRAMDATA")
# The older spelling of ProgramData's variable; read by PowerShell scripts.
_ALIAS_VARIABLES = ("ALLUSERSPROFILE",)

if _REAL_PROFILE_MARK in os.environ:
    # A pytest-xdist worker inherits the controller's already-redirected
    # environment; the real roots travel in the mark instead.
    REAL_PROFILE_ROOTS: dict[str, str] = json.loads(os.environ[_REAL_PROFILE_MARK])
else:
    REAL_PROFILE_ROOTS = {
        name: os.environ[name] for name in _ROOT_VARIABLES if os.environ.get(name)
    }
    os.environ[_REAL_PROFILE_MARK] = json.dumps(REAL_PROFILE_ROOTS)


def _point_roots_at(home: Path) -> None:
    """Send every user-profile root of this process into ``home``."""
    local = home / "AppData" / "Local"
    roaming = home / "AppData" / "Roaming"
    local.mkdir(parents=True, exist_ok=True)
    roaming.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    os.environ["LOCALAPPDATA"] = str(local)
    os.environ["APPDATA"] = str(roaming)
    program_data = home / "ProgramData"
    # The shell expands the all-users Startup folder from %PROGRAMDATA% and answers
    # "" for one that does not exist, so a child asking
    # [Environment]::GetFolderPath('CommonStartup') needs the place to be there.
    (program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "StartUp").mkdir(
        parents=True, exist_ok=True
    )
    os.environ["PROGRAMDATA"] = str(program_data)
    os.environ["ALLUSERSPROFILE"] = str(program_data)


_SESSION_PROFILE = tempfile.TemporaryDirectory(prefix="fpstune-test-profile-")
_point_roots_at(Path(_SESSION_PROFILE.name))


# Events that write, by the position of the path(s) they carry in the audit args.
_WRITE_PATH_ARGS: dict[str, tuple[int, ...]] = {
    "os.rename": (0, 1),  # os.replace emits this too: the source goes, the target is written
    "os.remove": (0,),
    "os.rmdir": (0,),
    "os.mkdir": (0,),
    "os.truncate": (0,),
    "shutil.copyfile": (1,),
    "shutil.copytree": (1,),
    "shutil.move": (0, 1),
    "shutil.rmtree": (0,),
}
_WRITE_MODE_CHARACTERS = frozenset("wax+")
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


class ProfileWriteWatch:
    """Audit hook: which paths under a real profile root did THIS process change?

    ``sys.addaudithook`` is per interpreter, so a write another process makes (a
    running Battle.net client, an editor, an antivirus) is invisible to it by
    construction; only this test process's own opens-for-write, renames, removals
    and shutil moves count. Reads are never recorded.

    Two kinds of path under a root are not the profile's own: the temporary
    directory (pytest's ``tmp_path`` lives in the Temp folder under ``%LOCALAPPDATA%``) and
    ``__pycache__`` (the interpreter caches the standard library next to it).

    The hook records and never raises: an exception thrown from an audit hook
    lands inside whatever call was being audited, in production code, far from
    the test that caused it. ``assert_clean`` reports at the test's boundary.
    """

    def __init__(self, roots: Iterable[str] = (), ignored: Iterable[str] = ()) -> None:
        self.roots: tuple[str, ...] = ()
        self.ignored: tuple[str, ...] = ()
        self.armed = False
        self.offenders: list[str] = []
        self.watch(roots, ignored)

    @staticmethod
    def _normal(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    def watch(self, roots: Iterable[str], ignored: Iterable[str] = ()) -> None:
        self.roots = tuple(self._normal(r) for r in roots if r)
        self.ignored = tuple(self._normal(i) for i in ignored if i)

    @staticmethod
    def _inside(path: str, root: str) -> bool:
        return path == root or path.startswith(root.rstrip(os.sep) + os.sep)

    def _consider(self, raw: object) -> None:
        # An int is a file descriptor and carries no path; anything else that is
        # not a path (None for a dir_fd-only call) is not ours to judge.
        if not isinstance(raw, str | bytes | os.PathLike):
            return
        path = os.fsdecode(raw)
        normal = self._normal(path)
        if "__pycache__" in normal.split(os.sep):
            return
        if any(self._inside(normal, ignored) for ignored in self.ignored):
            return
        if any(self._inside(normal, root) for root in self.roots):
            self.offenders.append(path)

    def __call__(self, event: str, args: tuple[object, ...]) -> None:
        if not self.armed or not self.roots:
            return
        if event == "open":
            _path, mode, flags = args
            writes = (isinstance(mode, str) and not _WRITE_MODE_CHARACTERS.isdisjoint(mode)) or (
                isinstance(flags, int) and bool(flags & _WRITE_FLAGS)
            )
            if writes:
                self._consider(args[0])
            return
        for position in _WRITE_PATH_ARGS.get(event, ()):
            self._consider(args[position])

    def assert_clean(self) -> None:
        offenders, self.offenders = self.offenders, []
        assert not offenders, f"a test wrote to the real user profile: {sorted(set(offenders))}"


_WATCH = ProfileWriteWatch(
    REAL_PROFILE_ROOTS.values(),
    ignored=(tempfile.gettempdir(), _SESSION_PROFILE.name),
)
sys.addaudithook(_WATCH)


# --- Network destinations: a test reaches the network only by saying so (P-HERMETIC) ---
#
# The catalogue's P-HERMETIC rule is that a test depends on neither the network,
# the clock nor ordering. The clock and ordering already have their own guards
# (the `timing` marker, `_no_host_processes`); the network did not. A test that
# resolves a real name or connects to a real host is not a test of this
# repository — it is a test of the machine's DNS and of the internet being
# reachable. It passes on a developer's machine and fails on a runner without
# network, and the failure is reported against the product rather than the test.
#
# Nothing in the suite needs it: every outbound call that is the subject of a
# test patches `urllib.request.urlopen` (test_updates, test_download,
# test_presentmon) or runs in a child process, which this hook cannot see by
# construction. Loopback stays allowed because several tests run a real local
# server and talk to it (uvicorn on 127.0.0.1 in test_shutdown_route, a bound
# socket in test_winapi_processes): a machine talking to itself is hermetic.
#
# A test that genuinely must reach a named host adds it here with the reason,
# and `tests/test_principles_testing.py` holds the allowlist to that shape: an
# entry without a reason, or one no test names any more, is red there.
NETWORK_ALLOWLIST: dict[str, str] = {}

# Names that mean this machine; `getaddrinfo` accepts them, `ipaddress` does not.
_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"})

# Every audit event that names an outward destination. `socket.bind` is not one:
# binding a port is local, and the tests that do it are the loopback servers.
_NETWORK_EVENTS = frozenset(
    {
        "socket.connect",
        "socket.getaddrinfo",
        "socket.getnameinfo",
        "socket.gethostbyname",
        "socket.gethostbyaddr",
    }
)


def _host_is_local(host: object) -> bool:
    """True for the loopback interface and for "no host" (a local/passive lookup)."""
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str):
        # An address shape this hook cannot read is not evidence of a remote
        # destination; the real calls it can read carry a str.
        return True
    host = host.strip()
    if not host or host in {"0.0.0.0", "::"}:
        return True
    if host.casefold() in _LOOPBACK_NAMES:
        return True
    bare = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    # An IPv6 zone index ("fe80::1%eth0") is not part of the address.
    bare = bare.split("%", 1)[0]
    try:
        return ipaddress.ip_address(bare).is_loopback
    except ValueError:
        return False


class NetworkWatch:
    """Audit hook: which non-loopback destinations did THIS process reach?

    Like `ProfileWriteWatch`, it records and never raises: an exception thrown
    from an audit hook lands inside whatever call was being audited, in
    production code, far from the test that caused it. The verdict is reported
    at the test's boundary (`_no_network`).

    The socket module raises these events from C, before the syscall, so a
    connection that is refused or times out is still seen; a call another
    process makes (a child fpstune, a PowerShell probe) is invisible here by
    construction, which is correct — the suite's own rule is about what the
    test process itself reaches.
    """

    def __init__(self, allowlist: dict[str, str] | None = None) -> None:
        self.allowlist = dict(allowlist or {})
        self.armed = False
        self.offenders: list[str] = []

    def _judge(self, event: str, host: object) -> None:
        if _host_is_local(host):
            return
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        if isinstance(host, str) and host.strip().casefold() in {
            allowed.casefold() for allowed in self.allowlist
        }:
            return
        self.offenders.append(f"{event} -> {host!r}")

    def __call__(self, event: str, args: tuple[object, ...]) -> None:
        if not self.armed or event not in _NETWORK_EVENTS:
            return
        if event == "socket.connect":
            address = args[1] if len(args) > 1 else None
            # AF_UNIX carries a filesystem path, not a destination on the wire.
            if isinstance(address, tuple) and address:
                self._judge(event, address[0])
            return
        if event == "socket.getnameinfo":
            address = args[0] if args else None
            if isinstance(address, tuple) and address:
                self._judge(event, address[0])
            return
        self._judge(event, args[0] if args else None)

    def assert_clean(self) -> None:
        offenders, self.offenders = self.offenders, []
        assert not offenders, (
            "a test reached the network (P-HERMETIC): "
            + ", ".join(sorted(set(offenders)))
            + ". Patch the call the test is about (urllib.request.urlopen and the "
            "socket the code uses are the two seams the suite already fakes), or — "
            "if the connection really is the subject — add the host to "
            "NETWORK_ALLOWLIST in tests/conftest.py with the reason."
        )


_NETWORK_WATCH = NetworkWatch(NETWORK_ALLOWLIST)
sys.addaudithook(_NETWORK_WATCH)


from fpstune.settings.applicability import HardwareContext  # noqa: E402
from fpstune.utils import user_paths as _user_paths  # noqa: E402

# The operating system's own answers, kept before `_isolated_profile` silences them,
# so the test that pins what they return on this machine can still ask.
REAL_SHELL_LOOKUPS = (_user_paths._shell_folders_value, _user_paths._known_folder)

# Mock Windows-specific modules when running on non-Windows
if sys.platform != "win32":
    # mimetypes binds winreg at import time and walks it on first use; importing
    # it before the stub keeps it off the registry path it cannot have here.
    import mimetypes

    mimetypes.init()
    sys.modules["winreg"] = MagicMock()
    # Mock subprocess.CREATE_NO_WINDOW for non-Windows
    if not hasattr(__import__("subprocess"), "CREATE_NO_WINDOW"):
        import subprocess

        subprocess.CREATE_NO_WINDOW = 0x08000000


@pytest.fixture(autouse=True, scope="session")
def _operation_lock_per_process() -> None:
    """Each test process takes its own operation lock, never the machine's.

    The lock is a machine-wide named mutex on purpose: one apply, cleanup or
    bench at a time. The suite runs in parallel worker processes, so under the
    shipped name a test in one worker holding the lock read as "the machine is
    busy" to a bench test in another, and three suite-route tests went red. A
    running fpstune on the developer's machine would do the same.
    """
    import os

    from fpstune.benchmark import operation_lock

    operation_lock.OPERATION_MUTEX = f"{operation_lock.OPERATION_MUTEX}-test-{os.getpid()}"


@pytest.fixture
def windows_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let Windows-gated pure-Python logic run on a development host.

    Game config files are plain text rewritten in Python, but every reader and
    writer answers "not installed" off Windows. A test that builds its install
    under ``tmp_path`` asks for this fixture to exercise that logic anyway.

    On Windows it does nothing, so the real system mutex stays under test there.
    Elsewhere it fakes the platform and sends ``file_lock`` to its documented
    process-local fallback, because kernel32 does not exist to be called.
    """
    if sys.platform == "win32":
        return
    # Imported against the real platform first: the power definitions adopt
    # Windows' own defaults from the registry at import, and a faked platform
    # would send that one-time read to the winreg stub above.
    from fpstune.settings.definitions import get_all_static_settings
    from fpstune.settings.executors import game_config_writer

    get_all_static_settings()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(game_config_writer, "_take_system_mutex", lambda _name: None)


@pytest.fixture(autouse=True)
def _isolated_profile(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every test gets its own user profile, never the runner's.

    `utils.user_paths` resolves every root (home, %LOCALAPPDATA%, %APPDATA%,
    ~/.fpstune, Documents, ProgramData) at call time, and the suite drives the real apply, scan and
    bench paths: without this, a run wrote bench results, the self-check and
    game config lines into the developer's own profile, and read them back in
    the next test. The process-wide stores are dropped too, so none carries one
    test's state into another.

    The helper is also wrapped so that a root which resolves to the real profile
    fails the test at the moment it is handed out: a test that un-redirects a
    variable is refused before anything is written.
    """
    from fpstune.settings import performance_headroom
    from fpstune.utils import user_paths

    home = tmp_path_factory.mktemp("home")
    # monkeypatch.setenv registers the restore; _point_roots_at assigns.
    for name in ("HOME", *_ROOT_VARIABLES, *_ALIAS_VARIABLES):
        monkeypatch.setenv(name, os.environ[name])
    _point_roots_at(home)
    monkeypatch.setattr(performance_headroom, "HEADROOM_PATH", home / ".fpstune" / "headroom.json")
    # The two answers an environment variable cannot redirect: the console user's
    # Shell Folders key and SHGetKnownFolderPath. A test sees a shell that says
    # nothing, so Documents is `<home>\Documents` and ProgramData is the
    # redirected `%PROGRAMDATA%`, both in the throwaway tree.
    monkeypatch.setattr(user_paths, "_shell_folders_value", lambda _name: None)
    monkeypatch.setattr(user_paths, "_known_folder", lambda _folder_id: None)

    real = {os.path.normcase(os.path.normpath(v)) for v in REAL_PROFILE_ROOTS.values()}
    resolve = user_paths.profile_env

    def guarded(name: str) -> str | None:
        value = resolve(name)
        if value is not None and os.path.normcase(os.path.normpath(value)) in real:
            raise AssertionError(f"{name} resolves to the real user profile: {value}")
        return value

    monkeypatch.setattr(user_paths, "profile_env", guarded)


@pytest.fixture(autouse=True)
def _real_profile_untouched():
    """Backstop: fail the test during which this process wrote to the real profile."""
    _WATCH.offenders.clear()
    _WATCH.armed = True
    try:
        yield
    finally:
        _WATCH.armed = False
    _WATCH.assert_clean()


@pytest.fixture(autouse=True)
def _no_network():
    """Backstop: fail the test during which this process reached a non-loopback host.

    The catalogue's P-HERMETIC, and the counterpart of `_real_profile_untouched`:
    a test that opens a real connection is depending on a machine that is not
    this repository. See `NetworkWatch` for why the verdict is reported here
    rather than thrown from the hook.
    """
    _NETWORK_WATCH.offenders.clear()
    _NETWORK_WATCH.armed = True
    try:
        yield
    finally:
        _NETWORK_WATCH.armed = False
    _NETWORK_WATCH.assert_clean()


@pytest.fixture(autouse=True)
def _no_host_processes() -> Iterator[None]:
    """A test never sees what is running on the machine it happens to run on.

    The running-game guard refuses a config write while the game (or its
    launcher) is open, by reading the real process list. On a developer's
    machine mid-session that list names ``cod23-cod`` and ``Battle.net``, so
    every apply test for those turned into "Modern Warfare III is running" with
    nothing wrong in the code (#104: eight red in the gate, green when the game
    was closed). A test that needs a process says so by patching the snapshot,
    which runs after this fixture and wins.
    """
    from fpstune.settings.executors import game_processes

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(game_processes, "_snapshot_process_names", lambda: frozenset())
        game_processes.reset_process_cache()
        yield
    game_processes.reset_process_cache()


@pytest.fixture(autouse=True)
def _quiet_logging():
    """Reduce logging noise during tests."""
    # Save original levels
    root_level = logging.root.level
    fpstune_logger = logging.getLogger("fpstune")
    fpstune_level = fpstune_logger.level

    # Set to WARNING to reduce noise
    logging.root.setLevel(logging.WARNING)
    fpstune_logger.setLevel(logging.WARNING)

    yield

    # Restore original levels
    logging.root.setLevel(root_level)
    fpstune_logger.setLevel(fpstune_level)


@pytest.fixture
def test_client():
    """Create FastAPI TestClient."""
    from fastapi.testclient import TestClient

    from fpstune.api.main import app

    return TestClient(app)


def neutral_hardware_context() -> HardwareContext:
    """The context of a machine nothing was detected on, and no guard is up.

    What a test hands to a patched `_get_hardware_context`: production never
    returns None there, so a stub that does exercises a state it cannot reach.
    Every field is its default, which `ApplicabilityChecker` reads as "nothing
    known"; a setting with no `applicable_conditions` is applicable against it,
    and a test that needs a condition met states it by building its own context.
    """
    return HardwareContext()

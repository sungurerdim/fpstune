"""Where each cleanup's bytes are, and how many of them this process can see.

One table, one walk, one list. The table names — for every cleanup whose target
is a folder or a file — the exact paths it measures, resolved from the
environment at call time and never written down (C9), plus the filter the delete
applies to them. The walk is ``os.scandir`` in this process. The list is handed
to both halves: :func:`resolved_paths` is what the sizer counts *and* what the
delete command is given, so the two cannot come to disagree about what a cleanup
covers.

Three defects measured on 2026-09-10 are why each of those is a rule rather than
a preference:

* ``%TEMP%`` and ``%LOCALAPPDATA%\\Temp`` are the same folder on a stock profile.
  The sizer walked both and the delete deduped them, so the shown size read
  109 MB where 54 MB was there — and the freed figure doubled with it. Here every
  path is resolved through its real path and a path already covered by a kept one
  is dropped, before either half sees the list.
* One ``try`` around a whole recursive enumeration ends the walk at the first
  denied subdirectory and keeps the partial sum. On this machine that reported
  Defender's scan history as 0 B against the 446 MB a per-directory walk found.
  Here each directory is opened in its own ``try``, so a denial costs that
  directory and not the tree.
* A folder that exists and cannot be listed at all is not empty. Unelevated, five
  targets reported ``0 MB`` or ``not_installed`` for folders that were plainly
  there. Here that is ``unavailable``, which is what C11 rule 3 requires: "could
  not measure" and "there is nothing" are different statements.

Speed is why this is in Python rather than in the shipped PowerShell script.
Measured over the same 17 registered types, back to back: the one-session
PowerShell batch 13 406-16 991 ms under game load and 3 130 ms idle, this module
209-525 ms. Process start, not folder walking, was most of the difference.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import re
import sys
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import NamedTuple

logger = logging.getLogger(__name__)

# How the cleanup command treats each path it is given. The sizer counts exactly
# what the mode would delete, which is the whole point of keeping them together.
CONTENTS = "contents"  # everything inside the path; the path itself survives
DIRECTORY = "directory"  # the path itself goes too
TOP_FILES = "top_files"  # only files directly inside it, subdirectories untouched
EXTERNAL = "external"  # measured here, removed by the type's own script


class SizeReading(NamedTuple):
    """What one walk of a cleanup's paths saw.

    ``size_bytes`` is exact bytes — never rounded here, because rounding to MB
    and back is how a 512 KB cache became "0 MB" and a freed figure became the
    subtraction of two roundings.

    ``status`` is one of:

    ``ready``
        A size was measured. It may legitimately be 0: an emptied folder is a
        reading, not a failure to take one.
    ``not_estimated``
        The bytes are real and the *promise* is not: a WSL virtual disk's file
        size is not what compacting it frees. Carried with the number, so a
        before/after pair still measures what a run reclaimed while the row
        declines to advertise a reclaimable size nothing on this side can know.
    ``unavailable``
        Every path that exists refused to be listed. Not 0, which reads as
        "nothing to clean" for a folder full of files this process cannot see.
    ``not_installed``
        Nothing that marks the target as present is on this machine.
    """

    status: str
    size_bytes: int | None


type PathSource = Callable[[], list[str]]


@dataclass(frozen=True)
class CleanupTarget:
    """One cleanup's paths, and what its command does to them.

    ``installed`` is what separates "the software is not here" from "the cache is
    gone because we just deleted it" — the defect that left five cleanups with no
    freed figure at all after a successful run. For a cleanup that empties a
    folder the two are the same question, so it defaults to ``paths``; for one
    that removes the folder it names something that outlives the delete: the
    game's own directory, the launcher's own directory.
    """

    cleanup_type: str
    paths: PathSource
    delete_mode: str = CONTENTS
    installed: PathSource | None = None
    #: Only files matching one of these are counted and deleted. Empty = all.
    name_globs: tuple[str, ...] = ()
    #: With no path present at all: hide the row (the target software is absent)
    #: or report a measured zero (an OS folder that simply holds nothing today).
    absent_is_not_installed: bool = True
    #: False where the measured bytes are real but are not a reclaimable size.
    estimates_reclaim: bool = True
    #: Count only files this process can still open for writing. Reserved for a
    #: small fixed file set normally held open by another process, where counting
    #: the locked ones promises bytes no delete can take: Explorer keeps every
    #: thumbnail cache database open, measured 15 of 15 on 2026-09-10.
    skip_locked_files: bool = False


# ---------------------------------------------------------------------------
# Path discovery. Everything below reads the environment, the registry or the
# launcher's own records; nothing names a user, a drive or a library (C9).
# ---------------------------------------------------------------------------


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if not value:
        return None
    return value.strip() or None


def _under(base: str | None, *parts: str) -> str | None:
    """``base`` joined with ``parts``, or None when the environment did not answer."""
    if not base:
        return None
    return os.path.join(base, *parts)


def _present(*candidates: str | None) -> list[str]:
    """The candidates the environment could resolve, in order, without blanks."""
    return [c for c in candidates if c]


def _existing_dirs(parent: str | None, *names: str) -> list[str]:
    """Each named subdirectory of ``parent`` that exists right now."""
    if not parent:
        return []
    found = []
    for name in names:
        path = os.path.join(parent, name)
        if os.path.isdir(path):
            found.append(path)
    return found


def _child_dirs(parent: str | None) -> list[str]:
    """Every immediate subdirectory of ``parent``, or nothing when it cannot be read."""
    if not parent or not os.path.isdir(parent):
        return []
    try:
        with os.scandir(parent) as entries:
            return [e.path for e in entries if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []


def _documents_dir() -> str | None:
    """This account's Documents folder, wherever the shell says it is.

    Read from the shell folder registry rather than assembled from the profile
    path, because Documents is routinely redirected — to OneDrive, or to another
    drive entirely — and a cleanup that walks the wrong one reports zero for a
    folder that is full.
    """
    fallback = _under(_env("USERPROFILE"), "Documents")
    if sys.platform != "win32":
        return fallback
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            raw, _ = winreg.QueryValueEx(key, "Personal")
    except OSError:
        return fallback
    return os.path.expandvars(str(raw)) or fallback


#: A drive-rooted path as Battle.net writes it into its own product database.
#: Kept identical to the expression the PowerShell half used, because it is the
#: shape of the data in that file rather than a guess about it.
_INSTALL_PATH = re.compile(r"[A-Za-z]:[/\\][A-Za-z0-9 ()_\\/-]{5,150}")


def _cod_install_dir(flavor: str) -> str | None:
    """The build folder holding this Call of Duty engine flavor, or None.

    Call of Duty keeps its caches beside the game data, in the user's own library
    on any drive under any name, so the path is read out of Battle.net's own
    record of where it put them. The build folder is globbed (``_retail_``,
    ``_beta_``): naming one is a constant that goes stale the day a title enters
    beta, which is exactly how MW4's caches went unseen.
    """
    agent_db = _under(_env("ProgramData"), "Battle.net", "Agent", "product.db")
    if not agent_db or not os.path.isfile(agent_db):
        return None
    try:
        with open(agent_db, "rb") as handle:
            text = handle.read().decode("cp1252", errors="ignore")
    except OSError:  # pragma: no cover - environment dependent
        return None
    for match in _INSTALL_PATH.finditer(text):
        library = match.group(0).rstrip().replace("/", "\\")
        if not os.path.isdir(library):
            continue
        for build in _child_dirs(library):
            name = os.path.basename(build)
            if not (name.startswith("_") and name.endswith("_")):
                continue
            if os.path.isdir(os.path.join(build, flavor)):
                return build
    return None


#: The caches a Call of Duty install rebuilds on its next launch. ``shadercache``
#: sits under the flavor directory; the other two sit beside it.
_COD_CACHE_SUBDIRS = ("{flavor}\\shadercache", "telescopeCache", "xpak_cache")


def _cod_cache_paths(flavor: str) -> list[str]:
    install = _cod_install_dir(flavor)
    if not install:
        return []
    return [os.path.join(install, sub.format(flavor=flavor)) for sub in _COD_CACHE_SUBDIRS]


def _cod_installed(flavor: str) -> list[str]:
    install = _cod_install_dir(flavor)
    return [os.path.join(install, flavor)] if install else []


def _vendor_cache_paths(base: str | None, subs: tuple[str, ...]) -> list[str]:
    """``subs`` directly under ``base``, plus ``subs`` under each subdirectory.

    The vendors all organise the same way and none of them documents the layout:
    a root cache plus one per driver version or per feature. Globbing the level
    below is what finds a cache written by a driver this build has never seen.
    """
    found = _existing_dirs(base, *subs)
    for child in _child_dirs(base):
        found.extend(_existing_dirs(child, *subs))
    return found


def _nvidia_shader_paths() -> list[str]:
    local = _existing_dirs(_under(_env("LOCALAPPDATA"), "NVIDIA"), "DXCache", "GLCache")
    per_driver = _under(_env("USERPROFILE"), "AppData", "LocalLow", "NVIDIA", "PerDriverVersion")
    return local + _vendor_cache_paths(per_driver, ("DXCache", "GLCache"))


def _firefox_cache_paths() -> list[str]:
    profiles = _under(_env("APPDATA"), "Mozilla", "Firefox", "Profiles")
    found: list[str] = []
    for profile in _child_dirs(profiles):
        found.extend(_existing_dirs(profile, "cache2", "startupCache", "OfflineCache"))
    return found


def _browser_cache_paths() -> list[str]:
    local = _env("LOCALAPPDATA")
    fixed = _present(
        _under(local, "Microsoft", "Edge", "User Data", "Default", "Cache", "Cache_Data"),
        _under(local, "Microsoft", "Edge", "User Data", "Default", "Code Cache"),
        _under(local, "Google", "Chrome", "User Data", "Default", "Cache", "Cache_Data"),
        _under(local, "Google", "Chrome", "User Data", "Default", "Code Cache"),
        _under(
            local, "BraveSoftware", "Brave-Browser", "User Data", "Default", "Cache", "Cache_Data"
        ),
    )
    return fixed + _firefox_cache_paths()


def _wsl_disk_paths() -> list[str]:
    """Every WSL2 virtual disk this account owns, from WSL's own registry record."""
    if sys.platform != "win32":
        return []
    import winreg

    found: list[str] = []
    try:
        root = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Lxss"
        )
    except OSError:
        return []
    with root:
        for index in range(winreg.QueryInfoKey(root)[0]):
            try:
                name = winreg.EnumKey(root, index)
                with winreg.OpenKey(root, name) as distro:
                    base, _ = winreg.QueryValueEx(distro, "BasePath")
            except OSError:  # pragma: no cover - environment dependent
                continue
            path = re.sub(r"^\\\\\?\\", "", str(base))
            try:
                with os.scandir(path) as entries:
                    found.extend(
                        e.path
                        for e in entries
                        if e.is_file(follow_symlinks=False) and e.name.lower().endswith(".vhdx")
                    )
            except OSError:
                continue
    return found


def _cache_under(root: str, *parts: str) -> PathSource:
    """One cache folder named relative to an environment root."""
    return lambda: _present(_under(_env(root), *parts))


def _leaves_under(
    root: str, base: tuple[str, ...], leaves: tuple[tuple[str, ...], ...]
) -> PathSource:
    """Several cache folders under one base that only exists on some machines."""

    def resolve() -> list[str]:
        parent = _under(_env(root), *base)
        if not parent:
            return []
        return [os.path.join(parent, *leaf) for leaf in leaves]

    return resolve


# ---------------------------------------------------------------------------
# The table.
# ---------------------------------------------------------------------------

_TARGETS: tuple[CleanupTarget, ...] = (
    CleanupTarget(
        "temp",
        # Three spellings, two of which name one folder on a stock profile. The
        # dedupe in `resolved_paths` is what stops that folder being counted
        # twice; listing all three is still right, because a redirected TEMP is a
        # fourth folder nothing else would find.
        lambda: _present(
            _env("TEMP"), _under(_env("LOCALAPPDATA"), "Temp"), _under(_env("windir"), "Temp")
        ),
        absent_is_not_installed=False,
    ),
    CleanupTarget("nvidia_shader", _nvidia_shader_paths),
    CleanupTarget(
        "amd_shader",
        lambda: _vendor_cache_paths(
            _under(_env("LOCALAPPDATA"), "AMD"), ("DxCache", "VkCache", "GLCache", "DXCache")
        ),
    ),
    CleanupTarget(
        "intel_shader",
        lambda: _vendor_cache_paths(_under(_env("LOCALAPPDATA"), "Intel"), ("ShaderCache",)),
    ),
    CleanupTarget("directx_shader", _cache_under("LOCALAPPDATA", "D3DSCache")),
    CleanupTarget(
        "battlenet_cache",
        # Both caches, where the sizer saw only the machine-wide one and the
        # delete removed both: bytes went that nothing had counted, so the freed
        # figure under-reported by whatever the per-account cache held.
        lambda: _present(
            _under(_env("ProgramData"), "Blizzard Entertainment", "Battle.net", "Cache"),
            _under(_env("APPDATA"), "Battle.net", "Cache"),
        ),
        delete_mode=DIRECTORY,
        installed=lambda: _present(
            _under(_env("ProgramData"), "Blizzard Entertainment", "Battle.net"),
            _under(_env("APPDATA"), "Battle.net"),
        ),
    ),
    CleanupTarget(
        "wer",
        lambda: _present(
            _under(_env("ALLUSERSPROFILE"), "Microsoft", "Windows", "WER", "ReportArchive"),
            _under(_env("ALLUSERSPROFILE"), "Microsoft", "Windows", "WER", "ReportQueue"),
            _under(_env("LOCALAPPDATA"), "Microsoft", "Windows", "WER", "ReportArchive"),
            _under(_env("LOCALAPPDATA"), "Microsoft", "Windows", "WER", "ReportQueue"),
        ),
        absent_is_not_installed=False,
    ),
    CleanupTarget(
        "defender",
        _leaves_under(
            "ALLUSERSPROFILE",
            ("Microsoft", "Windows Defender", "Scans"),
            (("History", "Service"), ("History", "Store"), ("MetaStore",), ("ScanResults",)),
        ),
        absent_is_not_installed=False,
    ),
    CleanupTarget(
        "prefetch",
        _cache_under("windir", "Prefetch"),
        # Top level only, and files only, because that is what the command does:
        # a subdirectory such as ReadyBoot is neither counted nor removed.
        delete_mode=TOP_FILES,
        absent_is_not_installed=False,
    ),
    CleanupTarget("browser", _browser_cache_paths, absent_is_not_installed=False),
    CleanupTarget(
        "windows_update_cache",
        _cache_under("windir", "SoftwareDistribution", "Download"),
        absent_is_not_installed=False,
    ),
    CleanupTarget(
        "delivery_optimization",
        # Cache and Logs, because the delete takes both. The sizer counted only
        # the cache, so every log byte removed was space nobody had promised.
        _leaves_under(
            "windir",
            (
                "ServiceProfiles",
                "NetworkService",
                "AppData",
                "Local",
                "Microsoft",
                "Windows",
                "DeliveryOptimization",
            ),
            (("Cache",), ("Logs",)),
        ),
        absent_is_not_installed=False,
    ),
    CleanupTarget(
        "thumbnail_cache",
        _cache_under("LOCALAPPDATA", "Microsoft", "Windows", "Explorer"),
        delete_mode=TOP_FILES,
        name_globs=("thumbcache_*.db", "IconCache.db"),
        absent_is_not_installed=False,
        skip_locked_files=True,
    ),
    CleanupTarget(
        "memory_dumps",
        lambda: _present(
            _under(_env("windir"), "Minidump"),
            _under(_env("windir"), "LiveKernelReports"),
            _under(_env("LOCALAPPDATA"), "CrashDumps"),
            # A single file rather than a folder, and the walk treats it as one.
            _under(_env("windir"), "MEMORY.DMP"),
        ),
        absent_is_not_installed=False,
    ),
    CleanupTarget(
        "discord_cache",
        _leaves_under(
            "APPDATA", ("discord",), (("Cache", "Cache_Data"), ("Code Cache",), ("GPUCache",))
        ),
    ),
    CleanupTarget(
        "epic_cache",
        _leaves_under(
            "LOCALAPPDATA",
            ("EpicGamesLauncher", "Saved"),
            (("webcache",), ("webcache_4147",), ("Logs",)),
        ),
    ),
    CleanupTarget(
        "steam_webcache",
        _leaves_under(
            "LOCALAPPDATA", ("Steam", "htmlcache"), (("Cache", "Cache_Data"), ("Code Cache",))
        ),
    ),
    CleanupTarget("pip_cache", _cache_under("LOCALAPPDATA", "pip", "Cache")),
    CleanupTarget("npm_cache", _cache_under("APPDATA", "npm-cache")),
    CleanupTarget("yarn_cache", _cache_under("LOCALAPPDATA", "Yarn", "Cache")),
    CleanupTarget("pnpm_cache", _cache_under("LOCALAPPDATA", "pnpm", "store")),
    CleanupTarget("nuget_cache", _cache_under("USERPROFILE", ".nuget", "packages")),
    CleanupTarget("maven_cache", _cache_under("USERPROFILE", ".m2", "repository")),
    CleanupTarget("gradle_cache", _cache_under("USERPROFILE", ".gradle", "caches")),
    CleanupTarget(
        "cargo_cache",
        _leaves_under("USERPROFILE", (".cargo", "registry"), (("cache",), ("src",))),
    ),
    CleanupTarget(
        "mw3_shader",
        lambda: _cod_cache_paths("cod23"),
        delete_mode=DIRECTORY,
        installed=lambda: _cod_installed("cod23"),
    ),
    CleanupTarget(
        "mw4_shader",
        lambda: _cod_cache_paths("cod26"),
        delete_mode=DIRECTORY,
        installed=lambda: _cod_installed("cod26"),
    ),
    CleanupTarget(
        "mw3_crash",
        lambda: _present(_under(_documents_dir(), "Call of Duty MWIII", "crashes")),
        delete_mode=DIRECTORY,
        installed=lambda: _present(_under(_documents_dir(), "Call of Duty MWIII")),
    ),
    CleanupTarget(
        "cod_crash_reports",
        _cache_under("LOCALAPPDATA", "Activision", "Call of Duty", "crash_reports"),
        delete_mode=DIRECTORY,
        installed=_cache_under("LOCALAPPDATA", "Activision", "Call of Duty"),
    ),
    CleanupTarget(
        "wsl_compact",
        # The disk files themselves: their bytes are real and their size is not a
        # promise. Compacting a sparse virtual disk returns the slack between what
        # the guest filesystem still uses and what the file occupies, and nothing
        # on this side of the VM can read that. Showing the whole disk as
        # reclaimable claimed 100% of it — measured, 96 MB offered for a disk no
        # compact can remove — so the row states no size, and the run's own
        # before/after file sizes are what it reports as freed.
        _wsl_disk_paths,
        delete_mode=EXTERNAL,
        estimates_reclaim=False,
    ),
)

#: Every cleanup whose target this process measures and, unless the mode is
#: ``EXTERNAL``, whose delete command is handed this module's own path list.
CLEANUP_TARGETS: dict[str, CleanupTarget] = {t.cleanup_type: t for t in _TARGETS}


# ---------------------------------------------------------------------------
# The walk.
# ---------------------------------------------------------------------------


def resolved_paths(target: CleanupTarget) -> list[str]:
    """This target's paths right now: real paths, deduped, parents winning.

    The one list. The sizer walks it and the delete command is given it, so a
    path in one and not the other is not something that can happen. Dedupe is by
    resolved real path — ``%TEMP%`` and ``%LOCALAPPDATA%\\Temp`` are one folder on
    a stock profile, and counting it twice doubled both the shown size and the
    freed figure — and a path already inside a kept one is dropped, because the
    walk of its parent counts its bytes.
    """
    try:
        raw = target.paths()
    except OSError as exc:  # pragma: no cover - environment dependent
        logger.debug("cleanup %s path discovery failed: %s", target.cleanup_type, exc)
        return []

    resolved: list[tuple[str, str]] = []
    for path in raw:
        if not path:
            continue
        try:
            real = os.path.realpath(path)
        except OSError:  # pragma: no cover - environment dependent
            real = os.path.abspath(path)
        resolved.append((os.path.normcase(real), real))

    # Shortest first, so a parent is always kept before the child it swallows.
    resolved.sort(key=lambda pair: len(pair[0]))
    kept_keys: list[str] = []
    kept: list[str] = []
    for key, real in resolved:
        if any(key == kept_key or key.startswith(kept_key + os.sep) for kept_key in kept_keys):
            continue
        kept_keys.append(key)
        kept.append(real)
    return kept


#: What a path turned out to be when this process asked about it.
PRESENT = "present"
ABSENT = "absent"
DENIED = "denied"


def _probe(path: str) -> str:
    """Whether ``path`` is here, is not here, or refused to say.

    ``os.path.exists`` collapses the last two into False, and that collapse is
    the whole of audit finding 3: unelevated, Prefetch, Windows Temp, the update
    cache, WER and Defender's scan history all answered "does not exist" and all
    five were sitting there full. A denial is a measurement that failed, which is
    a different row from a folder that is not on this machine (C11 rule 3).
    """
    try:
        os.stat(path)
    except PermissionError:
        return DENIED
    except OSError:
        return ABSENT
    return PRESENT


def _is_writable(path: str) -> bool:
    """Whether this process can still open ``path`` for writing.

    The question the delete will ask. A thumbnail cache database held open by
    Explorer answers no, and counting its bytes promises space no command can
    return — measured 15 of 15 held on 2026-09-10.
    """
    try:
        with open(path, "rb+"):
            return True
    except OSError:
        return False


def _counts(name: str, target: CleanupTarget) -> bool:
    if not target.name_globs:
        return True
    return any(fnmatch.fnmatch(name, glob) for glob in target.name_globs)


def _file_bytes(path: str, target: CleanupTarget) -> int:
    if not _counts(os.path.basename(path), target):
        return 0
    if target.skip_locked_files and not _is_writable(path):
        return 0
    try:
        return os.stat(path).st_size
    except OSError:
        return 0


def _dir_bytes(root: str, target: CleanupTarget) -> int | None:
    """Bytes under ``root`` the delete would take, or None if it cannot be read.

    Every directory is opened in its own ``try``: a denied subdirectory costs
    that subdirectory, not the walk. Only the root failing is a failure to
    measure — that is the difference between "446 MB, minus one folder we cannot
    see" and "we cannot see this target at all".

    Reparse points are stepped over rather than followed. A junction points at a
    tree the delete does not descend into, and following one both double-counts
    it and, for the compatibility junctions Windows leaves in a profile, loops.
    """
    total = 0
    stack = [root]
    top_level = True
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as scan:
                entries = list(scan)
        except OSError:
            if top_level:
                return None
            continue
        top_level = False
        for entry in entries:
            try:
                if entry.is_symlink() or entry.is_junction():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if target.delete_mode != TOP_FILES:
                        stack.append(entry.path)
                    continue
                if not _counts(entry.name, target):
                    continue
                if target.skip_locked_files and not _is_writable(entry.path):
                    continue
                total += entry.stat(follow_symlinks=False).st_size
            except OSError:
                # A file that vanished mid-walk contributed nothing, and one this
                # process cannot stat is one it also cannot delete.
                continue
    return total


def size_target(target: CleanupTarget) -> SizeReading:
    """Measure this cleanup's target with one walk in this process.

    Reports ``not_installed`` only when nothing marking the target as present
    exists — for a cleanup that removes its own directory that is the game's or
    the launcher's own folder, never the cache. Five of those used to look
    uninstalled the moment a run succeeded, which took the freed figure off the
    row with them.

    Where some of a target's paths read and others are denied, the total is what
    this process can see and the row still says ``ready``. That is not a partial
    sum passed off as a whole one: the delete command runs at exactly the same
    privilege as this walk, so bytes this process cannot see are bytes the run
    cannot free either, and the figure stays a promise the cleanup can keep. Only
    when *nothing* could be read is there no measurement to report.
    """
    paths = resolved_paths(target)
    if target.installed is None:
        markers = paths
    else:
        markers = [os.path.realpath(p) for p in target.installed() if p]
    if all(_probe(marker) == ABSENT for marker in markers):
        if target.absent_is_not_installed:
            return SizeReading("not_installed", None)
        return SizeReading("ready", 0)

    total = 0
    measured = 0
    denied = 0
    for path in paths:
        kind = _probe(path)
        if kind == ABSENT:
            continue
        if kind == DENIED:
            denied += 1
            continue
        if os.path.isdir(path):
            walked = _dir_bytes(path, target)
            if walked is None:
                denied += 1
                continue
            total += walked
        else:
            total += _file_bytes(path, target)
        measured += 1

    if measured == 0 and denied:
        # Every path that is there refused to be listed. Answering 0 here is what
        # made Prefetch, Windows Temp, the update cache, WER and Defender all
        # report nothing to clean on an unelevated run (C11 rule 3).
        return SizeReading("unavailable", None)
    return SizeReading("ready" if target.estimates_reclaim else "not_estimated", total)


#: How a path list reaches the delete command: one placeholder holding every
#: path, joined by a character Windows forbids in a path name. The substitution
#: layer escapes the whole thing for the single-quoted literal it lands in, so a
#: path stays data and never becomes script — and a path that somehow contains a
#: separator is refused rather than silently split into two shorter paths.
PATH_SEPARATOR = "|"

#: Characters that must never reach a generated command inside a path. The pipe
#: is the separator; the rest are PowerShell's own quoting and expansion. None of
#: them is legal in a Windows path name, so refusing them costs nothing real.
_FORBIDDEN_IN_PATH = frozenset('|"`$\r\n\x00')


class UnsafePath(ValueError):
    """A resolved path that cannot be handed to a command as data."""


def delete_arguments(target: CleanupTarget) -> dict[str, str]:
    """The paths and filter the delete command needs, as command arguments.

    The same list :func:`size_target` walks. Handing it over rather than letting
    the script rebuild it is what makes "shown" and "freed" two readings of one
    thing: every mismatch the audit found was a second copy of a path list that
    had drifted from the first.

    Raises:
        UnsafePath: a resolved path holds a character that cannot be carried
            through the placeholder safely. Refused, never escaped away, because
            no legal Windows path contains one and a path that does is not a path
            this process discovered.
    """
    paths = resolved_paths(target)
    for path in paths:
        bad = _FORBIDDEN_IN_PATH.intersection(path)
        if bad:
            raise UnsafePath(
                f"cleanup {target.cleanup_type}: path {path!r} contains {sorted(bad)!r}"
            )
    return {
        "paths": PATH_SEPARATOR.join(paths),
        "mode": target.delete_mode,
        "globs": PATH_SEPARATOR.join(target.name_globs),
    }


def size_types(types: Iterable[str]) -> dict[str, SizeReading]:
    """Measure every named type this module owns, in one thread-pool pass.

    Threaded because the work is directory reads, which release the interpreter
    lock: seventeen targets measured 209-525 ms together on this machine against
    13.4-17.0 s for the one-session PowerShell batch under the same load.
    """
    known = [(name, CLEANUP_TARGETS[name]) for name in types if name in CLEANUP_TARGETS]
    if not known:
        return {}
    if len(known) == 1:
        return {known[0][0]: size_target(known[0][1])}
    with ThreadPoolExecutor(max_workers=min(16, len(known))) as pool:
        readings = list(pool.map(lambda pair: size_target(pair[1]), known))
    return {name: reading for (name, _), reading in zip(known, readings, strict=True)}

"""Per-scan cache for game configuration files.

47 MW3 settings read the same ``options.*.cst`` file and 24 CS2 settings read
the same ``autoexec.cfg``. Each one used to spawn its own PowerShell process,
and process startup — not the read — dominated scan wall-clock. Reading each
file once in Python removes 71 subprocesses from a scan.

The cache lives in the same per-scan ContextVar as ps_batch, so a run never
sees another run's contents, and workers reach it because DetectionEngine
submits through ``copy_context().run``.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

from fpstune.settings.applicability import NOT_INSTALLED as _NOT_INSTALLED
from fpstune.settings.executors.game_config_writer import key_prefix
from fpstune.settings.executors.ps_batch import _get_cache, cache_once
from fpstune.utils.logger import get_logger

logger = get_logger()

# Sentinel matching what the per-setting PowerShell commands emitted when the
# game (or its config file) is not present. Re-exported from the applicability
# contract rather than spelled again here, so detection cannot know a sentinel
# this module does not emit — or, as happened, fail to know one it does.
NOT_INSTALLED = _NOT_INSTALLED

MW3_PLAYERS_DIR = Path("Call of Duty MWIII/players")
MW3_RELATIVE_PATH = MW3_PLAYERS_DIR / "options.4.cod23.cst"

# MW3's *second* config file: graphics live in options.4.cod23.cst above, while
# audio, input, aim and FOV live in a per-account gamerprofile one level down.
# Neither the account directory nor the filename is stable, so neither is
# spelled here (C9) — one machine carries `<activisionId>/gamerprofile.0.BASE.cst`
# beside `<liveId>/gamerprofile.pc.0.BASE.cst`, and which of the two the game
# reads is decided by modification time.
#
# Two things the glob has to get right:
#
# * **`mw3fix_backup` is excluded.** A third-party fixer leaves stale copies of
#   the profile under directories carrying that name. Writing to one changes
#   nothing for the game while reporting success — the same self-confirming trap
#   the PowerShell writer of this file already avoids, and it must be avoided
#   the same way here or the two writers would disagree about which file is live.
# * **Only `.cst`.** The `.cst0` sibling is a rolling text backup and the
#   `.csb0`/`.csb1` siblings are binary stores; `*.cst` matches none of them.
MW3_PROFILE_GLOB = "*/gamerprofile*.cst"
MW3_PROFILE_BACKUP_MARK = "mw3fix_backup"

CS2_CFG_DIR = Path("steamapps/common/Counter-Strike Global Offensive/game/csgo/cfg")
# Heroes of the Storm keeps display and graphics options in the Documents-level
# file. There is a second Variables.txt under Accounts/<id>/, but it holds only
# per-player preferences — hotkeys, chat, audio — and writing graphics keys there
# changes nothing the game reads.
HOTS_RELATIVE_PATH = Path("Heroes of the Storm/Variables.txt")

# MW4 (cod26) lives under %LOCALAPPDATA%, and every segment below the root moves
# between builds and between accounts, so none of them is spelled here (C9):
#
#   <LOCALAPPDATA>/Activision/Call of Duty/players*/s.*.cod26*.txt
#   <LOCALAPPDATA>/Activision/Call of Duty/players*/<accountId>/g.*.cod26.<n>*.l.txt
#
# `playersBeta` loses its suffix at release, `<accountId>` is the user's own
# Activision id, and the filenames carry the same beta tag. Globbing all four is
# the only way this works on a machine other than the one it was written on.
MW4_ROOT = Path("Activision/Call of Duty")
MW4_GLOBAL_GLOB = "players*/s.*.cod26*.txt"
# `.l.` marks the local copy — the one the game actually fills in. The sibling
# without it holds a single key, and the `pm` variant is excluded by requiring a
# digit right after `cod26.`, which is why the numeric class is not decoration.
MW4_PROFILE_GLOB = "players*/*/g.*.cod26.[0-9]*.l.txt"

_CACHE_KEY = "game_config_files"


def _documents_dir() -> Path | None:
    """Resolve the user's Documents folder, honouring OneDrive redirection.

    ``[Environment]::GetFolderPath('MyDocuments')`` follows the Shell Folders
    redirection; reading ``%USERPROFILE%\\Documents`` directly would miss the
    OneDrive case entirely.
    """
    if sys.platform != "win32":
        return None
    try:
        import winreg

        from fpstune.utils.winapi.session import registry_root

        # The console user's Documents, not the elevated token's: under another
        # administrator's credentials HKEY_CURRENT_USER is that administrator's
        # hive, whose Documents folder holds no game config at all.
        root, key_path = registry_root(
            "HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        )
        with winreg.OpenKey(root, key_path) as key:
            personal, _ = winreg.QueryValueEx(key, "Personal")
        expanded = Path(str(personal))
        if expanded.exists():
            return expanded
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("Documents folder lookup failed: %s", exc)

    fallback = Path.home() / "Documents"
    return fallback if fallback.exists() else None


def _steam_library_paths() -> list[Path]:
    """Return every Steam library root, starting with the install path."""
    if sys.platform != "win32":
        return []

    install: str | None = None
    try:
        import winreg

        for hive_path in (r"SOFTWARE\Valve\Steam", r"SOFTWARE\WOW6432Node\Valve\Steam"):
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    hive_path,
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
                ) as key:
                    install = str(winreg.QueryValueEx(key, "InstallPath")[0])
                    break
            except FileNotFoundError:
                continue
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("Steam install path lookup failed: %s", exc)

    if not install:
        return []

    roots = [Path(install)]
    library_vdf = Path(install) / "steamapps" / "libraryfolders.vdf"
    if library_vdf.exists():
        try:
            content = library_vdf.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r'"path"\s+"([^"]+)"', content):
                candidate = Path(match.group(1).replace("\\\\", "\\"))
                if candidate not in roots:
                    roots.append(candidate)
        except OSError as exc:
            logger.debug("libraryfolders.vdf read failed: %s", exc)

    return roots


# The schema version MW4 stamps into its own filenames. Both files carry one,
# in different places, which is why this reads every number group rather than a
# fixed position:
#
#     s.1.1.bt.cod26.txt          -> (1, 1, 26)
#     g.bt.cod26.1.0.l.txt        -> (26, 1, 0)
#
# Comparing the tuples orders builds of the same file correctly, and comparing
# across the two shapes never happens — each glob returns one shape.
_VERSION_NUMBERS = re.compile(r"\d+")


def _schema_version(path: Path) -> tuple[int, ...]:
    return tuple(int(n) for n in _VERSION_NUMBERS.findall(path.name))


def _newest(candidates: Iterable[Path]) -> Path | None:
    """Pick the live config among the builds left lying beside it, or None.

    **Schema version first, modification time only to break a tie.** A re-install
    or a build change leaves the previous file in place, and MW4's beta did
    exactly that: ``s.1.0.bt.cod26.txt`` and ``s.1.1.bt.cod26.txt`` sit in the
    same directory, and the game reads the higher one.

    Ordering on mtime alone was the whole bug. Anything that touches the retired
    file — fpstune's own earlier write, a restored backup, another "optimizer" —
    makes it the newest, and from then on every apply lands in a file the game
    does not read. Apply reports success, verify reports success (it re-reads
    what fpstune just wrote), and nothing changes in the game. That is the exact
    shape of the failure `game_processes` guards against from the other
    direction, and the same reason it cannot be caught downstream.

    Measured on a beta install 2026-08-30: ``s.1.0`` held the tuned values
    (MotionBlur Off, DoF Low, CorpseLimit 8) and ``s.1.1`` held the game's
    defaults, because the schema bump did not migrate them.
    """
    files = [p for p in candidates if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: (_schema_version(p), p.stat().st_mtime))


def _newest_by_mtime(candidates: Iterable[Path]) -> Path | None:
    """Pick the most recently written file, or None.

    Deliberately *not* `_newest`: that one orders on the schema version MW4
    stamps into its own filenames, which is a measured property of MW4's files
    and of nothing else. MW3's gamerprofile carries a number too
    (``gamerprofile.0.BASE.cst``), but nothing states it is a schema version, so
    ordering on it would be a guess about which file the game reads. Modification
    time is what the PowerShell writer of this same file already sorts on, and
    the two must agree or they would write to different files.
    """
    files = [p for p in candidates if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def mw3_profile_path() -> Path | None:
    """Discover MW3's per-account gamerprofile. Never a held path or id (C9)."""
    documents = _documents_dir()
    if documents is None:
        return None

    players = documents / MW3_PLAYERS_DIR
    if not players.is_dir():
        return None

    try:
        candidates = [
            path
            for path in players.glob(MW3_PROFILE_GLOB)
            if MW3_PROFILE_BACKUP_MARK not in str(path).casefold()
        ]
    except OSError as exc:  # pragma: no cover - environment dependent
        logger.debug("MW3 profile discovery failed under %s: %s", players, exc)
        return None

    return _newest_by_mtime(candidates)


def mw4_config_paths() -> tuple[Path | None, Path | None]:
    """Discover MW4's global and profile config files. Never a held path (C9)."""
    if sys.platform != "win32":
        return None, None

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None, None

    root = Path(local_app_data) / MW4_ROOT
    if not root.is_dir():
        return None, None

    try:
        return _newest(root.glob(MW4_GLOBAL_GLOB)), _newest(root.glob(MW4_PROFILE_GLOB))
    except OSError as exc:  # pragma: no cover - environment dependent
        logger.debug("MW4 config discovery failed under %s: %s", root, exc)
        return None, None


def _read_text(path: Path) -> str | None:
    try:
        # utf-8-sig because the BOM is not a promise either way: MW4's file has
        # none today and CS2's autoexec.cfg has one. Without the -sig a BOM would
        # ride along on the first key and make it unmatchable.
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        logger.debug("game config read failed for %s: %s", path, exc)
        return None


def _load_snapshot() -> dict[str, Any]:
    """Read every known game config file once.

    ``cs2_installed`` is tracked separately from ``cs2`` because the original
    commands distinguished the two: no CS2 install reports "not_installed",
    while an installed CS2 without an autoexec.cfg reports the setting's
    "absent" value (an unmanaged setting is simply at its default).
    """
    snapshot: dict[str, Any] = {
        "mw3": None,
        # MW3's second file, held apart from the first for the same reason MW4's
        # two are: a key name can appear in both and a setting names which one
        # it reads.
        "mw3_profile": None,
        "cs2": None,
        "cs2_installed": False,
        "hots": None,
        # MW4 keeps two files and a key can appear in both, so they are held
        # apart rather than concatenated — a setting names which one it reads.
        "mw4_global": None,
        "mw4_profile": None,
    }

    mw4_global, mw4_profile = mw4_config_paths()
    if mw4_global is not None:
        snapshot["mw4_global"] = _read_text(mw4_global)
    if mw4_profile is not None:
        snapshot["mw4_profile"] = _read_text(mw4_profile)

    documents = _documents_dir()
    if documents:
        mw3_path = documents / MW3_RELATIVE_PATH
        if mw3_path.exists():
            snapshot["mw3"] = _read_text(mw3_path)

        hots_path = documents / HOTS_RELATIVE_PATH
        if hots_path.exists():
            snapshot["hots"] = _read_text(hots_path)

    mw3_profile = mw3_profile_path()
    if mw3_profile is not None:
        snapshot["mw3_profile"] = _read_text(mw3_profile)

    for root in _steam_library_paths():
        cfg_dir = root / CS2_CFG_DIR
        if cfg_dir.is_dir():
            snapshot["cs2_installed"] = True
            autoexec = cfg_dir / "autoexec.cfg"
            if autoexec.exists():
                snapshot["cs2"] = _read_text(autoexec)
            break

    logger.debug(
        "[scan] game configs: mw3=%s mw3_profile=%s cs2_installed=%s cs2_autoexec=%s hots=%s "
        "mw4_global=%s mw4_profile=%s",
        "found" if snapshot["mw3"] is not None else "absent",
        "found" if snapshot["mw3_profile"] is not None else "absent",
        snapshot["cs2_installed"],
        "found" if snapshot["cs2"] is not None else "absent",
        "found" if snapshot["hots"] is not None else "absent",
        "found" if snapshot["mw4_global"] is not None else "absent",
        "found" if snapshot["mw4_profile"] is not None else "absent",
    )
    return snapshot


def prefetch_game_configs() -> dict[str, Any]:
    """Populate the active scan cache with game config file contents."""
    cache = _get_cache()
    if cache is not None:
        return cache_once(cache, _CACHE_KEY, _load_snapshot)
    return _load_snapshot()


def refresh_cached_config(snapshot_key: str, content: str) -> None:
    """Keep the per-scan snapshot in step with what a writer just put on disk.

    Apply is followed immediately by a detect, and that detect reads this cache.
    Without the refresh the verify step compares the new value against the
    pre-apply snapshot and reports a mismatch fpstune itself created.

    A no-op outside a scan: there is no snapshot to correct, and the next read
    loads the file fresh anyway.
    """
    cache = _get_cache()
    if cache is None:
        return
    snapshot = cache.get(_CACHE_KEY)
    if isinstance(snapshot, dict):
        snapshot[snapshot_key] = content


def _snapshot() -> dict[str, Any]:
    cache = _get_cache()
    if cache is not None:
        cached = cache.get(_CACHE_KEY)
        if cached is not None:
            return cast("dict[str, Any]", cached)
        return prefetch_game_configs()
    return _load_snapshot()


def get_mw3_option(key: str) -> Any:
    """Read one ``Key:0.0 = "value"`` entry from the MW3 options file."""
    content = _snapshot().get("mw3")
    if content is None:
        return NOT_INSTALLED

    pattern = rf'(?m)^\s*{re.escape(key)}:[\d.]+\s*=\s*"([^"]+)"'
    match = re.search(pattern, content)
    return match.group(1) if match else NOT_INSTALLED


def get_mw3_options_any_true(keys: list[str]) -> Any:
    """Report ``"true"`` when ANY of the given boolean keys is true.

    For a named-compound setting whose keys each independently enable the same
    behaviour, the concept is only off once every key is off. Reading just the
    first key would call the setting disabled while a sibling still switches the
    behaviour on — which is how MW3 kept pausing rendering with
    ``PauseRenderingEnabled`` already false.
    """
    values = [get_mw3_option(k) for k in keys]
    present = [v for v in values if v != NOT_INSTALLED]
    if not present:
        return NOT_INSTALLED
    return "true" if any(str(v).strip().lower() == "true" for v in present) else "false"


def get_hots_variable(key: str) -> Any:
    """Read one ``key=value`` entry from the Heroes of the Storm Variables.txt.

    Two shapes appear in the same file and both have to be read, because the
    game writes whichever it likes per key::

        vsync=true
        GraphicsOptionTextureQuality[2]=0

    The bracketed index is the game's own slot number, not something to choose,
    so it is matched but never invented — an apply that dropped it would leave
    the original key in place and add one the game never reads.

    Matching is case-insensitive because the file mixes conventions freely
    (``vsync`` beside ``GraphicsOptionSSAO``), and a user who edited the file by
    hand should not silently get a second copy of a key that is already there.
    """
    content = _snapshot().get("hots")
    if content is None:
        return NOT_INSTALLED

    pattern = rf"(?mi)^[ \t]*{re.escape(key)}(?:\[\d+\])?[ \t]*=[ \t]*(.*?)[ \t]*$"
    match = re.search(pattern, content)
    return match.group(1) if match else NOT_INSTALLED


# Both Call of Duty titles write one setting per line, and every line carries
# its own range or its own value list:
#
#     TextureQuality@0;61129;7764 = 1 // 0 to 3                 MW4
#     AspectRatio@0;19775;7764 = auto // one of auto, standard, 5:4, wide 16:10
#     Sprint Assist Delay KBM@1;23176;7764 = 0 // 0 to 12750    MW4
#     Sprint Assist Delay KBM@0 = 400 // 0 to 12750             MW3 gamerprofile
#
# Three things the shape forces. The name can contain spaces, so it cannot be
# tokenised on whitespace. The suffix after `@<scope>` is an opaque hash that is
# matched loosely and never rebuilt — MW4 writes one and MW3's gamerprofile does
# not, which is why it is optional rather than two patterns. And the trailing
# `//` comment is the authority on the range, which is why no setting of either
# game declares one in Python.
_SCOPED_ONE_OF = re.compile(r"^one\s+of\s+(?P<items>.+)$", re.IGNORECASE)
_SCOPED_RANGE = re.compile(r"^(?P<low>-?[\d.]+)\s+to\s+(?P<high>-?[\d.]+)$", re.IGNORECASE)


def _scoped_line_pattern(key: str, *, scope_optional: bool = False) -> re.Pattern[str] | None:
    """Build the matcher for one ``Name@<scope>`` key.

    The scope index is part of the key because the same name appears twice with
    different ranges — ``DxrMode@0`` is Off/On while ``DxrMode@1`` is
    Off..Ultra. Writing the value of one into the other writes something the
    game will not accept.

    The prefix comes from the writer's own builder rather than a second
    spelling of it, so a line this reader accepts is a line the writer can put
    back — including MW3's older scope-less schema, which ``scope_optional``
    selects and which ``game_config_writer.key_prefix`` documents.
    """
    prefix = key_prefix(key, scope_optional=scope_optional)
    if prefix is None:
        return None
    return re.compile(rf"(?m)^{prefix}(?P<value>.*?)[ \t]*(?:\/\/[ \t]*(?P<meta>.*?)[ \t]*)?$")


def _scoped_value(
    content: str | None, key: str, label: str, *, scope_optional: bool = False
) -> Any:
    """Read one ``Name@<scope> = value`` entry out of already-loaded text."""
    if content is None:
        return NOT_INSTALLED

    pattern = _scoped_line_pattern(key, scope_optional=scope_optional)
    if pattern is None:
        logger.debug("%s key %r has no @<scope> suffix; refusing to guess", label, key)
        return NOT_INSTALLED

    match = pattern.search(content)
    return match.group("value") if match else NOT_INSTALLED


def _scoped_metadata(
    content: str | None, key: str, *, scope_optional: bool = False
) -> dict[str, Any]:
    """Return the choices or numeric range the line's own ``//`` comment states.

    Empty when the key is absent or carries no trailing comment — the caller
    then has no authority to state a range, and must not invent one.
    """
    if content is None:
        return {}

    pattern = _scoped_line_pattern(key, scope_optional=scope_optional)
    if pattern is None:
        return {}

    match = pattern.search(content)
    if match is None:
        return {}

    meta = (match.group("meta") or "").strip()
    if not meta:
        return {}

    one_of = _SCOPED_ONE_OF.match(meta)
    if one_of:
        items = tuple(part.strip() for part in one_of.group("items").split(",") if part.strip())
        return {"choices": items} if items else {}

    numeric = _SCOPED_RANGE.match(meta)
    if numeric:
        low, high = numeric.group("low"), numeric.group("high")
        # Integer when the file writes it as one: TextureQuality's 0..3 must not
        # become 0.0..3.0, or the value written back stops matching the file.
        cast_fn: Any = float if ("." in low or "." in high) else int
        try:
            return {"minimum": cast_fn(low), "maximum": cast_fn(high)}
        except ValueError:  # pragma: no cover - the regex already constrains this
            return {}

    return {}


def _agreed(values: list[Any], label: str, keys: list[str]) -> Any:
    """Collapse a named-compound's readings into the one value it is at.

    Several keys that hold the same value list and mean the same thing are one
    setting, so the concept is only at a value when every key is. When they
    disagree the *last* differing value is reported rather than the first: the
    caller is a guard asking "has anything drifted from the recommendation", and
    answering with the first key would let a drifted second key hide behind a
    correct first one — the same failure MW3 had when it read only
    ``PauseRenderingEnabled`` and kept pausing rendering anyway.
    """
    present = [v for v in values if v != NOT_INSTALLED]
    if not present:
        return NOT_INSTALLED
    if len(set(present)) == 1:
        return present[0]

    logger.debug("%s compound %s disagrees across keys: %s", label, keys, present)
    return present[-1]


def get_mw3_profile_option(key: str) -> Any:
    """Read one ``Name@<scope> = value`` entry from MW3's gamerprofile.

    The second of MW3's two config files: audio, input, aim and FOV. Same line
    shape as MW4's files minus the ``;hash`` suffix, so it goes through the same
    parser rather than a second one.

    ``scope_optional`` because this game ships two schemas of the same file and
    both are live — the older one writes ``Name@ value`` with no scope digit
    and no ``=``. See ``game_config_writer.key_prefix``.
    """
    return _scoped_value(_mw3_profile_content(), key, "MW3 profile", scope_optional=True)


def get_mw3_profile_options_agreed(keys: list[str]) -> Any:
    """Read a named-compound MW3 profile setting: several keys, one setting.

    MW3 keeps one sensitivity multiplier per optic — ``ADS2xZoomSensitivity@0``
    through ``ADSHighZoomSensitivity@0`` — which are one concept between them
    (C8), so the concept is only at a value when every key is.
    """
    values = [get_mw3_profile_option(key) for key in keys]
    return _agreed(values, "MW3 profile", keys)


def get_mw3_profile_metadata(key: str) -> dict[str, Any]:
    """Return the choices or numeric range MW3's gamerprofile documents for a key."""
    return _scoped_metadata(_mw3_profile_content(), key, scope_optional=True)


def _mw3_profile_content() -> str | None:
    return cast("str | None", _snapshot().get("mw3_profile"))


MW4_SOURCES = ("global", "profile")


def _mw4_content(source: str) -> str | None:
    if source not in MW4_SOURCES:
        raise ValueError(f"unknown MW4 config source {source!r}")
    content = _snapshot().get(f"mw4_{source}")
    return cast("str | None", content)


def get_mw4_option(key: str, source: str = "global") -> Any:
    """Read one ``Name@<scope> = value`` entry from an MW4 config file.

    ``source="both"`` is for the keys MW4 keeps in *both* files — every volume
    control appears in the global file and again in the profile, under the same
    scope index but a different hash. Measured 2026-08-23: changing the music
    volume in-game wrote ``0.000000`` to both, so the game keeps them in step and
    a setting that wrote only one would be half-applied.

    With ``both``, disagreement reports the *last* differing value for the same
    reason the named-compound reader does: a guard asking "has anything drifted"
    must not let a drifted second copy hide behind a correct first one.
    """
    if source == "both":
        values = [get_mw4_option(key, s) for s in MW4_SOURCES]
        return _agreed(values, "MW4", [key])

    return _scoped_value(_mw4_content(source), key, "MW4")


def get_mw4_options_agreed(keys: list[str], source: str = "global") -> Any:
    """Read a named-compound MW4 setting: several keys that are one setting.

    ``SSRQuality@0`` and ``SSRQuality@1`` hold the same value list and mean the
    same thing, so the concept is only at a value when every key is.

    When the keys disagree the *last* differing value is reported rather than the
    first. The caller is a guard asking "has anything drifted from the
    recommendation", and answering with the first key would let a drifted second
    key hide behind a correct first one — the same failure MW3 had when it read
    only ``PauseRenderingEnabled`` and kept pausing rendering anyway.
    """
    values = [get_mw4_option(k, source) for k in keys]
    return _agreed(values, "MW4", keys)


def get_mw4_metadata(key: str, source: str = "global") -> dict[str, Any]:
    """Return the choices or numeric range MW4 itself documents for a key.

    Empty when the key is absent or carries no trailing comment — the caller
    then has no authority to state a range, and must not invent one.
    """
    if source == "both":
        # Whichever file actually documents it. They agree where both do.
        for candidate in MW4_SOURCES:
            found = get_mw4_metadata(key, candidate)
            if found:
                return found
        return {}

    return _scoped_metadata(_mw4_content(source), key)


def get_cs2_marker(name: str, present: str, absent: str) -> Any:
    """Report whether an fpstune-managed block exists in CS2's autoexec."""
    snapshot = _snapshot()
    if not snapshot.get("cs2_installed"):
        return NOT_INSTALLED

    content = snapshot.get("cs2")
    if content is None:
        # CS2 is installed but has no autoexec.cfg — nothing is managed yet.
        return absent
    return present if f"===fpstune-{name}-start===" in content else absent

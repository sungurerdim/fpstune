"""Read and rewrite one value in a game's own text config, and nothing else.

Fortnite, Apex Legends, Overwatch 2 and Rainbow Six Siege each keep their
graphics options in a plain text file in the console user's profile. Three
shapes cover them::

    FrameRateLimit=0.000000               Fortnite GameUserSettings.ini
    VSync=0                               Rainbow Six Siege GameSettings.ini
    VerticalSyncEnabled = "0"             Overwatch 2 Settings_v0.ini
    "setting.mat_vsync_mode"		"0"     Apex Legends videoconfig.txt

The rules every writer here follows, because each one is how a config edit
silently fails or does damage:

* **Only an existing line is rewritten.** A key the file does not carry is
  reported absent and never added: guessing the section a build reads a key
  from is how a write lands where the game never looks, and verify would still
  pass. The game writes every key it reads, so a missing key means this build
  does not use it.
* **The file keeps its bytes.** Encoding (UTF-8 with or without a BOM, UTF-16
  with its BOM), line endings and every other line are preserved; only the
  matched value changes, and the replace is atomic.
* **One lock for the whole read-modify-write**, a named system mutex per file
  shared with every other writer (``game_config_writer.file_lock``), so a
  parallel bulk apply cannot drop one setting's write with another's.
* **A key that appears more than once is written everywhere** and read from
  the first place, so the file never carries two answers to one question.

Which game is open is decided elsewhere: ``game_processes`` refuses the write
while the game runs, because each of these games writes its settings back from
memory when it exits.
"""

from __future__ import annotations

import codecs
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fpstune.settings.applicability import NOT_INSTALLED, NOT_SUPPORTED
from fpstune.utils.logger import get_logger

logger = get_logger()

# What a detect returns when the file exists but does not carry the key: this
# build of the game does not use it, so the setting does not apply here.
ABSENT = NOT_SUPPORTED

# Saved Games has no fixed name in Shell Folders; it is listed under its
# KNOWNFOLDERID (FOLDERID_SavedGames).
_SAVED_GAMES_ID = "{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}"

_BOMS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)


@dataclass(frozen=True)
class GameConfigFile:
    """Where one game's config lives and how its lines are shaped."""

    game: str
    locate: Callable[[], Path | None]
    # "ini": ``Key=Value`` / ``Key = "Value"``; "vdf": ``"key"<ws>"value"``.
    shape: str

    @property
    def mutex_name(self) -> str:
        return f"Global\\fpstune-{self.game}-config"


def _console_folder(value_name: str) -> Path | None:
    from fpstune.settings.executors.game_config_cache import _console_user_folder

    return _console_user_folder(value_name)


def _local_appdata() -> Path | None:
    return _console_folder("Local AppData")


def _documents() -> Path | None:
    from fpstune.settings.executors.game_config_cache import _documents_dir

    return _documents_dir()


def _saved_games() -> Path | None:
    folder = _console_folder(_SAVED_GAMES_ID)
    if folder is not None:
        return folder
    # Saved Games sits in the profile root; Local AppData is <profile>\AppData\Local.
    local = _local_appdata()
    if local is None:
        return None
    candidate = local.parent.parent / "Saved Games"
    return candidate if candidate.is_dir() else None


def _newest(paths: list[Path]) -> Path | None:
    """The file written last: the account that played most recently."""
    existing = [p for p in paths if p.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda p: p.stat().st_mtime)


def fortnite_path() -> Path | None:
    # https://www.esportstales.com/fortnite/how-to-increase-fps-video-options-gameusersettings
    # https://optimizer.byens-it.dk/en/games/fortnite
    local = _local_appdata()
    if local is None:
        return None
    return local / "FortniteGame" / "Saved" / "Config" / "WindowsClient" / "GameUserSettings.ini"


def apex_path() -> Path | None:
    # https://note.com/ebi_suuuuuu/n/nd51daeac3755
    # https://gamertagzero.com/apex-legends-how-to-get-maximum-fps-fps-boost-guide/
    saved = _saved_games()
    if saved is None:
        return None
    return saved / "Respawn" / "Apex" / "local" / "videoconfig.txt"


def overwatch_path() -> Path | None:
    # https://filepathgeek.com/posts/overwatch-2-settings-screenshots-location/
    # https://www.esportstales.com/overwatch/how-to-increase-fps-video-options
    documents = _documents()
    if documents is None:
        return None
    return documents / "Overwatch" / "Settings" / "Settings_v0.ini"


def siege_path() -> Path | None:
    # One folder per Ubisoft account under the game's folder; the newest file is
    # the account that played last (C9: the folder name is never carried).
    # https://steamcommunity.com/app/359550/discussions/0/1621724915806554641/
    # https://github.com/cjLGH/game-settings/blob/master/r6siege/GameSettings.ini
    documents = _documents()
    if documents is None:
        return None
    root = documents / "My Games" / "Rainbow Six - Siege"
    if not root.is_dir():
        return None
    return _newest(list(root.glob("*/GameSettings.ini")))


FILES: dict[str, GameConfigFile] = {
    "fortnite": GameConfigFile("fortnite", fortnite_path, "ini"),
    "apex": GameConfigFile("apex", apex_path, "vdf"),
    "overwatch": GameConfigFile("overwatch", overwatch_path, "ini"),
    "r6siege": GameConfigFile("r6siege", siege_path, "ini"),
}


def _pattern(shape: str, key: str) -> re.Pattern[str]:
    name = re.escape(key)
    if shape == "vdf":
        return re.compile(rf'(?mi)^(?P<head>[ \t]*"{name}"[ \t]+")(?P<value>[^"\r\n]*)(?P<tail>")')
    # Optional quotes round the value, optional spaces round the '='; the value
    # stops at the line end, never past it.
    return re.compile(
        rf'(?mi)^(?P<head>[ \t]*{name}[ \t]*=[ \t]*"?)(?P<value>[^"\r\n]*?)(?P<tail>"?[ \t]*)(?=\r?$)'
    )


def _decode(raw: bytes) -> tuple[str, bytes, str]:
    """Text, the BOM it came with, and the codec to write it back in."""
    for bom, codec in _BOMS:
        if raw.startswith(bom):
            return raw[len(bom) :].decode(codec), bom, codec
    return raw.decode("utf-8"), b"", "utf-8"


def _resolve(game: str) -> tuple[GameConfigFile, Path] | None:
    spec = FILES.get(game)
    if spec is None or sys.platform != "win32":
        return None
    path = spec.locate()
    if path is None or not path.is_file():
        return None
    return spec, path


def read_value(game: str, key: str, path: Path | None = None) -> str:
    """The value of ``key`` as the file holds it, ``ABSENT``, or ``NOT_INSTALLED``."""
    spec = FILES.get(game)
    if spec is None:
        return NOT_INSTALLED
    if path is None:
        resolved = _resolve(game)
        if resolved is None:
            return NOT_INSTALLED
        path = resolved[1]
    try:
        text, _, _ = _decode(path.read_bytes())
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("%s config unreadable: %s", game, exc)
        return NOT_INSTALLED
    match = _pattern(spec.shape, key).search(text)
    return match.group("value").strip() if match else ABSENT


def write_value(
    game: str, key: str, value: str, path: Path | None = None
) -> tuple[bool, str | None]:
    """Rewrite every line that sets ``key`` to ``value``, under the file's lock."""
    from fpstune.settings.executors.game_config_writer import (
        _clear_readonly,
        _match_number_format,
        _write_atomically,
        file_lock,
    )

    spec = FILES.get(game)
    if spec is None:
        return False, f"Unknown game '{game}'"
    if path is None:
        resolved = _resolve(game)
        if resolved is None:
            return False, "The game's config file was not found for this user"
        path = resolved[1]
    if re.search(r'["\r\n\v\f\x00]', value):
        return False, "A config value must be a single line without quotes"

    pattern = _pattern(spec.shape, key)
    with file_lock(spec.mutex_name):
        try:
            text, bom, codec = _decode(path.read_bytes())
        except UnicodeDecodeError:
            return (
                False,
                f"{path.name} is not in an encoding fpstune can rewrite safely; left untouched",
            )
        except OSError as exc:
            return False, f"{path.name} could not be read: {exc}"

        matches = list(pattern.finditer(text))
        if not matches:
            return False, f"{path.name} has no {key} line; this build of the game does not use it"

        written = _match_number_format(matches[0].group("value"), value)
        if all(m.group("value") == written for m in matches):
            return True, None
        updated = pattern.sub(lambda m: f"{m.group('head')}{written}{m.group('tail')}", text)
        try:
            _clear_readonly(path)
            _write_atomically(path, bom + updated.encode(codec))
        except OSError as exc:
            return False, str(exc)
    logger.debug("%s: %s = %s", game, key, written)
    return True, None


def game_ini_read(args: dict[str, Any]) -> str:
    """``PYTHON_DETECTORS`` entry: the raw value of ``args['key']`` in ``args['game']``'s file.

    ``integer`` reads a number the game writes as a float (``60.000000``) as the
    whole number a frame cap is.
    """
    raw = read_value(str(args["game"]), str(args["key"]))
    if args.get("integer") and raw not in (NOT_INSTALLED, NOT_SUPPORTED):
        try:
            return str(int(float(raw)))
        except ValueError:
            return raw
    return raw


def game_ini_write(args: dict[str, Any]) -> tuple[bool, str | None]:
    """``PYTHON_ACTIONS`` entry: write ``args['value']``.

    A choice setting names its writable raw values in ``allowed``; a display
    value with no raw form (a guard's "changed" reading) arrives here unmapped
    and is refused rather than written into the game's file. A numeric setting
    names ``min``/``max`` instead.
    """
    value = str(args.get("value", "")).strip()
    allowed = args.get("allowed")
    if allowed is not None and value not in str(allowed).split(","):
        return False, f"'{value}' is a reading, not a value fpstune can write"
    if "min" in args or "max" in args:
        try:
            number = float(value)
        except ValueError:
            return False, f"'{value}' is not a number"
        if not float(args.get("min", number)) <= number <= float(args.get("max", number)):
            return False, f"{value} is outside {args.get('min')}..{args.get('max')}"
    return write_value(str(args["game"]), str(args["key"]), value)

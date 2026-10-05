"""One value rewritten in a game's own config file, and nothing else changed.

Each test names the failure it guards: a line ending, encoding or neighbouring
line damaged; a key added where the game never reads it; a lost update between
parallel writers; a reading written back as a value.
"""

from __future__ import annotations

import codecs
import os
import threading
from pathlib import Path

import pytest

from fpstune.settings.applicability import NOT_INSTALLED, NOT_SUPPORTED
from fpstune.settings.executors import game_ini

FORTNITE = (
    "[/Script/FortniteGame.FortGameUserSettings]\r\n"
    "bUseVSync=True\r\n"
    "FrameRateLimit=60.000000\r\n"
    "ResolutionSizeX=2560\r\n"
)
APEX = (
    '"VideoConfig"\n{\n'
    '\t"setting.mat_vsync_mode"\t\t"2"\n'
    '\t"setting.mat_backbuffer_count"\t\t"2"\n'
    '\t"setting.volumetric_lighting"\t\t"1"\n'
    "}\n"
)
OVERWATCH = '[Render.13]\nFullScreenRefresh = "240"\nVerticalSyncEnabled = "1"\n'
SIEGE = (
    "[DISPLAY_SETTINGS]\r\n"
    ";VSync => 0 disabled / 1 frame / 2 frames\r\n"
    "VSync=1\r\n"
    "[DISPLAY]\r\n"
    ";FPSLimit => Limit the game's fps. Minimum of 30fps.\r\n"
    "FPSLimit=0\r\n"
)


def _file(
    tmp_path: Path, name: str, text: str, *, prefix: bytes = b"", codec: str = "utf-8"
) -> Path:
    path = tmp_path / name
    path.write_bytes(prefix + text.encode(codec))
    return path


def test_crlf_ini_rewrites_one_value_and_keeps_every_other_byte(tmp_path: Path) -> None:
    path = _file(tmp_path, "GameUserSettings.ini", FORTNITE)

    ok, message = game_ini.write_value("fortnite", "bUseVSync", "False", path)

    assert (ok, message) == (True, None)
    assert path.read_bytes() == FORTNITE.replace("bUseVSync=True", "bUseVSync=False").encode()
    assert game_ini.read_value("fortnite", "bUseVSync", path) == "False"


def test_a_float_cap_is_written_the_way_the_file_writes_numbers(tmp_path: Path) -> None:
    path = _file(tmp_path, "GameUserSettings.ini", FORTNITE)

    game_ini.write_value("fortnite", "FrameRateLimit", "224", path)

    assert "FrameRateLimit=224.000000\r\n" in path.read_bytes().decode("utf-8")


def test_the_vdf_shape_keeps_its_tabs_and_quotes(tmp_path: Path) -> None:
    path = _file(tmp_path, "videoconfig.txt", APEX)

    game_ini.write_value("apex", "setting.mat_vsync_mode", "0", path)

    assert path.read_text() == APEX.replace(
        '"setting.mat_vsync_mode"\t\t"2"', '"setting.mat_vsync_mode"\t\t"0"'
    )
    assert game_ini.read_value("apex", "setting.volumetric_lighting", path) == "1"


def test_a_quoted_spaced_ini_value_stays_quoted(tmp_path: Path) -> None:
    path = _file(tmp_path, "Settings_v0.ini", OVERWATCH)

    game_ini.write_value("overwatch", "VerticalSyncEnabled", "0", path)

    assert path.read_text() == OVERWATCH.replace(
        'VerticalSyncEnabled = "1"', 'VerticalSyncEnabled = "0"'
    )


def test_the_files_own_comment_lines_are_never_taken_for_the_key(tmp_path: Path) -> None:
    path = _file(tmp_path, "GameSettings.ini", SIEGE)

    assert game_ini.read_value("r6siege", "VSync", path) == "1"
    game_ini.write_value("r6siege", "VSync", "0", path)
    text = path.read_bytes().decode("utf-8")
    assert ";VSync => 0 disabled / 1 frame / 2 frames\r\nVSync=0\r\n" in text


@pytest.mark.parametrize(
    ("bom", "codec"),
    [(codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le")],
    ids=["utf8-bom", "utf16le-bom"],
)
def test_the_encoding_and_its_bom_survive_the_rewrite(
    tmp_path: Path, bom: bytes, codec: str
) -> None:
    path = _file(tmp_path, "Settings_v0.ini", OVERWATCH, prefix=bom, codec=codec)

    game_ini.write_value("overwatch", "VerticalSyncEnabled", "0", path)

    raw = path.read_bytes()
    assert raw.startswith(bom)
    assert raw[len(bom) :].decode(codec) == OVERWATCH.replace('"1"', '"0"', 1).replace(
        'FullScreenRefresh = "0"', 'FullScreenRefresh = "240"'
    )


def test_a_key_the_file_lacks_is_not_applicable_and_never_added(tmp_path: Path) -> None:
    path = _file(tmp_path, "GameSettings.ini", "[DISPLAY]\r\nBrightness=50.000000\r\n")
    before = path.read_bytes()

    assert game_ini.read_value("r6siege", "FPSLimit", path) == NOT_SUPPORTED
    ok, message = game_ini.write_value("r6siege", "FPSLimit", "138", path)

    assert ok is False and "no FPSLimit line" in str(message)
    assert path.read_bytes() == before


def test_a_key_set_twice_is_written_everywhere(tmp_path: Path) -> None:
    text = "[A]\nFrameRateLimit=60.000000\n[B]\nFrameRateLimit=120.000000\n"
    path = _file(tmp_path, "GameUserSettings.ini", text)

    game_ini.write_value("fortnite", "FrameRateLimit", "0", path)

    assert path.read_text().count("FrameRateLimit=0.000000") == 2


def test_a_value_that_would_add_a_line_is_refused(tmp_path: Path) -> None:
    path = _file(tmp_path, "GameSettings.ini", SIEGE)
    before = path.read_bytes()

    ok, _ = game_ini.write_value("r6siege", "VSync", "0\r\nFPSLimit=1", path)

    assert ok is False
    assert path.read_bytes() == before


def test_an_undecodable_file_is_left_untouched(tmp_path: Path) -> None:
    path = tmp_path / "GameSettings.ini"
    path.write_bytes(b"[DISPLAY]\r\nName=Jos\xe9\r\nVSync=1\r\n")
    before = path.read_bytes()

    ok, message = game_ini.write_value("r6siege", "VSync", "0", path)

    assert ok is False and "left untouched" in str(message)
    assert path.read_bytes() == before


def test_a_read_only_file_is_still_written(tmp_path: Path) -> None:
    # Guides tell players to mark these files read-only so the game cannot
    # revert them; a write that failed on that would leave fpstune unusable.
    path = _file(tmp_path, "videoconfig.txt", APEX)
    os.chmod(path, 0o444)

    ok, _ = game_ini.write_value("apex", "setting.volumetric_lighting", "0", path)

    assert ok is True
    assert game_ini.read_value("apex", "setting.volumetric_lighting", path) == "0"


def test_parallel_writers_to_one_file_lose_nothing(tmp_path: Path) -> None:
    path = _file(tmp_path, "videoconfig.txt", APEX)
    barrier = threading.Barrier(2)

    def write(key: str) -> None:
        barrier.wait()
        game_ini.write_value("apex", key, "0", path)

    threads = [
        threading.Thread(target=write, args=(key,))
        for key in ("setting.mat_vsync_mode", "setting.volumetric_lighting")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert game_ini.read_value("apex", "setting.mat_vsync_mode", path) == "0"
    assert game_ini.read_value("apex", "setting.volumetric_lighting", path) == "0"


class TestTheActionEntry:
    @pytest.fixture
    def siege(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        path = _file(tmp_path, "GameSettings.ini", SIEGE)
        monkeypatch.setattr(game_ini, "_resolve", lambda game: (game_ini.FILES[game], path))
        return path

    def test_a_reading_with_no_raw_form_is_refused(self, siege: Path) -> None:
        ok, message = game_ini.game_ini_write(
            {"game": "r6siege", "key": "VSync", "value": "changed", "allowed": "0,1,2"}
        )
        assert ok is False and "reading" in str(message)
        assert game_ini.read_value("r6siege", "VSync", siege) == "1"

    def test_a_cap_outside_its_range_is_refused(self, siege: Path) -> None:
        ok, _ = game_ini.game_ini_write(
            {"game": "r6siege", "key": "FPSLimit", "value": "5000", "min": 0, "max": 1000}
        )
        assert ok is False
        assert game_ini.read_value("r6siege", "FPSLimit", siege) == "0"

    def test_a_cap_in_range_is_written(self, siege: Path) -> None:
        ok, _ = game_ini.game_ini_write(
            {"game": "r6siege", "key": "FPSLimit", "value": "138", "min": 0, "max": 1000}
        )
        assert ok is True
        assert game_ini.read_value("r6siege", "FPSLimit", siege) == "138"

    def test_an_integer_reading_drops_the_float_tail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = _file(tmp_path, "GameUserSettings.ini", FORTNITE)
        monkeypatch.setattr(game_ini, "_resolve", lambda game: (game_ini.FILES[game], path))
        assert (
            game_ini.game_ini_read({"game": "fortnite", "key": "FrameRateLimit", "integer": True})
            == "60"
        )

    def test_a_game_that_is_not_installed_says_so(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(game_ini, "_resolve", lambda _game: None)
        assert (
            game_ini.game_ini_read({"game": "apex", "key": "setting.mat_vsync_mode"})
            == NOT_INSTALLED
        )


def test_siege_reads_the_account_that_played_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "My Games" / "Rainbow Six - Siege"
    old = root / "11111111-aaaa" / "GameSettings.ini"
    new = root / "22222222-bbbb" / "GameSettings.ini"
    for path, stamp in ((old, 1_000_000), (new, 2_000_000)):
        path.parent.mkdir(parents=True)
        path.write_text(SIEGE)
        os.utime(path, (stamp, stamp))
    monkeypatch.setattr(game_ini, "_documents", lambda: tmp_path)

    assert game_ini.siege_path() == new

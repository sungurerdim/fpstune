"""A CS2 setting must write a cvar CS2 actually has.

This is the third time the same mistake shipped, so it gets a mechanical guard
rather than a third fix:

  1. snd_mixahead (removed 2026-08-11) — a Source 1 audio command, claimed a
     12 ms latency saving in a game that answers "unknown command".
  2. Eleven settings removed here — six cvars absent from all 102 shipped CS2
     modules, plus the five 128-tick networking cvars Valve describes as
     "legacy networking convars that existed in CS:GO but never had an effect
     in CS2".

Every one reported success, because CS2 detection looks for fpstune's own marker
block in autoexec.cfg rather than anything the game acts on. A setting that
writes a dead line can therefore never disagree with itself: it writes the
marker, reads the marker back, and reports "optimized" forever.

The measurement that produced the list below, on 2026-08-22: every .dll and .exe
under the CS2 install was scanned for each cvar name as a byte string, since a
cvar name lives in the module that registers it. See TestAgainstTheInstalledGame
for the same check as a test, which runs when CS2 is present.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from fpstune.settings.definitions.game_configs import CS2_SETTINGS

# Confirmed absent from every shipped CS2 module, or confirmed inert by Valve's
# own removal note. Nothing in here may come back without new evidence — and a
# settings guide is not evidence, since most circulating "CS2 command" lists are
# recycled CS:GO configs.
DEAD_CVARS = {
    # Absent from all 102 modules
    "cl_cmdrate": "no such cvar in CS2; the line is never parsed",
    "cl_forcepreload": "no such cvar in CS2",
    "mat_queue_mode": "no such cvar in CS2; Source 2 has no material queue to set",
    "cl_disablefreezecam": "no such cvar in CS2",
    "cl_detail_max_sway": "no such cvar in CS2",
    "r_eyegloss": "no such cvar in CS2",
    "r_dynamic_lighting": "no such cvar in CS2",
    "snd_mixahead": "Source 1 audio; Steam Audio manages the buffer itself",
    "snd_mix_async": "Source 1 audio",
    "snd_headphone_pan_exponent": "Source 1 audio",
    # Present as symbols but inert: CS2 is subtick, and every value these were
    # given was derived from a 128-tick rate that does not exist.
    "rate": "legacy networking convar; no effect in CS2",
    "cl_updaterate": "legacy networking convar; no effect in CS2",
    "cl_interp": "no longer a tuning variable; it reports the effective interp",
    "cl_interp_ratio": "superseded by cl_net_buffer_ticks, which the game's own "
    "help text says not to set directly",
}


def _written_cvars() -> dict[str, str]:
    """Every cvar name a CS2 setting writes, mapped to the setting that writes it."""
    written: dict[str, str] = {}
    for setting in CS2_SETTINGS:
        cvar = (setting.apply_args or {}).get("cvar")
        if isinstance(cvar, str) and cvar:
            written[cvar] = setting.id
    return written


class TestNoSettingWritesADeadCvar:
    def test_no_shipped_cs2_setting_writes_one(self) -> None:
        written = _written_cvars()
        offenders = {c: (written[c], DEAD_CVARS[c]) for c in written.keys() & DEAD_CVARS.keys()}
        assert not offenders, "\n".join(
            f"{sid} writes {cvar!r} — {why}" for cvar, (sid, why) in sorted(offenders.items())
        )

    def test_the_guard_can_actually_fail(self) -> None:
        # A guard nobody has seen fail is a guard nobody knows works. This proves
        # the intersection above catches a dead cvar rather than always being
        # empty because _written_cvars() returned nothing.
        assert _written_cvars(), "no CS2 setting writes a cvar; the guard reads nothing"
        pretend = {"cl_cmdrate": "game_config:cs2:pretend"}
        assert pretend.keys() & DEAD_CVARS.keys() == {"cl_cmdrate"}

    def test_the_removed_settings_are_gone_from_the_registry(self) -> None:
        from fpstune.settings.registry import SettingsRegistry

        removed = [
            "game_config:cs2:rate",
            "game_config:cs2:updaterate",
            "game_config:cs2:cmdrate",
            "game_config:cs2:interp",
            "game_config:cs2:interp_ratio",
            "game_config:cs2:dynamic_lighting",
            "game_config:cs2:forcepreload",
            "game_config:cs2:mat_queue_mode",
            "game_config:cs2:disable_freezecam",
            "game_config:cs2:detail_sway",
            "game_config:cs2:eye_effects",
        ]
        registry = SettingsRegistry(discover_dynamic=False)
        still_there = [sid for sid in removed if registry.get(sid) is not None]
        assert not still_there, f"settings writing dead cvars are still registered: {still_there}"

    def test_the_dead_action_command_went_with_them(self) -> None:
        # A dead entry in ACTION_COMMANDS is a script that can still be invoked
        # by id, so removing the setting alone leaves the write path live.
        from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

        assert "cs2_dynamic_lighting_toggle" not in ACTION_COMMANDS


class TestAgainstTheInstalledGame:
    """The real check, when the machine can run it.

    Skipped rather than faked when CS2 is absent: asserting against a game that
    is not installed would be asserting against nothing. This is what caught the
    eleven, and it is what will catch the twelfth.
    """

    @pytest.fixture(scope="class")
    def modules(self) -> list[pathlib.Path]:
        # Every Steam library, discovered the same way the product discovers them
        # — libraryfolders.vdf off the registry install path. A drive letter
        # written into a test passes on one machine and silently skips on every
        # other, which is the same class of defect this file exists to catch.
        from fpstune.settings.executors.game_config_cache import (
            CS2_CFG_DIR,
            _steam_library_paths,
        )

        candidates: list[pathlib.Path] = []
        override = os.environ.get("FPSTUNE_CS2_DIR")
        if override:
            candidates.append(pathlib.Path(override))
        # CS2_CFG_DIR points at .../game/csgo/cfg; the install root is three up.
        candidates += [library / CS2_CFG_DIR.parents[2] for library in _steam_library_paths()]

        root = next((c for c in candidates if (c / "game").is_dir()), None)
        if root is None:
            pytest.skip("CS2 is not installed here")
        found = list(root.rglob("*.dll")) + list(root.rglob("*.exe"))
        if not found:
            pytest.skip("CS2 directory holds no modules to read")
        return found

    def test_every_cvar_we_write_exists_in_the_shipped_game(
        self, modules: list[pathlib.Path]
    ) -> None:
        written = _written_cvars()
        # Names of three characters or fewer match inside unrelated strings
        # ("rate" inside "framerate"), so a byte scan cannot answer for them.
        checkable = {c: s for c, s in written.items() if len(c) > 6 and "_" in c}
        assert checkable, "nothing long enough to search for; the scan proves nothing"

        needles = {c: c.encode() for c in checkable}
        seen: set[str] = set()
        for path in modules:
            if len(seen) == len(needles):
                break
            try:
                blob = path.read_bytes()
            except OSError:
                continue
            seen.update(c for c, n in needles.items() if c not in seen and n in blob)

        missing = {c: checkable[c] for c in checkable if c not in seen}
        assert not missing, "\n".join(
            f"{sid} writes {cvar!r}, which no CS2 module contains"
            for cvar, sid in sorted(missing.items())
        )

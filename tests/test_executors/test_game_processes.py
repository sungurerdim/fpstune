"""Tests for refusing to write a game's config while the game is running.

The failure this guards against is the only one that passes every check the
product has: apply writes the file, verify re-reads the file fpstune just wrote
and agrees, and then the game overwrites it on exit. Measured 2026-08-23 — MW4's
config was rewritten by ``cod26-cod`` six minutes into a test run that had not
touched it.

Every test here fakes the process list rather than reading the machine's, so the
suite gives the same answer whether or not a game happens to be open.
"""

from __future__ import annotations

import pytest

from fpstune.settings.executors import game_processes as gp


@pytest.fixture(autouse=True)
def clean_cache():
    gp.reset_process_cache()
    yield
    gp.reset_process_cache()


def _fake_processes(monkeypatch, names: set[str]) -> None:
    monkeypatch.setattr(gp, "_snapshot_process_names", lambda: frozenset(names))


class TestWhichGameASettingBelongsTo:
    @pytest.mark.parametrize(
        ("setting_id", "expected"),
        [
            ("game_config:mw4:texture_quality", "mw4"),
            ("game_config:mw3:vsync", "mw3"),
            ("game_config:cs2:fps_max", "cs2"),
            ("game_config:hots:vsync", "hots"),
        ],
    )
    def test_a_game_config_names_its_game(self, setting_id: str, expected: str) -> None:
        assert gp.game_of_setting(setting_id) == expected

    @pytest.mark.parametrize(
        "setting_id",
        [
            # Cleanup deletes caches rather than writing settings the game holds
            # in memory, so the overwrite-on-exit failure does not apply.
            "game_cleanup:mw3:shader_cache",
            "game_cleanup:steam:download_cache",
            "system:network_afd_receive_window",
            "gpu:nvidia_low_latency",
        ],
    )
    def test_everything_else_is_not_a_game_config(self, setting_id: str) -> None:
        assert gp.game_of_setting(setting_id) is None


class TestDetectingARunningGame:
    def test_the_measured_mw4_process_is_recognised(self, monkeypatch) -> None:
        """`cod26-cod` is the one name in this table that was actually observed."""
        _fake_processes(monkeypatch, {"cod26-cod", "explorer", "chrome"})
        assert gp.game_is_running("mw4") is True

    def test_matching_ignores_case(self, monkeypatch) -> None:
        _fake_processes(monkeypatch, {"cod26-cod"})
        monkeypatch.setitem(gp.GAME_PROCESSES, "mw4", ("COD26-COD",))
        assert gp.game_is_running("mw4") is True

    def test_a_closed_game_is_not_running(self, monkeypatch) -> None:
        _fake_processes(monkeypatch, {"explorer", "chrome"})
        assert gp.game_is_running("mw4") is False

    def test_the_launcher_services_are_not_the_game(self, monkeypatch) -> None:
        """`CODBrokerService` and `codCrashHandler` were both running beside MW4
        and both outlive it. Treating either as "the game is open" would block
        every apply on a machine that had launched it once."""
        _fake_processes(monkeypatch, {"codbrokerservice", "codcrashhandler", "battle.net"})
        assert gp.game_is_running("mw4") is False

    def test_an_unknown_game_key_is_not_running(self, monkeypatch) -> None:
        """A game fpstune has no process name for keeps its previous behaviour."""
        _fake_processes(monkeypatch, {"somegame"})
        assert gp.game_is_running("fortnite") is False

    def test_an_empty_snapshot_never_blocks(self, monkeypatch) -> None:
        """Enumeration failing must fall back to writing, not to refusing.

        This module only adds a warning; a machine where the snapshot fails must
        behave exactly as it did before the module existed.
        """
        _fake_processes(monkeypatch, set())
        assert gp.game_is_running("mw4") is False


class TestTheRefusal:
    def test_a_running_game_produces_a_message_that_says_what_to_do(self, monkeypatch) -> None:
        _fake_processes(monkeypatch, {"cod26-cod"})

        message = gp.refuse_if_game_is_running("game_config:mw4:texture_quality")

        assert message is not None
        assert "Modern Warfare IV" in message
        assert "Close the game" in message
        # The reason matters: without it the user reads a refusal as a bug.
        assert "memory" in message and "undone" in message

    def test_a_closed_game_does_not_refuse(self, monkeypatch) -> None:
        _fake_processes(monkeypatch, {"explorer"})
        assert gp.refuse_if_game_is_running("game_config:mw4:texture_quality") is None

    def test_one_running_game_does_not_block_another(self, monkeypatch) -> None:
        """MW4 being open says nothing about whether CS2's config is safe to write."""
        _fake_processes(monkeypatch, {"cod26-cod"})
        assert gp.refuse_if_game_is_running("game_config:cs2:fps_max") is None

    def test_a_system_setting_is_never_blocked(self, monkeypatch) -> None:
        _fake_processes(monkeypatch, {"cod26-cod"})
        assert gp.refuse_if_game_is_running("system:network_afd_receive_window") is None

    def test_a_cleanup_action_is_never_blocked(self, monkeypatch) -> None:
        _fake_processes(monkeypatch, {"cod26-cod"})
        assert gp.refuse_if_game_is_running("game_cleanup:mw3:shader_cache") is None


class TestCaching:
    def test_the_snapshot_is_reused_within_the_window(self, monkeypatch) -> None:
        """A bulk apply asks once per setting; 55 snapshots would be 55 sweeps."""
        calls = {"n": 0}

        def counting():
            calls["n"] += 1
            return frozenset({"cod26-cod"})

        monkeypatch.setattr(gp, "_snapshot_process_names", counting)

        for _ in range(10):
            gp.game_is_running("mw4")

        assert calls["n"] == 1

    def test_reset_forces_a_fresh_look(self, monkeypatch) -> None:
        """After the user closes the game, the next apply must see that."""
        _fake_processes(monkeypatch, {"cod26-cod"})
        assert gp.game_is_running("mw4") is True

        _fake_processes(monkeypatch, {"explorer"})
        assert gp.game_is_running("mw4") is True  # still cached

        gp.reset_process_cache()
        assert gp.game_is_running("mw4") is False

    def test_bypassing_the_cache_reads_again(self, monkeypatch) -> None:
        calls = {"n": 0}

        def counting():
            calls["n"] += 1
            return frozenset()

        monkeypatch.setattr(gp, "_snapshot_process_names", counting)
        gp.running_process_names(use_cache=False)
        gp.running_process_names(use_cache=False)
        assert calls["n"] == 2


class TestTheApplyPathHonoursIt:
    def test_apply_refuses_and_writes_nothing(self, monkeypatch, tmp_path) -> None:
        """The whole point: the write must not happen, not merely be reported."""
        from fpstune.settings.definitions.game_configs_mw4 import MW4_TEXTURE_QUALITY
        from fpstune.settings.executors.powershell import PowerShellExecutor

        players = tmp_path / "Activision" / "Call of Duty" / "players"
        players.mkdir(parents=True)
        config = players / "s.1.0.x.cod26.txt"
        config.write_bytes(b"1\nTextureQuality@0;61129;7764 = 1 // 0 to 3\n")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        _fake_processes(monkeypatch, {"cod26-cod"})

        ok, error = PowerShellExecutor().apply(MW4_TEXTURE_QUALITY, "0")

        assert ok is False
        assert error is not None and "Modern Warfare IV" in error
        assert b"TextureQuality@0;61129;7764 = 1" in config.read_bytes()

    def test_apply_proceeds_once_the_game_is_closed(self, monkeypatch, tmp_path) -> None:
        from fpstune.settings.definitions.game_configs_mw4 import MW4_TEXTURE_QUALITY
        from fpstune.settings.executors.powershell import PowerShellExecutor

        players = tmp_path / "Activision" / "Call of Duty" / "players"
        players.mkdir(parents=True)
        config = players / "s.1.0.x.cod26.txt"
        config.write_bytes(b"1\nTextureQuality@0;61129;7764 = 1 // 0 to 3\n")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        _fake_processes(monkeypatch, {"explorer"})

        ok, error = PowerShellExecutor().apply(MW4_TEXTURE_QUALITY, "0")

        assert ok is True, error
        assert b"TextureQuality@0;61129;7764 = 0" in config.read_bytes()


class TestTheTableItself:
    def test_every_game_with_processes_has_a_label(self) -> None:
        """The label is what the user reads; a missing one shows a raw key."""
        assert set(gp.GAME_PROCESSES) <= set(gp.GAME_LABELS)

    def test_no_process_name_carries_an_exe_suffix(self) -> None:
        """The snapshot strips `.exe`, so a name that keeps it never matches."""
        for game, names in gp.GAME_PROCESSES.items():
            for name in names:
                assert not name.lower().endswith(".exe"), f"{game}: {name}"

    def test_the_games_covered_match_the_games_that_ship_config_settings(self) -> None:
        """A game whose settings ship without a process name here can still be
        written into a running session — the failure this module exists to stop."""
        from fpstune.settings.registry import SettingsRegistry

        shipped = {
            s.id.split(":")[1]
            for s in SettingsRegistry(discover_dynamic=False).get_all()
            if s.id.startswith("game_config:")
        }
        assert shipped <= set(gp.GAME_PROCESSES), (
            f"no process name for: {shipped - set(gp.GAME_PROCESSES)}"
        )


class TestTheMessageReachesTheUser:
    """The refusal is only useful if the person reading the UI sees the reason.

    A refused apply that shows "failed" with no explanation reads as a bug in
    fpstune rather than as a game that is open.
    """

    def test_the_api_response_carries_the_reason(self, monkeypatch, tmp_path) -> None:
        from fpstune.api.routes.settings import _finalize_apply_response
        from fpstune.settings.definitions.game_configs_mw4 import MW4_TEXTURE_QUALITY
        from fpstune.settings.executors.powershell import PowerShellExecutor

        players = tmp_path / "Activision" / "Call of Duty" / "players"
        players.mkdir(parents=True)
        (players / "s.1.0.x.cod26.txt").write_bytes(
            b"1\nTextureQuality@0;61129;7764 = 1 // 0 to 3\n"
        )
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        _fake_processes(monkeypatch, {"cod26-cod"})

        success, error = PowerShellExecutor().apply(MW4_TEXTURE_QUALITY, "0")
        response = _finalize_apply_response(
            MW4_TEXTURE_QUALITY, "0", None, success, error, "Applied"
        )

        assert response.success is False
        assert response.error is not None
        assert "Modern Warfare IV" in response.error
        assert "Close the game" in response.error

    @pytest.mark.parametrize("game", sorted(gp.GAME_PROCESSES))
    def test_every_game_produces_a_readable_single_line(self, monkeypatch, game: str) -> None:
        """It renders in an 11px single-colour banner with no formatting and no
        truncation, so it has to be one line that reads as a sentence."""
        _fake_processes(monkeypatch, {gp.GAME_PROCESSES[game][0].casefold()})

        message = gp.refuse_if_game_is_running(f"game_config:{game}:anything")

        assert message is not None
        assert "\n" not in message, "the banner does not render line breaks"
        assert len(message) < 220, f"too long for the banner: {len(message)}"
        assert gp.GAME_LABELS[game] in message, "must name the game, not its process"
        assert message.endswith("."), "reads as a sentence, not a diagnostic"

"""Call of Duty caches are found where the machine actually put them.

Reported by the user: MW4's shader cache had no cleanup at all. Measured on the
machine that reported it, 2026-08-25:

    mw3_shader        ready|1581 MB
    mw4_shader        ready|2163 MB     <- previously invisible
    cod_crash_reports ready|0 MB

The reason MW4's was invisible is the interesting part, and it is a C9 defect
rather than a missing feature. The MW3 lookup joined the literal folder
``_retail_`` onto the install path — correct for a released title, and wrong for
the MW4 beta, which ships under ``_beta_``. A build-tagged directory is exactly
the class of name C9 says to glob rather than hardcode: what is stable is the
flavor directory (``cod23``, ``cod26``) inside it.

So both titles now go through one lookup that globs ``_*_``, and these tests pin
the properties that made the old one wrong.
"""

from __future__ import annotations

import pytest

from fpstune.settings.definitions import get_all_static_settings
from fpstune.settings.executors.powershell_actions import (
    ACTION_COMMANDS,
    _cod_cache_cleanup,
    _cod_cache_size,
    _cod_install_lookup,
)
from fpstune.settings.groups import group_for

COD_FLAVORS = [("cod23", "MW3"), ("cod26", "MW4")]


class TestTheInstallLookup:
    @pytest.mark.parametrize(("flavor", "label"), COD_FLAVORS)
    def test_the_build_folder_is_globbed_not_named(self, flavor: str, label: str) -> None:  # noqa: ARG002
        """`_retail_` as a literal is what hid 2.1 GB of MW4 cache."""
        script = _cod_install_lookup(flavor)
        assert "'_*_'" in script
        assert "_retail_" not in script
        assert "_beta_" not in script

    @pytest.mark.parametrize(("flavor", "label"), COD_FLAVORS)
    def test_the_flavor_is_what_identifies_the_title(self, flavor: str, label: str) -> None:  # noqa: ARG002
        assert f"Join-Path $build '{flavor}'" in _cod_install_lookup(flavor)

    def test_the_install_path_is_read_rather_than_assumed(self) -> None:
        """C9: the library is on whichever drive under whatever name the user chose.

        Battle.net's own product.db is the machine's record of where it put the
        game, so no path in this module belongs to any particular install.
        """
        script = _cod_install_lookup("cod26")
        assert r"C:\ProgramData\Battle.net\Agent\product.db" in script
        # The first entry is spelled apart so the scrubbed tree never contains
        # the developer machine's library-folder name as a literal.
        for developer_machine_path in ("Oyunla" + "r", "SteamLibrary", "Users\\"):
            assert developer_machine_path not in script


class TestWhatGetsDeleted:
    @pytest.mark.parametrize(("flavor", "label"), COD_FLAVORS)
    def test_only_caches_the_game_rebuilds(self, flavor: str, label: str) -> None:
        """Everything named here is regenerated on the next launch.

        The flavor directory itself holds tens of GB of game data; deleting the
        wrong subdirectory would mean a re-download, not a recompile.
        """
        script = _cod_cache_cleanup(flavor, label)
        assert f"{flavor}\\shadercache" in script
        assert "telescopeCache" in script
        assert "xpak_cache" in script
        # The parent of shadercache is the game itself.
        assert f"'{flavor}'," not in script

    @pytest.mark.parametrize(("flavor", "label"), COD_FLAVORS)
    def test_a_missing_install_deletes_nothing_and_says_so(self, flavor: str, label: str) -> None:
        script = _cod_cache_cleanup(flavor, label)
        assert f"FPSTUNE_WARN: {label} install dir not found" in script
        assert "exit 0" in script

    @pytest.mark.parametrize(("flavor", "label"), COD_FLAVORS)
    def test_the_size_probe_reads_the_same_directories_it_deletes(
        self, flavor: str, label: str
    ) -> None:
        """A size that measures one set and an apply that deletes another is a
        reported number nothing produced."""
        size = _cod_cache_size(flavor, label)
        for subdir in (f"{flavor}\\shadercache", "telescopeCache", "xpak_cache"):
            assert subdir in size
        assert "not_installed" in size


class TestTheyAreWired:
    def test_both_titles_have_an_apply_command(self) -> None:
        assert "mw3_shader_cache_cleanup" in ACTION_COMMANDS
        assert "mw4_shader_cache_cleanup" in ACTION_COMMANDS
        assert "cod_crash_reports_cleanup" in ACTION_COMMANDS

    def test_the_status_script_can_answer_for_both(self) -> None:
        """The detect side is one big switch; a title missing from it reports no
        size, which reads on screen as "nothing to reclaim"."""
        status = ACTION_COMMANDS["cleanup_status"]
        assert "'mw3_shader'" in status
        assert "'mw4_shader'" in status
        assert "'cod_crash_reports'" in status
        # Substituted at module load, like __PRUNE_ARGS__ — a leftover marker
        # would reach PowerShell as a bare token.
        assert "__MW3_SHADER_SIZE__" not in status
        assert "__MW4_SHADER_SIZE__" not in status

    @pytest.mark.parametrize(
        ("setting_id", "command"),
        [
            ("game_cleanup:mw3:shader_cache_cleanup", "mw3_shader_cache_cleanup"),
            ("game_cleanup:mw4:shader_cache_cleanup", "mw4_shader_cache_cleanup"),
            ("game_cleanup:cod_crash_reports", "cod_crash_reports_cleanup"),
        ],
    )
    def test_each_setting_points_at_its_own_command(self, setting_id: str, command: str) -> None:
        setting = next(s for s in get_all_static_settings() if s.id == setting_id)
        assert setting.apply_command == command
        assert setting.is_action
        assert setting.detect_command == "cleanup_status"
        # The detect type it asks for must be one the status script answers.
        assert f"'{setting.detect_args['type']}'" in ACTION_COMMANDS["cleanup_status"]

    def test_every_cod_cleanup_lands_under_a_heading(self) -> None:
        for setting_id, expected in [
            ("game_cleanup:mw4:shader_cache_cleanup", "Modern Warfare IV"),
            ("game_cleanup:mw3:shader_cache_cleanup", "Modern Warfare III"),
            # Written by the launcher rather than by one title.
            ("game_cleanup:cod_crash_reports", "Launchers & apps"),
        ]:
            group = group_for(setting_id)
            assert group is not None, setting_id
            assert group.label == expected

    def test_the_crash_folder_is_claimed_once(self) -> None:
        """Two per-game settings on one directory would each report freeing what
        the other already freed."""
        claimants = [
            s for s in get_all_static_settings() if s.apply_command == "cod_crash_reports_cleanup"
        ]
        assert len(claimants) == 1

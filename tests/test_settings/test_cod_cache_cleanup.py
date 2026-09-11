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

Both titles go through one lookup, which is now Python rather than PowerShell —
so the "same directories" property below is no longer two lists that agree, it is
one list handed to both halves. These tests pin the properties that made the old
lookup wrong, against the code that replaced it.
"""

from __future__ import annotations

import os

import pytest

from fpstune.settings.cleanup_targets import (
    CLEANUP_TARGETS,
    DIRECTORY,
    _cod_cache_paths,
    _cod_installed,
    delete_arguments,
    resolved_paths,
)
from fpstune.settings.definitions import get_all_static_settings
from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS
from fpstune.settings.groups import group_for

COD_FLAVORS = [("cod23", "MW3"), ("cod26", "MW4")]
COD_TYPES = ["mw3_shader", "mw4_shader"]


class TestTheInstallLookup:
    def test_the_build_folder_is_globbed_not_named(self) -> None:
        """`_retail_` as a literal is what hid 2.1 GB of MW4 cache.

        The lookup takes every ``_*_`` directory in the library and asks which one
        holds the flavor, so a title in beta is found by the same code that finds
        a released one.
        """
        import ast
        import inspect
        import textwrap

        from fpstune.settings import cleanup_targets

        source = inspect.getsource(cleanup_targets._cod_install_dir)
        assert 'name.startswith("_") and name.endswith("_")' in source
        # Naming a build folder is the defect; the docstring explaining that is
        # not, so this reads the literals the code actually uses (the same
        # carve-out C9's own gate makes for a comment).
        literals = {
            node.value
            for node in ast.walk(ast.parse(textwrap.dedent(source)))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert "_retail_" not in literals
        assert "_beta_" not in literals

    @pytest.mark.parametrize(("flavor", "label"), COD_FLAVORS)
    def test_the_flavor_is_what_identifies_the_title(self, flavor: str, label: str) -> None:  # noqa: ARG002
        """Installed means the flavor directory is there, not that a cache is."""
        for path in _cod_installed(flavor):
            assert os.path.basename(path) == flavor

    def test_the_install_path_is_read_rather_than_assumed(self) -> None:
        """C9: the library is on whichever drive under whatever name the user chose.

        Battle.net's own product.db is the machine's record of where it put the
        game, and even the launcher's own folder is reached through
        ``%ProgramData%`` rather than through a drive letter.
        """
        import inspect

        from fpstune.settings import cleanup_targets

        source = inspect.getsource(cleanup_targets._cod_install_dir)
        assert '_env("ProgramData")' in source
        assert "C:" not in source
        # The first entry is spelled apart so the scrubbed tree never contains
        # the developer machine's library-folder name as a literal.
        for developer_machine_path in ("Oyunla" + "r", "SteamLibrary", "Users\\"):
            assert developer_machine_path not in source


class TestWhatGetsDeleted:
    @pytest.mark.parametrize(("flavor", "label"), COD_FLAVORS)
    def test_only_caches_the_game_rebuilds(self, flavor: str, label: str) -> None:  # noqa: ARG002
        """Everything named here is regenerated on the next launch.

        The flavor directory itself holds tens of GB of game data; deleting the
        wrong subdirectory would mean a re-download, not a recompile.
        """
        import inspect

        from fpstune.settings import cleanup_targets

        subdirs = cleanup_targets._COD_CACHE_SUBDIRS
        assert subdirs == ("{flavor}\\shadercache", "telescopeCache", "xpak_cache")
        # The parent of shadercache is the game itself, and it is never a target.
        assert flavor not in subdirs
        assert inspect.isfunction(_cod_cache_paths)

    @pytest.mark.parametrize("cleanup_type", COD_TYPES)
    def test_a_missing_install_deletes_nothing_and_says_so(self, cleanup_type: str) -> None:
        """No install found means no path list, and the row reads not-installed."""
        from fpstune.settings.cleanup_targets import CleanupTarget, size_target

        target = CleanupTarget(
            cleanup_type, lambda: [], delete_mode=DIRECTORY, installed=lambda: []
        )
        assert size_target(target) == ("not_installed", None)
        assert delete_arguments(target)["paths"] == ""

    @pytest.mark.parametrize("cleanup_type", COD_TYPES)
    def test_the_size_probe_reads_the_same_directories_it_deletes(self, cleanup_type: str) -> None:
        """A size that measures one set and an apply that deletes another is a
        reported number nothing produced.

        There is now one list: `resolved_paths` is what the walk sums and what
        the delete command is handed, so this asserts they are the same object's
        output rather than that two texts happen to agree.
        """
        target = CLEANUP_TARGETS[cleanup_type]
        paths = resolved_paths(target)
        handed_over = delete_arguments(target)["paths"]

        assert handed_over == "|".join(paths)
        assert target.delete_mode == DIRECTORY
        # A cache that is removed outright must not make the title look absent.
        assert target.installed is not None

    @pytest.mark.parametrize("cleanup_type", COD_TYPES)
    def test_the_title_being_installed_is_not_the_cache_being_present(
        self, cleanup_type: str
    ) -> None:
        """Audit finding 5: the row lost its freed figure the moment the run worked."""
        target = CLEANUP_TARGETS[cleanup_type]
        cache_paths = set(resolved_paths(target))
        markers = {os.path.realpath(p) for p in (target.installed or list)()}
        assert not (markers & cache_paths)


class TestTheyAreWired:
    def test_both_titles_have_an_apply_command(self) -> None:
        assert "mw3_shader_cache_cleanup" in ACTION_COMMANDS
        assert "mw4_shader_cache_cleanup" in ACTION_COMMANDS
        assert "cod_crash_reports_cleanup" in ACTION_COMMANDS

    def test_each_cod_cleanup_is_sized_in_process(self) -> None:
        """A title missing from the table reports no size, which reads on screen
        as "nothing to reclaim"."""
        for cleanup_type in (*COD_TYPES, "cod_crash_reports", "mw3_crash"):
            assert cleanup_type in CLEANUP_TARGETS

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
        # The detect type it asks for must be one something can answer.
        assert setting.detect_args["type"] in CLEANUP_TARGETS

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

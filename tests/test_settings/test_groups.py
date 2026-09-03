"""Every grouped setting has a group, and the label comes from one place.

The gap this closes: a list surface can only offer the headings the backend
gives it. Before this, "Game Configs" was the finest heading 181 game settings
could get, so the guard that matters is not that a particular id maps to a
particular group — it is that *nothing in a grouped module falls through*. A new
cleanup added without a table entry, or a new game added without a
``GAME_LABELS`` entry, fails here rather than appearing under no heading.
"""

from __future__ import annotations

import pytest

from fpstune.settings.definitions import get_all_static_settings
from fpstune.settings.executors.game_processes import GAME_LABELS
from fpstune.settings.groups import group_for

GROUPED_MODULES = ("game_config", "game_cleanup", "cleanup")


@pytest.fixture(scope="module")
def all_settings():
    return get_all_static_settings()


def test_every_grouped_setting_resolves_a_group(all_settings):
    """No setting in a grouped module may land without a heading."""
    ungrouped = [
        s.id for s in all_settings if s.module in GROUPED_MODULES and group_for(s.id) is None
    ]
    assert ungrouped == [], (
        "these settings are in a grouped module but resolve no group — add a "
        f"_CLEANUP_GROUPS entry, or a GAME_LABELS entry for a new game: {ungrouped}"
    )


def test_ungrouped_modules_get_no_heading(all_settings):
    """A module with no groups says so, rather than inventing a single bucket."""
    for setting in all_settings:
        if setting.module in GROUPED_MODULES:
            continue
        assert group_for(setting.id) is None, (
            f"{setting.id} is in ungrouped module {setting.module} but resolved a group"
        )


def test_game_settings_group_by_the_game_in_their_id(all_settings):
    """A game's settings all land under that game, and under its own label."""
    seen: set[str] = set()
    for setting in all_settings:
        if setting.module != "game_config":
            continue
        game = setting.id.split(":")[1]
        group = group_for(setting.id)
        assert group is not None
        assert group.id == game
        assert group.label == GAME_LABELS[game]
        seen.add(game)

    # The registry ships four games today; if one is ever dropped this notices.
    assert seen == {"mw4", "mw3", "cs2", "hots"}


def test_the_label_is_not_a_second_copy_of_the_name():
    """C9: the display name ships from GAME_LABELS, never re-spelled here."""
    for game, label in GAME_LABELS.items():
        group = group_for(f"game_config:{game}:anything")
        assert group is not None
        assert group.label == label


def test_a_games_cleanup_groups_with_that_game():
    """`game_cleanup:mw3:x` belongs to MW3, not to a generic cleanup bucket."""
    group = group_for("game_cleanup:mw3:shader_cache_cleanup")
    assert group is not None
    assert group.label == GAME_LABELS["mw3"]


def test_games_sort_ahead_of_generic_groups():
    """A panel opens with the game the user came for, not with shader caches."""
    mw3 = group_for("game_cleanup:mw3:shader_cache_cleanup")
    shaders = group_for("game_cleanup:nvidia_shader_cache")
    windows = group_for("cleanup:temp_files")
    assert mw3 is not None and shaders is not None and windows is not None
    assert mw3.order < shaders.order
    # Windows cleanups head their own panel, where no game is listed.
    assert windows.order < shaders.order


def test_cleanups_split_by_who_wrote_the_files():
    """The four buckets the cleanup panel renders, each proven by one member."""
    assert group_for("cleanup:temp_files").id == "windows"  # type: ignore[union-attr]
    assert group_for("cleanup:browser_cache").id == "apps"  # type: ignore[union-attr]
    assert group_for("cleanup:cargo_cache").id == "developer"  # type: ignore[union-attr]
    assert group_for("cleanup:wsl_compact").id == "containers"  # type: ignore[union-attr]


def test_the_group_reaches_the_wire(all_settings):
    """The API carries it: a group nobody can read is the same as no group.

    Checked against the response builder rather than a live request, because the
    endpoint's own registry does hardware discovery this assertion has no use for.
    """
    from fpstune.api.definitions_view import setting_to_response

    game_setting = next(s for s in all_settings if s.module == "game_config")
    response = setting_to_response(game_setting)
    expected = group_for(game_setting.id)
    assert expected is not None
    assert response.group_id == expected.id
    assert response.group_label == expected.label
    assert response.group_order == expected.order

    flat = next(s for s in all_settings if s.module == "power")
    flat_response = setting_to_response(flat)
    assert flat_response.group_id is None
    assert flat_response.group_label is None
    assert flat_response.group_order is None


def test_an_unknown_id_is_not_forced_into_a_group():
    """A module-only id, or an unknown cleanup, resolves nothing."""
    assert group_for("cleanup") is None
    assert group_for("cleanup:not_a_real_cleanup") is None
    assert group_for("") is None

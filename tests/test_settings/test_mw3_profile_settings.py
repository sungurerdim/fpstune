"""Contract tests for MW3's (cod23) gamerprofile setting definitions.

These guard the properties that are easy to break by copying a neighbouring
setting or the MW4 file this family mirrors: the scope index that makes a key
unambiguous, the two games' different stock values for the same key, and the
guards whose whole job is that ``recommended_value`` equals ``default_value``.

Nothing here reads the developer's machine or a real install. Every value
asserted is one the definitions declare.
"""

from __future__ import annotations

import pytest

from fpstune.settings.definitions.game_configs_mw3_profile import MW3_PROFILE_SETTINGS
from fpstune.settings.groups import group_for

# Every setting whose recommendation is its default: it changes nothing on a
# correct machine and puts back what something else moved (product consequence
# 2). Kept as a list rather than derived, so a tweak that silently became a
# guard — or a guard that silently became a tweak — shows up as a failure here
# instead of passing a test that asks the code what it already does.
GUARDS = {
    "ads_sensitivity": "1.000000",
    "ads_zoom_sensitivity": "1.000000",
    "ads_hold_breath_sensitivity": "1.000000",
    "tactical_ads_sensitivity": "1.000000",
    "mouse_monitor_distance_coeff": "1.333333",
    "mouse_vertical_sensibility": "1.000000",
    "mouse_acceleration": "0.000000",
    "mouse_filter": "0.000000",
    "mouse_smoothing": "false",
    "ads_fov_scaling": "true",
    "gamepad_aim": "false",
}

# A tweak moves the machine; a guard puts it back. `fov` is the only one here
# that is offered rather than applied — it changes what the screen shows, so
# consequence 5 puts it in COMPLETE while the other three sit in the default
# scope. It still belongs on this list: it has a recommendation that differs
# from its default, which is the whole distinction this pairing tests.
TWEAKS = (
    "sprint_assist_delay_kbm",
    "sprint_assist_delay_gamepad",
    "ads_timing_sensitivity",
    "fov",
)


def _keys_of(setting) -> list[str]:
    """Every key a setting addresses. A named-compound declares several."""
    key = setting.detect_args["batch_key"]
    return [str(k) for k in key] if isinstance(key, (list, tuple)) else [str(key)]


def _by_name(name: str):
    return next(s for s in MW3_PROFILE_SETTINGS if s.id == f"game_config:mw3:{name}")


class TestEveryKeyIsUnambiguous:
    @pytest.mark.parametrize("setting", MW3_PROFILE_SETTINGS, ids=lambda s: s.id)
    def test_key_carries_a_scope_index(self, setting) -> None:
        """`Name` alone is not a key.

        The older of MW3's two profile schemas omits the digit, and the matcher
        accepts that — but a *declaration* without one would also match a file
        that has two scopes, which is how MW4's `DxrMode` would be written the
        wrong control's value.
        """
        for key in _keys_of(setting):
            name, sep, scope = key.rpartition("@")
            assert sep, f"{setting.id}: key {key!r} has no @<scope> suffix"
            assert scope.isdigit(), f"{setting.id}: {scope!r} is not a scope index"
            assert name, f"{setting.id}: key {key!r} has no name"

    @pytest.mark.parametrize("setting", MW3_PROFILE_SETTINGS, ids=lambda s: s.id)
    def test_key_carries_no_hash_suffix(self, setting) -> None:
        """MW4 writes `;61129;7764` after the scope and MW3's profile does not.

        Declaring one either way pins the setting to a build's own hashes; the
        file is the only place they are correct.
        """
        for key in _keys_of(setting):
            assert ";" not in key

    @pytest.mark.parametrize("setting", MW3_PROFILE_SETTINGS, ids=lambda s: s.id)
    def test_detect_and_apply_address_the_same_key_and_file(self, setting) -> None:
        """A mismatch would verify one key after writing another."""
        assert setting.detect_args["batch_config"] == "mw3_profile"
        assert setting.apply_args["batch_config"] == "mw3_profile"
        assert setting.apply_args["batch_key"] == setting.detect_args["batch_key"]

    def test_the_graphics_file_is_not_addressed_from_here(self) -> None:
        """MW3's two config files are held apart: `mw3` is the graphics
        options.cst and `mw3_profile` is the gamerprofile. A key name can appear
        in both and the two have different line shapes."""
        for setting in MW3_PROFILE_SETTINGS:
            assert setting.detect_args["batch_config"] != "mw3"

    def test_ids_are_unique(self) -> None:
        ids = [s.id for s in MW3_PROFILE_SETTINGS]
        assert len(ids) == len(set(ids))

    def test_no_id_collides_with_the_graphics_settings(self) -> None:
        """Both files ship under `game_config:mw3:`, so a repeated id would give
        the registry two settings that cannot both be reached."""
        from fpstune.settings.definitions.game_configs import GAME_CONFIG_SETTINGS

        existing = {s.id for s in GAME_CONFIG_SETTINGS}
        clashes = sorted(s.id for s in MW3_PROFILE_SETTINGS if s.id in existing)
        assert not clashes, clashes

    def test_no_key_is_claimed_by_two_settings(self) -> None:
        """Two settings writing one key would each undo the other on apply."""
        seen: dict[str, str] = {}
        for setting in MW3_PROFILE_SETTINGS:
            for key in _keys_of(setting):
                assert key not in seen, f"{key} claimed by both {seen.get(key)} and {setting.id}"
                seen[key] = setting.id

    @pytest.mark.parametrize("setting", MW3_PROFILE_SETTINGS, ids=lambda s: s.id)
    def test_recommended_and_default_are_offered_choices(self, setting) -> None:
        """C6: detection must never return a value outside `choices`."""
        if not setting.choices:
            return
        assert str(setting.default_value) in setting.choices
        assert str(setting.recommended_value) in setting.choices

    @pytest.mark.parametrize("setting", MW3_PROFILE_SETTINGS, ids=lambda s: s.id)
    def test_every_setting_lands_under_the_games_heading(self, setting) -> None:
        """A heading is the backend's word: a setting with no group renders
        under no heading at all."""
        group = group_for(setting.id)
        assert group is not None and group.id == "mw3", setting.id


class TestTheThreeTweaks:
    """Everything else here is a guard. These three actually move a value."""

    @pytest.mark.parametrize("name", ["sprint_assist_delay_kbm", "sprint_assist_delay_gamepad"])
    def test_sprint_engages_without_a_wait(self, name: str) -> None:
        """400 is MW3's own stock — two account profiles on one install both
        held it — while MW4 ships the same key at 0. `default_value` has to stay
        MW3's, because that is what `reset` writes back to a user's machine."""
        setting = _by_name(name)
        assert setting.default_value == 400
        assert setting.recommended_value == 0

    def test_the_key_with_spaces_survives(self) -> None:
        """`Sprint Assist Delay KBM@0` cannot be tokenised on whitespace."""
        assert (
            _by_name("sprint_assist_delay_kbm").detect_args["batch_key"]
            == "Sprint Assist Delay KBM@0"
        )
        assert (
            _by_name("sprint_assist_delay_gamepad").detect_args["batch_key"]
            == "Sprint Assist Delay Gamepad@0"
        )

    def test_ads_timing_recommends_immediately(self) -> None:
        """Same defect class as mouse acceleration: the on-screen result of a
        given movement must not depend on where the ADS animation is."""
        setting = _by_name("ads_timing_sensitivity")
        assert setting.default_value == 1
        assert setting.recommended_value == 0
        assert (setting.min_value, setting.max_value) == (0, 2)

    def test_the_timing_enum_is_spelled_out_for_the_reader(self) -> None:
        """MW3 stores 0..2 where MW4 stores words, so a row would otherwise show
        a bare number. The mapping is measured, not assumed: the Touch sibling
        reads 1 in MW3 and `interpolated` in MW4 (tasks.md, "Measured facts").
        """
        hints = _by_name("ads_timing_sensitivity").value_hints
        assert set(hints) == {"0", "1", "2"}
        assert hints["0"].startswith("immediately")
        assert hints["1"].startswith("interpolated")
        assert hints["2"].startswith("delayed")

    @pytest.mark.parametrize("name", TWEAKS)
    def test_a_tweak_is_not_a_guard(self, name: str) -> None:
        setting = _by_name(name)
        assert setting.recommended_value != setting.default_value


class TestTheGuardsHoldTheirDefault:
    """A guard detects drift and puts the machine back; changing its value
    would make it a tweak, and a different one than the copy describes."""

    @pytest.mark.parametrize(("name", "expected"), sorted(GUARDS.items()))
    def test_recommended_equals_default(self, name: str, expected: str) -> None:
        setting = _by_name(name)
        assert str(setting.recommended_value) == expected
        assert str(setting.default_value) == expected

    def test_every_setting_is_a_guard_or_a_named_tweak(self) -> None:
        """The two lists have to cover the module, or a setting could be added
        without either being asserted."""
        names = {s.id.rsplit(":", 1)[-1] for s in MW3_PROFILE_SETTINGS}
        assert names == set(GUARDS) | set(TWEAKS)

    @pytest.mark.parametrize(("name", "expected"), sorted(GUARDS.items()))
    def test_a_guard_says_it_puts_something_back(self, name: str, expected: str) -> None:
        """Consequence 2: a guard's copy must not read as a change it makes.

        `recommended_impact` is the line a user reads before pressing apply, so
        on a correct machine it has to describe detecting drift and undoing it,
        not a benefit that arrives from the press.
        """
        text = _by_name(name).recommended_impact.lower()
        assert text.startswith(expected.lower() + ":")
        assert "puts" in text or "leaves" in text, text

    def test_the_monitor_distance_coefficient_is_never_moved(self) -> None:
        """tasks.md decision 2, owner-confirmed: every other sensitivity here is
        a multiplier layered on this coefficient, so moving it would rescale all
        of them at once."""
        setting = _by_name("mouse_monitor_distance_coeff")
        assert setting.recommended_value == setting.default_value == "1.333333"
        assert "never" in setting.description.lower()

    def test_ads_sensitivity_guards_the_neutral_multiplier(self) -> None:
        """tasks.md decision 1: 1.0 is the neutral point in both games, and the
        0.850000 the profiles held is drift rather than a second right answer."""
        setting = _by_name("ads_sensitivity")
        assert setting.recommended_value == setting.default_value == "1.000000"
        assert (setting.min_value, setting.max_value) == (0.1, 4.0)

    def test_zoom_sensitivity_is_a_six_key_compound_at_one_scope(self) -> None:
        """C8: six distinct cvars, one concept — a per-zoom offset. Writing one
        and not the others leaves the concept half-applied, and a drifted zoom
        level would hide behind five correct ones."""
        keys = _keys_of(_by_name("ads_zoom_sensitivity"))
        assert len(keys) == 6
        assert len({k.rpartition("@")[0] for k in keys}) == 6
        assert {k.rpartition("@")[2] for k in keys} == {"0"}


class TestFieldOfViewShipsOnAStatedDefault:
    """It was held back for one missing fact, and it ships because that fact arrived.

    `default_value` is what `reset` writes back, so it has to be the state the
    game actually ships with. MW3's line states only its range (`// 60 to 120`),
    every profile on the reference machine held the maximum, and MW4's 90 is
    MW4's — nothing readable said what MW3's stock was, and a guessed one would
    have made `reset` write a state the game never had (C9). The product owner
    stated 90 on 2026-09-10; that is a source, and the setting ships on it.

    These assertions therefore pin two different things: that the recommendation
    is the file's own maximum, and that the default is *not* equal to it. The
    second is the one that matters — collapse them and `reset` silently becomes
    a second apply.
    """

    def _fov(self):
        return next(s for s in MW3_PROFILE_SETTINGS if s.id == "game_config:mw3:fov")

    def test_it_recommends_the_files_maximum_from_the_games_own_default(self) -> None:
        setting = self._fov()

        assert setting.default_value == "90.000000"
        assert setting.recommended_value == "120.000000"
        assert setting.default_value != setting.recommended_value

    def test_the_recommendation_is_the_declared_maximum(self) -> None:
        """120 is the ceiling the line's own `// 60 to 120` states, not a number
        chosen here — so a build that raises the cap makes this fail loudly."""
        setting = self._fov()

        assert setting.max_value == 120.0
        assert float(str(setting.recommended_value)) == setting.max_value

    def test_it_is_offered_rather_than_assumed(self) -> None:
        """Consequence 5: it changes what the screen shows and costs frames, so
        COMPLETE. In RECOMMENDED it would be applied to players who never asked
        for a smaller apparent target."""
        assert self._fov().scope.name == "COMPLETE"


class TestWhatIsDeliberatelyNotShipped:
    def test_the_binary_profile_keys_are_not_claimed(self) -> None:
        """Automatic Sprint, Tactical Sprint Behavior, mount and akimbo live in
        the `.csb0`/`.csb1` blobs, which store values with no key names. Writing
        blind would risk the player's whole profile (C1)."""
        ids = {s.id.rsplit(":", 1)[-1] for s in MW3_PROFILE_SETTINGS}
        for absent in ("automatic_sprint", "tactical_sprint_behavior", "akimbo_behavior"):
            assert absent not in ids

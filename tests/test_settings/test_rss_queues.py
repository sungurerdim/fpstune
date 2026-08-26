"""RSS queue counts belong to the driver, not to a constant in this repo.

`create_rss_queues_setting` shipped `choices=("1", "2", "4")` and
`default_value="4"` for every adapter on every machine. The CI runner's NIC
offers sixteen queues and was running at sixteen, so the setting read a value
outside its own `choices` and its verification could never succeed — the same
class of defect as the 1024-buffer constant (#45) and the `1Gbps_Full`
recommendation on a 2.5GbE adapter, both of which shipped and were both wrong on
real hardware.

Everything here is about deriving those numbers from what the adapter says about
itself: `ValidRegistryValues` when the driver publishes an enum, the numeric
min/max range when it publishes a range instead.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from fpstune.settings.definitions.network import (
    create_rss_queues_setting,
    rss_queue_recommendation,
)
from fpstune.settings.discovery.network import register_adapter_settings
from fpstune.settings.discovery.probes import (
    positive_ints,
    powers_of_two_between,
)
from fpstune.settings.registry import SettingsRegistry


class TestParsingWhatTheDriverPublishes:
    def test_an_enum_of_strings_is_read(self) -> None:
        """`ValidRegistryValues` arrives as text on most drivers."""
        assert positive_ints(["1", "2", "4", "8", "16"]) == [1, 2, 4, 8, 16]

    def test_a_single_valued_enum_is_not_a_list(self) -> None:
        """PowerShell unwraps one-element arrays, so a scalar must still parse."""
        assert positive_ints("2") == [2]

    def test_junk_is_dropped_rather_than_guessed_at(self) -> None:
        assert positive_ints(["x", 0, -1, None, "4"]) == [4]

    def test_nothing_publishable_yields_nothing(self) -> None:
        """An empty answer must stay empty — this is what gates registration."""
        assert positive_ints([]) == []
        assert positive_ints(None) == []

    def test_a_range_expands_to_powers_of_two(self) -> None:
        """A count of 3 has no meaning: RSS indirection is sized by hash bits."""
        assert powers_of_two_between(1, 16) == [1, 2, 4, 8, 16]

    def test_a_range_respects_its_floor(self) -> None:
        assert powers_of_two_between("2", "8") == [2, 4, 8]

    def test_an_impossible_range_yields_nothing(self) -> None:
        assert powers_of_two_between(16, 1) == []
        assert powers_of_two_between(None, None) == []


class TestTheRecommendation:
    """Two queues is the target, but only where the driver offers it."""

    def test_two_when_the_driver_offers_two(self) -> None:
        assert rss_queue_recommendation(("1", "2", "4", "8", "16")) == "2"

    def test_the_next_count_up_when_it_does_not(self) -> None:
        """Four is closer to the intent than sixteen is."""
        assert rss_queue_recommendation(("1", "4", "16")) == "4"

    def test_the_only_count_there_is(self) -> None:
        """A single-queue driver is left alone rather than told to do the impossible."""
        assert rss_queue_recommendation(("1",)) == "1"

    def test_the_largest_when_nothing_reaches_two(self) -> None:
        assert rss_queue_recommendation(("1",)) == "1"

    def test_a_driver_with_no_low_counts_gets_its_smallest(self) -> None:
        assert rss_queue_recommendation(("8", "16")) == "8"


class TestTheSettingReflectsTheAdapter:
    def test_choices_are_the_drivers_own(self) -> None:
        """The exact CI case: a 16-queue NIC must be able to report 16."""
        setting = create_rss_queues_setting(14, "Ethernet", ("1", "2", "4", "8", "16"), "16")
        assert setting.choices == ("1", "2", "4", "8", "16")
        assert "16" in setting.choices, (
            "the CI runner's NIC reads 16; a hardcoded ('1','2','4') made that "
            "reading unverifiable no matter whether the write worked"
        )

    def test_the_default_is_the_drivers_own(self) -> None:
        setting = create_rss_queues_setting(14, "Ethernet", ("1", "2", "4", "8", "16"), "16")
        assert setting.default_value == "16"

    def test_the_recommendation_is_always_a_choice(self) -> None:
        """A recommendation outside `choices` can be shown and never applied."""
        for counts in (("1", "2", "4"), ("1",), ("8", "16"), ("2", "4")):
            setting = create_rss_queues_setting(1, "A", counts, counts[-1])
            assert setting.recommended_value in setting.choices

    def test_the_impact_text_names_the_real_numbers(self) -> None:
        """ "2 queues" was written into the copy while the adapter ran sixteen."""
        setting = create_rss_queues_setting(14, "Ethernet", ("1", "2", "4", "8", "16"), "16")
        assert "16" in setting.current_impact
        assert "2 queues" in setting.recommended_impact

    def test_no_values_is_refused_rather_than_defaulted(self) -> None:
        """There is no safe constant to fall back to — that was the whole defect."""
        with pytest.raises(ValueError, match="no queue counts"):
            create_rss_queues_setting(14, "Ethernet", (), "4")


def _registry_reading(payload: object) -> dict:
    """Run `rss_queue_options` against a described PowerShell answer."""
    registry = SettingsRegistry(discover_dynamic=False)
    completed = subprocess.CompletedProcess(
        args=["powershell"], returncode=0, stdout=json.dumps(payload), stderr=""
    )
    with patch("fpstune.settings.discovery.probes.subprocess.run", return_value=completed):
        return registry._probes.rss_queue_options()


class TestDiscoveryReadsTheMachine:
    def test_an_enum_driver_is_read_whole(self) -> None:
        options = _registry_reading({"14": {"valid": ["1", "2", "4", "8", "16"], "default": "16"}})
        assert options == {14: (("1", "2", "4", "8", "16"), "16")}

    def test_a_range_driver_is_expanded(self) -> None:
        """Some drivers publish min/max instead of an enum; both are real."""
        options = _registry_reading({"7": {"valid": [], "min": 1, "max": 8, "default": "8"}})
        assert options == {7: (("1", "2", "4", "8"), "8")}

    def test_an_adapter_that_publishes_nothing_is_absent(self) -> None:
        """Absent from the result means 'register no setting for this adapter'."""
        assert _registry_reading({"3": {"valid": [], "default": ""}}) == {}

    def test_a_default_the_driver_does_not_accept_is_not_believed(self) -> None:
        """A default outside the enum would be a value the UI can never restore."""
        options = _registry_reading({"5": {"valid": ["1", "2"], "default": "32"}})
        assert options == {5: (("1", "2"), "2")}

    def test_a_failed_query_registers_nothing_rather_than_guessing(self) -> None:
        registry = SettingsRegistry(discover_dynamic=False)
        failed = subprocess.CompletedProcess(
            args=["powershell"], returncode=1, stdout="", stderr="denied"
        )
        with patch("fpstune.settings.discovery.probes.subprocess.run", return_value=failed):
            assert registry._probes.rss_queue_options() == {}

    def test_unparseable_output_registers_nothing(self) -> None:
        registry = SettingsRegistry(discover_dynamic=False)
        garbage = subprocess.CompletedProcess(
            args=["powershell"], returncode=0, stdout="not json at all", stderr=""
        )
        with patch("fpstune.settings.discovery.probes.subprocess.run", return_value=garbage):
            assert registry._probes.rss_queue_options() == {}


class TestRegistrationIsGatedOnTheReading:
    """No derived values, no setting — never a fallback constant."""

    def _register(self, rss_queue_options):
        registry = SettingsRegistry(discover_dynamic=False)
        register_adapter_settings(registry, 14, "Ethernet", "802.3", rss_queue_options)
        return {s.id for s in registry.get_all()}

    def test_registered_when_the_driver_publishes_values(self) -> None:
        assert "network:14:rss_queues" in self._register((("1", "2", "4", "8"), "8"))

    def test_not_registered_when_it_does_not(self) -> None:
        """Same user-visible outcome as the `not_supported` detect would give,
        without paying for a scan of a setting that can never apply."""
        assert "network:14:rss_queues" not in self._register(None)

    def test_the_other_adapter_settings_are_unaffected(self) -> None:
        """Gating one setting must not drop the fifteen beside it."""
        ids = self._register(None)
        assert "network:14:interrupt_moderation" in ids
        assert "network:14:flow_control" in ids

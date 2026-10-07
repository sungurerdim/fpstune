"""The keyword resolver: one table of which RegistryKeyword names which concept.

A driver's advanced property is addressed by the keyword its INF declares. The
label beside it is translated by the driver, so a lookup that reaches for the
label reads one thing on an English Windows and nothing on a Turkish or German
one. These tests pin the Python half (discovery, defaults, the accepted-value
check); ``tests/test_windows_contract/test_keyword_resolution.py`` runs the
PowerShell half against a fake adapter that answers in Turkish and German.
"""

from __future__ import annotations

import pytest

from fpstune.settings.applicability import ABSENT_READINGS, NOT_SUPPORTED, is_absent_reading
from fpstune.settings.definitions.network import (
    create_advanced_eee_setting,
    create_eee_setting,
    create_flow_control_setting,
    create_interrupt_moderation_setting,
    create_roaming_aggressiveness_setting,
    create_throughput_booster_setting,
    create_uapsd_setting,
)
from fpstune.settings.discovery.keyword_resolver import (
    CONCEPTS,
    AdapterProperty,
    KeywordConcept,
    accepts,
    concept,
    find,
    resolve,
)
from fpstune.settings.discovery.network import offer_accepted_choices


def table(*props: AdapterProperty) -> dict[str, AdapterProperty]:
    """An adapter's property table the way the probe stores it: lowercase keys."""
    return {prop.keyword.lower(): prop for prop in props}


ENABLED_DISABLED = ("0", "1")


class TestOldAndNewSpellings:
    """The standardised ``*`` keyword and the bare vendor one name one concept."""

    @pytest.mark.parametrize(
        ("published", "vendor"),
        [
            ("*EEE", "Intel"),
            ("EEE", "Realtek"),
            ("EEEControl", "Broadcom"),
            ("EnergyEfficientEthernet", "an older driver"),
        ],
    )
    def test_each_spelling_resolves_to_the_adapters_own(self, published: str, vendor: str) -> None:
        found = find(concept("eee"), table(AdapterProperty(published, ENABLED_DISABLED)))
        assert found is not None, vendor
        assert found.keyword == published

    def test_the_preferred_spelling_wins_whatever_order_the_driver_lists(self) -> None:
        both = table(AdapterProperty("EEE"), AdapterProperty("*EEE"))
        reversed_ = table(AdapterProperty("*EEE"), AdapterProperty("EEE"))
        for properties in (both, reversed_):
            found = find(concept("eee"), properties)
            assert found is not None
            assert found.keyword == "*EEE"

    def test_spelling_case_does_not_matter(self) -> None:
        found = find(concept("flow_control"), table(AdapterProperty("*FLOWCONTROL")))
        assert found is not None

    def test_a_stem_finds_the_vendor_family_spelling(self) -> None:
        for keyword in ("uAPSDSupport", "UAPSD"):
            assert concept("uapsd").matches(keyword), keyword
        assert concept("throughput_booster").matches("ThroughputBoosterEnabled")

    def test_an_unrelated_keyword_is_not_claimed(self) -> None:
        assert not concept("uapsd").matches("*FlowControl")
        assert not concept("throughput_booster").matches("PowerSavingMode")
        assert not concept("eee").matches("AdvancedEEE")  # a different concept entirely


class TestTheDisplayNameIsNotAnInput:
    """The resolver has no way to read a label, so a label cannot change an answer."""

    def test_a_property_is_found_by_keyword_whatever_its_label_says(self) -> None:
        # The same Intel keyword, labelled in English, Turkish or German: the
        # property table carries no label, so the answer is one answer.
        found = find(concept("uapsd"), table(AdapterProperty("uAPSDSupport", ENABLED_DISABLED)))
        assert found == AdapterProperty("uAPSDSupport", ENABLED_DISABLED)

    def test_a_label_on_an_unknown_keyword_claims_nothing(self) -> None:
        """An English "U-APSD" label on a keyword the table does not know stays unmatched."""
        vendor_specific = table(AdapterProperty("VendorPowerSavePoll", ENABLED_DISABLED))
        assert find(concept("uapsd"), vendor_specific) is None

    def test_the_property_record_has_no_label_field(self) -> None:
        assert set(AdapterProperty._fields) == {"keyword", "valid", "minimum", "maximum"}


class TestAbsentIsASentinel:
    def test_no_such_keyword_reads_as_not_supported(self) -> None:
        resolution = resolve(
            concept("advanced_eee"), table(AdapterProperty("*FlowControl")), (0, 1)
        )
        assert resolution.keyword is None
        assert resolution.reading == NOT_SUPPORTED
        assert is_absent_reading(resolution.reading)
        assert resolution.reading in ABSENT_READINGS

    def test_an_adapter_with_no_properties_at_all_is_absent(self) -> None:
        assert resolve(concept("eee"), {}, (0, 1)).reading == NOT_SUPPORTED

    def test_a_present_property_reads_as_its_own_spelling(self) -> None:
        resolution = resolve(
            concept("eee"), table(AdapterProperty("EEE", ENABLED_DISABLED)), (0, 1)
        )
        assert resolution.reading == "EEE"
        assert not is_absent_reading(resolution.reading)
        assert resolution.refused == ()


class TestValuesAreCheckedAgainstTheDriversOwnList:
    def test_an_enum_lists_exactly_what_it_takes(self) -> None:
        prop = AdapterProperty("*FlowControl", ("0", "3"))
        assert accepts(prop, 0)
        assert accepts(prop, 3)
        assert not accepts(prop, 1)
        assert not accepts(prop, 2)

    def test_the_listed_numbers_may_arrive_padded(self) -> None:
        assert accepts(AdapterProperty("*FlowControl", (" 0 ", "3")), 3)

    def test_a_numeric_range_bounds_the_value(self) -> None:
        prop = AdapterProperty("*RoamAggressiveness", (), 0, 2)
        assert accepts(prop, 0)
        assert accepts(prop, 2)
        assert not accepts(prop, 3)
        assert not accepts(prop, 4)
        assert not accepts(prop, -1)

    def test_the_list_beats_the_range_when_a_driver_publishes_both(self) -> None:
        prop = AdapterProperty("*FlowControl", ("0", "3"), 0, 10)
        assert not accepts(prop, 5)

    def test_a_range_of_zero_to_zero_is_not_a_range(self) -> None:
        """``NumericParameterMaxValue`` reads 0 on properties that are not numeric at all."""
        assert accepts(AdapterProperty("uAPSDSupport", (), 0, 0), 1)

    def test_nothing_published_gives_nothing_to_contradict(self) -> None:
        assert accepts(AdapterProperty("uAPSDSupport"), 1)

    def test_out_of_range_values_come_back_as_refused(self) -> None:
        resolution = resolve(
            concept("roaming_aggressiveness"),
            table(AdapterProperty("RoamAggressiveness", (), 0, 2)),
            (0, 1, 2, 3, 4),
        )
        assert resolution.keyword == "RoamAggressiveness"
        assert resolution.refused == (3, 4)
        assert resolution.reading == NOT_SUPPORTED

    def test_a_driver_that_lists_both_switch_values_is_not_refused(self) -> None:
        resolution = resolve(
            concept("uapsd"), table(AdapterProperty("uAPSDSupport", ENABLED_DISABLED)), (0, 1)
        )
        assert resolution.refused == ()
        assert resolution.reading == "uAPSDSupport"


class TestAConceptIsSafeToSpellIntoACommand:
    @pytest.mark.parametrize("hostile", ["x'; Remove-Item C:\\ #", "*", "", "a b", "EEE'"])
    def test_a_spelling_that_could_close_the_quote_is_refused(self, hostile: str) -> None:
        with pytest.raises(ValueError, match="not a keyword"):
            KeywordConcept("hostile", (hostile,))

    def test_a_concept_must_name_something(self) -> None:
        with pytest.raises(ValueError, match="names no keyword"):
            KeywordConcept("empty")

    def test_an_unknown_concept_is_a_bug_not_an_absence(self) -> None:
        with pytest.raises(KeyError, match="no keyword concept"):
            concept("not_a_concept")

    def test_every_listed_spelling_reaches_the_generated_condition(self) -> None:
        for name, known in CONCEPTS.items():
            condition = known.ps_select()
            for spelling in known.spellings:
                assert f"'{spelling}'" in condition, (name, spelling)
            for stem in known.stems:
                assert stem in condition, (name, stem)


class TestSettingsDeclareTheirConcept:
    FACTORIES = {
        "interrupt_moderation": create_interrupt_moderation_setting,
        "flow_control": create_flow_control_setting,
        "eee": create_eee_setting,
        "advanced_eee": create_advanced_eee_setting,
        "roaming_aggressiveness": create_roaming_aggressiveness_setting,
        "uapsd": create_uapsd_setting,
        "throughput_booster": create_throughput_booster_setting,
    }

    def test_the_table_and_the_settings_cover_the_same_concepts(self) -> None:
        assert set(self.FACTORIES) == set(CONCEPTS)

    @pytest.mark.parametrize("name", sorted(FACTORIES))
    def test_detect_and_apply_search_what_the_concept_lists(self, name: str) -> None:
        setting = self.FACTORIES[name](14, "Wi-Fi")
        known = concept(name)
        assert setting.detect_args["keyword_concept"] == name
        for command in (setting.detect_command, setting.apply_command):
            assert known.ps_select() in command
        batch = setting.detect_args.get("batch_adapter_keyword")
        if batch is not None:
            assert batch == list(known.spellings)

    @pytest.mark.parametrize("name", sorted(FACTORIES))
    def test_no_command_reads_a_label(self, name: str) -> None:
        setting = self.FACTORIES[name](14, "Wi-Fi")
        assert "DisplayName" not in setting.detect_command + setting.apply_command

    @pytest.mark.parametrize("name", sorted(FACTORIES))
    def test_apply_checks_the_drivers_own_list_before_writing(self, name: str) -> None:
        command = self.FACTORIES[name](14, "Wi-Fi").apply_command
        assert "ValidRegistryValues" in command
        assert "NumericParameterMaxValue" in command
        assert command.index("ValidRegistryValues") < command.index(
            "Set-NetAdapterAdvancedProperty"
        )


class TestOfferingOnlyWhatTheDriverAccepts:
    def test_choices_the_driver_refuses_are_not_offered(self) -> None:
        declared = create_flow_control_setting(14, "Ethernet")
        driver = table(AdapterProperty("*FlowControl", ("0", "3")))
        offered = offer_accepted_choices(declared, driver)
        assert offered is not None
        assert offered.choices == ("Rx & Tx Enabled", "Disabled")
        assert offered.recommended_value in offered.choices
        assert offered.default_value in offered.choices

    def test_a_driver_that_refuses_the_recommended_value_gets_no_setting(self) -> None:
        declared = create_uapsd_setting(14, "Wi-Fi")  # recommends Disabled == 0
        driver = table(AdapterProperty("uAPSDSupport", ("1",)))
        assert offer_accepted_choices(declared, driver) is None

    def test_a_driver_that_refuses_the_default_gets_no_setting(self) -> None:
        declared = create_uapsd_setting(14, "Wi-Fi")  # stock Enabled == 1
        driver = table(AdapterProperty("uAPSDSupport", ("0",)))
        assert offer_accepted_choices(declared, driver) is None

    def test_a_full_range_changes_nothing(self) -> None:
        declared = create_roaming_aggressiveness_setting(14, "Wi-Fi")
        driver = table(AdapterProperty("RoamAggressiveness", (), 0, 4))
        assert offer_accepted_choices(declared, driver) == declared

    def test_an_absent_keyword_is_left_to_detection_to_report(self) -> None:
        declared = create_eee_setting(14, "Ethernet")
        assert offer_accepted_choices(declared, table(AdapterProperty("*FlowControl"))) == declared

    def test_an_unread_table_is_not_a_refusal(self) -> None:
        declared = create_eee_setting(14, "Ethernet")
        assert offer_accepted_choices(declared, {}) == declared

    def test_a_setting_with_no_concept_is_untouched(self) -> None:
        from fpstune.settings.definitions.network import create_lso_setting

        declared = create_lso_setting(14, "Ethernet")
        assert offer_accepted_choices(declared, table(AdapterProperty("*LsoV2IPv4", ("9",)))) == (
            declared
        )

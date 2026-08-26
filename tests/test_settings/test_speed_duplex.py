"""Link negotiation must never be forced by a recommendation.

fpstune shipped `recommended_value="1Gbps_Full"` for Speed & Duplex, describing
it as preventing "auto-negotiation fallback". That reasoning is backwards.
IEEE 802.3 recommends auto-negotiation on every connection and makes it
mandatory at 1 GbE and above; forcing one end while the far end negotiates is
the textbook cause of a duplex mismatch, because the negotiating end can read
the speed but not the duplex and the standard then requires half duplex. The
link comes up and is quietly broken: collisions, retransmissions, latency spikes
and loss — the "packet loss / packet burst" symptom picture exactly.

Measured on the dev machine: a Realtek 2.5GbE adapter that this setting had
forced to 1.0 Gbps Full was linked at 100 Mbps, and the driver's own valid value
for its top speed is 2500 — so forcing also discarded 60% of the adapter.
"""

from __future__ import annotations

from fpstune.settings.definitions.network import create_speed_duplex_setting


def _speed_duplex(interface_index: int = 42):
    return create_speed_duplex_setting(interface_index, "Test Adapter")


def test_auto_negotiation_is_what_we_recommend() -> None:
    setting = _speed_duplex()
    assert setting.recommended_value == "Auto_Negotiation", (
        "forcing speed/duplex breaks the far end's duplex detection; IEEE 802.3 "
        "requires auto-negotiation at 1 GbE and above"
    )
    assert setting.default_value == "Auto_Negotiation"


def test_the_command_normalises_every_value_itself() -> None:
    """The enum is vendor-extended, so translation cannot live in `value_map`.

    2.5 Gbps is 2500 on this driver family where the NDIS range would suggest 7.
    A map built from one driver leaves every other adapter reporting a bare
    integer outside its own `choices` — the C6 violation this codebase has
    already fixed twice. The command therefore maps what it knows and folds
    everything else into a single "not negotiating" reading.
    """
    setting = _speed_duplex()
    assert setting.value_map == {}, "translation belongs in the command, not a partial map"
    for raw, token in (
        (0, "Auto_Negotiation"),
        (1, "10Mbps_Half"),
        (2, "10Mbps_Full"),
        (3, "100Mbps_Half"),
        (4, "100Mbps_Full"),
        (5, "1Gbps_Half"),
        (6, "1Gbps_Full"),
        (2500, "2.5Gbps_Full"),
    ):
        assert f"{raw} {{ '{token}' }}" in setting.detect_command
        assert token in setting.choices
    assert "default { 'Forced_Other' }" in setting.detect_command
    assert "Forced_Other" in setting.choices


def test_the_snapshot_shortcut_is_not_used() -> None:
    """The adapter snapshot hands back the raw number with no "unrecognised"."""
    setting = _speed_duplex()
    assert "batch_adapter_keyword" not in setting.detect_args


def test_every_settable_choice_can_be_applied() -> None:
    """A choice with no apply mapping is a value the UI offers and cannot write."""
    setting = _speed_duplex()
    for choice in setting.choices:
        if choice == "Forced_Other":
            # A reading, not a target: no single number could write it, and
            # fpstune has no reason to help a user force a speed.
            assert choice not in setting.apply_value_map
            continue
        assert choice in setting.apply_value_map, f"{choice} cannot be applied"


def test_apply_and_detect_agree_on_every_value() -> None:
    """Round-trip: what apply writes must be what detect normalises back to."""
    setting = _speed_duplex()
    for choice, raw in setting.apply_value_map.items():
        assert f"{raw} {{ '{choice}' }}" in setting.detect_command, (
            f"apply writes {raw} for {choice} but detect does not read it back"
        )

"""Tests for network setting definitions."""

import pytest

from fpstune.settings.base import SettingExecutor, SettingValueType
from fpstune.settings.definitions import network as network_module
from fpstune.settings.definitions.network import (
    CLOUDFLARE_FAMILY_IPS,
    CLOUDFLARE_SECURITY_IPS,
    CLOUDFLARE_STANDARD_IPS,
    CONGESTION_PROVIDER,
    DNS_LOCAL_PRIORITY,
    DNS_OVER_HTTPS,
    DNS_SECURITY,
    IPV6_PRIVACY,
    IPV6_RANDOM_IDS,
    NAGLE_ALGORITHM,
    NETWORK_SETTINGS,
    NETWORK_THROTTLING,
    NETWORK_THROTTLING_KEY,
    QOS_BANDWIDTH,
    RECEIVE_SEGMENT_COALESCING,
    RECEIVE_SIDE_SCALING,
    SCALING_HEURISTICS,
    TCP_AUTO_TUNING,
    TEREDO,
    create_checksum_offload_setting,
    create_eee_setting,
    create_flow_control_setting,
    create_interrupt_moderation_setting,
    create_lso_setting,
    create_msi_mode_setting,
    create_packet_coalescing_setting,
    create_power_management_setting,
    create_roaming_aggressiveness_setting,
    create_rss_base_processor_setting,
    create_throughput_booster_setting,
    create_uapsd_setting,
)


class TestNetworkSettingConstants:
    """Tests for network setting constants."""

    def test_cloudflare_security_ips(self) -> None:
        """Verify Cloudflare security DNS IPs."""
        assert CLOUDFLARE_SECURITY_IPS == ("1.1.1.2", "1.0.0.2")

    def test_cloudflare_family_ips(self) -> None:
        """Verify Cloudflare family DNS IPs."""
        assert CLOUDFLARE_FAMILY_IPS == ("1.1.1.3", "1.0.0.3")

    def test_cloudflare_standard_ips(self) -> None:
        """Verify Cloudflare standard DNS IPs."""
        assert CLOUDFLARE_STANDARD_IPS == ("1.1.1.1", "1.0.0.1")

    def test_network_throttling_key(self) -> None:
        """Verify network throttling registry path."""
        assert NETWORK_THROTTLING_KEY == (
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
        )


class TestStaticNetworkSettings:
    """Tests for static network settings."""

    @pytest.mark.parametrize(
        "setting",
        [
            TCP_AUTO_TUNING,
            NAGLE_ALGORITHM,
            SCALING_HEURISTICS,
            CONGESTION_PROVIDER,
            RECEIVE_SIDE_SCALING,
            RECEIVE_SEGMENT_COALESCING,
            NETWORK_THROTTLING,
            DNS_SECURITY,
            DNS_LOCAL_PRIORITY,
            QOS_BANDWIDTH,
            IPV6_PRIVACY,
            IPV6_RANDOM_IDS,
            TEREDO,
        ],
    )
    def test_setting_has_required_fields(self, setting: SettingExecutor) -> None:
        """Each static setting must have required fields."""
        assert setting.id, "Setting must have an ID"
        assert setting.category, "Setting must have a category"
        assert setting.display_name, "Setting must have a display name"
        assert ":" in setting.id, "Setting ID must contain ':' separator"

    def test_every_setting_defined_in_the_module_is_registered(self) -> None:
        """A definition written into network.py and left out of the list ships to nobody.

        This replaces `len(NETWORK_SETTINGS) == 28`. That assertion could not
        express the contract it was standing in for: a setting defined at module
        level and forgotten in `NETWORK_SETTINGS` moves the count by zero, so the
        count stayed green while the setting was invisible to the registry, the
        API and the UI alike. What it did instead was fail on every legitimate
        addition, which taught the reader to bump the number rather than ask
        whether the change was intended -- and the number did move, 26 to 28,
        between two audits.

        Derived from the module either way, so adding a setting correctly needs no
        edit here and adding one incorrectly fails here.
        """
        defined = {
            value.id
            for value in vars(network_module).values()
            if isinstance(value, SettingExecutor)
        }
        registered = {setting.id for setting in NETWORK_SETTINGS}

        assert sorted(defined - registered) == [], (
            "defined in definitions/network.py and absent from NETWORK_SETTINGS, "
            "so the registry never discovers them"
        )
        assert sorted(registered - defined) == [], (
            "listed in NETWORK_SETTINGS with no module-level definition, so this "
            "test can no longer see the whole set it is meant to guard"
        )

    def test_no_setting_is_registered_twice(self) -> None:
        """A duplicate entry makes detect and apply run the same command twice.

        The list is assembled by hand, so a copy-paste that repeats an entry is
        the failure mode. Two identical ids also collide in the registry's
        id-keyed map, where the second silently wins.
        """
        setting_ids = [setting.id for setting in NETWORK_SETTINGS]
        duplicates = sorted({i for i in setting_ids if setting_ids.count(i) > 1})
        assert duplicates == [], f"registered more than once: {duplicates}"

    def test_network_settings_list(self) -> None:
        """NETWORK_SETTINGS list should contain all static settings."""
        setting_ids = [s.id for s in NETWORK_SETTINGS]
        assert "network:tcp_auto_tuning" in setting_ids
        assert "network:nagle_algorithm" in setting_ids
        assert "network:dns_security" in setting_ids
        # Setting the resolver without encrypting the query only does half the job,
        # so these two ship together.
        assert "network:dns_over_https" in setting_ids
        assert "network:dns_local_priority" in setting_ids
        assert "network:qos_bandwidth" in setting_ids
        assert "network:ipv6_privacy" in setting_ids
        assert "network:teredo" in setting_ids
        assert "network:wifi_radio_when_wired" in setting_ids

    def test_tcp_auto_tuning_choices(self) -> None:
        """TCP auto-tuning should have correct choices."""
        assert TCP_AUTO_TUNING.value_type == SettingValueType.CHOICE
        assert "normal" in TCP_AUTO_TUNING.choices
        assert "disabled" in TCP_AUTO_TUNING.choices

    def test_network_throttling_value_map(self) -> None:
        """Network throttling value_map should map correctly."""
        assert NETWORK_THROTTLING.value_map[0xFFFFFFFF] == "disabled"
        assert NETWORK_THROTTLING.value_map[10] == "enabled"
        assert NETWORK_THROTTLING.value_map[None] == "enabled"

    def test_dns_security_choices(self) -> None:
        """DNS security should have correct choices."""
        assert "isp" in DNS_SECURITY.choices
        assert "cloudflare_security" in DNS_SECURITY.choices
        assert "cloudflare_family" in DNS_SECURITY.choices

    def test_no_dns_setting_claims_an_in_game_latency_gain(self) -> None:
        """DNS cannot move in-game latency, and the headline sums whatever is claimed.

        `lib/impact.ts` pushes every numeric `latency_ms` into the Gained/Potential
        figure shown on Home, and `dns_security` used to carry -12.0 -- the
        deterministic cap the impact_scores sweep applied, not a measurement. So the
        UI credited DNS with an invented 12 ms saving. Resolution happens once at
        connect time and match traffic goes straight to an IP, so any non-zero value
        here is a false claim rather than an optimistic one.
        """
        for setting in (DNS_SECURITY, DNS_OVER_HTTPS):
            latency = setting.impact_scores.get("latency_ms")
            assert latency == 0.0, (
                f"{setting.id} claims latency_ms={latency}, which the frontend adds to the "
                "user-visible latency total. DNS does not affect in-game latency."
            )


class TestAdapterSettingFactories:
    """Tests for per-adapter setting factory functions."""

    def test_create_interrupt_moderation_valid(self) -> None:
        """Factory should create valid setting for valid adapter."""
        setting = create_interrupt_moderation_setting(1, "Ethernet")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:1:interrupt_moderation"
        assert "Ethernet" in setting.display_name

    def test_create_flow_control_valid(self) -> None:
        """Factory should create valid flow control setting."""
        setting = create_flow_control_setting(2, "Ethernet")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:2:flow_control"

    def test_create_eee_valid(self) -> None:
        """Factory should create valid EEE setting."""
        setting = create_eee_setting(3, "Wi-Fi")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:3:eee"

    def test_create_power_management_valid(self) -> None:
        """Factory should create valid power management setting."""
        setting = create_power_management_setting(4, "Ethernet 2")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:4:power_management"

    def test_create_lso_valid(self) -> None:
        """Factory should create valid LSO setting."""
        setting = create_lso_setting(5, "Ethernet")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:5:lso"
        assert "Large Send Offload" in setting.display_name

    def test_create_checksum_offload_valid(self) -> None:
        """Factory should create valid checksum offload setting."""
        setting = create_checksum_offload_setting(6, "Ethernet")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:6:checksum_offload"
        assert "Checksum Offload" in setting.display_name

    def test_create_roaming_aggressiveness_valid(self) -> None:
        """Factory should create valid roaming aggressiveness setting."""
        setting = create_roaming_aggressiveness_setting(7, "Wi-Fi")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:7:roaming_aggressiveness"
        assert "Roaming Aggressiveness" in setting.display_name

    def test_create_uapsd_valid(self) -> None:
        """Factory should create valid WiFi U-APSD setting."""
        setting = create_uapsd_setting(8, "Wi-Fi")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:8:uapsd"
        assert setting.recommended_value == "Disabled"

    def test_create_throughput_booster_valid(self) -> None:
        """Factory should create valid WiFi Throughput Booster setting."""
        setting = create_throughput_booster_setting(9, "Wi-Fi")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:9:throughput_booster"
        assert setting.recommended_value == "Disabled"

    def test_create_packet_coalescing_valid(self) -> None:
        """Factory should create valid D0 packet coalescing setting."""
        setting = create_packet_coalescing_setting(10, "Wi-Fi")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:10:packet_coalescing"
        assert setting.recommended_value == "Disabled"

    def test_create_rss_base_processor_valid(self) -> None:
        """Factory should create valid RSS base processor setting."""
        setting = create_rss_base_processor_setting(11, "Ethernet")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:11:rss_base_processor"
        assert setting.recommended_value == "optimized"

    def test_create_msi_mode_valid(self) -> None:
        """Factory should create valid MSI mode setting with advanced risk."""
        setting = create_msi_mode_setting(12, "Ethernet")
        assert isinstance(setting, SettingExecutor)
        assert setting.id == "network:12:msi_mode"
        # C1 gate: advanced risk_level requires a non-None risk_warning
        assert setting.risk_level == "advanced"
        assert setting.risk_warning is not None
        assert setting.requires_reboot is True

    @pytest.mark.parametrize(
        "factory",
        [
            create_uapsd_setting,
            create_throughput_booster_setting,
            create_packet_coalescing_setting,
            create_rss_base_processor_setting,
            create_msi_mode_setting,
        ],
    )
    def test_new_factories_have_numeric_impact_score(self, factory: object) -> None:
        """C2 gate: each new setting has >=1 non-stability impact score."""
        setting = factory(1, "Test Adapter")  # type: ignore[operator]
        assert any(k != "stability" for k in setting.impact_scores), setting.id
        # C3 gate: description is a complete sentence ending with a period
        assert setting.description.endswith(".")

    def test_factory_uses_interface_index(self) -> None:
        """Factory uses numeric interface index (safe for commands)."""
        setting = create_interrupt_moderation_setting(42, "Test Adapter")
        assert "42" in setting.id
        assert "Test Adapter" in setting.display_name


class TestDnsResolverWiring:
    """Every offered resolver must be wired into detect *and* apply.

    #56 was exactly this class one level down: apply wrote every adapter while
    detect read one, so the UI reported success over a state that was never
    reached. A resolver present in `choices` but missing from either command is
    the same defect — the UI offers it, and one half of the pipeline has never
    heard of it.
    """

    @staticmethod
    def _setting():
        from fpstune.settings.registry import SettingsRegistry

        setting = SettingsRegistry(discover_dynamic=False).get("network:dns_security")
        assert setting is not None
        return setting

    def test_every_choice_is_known_to_both_commands(self) -> None:
        setting = self._setting()
        for choice in setting.choices:
            if choice == "isp":
                # The default branch: detect's fallback and apply's else.
                continue
            assert f"{choice} = '" in setting.detect_command, (
                f"{choice} is offered but detect can never report it"
            )
            assert f"'%value%' -eq '{choice}'" in setting.apply_command, (
                f"{choice} is offered but apply would fall through to the DHCP reset"
            )

    def test_quad9_is_the_default_and_the_ecs_endpoint_is_not(self) -> None:
        """Quad9 wins on the tiebreak, not on speed.

        Lookup speed is level — median 7 ms against 8 ms over 25 domains x 2
        rounds with the servers interleaved, which is noise. The tiebreak is
        EDNS Client Subnet: Quad9 sends the hint a CDN uses to pick an edge and
        Cloudflare does not, so patch downloads steer nearer.
        """
        setting = self._setting()
        assert setting.recommended_value == "quad9"
        assert "cloudflare_security" in setting.choices, (
            "the previous default must remain selectable, not vanish under users"
        )
        assert "9.9.9.11" not in setting.apply_command, (
            "Quad9's ECS endpoint measured p90 267 ms and is deliberately excluded"
        )

    def test_detect_expects_sorted_resolver_pairs(self) -> None:
        """Detect compares against Sort-Object output, so the literals must be sorted."""
        import re

        setting = self._setting()
        for name, pair in re.findall(r"(\w+) = '([\d.,]+)'", setting.detect_command):
            addresses = pair.split(",")
            assert addresses == sorted(addresses), (
                f"{name} literal {pair!r} is not sorted, so it can never match"
            )


class TestWifiRadioWhenWired:
    """The safety lives in the command, not in the warning.

    A user clicks past a warning once and lives with the setting for months. So
    apply refuses to disable the radio unless it can first see a connected wired
    link — it cannot take away the only link a machine has.
    """

    @staticmethod
    def _setting():
        from fpstune.settings.registry import SettingsRegistry

        setting = SettingsRegistry(discover_dynamic=False).get("network:wifi_radio_when_wired")
        assert setting is not None
        return setting

    def test_apply_refuses_without_a_connected_wired_link(self) -> None:
        command = self._setting().apply_command
        assert "refusing to disable Wi-Fi" in command
        # The refusal must be checked in the disable branch, before the disable.
        disable_branch = command.split("'radio_off'", 1)[1]
        assert disable_branch.index("$wired.Count -eq 0") < disable_branch.index(
            "Disable-NetAdapter"
        ), "the wired-link check must run before the adapter is disabled"

    def test_it_requires_an_explicit_confirmation(self) -> None:
        setting = self._setting()
        assert setting.risk_level == "advanced"
        assert setting.risk_warning
        assert "no network at all" in setting.risk_warning

    def test_reset_turns_the_radio_back_on(self) -> None:
        """default_value is what reset writes, so it must restore connectivity.

        This test passed for months while reset could not work at all: the enable
        branch looked the adapter up with `Get-NetAdapter -Physical`, which stops
        returning it once it is disabled, so fpstune could switch the radio off and
        never switch it back on. Asserting that a string appears in a command says
        nothing about whether that command can reach anything.
        `tests/test_windows_contract/test_wifi_radio.py` is the check that can fail.
        """
        setting = self._setting()
        assert setting.default_value == "radio_on"
        assert "Enable-NetAdapter" in setting.apply_command

    def test_it_reports_not_applicable_rather_than_pretending(self) -> None:
        """No Wi-Fi, or no wired link, means the recommendation is meaningless."""
        command = self._setting().detect_command
        assert "not_applicable" in command
        assert "not_applicable" in self._setting().choices

    def test_failures_are_reported_not_swallowed(self) -> None:
        command = self._setting().apply_command
        assert "-EA Stop" in command
        assert "'error: '" in command

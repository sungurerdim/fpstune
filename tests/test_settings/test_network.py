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
    TCP_AUTO_TUNING,
    TEREDO,
    create_checksum_offload_setting,
    create_eee_setting,
    create_flow_control_setting,
    create_interrupt_moderation_setting,
    create_lso_setting,
    create_msi_mode_setting,
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


class TestRetiredAndGuarded:
    """What a retired tweak leaves behind (consequence 6).

    Each of these once recommended a state that bought nothing a player can
    measure and cost something real: privacy, Xbox network connectivity, CPU on
    downloads, the QoS reserve voice chat uses. The guard recommends the
    harmless state so a machine already carrying the tweak is put back.
    """

    @pytest.mark.parametrize(
        ("setting", "harmless"),
        [
            (RECEIVE_SEGMENT_COALESCING, "enabled"),
            (IPV6_PRIVACY, "enabled"),
            (IPV6_RANDOM_IDS, "enabled"),
            (TEREDO, "enabled"),
            (QOS_BANDWIDTH, "standard"),
            (CONGESTION_PROVIDER, "CUBIC"),
        ],
    )
    def test_the_guard_recommends_the_windows_default(
        self, setting: SettingExecutor, harmless: str
    ) -> None:
        assert setting.default_value == harmless, setting.id
        assert setting.recommended_value == harmless, setting.id
        assert setting.risk_level != "advanced", setting.id

    def test_teredo_stock_is_the_default_client(self) -> None:
        """Windows ships Teredo as type=default; the old row called that 'disabled'."""
        assert TEREDO.value_map["default"] == "enabled"
        assert TEREDO.apply_value_map["enabled"] == "default"

    def test_qos_policy_guard_deletes_the_value(self) -> None:
        """Stock has no NonBestEffortLimit policy at all; any value is a change."""
        assert QOS_BANDWIDTH.apply_value_map["standard"] is None
        assert QOS_BANDWIDTH.value_map[None] == "standard"

    def test_default_ttl_reset_deletes_the_value(self) -> None:
        """Writing 128 left a value Windows never had; stock is the value's absence."""
        assert network_module.DEFAULT_TTL.apply_value_map["default"] is None

    def test_congestion_provider_is_written_through_the_supplemental_template(self) -> None:
        """Set-NetTCPSetting cannot write CongestionProvider on a client, and has no CUBIC."""
        assert "Set-NetTCPSetting" not in CONGESTION_PROVIDER.apply_command
        assert CONGESTION_PROVIDER.apply_command == (
            "interface tcp set supplemental template=internet congestionprovider=%value%"
        )
        assert CONGESTION_PROVIDER.apply_value_map["CUBIC"] == "cubic"
        for raw in ("CUBIC", "Default"):
            assert CONGESTION_PROVIDER.value_map[raw] == "CUBIC"

    @pytest.mark.parametrize(
        "retired",
        [
            "network:scaling_heuristics",
            "network:qos_nla",
            "network:tcp_timed_wait_delay",
        ],
    )
    def test_placebos_are_gone(self, retired: str) -> None:
        assert retired not in {s.id for s in NETWORK_SETTINGS}
        assert not hasattr(network_module, "create_packet_coalescing_setting")


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

    def test_create_rss_base_processor_valid(self) -> None:
        """Factory should create valid RSS base processor setting."""
        setting = create_rss_base_processor_setting(11, "Ethernet", 2)
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
            # target_core is derived by the caller; 2 stands in as a fixture
            lambda idx, name: create_rss_base_processor_setting(idx, name, 2),
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
    """A guard: fpstune never switches the Wi-Fi adapter off.

    It used to, whenever a cable was connected, and a machine whose cable was
    later unplugged was left with no network and no visible reason. The device
    must always keep a way to reach the internet, so the setting now only ever
    enables the radio (consequence 6).
    """

    @staticmethod
    def _setting():
        from fpstune.settings.registry import SettingsRegistry

        setting = SettingsRegistry(discover_dynamic=False).get("network:wifi_radio_when_wired")
        assert setting is not None
        return setting

    def test_recommends_the_radio_on(self) -> None:
        setting = self._setting()
        assert setting.recommended_value == setting.default_value == "radio_on"

    def test_no_command_can_disable_an_adapter(self) -> None:
        setting = self._setting()
        for command in (setting.detect_command, setting.apply_command):
            assert "Disable-NetAdapter" not in command

    def test_asking_for_radio_off_is_refused(self) -> None:
        """A manual pick could still ask for it; the command says no."""
        command = self._setting().apply_command
        refusal = command.index("does not switch the Wi-Fi adapter off")
        assert refusal < command.index("Enable-NetAdapter")

    def test_it_is_not_a_risk_the_user_must_confirm(self) -> None:
        setting = self._setting()
        assert setting.risk_level != "advanced"
        assert setting.risk_warning is None

    def test_failures_are_reported_not_swallowed(self) -> None:
        command = self._setting().apply_command
        assert "-EA Stop" in command
        assert "'error: '" in command


def test_dscp_policy_flag_is_written_as_the_string_windows_reads() -> None:
    """``Do not use NLA`` is REG_SZ "1" in Microsoft's own instructions.

    The action wrote a DWORD, which the QoS service does not honour, so the DSCP
    policies it created stayed inert on every machine outside a domain.
    """
    from fpstune.settings.executors.powershell_actions import ACTION_COMMANDS

    script = ACTION_COMMANDS["dscp_qos_toggle"]
    assert "-Name 'Do not use NLA' -Value '1' -Type String" in script
    assert "-Type DWord" not in script.split("Do not use NLA", 1)[1].split("\n", 1)[0]


@pytest.mark.parametrize(
    ("factory", "keyword"),
    [
        (create_interrupt_moderation_setting, "InterruptModeration"),
        (create_flow_control_setting, "FlowControl"),
        (create_roaming_aggressiveness_setting, "RoamAggressiveness"),
        (network_module.create_advanced_eee_setting, "AdvancedEEE"),
    ],
)
def test_detect_reads_every_spelling_apply_writes(factory: object, keyword: str) -> None:
    """Apply writes whichever of '*Keyword' and the bare vendor 'Keyword' the
    driver publishes; detect only asked for '*Keyword', so on a driver with the
    bare spelling a write that worked was read back as not supported."""
    setting = factory(5, "Ethernet")  # type: ignore[operator]
    assert setting.detect_args["batch_adapter_keyword"] == [f"*{keyword}", keyword]
    assert f"'*{keyword}','{keyword}'" in setting.detect_command
    assert f"'*{keyword}','{keyword}'" in setting.apply_command.replace("@(", "").replace(")", "")


def test_msi_default_is_the_drivers_inf_value_not_a_recorded_one() -> None:
    """Many NIC INFs set MSISupported=1 themselves. Reset used to delete the value,
    which switched message-signalled interrupts *off* on that hardware; then it restored
    a stashed original. It now writes what the adapter's own INF installs."""
    setting = create_msi_mode_setting(5, "Ethernet")
    assert setting.apply_command == "msi_mode_write"
    assert "Original" not in setting.apply_command + setting.detect_command


def test_msi_finds_its_device_by_interface_index_not_display_name() -> None:
    """Two identical NICs share a FriendlyName; the first match was the wrong one."""
    setting = create_msi_mode_setting(5, "Ethernet")
    for args in (setting.detect_args, setting.apply_args):
        assert args == {"device": "nic", "ifindex": 5}
    assert "Ethernet" not in repr(setting.apply_args)


class TestIpv6ResolversFollowTheChoice:
    """A dual-stack line asks its IPv6 resolver first. Setting only the IPv4 pair
    left the router's IPv6 resolver answering, so the filtering and encryption
    the user chose applied to whichever lookups happened to go over IPv4."""

    @pytest.mark.parametrize("choice", sorted(network_module.RESOLVER_IPV6))
    def test_apply_writes_the_ipv6_pair_and_detect_requires_it(self, choice: str) -> None:
        pair = network_module.RESOLVER_IPV6[choice]
        quoted = ",".join(f"'{address}'" for address in pair)
        assert f"$v6 = @({quoted})" in DNS_SECURITY.apply_command
        assert f"{choice} = '{','.join(sorted(pair))}'" in DNS_SECURITY.detect_command
        assert "-AddressFamily IPv6" in DNS_SECURITY.detect_command

    def test_ipv6_is_only_written_where_it_is_bound(self) -> None:
        assert "Get-NetIPInterface -InterfaceIndex $adapter.ifIndex" in DNS_SECURITY.apply_command

    def test_every_ipv6_resolver_has_a_doh_template(self) -> None:
        for pair in network_module.RESOLVER_IPV6.values():
            for address in pair:
                assert address in network_module._DOH_TEMPLATES, address

    def test_doh_flags_go_under_doh6_for_an_ipv6_server(self) -> None:
        key = network_module._DOH_INTERFACE_KEY_PS
        assert "'Doh6'" in key and "'Doh'" in key
        # Both families are read, not just IPv4.
        assert "-AddressFamily IPv4" not in DNS_OVER_HTTPS.apply_command

"""Per-adapter network settings, one adapter at a time.

What each adapter gets is decided by what that adapter is: the medium gates the
medium-exclusive settings, and the driver's own published values gate RSS queue
control. There is no fallback constant anywhere in here — a queue count a driver
does not accept is not a choice to offer, and an MTU nobody measured is not a
target (C1).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor
    from fpstune.settings.discovery import Registrar
    from fpstune.settings.discovery.probes import HardwareProbes, NetworkAdapter

logger = logging.getLogger(__name__)


def with_driver_default(setting: SettingExecutor, defaults: Mapping[str, str]) -> SettingExecutor:
    """``setting`` whose ``default_value`` is this driver's own default.

    The hardcoded default was one vendor's: reset wrote it to every driver, so a
    NIC that ships flow control on Rx only was "reset" to Rx & Tx. The driver
    publishes its default with the property; where that maps to one of the
    setting's choices it is the stock value. Anything it does not map to — no
    keyword, an unpublished default, a raw value outside the table — leaves the
    declared default in place.
    """
    from fpstune.settings.applicability import values_equal
    from fpstune.settings.base import UNMAPPED
    from fpstune.settings.executors import map_raw_to_display

    keywords = setting.detect_args.get("batch_adapter_keyword")
    # A catch-all row ("changed") is a reading, never a stock value.
    if not keywords or not defaults or UNMAPPED in setting.value_map:
        return setting
    for keyword in [keywords] if isinstance(keywords, str) else list(keywords):
        raw = defaults.get(str(keyword).lower())
        if raw is None:
            continue
        display = map_raw_to_display(setting.value_map, raw) if setting.value_map else None
        if display in setting.choices and not values_equal(display, setting.default_value):
            return replace(setting, default_value=display)
        return setting
    return setting


def filter_valid_adapters(adapters: list[NetworkAdapter]) -> list[NetworkAdapter]:
    """Drop adapters Windows named nothing at all; keep every other name intact.

    A name is never spelled into a command — ``utils/powershell.py`` rewrites an
    ``-InterfaceIndex`` command into a ``-Name $var`` lookup PowerShell performs
    for itself, so the name crosses no string boundary and needs no character
    allowlist. An allowlist here would only be able to *lose* adapters: a vendor
    name carries parentheses and dots, and a non-English Windows names its
    adapters in the system language, so any ASCII pattern narrow enough to look
    like a guard silently drops real hardware.

    An empty name is different — it is the identifier the UI labels the card
    with, and there is nothing to show. So is an empty PnP device id: it is
    what names the adapter's settings (C5), and without it they could not be
    told apart from another adapter's next session.
    """
    valid = []
    for adapter in adapters:
        if not adapter.name or not adapter.instance_id:
            logger.debug("Skipping adapter %d with no name or device id", adapter.interface_index)
            continue
        valid.append(adapter)
    return valid


def register_adapter_settings(
    registry: Registrar,
    interface_index: int,
    display_name: str,
    media_type: str = "",
    rss_queue_options: tuple[tuple[str, ...], str] | None = None,
    *,
    instance_id: str,
    property_defaults: Mapping[str, str] | None = None,
) -> int:
    """Register per-adapter network settings, gated by adapter medium.

    BEST PRACTICE: Use InterfaceIndex (numeric) for PowerShell commands.
    Display name is only used for UI labels.

    The medium (WiFi vs Ethernet) is detected once during adapter discovery and
    passed in here, so medium-exclusive settings are never registered on adapters
    that cannot use them — no per-setting hardware probe. Settings that exist on
    both media (with driver variance) stay universal and self-report not_supported.

    Args:
        registry: Where the settings land.
        interface_index: Network adapter InterfaceIndex (numeric, safe for commands).
        display_name: Human-readable adapter name (for UI display only).
        media_type: Adapter MediaType from Get-NetAdapter (e.g. "Native 802.11", "802.3").
        instance_id: The adapter's PnP device id; the settings are named by it.
        property_defaults: This adapter's ``{lowercase keyword: DefaultRegistryValue}``;
            a setting's default becomes the driver's own wherever it publishes one.
        rss_queue_options: This adapter's own ``(queue_counts, driver_default)``
            for ``*NumRssQueues``, or None when its driver does not expose the
            keyword. There is no fallback: a queue count this driver does not
            accept is not a choice to offer, and the setting is simply not
            registered — the same outcome as the ``not_supported`` its detect
            command would have reported.

    Returns:
        Number of settings registered for this adapter.
    """
    from fpstune.settings.definitions.network import (
        create_advanced_eee_setting,
        create_checksum_offload_setting,
        create_eee_setting,
        create_flow_control_setting,
        create_gigalite_setting,
        create_green_ethernet_setting,
        create_interrupt_moderation_setting,
        create_link_capability_setting,
        create_lso_setting,
        create_msi_mode_setting,
        create_nic_power_saving_setting,
        create_power_management_setting,
        create_receive_buffers_setting,
        create_roaming_aggressiveness_setting,
        create_rss_base_processor_setting,
        create_rss_queues_setting,
        create_speed_duplex_setting,
        create_throughput_booster_setting,
        create_transmit_buffers_setting,
        create_uapsd_setting,
        create_wake_on_lan_setting,
    )

    is_wifi = "802.11" in media_type
    is_ethernet = "802.3" in media_type

    # Settings present on both media (driver variance handled via not_supported)
    settings_to_register = [
        create_interrupt_moderation_setting(interface_index, display_name),
        create_flow_control_setting(interface_index, display_name),
        create_eee_setting(interface_index, display_name),
        create_advanced_eee_setting(interface_index, display_name),
        create_power_management_setting(interface_index, display_name),
        create_lso_setting(interface_index, display_name),
        create_checksum_offload_setting(interface_index, display_name),
        create_wake_on_lan_setting(interface_index, display_name),
        create_receive_buffers_setting(interface_index, display_name),
        create_transmit_buffers_setting(interface_index, display_name),
        create_msi_mode_setting(interface_index, display_name),
        # Vendor power savers. Absent on non-Realtek adapters, where the
        # keyword lookup answers not_supported and the setting drops out.
        create_green_ethernet_setting(interface_index, display_name),
        create_gigalite_setting(interface_index, display_name),
        create_nic_power_saving_setting(interface_index, display_name),
    ]

    # RSS base processor, only where a safe core exists: an unknown topology
    # or too few P-cores means no placement — moving NIC receive DPCs onto an
    # E-core is a regression, not a tweak (B2).
    from fpstune.settings.definitions.network import rss_target_core
    from fpstune.utils.detect import get_cpu_detailed_info

    rss_target = rss_target_core(get_cpu_detailed_info())
    if rss_target is not None:
        settings_to_register.append(
            create_rss_base_processor_setting(interface_index, display_name, rss_target)
        )
    else:
        logger.info(
            "RSS base processor not offered on %s: no safe core placement "
            "(topology unknown or too few performance cores)",
            display_name,
        )

    # RSS queue control, only where this driver publishes the values it takes.
    if rss_queue_options is not None:
        queue_counts, driver_default = rss_queue_options
        settings_to_register.append(
            create_rss_queues_setting(interface_index, display_name, queue_counts, driver_default)
        )

    # WiFi-exclusive settings: only meaningful on 802.11 adapters
    if is_wifi or not media_type:
        settings_to_register.extend(
            [
                create_roaming_aggressiveness_setting(interface_index, display_name),
                create_uapsd_setting(interface_index, display_name),
                create_throughput_booster_setting(interface_index, display_name),
            ]
        )

    # Ethernet-exclusive settings: WiFi has no fixed speed/duplex link mode, and
    # its rate is renegotiated continuously, so "below capability" would fire on
    # a healthy radio that simply moved further from the access point.
    if is_ethernet or not media_type:
        settings_to_register.append(create_speed_duplex_setting(interface_index, display_name))
        settings_to_register.append(create_link_capability_setting(interface_index, display_name))

    from fpstune.settings.definitions.network import adapter_key, keyed_to_adapter

    key = adapter_key(instance_id)
    for setting in settings_to_register:
        setting = with_driver_default(setting, property_defaults or {})
        registry.register(keyed_to_adapter(setting, interface_index, key, display_name))

    return len(settings_to_register)


def register_path_mtu_setting(
    registry: Registrar,
    probes: HardwareProbes,
    adapters: list[NetworkAdapter],
) -> int:
    """Register the MTU setting on the adapter the path MTU was measured through.

    Two reasons this is not registered on every adapter. The probe travels the
    default route, so its answer describes that path and nothing else — offering
    the same number for a second adapter would claim a measurement that was never
    taken. And a measurement that did not conclude registers nothing at all: an
    MTU target has to be the line's real ceiling, and 1492 is as wrong on a plain
    Ethernet line as 1500 is on PPPoE.

    Returns:
        1 if the setting was registered, 0 otherwise.
    """
    from fpstune.settings.definitions.network import (
        adapter_key,
        create_mtu_setting,
        keyed_to_adapter,
    )
    from fpstune.utils.path_mtu import probe_path_mtu

    if not adapters:
        return 0

    interface_index = probes.default_route_interface_index()
    if interface_index is None:
        logger.debug("No default IPv4 route; MTU setting not registered")
        return 0

    adapter = next((a for a in adapters if a.interface_index == interface_index), None)
    if adapter is None:
        # The default route points at something outside the physical adapter
        # list — a VPN or a virtual switch. Its MTU is that software's business.
        logger.debug(
            "Default route is on interface %d, which is not a physical adapter",
            interface_index,
        )
        return 0

    path_mtu = probe_path_mtu()
    if path_mtu is None:
        logger.debug("Path MTU unmeasurable; MTU setting not registered")
        return 0

    setting = create_mtu_setting(interface_index, adapter.name, path_mtu)
    registry.register(
        keyed_to_adapter(setting, interface_index, adapter_key(adapter.instance_id), adapter.name)
    )
    return 1


def discover_network_adapter_settings(registry: Registrar, probes: HardwareProbes) -> int:
    """Discover active network adapters and create per-adapter settings.

    BEST PRACTICE: Uses InterfaceIndex (numeric) for commands, display_name for UI.

    Returns:
        Count of discovered adapters (not settings).
    """
    # Step 1: Get adapters via PowerShell (returns (index, name, media_type) tuples)
    adapters = probes.active_adapters()

    # Step 2: Filter (InterfaceIndex is always valid, just sanity check)
    valid_adapters = filter_valid_adapters(adapters)

    # Step 3: read what each driver says about itself, once for the machine.
    rss_queue_options = probes.rss_queue_options()
    property_defaults = probes.adapter_property_defaults()

    # Step 4: Register settings for each adapter using InterfaceIndex.
    # media_type gates medium-exclusive settings (single detection, no per-tweak probe).
    for adapter in valid_adapters:
        register_adapter_settings(
            registry,
            adapter.interface_index,
            adapter.name,
            adapter.media_type,
            rss_queue_options.get(adapter.interface_index),
            instance_id=adapter.instance_id,
            property_defaults=property_defaults.get(adapter.interface_index),
        )

    # Step 5: the MTU setting, on the one adapter the measurement applies to.
    register_path_mtu_setting(registry, probes, valid_adapters)

    logger.debug("Discovered %d network adapter(s)", len(valid_adapters))
    return len(valid_adapters)


def discover_wifi_advisories(registry: Registrar, probes: HardwareProbes) -> int:
    """Register the Wi-Fi link-quality and security advisories on every Wi-Fi adapter.

    Runs after the per-adapter settings so it reads the same memoised adapter
    list. An adapter whose GUID the probe could not pair is skipped rather than
    registered blind: without the GUID the detector has nothing to ask the WLAN
    API for.

    Returns:
        Number of advisories registered.
    """
    from fpstune.settings.definitions.network import (
        adapter_key,
        create_wifi_link_quality_setting,
        create_wifi_security_setting,
        keyed_to_adapter,
    )

    adapters = filter_valid_adapters(probes.active_adapters())
    wifi = [a for a in adapters if "802.11" in (a.media_type or "")]
    if not wifi:
        return 0

    guids = probes.adapter_guids()
    count = 0
    for adapter in wifi:
        index, name = adapter.interface_index, adapter.name
        guid = guids.get(index)
        if not guid:
            logger.debug(
                "No InterfaceGuid for Wi-Fi adapter %d; link-quality advisory skipped", index
            )
            continue
        key = adapter_key(adapter.instance_id)
        for setting in (
            create_wifi_link_quality_setting(index, guid, name),
            create_wifi_security_setting(index, guid, name),
        ):
            registry.register(keyed_to_adapter(setting, index, key, name))
        count += 2
    return count

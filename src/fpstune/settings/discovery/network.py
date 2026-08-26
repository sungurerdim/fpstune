"""Per-adapter network settings, one adapter at a time.

What each adapter gets is decided by what that adapter is: the medium gates the
medium-exclusive settings, and the driver's own published values gate RSS queue
control. There is no fallback constant anywhere in here — a queue count a driver
does not accept is not a choice to offer, and an MTU nobody measured is not a
target (C1).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fpstune.settings.discovery import Registrar
    from fpstune.settings.discovery.probes import HardwareProbes

logger = logging.getLogger(__name__)


def filter_valid_adapters(adapters: list[tuple[int, str, str]]) -> list[tuple[int, str, str]]:
    """Drop adapters Windows named nothing at all; keep every other name intact.

    A name is never spelled into a command — ``utils/powershell.py`` rewrites an
    ``-InterfaceIndex`` command into a ``-Name $var`` lookup PowerShell performs
    for itself, so the name crosses no string boundary and needs no character
    allowlist. An allowlist here would only be able to *lose* adapters: a vendor
    name carries parentheses and dots, and a non-English Windows names its
    adapters in the system language, so any ASCII pattern narrow enough to look
    like a guard silently drops real hardware.

    An empty name is different — it is the identifier the UI labels the card
    with, and there is nothing to show.

    Args:
        adapters: List of (interface_index, display_name, media_type) tuples.

    Returns:
        The same tuples, minus any whose display name is empty.
    """
    valid = []
    for idx, name, media_type in adapters:
        if not name:
            logger.debug("Skipping adapter %d with empty name", idx)
            continue
        valid.append((idx, name, media_type))
    return valid


def register_adapter_settings(
    registry: Registrar,
    interface_index: int,
    display_name: str,
    media_type: str = "",
    rss_queue_options: tuple[tuple[str, ...], str] | None = None,
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
        create_packet_coalescing_setting,
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
        create_packet_coalescing_setting(interface_index, display_name),
        create_rss_base_processor_setting(interface_index, display_name),
        create_msi_mode_setting(interface_index, display_name),
        # Vendor power savers. Absent on non-Realtek adapters, where the
        # keyword lookup answers not_supported and the setting drops out.
        create_green_ethernet_setting(interface_index, display_name),
        create_gigalite_setting(interface_index, display_name),
        create_nic_power_saving_setting(interface_index, display_name),
    ]

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

    for setting in settings_to_register:
        registry.register(setting)

    return len(settings_to_register)


def register_path_mtu_setting(
    registry: Registrar,
    probes: HardwareProbes,
    adapters: list[tuple[int, str, str]],
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
    from fpstune.settings.definitions.network import create_mtu_setting
    from fpstune.utils.path_mtu import probe_path_mtu

    if not adapters:
        return 0

    interface_index = probes.default_route_interface_index()
    if interface_index is None:
        logger.debug("No default IPv4 route; MTU setting not registered")
        return 0

    display_name = next((name for idx, name, _ in adapters if idx == interface_index), None)
    if display_name is None:
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

    registry.register(create_mtu_setting(interface_index, display_name, path_mtu))
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

    # Step 4: Register settings for each adapter using InterfaceIndex.
    # media_type gates medium-exclusive settings (single detection, no per-tweak probe).
    for interface_index, display_name, media_type in valid_adapters:
        register_adapter_settings(
            registry,
            interface_index,
            display_name,
            media_type,
            rss_queue_options.get(interface_index),
        )

    # Step 5: the MTU setting, on the one adapter the measurement applies to.
    register_path_mtu_setting(registry, probes, valid_adapters)

    logger.debug("Discovered %d network adapter(s)", len(valid_adapters))
    return len(valid_adapters)

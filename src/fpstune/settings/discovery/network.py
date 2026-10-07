"""Per-adapter network settings, one adapter at a time.

What each adapter gets is decided by what that adapter is: the medium gates the
medium-exclusive settings, and the driver's own published values gate RSS queue
control. There is no fallback constant anywhere in here — a queue count a driver
does not accept is not a choice to offer, and an MTU nobody measured is not a
target (C1).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from fpstune.settings.discovery import keyword_resolver

if TYPE_CHECKING:
    from fpstune.settings.base import SettingExecutor
    from fpstune.settings.discovery import Registrar
    from fpstune.settings.discovery.keyword_resolver import AdapterProperty
    from fpstune.settings.discovery.probes import HardwareProbes, NetworkAdapter

logger = logging.getLogger(__name__)


def with_driver_default(
    setting: SettingExecutor,
    defaults: Mapping[str, str],
) -> SettingExecutor:
    """``setting`` whose ``default_value`` is this driver's own default.

    The hardcoded default was one vendor's: reset wrote it to every driver, so a
    NIC that ships flow control on Rx only was "reset" to Rx & Tx. The driver
    publishes its default with the property; where that maps to one of the
    setting's choices it is the stock value. Anything it does not map to — no
    keyword, an unpublished default, a raw value outside the table — leaves the
    declared default in place.

    A property is found by its ``RegistryKeyword`` alone, never by the label the
    control panel shows: that label is translated, so a lookup through it works on
    one Windows language and silently reads nothing on another.
    """
    from fpstune.settings.applicability import values_equal
    from fpstune.settings.base import UNMAPPED
    from fpstune.settings.executors import map_raw_to_display

    match = setting.detect_args.get("driver_default_match")
    if match:
        pattern = re.compile(str(match), re.IGNORECASE)
        return _with_switch_default(
            setting, defaults, lambda keyword: pattern.search(keyword) is not None
        )

    keywords = setting.detect_args.get("batch_adapter_keyword")
    if not keywords:
        concept_name = setting.detect_args.get("keyword_concept")
        if concept_name:
            return _with_switch_default(
                setting, defaults, keyword_resolver.concept(str(concept_name)).matches
            )
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


def _with_switch_default(
    setting: SettingExecutor,
    defaults: Mapping[str, str],
    is_ours: Callable[[str], bool],
) -> SettingExecutor:
    """An Enabled/Disabled ``setting`` whose stock value is read from the driver.

    These settings find their property through a cmdlet or a keyword search, so
    ``is_ours`` says which of the property table's keywords the detect command
    reads: a pattern named by ``detect_args["driver_default_match"]``, or a keyword
    concept named by ``detect_args["keyword_concept"]`` (the keyword resolver, the
    same table the detect command is generated from). The state is read the way
    detection reads it:
    Disabled only when every matching keyword is 0. So the stock value is Disabled
    only when the driver publishes at least one matching default and every one of
    them is 0; any other answer — nothing published, a default that is not a
    number, one keyword still on — leaves the declared ``Enabled`` in place.

    A setting that spans several keywords and declares ``keyword_defaults`` in its
    ``apply_args`` also learns each keyword's own default when the driver ships them
    in different states, so writing the stock value restores each one rather than
    one raw value in all of them.
    """
    if setting.choices != ("Enabled", "Disabled") or not defaults:
        return setting
    matched = {keyword: raw for keyword, raw in defaults.items() if is_ours(keyword)}
    if not matched:
        return setting
    try:
        values = {keyword: int(raw.strip()) for keyword, raw in matched.items()}
    except ValueError:
        return setting
    stock = "Disabled" if all(value == 0 for value in values.values()) else setting.default_value
    adopted = replace(setting, default_value=stock)
    if "keyword_defaults" in setting.apply_args and len(set(values.values())) > 1:
        pairs = ",".join(f"{keyword}={value}" for keyword, value in sorted(values.items()))
        adopted = replace(
            adopted,
            apply_args={**setting.apply_args, "keyword_defaults": pairs, "stock_state": stock},
        )
    return adopted


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


def offer_accepted_choices(
    setting: SettingExecutor,
    properties: Mapping[str, AdapterProperty],
    adapter_name: str = "",
) -> SettingExecutor | None:
    """``setting`` narrowed to the values this adapter's driver itself accepts.

    A setting that declares a ``keyword_concept`` is resolved against the driver's
    own published list or range (``keyword_resolver``): a choice whose written
    number the driver refuses is not offered, because writing it either fails or is
    misread by the hardware (C1, C10). When that removes the recommended or the
    default choice there is nothing left to tune or to reset to, so the setting is
    not offered at all (``None``).

    A driver that does not publish the concept, or an adapter whose table could not
    be read, leaves the setting untouched: absence is still answered at detect time
    with the ``not_supported`` sentinel, and an unread table is not a refusal.
    """
    concept_name = setting.detect_args.get("keyword_concept")
    if not concept_name or not properties:
        return setting

    written = {
        choice: number
        for choice, number in setting.apply_value_map.items()
        if isinstance(number, int) and not isinstance(number, bool)
    }
    resolution = keyword_resolver.resolve(
        keyword_resolver.concept(str(concept_name)), properties, written.values()
    )
    if not resolution.refused:
        return setting

    refused_choices = {choice for choice, number in written.items() if number in resolution.refused}
    kept = tuple(choice for choice in setting.choices if choice not in refused_choices)
    if setting.recommended_value not in kept or setting.default_value not in kept:
        logger.info(
            "%s not offered on %s: the driver refuses %s",
            setting.id,
            adapter_name or "adapter",
            ", ".join(sorted(refused_choices)),
        )
        return None
    return replace(setting, choices=kept)


def register_adapter_settings(
    registry: Registrar,
    interface_index: int,
    display_name: str,
    media_type: str = "",
    rss_queue_options: tuple[tuple[str, ...], str] | None = None,
    *,
    instance_id: str,
    property_defaults: Mapping[str, str] | None = None,
    properties: Mapping[str, AdapterProperty] | None = None,
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
        properties: This adapter's ``{lowercase keyword: AdapterProperty}``, the
            driver's own accepted values; a setting is offered only with choices the
            driver itself accepts, and not at all when the driver refuses its
            recommended or its default value.
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

    return _register_derived(
        registry,
        settings_to_register,
        (interface_index, instance_id, display_name),
        property_defaults or {},
        properties or {},
    )


def _register_derived(
    registry: Registrar,
    settings: list[SettingExecutor],
    adapter: tuple[int, str, str],
    property_defaults: Mapping[str, str],
    properties: Mapping[str, AdapterProperty],
) -> int:
    """Register ``settings`` for one adapter, each valued from its own driver.

    The default is the driver's own and the choices are the ones its driver
    accepts; a setting the driver leaves nothing to tune on is not registered.
    Returns how many were.
    """
    from fpstune.settings.definitions.network import adapter_key, keyed_to_adapter

    interface_index, instance_id, display_name = adapter
    key = adapter_key(instance_id)
    registered = 0
    for setting in settings:
        setting = with_driver_default(setting, property_defaults)
        offered = offer_accepted_choices(setting, properties, display_name)
        if offered is None:
            continue
        registry.register(keyed_to_adapter(offered, interface_index, key, display_name))
        registered += 1
    return registered


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
    properties = probes.adapter_properties()

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
            properties=properties.get(adapter.interface_index),
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

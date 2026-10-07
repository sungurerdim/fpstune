"""The adapter inventory names no adapter by its words: identity is the PnP device id.

The inventory script used to find an adapter's PnP ``InstanceId`` by matching text:
the WMI ``Description``, the connection name, the PnP ``FriendlyName`` (exact, then
partial, then by vendor brand), and it told Wi-Fi from Ethernet by looking for the
words "Wi-Fi" or "Wireless" in a ``FriendlyName``. Every one of those strings is the
driver's own and is translated on a non-English Windows; two identical NICs share
them outright. The script now takes the id ``Get-NetAdapter`` already carries,
joins WMI and PnP on it, and reads the medium from the numbers the driver INF
declares (``*PhysicalMediaType``, ``*IfType``).

As everywhere in this directory the shipped script runs verbatim; only the cmdlets it
calls are shadowed by functions answering from the fake host's JSON.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import pytest
from tests.test_windows_contract.conftest import run_shipped_script

from fpstune.api.hardware.network_adapters import _ADAPTER_INVENTORY_SCRIPT

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_PRELUDE = r"""
$ErrorActionPreference = 'Stop'
$FpsFake = Get-Content $env:FPSTUNE_FAKE_HOST -Raw -Encoding UTF8 | ConvertFrom-Json

function Get-NetAdapter {
    [CmdletBinding()] param([switch]$IncludeHidden)
    foreach ($a in $FpsFake.netAdapters) {
        [pscustomobject]@{
            Name = $a.name; InterfaceDescription = $a.description; InterfaceIndex = $a.ifIndex
            PnPDeviceID = $a.pnpId; Virtual = $a.virtual; AdminStatus = 1; Status = 'Up'
            HardwareInterface = $a.hardware; NdisPhysicalMedium = $a.medium
            InterfaceGuid = $a.guid; MediaType = $a.mediaType; MacAddress = $a.mac; LinkSpeed = '1 Gbps'
        }
    }
}

function Get-PnpDevice {
    [CmdletBinding()] param([string]$Class)
    foreach ($d in $FpsFake.pnp) {
        [pscustomobject]@{
            FriendlyName = $d.friendlyName; InstanceId = $d.id
            Status = $d.status; ConfigManagerErrorCode = $d.problem
        }
    }
}

function Get-PnpDeviceProperty {
    [CmdletBinding()] param([string]$InstanceId, [string]$KeyName)
    $d = $FpsFake.pnp | Where-Object { $_.id -eq $InstanceId } | Select-Object -First 1
    if ($d -and $d.driverKey) { [pscustomobject]@{ Data = $d.driverKey } }
}

function Get-ItemProperty {
    [CmdletBinding()] param([string]$LiteralPath)
    $d = $FpsFake.pnp | Where-Object { $_.driverKey -and $LiteralPath.EndsWith($_.driverKey) } | Select-Object -First 1
    if ($d) { [pscustomobject]@{ '*PhysicalMediaType' = $d.physicalMedium; '*IfType' = $d.ifType } }
}

function Get-CimInstance {
    [CmdletBinding()] param([string]$ClassName, [string]$Filter)
    foreach ($w in $FpsFake.wmi) {
        [pscustomobject]@{
            PNPDeviceID = $w.id; NetEnabled = $w.netEnabled
            Description = $w.description; NetConnectionID = $w.connectionName
        }
    }
}

function Get-NetIPAddress { [CmdletBinding()] param([int]$InterfaceIndex, [string]$AddressFamily) }
function Get-NetRoute { [CmdletBinding()] param([int]$InterfaceIndex, [string]$DestinationPrefix) }
function Get-DnsClientServerAddress { [CmdletBinding()] param([int]$InterfaceIndex, [string]$AddressFamily) }
"""

# Adapter ids as Windows prints them: a bus prefix, vendor/device numbers, an instance.
REALTEK_PCI = "PCI\\VEN_10EC&DEV_8125&SUBSYS_11471D05&REV_05\\01000000684CE00000"
INTEL_WIFI_PCI = "PCI\\VEN_8086&DEV_43F0&SUBSYS_00748086&REV_11\\3&11583659&0&A3"
DOCK_USB_1 = "USB\\VID_0BDA&PID_8153\\000001"
DOCK_USB_2 = "USB\\VID_0BDA&PID_8153\\000002"
SOFTWARE_BRIDGE = "SWD\\MSRRAS\\MS_NDISWANBH"
OLD_INTEL_WIFI_PCI = "PCI\\VEN_8086&DEV_24FD&SUBSYS_90108086&REV_78\\4&2B0C1E0&0&00E2"
OLD_REALTEK_PCI = "PCI\\VEN_10EC&DEV_8168&SUBSYS_816810EC&REV_15\\4&1C2A5D1&0&00F0"


def net(
    name: str,
    description: str,
    index: int,
    pnp_id: str,
    media: str = "802.3",
    *,
    virtual: bool = False,
    hardware: bool | None = None,
    medium: int | None = None,
) -> dict:
    """A Get-NetAdapter row: the driver's flags and NDIS medium, not its words.

    Defaults describe real hardware (`HardwareInterface` true unless virtual; medium
    14 = 802.3, 9 = native 802.11).
    """
    return {
        "name": name,
        "description": description,
        "ifIndex": index,
        "pnpId": pnp_id,
        "virtual": virtual,
        "hardware": (not virtual) if hardware is None else hardware,
        "medium": (9 if media == "Native 802.11" else 14) if medium is None else medium,
        "guid": f"{{guid-{index}}}",
        "mediaType": media,
        "mac": f"00-11-22-33-44-{index:02d}",
    }


def inventory(host: dict[str, Any]) -> list[dict[str, Any]]:
    host = {"netAdapters": [], "pnp": [], "wmi": [], **host}
    output = run_shipped_script(_PRELUDE + _ADAPTER_INVENTORY_SCRIPT, host)
    data = json.loads(output)
    return data if isinstance(data, list) else [data]


def by_name(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {record["Name"]: record for record in records}


# What each API prints for the same device on a German Windows: the connection name,
# the NetAdapter description, the PnP FriendlyName and the WMI description all differ.
TRANSLATED_HOST = {
    "netAdapters": [
        net("Ethernet", "Realtek PCIe-GbE-Familiencontroller", 19, REALTEK_PCI),
        net("WLAN", "Intel(R) Wi-Fi 6 AX200 160MHz", 4, INTEL_WIFI_PCI, "Native 802.11"),
    ],
    "pnp": [
        {"friendlyName": "Realtek PCIe GbE Familien-Controller", "id": REALTEK_PCI, "status": "OK"},
        {"friendlyName": "Intel(R) Wi-Fi 6 AX200 160 MHz", "id": INTEL_WIFI_PCI, "status": "OK"},
    ],
    "wmi": [
        {
            "id": REALTEK_PCI,
            "netEnabled": True,
            "description": "Realtek PCIe GbE-Familiencontroller",
            "connectionName": "LAN-Verbindung",
        },
        {
            "id": INTEL_WIFI_PCI,
            "netEnabled": False,
            "description": "Intel(R) Wi-Fi 6 AX200",
            "connectionName": "WLAN-Verbindung",
        },
    ],
}


class TestIdentityIsTheDevicesOwnId:
    def test_each_adapter_gets_its_own_id_though_every_name_differs_across_apis(self) -> None:
        records = by_name(inventory(TRANSLATED_HOST))
        assert records["Ethernet"]["InstanceId"] == REALTEK_PCI
        assert records["WLAN"]["InstanceId"] == INTEL_WIFI_PCI

    def test_the_hardware_state_is_joined_on_that_id(self) -> None:
        records = by_name(inventory(TRANSLATED_HOST))
        assert records["Ethernet"]["WmiNetEnabled"] is True
        assert records["WLAN"]["WmiNetEnabled"] is False

    def test_two_identical_nics_keep_their_own_id_and_state(self) -> None:
        """Same description, same vendor: a join on text hands both the first one's."""
        description = "Realtek USB GbE Family Controller"
        host = {
            "netAdapters": [
                net("Ethernet 2", description, 21, DOCK_USB_1),
                net("Ethernet 3", f"{description} #2", 22, DOCK_USB_2),
            ],
            "pnp": [
                {"friendlyName": description, "id": DOCK_USB_1, "status": "OK"},
                {"friendlyName": description, "id": DOCK_USB_2, "status": "OK"},
            ],
            "wmi": [
                {"id": DOCK_USB_1, "netEnabled": True, "description": description},
                {"id": DOCK_USB_2, "netEnabled": False, "description": description},
            ],
        }
        records = by_name(inventory(host))
        assert records["Ethernet 2"]["InstanceId"] == DOCK_USB_1
        assert records["Ethernet 3"]["InstanceId"] == DOCK_USB_2
        assert records["Ethernet 2"]["WmiNetEnabled"] is True
        assert records["Ethernet 3"]["WmiNetEnabled"] is False

    def test_a_non_physical_adapter_borrows_no_physical_id_by_vendor_name(self) -> None:
        """A software adapter whose name contains a vendor brand is not the NIC with that brand."""
        host = {
            "netAdapters": [
                net("Ethernet", "Intel(R) Ethernet Connection I219-V", 7, REALTEK_PCI),
                net("Bridge", "Intel(R) Network Bridge Link", 9, SOFTWARE_BRIDGE),
            ],
            "pnp": [
                {
                    "friendlyName": "Intel(R) Ethernet Connection I219-V",
                    "id": REALTEK_PCI,
                    "status": "OK",
                }
            ],
        }
        records = by_name(inventory(host))
        assert records["Ethernet"]["InstanceId"] == REALTEK_PCI
        assert records["Bridge"]["InstanceId"] is None

    def test_a_listed_adapter_is_not_listed_again_from_pnp(self) -> None:
        """The PnP pass skips by id: a translated FriendlyName no longer slips past a name check."""
        records = inventory(TRANSLATED_HOST)
        ids = [record["InstanceId"] for record in records]
        assert sorted(ids) == sorted([REALTEK_PCI, INTEL_WIFI_PCI])


class TestMediumComesFromTheDriversNumbers:
    """A device Device Manager disabled is absent from Get-NetAdapter; only the PnP pass sees it."""

    @staticmethod
    def disabled(friendly_name: str, device_id: str, **driver: Any) -> dict[str, Any]:
        return {
            "friendlyName": friendly_name,
            "id": device_id,
            "status": "Error",
            "problem": 22,
            "driverKey": "{4d36e972-e325-11ce-bfc1-08002be10318}\\0007",
            **driver,
        }

    def test_a_wifi_card_with_a_turkish_name_is_still_wifi(self) -> None:
        """ "Kablosuz" is Turkish for wireless: no 'Wi-Fi' or 'Wireless' anywhere in the name."""
        card = self.disabled(
            "Intel(R) Dual Band Kablosuz-AC 8265",
            OLD_INTEL_WIFI_PCI,
            physicalMedium=9,
            ifType=71,
        )
        records = inventory({"pnp": [card]})
        assert records[0]["InstanceId"] == OLD_INTEL_WIFI_PCI
        assert records[0]["MediaType"] == "Native 802.11"

    def test_an_ethernet_card_with_a_turkish_name_is_ethernet(self) -> None:
        card = self.disabled(
            "Realtek PCIe GbE Aile Denetleyicisi", OLD_REALTEK_PCI, physicalMedium=14, ifType=6
        )
        assert inventory({"pnp": [card]})[0]["MediaType"] == "802.3"

    def test_an_english_name_does_not_make_a_card_wifi_against_its_own_numbers(self) -> None:
        """The words lie in both directions: a name that says Wi-Fi on a card that is wired."""
        card = self.disabled(
            "Wireless-ready Gigabit Ethernet Controller",
            OLD_REALTEK_PCI,
            physicalMedium=14,
            ifType=6,
        )
        assert inventory({"pnp": [card]})[0]["MediaType"] == "802.3"

    def test_the_older_wireless_lan_medium_number_counts_as_wifi(self) -> None:
        card = self.disabled("Old radio", OLD_INTEL_WIFI_PCI, physicalMedium=1)
        assert inventory({"pnp": [card]})[0]["MediaType"] == "Native 802.11"

    def test_the_ifType_alone_is_enough_when_the_medium_is_not_declared(self) -> None:
        card = self.disabled("Radio", OLD_INTEL_WIFI_PCI, ifType=71)
        assert inventory({"pnp": [card]})[0]["MediaType"] == "Native 802.11"

    def test_an_unreadable_driver_key_is_an_unknown_medium_not_ethernet(self) -> None:
        card = {
            "friendlyName": "Intel(R) Wi-Fi 6 AX200",
            "id": OLD_INTEL_WIFI_PCI,
            "status": "Error",
            "problem": 22,
        }
        assert inventory({"pnp": [card]})[0]["MediaType"] == ""


class TestHardwareIsToldFromSoftwareByTheDriversNumbers:
    """Method 1 and the PnP pass refuse software adapters without reading a word of text.

    Every description below is Turkish and none carries a word the old filters knew
    ("Virtual", "Miniport", "Hyper-V", "Bluetooth", "Wi-Fi Direct"): the flags and the
    NDIS medium are all the script has to go on.
    """

    HYPER_V = net(
        "vEthernet (Varsayılan Anahtar)",
        "Sanal Ethernet Bağdaştırıcısı",
        20,
        "ROOT\\VMS_MP\\0000",
        virtual=True,
    )
    BLUETOOTH_PAN = net(
        "Bluetooth Ağ Bağlantısı",
        "Kişisel Alan Ağı Aygıtı",
        21,
        "BTH\\MS_BTHPAN\\6&2A",
        medium=10,
    )
    SOFTWARE_BRIDGE = net("Köprü", "Ağ Köprüsü Bağdaycısı", 22, SOFTWARE_BRIDGE, hardware=False)
    PHYSICAL = net("Ethernet", "Realtek PCIe GbE Aile Denetleyicisi", 19, REALTEK_PCI)

    def test_only_the_physical_nic_is_listed(self) -> None:
        host = {
            "netAdapters": [self.HYPER_V, self.BLUETOOTH_PAN, self.SOFTWARE_BRIDGE, self.PHYSICAL],
            "pnp": [
                {"friendlyName": "Realtek PCIe GbE Aile Denetleyicisi", "id": REALTEK_PCI},
            ],
        }
        assert list(by_name(inventory(host))) == ["Ethernet"]

    def test_a_refused_adapter_is_not_listed_again_by_the_pnp_pass(self) -> None:
        """A virtual adapter on a PCI id is still not hardware, whatever its PnP name says.

        The PnP pass exists for disabled and unplugged cards that Get-NetAdapter no
        longer lists; it must not resurrect one Get-NetAdapter listed and refused.
        """
        refused = net(
            "Sanal Anahtar",
            "Sanal Anahtar Bağdaştırıcısı",
            23,
            "PCI\\VEN_15AD&DEV_07B0\\4&1A2B3C&0&00A8",
            virtual=True,
        )
        host = {
            "netAdapters": [refused, self.PHYSICAL],
            "pnp": [
                {"friendlyName": "Sanal Anahtar Bağdaştırıcısı", "id": refused["pnpId"]},
                {"friendlyName": "Realtek PCIe GbE Aile Denetleyicisi", "id": REALTEK_PCI},
            ],
        }
        assert [r["InstanceId"] for r in inventory(host)] == [REALTEK_PCI]

    def test_a_disabled_card_only_the_pnp_pass_sees_is_still_listed(self) -> None:
        """The refusal list must not swallow the very devices the PnP pass exists for."""
        host = {
            "netAdapters": [self.HYPER_V],
            "pnp": [
                {
                    "friendlyName": "Intel(R) Dual Band Kablosuz-AC 8265",
                    "id": OLD_INTEL_WIFI_PCI,
                    "status": "Error",
                    "problem": 22,
                    "driverKey": "{4d36e972-e325-11ce-bfc1-08002be10318}\0007",
                    "physicalMedium": 9,
                    "ifType": 71,
                }
            ],
        }
        assert [r["InstanceId"] for r in inventory(host)] == [OLD_INTEL_WIFI_PCI]

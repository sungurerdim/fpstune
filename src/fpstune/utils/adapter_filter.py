"""Which network adapters are real hardware, decided by numbers and booleans.

Every Windows language translates an adapter's ``InterfaceDescription`` and
``FriendlyName``, so a filter on the words "Virtual" or "Bluetooth" works on an
English Windows and quietly lets the same adapters through on any other.
The properties below are not text:

* ``HardwareInterface`` is true when the driver declares ``NCF_PHYSICAL``. On the
  development host the Hyper-V switch and its extension, the Wi-Fi Direct
  adapters, the kernel debug NIC and the Teredo, 6to4 and IP-HTTPS interfaces
  all report false, and the Ethernet and Wi-Fi cards true.
* ``Virtual`` is the NDIS virtual flag, true for that same software set.
* ``NdisPhysicalMedium`` is the NDIS medium enum; 10 is Bluetooth, whose PAN
  adapter is hardware-backed and so passes the first two but is not a NIC a
  network tweak applies to.

``-Physical`` is deliberately not used: a disabled adapter drops out of it
altogether, and a guard that cannot see a disabled radio could never turn it
back on (see ``_WIFI_ADAPTERS`` in ``settings/definitions/network.py``).
"""

from __future__ import annotations

from typing import Final

# NDIS_PHYSICAL_MEDIUM: NdisPhysicalMediumBluetooth.
NDIS_PHYSICAL_MEDIUM_BLUETOOTH: Final = 10

# A PowerShell boolean expression over `$_` as a Get-NetAdapter object.
PHYSICAL_ADAPTER: Final = (
    "$_.HardwareInterface -and -not $_.Virtual -and "
    f"$_.NdisPhysicalMedium -ne {NDIS_PHYSICAL_MEDIUM_BLUETOOTH}"
)

# The same expression, narrowed to an adapter that is up (InterfaceOperationalStatus
# 1 is the numeric "Up", which no Windows language changes).
PHYSICAL_ADAPTER_UP: Final = f"[int]$_.InterfaceOperationalStatus -eq 1 -and {PHYSICAL_ADAPTER}"

# Physical adapters that are up, waiting out an adapter restart. A NIC restart
# takes the interface down for a moment; a detector that reads at that instant
# sees zero adapters and used to answer "ISP" (dns_security) or "not_supported"
# (DoH), which is a false state, not a transient reading. The wait is bounded so
# a genuinely disconnected machine still answers: after it, `$adapters` is empty
# and the caller's own absent-state handling runs.
#
# Every adapter-backed detector that would otherwise read through a restart
# should use this instead of a bare `Get-NetAdapter | Where-Object`.
PHYSICAL_ADAPTERS_UP: Final = (
    "$deadline = (Get-Date).AddSeconds(10); "
    "do { "
    "$adapters = @(Get-NetAdapter -ErrorAction SilentlyContinue | Where-Object { "
    f"{PHYSICAL_ADAPTER_UP} "
    "}); "
    "if ($adapters.Count -gt 0) { break }; "
    "Start-Sleep -Milliseconds 500 "
    "} while ((Get-Date) -lt $deadline); "
    "$adapters"
)

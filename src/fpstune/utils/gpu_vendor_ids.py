"""GPU vendor identity from PCI vendor IDs: the one vocabulary.

Which vendor made a GPU, and which chip is integrated or discrete, are facts
about the PCI vendor ID in `Win32_VideoController.PNPDeviceID` (`PCI\\VEN_10DE&...`),
never about the marketing string in `.Name`: names are localised, renamed per
driver release and invented per board partner, and a pattern over them silently
misreads every product line it did not list (C10: capability, not model lists).
The IDs below are the PCI-SIG vendor registrations.

This module sits under `utils` so both layers read the same constants:
`utils/detect.py` (which vendor is the primary GPU) and
`settings/applicability.py` (is there a hybrid pair), plus the PowerShell probe
in `settings/definitions/gpu.py` built from them.
"""

from __future__ import annotations

import re

INTEL_VENDOR_ID = "8086"
NVIDIA_VENDOR_ID = "10DE"
AMD_VENDOR_ID = "1002"

_VENDOR_ID_RE = re.compile(r"VEN_([0-9A-F]{4})&")


def vendor_id_of(pnp_device_id: str) -> str | None:
    """Return the upper-case PCI vendor ID in a ``PNPDeviceID``, or None if it has none."""
    match = _VENDOR_ID_RE.search(pnp_device_id.upper())
    return match.group(1) if match else None


def has_vendor(pnp_device_id: str, vendor_ids: tuple[str, ...]) -> bool:
    """True when the ``PNPDeviceID`` carries one of these PCI vendor IDs."""
    return vendor_id_of(pnp_device_id) in vendor_ids

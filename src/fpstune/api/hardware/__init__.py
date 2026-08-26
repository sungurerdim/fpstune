"""Hardware detection behind the hardware panel.

Read-only PowerShell probes that enumerate network adapters, storage drives and
audio endpoints. They live under ``api`` rather than ``utils`` because they
return ``api.schemas`` objects: putting them in ``utils`` would point the lowest
layer of the codebase at the API's response models. They are not under
``api.routes`` because none of them is a route — no router, no request, nothing
HTTP-shaped.
"""

from fpstune.api.hardware.audio import get_audio_devices
from fpstune.api.hardware.network_adapters import get_detailed_network_adapters
from fpstune.api.hardware.storage import get_detailed_storage_drives

__all__ = [
    "get_audio_devices",
    "get_detailed_network_adapters",
    "get_detailed_storage_drives",
]

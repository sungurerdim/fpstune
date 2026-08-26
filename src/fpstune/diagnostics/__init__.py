"""Diagnostics that answer a symptom rather than expose a setting."""

from fpstune.diagnostics.mpo_effect import MpoObservation, read_capture, read_latest
from fpstune.diagnostics.packet_burst import (
    PacketBurstCheck,
    PacketBurstReport,
    build_report,
)

__all__ = [
    "MpoObservation",
    "PacketBurstCheck",
    "PacketBurstReport",
    "build_report",
    "read_capture",
    "read_latest",
]

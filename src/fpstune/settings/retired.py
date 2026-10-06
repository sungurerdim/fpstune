"""Every setting id fpstune shipped and later removed, and what became of it.

Product Goal consequence 6: retiring a harmful tweak means guaranteeing its
harmless value, because machines that already carry it keep carrying it. Deleting
the row hides the harm. This module is the one record that a removal was *decided*:
each retired id says which of four things happened to it.

``guard``      the id's control lives on as a row whose ``recommended_value`` is
               the harmless state (``== default_value``); ``target`` names it.
``replaced``   the same control lives on under another id (merged, renamed, split
               per endpoint); ``target`` names the surviving row.
``no_op``      limit 1 of consequence 6: no guard for a no-op. The key is ignored
               by Windows 11 or by the program, so there is no harmful state to
               restore. ``reason`` records the evidence.
``mitigation`` limit 2: the switch cost security, so it stays retired and a guard
               restoring the mitigation (``target``) covers it.

``tests/test_settings/test_retired.py`` pins the registered id set in
``registered_ids.txt``: an id that leaves the registry without an entry here fails
the test, which is the mechanical half of consequence 6.

Scope of the record: static definitions only (``get_all_static_settings``).
Per-adapter, per-endpoint and per-title rows are discovered at runtime and depend
on the machine. The history behind this list starts at the first commit that
carried the definitions; an id removed before it cannot be recovered from git.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Kind = Literal["guard", "replaced", "no_op", "mitigation"]


@dataclass(frozen=True)
class Retired:
    """What became of one removed setting id."""

    kind: Kind
    reason: str
    target: str | None = None


RETIRED: dict[str, Retired] = {
    # --- audio: the HKCU effect and exclusive-mode flags nothing reads ---------
    "audio:enhancements": Retired(
        "no_op",
        "HKCU DisableFXEffects is read by nothing in the Windows audio stack; "
        "the per-endpoint row is audio:endpoint_enhancements (fbfa7c7).",
    ),
    "audio:exclusive_mode": Retired(
        "guard",
        "HKCU DisableExclusiveMode was a placebo; the per-endpoint guard keeps "
        "exclusive access allowed (fbfa7c7).",
        "audio:endpoint_exclusive_mode",
    ),
    # --- games: lines the game ignores ----------------------------------------
    "game_config:cs2:disable_ragdolls": Retired(
        "no_op",
        "cl_disable_ragdolls is cheat-protected in CS2 (sv_cheats 1), so the "
        "autoexec line was ignored on every server a match is played on.",
    ),
    "game_config:mw3:velocity_blur": Retired(
        "no_op",
        "EnableVelocityBasedBlur stays 'true' while the in-game World Motion Blur "
        "reads off: the key is not the switch (see the note above MW3_SHADOW_QUALITY).",
    ),
    # --- NVIDIA: duplicate controls merged into one DRS key each ---------------
    "gpu-nvidia:max_prerendered": Retired(
        "replaced",
        "Same DRS key as low_latency; merged when settings moved to NVAPI (baade80).",
        "gpu-nvidia:low_latency",
    ),
    "gpu-nvidia:ogl_thread_opt": Retired(
        "replaced",
        "Same DRS key as threaded_opt; merged when settings moved to NVAPI (baade80).",
        "gpu-nvidia:threaded_opt",
    ),
    # --- Battle.net: keys no client config on record carries -------------------
    "launcher:bnet:p2p": Retired(
        "no_op",
        "Client.P2PEnabled appears in no Battle.net.config on record; Blizzard "
        "retired peer-to-peer patching.",
    ),
    "launcher:bnet:background_download": Retired(
        "no_op",
        "Client.BackgroundDownload appears in no Battle.net.config on record.",
    ),
    "launcher:bnet:background_download_limit": Retired(
        "no_op",
        "Client.BackgroundDownloadLimit appears in no Battle.net.config on record; "
        "the client's one cap is Client.Install.DownloadLimitNextPatchInBps.",
    ),
    # --- network ---------------------------------------------------------------
    "network:qos_nla": Retired(
        "replaced",
        "Wrote 'Do not use NLA' as a DWORD; Microsoft documents REG_SZ '1'. The flag "
        "is now part of the DSCP QoS named compound (C8).",
        "system:network_dscp_qos",
    ),
    "network:scaling_heuristics": Retired(
        "no_op",
        "Windows 8.1 and later ignore the key; recommended == default, so it only "
        "ever restored a state nothing reads.",
    ),
    "network:tcp_timed_wait_delay": Retired(
        "guard",
        "TcpTimedWaitDelay is honoured by Windows 11 and old fpstune wrote 30 s "
        "against the stock 120 s (key absent). Retired with the placebo sweep "
        "(b27a638); the guard row deletes the value so Windows' own wait applies "
        "(owner decision 2026-10-06, consequence 6).",
        "network:time_wait_delay",
    ),
    # --- priority: MMCSS values Microsoft documents as unused ------------------
    "priority:gpu_priority": Retired(
        "no_op",
        "MMCSS 'GPU Priority' is unused per Microsoft; the old row wrote the stock 8 (27599be).",
    ),
    "priority:sfio_priority": Retired(
        "no_op",
        "MMCSS 'SFIO Priority' is unused per Microsoft (27599be).",
    ),
    # --- privacy and visual: placebos Windows 11 ignores -----------------------
    "privacy:accepted_policy": Retired(
        "no_op",
        "A consent flag, not a collection switch; nothing changes when it is set.",
    ),
    "privacy:bing_search": Retired(
        "replaced",
        "BingSearchEnabled is ignored by Windows 11 search; the policy it honours "
        "is the web-search policy row.",
        "privacy:web_search_policy",
    ),
    "privacy:ceip": Retired(
        "no_op",
        "SQMClient has not driven anything since Windows 10.",
    ),
    "privacy:cortana": Retired(
        "no_op",
        "The Cortana app is gone from Windows 11; AllowCortana controls nothing.",
    ),
    "privacy:tile_notifications": Retired(
        "no_op",
        "Live Tiles are Windows 10 only.",
    ),
    "visual:smooth_scrolling": Retired(
        "no_op",
        "Control Panel\\Desktop SmoothScroll is not the value Windows reads.",
    ),
}

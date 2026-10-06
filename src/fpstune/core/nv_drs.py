"""Which NVIDIA driver (DRS) keys each fpstune setting reads and writes.

One table serves both directions, so a value can never be written under one
meaning and read back under another. Every ID and value is copied from NVIDIA's
own ``NvApiDriverSettings.h`` (github.com/NVIDIA/nvapi) unless its entry says
otherwise; a key NVIDIA does not publish is taken from nvidiaProfileInspector's
``CustomSettingNames.xml`` and marked ``published=False``.

Stock is never written. Choosing a setting's stock value deletes its keys from
the global profile, so the driver's own default applies on this driver version.
Reading treats an absent key as that stock value.

A key the installed driver does not define is a capability fact, not a failure
(``missing`` below, from ``nvapi.known_setting_ids``). Each key type answers
``supports(missing)`` — whether the setting means anything on this driver — and
``changes_for`` leaves a missing key out of what it writes, refusing a choice
whose meaning lived in that key.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

# NvApiDriverSettings.h setting IDs.
PREFERRED_PSTATE = 0x1057EB71
PRERENDERLIMIT = 0x007BA09E
OGL_THREAD_CONTROL = 0x20C1221E
VSYNCMODE = 0x00A879CF
PS_SHADERDISKCACHE = 0x00198FFF
QUALITY_ENHANCEMENTS = 0x00CE2691
OGL_TRIPLE_BUFFER = 0x20FDD1F9
FRL_FPS = 0x10835002
VRR_MODE = 0x1194F158
VRR_APP_OVERRIDE = 0x10A879CF
PS_TEXFILTER_ANISO_OPTS2 = 0x00E73211
PS_TEXFILTER_NO_NEG_LODBIAS = 0x0019BB68

# Not in NvApiDriverSettings.h; IDs from nvidiaProfileInspector's
# CustomSettingNames.xml ("Ultra Low Latency - Enabled", "Ultra Low Latency -
# CPL State", "Frame Rate Limiter - Background Application", "CUDA - Force P2
# State").
ULL_ENABLED = 0x10835000
ULL_CPL_STATE = 0x0005F543
FRL_BACKGROUND = 0x10835005
CUDA_FORCE_P2 = 0x50166C5E

FRL_MAX = 0x3FF  # FRL_FPS_MAX


@dataclass(frozen=True)
class EnumKey:
    """A choice setting: each display value is a set of DRS key values.

    ``write_only`` keys are written with a choice but ignored when reading: the
    Ultra Low Latency "CPL state" only tells NVIDIA Control Panel which radio
    button to show, so a profile tool that never set it must still read as the
    tier the driver actually runs.

    A tier is identified by its effect (the ids in ``values``), never by the
    word a vendor prints on it, and the vendor's words change with the driver
    generation: the same one-queued-frame tier is "On" in NVIDIA Control Panel
    next to an "Ultra" that needs ``ULL_ENABLED``, and "Ultra" in the NVIDIA App,
    whose driver has no such key. ``labels`` names each tier (as an i18n key the
    frontend translates, C4) when the driver defines every key;
    ``labels_without`` replaces those names for a key the driver lacks. Which
    names apply is read from the driver's own key table, never from a version.
    A key whose absence cannot move a tier's name says why in ``label_reason``.
    """

    key: str
    values: Mapping[str, Mapping[int, int]]
    stock: str
    published: bool = True
    write_only: frozenset[int] = field(default_factory=frozenset)
    labels: Mapping[str, str] = field(default_factory=dict)
    labels_without: Mapping[int, Mapping[str, str]] = field(default_factory=dict)
    label_reason: str = ""

    @property
    def ids(self) -> tuple[int, ...]:
        ids: dict[int, None] = {}
        for mapping in self.values.values():
            ids.update(dict.fromkeys(mapping))
        return tuple(ids)

    @property
    def read_ids(self) -> tuple[int, ...]:
        return tuple(i for i in self.ids if i not in self.write_only)

    def expressible(self, choice: str, missing: Collection[int] = ()) -> bool:
        """Whether this driver can hold ``choice`` with the keys it defines.

        A key the driver lacks reads as that key's stock value, so it costs a
        choice nothing when the choice wants exactly that value (Low Latency
        "on" wants ULL_ENABLED=0, which an absent ULL_ENABLED already is) or
        when the key is write-only, a record for NVIDIA Control Panel's radio
        button that the driver never acts on (ULL_CPL_STATE). Any other missing
        key carries the choice's meaning: "ultra" without ULL_ENABLED would run
        exactly as "on", so it is not offered.
        """
        stock = self.values[self.stock]
        target = self.values[choice]
        return all(
            i in self.write_only or target.get(i, 0) == stock.get(i, 0)
            for i in self.ids
            if i in missing
        )

    def choices(self, missing: Collection[int] = ()) -> tuple[str, ...]:
        """The choices this driver can hold, in table order."""
        return tuple(c for c in self.values if self.expressible(c, missing))

    def supports(self, missing: Collection[int] = ()) -> bool:
        """False when no choice but the stock one survives: nothing to change here."""
        return len(self.choices(missing)) > 1

    def choice_labels(self, missing: Collection[int] = ()) -> dict[str, str]:
        """The i18n label key of each choice this driver can hold, by capability.

        Empty for a key that names its tiers by their own ids.
        """
        named = dict(self.labels)
        for key_id, replacement in self.labels_without.items():
            if key_id in missing:
                named.update(replacement)
        held = self.choices(missing)
        return {choice: label for choice, label in named.items() if choice in held}

    def changes_for(self, choice: str, missing: Collection[int] = ()) -> dict[int, int | None]:
        if choice not in self.values:
            raise ValueError(f"{choice!r} is not one of {tuple(self.values)}")
        if not self.expressible(choice, missing):
            lacking = ", ".join(f"{i:#010x}" for i in self.ids if i in missing)
            raise ValueError(
                f"{choice!r} is not available on this driver: it does not have the "
                f"NVIDIA setting {lacking} that {self.key} {choice!r} needs"
            )
        live = [i for i in self.ids if i not in missing]
        if choice == self.stock:
            return dict.fromkeys(live)
        target = self.values[choice]
        return {setting_id: target.get(setting_id) for setting_id in live}

    def decode(self, raw: Mapping[int, int]) -> str | None:
        """The choice the driver is in, or None for a state no choice describes."""
        stock = self.values[self.stock]
        effective = {i: raw.get(i, stock.get(i, 0)) for i in self.read_ids}
        for choice, mapping in self.values.items():
            if all(effective[i] == mapping.get(i, 0) for i in self.read_ids):
                return choice
        return None


@dataclass(frozen=True)
class NumberKey:
    """A numeric setting stored in one DRS key; ``stock`` is the driver default."""

    key: str
    setting_id: int
    stock: int
    maximum: int
    published: bool = True

    @property
    def ids(self) -> tuple[int, ...]:
        return (self.setting_id,)

    @property
    def read_ids(self) -> tuple[int, ...]:
        return self.ids

    def supports(self, missing: Collection[int] = ()) -> bool:
        return self.setting_id not in missing

    def changes_for(self, value: int, missing: Collection[int] = ()) -> dict[int, int | None]:
        if not 0 <= value <= self.maximum:
            raise ValueError(f"{value} is outside 0-{self.maximum}")
        if self.setting_id in missing:
            raise ValueError(
                f"this driver does not have the NVIDIA setting {self.setting_id:#010x} "
                f"that {self.key} needs"
            )
        return {self.setting_id: None if value == self.stock else value}

    def decode(self, raw: Mapping[int, int]) -> int:
        return raw.get(self.setting_id, self.stock)


DrsKey = EnumKey | NumberKey

_KEYS: tuple[DrsKey, ...] = (
    EnumKey(
        "power_mode",
        {
            # PREFERRED_PSTATE_OPTIMAL_POWER / _ADAPTIVE / _PREFER_MAX.
            "optimal": {PREFERRED_PSTATE: 0x5},
            "adaptive": {PREFERRED_PSTATE: 0x0},
            "maximum": {PREFERRED_PSTATE: 0x1},
        },
        stock="optimal",
    ),
    EnumKey(
        "low_latency",
        {
            # Low Latency Mode is up to three keys: the pre-render limit, the
            # Ultra switch, and the panel's own record of which tier it shows.
            # PRERENDERLIMIT_APP_CONTROLLED is 0. The Ultra pair is not
            # published by NVIDIA; the table follows `fpstune nvidia-dump`
            # before and after each choice, measured on two driver generations:
            #   NVIDIA Control Panel, legacy driver: Off writes PRERENDERLIMIT 0,
            #     On writes PRERENDERLIMIT 1 (+ ULL_CPL_STATE 1), Ultra writes
            #     PRERENDERLIMIT 1 + ULL_ENABLED 1 (+ ULL_CPL_STATE 2).
            #   NVIDIA App, driver 617.14 (neither ULL key defined): offers only
            #     Off and Ultra; Ultra writes PRERENDERLIMIT 1 and nothing else,
            #     Off writes PRERENDERLIMIT 0. The App's "Ultra" is therefore this
            #     table's "on" tier — one queued frame — under the vendor's newer
            #     name, which is why `labels_without` renames it.
            "off": {PRERENDERLIMIT: 0, ULL_ENABLED: 0, ULL_CPL_STATE: 0},
            "on": {PRERENDERLIMIT: 1, ULL_ENABLED: 0, ULL_CPL_STATE: 1},
            "ultra": {PRERENDERLIMIT: 1, ULL_ENABLED: 1, ULL_CPL_STATE: 2},
        },
        stock="off",
        published=False,
        write_only=frozenset({ULL_CPL_STATE}),
        labels={"off": "tier.off", "on": "tier.on", "ultra": "tier.ultra"},
        labels_without={ULL_ENABLED: {"off": "tier.off", "on": "tier.ultra"}},
    ),
    EnumKey(
        # NVIDIA Control Panel's "Threaded optimization". The key is named OGL_
        # but it is the one control for every API (OGL_THREAD_CONTROL_STRING is
        # L"Threaded optimization"). 0 is the driver's own auto choice.
        "threaded_opt",
        {
            "auto": {OGL_THREAD_CONTROL: 0x0},
            "on": {OGL_THREAD_CONTROL: 0x1},
            "off": {OGL_THREAD_CONTROL: 0x2},
        },
        stock="auto",
    ),
    EnumKey(
        "vsync",
        {
            # VSYNCMODE_PASSIVE (the 3D application decides) / _FORCEOFF / _FORCEON.
            "app": {VSYNCMODE: 0x60925292},
            "off": {VSYNCMODE: 0x08416747},
            "on": {VSYNCMODE: 0x47814940},
        },
        stock="app",
    ),
    EnumKey(
        "shader_cache",
        {"on": {PS_SHADERDISKCACHE: 0x1}, "off": {PS_SHADERDISKCACHE: 0x0}},
        stock="on",
    ),
    EnumKey(
        "texture_quality",
        {
            # QUALITY_ENHANCEMENTS_HIGHQUALITY / _QUALITY / _PERFORMANCE / _HIGHPERFORMANCE.
            "high_quality": {QUALITY_ENHANCEMENTS: 0xFFFFFFF6},
            "quality": {QUALITY_ENHANCEMENTS: 0x0},
            "performance": {QUALITY_ENHANCEMENTS: 0xA},
            "high_performance": {QUALITY_ENHANCEMENTS: 0x14},
        },
        stock="quality",
    ),
    EnumKey(
        "triple_buffer",
        {"off": {OGL_TRIPLE_BUFFER: 0x0}, "on": {OGL_TRIPLE_BUFFER: 0x1}},
        stock="off",
    ),
    EnumKey(
        "vrr_mode",
        {
            # VRR_MODE_DISABLED / _FULLSCREEN_ONLY (the driver default) /
            # _FULLSCREEN_AND_WINDOWED. "on" is the last: borderless included.
            "off": {VRR_MODE: 0x0},
            "fullscreen": {VRR_MODE: 0x1},
            "on": {VRR_MODE: 0x2},
        },
        stock="fullscreen",
    ),
    EnumKey(
        "vrr_app_override",
        {
            # VRR_APP_OVERRIDE_ALLOW (default) / _DISALLOW. The enum has no
            # "force on"; FORCE_OFF is 1, which an earlier release wrote for it.
            "driver_default": {VRR_APP_OVERRIDE: 0x0},
            "off": {VRR_APP_OVERRIDE: 0x2},
        },
        stock="driver_default",
    ),
    EnumKey(
        "aniso_sample_opt",
        {"off": {PS_TEXFILTER_ANISO_OPTS2: 0x0}, "on": {PS_TEXFILTER_ANISO_OPTS2: 0x1}},
        stock="off",
    ),
    EnumKey(
        "texture_lod_bias",
        {
            # PS_TEXFILTER_NO_NEG_LODBIAS_OFF ("Allow") / _ON ("Clamp").
            "allow": {PS_TEXFILTER_NO_NEG_LODBIAS: 0x0},
            "clamp": {PS_TEXFILTER_NO_NEG_LODBIAS: 0x1},
        },
        stock="allow",
    ),
    EnumKey(
        "cuda_force_p2",
        # nvidiaProfileInspector lists the driver default as On (1).
        {"on": {CUDA_FORCE_P2: 0x1}, "off": {CUDA_FORCE_P2: 0x0}},
        stock="on",
        published=False,
        label_reason=(
            "one key and two tiers: a driver without it does not support the setting at "
            "all, so no tier can be renamed by what the driver lacks"
        ),
    ),
    NumberKey("fps_limit", FRL_FPS, stock=0, maximum=FRL_MAX),
    NumberKey("bg_app_fps", FRL_BACKGROUND, stock=0, maximum=FRL_MAX, published=False),
)

KEYS: dict[str, DrsKey] = {k.key: k for k in _KEYS}


def lookup(key: str) -> DrsKey | None:
    return KEYS.get(key)


def mapped_ids() -> frozenset[int]:
    """Every DRS setting id this table reads or writes."""
    return frozenset(i for key in KEYS.values() for i in key.ids)

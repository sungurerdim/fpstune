"""A setting's copy states what changes, never by how much (C2, C11 rule 1).

A figure in the words a player reads ("~50MB RAM saved", "5-15% FPS", "8-16 ms
extra input lag") is a claim nothing on this machine produced. Eight commits fixed
that one shape one row at a time (fc4aba7 and d15c4df among them) because nothing
checked the class. Numeric claims belong in ``impact_scores`` (C2), where C11's
``SOURCES`` / ``NO_INSTRUMENT`` bind each metric to an instrument or a named
reason; the copy says what the setting does.

The guard reads every registered setting's ``description``, ``current_impact``,
``recommended_impact``, ``effect`` and ``risk_warning``, and the string literals of
the frontend catalogues ``en.ts``, ``tr.ts`` and ``settingsTr.ts``, and fails on a
quantity: a number tied to ``%``, ``ms``, ``fps``, ``KB``, ``MB``, ``GB`` or ``x``
(Turkish writes the percent sign in front: ``%20``).

What is *not* a claim, and is listed with its reason in ``FACTS``: the setting's
own value ("caps at 20%"), a stock value ("15.6ms default"), a published scale
("Quality renders at 67%"), a size limit. The state lead of an impact string
("30ms: ...") names the value the row is in, so it is not read; the metric name
"1% lows" is not a quantity either.

``PENDING`` is the measured backlog: rows that still carry a claim. It only
shrinks: an entry that no longer violates fails the test, so fixing a row removes
its line and nothing can be added to hide a new one.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from fpstune.settings.base import SettingExecutor
from fpstune.settings.definitions import get_all_static_settings

_NUMBER = r"(?<![\w.,])~?\+?\d+(?:[.,]\d+)?(?:\s*[-–]\s*\d+(?:[.,]\d+)?)?"
_CLAIM = re.compile(
    rf"(?:{_NUMBER}\s*(?:%|(?:ms|fps|kb|mb|gb|x)(?![A-Za-z]))|%\s*{_NUMBER})",
    re.IGNORECASE,
)
_NOT_A_QUANTITY = re.compile(r"(?:\{[^}]*\}|\b1%\s*lows?\b|%1\s*(?:düşük|low)\w*)", re.IGNORECASE)

COPY_FIELDS = ("description", "current_impact", "recommended_impact", "effect", "risk_warning")
_I18N = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n"
I18N_FILES = ("en.ts", "tr.ts", "settingsTr.ts")


def _norm(token: str) -> str:
    """``~10 - 20 ms`` and ``10–20ms`` compare equal."""
    return re.sub(r"[\s~+]", "", token).replace("–", "-").lower()


def quantified_claims(text: str) -> list[str]:
    """Every quantity in ``text`` once placeholders and the "1% lows" metric name are set aside."""
    return [_norm(m.group(0)) for m in _CLAIM.finditer(_NOT_A_QUANTITY.sub(" ", text))]


def _body(field: str, text: str) -> str:
    """An impact string is ``State: consequence``; the state names the value, not a claim."""
    if field.endswith("_impact"):
        state, colon, rest = text.partition(":")
        return rest if colon else text
    return text


# (setting id, field) -> {quantity: reason}. A listed quantity is a fact, not a performance claim.
FACTS: dict[tuple[str, str], dict[str, str]] = {
    ("power:cpu_perf_check_interval", "current_impact"): {
        "30ms": "the stock interval, named as the state the row is in"
    },
    ("timer:global_timer_resolution", "current_impact"): {
        "15.6ms": "Windows' own default timer period"
    },
    ("network:tcp_del_ack_ticks", "current_impact"): {
        "200ms": "the stock delayed-ACK timer (2 ticks of 100 ms)"
    },
    ("gpu-nvidia:battery_boost", "description"): {
        "30fps": "NVIDIA App's own Battery Boost cap value"
    },
    ("gpu-nvidia:battery_boost", "current_impact"): {
        "30fps": "NVIDIA App's own Battery Boost cap value"
    },
    ("gpu-hardware:resizable_bar", "current_impact"): {
        "256mb": "the PCI BAR window size without Resizable BAR (a PCIe fact)"
    },
    ("memory:purge_standby", "description"): {
        "16gb": "the RAM size below which the purge is offered"
    },
    ("system:delivery_optimization_bandwidth", "description"): {"20%": "the cap this row writes"},
    ("system:delivery_optimization_bandwidth", "effect"): {"20%": "the cap this row writes"},
    ("system:onedrive_upload_limit", "description"): {"30%": "the cap this row writes"},
    ("system:onedrive_upload_limit", "effect"): {"30%": "the cap this row writes"},
    ("system:network_afd_receive_window", "description"): {
        "128kb": "the buffer size this row writes"
    },
    ("system:network_afd_receive_window", "recommended_impact"): {
        "128kb": "the buffer size this row writes"
    },
    ("system:network_afd_send_window", "description"): {"128kb": "the buffer size this row writes"},
    ("system:network_afd_send_window", "recommended_impact"): {
        "128kb": "the buffer size this row writes"
    },
    ("cleanup:shadow_copy_reclaim", "description"): {"10%": "the cap this row writes"},
    ("cleanup:shadow_copy_reclaim", "current_impact"): {"10%": "the cap this row writes"},
    ("cleanup:shadow_copy_reclaim", "recommended_impact"): {"10%": "the cap this row writes"},
    ("audio:communications_ducking", "description"): {"80%": "Windows' own default ducking depth"},
    ("game_config:cs2:maxping", "description"): {"50ms": "the limit this row writes"},
    ("game_config:cs2:maxping", "effect"): {"50ms": "the limit this row writes"},
    ("game_config:mw3:dlss_perf_mode", "description"): {
        "67%": "NVIDIA's published DLSS scale per tier",
        "58%": "NVIDIA's published DLSS scale per tier",
        "50%": "NVIDIA's published DLSS scale per tier",
    },
    ("game_config:mw3:dlss_perf_mode", "current_impact"): {"67%": "NVIDIA's published DLSS scale"},
    ("game_config:mw3:dlss_perf_mode", "recommended_impact"): {
        "58%": "NVIDIA's published DLSS scale"
    },
    ("game_config:mw4:dlss_perf_mode", "current_impact"): {"67%": "NVIDIA's published DLSS scale"},
    ("game_config:mw4:dlss_perf_mode", "recommended_impact"): {
        "58%": "NVIDIA's published DLSS scale"
    },
    ("game_config:mw3:render_resolution", "description"): {"67%": "NVIDIA's published DLSS scale"},
    ("game_config:mw3:render_resolution", "current_impact"): {
        "50%": "the render scale being named",
        "67%": "NVIDIA's published DLSS scale",
        "33%": "arithmetic of the two scales (50% x 67%)",
    },
    ("game_config:mw3:render_resolution", "recommended_impact"): {
        "67%": "NVIDIA's published DLSS scale"
    },
    ("game_config:mw3:anisotropic", "description"): {"4x": "the filtering tier this row writes"},
    ("game_config:mw3:anisotropic", "effect"): {"4x": "the filtering tier this row writes"},
    ("game_config:mw3:fps_cap_out_of_focus", "effect"): {"30fps": "the cap this row writes"},
    ("game_config:mw3:vsync_menu", "description"): {"100%": "the value this row writes"},
    ("game_config:mw4:pause_rendering", "description"): {
        "30fps": "the unfocused cap another row writes"
    },
    ("game_config:mw3:local_texture_quality", "current_impact"): {"8gb": "a card's VRAM capacity"},
    ("game_config:mw3:local_texture_quality", "recommended_impact"): {
        "8gb": "a card's VRAM capacity"
    },
    ("game_config:mw3:texture_resolution", "description"): {"8gb": "a card's VRAM capacity"},
    ("game_config:mw3:texture_resolution", "current_impact"): {"8gb": "a card's VRAM capacity"},
    ("game_config:mw3:texture_resolution", "effect"): {"8gb": "a card's VRAM capacity"},
}

# Quantities in the frontend catalogues that are facts, keyed by (file, a distinctive
# fragment of the string).
I18N_FACTS: dict[tuple[str, str], dict[str, str]] = {
    ("en.ts", "Unigine Superposition Basic, a "): {"1.3gb": "size of a one-time download"},
    ("en.ts", "Install the scene ("): {"1.3gb": "size of a one-time download"},
    ("tr.ts", "Test sahnesi Unigine"): {"1,3gb": "size of a one-time download"},
    ("tr.ts", "Sahneyi kur ("): {"1,3gb": "size of a one-time download"},
    ("settingsTr.ts", "%100, çekirdek park"): {"%100": "the value the row writes"},
    ("settingsTr.ts", "oyunları 30 FPS civarında"): {
        "30fps": "NVIDIA App's own Battery Boost cap value"
    },
    ("settingsTr.ts", "16 GB altı RAM"): {"16gb": "the RAM size below which the purge is offered"},
    ("settingsTr.ts", "hattın %20'siyle"): {"%20": "the cap this row writes"},
    ("settingsTr.ts", "yükleme hızının %30'uyla"): {"%30": "the cap this row writes"},
    ("settingsTr.ts", "alma arabelleğini 128 KB"): {"128kb": "the buffer size this row writes"},
    ("settingsTr.ts", "gönderme arabelleğini 128 KB"): {"128kb": "the buffer size this row writes"},
    ("settingsTr.ts", "kapasitenin %10'uyla"): {"%10": "the cap this row writes"},
    ("settingsTr.ts", "diğer tüm sesleri %80"): {"%80": "Windows' own default ducking depth"},
    ("settingsTr.ts", "mm_dedicated_search_maxping 50"): {"50ms": "the limit this row writes"},
    ("settingsTr.ts", "DLSS iç çizim ölçeği"): {
        "%67": "NVIDIA's published DLSS scale per tier",
        "%58": "NVIDIA's published DLSS scale per tier",
        "%50": "NVIDIA's published DLSS scale per tier",
    },
    ("settingsTr.ts", "8 GB kartlarda"): {"8gb": "a card's VRAM capacity"},
    ("settingsTr.ts", "Normal (4x)"): {"4x": "the filtering tier this row writes"},
    ("settingsTr.ts", "%100, menü kare hızını"): {"%100": "the value this row writes"},
    ("settingsTr.ts", "Odak dışı kare sınırı aynı işi 30 fps"): {
        "30fps": "the unfocused cap another row writes"
    },
}

# Rows that still carry a claim, measured 2026-10-06. Shrink-only: delete a line when its
# row is fixed; the test fails on a line whose row no longer violates.
PENDING: dict[tuple[str, str], str] = {
    ("game_config:mw3:anisotropic", "current_impact"): "8x, 16x, 2-3%",
    ("game_config:mw3:dlss_frame_generation", "current_impact"): "10-20ms",
    ("game_config:mw3:dxr_mode", "current_impact"): "20-40%",
    ("game_config:mw3:dxr_mode", "description"): "20-40%",
    ("game_config:mw3:dxr_mode", "recommended_impact"): "20-40%",
    ("game_config:mw3:fsr_frame_interpolation", "current_impact"): "10-20ms",
    ("game_config:mw3:nvidia_reflex", "current_impact"): "10-20ms",
    ("game_config:mw3:nvidia_reflex", "recommended_impact"): "5-15ms",
    ("game_config:mw3:particle_quality", "recommended_impact"): "1.3%, 4%",
    ("game_config:mw3:shader_quality", "current_impact"): "11%",
    ("game_config:mw3:shader_quality", "recommended_impact"): "11%",
    ("game_config:mw3:shadow_quality", "recommended_impact"): "3.6%",
    ("game_config:mw3:ssao", "recommended_impact"): "3-5%",
    ("game_config:mw3:ssr", "current_impact"): "10%",
    ("game_config:mw3:ssr", "recommended_impact"): "5-10%",
    ("game_config:mw3:static_reflection_quality", "current_impact"): "0-1%",
    ("game_config:mw3:static_reflection_quality", "description"): "0-1%",
    ("game_config:mw3:static_reflection_quality", "recommended_impact"): "0-1%",
    ("game_config:mw3:sun_shadow_cascade", "current_impact"): "5-8%",
    ("game_config:mw3:sun_shadow_cascade", "recommended_impact"): "5-8%",
    ("game_config:mw3:tessellation", "current_impact"): "2-5%",
    ("game_config:mw3:tessellation", "recommended_impact"): "2-5%",
    ("game_config:mw3:texture_resolution", "current_impact"): "1-3gb",
    ("game_config:mw3:texture_resolution", "description"): "1-2gb",
    ("game_config:mw3:texture_resolution", "recommended_impact"): "4-6gb",
    ("game_config:mw3:volumetric_quality", "current_impact"): "5-15%",
    ("game_config:mw3:vrs", "description"): "10%",
    ("game_config:mw3:vrs", "recommended_impact"): "0-10%",
    ("game_config:mw3:water_caustics", "current_impact"): "1-2%",
    ("game_config:mw3:water_caustics", "recommended_impact"): "1-2%",
    ("game_config:mw3:weather_grid", "recommended_impact"): "0-1%",
    ("game_config:mw4:amd_antilag", "current_impact"): "10-20ms",
    ("game_config:mw4:dlss_model", "current_impact"): "3%",
    ("game_config:mw4:dlss_model", "description"): "3%",
    ("game_config:mw4:intel_xell", "current_impact"): "10-20ms",
    ("game_config:mw4:model_quality", "current_impact"): "3-6%",
    ("game_config:mw4:nvidia_reflex", "current_impact"): "10-20ms",
    ("game_config:mw4:world_streaming", "current_impact"): "2%",
}
# (file, fragment of the string) -> what the claim is. Same rule, for the catalogues.
I18N_PENDING: dict[tuple[str, str], str] = {
    ("settingsTr.ts", "Dünya yüzeyleri ve nesneler için doku ay"): "1-2gb",
    ("settingsTr.ts", "Gölge ve yansımalar için DirectX ışın iz"): "%20-40",
    ("settingsTr.ts", "Küp harita yansıma sondalarının yeniden "): "%0-1",
    ("settingsTr.ts", "Sürücünün daha az fark edilir saydığı ek"): "%10",
    ("settingsTr.ts", "Yükselticiden ÖNCE uygulanan dış çizim ö"): "%89",
    ("settingsTr.ts", "Yükseltmeyi hangi DLSS sinir modelinin y"): "%3",
}


def _per_adapter_settings() -> list[SettingExecutor]:
    """The per-adapter rows are built per machine; the factories that take only an adapter."""
    from fpstune.settings.definitions import network

    rows: list[SettingExecutor] = []
    for name, factory in vars(network).items():
        if not (name.startswith("create_") and name.endswith("_setting")):
            continue
        if list(inspect.signature(factory).parameters) == ["interface_index", "display_name"]:
            rows.append(factory(7, "Test adapter"))
    return rows


def _id_key(setting_id: str) -> str:
    """A per-adapter id carries the adapter's index; the record names the pattern (C9)."""
    return re.sub(r"^network:\d+:", "network:*:", setting_id)


def _setting_violations() -> dict[tuple[str, str], list[str]]:
    found: dict[tuple[str, str], list[str]] = {}
    for setting in [*get_all_static_settings(), *_per_adapter_settings()]:
        for field in COPY_FIELDS:
            text = getattr(setting, field, None)
            if not text:
                continue
            key = (_id_key(setting.id), field)
            allowed = FACTS.get(key, {})
            bad = [q for q in quantified_claims(_body(field, text)) if q not in allowed]
            if bad:
                found[key] = bad
    return found


def _i18n_strings() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for name in I18N_FILES:
        source = (_I18N / name).read_text(encoding="utf-8")
        out += [(name, m.group(1)) for m in re.finditer(r'"((?:[^"\\\n]|\\.)*)"', source)]
    return out


def _i18n_violations() -> dict[tuple[str, str], list[str]]:
    found: dict[tuple[str, str], list[str]] = {}
    for name, text in _i18n_strings():
        allowed: dict[str, str] = {}
        for (fact_file, fragment), quantities in I18N_FACTS.items():
            if fact_file == name and fragment in text:
                allowed.update(quantities)
        bad = [q for q in quantified_claims(text) if q not in allowed]
        if bad:
            found[(name, text)] = bad
    return found


def test_no_registered_copy_quotes_a_quantity_nothing_measured() -> None:
    new = {k: v for k, v in _setting_violations().items() if k not in PENDING}

    assert not new, (
        "copy states how much instead of what changes (C2/C11): move the figure to "
        "impact_scores, or list a fact in FACTS with its reason:\n"
        + "\n".join(f"  {sid} {field}: {q}" for (sid, field), q in sorted(new.items()))
    )


def test_pending_settings_only_shrink() -> None:
    violating = _setting_violations()
    fixed = sorted(k for k in PENDING if k not in violating)

    assert not fixed, f"these rows no longer carry a claim; delete them from PENDING: {fixed}"


def test_every_fact_is_still_a_quantity_in_the_copy() -> None:
    """A fact whose figure left the copy is a stale exemption that could mask a new claim."""
    by_id: dict[str, SettingExecutor] = {s.id: s for s in get_all_static_settings()}
    stale = []
    for (sid, field), quantities in FACTS.items():
        setting = by_id.get(sid)
        text = getattr(setting, field, None) if setting else None
        present = set(quantified_claims(_body(field, text))) if text else set()
        stale += [(sid, field, q) for q in quantities if q not in present]

    assert not stale, f"FACTS lists a quantity the copy no longer contains: {stale}"


def test_no_catalogue_string_quotes_a_quantity_nothing_measured() -> None:
    new = {
        k: v
        for k, v in _i18n_violations().items()
        if not any(f == k[0] and frag in k[1] for f, frag in I18N_PENDING)
    }

    assert not new, (
        "a frontend catalogue string states how much (C2/C11): reword it, or list a fact "
        "in I18N_FACTS with its reason:\n"
        + "\n".join(f"  {f}: {t[:110]!r} -> {q}" for (f, t), q in sorted(new.items()))
    )


def test_pending_catalogue_strings_only_shrink() -> None:
    violating = _i18n_violations()
    fixed = sorted(
        (f, frag)
        for f, frag in I18N_PENDING
        if not any(f == name and frag in text for name, text in violating)
    )

    assert not fixed, (
        f"these strings no longer carry a claim; delete them from I18N_PENDING: {fixed}"
    )


def test_every_catalogue_fact_is_still_a_quantity_in_its_string() -> None:
    strings = _i18n_strings()
    stale = []
    for (name, fragment), quantities in I18N_FACTS.items():
        present = {
            q
            for file, text in strings
            if file == name and fragment in text
            for q in quantified_claims(text)
        }
        stale += [(name, fragment, q) for q in quantities if q not in present]

    assert not stale, f"I18N_FACTS lists a quantity no string contains any more: {stale}"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Disabled: No widgets process -> ~100MB RAM freed", ["100mb"]),
        ("Saves ~100-300MB RAM.", ["100-300mb"]),
        ("Enabled: 5-21% FPS gain in streaming-heavy titles", ["5-21%"]),
        ("5–10ms lower frame latency", ["5-10ms"]),
        ("up to 20 - 40 ms input delay", ["20-40ms"]),
        ("Kapatmak 4-16 GB SSD alanı boşaltır.", ["4-16gb"]),
        ("kare hızının %20-40'ına mal olur", ["%20-40"]),
        ("tek seferlik 1,3 GB'lık bir indirme", ["1,3gb"]),
        ("2x as fast", ["2x"]),
        ("steadier 1% lows and 1% low drops", []),
        ("Signal {signal}% on the {band} GHz band", []),
        ("Windows 11 build 26200, 3 retries, 2 frames", []),
        ("max stable 5 mbps? no", []),
    ],
)
def test_the_detector_reads_quantities_in_both_languages(text: str, expected: list[str]) -> None:
    """Pins the rule, so a loosened pattern cannot quietly stop the guards above firing."""
    assert quantified_claims(text) == expected


def test_nagle_scores_describe_the_state_the_row_recommends() -> None:
    """Nagle's row recommends the stock state (batching on); its scores once claimed a latency
    gain and a throughput loss, the effects of the opposite action."""
    from fpstune.settings.definitions.network import NAGLE_ALGORITHM

    assert NAGLE_ALGORITHM.recommended_value == NAGLE_ALGORITHM.default_value == "enabled"
    assert NAGLE_ALGORITHM.impact_scores["latency_ms"] == 0.0
    assert NAGLE_ALGORITHM.impact_scores["download_throughput"] != "reduced"

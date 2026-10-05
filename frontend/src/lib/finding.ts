import { t, getLocale } from "../i18n";
import type { MessageKey } from "../i18n/en";
import { formatSettingValue, type Setting } from "../types/setting";

/**
 * The sentence an advisory's measured finding becomes.
 *
 * A finding arrives from the backend as numbers under a `kind` — the rate this
 * link negotiated and the rate the adapter can do, the signal and band a radio
 * is on. This is the one place those numbers become words: a summary that says
 * what was measured, and, when something is wrong, the one move that fixes it.
 * Every number is the machine's own (C9, C11); this module only phrases it.
 *
 * A kind this module has no sentence for yields null, and the row falls back
 * to its static description — never to raw JSON.
 */

export interface FindingText {
  /** What was measured, e.g. "Link at 100 Mbps; the adapter supports 2.5 Gbps." */
  summary: string;
  /** The move that fixes it; empty when nothing is wrong. */
  advice: string;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** "100 Mbps", "1 Gbps", "2.5 Gbps" — in the active locale's decimal form. */
export function formatMbps(mbps: number): string {
  if (mbps >= 1000) {
    const gbps = mbps / 1000;
    return `${gbps.toLocaleString(getLocale())} Gbps`;
  }
  return `${mbps.toLocaleString(getLocale())} Mbps`;
}

/**
 * The cable class a ceiling needs. 2.5 Gbps and up wants Cat 6; gigabit runs on
 * Cat 5e. Below that any Ethernet cable carries it, so nothing is named.
 */
export function cableFor(ceilingMbps: number): string {
  if (ceilingMbps >= 2500) return "Cat 6";
  if (ceilingMbps >= 1000) return "Cat 5e";
  return "";
}

function linkSpeed(finding: Record<string, unknown>): FindingText | null {
  const linked = num(finding.linked_mbps);
  const ceiling = num(finding.ceiling_mbps);
  if (linked === null || ceiling === null) return null;
  const params = { linked: formatMbps(linked), ceiling: formatMbps(ceiling) };
  if (linked >= ceiling) {
    return { summary: t("finding.linkSpeed.atCeiling", params), advice: "" };
  }
  const cable = cableFor(ceiling);
  return {
    summary: t("finding.linkSpeed.below", params),
    advice: cable
      ? t("finding.linkSpeed.adviceCable", { ...params, cable })
      : t("finding.linkSpeed.adviceFarEnd", params),
  };
}

function wifiLink(
  finding: Record<string, unknown>,
  value: unknown,
): FindingText | null {
  const signal = num(finding.signal_percent);
  if (signal === null) return null;
  const band = num(finding.band_ghz) ?? 0;
  const radio = typeof finding.radio === "string" ? finding.radio : "";
  const params = {
    signal,
    band: band.toLocaleString(getLocale()),
    radio: radio ? ` (${radio})` : "",
  };
  const summary =
    band > 0
      ? t("finding.wifi.onBand", params)
      : t("finding.wifi.bandUnknown", params);
  const adviceKey: MessageKey | null =
    value === "weak_signal"
      ? "finding.wifi.adviceSignal"
      : value === "on_2_4ghz"
        ? "finding.wifi.adviceBand"
        : null;
  return { summary, advice: adviceKey ? t(adviceKey) : "" };
}

function wifiSecurity(
  finding: Record<string, unknown>,
  value: unknown,
): FindingText | null {
  const auth = typeof finding.auth === "string" ? finding.auth : "";
  const cipher = typeof finding.cipher === "string" ? finding.cipher : "";
  if (!auth && !cipher) return null;
  const params = { auth: auth || "?", cipher: cipher || "?" };
  if (value === "legacy_cipher") {
    return {
      summary: t("finding.wifiSecurity.legacyCipher", params),
      advice: t("finding.wifiSecurity.adviceCipher"),
    };
  }
  if (value === "wpa3_available") {
    return {
      summary: t("finding.wifiSecurity.wpa3Available", params),
      advice: t("finding.wifiSecurity.adviceWpa3"),
    };
  }
  return { summary: t("finding.wifiSecurity.good", params), advice: "" };
}

function thermal(finding: Record<string, unknown>): FindingText | null {
  const throttling = finding.throttling;
  if (typeof throttling !== "boolean") return null;
  const celsius = num(finding.celsius);
  // The temperature is context, not the verdict: an ACPI zone's meaning varies
  // by board, so it is reported as the zone reading it is and never turned into
  // a threshold. The verdict is what the firmware itself says.
  const reading =
    celsius === null
      ? t("finding.thermal.noReading")
      : t("finding.thermal.zoneReads", { celsius });
  return throttling
    ? {
        summary: t("finding.thermal.throttling", { reading }),
        advice: t("finding.thermal.advice"),
      }
    : { summary: t("finding.thermal.notThrottling", { reading }), advice: "" };
}

function powerDcRail(finding: Record<string, unknown>): FindingText | null {
  const dc = finding.dc_value;
  const stock = finding.windows_dc_default;
  if (dc === undefined || dc === null || stock === undefined || stock === null) return null;
  // fpstune tunes the mains rail only; on battery Windows' own value is the
  // answer, so a battery value that differs from it is drift (another
  // optimizer, or an older fpstune that wrote both rails) and the next apply
  // puts it back.
  return {
    summary: t("finding.powerDcRail.drift", { dc: String(dc), stock: String(stock) }),
    advice: t("finding.powerDcRail.advice"),
  };
}

/** How many names a startup-apps sentence spells out before "and N more". */
const STARTUP_NAMES_SHOWN = 5;

function startupApps(finding: Record<string, unknown>): FindingText | null {
  const count = num(finding.count);
  if (count === null) return null;
  if (count === 0) return { summary: t("finding.startupApps.none"), advice: "" };
  const listed = Array.isArray(finding.names)
    ? finding.names.filter((name): name is string => typeof name === "string")
    : [];
  // A count with no names to show is no sentence; the row keeps its description.
  if (listed.length === 0) return null;
  const shown = listed.slice(0, STARTUP_NAMES_SHOWN).join(", ");
  // The detect script names at most twelve; the count is the whole list.
  const rest = count - Math.min(listed.length, STARTUP_NAMES_SHOWN);
  const names = rest > 0 ? t("finding.startupApps.more", { names: shown, rest }) : shown;
  return {
    summary:
      count === 1
        ? t("finding.startupApps.one", { names })
        : t("finding.startupApps.many", { count, names }),
    advice: t("finding.startupApps.advice"),
  };
}

/** "16.7" — a frame's time on screen at `hz`, in the active locale. */
function frameMs(hz: number): string {
  return (1000 / hz).toLocaleString(getLocale(), { maximumFractionDigits: 1 });
}

function displayMode(finding: Record<string, unknown>): FindingText | null {
  const width = num(finding.width);
  const height = num(finding.height);
  const hz = num(finding.refresh_hz);
  const nativeWidth = num(finding.native_width);
  const nativeHeight = num(finding.native_height);
  const max = num(finding.max_refresh_hz);
  if ([width, height, hz, nativeWidth, nativeHeight, max].some((v) => v === null || v === 0)) {
    return null;
  }
  const lowRefresh = hz! < max!;
  const lowResolution = width !== nativeWidth || height !== nativeHeight;
  const parts: string[] = [];
  if (lowRefresh) {
    parts.push(
      t("finding.displayMode.lowRefresh", {
        hz: hz!,
        max: max!,
        oldMs: frameMs(hz!),
        newMs: frameMs(max!),
      }),
    );
  }
  if (lowResolution) {
    parts.push(
      t("finding.displayMode.lowResolution", {
        width: width!,
        height: height!,
        nativeWidth: nativeWidth!,
        nativeHeight: nativeHeight!,
      }),
    );
  }
  if (parts.length === 0) {
    return {
      summary: t("finding.displayMode.native", { width: width!, height: height!, hz: hz! }),
      advice: "",
    };
  }
  if (finding.primary === false) parts.push(t("finding.displayMode.secondary"));
  return { summary: parts.join(" "), advice: t("finding.displayMode.advice") };
}

/** The finding's sentence(s) for this setting, or null when it carries none. */
export function describeFinding(setting: Setting): FindingText | null {
  const finding = setting.finding;
  if (!finding) return null;
  switch (finding.kind) {
    case "link_speed":
      return linkSpeed(finding);
    case "wifi_link":
      return wifiLink(finding, setting.currentValue);
    case "wifi_security":
      return wifiSecurity(finding, setting.currentValue);
    case "thermal":
      return thermal(finding);
    case "power_dc_rail":
      return powerDcRail(finding);
    case "startup_apps":
      return startupApps(finding);
    case "display_mode":
      return displayMode(finding);
    default:
      return null;
  }
}

/**
 * The readable form of an advisory's one-word value. `below_capability` is a
 * state name for the comparison code; a row shows "Below the adapter's maximum".
 * Only the words this catalogue names are translated — anything else renders
 * as itself, so a new enum is visible rather than silently mislabelled.
 */
const CHOICE_KEYS: Record<string, MessageKey> = {
  at_capability: "choice.at_capability",
  below_capability: "choice.below_capability",
  good: "choice.good",
  weak_signal: "choice.weak_signal",
  on_2_4ghz: "choice.on_2_4ghz",
  legacy_cipher: "choice.legacy_cipher",
  wpa3_available: "choice.wpa3_available",
  not_throttling: "choice.not_throttling",
  throttling: "choice.throttling",
  none_at_startup: "choice.none_at_startup",
  apps_at_startup: "choice.apps_at_startup",
  native: "choice.native",
  not_native: "choice.not_native",
};

/** A tweak that explains its state with measured numbers, like an advisory does. */
export function explainsWithFinding(setting: Setting): boolean {
  return setting.isReadonly || setting.finding?.kind === "display_mode";
}

export function advisoryChoiceLabel(value: unknown): string | null {
  const key = typeof value === "string" ? CHOICE_KEYS[value] : undefined;
  return key ? t(key) : null;
}

/**
 * The one way a row prints a setting's value: an advisory's state name in
 * words, else the raw-value hint the definition carries, else the value.
 */
export function valueLabel(setting: Setting, value: unknown): string {
  if (explainsWithFinding(setting)) {
    const words = advisoryChoiceLabel(value);
    if (words) return words;
  }
  const hint = value !== null ? setting.valueHints?.[String(value)] : undefined;
  return hint ?? formatSettingValue(value);
}

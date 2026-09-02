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
};

export function advisoryChoiceLabel(value: unknown): string | null {
  const key = typeof value === "string" ? CHOICE_KEYS[value] : undefined;
  return key ? t(key) : null;
}

/**
 * The one way a row prints a setting's value: an advisory's state name in
 * words, else the raw-value hint the definition carries, else the value.
 */
export function valueLabel(setting: Setting, value: unknown): string {
  if (setting.isReadonly) {
    const words = advisoryChoiceLabel(value);
    if (words) return words;
  }
  const hint = value !== null ? setting.valueHints?.[String(value)] : undefined;
  return hint ?? formatSettingValue(value);
}

import type { MessageKey } from "../i18n/en";
import type { HardwareComponent, Setting, TweakDomain } from "../types/setting";

/**
 * Which page owns a tweak.
 *
 * The backend decides (`SettingExecutor.domain`): a tweak's category is the
 * physical component it acts on, never how it is set — PCIe link power saving is
 * a powercfg key and still a PCIe tweak. Every surface asks these predicates and
 * none re-derives the split from an id, so the three partition the registry and
 * nothing lands twice.
 */

/** True when a tweak is a line in a game's own config file. */
export function isGameTweak(setting: Setting): boolean {
  return setting.domain === "game";
}

/** True when a tweak acts on a physical component. */
export function isHardwareTweak(setting: Setting): boolean {
  return setting.domain === "hardware";
}

/** True for a software tweak: everything neither hardware nor a game's own file. */
export function isSoftwareTweak(setting: Setting): boolean {
  return setting.domain === "software";
}

/** True when a tweak acts on the named physical component. */
export function isComponentTweak(setting: Setting, component: HardwareComponent): boolean {
  return setting.component === component;
}

/**
 * The name of the default a domain's "Reset to default" writes back: Windows'
 * own value for a software tweak, the driver's for a component, the game's for
 * a line in its config file. One way back everywhere; only the word differs.
 */
export const DEFAULT_KIND_KEY = {
  software: "reset.kind.software",
  hardware: "reset.kind.hardware",
  game: "reset.kind.game",
} as const satisfies Record<TweakDomain, MessageKey>;

/** The default-kind word for one setting's domain. */
export function defaultKindKey(setting: Setting): MessageKey {
  return DEFAULT_KIND_KEY[setting.domain];
}

/** The one domain every setting in a scope shares, or "mixed" when they differ. */
export function scopeDomain(settings: readonly Setting[]): TweakDomain | "mixed" {
  const first = settings[0]?.domain;
  if (first === undefined) return "mixed";
  return settings.every((s) => s.domain === first) ? first : "mixed";
}

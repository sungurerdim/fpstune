import type { HardwareComponent, Setting } from "../types/setting";

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

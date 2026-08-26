import type { Setting } from "../types/setting";

/**
 * Which settings modules belong to a piece of hardware.
 *
 * This list is the single source for the hardware/software split. The Hardware page
 * uses it to decide what to render on a device, and Home uses it to decide what goes
 * in the hardware group — so a module added here shows up in both, and neither
 * screen can end up claiming a tweak the other does not.
 *
 * `storage`, `audio` and `display` are on this page without being per-device: TRIM
 * and 8.3 names are filesystem-wide, enhancements and ducking are system audio
 * policy, windowed flip model and MPO are the display stack. They belong to the
 * hardware domain and sit at section level rather than under one drive or endpoint.
 */
export const HARDWARE_MODULES = [
  "gpu-nvidia",
  "gpu-amd",
  "gpu-hardware",
  "display",
  "storage",
  "audio",
] as const;

/**
 * Findings about a physical component that has no settings module of its own.
 *
 * CPU and RAM are on the Hardware page as hardware, but neither has a module — their
 * two findings live under `system`, alongside ~180 software settings, so neither
 * `HARDWARE_MODULES` nor anything else could reach them. The consequence was
 * concrete: XMP, which claims +5-15% in CPU-bound titles and is the single largest
 * hardware finding fpstune makes, was filed as a software tweak and never appeared
 * next to the memory it is about.
 *
 * Listed by id rather than by widening `HARDWARE_MODULES` to "system", which would
 * move every one of those 180 settings onto the Hardware page.
 */
export const PHYSICAL_COMPONENT_TWEAKS = {
  cpu: ["system:thermal_condition"],
  memory: ["system:xmp_expo"],
} as const satisfies Record<string, readonly string[]>;

/** True when a tweak is a finding about the named physical component. */
export function isComponentTweak(
  setting: Setting,
  component: keyof typeof PHYSICAL_COMPONENT_TWEAKS,
): boolean {
  return (PHYSICAL_COMPONENT_TWEAKS[component] as readonly string[]).includes(setting.id);
}

/**
 * Per-adapter settings are named `network:<interfaceIndex>:<name>`.
 *
 * The index rather than the adapter name, because names are localised — fpstune
 * stores the index deliberately, and this is what lets a tweak be attributed to one
 * physical adapter. The rest of the `network` module (TCP stack, DNS, QoS) is
 * system-wide and therefore software.
 */
const PER_ADAPTER_ID = /^network:\d+:/;

/**
 * Settings that live inside a game's own config file rather than in Windows.
 *
 * A third domain beside hardware and software, and the largest of the three: 181
 * of the registry's settings are one game's config line. They were listed among
 * ~180 Windows tweaks under a single "Game Configs" category, where a Modern
 * Warfare shadow tier sat between a TCP window and a scheduled task.
 *
 * `game_cleanup` is deliberately not here. Those ten are delete actions — they
 * reclaim disk and change no setting — and they already have a home in Cleanup &
 * Repair, where the one Run button drives them.
 */
const GAME_MODULE = "game_config";

/** True when a tweak is a line in a game's own config file. */
export function isGameTweak(setting: Setting): boolean {
  return setting.module === GAME_MODULE;
}

/** True when a tweak belongs to the hardware domain rather than the software one. */
export function isHardwareTweak(setting: Setting): boolean {
  return (
    (HARDWARE_MODULES as readonly string[]).includes(setting.module) ||
    PER_ADAPTER_ID.test(setting.id) ||
    Object.values(PHYSICAL_COMPONENT_TWEAKS).some((ids) =>
      (ids as readonly string[]).includes(setting.id),
    )
  );
}

import { useMemo } from "react";
import { useStore } from "../store";
import { isTweakAdvisory, isTweakListable, isTweakSuboptimal } from "../lib/tweakStatus";
import type { Setting } from "../types/setting";

/** One device's tweaks and what they add up to. */
export interface DeviceTweaks {
  /** Every listed row: writable ones with a reading, plus unresolved advisories. */
  settings: Setting[];
  /** Writable rows away from their ideal value. */
  toApply: number;
  /** Findings only the user can act on (BIOS, cable, placement). */
  advisories: number;
}

/**
 * The tweaks a predicate claims, read from the store.
 *
 * Shared by the Hardware page's card and Home's compact card, so "3 to apply"
 * on Home is the same count the card it opens shows.
 */
export function useDeviceTweaks(match: ((setting: Setting) => boolean) | undefined): DeviceTweaks {
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  return useMemo(() => {
    const listed: Setting[] = [];
    if (match) {
      for (const s of settings.values()) {
        if (match(s) && (isTweakListable(s) || isTweakAdvisory(s))) listed.push(s);
      }
    }
    listed.sort((a, b) => a.categoryOrder - b.categoryOrder);
    return {
      settings: listed,
      toApply: listed.filter(isTweakSuboptimal).length,
      advisories: listed.filter(isTweakAdvisory).length,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settings, settingsVersion, match]);
}

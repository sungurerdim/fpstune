/**
 * Plain helpers for the hardware cards.
 *
 * Separate from `shared.tsx` because a file that exports both components and
 * functions breaks React Fast Refresh — the whole module reloads instead of the
 * component, which the linter flags.
 */

import type { HardwareInfo } from "../../lib/hardware-manager";

export function isCategoryLoading(
  hardware: HardwareInfo | undefined | null,
  isLoading: boolean,
  category: string,
): boolean {
  if (isLoading) return true;
  if (!hardware) return true;
  if (hardware.detecting) {
    if (category === "gpu") return !hardware.gpus?.length;
  }
  return false;
}

export function safeArray<T>(arr: T[] | undefined | null): T[] {
  return Array.isArray(arr) ? arr : [];
}

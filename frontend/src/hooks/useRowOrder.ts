import { useMemo, useState } from "react";
import type { Setting } from "../types/setting";

/** Where a row sits among its neighbours: what needs work, what is right, what is unread. */
const NOT_OPTIMIZED = 0;
const OPTIMIZED = 1;
const UNREAD = 2;

/**
 * The order rows are listed in: not optimized first, then optimized, each in the
 * backend's own order.
 *
 * "First" is decided once per row — the moment it is first read — and then
 * kept. Applying a tweak flips its verdict, and a list that re-sorted on every
 * verdict would slide the next row under the pointer while it is being clicked.
 * The row that was fixed stays where it was, now marked fixed; the next load
 * (a restart, or a row read for the first time) lists it among the optimized.
 *
 * The verdict is the backend's `isOptimized`, never recomputed here.
 */
export function useRowOrder(settings: readonly Setting[]): (a: Setting, b: Setting) => number {
  const [ranks, setRanks] = useState<ReadonlyMap<string, number>>(() => new Map());

  // Rows read since the last render join the ranking now rather than in an
  // effect, so a list never paints once in the wrong order before it is fixed.
  let grown: Map<string, number> | null = null;
  for (const s of settings) {
    if (s.currentValue === null || ranks.has(s.id) || grown?.has(s.id)) continue;
    grown ??= new Map(ranks);
    grown.set(s.id, s.isOptimized ? OPTIMIZED : NOT_OPTIMIZED);
  }
  if (grown) setRanks(grown);
  const current = grown ?? ranks;

  return useMemo(
    () => (a, b) =>
      (current.get(a.id) ?? UNREAD) - (current.get(b.id) ?? UNREAD) ||
      a.categoryOrder - b.categoryOrder ||
      a.displayName.localeCompare(b.displayName),
    [current],
  );
}

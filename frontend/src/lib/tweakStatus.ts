import type { Setting } from "../types/setting";

/**
 * A tweak that is applicable, settable, actually read, and not at its ideal value.
 *
 * One definition shared by Home's list and the per-device lists on the Hardware
 * page. Two copies would drift, and then one screen would offer a fix the other
 * says is unnecessary — the UI version of a detect that observes less than its
 * apply writes, which is the defect class this codebase keeps paying for.
 *
 * Each clause earns its place:
 *  - `isApplicable`: the hardware or software the tweak targets is present at all
 *  - `!isAction`: actions have no state to be ideal or not; they just run
 *  - `!isReadonly`: advisory settings are shown, never applied
 *  - `currentValue !== null`: nothing has been read yet, so "not ideal" is unknown
 *    rather than false — claiming it either way is asserting a result we lack
 */
export function isTweakSuboptimal(setting: Setting): boolean {
  return (
    setting.isApplicable &&
    !setting.isAction &&
    !setting.isReadonly &&
    setting.currentValue !== null &&
    setting.status === "suboptimal"
  );
}

/** A tweak worth listing on a device card: applicable, settable, and detected. */
export function isTweakListable(setting: Setting): boolean {
  return (
    setting.isApplicable &&
    !setting.isAction &&
    !setting.isReadonly &&
    setting.currentValue !== null
  );
}

/**
 * A finding the device has that fpstune cannot write — Resizable BAR, a fan curve,
 * a link running under the adapter's own capability.
 *
 * These were invisible on the Hardware page: `isTweakListable` excludes
 * `isReadonly`, and nothing else listed them, so the findings most likely to cost
 * real frames were the ones the page never mentioned. They are deliberately kept
 * apart from `isTweakSuboptimal` rather than folded into it — a count that mixes
 * "fpstune will fix this" with "only you can fix this" makes the Fix-all button a
 * lie about its own scope.
 *
 * `status === "suboptimal"` is what makes it a finding at all: an advisory sitting
 * at its recommended value is a passed check, not an item.
 */
export function isTweakAdvisory(setting: Setting): boolean {
  return (
    setting.isApplicable &&
    !setting.isAction &&
    setting.isReadonly &&
    setting.currentValue !== null &&
    setting.status === "suboptimal"
  );
}

/**
 * A read-only row: a finding fpstune cannot write (a cable, an XMP profile), a
 * check that found nothing wrong, or one that could not read anything. All
 * three are listed — a check that found nothing is the evidence it ran, and a
 * detector that could not answer must not look like one that was never wired —
 * under "Manual steps", never in a count and never behind an Apply.
 */
export function isTweakManual(setting: Setting): boolean {
  return setting.isApplicable && !setting.isAction && setting.isReadonly;
}

/**
 * A row the Optimize tab lists: it applies to this machine, is a setting rather
 * than a cleanup run, and has been read — or is being read right now, so its
 * line says "Reading…" instead of the row being absent. A writable setting
 * whose read came back empty is the detection notice's business, not a row's;
 * a read-only one stays, saying "Not read".
 */
export function isOptimizeRow(setting: Setting): boolean {
  return (
    setting.isApplicable &&
    !setting.isAction &&
    (setting.currentValue !== null || setting.status === "loading" || setting.isReadonly)
  );
}

/** What a category header counts. */
export interface TweakCounts {
  /** Tweaks that were read and apply here. */
  total: number;
  /** Of those, the ones the backend marked not optimized. */
  notOptimized: number;
  /** Tweaks still being read: no answer yet, so neither number includes them. */
  reading: number;
}

/**
 * The numbers behind "N of M not optimized".
 *
 * A read-only row is a manual step, a cleanup is an action, one that does not
 * apply here cannot be optimized, and one still being read has no answer yet —
 * none of those is "not optimized". The verdict is the backend's `isOptimized`,
 * never recomputed from the two values.
 */
export function tweakCounts(settings: Iterable<Setting>): TweakCounts {
  const counts: TweakCounts = { total: 0, notOptimized: 0, reading: 0 };
  for (const s of settings) {
    if (s.isReadonly || s.isAction || !s.isApplicable) continue;
    if (s.status === "loading" && s.currentValue === null) {
      counts.reading += 1;
      continue;
    }
    counts.total += 1;
    if (!s.isOptimized) counts.notOptimized += 1;
  }
  return counts;
}

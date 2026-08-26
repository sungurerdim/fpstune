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

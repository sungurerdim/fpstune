/**
 * Reading a ledger area without inventing anything it does not say.
 *
 * Two rules from C11 decide every line here. A number the instrument did not
 * produce is not shown, so an unmeasured area gets its reason and nothing else.
 * And no two areas are ever combined: there is deliberately no function in this
 * file that takes more than one area's numbers, because the three headlines
 * fpstune shipped wrong were all sums.
 *
 * The third rule is quieter and belongs to `verdictOf`. Which direction counts
 * as an improvement is a property of the metric — fewer milliseconds is better,
 * more megabytes per second is better — and that judgement lives server-side
 * with `improves_upward`. When the payload carries it, this names a winner;
 * when it does not, the change is shown at its measured size and called
 * "changed", never guessed at from the area's name.
 */

import type { LedgerArea, LedgerJob } from "./api";

export type AreaVerdict =
  /** Moved the way this metric improves, by more than the machine's own noise. */
  | "improved"
  /** Moved the other way, by more than the noise. */
  | "worse"
  /** Moved past the noise, but nothing here knows which way is up. */
  | "changed"
  /** Inside this machine's own variation — not "no change", "cannot tell". */
  | "within_noise"
  /** No pair, no instrument, or a bench that could not run. Carries a reason. */
  | "unmeasured";

export function verdictOf(area: LedgerArea): AreaVerdict {
  if (!area.measured) return "unmeasured";
  if (!area.exceeds_noise) return "within_noise";

  // The server's own word first, when it has one: a second opinion computed
  // here is a second opinion that will eventually disagree with it.
  if (area.verdict === "improved" || area.verdict === "worse") {
    return area.verdict;
  }

  const delta = area.delta;
  if (
    (area.improves_upward === true || area.improves_upward === false) &&
    delta !== null &&
    delta !== 0
  ) {
    return delta > 0 === area.improves_upward ? "improved" : "worse";
  }
  return "changed";
}

/**
 * One reading, in the instrument's own unit.
 *
 * Two decimals, matching the comparison table, and the unit verbatim from the
 * bench that produced it — never converted, because a converted number is one
 * no instrument reported.
 */
export function formatReading(value: number | null, unit: string): string {
  if (value === null) return "";
  return `${value.toFixed(2)}${unit}`;
}

/** The same, with the sign kept: +2.10ms and -2.10ms are opposite results. */
export function formatDelta(value: number | null, unit: string): string {
  if (value === null) return "";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}${unit}`;
}

/**
 * What a bench key is called, in the backend's own words.
 *
 * The areas carry the mapping — each names its instrument and its label — so a
 * running job's bench key becomes a name the user can read without a second
 * request and without a table of labels invented here (C9). A key no area
 * claims stays the key it is, which is honest and still identifies the step.
 */
export function benchLabel(areas: LedgerArea[], key: string | null): string {
  if (!key) return "";
  for (const area of areas) {
    if (area.instrument === key) return area.label;
  }
  return key;
}

/** How far through its plan a job is, as a step number a human counts from 1. */
export function jobStep(job: LedgerJob): { step: number; total: number } {
  const total = job.plan.length;
  // `step_index` counts finished steps, so the step being worked on is the next
  // one — and a finished plan must not report step 8 of 7.
  return { step: Math.min(job.step_index + 1, Math.max(total, 1)), total };
}

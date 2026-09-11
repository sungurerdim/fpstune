/**
 * What an action's detected value is a reading *of*.
 *
 * Every action reports its state in one string of the form `kind|payload`, and
 * until this existed every one of them went through `parseCleanupSize` — which
 * splits on "|" and returns whatever follows, whatever it is. That is right for
 * `ready|4096 MB` and silently wrong for the rest: `maintenance:ssd_retrim`
 * answers `overdue|never` or `ok|23 days`, so a machine whose SSDs had never
 * been retrimmed showed "never" in a badge with a hard-drive icon, next to
 * cleanups measured in megabytes — a maintenance date rendered as disk space.
 *
 * Two rules the shape enforces:
 *
 * 1. **A reading names its own kind.** The caller switches on `kind` and cannot
 *    reach the payload without doing so, which is what makes the mix-up above
 *    unrepresentable rather than merely fixed.
 * 2. **A payload that cannot be read is `null`, never a default.** "This SSD has
 *    never been retrimmed" is a claim about the user's machine; an `overdue|`
 *    with nothing readable behind it is not evidence for it, so nothing is shown
 *    (C11 rule 3 — what could not be measured says so).
 *
 * Size readings keep their existing behaviour exactly, including the prefix a
 * size may carry that is not `ready|`: this parser is what the rows ask, and a
 * size that stopped rendering would be a regression, not a fix.
 */

import { parseCleanupSize } from "./cleanupSize";

export type ActionReading =
  /** A reclaimable amount, verbatim: "4096 MB", "calculating", "unavailable". */
  | { kind: "size"; size: string }
  /** Upkeep that is late — `never` when no run was ever recorded. */
  | { kind: "overdue"; detail: "never" | { days: number } }
  /** Upkeep that is current, with the age of the oldest run. */
  | { kind: "ok"; days: number };

/** `23 days`, or the `1 day` a future backend might spell correctly. */
const DAYS = /^(\d+)\s*days?$/;

/**
 * Parse an action's detected value into the kind of reading it is.
 *
 * `null` for anything with no readable kind — including a non-string value, an
 * empty payload, and an age nobody can parse.
 */
export function parseActionReading(value: unknown): ActionReading | null {
  if (typeof value !== "string") return null;
  const separator = value.indexOf("|");
  if (separator === -1) return null;

  const kind = value.slice(0, separator).trim().toLowerCase();
  const payload = value.slice(separator + 1).trim();
  if (payload === "") return null;

  if (kind === "overdue") {
    if (payload.toLowerCase() === "never") {
      return { kind: "overdue", detail: "never" };
    }
    const days = DAYS.exec(payload);
    return days ? { kind: "overdue", detail: { days: Number(days[1]) } } : null;
  }

  if (kind === "ok") {
    const days = DAYS.exec(payload);
    return days ? { kind: "ok", days: Number(days[1]) } : null;
  }

  // Everything else is a size, which is what the rows have always assumed —
  // `parseCleanupSize` stays the one implementation of that reading.
  const size = parseCleanupSize(value);
  return size === null || size === "" ? null : { kind: "size", size };
}

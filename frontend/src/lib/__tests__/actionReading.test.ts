/**
 * An action's detected value says what *kind* of reading it is, and the row has
 * to ask before it renders one.
 *
 * The defect this guards: every action reading went through `parseCleanupSize`,
 * which splits on "|" and hands back whatever is on the right of it. That is
 * correct for `ready|4096 MB` and silently wrong for everything else — the SSD
 * retrim reports `overdue|never` and `ok|23 days`, so the row put "never" and
 * "23 days" in a badge with a hard-drive icon, presenting a maintenance date as
 * an amount of disk space.
 *
 * The parser is strict on purpose. A reading it cannot account for is `null`,
 * not a guess: an unreadable overdue payload must not become "never run", which
 * would be a claim about this machine that nothing measured (C11 rule 3).
 */

import { describe, it, expect } from "vitest";
import { parseActionReading } from "../actionReading";
import { parseCleanupSize, parseSizeToMB } from "../cleanupSize";

describe("size readings", () => {
  it("reads the measured size a cleanup scan reported", () => {
    expect(parseActionReading("ready|4096 MB")).toEqual({
      kind: "size",
      size: "4096 MB",
    });
  });

  it("keeps the two states a size can be in besides a number", () => {
    expect(parseActionReading("ready|calculating")).toEqual({
      kind: "size",
      size: "calculating",
    });
    expect(parseActionReading("ready|unavailable")).toEqual({
      kind: "size",
      size: "unavailable",
    });
  });

  it("preserves whatever the backend qualified the size with", () => {
    // `system:dism_cleanup` reports which component store the bytes are in.
    expect(parseActionReading("ready|1234 MB (WinSxS)")).toEqual({
      kind: "size",
      size: "1234 MB (WinSxS)",
    });
  });
});

describe("TRIM readings — the ones that were being shown as sizes", () => {
  it("reads a volume that has never been retrimmed", () => {
    expect(parseActionReading("overdue|never")).toEqual({
      kind: "overdue",
      detail: "never",
    });
  });

  it("reads how long a retrim has been overdue", () => {
    expect(parseActionReading("overdue|23 days")).toEqual({
      kind: "overdue",
      detail: { days: 23 },
    });
  });

  it("reads the age of the oldest retrim when every volume is current", () => {
    expect(parseActionReading("ok|3 days")).toEqual({ kind: "ok", days: 3 });
  });

  it("reads the retrim that has just run", () => {
    // What the `applied` event carries back the moment the action succeeds.
    expect(parseActionReading("ok|0 days")).toEqual({ kind: "ok", days: 0 });
  });

  it("reads the singular day the backend still spells as plural", () => {
    expect(parseActionReading("ok|1 days")).toEqual({ kind: "ok", days: 1 });
    expect(parseActionReading("ok|1 day")).toEqual({ kind: "ok", days: 1 });
  });

  it("never presents a TRIM date as an amount of disk space", () => {
    // The whole defect, pinned: these two used to reach the size badge.
    for (const value of ["overdue|never", "overdue|23 days", "ok|3 days"]) {
      expect(parseActionReading(value)?.kind).not.toBe("size");
    }
  });
});

describe("what the parser refuses to guess", () => {
  it("has no reading for a value that is not a string", () => {
    expect(parseActionReading(null)).toBeNull();
    expect(parseActionReading(undefined)).toBeNull();
    expect(parseActionReading(42)).toBeNull();
    expect(parseActionReading(false)).toBeNull();
  });

  it("has no reading for a value with no kind at all", () => {
    expect(parseActionReading("")).toBeNull();
    expect(parseActionReading("4096 MB")).toBeNull();
    expect(parseActionReading("ready|")).toBeNull();
  });

  it("refuses an overdue payload it cannot account for, rather than assuming", () => {
    // "never run" is a statement about this machine. A payload nobody could
    // read is not evidence for it.
    expect(parseActionReading("overdue|")).toBeNull();
    expect(parseActionReading("overdue|soon")).toBeNull();
    expect(parseActionReading("ok|recently")).toBeNull();
  });

  it("tolerates the spacing and case a shell may put around the reading", () => {
    expect(parseActionReading("  ok|3 days  ")).toEqual({
      kind: "ok",
      days: 3,
    });
    expect(parseActionReading("Overdue|Never")).toEqual({
      kind: "overdue",
      detail: "never",
    });
  });
});

describe("the size helpers are unchanged", () => {
  it("still reads a cleanup size exactly as before", () => {
    expect(parseCleanupSize("ready|4096 MB")).toBe("4096 MB");
    expect(parseSizeToMB("ready|2 GB")).toBe(2048);
    expect(parseSizeToMB("ready|calculating")).toBeNull();
  });

  it("counts no megabytes towards a TRIM reading", () => {
    // Home totals reclaimable space with this; a day count must never join in.
    expect(parseSizeToMB("overdue|23 days")).toBeNull();
    expect(parseSizeToMB("ok|3 days")).toBeNull();
  });
});

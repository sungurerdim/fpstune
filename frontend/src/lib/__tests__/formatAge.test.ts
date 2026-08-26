/**
 * A headroom reading's date is the only thing separating "this machine reaches
 * 57 fps" from "this machine reached 57 fps before you changed anything", and
 * the product spends that number on a real decision — whether raising image
 * quality is a tweak or a way of lowering the ceiling.
 *
 * There were two `formatAge` functions: a day-grained one in `lib/` with seven
 * tests and no importer, and this minute-grained one inlined in HeadroomPanel
 * with no tests at all. The tested one was not the shipped one, so the suite
 * proved nothing. This is the shipped one, and these pin the two edges that
 * would print a lie: a backend clock ahead of the browser's must not render
 * "-2 min ago", and an unmeasured game must not render "NaN min ago".
 */

import { describe, it, expect } from "vitest";
import { formatAge } from "../formatAge";

/** Epoch seconds, matching GameHeadroom.measured_at. */
const NOW_MS = Date.parse("2026-08-25T12:00:00Z");
const secondsBefore = (seconds: number) => NOW_MS / 1000 - seconds;

describe("formatAge", () => {
  it("says just now inside the first ninety seconds", () => {
    expect(formatAge(secondsBefore(0), NOW_MS)).toBe("just now");
    expect(formatAge(secondsBefore(89), NOW_MS)).toBe("just now");
  });

  it("counts minutes once the reading is older than that", () => {
    expect(formatAge(secondsBefore(90), NOW_MS)).toBe("2 min ago");
    expect(formatAge(secondsBefore(12 * 60), NOW_MS)).toBe("12 min ago");
  });

  it("switches to hours at ninety minutes rather than counting past it", () => {
    expect(formatAge(secondsBefore(89 * 60), NOW_MS)).toBe("89 min ago");
    expect(formatAge(secondsBefore(90 * 60), NOW_MS)).toBe("2 h ago");
  });

  it("switches to days at thirty-six hours", () => {
    expect(formatAge(secondsBefore(35 * 3600), NOW_MS)).toBe("35 h ago");
    expect(formatAge(secondsBefore(36 * 3600), NOW_MS)).toBe("2 d ago");
    expect(formatAge(secondsBefore(5 * 24 * 3600), NOW_MS)).toBe("5 d ago");
  });

  it("says just now rather than a negative age when the clocks disagree", () => {
    // The backend stamps `measured_at` from its own clock; the browser reads
    // its own. A few seconds of skew must not surface as "-2 min ago", which
    // reads as a bug in the app rather than in the clock.
    expect(formatAge(secondsBefore(-300), NOW_MS)).toBe("just now");
  });

  it("says nothing rather than NaN for a game that was never measured", () => {
    expect(formatAge(null, NOW_MS)).toBe("");
  });
});

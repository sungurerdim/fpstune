/**
 * E4: the window is whatever the friend's browser is.
 *
 * jsdom performs no layout — every element measures 0×0 — so "renders at
 * 1024/1920/3440 without overflow" cannot be asserted here (V4; the
 * browser-level check lives with E7's axe run). What CAN be pinned is the
 * property that made ultrawide a 1280px column of small type: a hard width
 * cap with no wide-screen override, and zero `2xl:` utilities anywhere.
 */

import { describe, it, expect } from "vitest";

const SOURCES = import.meta.glob("../**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

function shipped(): Array<[string, string]> {
  return Object.entries(SOURCES).filter(
    ([path]) =>
      !path.includes(".test.") &&
      !path.includes("__tests__/") &&
      !path.includes("/test/"),
  );
}

describe("E4: responsiveness", () => {
  it("every width cap carries a wide-screen override", () => {
    // max-w-7xl alone froze a 3440px display at a 1280px column. A cap is
    // fine as the *base*; what is forbidden is a cap with no 2xl: escape.
    const uncapped: string[] = [];
    for (const [path, source] of shipped()) {
      for (const line of source.split("\n")) {
        if (line.includes("max-w-7xl") && !line.includes("2xl:max-w")) {
          uncapped.push(`${path}: ${line.trim().slice(0, 80)}`);
        }
      }
    }
    expect(
      uncapped,
      `width caps with no 2xl: override: ${uncapped.join("; ")}`,
    ).toEqual([]);
  });

  it("wide screens gain information, not whitespace", () => {
    // The mechanical trace of the claim: at least one layout changes shape
    // at 2xl. Before E4 the whole app contained zero 2xl: utilities.
    const uses2xl = shipped().some(([, source]) => source.includes("2xl:"));
    expect(uses2xl).toBe(true);
  });
});

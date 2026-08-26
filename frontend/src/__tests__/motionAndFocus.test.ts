/**
 * E7's mechanical half: one focus convention, motion as a preference.
 *
 * The contrast rule lives in e2e/a11y.spec.ts (real browser — jsdom computes
 * no styles). What CAN be pinned here: index.css owns the single
 * :focus-visible rule and the prefers-reduced-motion escape, and no
 * component carries its own focus: utility — three ring recipes on 8 of 48
 * buttons is the decay this forbids.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it, expect } from "vitest";

const SOURCES = import.meta.glob("../**/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const indexCss = readFileSync(join(__dirname, "..", "index.css"), "utf8");

describe("E7: motion and focus conventions", () => {
  it("index.css owns the one focus rule and the reduced-motion escape", () => {
    expect(indexCss).toContain(":focus-visible");
    expect(indexCss).toContain("prefers-reduced-motion: reduce");
  });

  it("no component spells its own focus style", () => {
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(SOURCES)) {
      if (path.includes(".test.") || path.includes("__tests__/")) continue;
      if (/\b(?:focus|focus-visible):(?:ring|outline)/.test(source)) {
        offenders.push(path);
      }
    }
    expect(
      offenders,
      `components with ad-hoc focus styles — the global :focus-visible rule ` +
        `is the convention: ${offenders.join(", ")}`,
    ).toEqual([]);
  });
});

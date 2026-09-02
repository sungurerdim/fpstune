/**
 * The Turkish copy is held to the same shape as the English (C3).
 *
 * The backend gate `tests/test_quality_gates.py::TestC3TooltipCopy` caps the
 * English registry: a description is one or two sentences and at most 200
 * characters, an `effect` is one short phrase of at most 120 with no trailing
 * period. Turkish is what a Turkish user actually reads, so the same caps hold
 * here — otherwise the locale a user sees is the one nothing checks.
 */

import { describe, it, expect } from "vitest";
import { settingsTr } from "../settingsTr";

const DESCRIPTION_MAX_CHARS = 200;
const DESCRIPTION_MAX_SENTENCES = 2;
const EFFECT_MAX_CHARS = 120;

/** A terminator followed by a capital or the end; "2,5 Gbps" does not split. */
function sentences(text: string): number {
  return (text.trim().match(/[.!?](?=\s+[A-ZÇĞİÖŞÜ"(]|$)/g) ?? []).length;
}

const entries = Object.entries(settingsTr);

describe("the Turkish catalogue keeps the copy rules the English one does", () => {
  it("has entries to check", () => {
    expect(entries.length).toBeGreaterThan(100);
  });

  it("keeps every description to one or two sentences ending in a period", () => {
    // An empty Turkish description is deliberate and documented in
    // `i18n/settings.ts`: a machine-derived description (a panel's refresh
    // ceiling, a VRAM budget) is composed per machine by the backend, so a
    // static translation would freeze one machine's numbers into source (C9).
    // Empty falls through to the English, machine-correct text.
    const offenders = entries
      .filter(([, v]) => v.description.trim())
      .filter(
        ([, v]) =>
          !v.description.trimEnd().endsWith(".") ||
          sentences(v.description) > DESCRIPTION_MAX_SENTENCES,
      )
      .map(([id]) => id);
    expect(offenders).toEqual([]);
  });

  it("keeps every description inside a tooltip", () => {
    const offenders = entries
      .filter(([, v]) => v.description.length > DESCRIPTION_MAX_CHARS)
      .map(([id, v]) => `${id} (${v.description.length})`);
    expect(offenders).toEqual([]);
  });

  it("keeps every effect one short phrase with no trailing period", () => {
    const offenders = entries
      .filter(
        ([, v]) =>
          v.effect !== undefined &&
          (v.effect.length > EFFECT_MAX_CHARS ||
            v.effect.trimEnd().endsWith(".")),
      )
      .map(([id, v]) => `${id} (${v.effect?.length})`);
    expect(offenders).toEqual([]);
  });

  it("never leaves a name empty, which would render as a blank row", () => {
    // Only the name: a row leads with it and has no English to fall back to
    // that would still be right, whereas an absent description deliberately
    // falls through (see above).
    const offenders = entries
      .filter(([, v]) => !v.name.trim())
      .map(([id]) => id);
    expect(offenders).toEqual([]);
  });
});

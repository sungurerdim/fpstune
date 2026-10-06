/**
 * A state or value label is read in a row, next to another label and an arrow.
 *
 * `tests/test_quality_gates.py::TestC3TooltipCopy` caps what a *description*
 * and an *effect* may run to; nothing capped the short words a row prints for a
 * state, so "Bağdaştırıcının en yükseğinin altında" (37 characters, the
 * longest) shipped and wrapped a row three ways at narrow widths. The caps
 * below were set on 2026-10-06 from the catalogues' own distribution:
 *
 *  - `choice.*` / `tier.*` (a state or tier name): median 11-13 characters,
 *    longest 27 in English and 29 in Turkish once the 37-character outlier was
 *    shortened. 30 holds all of them and refuses a label that is a phrase.
 *
 * Not capped here: `finding.*`. Those are sentences with placeholders, whose
 * measured distribution is wide (a summary runs 40-167 characters, an advice
 * line up to 144) and which are meant to wrap; their frame is held by the
 * narrow-width rules, not by a length.
 */

import { describe, expect, it } from "vitest";
import { en } from "../en";
import { tr } from "../tr";

const STATE_LABEL_MAX_CHARS = 30;

function over(
  catalogue: Record<string, string>,
  prefixes: string[],
  max: number,
): string[] {
  return Object.entries(catalogue)
    .filter(([key]) => prefixes.some((p) => key.startsWith(p)))
    .filter(([, text]) => text.length > max)
    .map(([key, text]) => `${key} (${text.length}): ${text}`);
}

describe.each([
  ["en", en as Record<string, string>],
  ["tr", tr as Record<string, string>],
])("label length (%s)", (_locale, catalogue) => {
  it("finds the labels it caps", () => {
    // A prefix that matches nothing would pass forever.
    const keys = Object.keys(catalogue);
    expect(keys.filter((k) => k.startsWith("choice.")).length).toBeGreaterThan(10);
  });

  it(`keeps a state or tier name within ${STATE_LABEL_MAX_CHARS} characters`, () => {
    expect(over(catalogue, ["choice.", "tier."], STATE_LABEL_MAX_CHARS)).toEqual([]);
  });
});

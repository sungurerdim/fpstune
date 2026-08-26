/**
 * E9 GATE: token discipline — no raw palette colour, no sub-floor font size.
 *
 * The defect this guards: the app accumulated 47 non-token colours and 32
 * hand-picked sub-12px font sizes, concentrated in exactly the semantics that
 * should be tokens (headroom tiers, verify verdicts, impact chips). A raw
 * `bg-emerald-400` is a decision nobody can change centrally; a `text-[9px]`
 * label is roughly half what an adult reads comfortably.
 *
 * The baseline below froze the violations the E-epic inherited, per file.
 * It may only shrink: a new violation (or one added to a clean file) fails
 * immediately, and a file that improves turns its entry stale — update the
 * count here in the same change, so the shrink is visible in the diff.
 *
 * The copy-pasted-primitive-string half of E9 lands with E2's primitives —
 * a duplication gate needs the canonical spelling to exist first.
 */

import { describe, it, expect } from "vitest";

// Every shipped source file as raw text, resolved by Vite at transform time —
// no fs, no @types/node. Test files are excluded below by path.
const SOURCES = import.meta.glob("../**/*.{ts,tsx}", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

// A hand-picked pixel size below the readable floor. Sizes >= 12 are fine.
const SUB_FLOOR = /text-\[(\d+)px\]/g;

// A Tailwind palette colour used directly instead of a semantic token
// (primary/success/warning/destructive/muted/...). The palette names are
// spelled out so a new token name can never false-positive.
const RAW_COLOUR =
  /(?:bg|text|border|ring|fill|stroke|from|to|via)-(?:red|green|blue|emerald|amber|purple|rose|slate|zinc|gray|neutral|stone|orange|yellow|lime|teal|cyan|sky|indigo|violet|fuchsia|pink)-\d+/g;

// Frozen at the E9 audit (90 violations, 18 files); shrunk to 73/15 by the
// amber→warning conversion and the ConfirmDialog move to primitives.
// Shrink-only. types/setting.ts is the impact-category octet — eight
// semantic hues that want their own tokens, not a mapping onto warning.
const _FROZEN = new Map<string, number>([
  ["components/CleanupListRow.tsx", 1],
  ["components/CleanupPanel.tsx", 1],
  ["components/HeadroomPanel.tsx", 7],
  ["components/HomeTab.tsx", 6],
  ["components/SettingInfoTooltip.tsx", 4],
  ["components/SettingStateDisplay.tsx", 5],
  ["components/SettingsTab.tsx", 2],
  ["components/SuitePanel.tsx", 1],
  ["components/TabNavigation.tsx", 1],
  ["components/TweakListRow.tsx", 2],
  ["components/TweakSetting.tsx", 11],
  ["components/VerifyPanel.tsx", 5],
  ["components/hardware/DeviceTweakList.tsx", 1],
  ["components/ui/PillSelector.tsx", 1],
  ["types/setting.ts", 25],
]);

// The third E9 pattern, live now that E2's primitives exist: a primitive's
// class recipe retyped in a component instead of using the primitive. The
// spellings below are the canonical recipes; ui/ itself is exempt (that is
// where they are allowed to live).
const PRIMITIVE_RECIPES = [
  "bg-card rounded-lg border border-border",
  "bg-primary text-primary-foreground hover:bg-primary/90",
] as const;

// Emptied by the E2 migration: every recipe use outside ui/ now renders the
// primitive. Shrink-only — an entry would only ever be re-added by reverting
// the migration, which the test above already fails.
const _FROZEN_RECIPES = new Map<string, number>([]);

function violationsByFile(): Map<string, number> {
  const found = new Map<string, number>();
  for (const [path, source] of Object.entries(SOURCES)) {
    const file = path.replace(/^\.\.\//, "");
    if (
      file.includes(".test.") ||
      file.includes("__tests__/") ||
      file.startsWith("test/")
    ) {
      continue;
    }
    let count = 0;
    for (const match of source.matchAll(SUB_FLOOR)) {
      if (parseInt(match[1], 10) < 12) count++;
    }
    count += [...source.matchAll(RAW_COLOUR)].length;
    if (count > 0) found.set(file, count);
  }
  return found;
}

function recipeViolationsByFile(): Map<string, number> {
  const found = new Map<string, number>();
  for (const [path, source] of Object.entries(SOURCES)) {
    const file = path.replace(/^\.\.\//, "");
    if (
      file.includes(".test.") ||
      file.includes("__tests__/") ||
      file.startsWith("test/") ||
      file.startsWith("components/ui/")
    ) {
      continue;
    }
    let count = 0;
    for (const recipe of PRIMITIVE_RECIPES) {
      count += source.split(recipe).length - 1;
    }
    if (count > 0) found.set(file, count);
  }
  return found;
}

describe("E9: token discipline", () => {
  const found = violationsByFile();

  it("no file gains a raw colour or sub-floor font size", () => {
    const grown: string[] = [];
    for (const [file, count] of found) {
      const allowed = _FROZEN.get(file) ?? 0;
      if (count > allowed) {
        grown.push(`${file}: ${count} violations (baseline ${allowed})`);
      }
    }
    expect(
      grown,
      "use a semantic token (primary/success/warning/...) and text-xs or " +
        `larger — new raw-palette or sub-floor uses: ${grown.join("; ")}`,
    ).toEqual([]);
  });

  it("the baseline only shrinks", () => {
    const stale: string[] = [];
    for (const [file, allowed] of _FROZEN) {
      const count = found.get(file) ?? 0;
      if (count < allowed) {
        stale.push(`${file}: now ${count}, baseline says ${allowed}`);
      }
    }
    expect(
      stale,
      "files that improved — lower their baseline entries so the shrink is " +
        `on the record: ${stale.join("; ")}`,
    ).toEqual([]);
  });

  const recipes = recipeViolationsByFile();

  it("no file re-spells a primitive's recipe by hand", () => {
    const grown: string[] = [];
    for (const [file, count] of recipes) {
      const allowed = _FROZEN_RECIPES.get(file) ?? 0;
      if (count > allowed) {
        grown.push(`${file}: ${count} (baseline ${allowed})`);
      }
    }
    expect(
      grown,
      "render <Card>/<Button variant=primary> instead of retyping the " +
        `recipe: ${grown.join("; ")}`,
    ).toEqual([]);
  });

  it("the recipe baseline only shrinks", () => {
    const stale: string[] = [];
    for (const [file, allowed] of _FROZEN_RECIPES) {
      const count = recipes.get(file) ?? 0;
      if (count < allowed) {
        stale.push(`${file}: now ${count}, baseline says ${allowed}`);
      }
    }
    expect(stale, `lower these baseline entries: ${stale.join("; ")}`).toEqual(
      [],
    );
  });
});

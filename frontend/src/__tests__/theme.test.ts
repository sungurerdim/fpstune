/**
 * E1: the token layer holds — both themes declare the same variables, and
 * Tailwind's palette reads only variables.
 *
 * The defect each half guards: a variable missing from one theme block
 * silently inherits the other theme's value (a dark-blue card on a white
 * page — the half-themed screen); a literal colour in the palette is
 * invisible to theming and to the E9 gate, which polices components, not the
 * palette. jsdom computes no styles, so "the light theme renders" is pinned
 * here as the property that makes it true: complete, variable-fed palettes.
 *
 * Tailwind 4 moved the palette out of `tailwind.config.js` and into the
 * stylesheet's own `@theme` block, so this reads the CSS for both halves now.
 * The property being asserted did not change with it.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it, expect } from "vitest";

// Read from disk: vitest's css pipeline intercepts .css imports (even with
// the ?raw query), returning an empty module instead of the text.
const indexCss = readFileSync(join(__dirname, "..", "index.css"), "utf8");

function variablesIn(block: string): Set<string> {
  return new Set([...block.matchAll(/--([\w-]+):/g)].map((match) => match[1]));
}

function blockAfter(opening: string): string {
  const start = indexCss.indexOf(opening);
  expect(start, `no ${opening.trim()} block in index.css`).toBeGreaterThan(-1);
  const end = indexCss.indexOf("}", start);
  return indexCss.slice(start, end);
}

/** Every `--color-*` the palette declares, mapped to the value it reads. */
function paletteColors(): Record<string, string> {
  const theme = blockAfter("@theme {");
  const colors: Record<string, string> = {};
  for (const match of theme.matchAll(/--color-([\w-]+):\s*([^;]+);/g)) {
    colors[match[1]] = match[2].trim();
  }
  return colors;
}

describe("E1: the token layer", () => {
  it("light and dark declare the same variable set", () => {
    const light = variablesIn(blockAfter(":root {"));
    const dark = variablesIn(blockAfter(".dark {"));
    expect([...light].sort()).toEqual([...dark].sort());
    expect(light.size).toBeGreaterThan(20);
  });

  it("the palette is not empty, so the checks below mean something", () => {
    // Without this, a rename of the @theme block would make the two assertions
    // that follow pass over nothing at all.
    expect(Object.keys(paletteColors()).length).toBeGreaterThan(20);
  });

  it("every palette colour reads a CSS variable, never a literal", () => {
    const literals = Object.entries(paletteColors())
      .filter(([, value]) => !/^hsl\(var\(--[\w-]+\)\)$/.test(value))
      .map(([name, value]) => `${name}: ${value}`);
    expect(
      literals,
      `palette colours holding literals instead of var(): ${literals.join("; ")}`,
    ).toEqual([]);
  });

  it("every colour the palette names has a variable in both themes", () => {
    const light = variablesIn(blockAfter(":root {"));
    const dark = variablesIn(blockAfter(".dark {"));
    const missing = Object.values(paletteColors())
      .map((value) => /var\(--([\w-]+)\)/.exec(value)?.[1])
      .filter((name): name is string => name !== undefined)
      .filter((name) => !light.has(name) || !dark.has(name));
    expect(missing).toEqual([]);
  });
});

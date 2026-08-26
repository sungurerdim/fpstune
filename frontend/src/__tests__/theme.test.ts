/**
 * E1: the token layer holds — both themes declare the same variables, and
 * Tailwind's palette reads only variables.
 *
 * The defect each half guards: a variable missing from one theme block
 * silently inherits the other theme's value (a dark-blue card on a white
 * page — the half-themed screen); a literal colour in the Tailwind config is
 * invisible to theming and to the E9 gate, which polices components, not the
 * config. jsdom computes no styles, so "the light theme renders" is pinned
 * here as the property that makes it true: complete, variable-fed palettes.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it, expect } from "vitest";
// @ts-expect-error -- the Tailwind config is untyped JS by design
import tailwindConfig from "../../tailwind.config.js";

// Read from disk: vitest's css pipeline intercepts .css imports (even with
// the ?raw query), returning an empty module instead of the text.
const indexCss = readFileSync(join(__dirname, "..", "index.css"), "utf8");

function variablesIn(block: string): Set<string> {
  return new Set(
    [...block.matchAll(/--([\w-]+):/g)].map((match) => match[1]),
  );
}

function themeBlock(selector: string): string {
  const source = indexCss;
  const start = source.indexOf(`${selector} {`);
  expect(start, `no ${selector} block in index.css`).toBeGreaterThan(-1);
  const end = source.indexOf("}", start);
  return source.slice(start, end);
}

describe("E1: the token layer", () => {
  it("light and dark declare the same variable set", () => {
    const light = variablesIn(themeBlock(":root"));
    const dark = variablesIn(themeBlock(".dark"));
    expect([...light].sort()).toEqual([...dark].sort());
    expect(light.size).toBeGreaterThan(20);
  });

  it("every Tailwind colour reads a CSS variable, never a literal", () => {
    const colors = tailwindConfig.theme.extend.colors as Record<string, string>;
    const literals = Object.entries(colors)
      .filter(([, value]) => !/^hsl\(var\(--[\w-]+\)\)$/.test(value))
      .map(([name, value]) => `${name}: ${value}`);
    expect(
      literals,
      `theme colours holding literals instead of var(): ${literals.join("; ")}`,
    ).toEqual([]);
  });

  it("every colour the config names has a variable in both themes", () => {
    const colors = tailwindConfig.theme.extend.colors as Record<string, string>;
    const light = variablesIn(themeBlock(":root"));
    const dark = variablesIn(themeBlock(".dark"));
    const missing = Object.values(colors)
      .map((value) => /var\(--([\w-]+)\)/.exec(value)?.[1])
      .filter((name): name is string => name !== undefined)
      .filter((name) => !light.has(name) || !dark.has(name));
    expect(missing).toEqual([]);
  });
});

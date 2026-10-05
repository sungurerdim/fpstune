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
import { afterEach, describe, it, expect, vi } from "vitest";

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

/**
 * Contrast of one colour on another (WCAG 2.x), from the `H S% L%` triplets the
 * tokens are written in.
 */
function rgbOf(triplet: string): [number, number, number] {
  const [h, sPct, lPct] = triplet.split(/\s+/).map((part) => parseFloat(part));
  const s = sPct / 100;
  const l = lPct / 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const sector = Math.floor(h / 60) % 6;
  const [r, g, b] = [
    [c, x, 0],
    [x, c, 0],
    [0, c, x],
    [0, x, c],
    [x, 0, c],
    [c, 0, x],
  ][sector];
  return [r + m, g + m, b + m];
}

function luminance([r, g, b]: [number, number, number]): number {
  const lin = (u: number) => (u <= 0.03928 ? u / 12.92 : ((u + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(a: [number, number, number], b: [number, number, number]): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (hi + 0.05) / (lo + 0.05);
}

/** `fg` laid over `bg` at `alpha`: what a `bg-tone/20` chip actually paints. */
function tint(fg: [number, number, number], bg: [number, number, number], alpha: number) {
  return fg.map((channel, i) => channel * alpha + bg[i] * (1 - alpha)) as [number, number, number];
}

const AA = 4.5;
const themes = {
  light: variablesWithValues(blockAfter(":root {")),
  dark: variablesWithValues(blockAfter(".dark {")),
};

function variablesWithValues(block: string): Record<string, string> {
  return Object.fromEntries(
    [...block.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]),
  );
}

describe.each(Object.entries(themes))("every text token is legible in the %s theme (WCAG AA)", (_name, tokens) => {
  const surfaces = ["background", "card", "card-elevated"] as const;

  it("body text on every surface", () => {
    for (const text of ["foreground", "card-foreground", "popover-foreground"]) {
      for (const surface of [...surfaces, "popover", "muted", "secondary"]) {
        expect(
          contrast(rgbOf(tokens[text]), rgbOf(tokens[surface])),
          `${text} on ${surface}`,
        ).toBeGreaterThanOrEqual(AA);
      }
    }
  });

  it("secondary text on the surfaces it is drawn on, muted fills included", () => {
    for (const surface of [...surfaces, "muted", "secondary", "accent"]) {
      expect(
        contrast(rgbOf(tokens["muted-foreground"]), rgbOf(tokens[surface])),
        `muted-foreground on ${surface}`,
      ).toBeGreaterThanOrEqual(AA);
    }
    expect(contrast(rgbOf(tokens["secondary-foreground"]), rgbOf(tokens.secondary))).toBeGreaterThanOrEqual(AA);
    expect(contrast(rgbOf(tokens["accent-foreground"]), rgbOf(tokens.accent))).toBeGreaterThanOrEqual(AA);
  });

  it("status and domain colours as text, bare and on their own 20% chip tint", () => {
    const tones = [
      "primary",
      "success",
      "warning",
      "destructive",
      "score-low",
      "score-mid",
      "score-high",
      "domain-hardware",
      "domain-software",
      "domain-game",
    ];
    for (const tone of tones) {
      const colour = rgbOf(tokens[tone]);
      for (const surface of surfaces) {
        expect(contrast(colour, rgbOf(tokens[surface])), `${tone} on ${surface}`).toBeGreaterThanOrEqual(AA);
      }
      expect(
        contrast(colour, tint(colour, rgbOf(tokens.card), 0.2)),
        `${tone} on its 20% chip over a card`,
      ).toBeGreaterThanOrEqual(AA);
    }
  });

  it("the text a filled button or badge carries, on its own fill", () => {
    for (const [text, fill] of [
      ["primary-foreground", "primary"],
      ["destructive-foreground", "destructive"],
      ["warning-foreground", "warning"],
    ]) {
      expect(contrast(rgbOf(tokens[text]), rgbOf(tokens[fill])), `${text} on ${fill}`).toBeGreaterThanOrEqual(AA);
    }
  });
});

describe("the colour scheme follows the theme", () => {
  it("tells the browser which scheme each theme is, for scrollbars and form controls", () => {
    expect(blockAfter(":root {")).toMatch(/color-scheme:\s*light/);
    expect(blockAfter(".dark {")).toMatch(/color-scheme:\s*dark/);
  });
});

/**
 * The first-paint script in index.html, run for real. A dark theme painted
 * after a light flash is the failure; so is a default that follows the OS when
 * the product decided light.
 */
describe("index.html applies the theme before first paint", () => {
  const html = readFileSync(join(__dirname, "..", "..", "index.html"), "utf8");
  const script = /<script>([\s\S]*?)<\/script>/.exec(html)?.[1] ?? "";

  function runScript(stored: string | null, osPrefersDark = false) {
    const storage = {
      getItem: (key: string) => (key === "fpstune-theme" ? stored : null),
    };
    vi.stubGlobal("localStorage", storage);
    vi.stubGlobal(
      "matchMedia",
      (query: string) => ({ matches: osPrefersDark && query.includes("dark") }),
    );
    document.documentElement.className = "";
    document.documentElement.style.colorScheme = "";
    new Function(script)();
    return document.documentElement;
  }

  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.className = "";
    document.documentElement.style.colorScheme = "";
  });

  it("finds the script", () => {
    expect(script).toContain("fpstune-theme");
  });

  it("does not ship the page dark: the markup carries no theme class of its own", () => {
    expect(html).not.toMatch(/<html[^>]*class=/);
  });

  it("is light with nothing stored, even when the OS prefers dark", () => {
    const root = runScript(null, true);
    expect(root.classList.contains("dark")).toBe(false);
    expect(root.style.colorScheme).toBe("light");
  });

  it("is dark only when the user chose dark", () => {
    const root = runScript("dark");
    expect(root.classList.contains("dark")).toBe(true);
    expect(root.style.colorScheme).toBe("dark");
  });

  it("is light for an explicit light choice, even when the OS prefers dark", () => {
    expect(runScript("light", true).classList.contains("dark")).toBe(false);
  });

  it("falls back to light when storage is blocked", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
    });
    document.documentElement.className = "";
    new Function(script)();
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});

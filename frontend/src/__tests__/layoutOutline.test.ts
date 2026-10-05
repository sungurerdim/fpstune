/**
 * The layout snapshots are only as honest as the helper that resolves widths.
 *
 * A resolver that ignored a breakpoint, or let `hover:` count as a layout, would
 * make every page snapshot agree with itself while describing a layout nobody
 * gets. Each case here names the way that would go wrong.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it, expect } from "vitest";
import { BREAKPOINTS_PX, layoutOutline, resolveLayout, setViewport } from "../test/layoutOutline";

// Read from disk: the test runner turns a stylesheet import into an empty module.
const STYLES = readFileSync(resolve(process.cwd(), "src/index.css"), "utf-8");

describe("resolveLayout", () => {
  const cols = "grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3";

  it("keeps the base utility below every breakpoint", () => {
    expect(resolveLayout(cols, 390)["grid-cols"]).toBe("grid-cols-1");
  });

  it("applies a breakpoint exactly at its min-width, not one pixel before", () => {
    expect(resolveLayout(cols, 1023)["grid-cols"]).toBe("grid-cols-1");
    expect(resolveLayout(cols, 1024)["grid-cols"]).toBe("grid-cols-2");
  });

  it("lets the widest matching breakpoint win whatever order the classes are written in", () => {
    expect(resolveLayout("2xl:grid-cols-3 grid-cols-1 lg:grid-cols-2", 2560)["grid-cols"]).toBe(
      "grid-cols-3",
    );
  });

  it("ignores state variants, which describe a pointer and not a window", () => {
    expect(resolveLayout("grid-cols-1 hover:grid-cols-4 focus-visible:grid-cols-5", 2560)).toEqual({
      "grid-cols": "grid-cols-1",
    });
  });

  it("reports an element that is hidden below a breakpoint and shown above it", () => {
    expect(resolveLayout("hidden lg:flex", 390).display).toBe("hidden");
    expect(resolveLayout("hidden lg:flex", 1280).display).toBe("flex");
  });

  it("resolves the arbitrary-value columns the benchmarks page uses", () => {
    const tpl = "grid-cols-1 2xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]";
    expect(resolveLayout(tpl, 1920)["grid-cols"]).toBe("grid-cols-[minmax(0,2fr)_minmax(0,1fr)]");
  });
});

describe("layoutOutline", () => {
  it("nests a column grid under the landmark that holds it and shows the width", () => {
    document.body.innerHTML =
      '<section data-testid="page"><div data-testid="rows" class="grid grid-cols-1 xl:grid-cols-2"></div></section>';

    expect(layoutOutline(document.body, 1280)).toBe(
      ["viewport 1280px", "section#page", "  div#rows [grid-cols-2]"].join("\n"),
    );
    expect(layoutOutline(document.body, 390)).toContain("div#rows [grid-cols-1]");
  });
});

describe("the breakpoint table", () => {
  it("matches the 3xl breakpoint the app declares in index.css", () => {
    const declared = /--breakpoint-3xl:\s*([\d.]+)rem/.exec(STYLES);
    expect(declared, "index.css declares --breakpoint-3xl in rem").not.toBeNull();
    const px = Number(declared![1]) * 16;
    expect(BREAKPOINTS_PX.find(([name]) => name === "3xl")?.[1]).toBe(px);
  });
});

describe("setViewport", () => {
  it("answers min-width queries the way a browser at that width would", () => {
    setViewport(1280);
    expect(window.innerWidth).toBe(1280);
    expect(window.matchMedia("(min-width: 1024px)").matches).toBe(true);
    expect(window.matchMedia("(min-width: 1536px)").matches).toBe(false);
    expect(window.matchMedia("(max-width: 1279px)").matches).toBe(false);
  });
});

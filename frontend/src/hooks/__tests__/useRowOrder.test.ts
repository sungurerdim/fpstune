import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { useRowOrder } from "../useRowOrder";
import type { Setting } from "../../types/setting";

const row = (id: string, over: Partial<Setting> = {}) =>
  ({
    id,
    displayName: id,
    categoryOrder: 0,
    currentValue: "on",
    isOptimized: false,
    ...over,
  }) as Setting;

const order = (compare: (a: Setting, b: Setting) => number, rows: Setting[]) =>
  [...rows].sort(compare).map((s) => s.id);

describe("useRowOrder", () => {
  it("lists what is not optimized first, whatever order it arrived in", () => {
    const rows = [row("a", { isOptimized: true }), row("b"), row("c", { isOptimized: true }), row("d")];
    const { result } = renderHook(() => useRowOrder(rows));

    expect(order(result.current, rows)).toEqual(["b", "d", "a", "c"]);
  });

  it("keeps a row where it was after applying it, so the next click lands on the same row", () => {
    const before = [row("a"), row("b"), row("c")];
    const { result, rerender } = renderHook(({ rows }) => useRowOrder(rows), {
      initialProps: { rows: before },
    });
    expect(order(result.current, before)).toEqual(["a", "b", "c"]);

    // "a" is applied: the backend now says it is optimized.
    const after = [row("a", { isOptimized: true }), row("b"), row("c")];
    rerender({ rows: after });

    expect(order(result.current, after)).toEqual(["a", "b", "c"]);
  });

  it("places a row read later by its verdict at that moment, and rows still unread last", () => {
    const loading = (id: string) => row(id, { currentValue: null });
    const first = [row("a", { isOptimized: true }), loading("late")];
    const { result, rerender } = renderHook(({ rows }) => useRowOrder(rows), {
      initialProps: { rows: first },
    });
    expect(order(result.current, first)).toEqual(["a", "late"]);

    const second = [row("a", { isOptimized: true }), row("late")];
    rerender({ rows: second });

    expect(order(result.current, second)).toEqual(["late", "a"]);
  });

  it("breaks ties by the backend's own order, then by name", () => {
    const rows = [
      row("z", { categoryOrder: 1, displayName: "Zeta" }),
      row("m", { categoryOrder: 0, displayName: "Mu" }),
      row("a", { categoryOrder: 0, displayName: "Alpha" }),
    ];
    const { result } = renderHook(() => useRowOrder(rows));

    expect(order(result.current, rows)).toEqual(["a", "m", "z"]);
  });
});

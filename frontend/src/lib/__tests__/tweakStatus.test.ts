import { describe, it, expect } from "vitest";
import { isOptimizeRow, isTweakManual, tweakCounts } from "../tweakStatus";
import type { Setting } from "../../types/setting";

const tweak = (over: Partial<Setting> = {}) =>
  ({
    isApplicable: true,
    isAction: false,
    isReadonly: false,
    currentValue: "on",
    status: "suboptimal",
    isOptimized: false,
    ...over,
  }) as Setting;

describe("tweakCounts", () => {
  it("counts the backend's verdict, and only over tweaks that were read", () => {
    const counts = tweakCounts([
      tweak(),
      tweak(),
      tweak({ isOptimized: true, status: "optimal" }),
    ]);

    expect(counts).toEqual({ total: 3, notOptimized: 2, reading: 0 });
  });

  it("leaves out what is not a tweak to optimize: advisories, actions, absent settings", () => {
    const counts = tweakCounts([
      tweak(),
      tweak({ isReadonly: true }),
      tweak({ isAction: true }),
      tweak({ isApplicable: false }),
    ]);

    expect(counts).toEqual({ total: 1, notOptimized: 1, reading: 0 });
  });

  it("keeps a setting still being read out of both numbers and says it is reading", () => {
    const counts = tweakCounts([tweak(), tweak({ status: "loading", currentValue: null })]);

    expect(counts).toEqual({ total: 1, notOptimized: 1, reading: 1 });
  });

  it("does not recompute the verdict from the values", () => {
    const counts = tweakCounts([tweak({ isOptimized: true, currentValue: "on" })]);

    expect(counts.notOptimized).toBe(0);
  });
});

describe("isOptimizeRow", () => {
  it("lists a read setting and one being read, never an empty read or an action", () => {
    expect(isOptimizeRow(tweak())).toBe(true);
    expect(isOptimizeRow(tweak({ currentValue: null, status: "loading" }))).toBe(true);
    expect(isOptimizeRow(tweak({ currentValue: null, status: "default" }))).toBe(false);
    expect(isOptimizeRow(tweak({ isAction: true }))).toBe(false);
    expect(isOptimizeRow(tweak({ isApplicable: false }))).toBe(false);
  });

  it("keeps a read-only row whose check read nothing: a silent detector must not look unwired", () => {
    expect(isOptimizeRow(tweak({ isReadonly: true, currentValue: null, status: "default" }))).toBe(true);
  });
});

describe("isTweakManual", () => {
  it("is every applicable read-only row: a finding, a check that passed, one that read nothing", () => {
    expect(isTweakManual(tweak({ isReadonly: true }))).toBe(true);
    expect(isTweakManual(tweak({ isReadonly: true, isOptimized: true, status: "optimal" }))).toBe(true);
    expect(isTweakManual(tweak({ isReadonly: true, currentValue: null }))).toBe(true);
  });

  it("is not a writable setting, a cleanup, or something absent from this machine", () => {
    expect(isTweakManual(tweak())).toBe(false);
    expect(isTweakManual(tweak({ isReadonly: true, isAction: true }))).toBe(false);
    expect(isTweakManual(tweak({ isReadonly: true, isApplicable: false }))).toBe(false);
  });
});

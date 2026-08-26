/**
 * Tests for useImpactSummary hook.
 *
 * Most of this file used to assert the shape of a headline that summed every
 * setting's claimed fps into one figure. That figure is gone — see
 * `lib/impact.ts` — so what is left checks the counts, and one test at the
 * bottom makes sure the sum cannot come back.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useStore } from "../../store";
import { useImpactSummary } from "../useImpactSummary";
import type { Setting } from "../../types/setting";

function makeSetting(overrides: Partial<Setting>): Setting {
  return {
    id: "timer:hpet" as `${string}:${string}`,
    module: "timer",
    name: "hpet",
    displayName: "HPET",
    description: "High Precision Event Timer. Controls system timer source.",
    category: "core",
    valueType: "choice",
    choices: ["enabled", "disabled"],
    defaultValue: "enabled",
    recommendedValue: "disabled",
    requiresReboot: true,
    isAction: false,
    scope: "essential",
    currentImpact: "Enabled: higher latency",
    recommendedImpact: "Disabled: lower latency",
    categoryOrder: 0,
    riskLevel: "low",
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "enabled",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    impactCategories: [],
    ...overrides,
  };
}

describe("useImpactSummary", () => {
  beforeEach(() => {
    useStore.setState({
      settings: new Map(),
      _settingsVersion: 0,
    });
  });

  it("returns zero scores when no settings exist", () => {
    const { result } = renderHook(() => useImpactSummary());
    expect(result.current.score.total).toBe(0);
    expect(result.current.score.optimized).toBe(0);
    expect(result.current.score.percentage).toBe(0);
    expect(result.current.potential.latencyTweaks).toBe(0);
    expect(result.current.gained.count).toBe(0);
  });

  it("counts scorable settings (applicable, not action, detected, not readonly)", () => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set("timer:hpet", makeSetting({ id: "timer:hpet" }));
    // action setting — should NOT be scored
    settings.set(
      "cleanup:temp",
      makeSetting({
        id: "cleanup:temp",
        module: "cleanup",
        name: "temp",
        isAction: true,
        currentValue: "ready|500 MB",
      }),
    );
    // not applicable — should NOT be scored
    settings.set(
      "gpu:nvcp",
      makeSetting({
        id: "gpu:nvcp",
        module: "gpu",
        name: "nvcp",
        isApplicable: false,
        currentValue: null,
      }),
    );
    useStore.setState({ settings, _settingsVersion: 1 });

    const { result } = renderHook(() => useImpactSummary());
    // Only "timer:hpet" is scorable (applicable, not action, has currentValue, not readonly)
    expect(result.current.score.total).toBe(1);
    expect(result.current.score.optimized).toBe(0);
    expect(result.current.score.percentage).toBe(0);
  });

  it("counts optimized settings correctly", () => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set(
      "timer:hpet",
      makeSetting({
        id: "timer:hpet",
        currentValue: "disabled",
        isOptimized: true,
        status: "optimal",
      }),
    );
    settings.set(
      "power:usb",
      makeSetting({
        id: "power:usb",
        module: "power",
        name: "usb",
        currentValue: "enabled",
        isOptimized: false,
        status: "suboptimal",
      }),
    );
    useStore.setState({ settings, _settingsVersion: 1 });

    const { result } = renderHook(() => useImpactSummary());
    expect(result.current.score.total).toBe(2);
    expect(result.current.score.optimized).toBe(1);
    expect(result.current.score.percentage).toBe(50);
  });

  it("counts an fps claim without turning it into a number", () => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set(
      "timer:hpet",
      makeSetting({
        id: "timer:hpet",
        currentValue: "enabled",
        isOptimized: false,
        impactScores: { fps: "+3-5%" },
      }),
    );
    useStore.setState({ settings, _settingsVersion: 1 });

    const { result } = renderHook(() => useImpactSummary());

    // The setting is scored — it is a real tweak sitting at the wrong value —
    // and its "+3-5%" produces no headline figure, because a claim is not a
    // measurement and a total of claims is not one either.
    expect(result.current.score.total).toBe(1);
    expect(result.current.score.optimized).toBe(0);
    expect(result.current.potential.latencyTweaks).toBe(0);
    expect(result.current.potential.ramTweaks).toBe(0);
    expect("fpsGain" in result.current.potential).toBe(false);
  });

  it("computes fps gained from optimized settings", () => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set(
      "timer:hpet",
      makeSetting({
        id: "timer:hpet",
        currentValue: "disabled",
        isOptimized: true,
        status: "optimal",
        impactScores: { fps: "+5%" },
      }),
    );
    useStore.setState({ settings, _settingsVersion: 1 });

    const { result } = renderHook(() => useImpactSummary());
    expect(result.current.gained.count).toBe(1);
    // No suboptimal settings → potential fps is "+0%"
  });

  it("counts latency-affecting tweaks instead of summing their milliseconds", () => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set(
      "network:nagle",
      makeSetting({
        id: "network:nagle",
        module: "network",
        name: "nagle",
        currentValue: "enabled",
        isOptimized: false,
        impactScores: { latency_ms: -15 },
      }),
    );
    useStore.setState({ settings, _settingsVersion: 1 });

    const { result } = renderHook(() => useImpactSummary());
    // Summing latency_ms across unrelated subsystems produced "-683ms" on a real
    // machine — DNS lookup time, mouse polling and timer resolution are different
    // clocks and cannot be added. The headline reports how many tweaks have a
    // latency effect; the millisecond figure stays on the row that owns it.
    expect(result.current.potential.latencyTweaks).toBe(1);
  });

  it("surfaces ram_saved from suboptimal settings", () => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set(
      "system:svch",
      makeSetting({
        id: "system:svch",
        module: "system",
        name: "svch",
        currentValue: "default",
        isOptimized: false,
        impactScores: { ram_saved: "50-150MB" },
      }),
    );
    useStore.setState({ settings, _settingsVersion: 1 });

    const { result } = renderHook(() => useImpactSummary());

    // A count, not the first row's string shown as though it were the total.
    expect(result.current.potential.ramTweaks).toBe(1);
  });

  it("ignores readonly settings from scoring", () => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set(
      "timer:hpet",
      makeSetting({
        id: "timer:hpet",
        isReadonly: true,
        currentValue: "enabled",
      }),
    );
    useStore.setState({ settings, _settingsVersion: 1 });

    const { result } = renderHook(() => useImpactSummary());
    expect(result.current.score.total).toBe(0);
  });

  it("recomputes when settingsVersion changes", () => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set("timer:hpet", makeSetting({ id: "timer:hpet" }));
    useStore.setState({ settings, _settingsVersion: 0 });

    const { result, rerender } = renderHook(() => useImpactSummary());
    expect(result.current.score.total).toBe(1);

    // Add another setting by bumping version (mimics store mutation)
    const settings2 = new Map(settings);
    settings2.set(
      "power:usb",
      makeSetting({
        id: "power:usb",
        module: "power",
        name: "usb",
        currentValue: "enabled",
      }),
    );
    useStore.setState({ settings: settings2, _settingsVersion: 1 });
    rerender();

    expect(result.current.score.total).toBe(2);
  });
});

describe("useImpactSummary — settings that recommend the factory default", () => {
  beforeEach(() => {
    useStore.setState({ settings: new Map(), _settingsVersion: 0 });
  });

  it("does not credit a gain the machine was born with", () => {
    // 54 shipped settings recommend exactly what Windows/the game already sets.
    // They are drift guards, so they stay — but "GAINED +N% FPS" from one is a
    // benefit measured against a state the machine is never in.
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set(
      "network:tcp_auto_tuning",
      makeSetting({
        id: "network:tcp_auto_tuning",
        module: "network",
        name: "tcp_auto_tuning",
        defaultValue: "normal",
        recommendedValue: "normal",
        currentValue: "normal",
        isOptimized: true,
        status: "optimal",
        impactScores: { fps: "+10-20%", latency_ms: -30 },
      }),
    );
    useStore.setState({ settings, _settingsVersion: 1 });

    const { result } = renderHook(() => useImpactSummary());
    // Still scored — "this is at its ideal value" is true and worth showing.
    expect(result.current.score.optimized).toBe(1);
    expect(result.current.score.total).toBe(1);
    // But nothing was gained.
    expect(result.current.gained.count).toBe(0);
    expect(result.current.gained.latencyTweaks).toBe(0);
  });

  it("still credits a gain when the recommendation differs from the default", () => {
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set(
      "timer:hpet",
      makeSetting({
        id: "timer:hpet",
        defaultValue: "enabled",
        recommendedValue: "disabled",
        currentValue: "disabled",
        isOptimized: true,
        status: "optimal",
        impactScores: { fps: "+10-20%", latency_ms: -30 },
      }),
    );
    useStore.setState({ settings, _settingsVersion: 1 });

    const { result } = renderHook(() => useImpactSummary());
    expect(result.current.gained.count).toBe(1);
    expect(result.current.gained.latencyTweaks).toBe(1);
  });

  it("still counts a drifted factory-default setting as potential", () => {
    // The whole reason these settings exist: the machine moved off the default
    // and putting it back is a real recovery.
    const settings = new Map<`${string}:${string}`, Setting>();
    settings.set(
      "network:tcp_auto_tuning",
      makeSetting({
        id: "network:tcp_auto_tuning",
        module: "network",
        name: "tcp_auto_tuning",
        defaultValue: "normal",
        recommendedValue: "normal",
        currentValue: "disabled",
        isOptimized: false,
        status: "suboptimal",
        impactScores: { fps: "+10-20%", latency_ms: -30 },
      }),
    );
    useStore.setState({ settings, _settingsVersion: 1 });

    const { result } = renderHook(() => useImpactSummary());
    expect(result.current.potential.latencyTweaks).toBe(1);
  });
});

describe("the summed-claim headline cannot come back", () => {
  /**
   * C11 rule 1, bound to a test rather than to a comment.
   *
   * The home screen once read "Gained +28-45% FPS". Nothing measured it: every
   * setting's claimed fps midpoint was summed under an invented decay curve and
   * spread across an invented range. The machine it rendered on was measuring
   * 19% of its own frame-rate target at the time.
   *
   * It was the third time the same mistake shipped — after the summed "-683ms"
   * latency and `dns_security`'s invented "-12 ms" — and the first two were
   * each fixed in isolation, which is exactly why there is a test now.
   */
  beforeEach(() => {
    useStore.setState({ settings: new Map(), _settingsVersion: 0 });
  });

  function withFpsClaims(claims: string[]) {
    const settings = new Map<`${string}:${string}`, Setting>();
    claims.forEach((fps, index) => {
      const id = `system:claim${index}` as `${string}:${string}`;
      settings.set(
        id,
        makeSetting({
          id,
          module: "system",
          name: `claim${index}`,
          isOptimized: true,
          currentValue: "disabled",
          defaultValue: "enabled",
          recommendedValue: "disabled",
          impactScores: { fps: fps },
        }),
      );
    });
    useStore.setState({ settings, _settingsVersion: 1 });
  }

  it("reports no gain figure however many settings claim one", () => {
    withFpsClaims(["+3-5%", "+8-12%", "+5%", "+2-4%", "+10-20%", "+6%"]);

    const { result } = renderHook(() => useImpactSummary());
    const everything = JSON.stringify(result.current);

    // Not "the total is zero" — there is no total. A figure would mean the
    // arithmetic came back under another name.
    expect(everything).not.toMatch(/%/);
    expect("fpsGain" in result.current.gained).toBe(false);
    expect("fpsGain" in result.current.potential).toBe(false);
  });

  it("counts the settings instead, which is the honest thing it knows", () => {
    withFpsClaims(["+3-5%", "+8-12%", "+5%"]);

    const { result } = renderHook(() => useImpactSummary());

    expect(result.current.gained.count).toBe(3);
    expect(result.current.score.optimized).toBe(3);
  });

  it("does not grow a gain when more claims are added", () => {
    withFpsClaims(["+3-5%"]);
    const one = renderHook(() => useImpactSummary()).result.current;

    withFpsClaims(["+3-5%", "+40-60%", "+80%"]);
    const many = renderHook(() => useImpactSummary()).result.current;

    // The only thing that moved is the count. If a headline figure existed,
    // adding a "+80%" claim would move it — that is the whole failure mode.
    expect(JSON.stringify({ ...one, score: null, gained: null })).toBe(
      JSON.stringify({ ...many, score: null, gained: null }),
    );
    expect(many.gained.count).toBeGreaterThan(one.gained.count);
  });
});

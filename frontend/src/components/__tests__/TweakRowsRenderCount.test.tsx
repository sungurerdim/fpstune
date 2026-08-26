/**
 * G3: the 400-row list re-renders one row when one setting changes.
 *
 * TweakRows' memo contract (documented in the component: closures built in
 * the row so the parent's rebuild cannot fail the comparison) is what makes
 * a 400-row list usable — and a contract only a comment held. This pins it:
 * seed 400 rows, bump one setting through the store the way detection does,
 * and count actual row renders. If someone reintroduces a per-render closure
 * prop, this fails with 400 extra renders, not a vague slowness report.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TweakRows } from "../TweakRows";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

const renderCounts = new Map<string, number>();

vi.mock("../TweakSetting", () => ({
  TweakSetting: ({ setting }: { setting: Setting }) => {
    renderCounts.set(setting.id, (renderCounts.get(setting.id) ?? 0) + 1);
    return <div data-testid="row" />;
  },
}));

function makeSetting(index: number): Setting {
  return {
    id: `system:probe_${index}`,
    module: "system",
    name: `probe_${index}`,
    displayName: `Probe ${index}`,
    description: "Probe. It matters.",
    impactCategories: [],
    category: "network",
    valueType: "choice",
    choices: ["off", "on"],
    defaultValue: "off",
    recommendedValue: "on",
    requiresReboot: false,
    isAction: false,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    categoryOrder: 0,
    riskLevel: "low",
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: "off",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
  } as unknown as Setting;
}

const ROWS = 400;

describe("G3: TweakRows render budget", () => {
  beforeEach(() => {
    renderCounts.clear();
    useStore.setState({
      settings: new Map(
        Array.from({ length: ROWS }, (_, i) => {
          const s = makeSetting(i);
          return [s.id, s] as const;
        }),
      ),
      _settingsVersion: 1,
    } as never);
  });

  it("updating one setting re-renders one row, not four hundred", () => {
    const client = new QueryClient();
    const list = (rows: Setting[]) => (
      <QueryClientProvider client={client}>
        <TweakRows rows={rows.map((setting) => ({ setting }))} />
      </QueryClientProvider>
    );

    const { rerender } = render(
      list([...useStore.getState().settings.values()]),
    );
    expect(renderCounts.size).toBe(ROWS);

    // One setting changes the way detection changes it: a fresh object for
    // that id, the same references for every other.
    act(() => {
      useStore
        .getState()
        .setSettingDetectionResult("system:probe_7", "on", true, true);
    });
    renderCounts.clear();
    rerender(list([...useStore.getState().settings.values()]));

    // The memo contract: the changed row renders, the other 399 do not.
    expect(renderCounts.get("system:probe_7")).toBe(1);
    const cascaded = [...renderCounts.keys()].filter(
      (id) => id !== "system:probe_7",
    );
    expect(
      cascaded.length,
      `rows that re-rendered without changing: ${cascaded.slice(0, 5).join(", ")}…`,
    ).toBe(0);
  });
});
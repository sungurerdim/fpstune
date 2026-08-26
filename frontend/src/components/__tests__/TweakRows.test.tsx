/**
 * A scan re-renders every row in the list, whether or not the row changed.
 *
 * `_settingsVersion` bumps once per category during a detection pass and once
 * per apply, and every list on screen rebuilds its rows from it. Each row was
 * handed five freshly-created closures — `onApplyValue`, `onReset`, `onUndo`,
 * `onVerify`, `onSelect` — so no memo could ever hold: the props differed by
 * identity on every single bump, for all eighty rows, while the settings behind
 * seventy-nine of them had not moved.
 *
 * The row is counted rather than timed. A render count is the thing that
 * actually regressed, and it is the same number on any machine.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "../../test/utils";
import { TweakRows, type TweakRow } from "../TweakRows";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

const renderCounts = new Map<string, number>();

vi.mock("../TweakSetting", () => ({
  TweakSetting: ({ setting }: { setting: Setting }) => {
    renderCounts.set(setting.id, (renderCounts.get(setting.id) ?? 0) + 1);
    return <div data-testid={setting.id}>{setting.displayName}</div>;
  },
}));

function makeSetting(id: string, displayName: string): Setting {
  return {
    id: id as `${string}:${string}`,
    module: id.split(":")[0],
    name: id.split(":").slice(1).join(":"),
    displayName,
    description: "Controls something. It matters for latency.",
    impactCategories: [],
    category: "network",
    valueType: "choice",
    choices: ["enabled", "disabled"],
    defaultValue: "enabled",
    recommendedValue: "disabled",
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
    currentValue: "enabled",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
  } as Setting;
}

const NAGLE = makeSetting("network:nagle", "Nagle's Algorithm");
const RSS = makeSetting("network:rss", "Receive Side Scaling");

/** A row list rebuilt the way the tabs rebuild theirs: new array, new icon
 *  elements, the same setting objects for anything that did not change. */
function rowsFor(settings: Setting[]): TweakRow[] {
  return settings.map((setting) => ({
    setting,
    contextLabel: "Network · Adapters",
    contextIcon: <span data-testid={`icon-${setting.id}`} />,
  }));
}

describe("TweakRows re-renders only the rows that moved", () => {
  beforeEach(() => {
    renderCounts.clear();
    useStore.setState({
      settings: new Map(),
      selectedSettingIds: new Set(),
      operationStatus: {},
    } as never);
  });

  it("leaves an untouched row alone when the list is rebuilt", () => {
    const { rerender } = render(<TweakRows rows={rowsFor([NAGLE, RSS])} />);

    expect(renderCounts.get("network:nagle")).toBe(1);
    expect(renderCounts.get("network:rss")).toBe(1);

    // The bump: a brand-new rows array with brand-new context icons, exactly
    // what a `_settingsVersion` change produces, and not one setting changed.
    rerender(<TweakRows rows={rowsFor([NAGLE, RSS])} />);

    expect(renderCounts.get("network:nagle")).toBe(1);
    expect(renderCounts.get("network:rss")).toBe(1);
  });

  it("still re-renders the one row whose setting actually changed", () => {
    const { rerender } = render(<TweakRows rows={rowsFor([NAGLE, RSS])} />);

    const applied: Setting = { ...RSS, currentValue: "disabled", isOptimized: true };
    rerender(<TweakRows rows={rowsFor([NAGLE, applied])} />);

    expect(renderCounts.get("network:rss")).toBe(2);
    expect(renderCounts.get("network:nagle")).toBe(1);
    expect(screen.getByTestId("network:rss")).toBeInTheDocument();
  });

  it("re-renders a row whose selection state changed, and only that row", () => {
    const { rerender } = render(<TweakRows rows={rowsFor([NAGLE, RSS])} />);

    useStore.setState({
      selectedSettingIds: new Set(["network:nagle"]),
    } as never);
    rerender(<TweakRows rows={rowsFor([NAGLE, RSS])} />);

    expect(renderCounts.get("network:nagle")).toBe(2);
    expect(renderCounts.get("network:rss")).toBe(1);
  });
});

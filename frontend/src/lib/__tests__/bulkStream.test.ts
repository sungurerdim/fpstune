/**
 * The server derives no value for a bulk run, so the client's map is the whole
 * truth of what gets written. Each rule below is a way that map once could have
 * (or still could) tell the machine the wrong thing.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { bulkTargets } from "../bulkStream";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

function makeSetting(overrides: Partial<Setting> & { id: string }): Setting {
  return {
    domain: "software",
    module: overrides.id.split(":")[0],
    name: overrides.id.split(":").slice(1).join(":"),
    displayName: "A Tweak",
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
    ...overrides,
  } as Setting;
}

const TWEAK = makeSetting({ id: "network:nagle" });
// An action fpstune does NOT recommend running unprompted: the trap.
const REPAIR = makeSetting({
  id: "maintenance:sfc_scan",
  isAction: true,
  valueType: "bool",
  choices: [],
  defaultValue: false,
  recommendedValue: false,
});
const NO_DEFAULT = makeSetting({ id: "network:no_default", defaultValue: null });

beforeEach(() => {
  useStore.setState({
    settings: new Map(
      [TWEAK, REPAIR, NO_DEFAULT].map((s) => [s.id, s] as [Setting["id"], Setting]),
    ),
  } as never);
});

describe("bulkTargets", () => {
  it("applies an ordinary setting's recommendation", () => {
    expect(bulkTargets(["network:nagle"], "apply")).toEqual({
      "network:nagle": "disabled",
    });
  });

  it("runs an action with true even when it is not recommended unasked", () => {
    expect(REPAIR.recommendedValue).toBe(false);
    expect(bulkTargets(["maintenance:sfc_scan"], "apply")).toEqual({
      "maintenance:sfc_scan": true,
    });
  });

  it("resets every row to its own default, an action's being do-not-run", () => {
    expect(
      bulkTargets(["network:nagle", "maintenance:sfc_scan"], "reset"),
    ).toEqual({ "network:nagle": "enabled", "maintenance:sfc_scan": false });
  });

  it("sends null for a row with no derivable default, so the backend refuses it", () => {
    expect(bulkTargets(["network:no_default"], "reset")).toEqual({
      "network:no_default": null,
    });
  });

  it("sends null for an id the store does not know, so the stream reports it", () => {
    expect(bulkTargets(["ghost:setting"], "apply")).toEqual({
      "ghost:setting": null,
    });
  });
});

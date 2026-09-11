/**
 * The tab's top band states one number and keeps no second list.
 *
 * It used to hold a "Cleanup Results" readout listing every action that had run
 * — a copy of rows that were already on the page below it — and a "Running"
 * panel listing copies of the ones still going. Each cleanup was therefore on
 * screen two or three times. The rows own all of that now; what is left up here
 * is the session total, which no single row can state.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "../../test/utils";
import { DiskCleanupTab } from "../DiskCleanupTab";
import { makeRunner } from "../../test/runner";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

vi.mock("../../hooks/useCleanupRunner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../hooks/useCleanupRunner")>()),
  useCleanupRunner: () => makeRunner(),
}));

function cleanup(name: string, displayName: string, size: string): Setting {
  return {
    id: `cleanup:${name}` as `${string}:${string}`,
    groupId: "windows",
    groupLabel: "Windows",
    groupOrder: 1,
    module: "cleanup",
    name,
    displayName,
    description: "Removes files that are safe to delete.",
    category: "maintenance",
    valueType: "bool",
    choices: [],
    defaultValue: false,
    recommendedValue: true,
    requiresReboot: false,
    isAction: true,
    scope: "recommended",
    currentImpact: "",
    recommendedImpact: "",
    categoryOrder: 0,
    riskLevel: "safe",
    evidenceLevel: "likely",
    sources: [],
    applicableConditions: {},
    isReadonly: false,
    currentValue: size,
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    impactCategories: [],
  };
}

function setStore(cleanupResults: Record<string, unknown> = {}) {
  useStore.setState({
    settings: new Map([
      ["cleanup:temp_files", cleanup("temp_files", "Temp Files", "ready|1 GB")],
      ["cleanup:event_logs", cleanup("event_logs", "Event Logs", "ready|40 MB")],
    ]),
    cleanupResults,
    runSteps: [],
    maintenanceSelection: {},
  } as never);
}

describe("the Cleanup tab's top band", () => {
  beforeEach(() => setStore());

  it("states no total before anything has been run", () => {
    render(<DiskCleanupTab />);

    expect(screen.queryByText(/Freed/)).not.toBeInTheDocument();
  });

  it("adds up only what the backend measured each run freeing", () => {
    // Every addend is a byte count an instrument returned, which is what makes
    // this a measurement rather than a sum of claims (C11 rule 1). The failed
    // run contributes nothing.
    setStore({
      "cleanup:temp_files": {
        id: "cleanup:temp_files",
        name: "Temp Files",
        success: true,
        sized: true,
        freedMB: 1536,
      },
      "cleanup:event_logs": {
        id: "cleanup:event_logs",
        name: "Event Logs",
        success: true,
        sized: true,
        freedMB: 512,
      },
      "cleanup:prefetch": {
        id: "cleanup:prefetch",
        name: "Prefetch Files",
        success: false,
        sized: false,
        freedMB: null,
        error: "Access to the path is denied",
      },
    });

    render(<DiskCleanupTab />);

    expect(screen.getAllByText("Freed 2.0 GB")).toHaveLength(1);
  });

  it("keeps no second list of what ran beside the rows that ran it", () => {
    // Two rows that each freed the same amount: the figure appears once per
    // row and the total once in the band — four statements about two cleanups,
    // where the old layout made ten.
    setStore({
      "cleanup:temp_files": {
        id: "cleanup:temp_files",
        name: "Temp Files",
        success: true,
        sized: true,
        freedMB: 1024,
      },
      "cleanup:event_logs": {
        id: "cleanup:event_logs",
        name: "Event Logs",
        success: true,
        sized: true,
        freedMB: 1024,
      },
    });

    render(<DiskCleanupTab />);

    expect(screen.getAllByText("Temp Files")).toHaveLength(1);
    expect(screen.getAllByText("Event Logs")).toHaveLength(1);
    // One per row, and no third copy in a results list.
    expect(screen.getAllByText("Freed 1.0 GB")).toHaveLength(2);
    // The band's total, which no single row states.
    expect(screen.getAllByText("Freed 2.0 GB")).toHaveLength(1);
  });
});

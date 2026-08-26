/**
 * Home must not state a result it has not observed.
 *
 * Two empty-state messages were making claims the app had no basis for:
 *   - the tweaks list said "Everything applicable is already optimized." while
 *     detection was still running, i.e. before a single value had been read
 *   - the cleanup list said "Calculating cleanup sizes… or nothing to reclaim.",
 *     admitting in one sentence that it did not know which of the two it was,
 *     while `sizesCalculating` knew all along
 *
 * An empty list means two different things, and picking the wrong one is the same
 * defect class as an apply that reports success without verifying: a confident
 * statement with nothing behind it.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "../../test/utils";
import { HomeTab } from "../HomeTab";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

vi.mock("../../hooks/useBulkApply", () => ({
  useBulkApply: () => ({ apply: vi.fn(), isApplying: false }),
}));

vi.mock("../../hooks/useCleanupRunner", () => ({
  useCleanupRunner: () => ({
    selectedIds: [],
    selectedCount: 0,
    hasSelection: false,
    isRunning: false,
    run: vi.fn(),
    confirmIds: null,
    confirmRun: vi.fn(),
    cancelConfirm: vi.fn(),
  }),
}));

/** A cleanup whose size is still being computed in the background. */
function pendingCleanup(): Setting {
  return {
    id: "cleanup:temp_files" as `${string}:${string}`,
    module: "cleanup",
    name: "temp_files",
    displayName: "Temp Files",
    description: "Clears temporary files from the system.",
    category: "cleanup",
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
    // No parseable size yet, so the row is filtered out of the list and the
    // empty state is what the user actually reads.
    currentValue: "ready|calculating",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    impactCategories: [],
  };
}

function setStore(settings: Setting[], detecting: boolean) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    categories: new Map(),
    cleanupResults: {},
    categoryDetectionStatus: detecting
      ? { core: "loading" }
      : { core: "success" },
  } as never);
}

describe("HomeTab empty states", () => {
  beforeEach(() => {
    setStore([], false);
  });

  // Home shows three groups — hardware, software and game — so each message appears
  // once per group. Asserting on all of them is the stronger check: no domain may
  // claim a result the app does not have.
  it("does not claim everything is optimized while detection is running", () => {
    setStore([], true);
    render(<HomeTab />);

    expect(screen.queryByText(/already optimized/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/Reading your current settings/i)).toHaveLength(3);
  });

  it("the scan shows real progress, not just a spinner (E5)", () => {
    setStore([], true);
    render(<HomeTab />);

    const bar = screen.getByRole("progressbar", {
      name: /Detection progress across setting categories/,
    });
    // One category, still loading: 0 of 1 done.
    expect(bar).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getByText(/0\/1 categories read/)).toBeInTheDocument();
  });

  it("says everything is optimized only once detection has finished", () => {
    setStore([], false);
    render(<HomeTab />);

    expect(screen.getAllByText(/already optimized/i)).toHaveLength(3);
    expect(
      screen.queryByText(/Reading your current settings/i),
    ).not.toBeInTheDocument();
  });

  it("separates hardware, software and game tweaks", () => {
    setStore([], false);
    render(<HomeTab />);

    expect(screen.getByText("Hardware tweaks")).toBeInTheDocument();
    expect(screen.getByText("Software tweaks")).toBeInTheDocument();
    expect(screen.getByText("Game tweaks")).toBeInTheDocument();
  });

  it("offers no bulk apply for a group with nothing outstanding", () => {
    // A disabled "Apply All" on an empty group is a control that cannot do anything;
    // the count in the label is what makes the button's scope legible.
    setStore([], false);
    render(<HomeTab />);

    expect(screen.queryByRole("button", { name: /apply all/i })).not.toBeInTheDocument();
  });

  it("says sizes are being measured while a cleanup is still calculating", () => {
    setStore([pendingCleanup()], false);
    render(<HomeTab />);

    expect(
      screen.getByText(/Measuring what can be reclaimed/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Nothing to reclaim/i)).not.toBeInTheDocument();
  });

  it("says there is nothing to reclaim only when no size is pending", () => {
    setStore([], false);
    render(<HomeTab />);

    expect(screen.getByText(/Nothing to reclaim right now/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/Measuring what can be reclaimed/i),
    ).not.toBeInTheDocument();
  });

  it("never shows a message that hedges between two states", () => {
    // Pins the specific wording that was wrong, so it cannot come back.
    setStore([pendingCleanup()], true);
    render(<HomeTab />);

    expect(screen.queryByText(/or nothing to reclaim/i)).not.toBeInTheDocument();
  });
});

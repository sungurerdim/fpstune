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
import { act, render, screen } from "../../test/utils";
import { HomeTab } from "../HomeTab";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

// Home mounts the whole product now (D1); the device/maintenance surfaces
// have their own tests, and their live fetches only add teardown noise here.
vi.mock("../HardwarePanel", () => ({
  HardwarePanel: () => null,
}));
vi.mock("../MaintenancePanel", () => ({
  MaintenancePanel: () => null,
}));
vi.mock("../SelfCheckNotice", () => ({
  SelfCheckNotice: () => null,
}));

// HomeTab asks the headroom API on mount. Left unmocked, that is a real fetch
// against no server in jsdom, rejected after the test has finished; vitest
// reported it as an unhandled error in the full pre-commit run on 2026-09-02.
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    headroomApi: { list: () => Promise.resolve({ games: [] }) },
  };
});

vi.mock("../../hooks/useBulkApply", () => ({
  useBulkApply: () => ({ apply: vi.fn(), isApplying: false }),
}));

// Only the runner: `isDockerCleanup` is a pure predicate the rows call, and a
// mock that dropped it would fail on the export rather than on the behaviour.
const { runMock } = vi.hoisted(() => ({ runMock: vi.fn() }));
vi.mock("../../hooks/useCleanupRunner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../hooks/useCleanupRunner")>()),
  useCleanupRunner: () => ({
    selectedIds: [],
    selectedCount: 0,
    hasSelection: false,
    isRunning: false,
    run: runMock,
    confirmIds: null,
    confirmRun: vi.fn(),
    cancelConfirm: vi.fn(),
  }),
}));

/** A cleanup whose size the background scan has already measured. */
function measuredCleanup(overrides: Partial<Setting> = {}): Setting {
  return { ...pendingCleanup(), currentValue: "ready|4096 MB", ...overrides };
}

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
    runSteps: [],
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
    expect(screen.getAllByText(/Reading your current settings/i)).toHaveLength(
      3,
    );
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

    expect(
      screen.queryByRole("button", { name: /apply all/i }),
    ).not.toBeInTheDocument();
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

    expect(
      screen.getByText(/Nothing to reclaim right now/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Measuring what can be reclaimed/i),
    ).not.toBeInTheDocument();
  });

  it("never shows a message that hedges between two states", () => {
    // Pins the specific wording that was wrong, so it cannot come back.
    setStore([pendingCleanup()], true);
    render(<HomeTab />);

    expect(
      screen.queryByText(/or nothing to reclaim/i),
    ).not.toBeInTheDocument();
  });
});

/**
 * A running cleanup is reported in the row that started it, and nowhere else.
 *
 * Pressing Run used to open a separate "running" panel above this list holding a
 * copy of every selected action, so one cleanup was on the page twice — its size
 * in one row, its progress in another, matched up by name.
 */
describe("HomeTab has one place per cleanup", () => {
  beforeEach(() => {
    setStore([measuredCleanup()], false);
  });

  it("names a running cleanup exactly once", () => {
    render(<HomeTab />);
    act(() => {
      useStore
        .getState()
        .beginRun([{ id: "cleanup:temp_files", name: "Temp Files" }]);
      useStore.getState().updateRunStep("cleanup:temp_files", {
        status: "running",
        startedAt: Date.now(),
        command: "Remove-Item -Recurse -Force",
      });
    });

    expect(screen.getAllByText("Temp Files")).toHaveLength(1);
    // And the progress is inside that one row: the command it is running is on
    // the page, without a second list to carry it.
    expect(
      screen.getByText(/Remove-Item -Recurse -Force/),
    ).toBeInTheDocument();
  });

  it("names a finished cleanup exactly once, with its freed figure", () => {
    render(<HomeTab />);
    act(() => {
      useStore
        .getState()
        .beginRun([{ id: "cleanup:temp_files", name: "Temp Files" }]);
      useStore.getState().updateRunStep("cleanup:temp_files", {
        status: "done",
        endedAt: Date.now(),
      });
      useStore.getState().recordCleanupResults([
        {
          id: "cleanup:temp_files",
          name: "Temp Files",
          success: true,
          sized: true,
          freedMB: 2048,
        },
      ]);
    });

    expect(screen.getAllByText("Temp Files")).toHaveLength(1);
    expect(screen.getAllByText("Freed 2.0 GB")).toHaveLength(1);
  });
});

/**
 * "What still needs doing" includes upkeep that is late, not only bytes.
 *
 * `maintenance:ssd_retrim` detects that Windows' own weekly optimization has
 * not run — the reading is `overdue|23 days` — and until this existed the only
 * place on Home that fact appeared was the repair panel at the bottom, under a
 * heading about SFC and DISM. The to-do card above it, which is what a user
 * reads to decide what to press, listed cleanups with a size and nothing else.
 *
 * It is listed exactly once: the same row in two places is the defect
 * <ActionRow/> was built to end, so Home hands the ids it has already listed to
 * the repair panel to leave out.
 */
describe("Home lists upkeep that is overdue", () => {
  /** The retrim as detected: overdue, with how long by. */
  function overdueRetrim(overrides: Partial<Setting> = {}): Setting {
    return {
      ...pendingCleanup(),
      id: "maintenance:ssd_retrim" as `${string}:${string}`,
      module: "maintenance",
      name: "ssd_retrim",
      displayName: "SSD TRIM Overdue",
      description: "Tells every SSD which blocks are free again.",
      category: "maintenance",
      categoryOrder: 26,
      currentValue: "overdue|23 days",
      ...overrides,
    };
  }

  beforeEach(() => {
    runMock.mockClear();
  });

  it("puts an overdue TRIM in the to-do card, as a duration not a size", () => {
    setStore([overdueRetrim()], false);
    render(<HomeTab />);

    const rows = screen.getByTestId("home-cleanup-rows");
    expect(rows).toHaveTextContent("SSD TRIM Overdue");
    expect(rows).toHaveTextContent("TRIM overdue: 23 days ago");
    expect(
      screen.queryByText(/Nothing to reclaim right now/i),
    ).not.toBeInTheDocument();
  });

  it("leaves a TRIM that is up to date off the list of things to do", () => {
    setStore([overdueRetrim({ currentValue: "ok|3 days" })], false);
    render(<HomeTab />);

    expect(screen.queryByText("SSD TRIM Overdue")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Nothing to reclaim right now/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run all/i })).toBeDisabled();
  });

  it("counts it among the card's items, so the heading matches the rows", () => {
    setStore([measuredCleanup(), overdueRetrim()], false);
    render(<HomeTab />);

    expect(screen.getByTestId("home-cleanup-count")).toHaveTextContent("2");
  });

  it("names the card for what it holds once upkeep is in it", () => {
    setStore([measuredCleanup()], false);
    const { unmount } = render(<HomeTab />);
    expect(
      screen.getByText("Available disk cleanup actions"),
    ).toBeInTheDocument();
    unmount();

    setStore([measuredCleanup(), overdueRetrim()], false);
    render(<HomeTab />);
    expect(screen.getByText("Disk cleanup and upkeep")).toBeInTheDocument();
  });

  it("runs the overdue TRIM as part of Run All", () => {
    // The button is the card's promise: every row under it. A to-do row that
    // Run All skipped would still be overdue after the user had run everything.
    setStore([measuredCleanup(), overdueRetrim()], false);
    render(<HomeTab />);

    act(() => {
      screen.getByRole("button", { name: /run all/i }).click();
    });

    expect(runMock).toHaveBeenCalledTimes(1);
    const ids = runMock.mock.calls[0][0] as string[];
    expect(ids).toContain("maintenance:ssd_retrim");
    expect(ids).toContain("cleanup:temp_files");
  });
});

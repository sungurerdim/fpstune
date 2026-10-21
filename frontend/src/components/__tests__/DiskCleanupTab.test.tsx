/**
 * The Cleanup tab: one surface for every action that gives something back.
 *
 * It replaces three: a system panel, a game panel and a repair card, each with
 * its own Run, its own heading rules and its own card for a row. Here rows are
 * the shared one-line row, sections are the shared collapsed section headed by
 * the backend's own `group_label`, and a run goes through the one apply path.
 *
 * The measuring tests are ported from the system panel. The first scan answers
 * `ready|calculating` for every cleanup — including ones whose software is not
 * installed — and the next answers "not installed" for those. Measured: 293
 * detected on scan 1, 281 on scans 2+, and all twelve that move are
 * cleanup/game_cleanup. So twelve full, selectable rows appeared on first load
 * and then vanished. The backend is truthful at every step; the defect was
 * presenting "not known" as a finished row.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, within } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { DiskCleanupTab } from "../DiskCleanupTab";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

const { run, stop, applyState } = vi.hoisted(() => ({
  run: vi.fn(),
  stop: vi.fn(),
  applyState: { isRunning: false },
}));

vi.mock("../../hooks/useApply", () => ({
  useApply: () => ({
    apply: vi.fn(),
    reset: vi.fn(),
    run,
    stop,
    pendingIds: new Set<string>(),
    isPending: () => false,
    isRunning: applyState.isRunning,
  }),
}));

const WINDOWS = { id: "windows", label: "Windows", order: 1 };
const DEVELOPER = { id: "developer", label: "Developer caches", order: 3 };
const CONTAINERS = { id: "containers", label: "Containers & WSL", order: 4 };

function action(
  module: string,
  name: string,
  currentValue: unknown,
  displayName: string,
  group: { id: string; label: string; order: number } | null = WINDOWS,
  overrides: Partial<Setting> = {},
): Setting {
  return {
    id: `${module}:${name}` as `${string}:${string}`,
    domain: "software",
    ...(group
      ? { groupId: group.id, groupLabel: group.label, groupOrder: group.order }
      : {}),
    module,
    name,
    displayName,
    description: "Removes files that are safe to delete.",
    category: "maintenance",
    valueType: "bool",
    choices: [],
    defaultValue: false,
    recommendedValue: false,
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
    currentValue,
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    impactCategories: [],
    ...overrides,
  } as Setting;
}

const cleanup = (
  name: string,
  currentValue: unknown,
  displayName: string,
  group = WINDOWS,
) => action("cleanup", name, currentValue, displayName, group);

function setSettings(settings: Setting[], extra: Record<string, unknown> = {}) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    maintenanceSelection: {},
    cleanupResults: {},
    runSteps: [],
    operationStatus: {},
    operationError: {},
    ...extra,
  } as never);
}

/** Open a section by its heading: they are collapsed until asked for. */
async function open(heading: string) {
  await userEvent.click(screen.getByRole("button", { name: new RegExp(heading) }));
}

beforeEach(() => {
  run.mockReset();
  stop.mockReset();
  applyState.isRunning = false;
  setSettings([]);
});

describe("a size that is still being measured", () => {
  it("keeps a still-measuring cleanup out of the selectable list", async () => {
    setSettings([
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
      cleanup("yarn_cache", "ready|calculating", "Yarn Cache"),
    ]);
    render(<DiskCleanupTab />);
    await open("Windows");

    // The measured one is a real row with a checkbox; the pending one is named
    // in the measuring line and has none, so it cannot be selected on a size
    // nobody has read yet.
    expect(screen.getByRole("checkbox", { name: "Select Temp Files" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: /Yarn Cache/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Measuring 1 more/i)).toBeInTheDocument();
    expect(screen.getByText(/Yarn Cache/)).toBeInTheDocument();
  });

  it("counts every pending cleanup in one line rather than N disappearing rows", () => {
    setSettings([
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
      cleanup("yarn_cache", "ready|calculating", "Yarn Cache"),
      cleanup("pnpm_cache", "ready|calculating", "pnpm Cache"),
      cleanup("nuget_cache", "ready|calculating", "NuGet Cache"),
    ]);
    render(<DiskCleanupTab />);

    expect(screen.getByText(/Measuring 3 more/i)).toBeInTheDocument();
  });

  it("says what a name vanishing from the measuring line means", () => {
    // Without this sentence the disappearance is still unexplained, just quieter.
    setSettings([
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
      cleanup("yarn_cache", "ready|calculating", "Yarn Cache"),
    ]);
    render(<DiskCleanupTab />);

    expect(
      screen.getByText(/nothing to reclaim, or its software is not installed/i),
    ).toBeInTheDocument();
  });

  it("drops the measuring line once every size is known", () => {
    setSettings([cleanup("temp_files", "ready|1.2 GB", "Temp Files")]);
    render(<DiskCleanupTab />);

    expect(screen.queryByText(/Measuring/i)).not.toBeInTheDocument();
  });

  it("still renders while every cleanup is pending", () => {
    // Returning nothing here would make the whole tab pop in, which is the same
    // defect one level up.
    setSettings([cleanup("yarn_cache", "ready|calculating", "Yarn Cache")]);
    render(<DiskCleanupTab />);

    expect(screen.getByText(/Measuring 1 more/i)).toBeInTheDocument();
  });
});

describe("the groups", () => {
  it("heads each group with the label the backend sent, in its order, collapsed", () => {
    // A flat list put a Rust registry beside a Windows event log. The headings
    // are the backend's, so a game's name is never spelled in TypeScript.
    setSettings([
      cleanup("cargo_cache", "ready|900 MB", "Cargo Registry", DEVELOPER),
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
    ]);
    render(<DiskCleanupTab />);

    const headings = screen
      .getAllByRole("heading", { level: 3 })
      .map((h) => h.textContent?.trim());
    expect(headings).toEqual(["Windows", "Developer caches"]);
    expect(screen.queryByText("Temp Files")).not.toBeInTheDocument();
  });

  it("does not add overlapping Docker alternatives into one promise", () => {
    // prune and prune-all share layers, and WSL compact touches the same
    // Docker Desktop disks. 12.7 GB + 8.7 GB is one 12.7 GB choice, not 20.9.
    setSettings([
      action("cleanup", "docker_prune", "ready|8744 MB", "Docker prune", CONTAINERS),
      action("cleanup", "docker_prune_all", "ready|12702 MB", "Docker prune all", CONTAINERS),
    ]);
    render(<DiskCleanupTab />);

    expect(screen.getByText("12.4 GB")).toBeInTheDocument();
    expect(screen.queryByText("20.9 GB")).not.toBeInTheDocument();
  });

  it("lists a repair under the maintenance heading, not under 'Other'", async () => {
    setSettings([
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
      action("maintenance", "sfc_scan", null, "SFC Scan", null),
    ]);
    render(<DiskCleanupTab />);

    expect(screen.getByRole("heading", { name: "System Maintenance" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Other" })).not.toBeInTheDocument();
    await open("System Maintenance");
    expect(screen.getByText("SFC Scan")).toBeInTheDocument();
  });

  it("puts a cleanup the backend never grouped under 'Other' instead of dropping it", () => {
    setSettings([
      {
        ...cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
        groupId: undefined,
        groupLabel: undefined,
        groupOrder: undefined,
      } as Setting,
    ]);
    render(<DiskCleanupTab />);

    expect(screen.getByRole("heading", { name: "Other" })).toBeInTheDocument();
  });

  it("selects a whole group from its header, and clears it again", async () => {
    setSettings([
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
      cleanup("event_logs", "ready|40 MB", "Event Logs"),
      cleanup("cargo_cache", "ready|900 MB", "Cargo Registry", DEVELOPER),
    ]);
    render(<DiskCleanupTab />);

    const selectWindows = screen.getByLabelText("Select all in Windows");
    await userEvent.click(selectWindows);

    // The two Windows cleanups and neither of the others: a group checkbox that
    // reached across groups would run a delete the user did not ask for.
    expect(useStore.getState().maintenanceSelection).toEqual({
      "cleanup:temp_files": true,
      "cleanup:event_logs": true,
    });

    await userEvent.click(selectWindows);
    expect(useStore.getState().maintenanceSelection).toEqual({
      "cleanup:temp_files": false,
      "cleanup:event_logs": false,
    });
  });

  it("adds up only what the scan measured on this disk", () => {
    // The one place summing is a measurement rather than a claim: every addend is
    // a byte count an instrument returned. An unmeasured row contributes nothing.
    setSettings([
      cleanup("temp_files", "ready|1 GB", "Temp Files"),
      cleanup("event_logs", "ready|500 MB", "Event Logs"),
      cleanup("prefetch", "ready|unavailable", "Prefetch Files"),
    ]);
    render(<DiskCleanupTab />);

    expect(screen.getByText("1.5 GB")).toBeInTheDocument();
  });

  it("lists the largest reclaim first inside a group", async () => {
    setSettings([
      cleanup("event_logs", "ready|40 MB", "Event Logs"),
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
    ]);
    render(<DiskCleanupTab />);
    await open("Windows");

    const rows = screen.getAllByTestId("tweak-row").map((r) => r.textContent);
    expect(rows[0]).toContain("Temp Files");
    expect(rows[1]).toContain("Event Logs");
  });

  it("hides what is not on this machine", () => {
    setSettings([
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
      { ...cleanup("steam_webcache", "ready|1 GB", "Steam"), isApplicable: false } as Setting,
    ]);
    render(<DiskCleanupTab />);

    expect(screen.queryByLabelText(/Steam/)).not.toBeInTheDocument();
  });
});

describe("what is freed", () => {
  const rows = [
    cleanup("temp_files", "ready|1 GB", "Temp Files"),
    cleanup("event_logs", "ready|40 MB", "Event Logs"),
  ];

  it("states no total before anything has been run", () => {
    setSettings(rows);
    render(<DiskCleanupTab />);

    expect(screen.queryByText(/Freed/)).not.toBeInTheDocument();
  });

  it("adds up only what the backend measured each run freeing", () => {
    // Every addend is a byte count an instrument returned, which is what makes
    // this a measurement rather than a sum of claims (C11 rule 1). The failed
    // run contributes nothing, and neither does one that measured no byte count.
    setSettings(rows, {
      cleanupResults: {
        "cleanup:temp_files": { id: "cleanup:temp_files", name: "Temp Files", success: true, sized: true, freedMB: 1536 },
        "cleanup:event_logs": { id: "cleanup:event_logs", name: "Event Logs", success: true, sized: true, freedMB: 512 },
        "cleanup:prefetch": { id: "cleanup:prefetch", name: "Prefetch", success: false, sized: false, freedMB: null, error: "denied" },
        "maintenance:sfc_scan": { id: "maintenance:sfc_scan", name: "SFC", success: true, sized: false, freedMB: null },
      },
    });
    render(<DiskCleanupTab />);

    expect(screen.getAllByText("Freed 2.0 GB")).toHaveLength(1);
  });

  it("shows each row's own freed figure beside its name, and the total once", async () => {
    setSettings(rows, {
      cleanupResults: {
        "cleanup:temp_files": { id: "cleanup:temp_files", name: "Temp Files", success: true, sized: true, freedMB: 1024 },
        "cleanup:event_logs": { id: "cleanup:event_logs", name: "Event Logs", success: true, sized: true, freedMB: 1024 },
      },
    });
    render(<DiskCleanupTab />);
    await open("Windows");

    expect(screen.getAllByText("Temp Files")).toHaveLength(1);
    expect(screen.getAllByText("Freed 1.0 GB")).toHaveLength(2);
    expect(screen.getAllByText("Freed 2.0 GB")).toHaveLength(1);
  });
});

describe("running", () => {
  it("runs this row's action and no other, through the one apply path", async () => {
    setSettings([
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
      cleanup("event_logs", "ready|40 MB", "Event Logs"),
    ]);
    render(<DiskCleanupTab />);
    await open("Windows");

    await userEvent.click(screen.getByRole("button", { name: "Apply Temp Files" }));

    // `apply` for an action means "run it": the recommended value of 24 of the 38
    // shipped actions is false, so the value is never read off the row.
    expect(run).toHaveBeenCalledWith("apply", ["cleanup:temp_files"]);
  });

  it("runs the selection from the one Run button, then forgets it", async () => {
    setSettings([
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
      cleanup("event_logs", "ready|40 MB", "Event Logs"),
    ]);
    render(<DiskCleanupTab />);
    expect(screen.getByRole("button", { name: "Run Cleanup" })).toBeDisabled();

    await open("Windows");
    await userEvent.click(screen.getByRole("checkbox", { name: "Select Temp Files" }));
    await userEvent.click(screen.getByRole("button", { name: "Run Cleanup (1)" }));

    expect(run).toHaveBeenCalledWith("apply", ["cleanup:temp_files"]);
    expect(useStore.getState().maintenanceSelection["cleanup:temp_files"]).toBe(false);
  });

  it("starts nothing while another run holds the machine, and offers Stop", async () => {
    applyState.isRunning = true;
    setSettings([cleanup("temp_files", "ready|1.2 GB", "Temp Files")], {
      maintenanceSelection: { "cleanup:temp_files": true },
    });
    render(<DiskCleanupTab />);
    await open("Windows");

    await userEvent.click(screen.getByRole("button", { name: "Apply Temp Files" }));
    expect(run).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(stop).toHaveBeenCalledTimes(1);
  });

  it("asks before a docker prune shuts Docker and WSL down, and runs nothing until told", async () => {
    setSettings([
      action("cleanup", "docker_prune", "ready|3 GB", "Docker Prune", {
        id: "containers",
        label: "Containers & WSL",
        order: 4,
      }),
    ]);
    render(<DiskCleanupTab />);
    await open("Containers");

    await userEvent.click(screen.getByRole("button", { name: "Apply Docker Prune" }));
    expect(run).not.toHaveBeenCalled();

    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: /Cancel/ }));
    expect(run).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Apply Docker Prune" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Prune & compact" }));
    expect(run).toHaveBeenCalledWith("apply", ["cleanup:docker_prune"]);
  });

  it("keeps an action's precondition behind its (i), in the user's language", async () => {
    setSettings([
      action("maintenance", "dism_health", null, "DISM Health Check", null),
    ]);
    render(<DiskCleanupTab />);
    await open("System Maintenance");

    await userEvent.click(
      screen.getByRole("button", { name: "Information about DISM Health Check" }),
    );

    expect(screen.getByText(/May require internet connection/)).toBeInTheDocument();
  });
});

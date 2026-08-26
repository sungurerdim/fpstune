/**
 * A cleanup whose size is still being measured must not look like a finished row.
 *
 * The first scan answers `ready|calculating` for every cleanup — including ones
 * whose software is not installed — and the next answers `not_available` for those.
 * Measured: 293 detected on scan 1, 281 on scans 2+, and all twelve that move are
 * cleanup/game_cleanup. So twelve full, selectable rows appeared on first load and
 * then vanished.
 *
 * The backend is truthful at every step; it genuinely does not know yet, and making
 * it answer `not_available` on a cache miss would load a fourth meaning onto
 * `is_applicable`. The defect is in the presentation: "not known" was rendered as a
 * finished answer. A name leaving a group labelled "Measuring" reads as the answer it
 * is; a row leaving the list reads as a glitch.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { CleanupPanel } from "../CleanupPanel";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

function cleanup(
  name: string,
  currentValue: unknown,
  displayName: string,
  group: { id: string; label: string; order: number } = {
    id: "windows",
    label: "Windows",
    order: 1,
  },
): Setting {
  return {
    id: `cleanup:${name}` as `${string}:${string}`,
    groupId: group.id,
    groupLabel: group.label,
    groupOrder: group.order,
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
    currentValue,
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    impactCategories: [],
  } as Setting;
}

const DEVELOPER = { id: "developer", label: "Developer caches", order: 3 };

/** Every checkbox except the ones a group header owns. */
function rowCheckboxes() {
  return screen
    .getAllByRole("checkbox")
    .filter(
      (box) => !box.getAttribute("aria-label")?.startsWith("Select all in"),
    );
}

function setSettings(settings: Setting[]) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    maintenanceSelection: {},
  } as never);
}

describe("CleanupPanel measuring state", () => {
  beforeEach(() => setSettings([]));

  it("keeps a still-measuring cleanup out of the selectable list", () => {
    setSettings([
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
      cleanup("yarn_cache", "ready|calculating", "Yarn Cache"),
    ]);
    render(<CleanupPanel initialCollapsed={false} />);

    // The measured one is a real row with a checkbox; the pending one is named in
    // the measuring group and has none, so it cannot be selected on a size nobody
    // has read yet. The group header's own checkbox is excluded — it selects a
    // group, it is not a row.
    expect(rowCheckboxes()).toHaveLength(1);
    expect(screen.getByText("Temp Files")).toBeInTheDocument();
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
    render(<CleanupPanel initialCollapsed={false} />);

    expect(screen.getByText(/Measuring 3 more/i)).toBeInTheDocument();
  });

  it("says what a name vanishing from the measuring group means", () => {
    // Without this sentence the disappearance is still unexplained, just quieter.
    setSettings([
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
      cleanup("yarn_cache", "ready|calculating", "Yarn Cache"),
    ]);
    render(<CleanupPanel initialCollapsed={false} />);

    expect(screen.getByText(/nothing to reclaim, or its software is not installed/i)).toBeInTheDocument();
  });

  it("drops the measuring group once every size is known", () => {
    setSettings([cleanup("temp_files", "ready|1.2 GB", "Temp Files")]);
    render(<CleanupPanel initialCollapsed={false} />);

    expect(screen.queryByText(/Measuring/i)).not.toBeInTheDocument();
  });

  it("heads each group with the label the backend sent, in its order", () => {
    // A flat list put a Rust registry beside a Windows event log. The headings
    // are the backend's, so a game's name is never spelled in TypeScript.
    setSettings([
      cleanup("cargo_cache", "ready|900 MB", "Cargo Registry", DEVELOPER),
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
    ]);
    render(<CleanupPanel initialCollapsed={false} />);

    const headings = screen
      .getAllByRole("heading", { level: 4 })
      .map((h) => h.textContent);
    expect(headings).toEqual(["Windows", "Developer caches"]);
  });

  it("selects a whole group from its header, and clears it again", async () => {
    setSettings([
      cleanup("temp_files", "ready|1.2 GB", "Temp Files"),
      cleanup("event_logs", "ready|40 MB", "Event Logs"),
      cleanup("cargo_cache", "ready|900 MB", "Cargo Registry", DEVELOPER),
    ]);
    render(<CleanupPanel initialCollapsed={false} />);

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
    render(<CleanupPanel initialCollapsed={false} />);

    expect(screen.getByText("1.5 GB")).toBeInTheDocument();
  });

  it("still renders while every cleanup is pending", () => {
    // Returning null here would make the whole panel pop in, which is the same
    // defect one level up.
    setSettings([cleanup("yarn_cache", "ready|calculating", "Yarn Cache")]);
    render(<CleanupPanel initialCollapsed={false} />);

    expect(screen.getByText(/Measuring 1 more/i)).toBeInTheDocument();
  });
});

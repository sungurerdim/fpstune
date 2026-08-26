/**
 * The two buttons mean exactly their category, and nothing runs unconfirmed.
 *
 * Competitive Max applies essential + recommended — the most frames without
 * touching what the player sees or hears. Absolute Max adds complete, and its
 * confirmation lists what is lost, drawn from each setting's own
 * perceptible_cost sentence. Before this surface existed, the first action on
 * Home was a bulk registry write behind a bare blue button with no
 * confirmation at all.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "../../test/utils";
import { HomeTab } from "../HomeTab";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

const applySpy = vi.fn();
vi.mock("../../hooks/useBulkApply", () => ({
  useBulkApply: () => ({ apply: applySpy, isApplying: false }),
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

const restorePoint = vi.fn().mockResolvedValue({ success: true, message: "" });
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, createRestorePoint: () => restorePoint() },
    headroomApi: { list: vi.fn().mockResolvedValue({ games: [] }) },
  };
});

function makeSetting(over: Partial<Setting> & Pick<Setting, "id">): Setting {
  return {
    module: over.id.split(":")[0],
    name: over.id.split(":").slice(1).join(":"),
    displayName: over.id,
    description: "Controls something. It matters.",
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
    ...over,
  } as Setting;
}

const ESSENTIAL = makeSetting({
  id: "timer:resolution" as `${string}:${string}`,
  scope: "essential",
});
const RECOMMENDED = makeSetting({
  id: "network:nagle" as `${string}:${string}`,
  scope: "recommended",
});
const COMPLETE = makeSetting({
  id: "game_config:mw4:model_quality" as `${string}:${string}`,
  scope: "complete",
  perceptibleCost:
    "Characters and objects render at reduced model detail; at long range, identification takes a beat longer.",
});

function seed() {
  useStore.setState({
    settings: new Map(
      [ESSENTIAL, RECOMMENDED, COMPLETE].map((s) => [s.id, s]),
    ),
    categories: new Map(),
    cleanupResults: {},
    operationStatus: {},
    _settingsVersion: 1,
  } as never);
}

describe("the two buttons", () => {
  beforeEach(() => {
    applySpy.mockClear();
    restorePoint.mockClear();
    seed();
  });

  it("Competitive Max applies exactly essential + recommended, never complete", async () => {
    render(<HomeTab />);
    fireEvent.click(screen.getByText(/Competitive Max/));
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await vi.waitFor(() => expect(applySpy).toHaveBeenCalledTimes(1));
    const payload = applySpy.mock.calls[0][0] as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual([
      "network:nagle",
      "timer:resolution",
    ]);
  });

  it("Absolute Max applies all three, and says what is lost before running", async () => {
    render(<HomeTab />);
    fireEvent.click(screen.getByText(/Absolute Max/));
    // The cost copy is on screen before anything runs (consequence 5).
    expect(
      await screen.findByText(/reduced model detail/),
    ).toBeInTheDocument();
    expect(applySpy).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Spend it"));
    await vi.waitFor(() => expect(applySpy).toHaveBeenCalledTimes(1));
    const payload = applySpy.mock.calls[0][0] as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual([
      "game_config:mw4:model_quality",
      "network:nagle",
      "timer:resolution",
    ]);
  });

  it("cancelling the confirmation applies nothing", async () => {
    render(<HomeTab />);
    fireEvent.click(screen.getByText(/Competitive Max/));
    fireEvent.click(await screen.findByText("Cancel"));
    expect(applySpy).not.toHaveBeenCalled();
  });

  it("the restore point is created before the apply when asked", async () => {
    render(<HomeTab />);
    fireEvent.click(screen.getByText(/Competitive Max/));
    fireEvent.click(await screen.findByRole("button", { name: "Apply" }));
    await vi.waitFor(() => expect(applySpy).toHaveBeenCalled());
    expect(restorePoint).toHaveBeenCalledTimes(1);
    expect(restorePoint.mock.invocationCallOrder[0]).toBeLessThan(
      applySpy.mock.invocationCallOrder[0],
    );
  });
});

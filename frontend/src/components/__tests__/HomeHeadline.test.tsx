/**
 * Every number on Home says what it is a number of.
 *
 * Reported by the user, reading their own machine: "367/367 optimized",
 * "57/297 Modern Warfare IV fps" and "226 tweaks active" on one screen, in three
 * separate chips. All three figures were correct and none of them was legible —
 * the 226 is a *subset* of the 367 (the ones fpstune actually wrote, as against
 * the ones that already matched the stock value), and nothing said so, so the
 * two read as a contradiction. The fps pair read as a count of things rather
 * than a frame rate against what the display can show.
 *
 * This is the same failure the C11 work is about, one step further out: there
 * the defect was showing a number nothing measured, here it is showing a
 * measured number whose referent the reader has to reconstruct. A figure nobody
 * can interpret is not information, and the user's own words were "I could not
 * even work out what they meant".
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

const headroomList = vi.fn();
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, headroomApi: { list: () => headroomList() } };
});

/** An applied tweak: at its ideal value, and that value is not the stock one. */
function changedByUs(id: string): Setting {
  return {
    id: id as `${string}:${string}`,
    module: id.split(":")[0],
    name: id.split(":").slice(1).join(":"),
    displayName: "A Tweak",
    description: "Controls something. It matters for latency.",
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
    impactCategories: [],
    currentValue: "disabled",
    status: "optimal",
    executionStatus: "idle",
    isOptimized: true,
    isApplicable: true,
  } as Setting;
}

/** A guard: already correct, because the stock value *is* the right one. */
function alreadyCorrect(id: string): Setting {
  return {
    ...changedByUs(id),
    defaultValue: "disabled",
    // The backend computes this with values_equal; fixtures state it.
    isDriftGuard: true,
  } as Setting;
}

function setStore(settings: Setting[]) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    categories: new Map(),
    cleanupResults: {},
    categoryDetectionStatus: { core: "success" },
  } as never);
}

describe("Home headline", () => {
  beforeEach(() => {
    headroomList.mockResolvedValue({ games: [] });
    setStore([]);
  });

  it("says what the optimized count counts", async () => {
    setStore([changedByUs("network:nagle"), alreadyCorrect("system:gamedvr")]);
    render(<HomeTab />);

    expect(await screen.findByText("2/2")).toBeInTheDocument();
    expect(
      screen.getByText("settings at their ideal value"),
    ).toBeInTheDocument();
  });

  it("shows the applied count as the part of the whole that it is", async () => {
    // The reported confusion, exactly: one of these two is at its ideal value
    // because fpstune wrote it, the other because the machine already agreed.
    setStore([changedByUs("network:nagle"), alreadyCorrect("system:gamedvr")]);
    render(<HomeTab />);

    expect(
      await screen.findByText(
        "1 fpstune changed · 1 were already correct · 1 drift guards standing watch",
      ),
    ).toBeInTheDocument();
  });

  it("no longer shows a bare count labelled only 'tweaks active'", async () => {
    setStore([changedByUs("network:nagle")]);
    render(<HomeTab />);

    await screen.findByText("1/1");
    expect(screen.queryByText("tweaks active")).not.toBeInTheDocument();
    expect(screen.queryByText("Applied")).not.toBeInTheDocument();
  });

  it("reads a measurement as a frame rate, not as a ratio of things", async () => {
    headroomList.mockResolvedValue({
      games: [
        {
          game: "mw4",
          label: "Modern Warfare IV",
          is_measured: true,
          measured_fps: 57.4,
          target_fps: 297,
        },
      ],
    });
    render(<HomeTab />);

    expect(await screen.findByText("57 fps")).toBeInTheDocument();
    expect(screen.getByText("Modern Warfare IV")).toBeInTheDocument();
    expect(
      screen.getByText("19% of the 297 fps this display can show"),
    ).toBeInTheDocument();
    // The old rendering, which read as two counted things.
    expect(screen.queryByText("57/297")).not.toBeInTheDocument();
  });

  it("says a panel with no known refresh has no target, rather than inventing one", async () => {
    headroomList.mockResolvedValue({
      games: [
        {
          game: "cs2",
          label: "Counter-Strike 2",
          is_measured: true,
          measured_fps: 240,
          target_fps: null,
        },
      ],
    });
    render(<HomeTab />);

    expect(await screen.findByText("240 fps")).toBeInTheDocument();
    expect(
      screen.getByText("no display target — panel refresh unknown"),
    ).toBeInTheDocument();
  });
});

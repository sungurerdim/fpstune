/**
 * Game Tweaks groups a game's config lines under that game, and under the name the
 * backend gave it.
 *
 * The defect this closes: `module` is the first segment of a setting id, so every
 * game collapses to `game_config` and no screen could tell Modern Warfare from
 * Counter-Strike. These tests pin the property that made that a defect — a section
 * per game, a bulk apply that never crosses a game boundary — and the C9 half of
 * it: the heading is whatever the backend sent, never a name spelled in TypeScript.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { GameTweaksTab } from "../GameTweaksTab";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

const applyMock = vi.fn();
vi.mock("../../hooks/useBulkApply", () => ({
  useBulkApply: () => ({
    apply: (payload: Record<string, unknown>) => applyMock(payload),
    isApplying: false,
    lastResult: null,
  }),
}));

function makeSetting(over: Partial<Setting> & Pick<Setting, "id">): Setting {
  return {
    module: over.id.split(":")[0],
    name: over.id.split(":").slice(1).join(":"),
    displayName: "A Game Tweak",
    description: "Controls something in the game. It matters for frame rate.",
    impactCategories: [],
    category: "game_config",
    valueType: "choice",
    choices: ["Low", "High"],
    defaultValue: "High",
    recommendedValue: "Low",
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
    currentValue: "High",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    ...over,
  } as Setting;
}

function setStore(settings: Setting[], detecting = false) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    selectedSettingIds: new Set(),
    operationStatus: {},
    categoryDetectionStatus: detecting ? { core: "loading" } : { core: "success" },
  } as never);
}

const MW4 = makeSetting({
  id: "game_config:mw4:shadow_quality" as `${string}:${string}`,
  displayName: "Shadow Quality",
  groupId: "mw4",
  groupLabel: "Modern Warfare IV",
  groupOrder: 10,
});

const CS2 = makeSetting({
  id: "game_config:cs2:fps_max" as `${string}:${string}`,
  displayName: "FPS Max",
  groupId: "cs2",
  groupLabel: "Counter-Strike 2",
  groupOrder: 12,
});

describe("GameTweaksTab", () => {
  beforeEach(() => {
    applyMock.mockClear();
    setStore([]);
  });

  it("heads each section with the name the backend sent", () => {
    setStore([MW4, CS2]);
    render(<GameTweaksTab />);

    // By role, because the game's name is also an option in the filter — which is
    // itself the point: both come from the same backend label.
    expect(
      screen.getByRole("heading", { name: "Modern Warfare IV" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Counter-Strike 2" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Shadow Quality")).toBeInTheDocument();
    expect(screen.getByText("FPS Max")).toBeInTheDocument();
  });

  it("never writes two games' files for one press", async () => {
    setStore([MW4, CS2]);
    render(<GameTweaksTab />);

    const buttons = screen.getAllByRole("button", { name: /apply all/i });
    expect(buttons).toHaveLength(2);

    await userEvent.click(buttons[0]);
    expect(applyMock).toHaveBeenCalledWith({
      "game_config:mw4:shadow_quality": "Low",
    });
  });

  it("shows only the game the filter selects", async () => {
    setStore([MW4, CS2]);
    render(<GameTweaksTab />);

    await userEvent.selectOptions(screen.getByLabelText("Filter by game"), "cs2");

    expect(screen.queryByText("Shadow Quality")).not.toBeInTheDocument();
    expect(screen.getByText("FPS Max")).toBeInTheDocument();
  });

  it("puts already-correct settings behind a fold", async () => {
    const applied = makeSetting({
      id: "game_config:mw4:motion_blur" as `${string}:${string}`,
      displayName: "Motion Blur",
      groupId: "mw4",
      groupLabel: "Modern Warfare IV",
      groupOrder: 10,
      currentValue: "Low",
      isOptimized: true,
      status: "optimal",
    });
    setStore([MW4, applied]);
    render(<GameTweaksTab />);

    expect(screen.getByText("Shadow Quality")).toBeInTheDocument();
    expect(screen.queryByText("Motion Blur")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("Optimized"));
    expect(screen.getByText("Motion Blur")).toBeInTheDocument();
  });

  it("counts an advisory into no button that promises a write", () => {
    const advisory = makeSetting({
      id: "game_config:mw4:read_only" as `${string}:${string}`,
      displayName: "Detected Only",
      groupId: "mw4",
      groupLabel: "Modern Warfare IV",
      groupOrder: 10,
      isReadonly: true,
    });
    setStore([advisory]);
    render(<GameTweaksTab />);

    expect(screen.getByText("Detected Only")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /apply all/i }),
    ).not.toBeInTheDocument();
  });

  it("leaves out a setting nothing has been read for", () => {
    // "Not ideal" is unknown before detection answers; either band would be a claim.
    setStore(
      [
        makeSetting({
          id: "game_config:mw4:shadow_quality" as `${string}:${string}`,
          displayName: "Shadow Quality",
          groupId: "mw4",
          groupLabel: "Modern Warfare IV",
          currentValue: null,
          status: "loading",
        }),
      ],
      true,
    );
    render(<GameTweaksTab />);

    expect(screen.queryByText("Shadow Quality")).not.toBeInTheDocument();
    expect(screen.queryByText("Modern Warfare IV")).not.toBeInTheDocument();
  });

  it("says no game was found rather than claiming everything is applied", () => {
    setStore([]);
    render(<GameTweaksTab />);

    expect(screen.getByText(/No supported game config was found/i)).toBeInTheDocument();
  });

  it("ignores settings that are not a game's config line", () => {
    const windowsTweak = makeSetting({
      id: "system:gamedvr" as `${string}:${string}`,
      displayName: "Game DVR",
      category: "system",
    });
    setStore([windowsTweak]);
    render(<GameTweaksTab />);

    expect(screen.queryByText("Game DVR")).not.toBeInTheDocument();
  });
});

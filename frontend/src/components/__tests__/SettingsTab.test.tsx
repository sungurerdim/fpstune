/**
 * The Optimizations tab must show a suboptimal tweak, and let it be fixed, without
 * anything being expanded.
 *
 * The shape this replaces put four levels between the user and a setting — band ->
 * category -> module card -> expand — so a 1600px screen showed six module cards and
 * zero actual tweaks. These tests pin the property that made that a defect, not the
 * markup that happened to fix it: a tweak that needs attention is readable and
 * actionable on first render.
 *
 * They also pin the advisory case, which is the reason this surface exists at all.
 * `is_readonly` settings are the ones fpstune can observe and cannot write (a link
 * negotiated below the adapter's capability, an XMP profile left off). They must be
 * visible — a diagnostic nobody can find is the same as no diagnostic — and they must
 * never be counted into a button that promises a write.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { SettingsTab } from "../SettingsTab";
import { useStore } from "../../store";
import type { CategoryMetadata, ModuleMetadata, Setting } from "../../types/setting";
import { Wifi } from "lucide-react";

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
    ...over,
  } as Setting;
}

const NETWORK: CategoryMetadata = {
  id: "network",
  displayName: "Network",
  description: "TCP/IP and adapter tuning",
  icon: "Wifi",
  color: "text-blue-500",
  isActionOnly: false,
  order: 1,
};

const SYSTEM: CategoryMetadata = {
  id: "system",
  displayName: "System Tuning",
  description: "Services and background processes",
  icon: "Settings",
  color: "text-gray-500",
  isActionOnly: false,
  order: 2,
};

const MODULES = new Map<string, ModuleMetadata>([
  ["network", { id: "network", displayName: "Network", description: "", order: 1 }],
  ["system", { id: "system", displayName: "Windows", description: "", order: 2 }],
]);

function renderTab(
  groups: Array<{ category: CategoryMetadata; settings: Setting[] }>,
) {
  return render(
    <SettingsTab
      categoriesWithSettings={groups}
      moduleMetaMap={MODULES}
      definitionsLoading={false}
      gpuCategoryStatus="done"
      hasGpuSettings={false}
      getIconByName={() => Wifi}
    />,
  );
}

describe("SettingsTab flat list", () => {
  beforeEach(() => {
    applyMock.mockClear();
    useStore.setState({
      settings: new Map(),
      selectedSettingIds: new Set(),
      operationStatus: {},
      categoryDetectionStatus: {},
    } as never);
  });

  it("shows a suboptimal tweak's current and target value on first render", () => {
    const s = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      displayName: "Nagle's Algorithm",
    });
    renderTab([{ category: NETWORK, settings: [s] }]);

    // Visible without expanding anything — no click, no accordion.
    expect(screen.getByText("Nagle's Algorithm")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("Target")).toBeInTheDocument();
  });

  it("puts optimized tweaks behind a collapsed band so they cannot drown the rest", async () => {
    const bad = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      displayName: "Nagle's Algorithm",
    });
    const good = makeSetting({
      id: "network:rss" as `${string}:${string}`,
      displayName: "Receive Side Scaling",
      currentValue: "disabled",
      isOptimized: true,
      status: "optimal",
    });
    renderTab([{ category: NETWORK, settings: [bad, good] }]);

    expect(screen.getByText("Nagle's Algorithm")).toBeInTheDocument();
    expect(screen.queryByText("Receive Side Scaling")).not.toBeInTheDocument();

    await userEvent.click(screen.getByText("Optimized"));
    expect(screen.getByText("Receive Side Scaling")).toBeInTheDocument();
  });

  it("shows an advisory but never counts it into Fix all", async () => {
    // The link-speed case: fpstune can read it and cannot write it. Counting it
    // would make the button promise a write it cannot perform.
    const fixable = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      displayName: "Nagle's Algorithm",
    });
    const advisory = makeSetting({
      id: "system:xmp_expo" as `${string}:${string}`,
      displayName: "XMP / EXPO Memory Profile",
      category: "system",
      isReadonly: true,
      currentValue: "disabled",
      recommendedValue: "enabled",
    });
    renderTab([
      { category: NETWORK, settings: [fixable] },
      { category: SYSTEM, settings: [advisory] },
    ]);

    expect(screen.getByText("XMP / EXPO Memory Profile")).toBeInTheDocument();
    expect(screen.getByText("Advisory")).toBeInTheDocument();

    const fixAll = screen.getByRole("button", { name: /fix all/i });
    expect(fixAll).toHaveTextContent("Fix all 1");

    await userEvent.click(fixAll);
    expect(applyMock).toHaveBeenCalledWith({ "network:nagle": "disabled" });
  });

  it("filters by the kind of gain, not just the subsystem", async () => {
    // The dashboard header counted "latency tweaks" while this screen offered
    // no way to see which rows those were.
    const lat = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      displayName: "Nagle's Algorithm",
      impactCategories: ["latency"],
    });
    const fps = makeSetting({
      id: "system:gamedvr" as `${string}:${string}`,
      displayName: "Game DVR",
      category: "system",
      impactCategories: ["fps"],
    });
    renderTab([
      { category: NETWORK, settings: [lat] },
      { category: SYSTEM, settings: [fps] },
    ]);

    expect(screen.getByText("Nagle's Algorithm")).toBeInTheDocument();
    expect(screen.getByText("Game DVR")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /^Latency/ }));

    expect(screen.getByText("Nagle's Algorithm")).toBeInTheDocument();
    expect(screen.queryByText("Game DVR")).not.toBeInTheDocument();
  });

  it("clears the impact filter when the active chip is clicked again", async () => {
    const lat = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      displayName: "Nagle's Algorithm",
      impactCategories: ["latency"],
    });
    const fps = makeSetting({
      id: "system:gamedvr" as `${string}:${string}`,
      displayName: "Game DVR",
      category: "system",
      impactCategories: ["fps"],
    });
    renderTab([
      { category: NETWORK, settings: [lat] },
      { category: SYSTEM, settings: [fps] },
    ]);

    const chip = screen.getByRole("button", { name: /^Latency/ });
    await userEvent.click(chip);
    expect(screen.queryByText("Game DVR")).not.toBeInTheDocument();
    await userEvent.click(chip);
    expect(screen.getByText("Game DVR")).toBeInTheDocument();
  });

  it("offers no chip for an impact no visible setting has", () => {
    const lat = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      impactCategories: ["latency"],
    });
    renderTab([{ category: NETWORK, settings: [lat] }]);

    // A chip that empties the list is worse than no chip.
    expect(screen.getByRole("button", { name: /^Latency/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Storage/ })).not.toBeInTheDocument();
  });

  it("scopes Fix all to the rows the category filter leaves on screen", async () => {
    const net = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      displayName: "Nagle's Algorithm",
    });
    const sys = makeSetting({
      id: "system:gamedvr" as `${string}:${string}`,
      displayName: "Game DVR",
      category: "system",
    });
    renderTab([
      { category: NETWORK, settings: [net] },
      { category: SYSTEM, settings: [sys] },
    ]);

    expect(screen.getByRole("button", { name: /fix all/i })).toHaveTextContent(
      "Fix all 2",
    );

    await userEvent.selectOptions(
      screen.getByLabelText("Filter by category"),
      "system",
    );

    expect(screen.queryByText("Nagle's Algorithm")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /fix all/i }));
    expect(applyMock).toHaveBeenCalledWith({ "system:gamedvr": "disabled" });
  });

  it("offers no Fix all when every visible row is an advisory", () => {
    const advisory = makeSetting({
      id: "system:xmp_expo" as `${string}:${string}`,
      displayName: "XMP / EXPO Memory Profile",
      category: "system",
      isReadonly: true,
      currentValue: "disabled",
      recommendedValue: "enabled",
    });
    renderTab([{ category: SYSTEM, settings: [advisory] }]);

    // A button that can act on nothing is a control that lies about its scope.
    expect(
      screen.queryByRole("button", { name: /fix all/i }),
    ).not.toBeInTheDocument();
  });

  it("says where a row came from, since no card is left to say it", () => {
    const s = makeSetting({
      id: "system:gamedvr" as `${string}:${string}`,
      displayName: "Game DVR",
      category: "system",
    });
    renderTab([{ category: SYSTEM, settings: [s] }]);

    expect(screen.getByText("System Tuning · Windows")).toBeInTheDocument();
  });

  it("leaves a game's config line to the Game Tweaks tab", () => {
    // The invariant: each list surface excludes the domains it does not own, or
    // one setting is counted twice. 181 of the registry's settings are game
    // config lines, and every one of them used to land here.
    const windows = makeSetting({
      id: "system:gamedvr" as `${string}:${string}`,
      displayName: "Game DVR",
      category: "system",
    });
    const game = makeSetting({
      id: "game_config:mw4:shadow_quality" as `${string}:${string}`,
      displayName: "MW4 Shadow Quality",
      category: "system",
      groupId: "mw4",
      groupLabel: "Modern Warfare IV",
    });
    renderTab([{ category: SYSTEM, settings: [windows, game] }]);

    expect(screen.getByText("Game DVR")).toBeInTheDocument();
    expect(screen.queryByText("MW4 Shadow Quality")).not.toBeInTheDocument();
    // And the bulk button counts what is on screen, not what was filtered out.
    expect(screen.getByRole("button", { name: /fix all/i })).toHaveTextContent(
      "Fix all 1",
    );
  });

  it("leaves out a setting nothing has been read for", () => {
    // "Not ideal" is unknown before detection answers; either band would be a claim.
    const s = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      displayName: "Nagle's Algorithm",
      currentValue: null,
      status: "loading",
    });
    renderTab([{ category: NETWORK, settings: [s] }]);

    expect(screen.queryByText("Nagle's Algorithm")).not.toBeInTheDocument();
    expect(screen.getByText(/Nothing needs optimization/i)).toBeInTheDocument();
  });
});

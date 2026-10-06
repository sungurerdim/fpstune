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
import { metricChip, render, screen } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { SettingsTab } from "../SettingsTab";
import { useStore } from "../../store";
import type { CategoryMetadata, ModuleMetadata, Setting } from "../../types/setting";
import { Wifi } from "lucide-react";

const runMock = vi.fn();
vi.mock("../../hooks/useBulkStream", () => ({
  useBulkStream: () => ({
    run: (action: string, ids: string[]) => runMock(action, ids),
    stop: vi.fn(),
    isRunning: false,
  }),
}));

/** The page-scope Apply, which counts exactly the rows the filters leave on screen. */
const pageApply = () => screen.getByRole("button", { name: /^Apply \d+ tweaks: Software Tweaks$/ });

/** Press a page action and answer its confirmation. */
async function confirmPageApply() {
  await userEvent.click(pageApply());
  await userEvent.click(screen.getByRole("button", { name: "Apply" }));
}

function makeSetting(over: Partial<Setting> & Pick<Setting, "id">): Setting {
  return {
    module: over.id.split(":")[0],
    domain: over.id.startsWith("game_config:") ? "game" : "software",
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
    runMock.mockClear();
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

    await userEvent.click(screen.getByRole("button", { name: /show 1 already ideal/i }));
    expect(screen.getByText("Receive Side Scaling")).toBeInTheDocument();
  });

  it("shows an advisory but never counts it into the page's Apply", async () => {
    // The link-speed case: fpstune can read it and cannot write it. Counting it
    // would make the button promise a write it cannot perform.
    const fixable = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      displayName: "Nagle's Algorithm",
    });
    const advisory = makeSetting({
      // A software advisory: XMP used to stand in here, but it is a memory
      // finding and belongs to the Hardware tab.
      id: "system:startup_apps" as `${string}:${string}`,
      displayName: "Startup apps",
      category: "system",
      isReadonly: true,
      currentValue: "apps_at_startup",
      recommendedValue: "none_at_startup",
    });
    renderTab([
      { category: NETWORK, settings: [fixable] },
      { category: SYSTEM, settings: [advisory] },
    ]);

    expect(screen.getByText("Startup apps")).toBeInTheDocument();
    expect(screen.getByText("Advisory")).toBeInTheDocument();

    expect(pageApply()).toHaveTextContent("Apply (1)");

    await confirmPageApply();
    expect(runMock).toHaveBeenCalledWith("apply", ["network:nagle"]);
  });

  it("labels each row with what it improves instead of a second filter", () => {
    const lat = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      displayName: "Nagle's Algorithm",
      impactCategories: ["latency"],
    });
    const { container } = renderTab([{ category: NETWORK, settings: [lat] }]);

    // The label is on the row; the only filter bar is the category chips.
    expect(container.querySelector('[data-category="latency"]')).toHaveTextContent("Latency");
    expect(screen.queryByRole("group", { name: /impact/i })).not.toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Filter by category" })).toBeInTheDocument();
  });

  it("puts rows under their category heading, each with its own count", () => {
    const net = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      displayName: "Nagle's Algorithm",
    });
    const ok = makeSetting({
      id: "network:rss" as `${string}:${string}`,
      displayName: "Receive Side Scaling",
      isOptimized: true,
      status: "optimal",
    });
    renderTab([{ category: NETWORK, settings: [net, ok] }]);

    const section = screen.getByRole("region", { name: "Network" });
    expect(metricChip("1 to fix", section)).toBeInTheDocument();
    expect(metricChip("2 total", section)).toBeInTheDocument();
  });

  it("scopes a heading's actions to its own category", async () => {
    // Both rows differ from the Windows default; only the heading's own may move.
    const net = makeSetting({
      id: "network:nagle" as `${string}:${string}`,
      displayName: "Nagle's Algorithm",
      defaultValue: "auto",
    });
    const sys = makeSetting({
      id: "system:gamedvr" as `${string}:${string}`,
      displayName: "Game DVR",
      category: "system",
      defaultValue: "auto",
    });
    renderTab([
      { category: NETWORK, settings: [net] },
      { category: SYSTEM, settings: [sys] },
    ]);

    await userEvent.click(
      screen.getByRole("button", { name: "Reset 1 settings to the Windows default: System Tuning" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset to default" }));
    expect(runMock).toHaveBeenCalledWith("reset", ["system:gamedvr"]);
  });

  it("offers no chip for a category the search has emptied", async () => {
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

    await userEvent.type(screen.getByRole("searchbox"), "nagle");
    // A chip that empties the list is worse than no chip.
    expect(screen.getByRole("button", { name: /^Network/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^System Tuning/ })).not.toBeInTheDocument();
  });

  it("scopes the page's Apply to the rows the category filter leaves on screen", async () => {
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

    expect(pageApply()).toHaveTextContent("Apply (2)");

    await userEvent.click(screen.getByRole("button", { name: /^System Tuning/ }));

    expect(screen.queryByText("Nagle's Algorithm")).not.toBeInTheDocument();
    await confirmPageApply();
    expect(runMock).toHaveBeenCalledWith("apply", ["system:gamedvr"]);
  });

  it("disables the page action, naming why, when every visible row is an advisory", () => {
    const advisory = makeSetting({
      // A software advisory: XMP used to stand in here, but it is a memory
      // finding and belongs to the Hardware tab.
      id: "system:startup_apps" as `${string}:${string}`,
      displayName: "Startup apps",
      category: "system",
      isReadonly: true,
      currentValue: "apps_at_startup",
      recommendedValue: "none_at_startup",
    });
    renderTab([{ category: SYSTEM, settings: [advisory] }]);

    // A button that can act on nothing is a control that lies about its scope:
    // it stays where it always is, disabled, and its name says why.
    expect(screen.getByText("Startup apps")).toBeInTheDocument();
    const apply = screen.getByRole("button", {
      name: "Apply: nothing to apply in Software Tweaks",
    });
    expect(apply).toBeDisabled();
    expect(screen.queryByRole("button", { name: /^Apply \d+ tweaks: Software Tweaks$/ })).not.toBeInTheDocument();
  });

  it("names the module on a row only where the heading does not already say it", () => {
    const s = makeSetting({
      id: "system:gamedvr" as `${string}:${string}`,
      displayName: "Game DVR",
      category: "system",
    });
    renderTab([{ category: SYSTEM, settings: [s] }]);

    expect(screen.getByRole("heading", { name: "System Tuning" })).toBeInTheDocument();
    expect(screen.getByText("Windows")).toBeInTheDocument();
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
    expect(pageApply()).toHaveTextContent("Apply (1)");
  });

  it("leaves a power-plan key that acts on hardware to the Hardware tab", () => {
    // PCIe link power saving is written by powercfg, yet it slows the GPU and
    // NVMe link — the category is the component it acts on, not how it is set.
    const plan = makeSetting({
      id: "power:hibernation" as `${string}:${string}`,
      displayName: "Hibernation",
      category: "system",
    });
    const pcie = makeSetting({
      id: "power:pcie_link_state" as `${string}:${string}`,
      displayName: "PCIe Link State Power Management",
      category: "system",
      domain: "hardware",
      component: "pcie",
    });
    renderTab([{ category: SYSTEM, settings: [plan, pcie] }]);

    expect(screen.getByText("Hibernation")).toBeInTheDocument();
    expect(screen.queryByText("PCIe Link State Power Management")).not.toBeInTheDocument();
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
    expect(screen.getByText(/Nothing to do here/i)).toBeInTheDocument();
  });
});

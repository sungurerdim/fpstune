/**
 * The Optimize tab answers one question — what is not optimized — and puts the
 * fix beside the answer.
 *
 * These pin the properties that made earlier shapes of this page defects, not
 * the markup that happens to hold them: a closed page already says how much is
 * left, a tweak lands in exactly one category and never two (181 game config
 * lines once counted as software), a game is a section of its own headed by the
 * backend's word for it, an advisory is shown and never counted into a button
 * that promises a write, and applying a row does not slide the next one away.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { OptimizeTab } from "../OptimizeTab";
import { useStore } from "../../store";
import { api, type HardwareInfo } from "../../lib/api";
import type { CategoryMetadata, Setting } from "../../types/setting";

const runMock = vi.fn();
const applyMock = vi.fn();
vi.mock("../../hooks/useApply", () => ({
  useApply: () => ({
    run: (action: string, ids: string[]) => runMock(action, ids),
    apply: (setting: Setting, value: unknown) => applyMock(setting.id, value),
    reset: vi.fn(),
    stop: vi.fn(),
    pendingIds: new Set<string>(),
    isPending: () => false,
    isRunning: false,
  }),
}));

const machine = vi.hoisted(() => ({
  hardware: {
    cpu: { name: "Example CPU", physical_cores: 8, logical_cores: 16, architecture: "x64" },
    gpus: [{ vendor: "NVIDIA", name: "Example GPU", vram_mb: 8192 }],
    monitors: [],
    network_adapters: [],
    storage_drives: [],
    audio_devices: [],
    detecting: false,
  } as unknown as HardwareInfo,
}));
vi.mock("../hardware/useHardware", () => ({
  useHardware: () => ({ hardware: machine.hardware, isLoading: false }),
}));
vi.mock("../hardware/useRefreshOnFocus", () => ({ useRefreshOnFocus: () => undefined }));

function makeSetting(over: Partial<Setting> & Pick<Setting, "id">): Setting {
  return {
    module: over.id.split(":")[0],
    domain: over.id.startsWith("game_config:") ? "game" : "software",
    name: over.id.split(":").slice(1).join(":"),
    displayName: over.id,
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

const id = (value: string) => value as Setting["id"];
const optimal = (over: Partial<Setting> & Pick<Setting, "id">) =>
  makeSetting({ currentValue: "disabled", status: "optimal", isOptimized: true, ...over });

const NETWORK = { id: "network", displayName: "Network", order: 1 } as CategoryMetadata;
const SYSTEM = { id: "system", displayName: "System Tuning", order: 2 } as CategoryMetadata;

function seed(settings: Setting[]) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    categories: new Map([NETWORK, SYSTEM].map((c) => [c.id, c])),
    selectedSettingIds: new Set(),
    operationStatus: {},
    operationError: {},
    categoryDetectionStatus: { core: "done" },
  } as never);
}

const header = (name: RegExp | string) => screen.getByRole("button", { name });

/** Open every closed category, device and game on the page, level after level. */
function openAll() {
  for (let pass = 0; pass < 4; pass += 1) {
    for (const closed of document.querySelectorAll('h2 [aria-expanded="false"], h3 [aria-expanded="false"]')) {
      fireEvent.click(closed);
    }
  }
}

const rowNames = () =>
  screen.getAllByTestId("tweak-row").map((row) => within(row).getByRole("checkbox").getAttribute("aria-label"));

const asAdmin = (is_admin: boolean) =>
  vi.spyOn(api, "getSystemInfo").mockResolvedValue({ is_admin } as Awaited<ReturnType<typeof api.getSystemInfo>>);

beforeEach(() => {
  runMock.mockClear();
  applyMock.mockClear();
  vi.restoreAllMocks();
  asAdmin(true);
  seed([]);
});

describe("the closed page", () => {
  it("is three lines, each already saying how much of it is not optimized", () => {
    seed([
      makeSetting({ id: id("network:nagle") }),
      optimal({ id: id("network:rss") }),
      makeSetting({ id: id("game_config:mw4:shadow"), groupId: "mw4", groupLabel: "Modern Warfare IV" }),
      makeSetting({ id: id("gpu-hardware:hags"), domain: "hardware", component: "gpu" }),
    ]);
    render(<OptimizeTab />);

    expect(header(/^Software/)).toHaveAccessibleName("Software 1 of 2 not optimized");
    expect(header(/^Hardware/)).toHaveAccessibleName("Hardware 1 of 1 not optimized");
    expect(header(/^Games/)).toHaveAccessibleName("Games 1 of 1 not optimized");
    // Nothing is expanded: no row is on screen until a category is asked for.
    expect(screen.queryAllByTestId("tweak-row")).toHaveLength(0);
    for (const section of screen.getAllByRole("heading", { level: 2 })) {
      expect(within(section).getByRole("button")).toHaveAttribute("aria-expanded", "false");
    }
  });

  it("says it is reading, not 'nothing to do', while detection has answered for nothing yet", () => {
    seed([makeSetting({ id: id("network:nagle"), currentValue: null, status: "loading" })]);
    render(<OptimizeTab />);

    expect(header(/^Software/)).toHaveAccessibleName("Software Reading…");
  });
});

describe("a category opens to its own rows, not-optimized ones first", () => {
  it("lists what needs work above what is already right, and shows current and target at once", async () => {
    seed([
      optimal({ id: id("network:rss"), displayName: "Receive Side Scaling" }),
      makeSetting({ id: id("network:nagle"), displayName: "Nagle's Algorithm" }),
    ]);
    render(<OptimizeTab />);

    await userEvent.click(header(/^Software/));
    await userEvent.click(header(/^Network/));

    expect(rowNames()).toEqual(["Select Nagle's Algorithm", "Select Receive Side Scaling"]);
    expect(screen.getByRole("button", { name: "Apply Nagle's Algorithm" })).toBeInTheDocument();
  });

  it("keeps a row where it was after it is applied, so the next click lands on the same row", async () => {
    seed([
      makeSetting({ id: id("network:a"), displayName: "Alpha" }),
      makeSetting({ id: id("network:b"), displayName: "Beta" }),
    ]);
    render(<OptimizeTab />);
    await userEvent.click(header(/^Software/));
    await userEvent.click(header(/^Network/));
    expect(rowNames()).toEqual(["Select Alpha", "Select Beta"]);

    // The backend now says Alpha is optimized.
    useStore.setState({
      settings: new Map([
        [id("network:a"), optimal({ id: id("network:a"), displayName: "Alpha" })],
        [id("network:b"), makeSetting({ id: id("network:b"), displayName: "Beta" })],
      ]),
      _settingsVersion: useStore.getState()._settingsVersion + 1,
    } as never);

    expect(await screen.findByRole("button", { name: "Apply Beta" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply Alpha" })).not.toBeInTheDocument();
    expect(rowNames()).toEqual(["Select Alpha", "Select Beta"]);
  });

  it("writes the recommended value when a row's Apply is pressed", async () => {
    seed([makeSetting({ id: id("network:nagle"), displayName: "Nagle's Algorithm" })]);
    render(<OptimizeTab />);
    await userEvent.click(header(/^Software/));
    await userEvent.click(header(/^Network/));

    await userEvent.click(screen.getByRole("button", { name: "Apply Nagle's Algorithm" }));

    expect(applyMock).toHaveBeenCalledWith("network:nagle", "disabled");
  });

  it("puts each category under the backend's heading, with its own count", async () => {
    seed([
      makeSetting({ id: id("network:nagle") }),
      optimal({ id: id("network:rss") }),
      makeSetting({ id: id("system:gamedvr"), category: "system" as Setting["category"] }),
    ]);
    render(<OptimizeTab />);
    await userEvent.click(header(/^Software/));

    expect(header(/^Network/)).toHaveAccessibleName("Network 1 of 2 not optimized");
    expect(header(/^System Tuning/)).toHaveAccessibleName("System Tuning 1 of 1 not optimized");
  });
});

describe("what a closed page costs", () => {
  it("draws no row at all for a registry of hundreds, and none when one of them changes", async () => {
    // The render budget of the old flat lists ("one change re-renders one row,
    // not four hundred") holds here by construction: a closed category draws
    // nothing, so a change to a row nobody opened costs the page no row.
    const many = Array.from({ length: 400 }, (_, n) =>
      makeSetting({ id: id(`network:tweak_${n}`), displayName: `Tweak ${n}` }),
    );
    seed(many);
    render(<OptimizeTab />);
    expect(screen.queryAllByTestId("tweak-row")).toHaveLength(0);

    useStore.setState({
      settings: new Map(
        many.map((s) => [s.id, s.id === "network:tweak_7" ? optimal({ id: s.id }) : s]),
      ),
      _settingsVersion: useStore.getState()._settingsVersion + 1,
    } as never);

    expect(await screen.findByRole("button", { name: "Software 399 of 400 not optimized" })).toBeInTheDocument();
    expect(screen.queryAllByTestId("tweak-row")).toHaveLength(0);
  });

  it("draws only the rows of the category that was opened", async () => {
    seed([
      ...Array.from({ length: 30 }, (_, n) => makeSetting({ id: id(`network:tweak_${n}`) })),
      ...Array.from({ length: 30 }, (_, n) =>
        makeSetting({ id: id(`system:tweak_${n}`), category: "system" as Setting["category"] }),
      ),
    ]);
    render(<OptimizeTab />);
    await userEvent.click(header(/^Software/));
    await userEvent.click(header(/^Network/));

    expect(screen.getAllByTestId("tweak-row")).toHaveLength(30);
  });
});

describe("a tweak is in exactly one category", () => {
  it("leaves a game's config line to Games, and a hardware key to Hardware", () => {
    // The invariant the old tabs each enforced by hand: a surface excludes the
    // domains it does not own, or one setting is counted twice.
    const windows = makeSetting({ id: id("system:gamedvr"), displayName: "Game DVR", category: "system" as Setting["category"] });
    const game = makeSetting({
      id: id("game_config:mw4:shadow_quality"),
      displayName: "MW4 Shadow Quality",
      category: "system" as Setting["category"],
      groupId: "mw4",
      groupLabel: "Modern Warfare IV",
    });
    const pcie = makeSetting({
      id: id("power:pcie_link_state"),
      displayName: "PCIe Link State Power Management",
      category: "system" as Setting["category"],
      domain: "hardware",
      component: "pcie",
    });
    seed([windows, game, pcie]);
    render(<OptimizeTab />);
    openAll();

    const section = (name: RegExp) =>
      within(
        screen.getByRole("heading", { level: 2, name }).closest<HTMLElement>('[data-testid="category-section"]')!,
      );
    expect(section(/^Software/).getByText("Game DVR")).toBeInTheDocument();
    expect(section(/^Software/).queryByText("MW4 Shadow Quality")).not.toBeInTheDocument();
    expect(section(/^Software/).queryByText("PCIe Link State Power Management")).not.toBeInTheDocument();
    expect(section(/^Games/).getByText("MW4 Shadow Quality")).toBeInTheDocument();
    expect(section(/^Hardware/).getByText("PCIe Link State Power Management")).toBeInTheDocument();
  });

  it("renders every setting once across all three categories, advisories that found nothing included", () => {
    const all = [
      makeSetting({ id: id("network:nagle"), displayName: "Nagle's Algorithm" }),
      optimal({ id: id("network:rss"), displayName: "Receive Side Scaling" }),
      makeSetting({ id: id("system:gamedvr"), displayName: "Game DVR", category: "system" as Setting["category"] }),
      makeSetting({ id: id("gpu-hardware:hags"), displayName: "Hardware Scheduling", domain: "hardware", component: "gpu" }),
      makeSetting({ id: id("power:pcie_link_state"), displayName: "PCIe Link State", domain: "hardware", component: "pcie" }),
      // Claimed by no device the machine has: still on the page, not dropped.
      makeSetting({ id: id("display:monzzzz:refresh"), displayName: "Refresh Rate", domain: "hardware", component: "display" }),
      makeSetting({ id: id("game_config:mw4:shadow"), displayName: "Shadow Quality", groupId: "mw4", groupLabel: "Modern Warfare IV" }),
      makeSetting({ id: id("game_config:cs2:fps_max"), displayName: "FPS Max", groupId: "cs2", groupLabel: "Counter-Strike 2" }),
      // Read-only checks: one that found nothing, one that read nothing, one on a device.
      optimal({ id: id("system:xmp_ok"), displayName: "XMP profile", isReadonly: true, category: "system" as Setting["category"] }),
      makeSetting({
        id: id("system:thermal_zones"),
        displayName: "Thermal zones",
        isReadonly: true,
        category: "system" as Setting["category"],
        currentValue: null,
        status: "default",
      }),
      makeSetting({
        id: id("gpu-hardware:rebar"),
        displayName: "Resizable BAR",
        domain: "hardware",
        component: "gpu",
        isReadonly: true,
        currentValue: null,
        status: "default",
      }),
    ];
    seed(all);
    render(<OptimizeTab />);
    openAll();
    // Manual steps are folded away inside each list: open those too.
    for (const manual of screen.queryAllByRole("button", { name: /^Manual steps/ })) fireEvent.click(manual);

    // One device is open at a time, so the device rows are read device by device.
    const inDevices = (row: HTMLElement) => row.closest('[aria-label="Devices"]') !== null;
    const names = (rows: HTMLElement[]) => rows.map((row) => row.querySelector("[title]")!.getAttribute("title")!);
    const drawn = names(screen.queryAllByTestId("tweak-row").filter((row) => !inDevices(row)));
    const devices = within(screen.getByRole("list", { name: "Devices" })).getAllByRole("heading", { level: 3 });
    for (const device of devices.map((heading) => within(heading).getByRole("button"))) {
      // The last device is left open by `openAll`: close it, then open this one.
      if (device.getAttribute("aria-expanded") === "true") fireEvent.click(device);
      fireEvent.click(device);
      for (const manual of screen.queryAllByRole("button", { name: /^Manual steps/ })) {
        if (manual.getAttribute("aria-expanded") === "false") fireEvent.click(manual);
      }
      drawn.push(...names(screen.queryAllByTestId("tweak-row").filter(inDevices)));
    }

    expect(drawn.sort()).toEqual(all.map((s) => s.displayName).sort());
  });

  it("leaves out a setting nothing has been read for", () => {
    // "Not ideal" is unknown before detection answers; listing it is a claim.
    seed([makeSetting({ id: id("network:nagle"), displayName: "Nagle's Algorithm", currentValue: null, status: "default" })]);
    render(<OptimizeTab />);
    openAll();

    expect(screen.queryByText("Nagle's Algorithm")).not.toBeInTheDocument();
  });
});

describe("a check that read nothing says so on its line", () => {
  const unread = makeSetting({
    id: id("system:thermal_zones"),
    displayName: "Thermal zones",
    category: "system" as Setting["category"],
    isReadonly: true,
    currentValue: null,
    status: "default",
  });

  const open = async () => {
    render(<OptimizeTab />);
    await userEvent.click(header(/^Software/));
    await userEvent.click(header(/^System Tuning/));
    await userEvent.click(screen.getByRole("button", { name: "Manual steps (1)" }));
  };

  it("names elevation as the likely reason when fpstune is not elevated", async () => {
    asAdmin(false);
    seed([unread]);
    await open();

    expect(await screen.findByText(/not running as Administrator/)).toBeInTheDocument();
  });

  it("gives the detector's own reason when it had one", async () => {
    seed([{ ...unread, detectionError: "WMI timed out" } as Setting]);
    await open();

    expect(screen.getByText("Nothing was read: WMI timed out")).toBeInTheDocument();
  });

  it("says nothing was read, without a guess, when there is no reason to give", async () => {
    seed([unread]);
    await open();

    expect(await screen.findByText(/there is no finding here to act on/)).toBeInTheDocument();
    expect(screen.queryByText(/Administrator/)).not.toBeInTheDocument();
  });

  it("never counts it: it is not a tweak", () => {
    seed([unread, makeSetting({ id: id("system:gamedvr"), category: "system" as Setting["category"] })]);
    render(<OptimizeTab />);

    expect(header(/^Software/)).toHaveAccessibleName("Software 1 of 1 not optimized");
  });
});

describe("Hardware is a list of devices", () => {
  it("lists the machine's devices and opens one to its own rows", async () => {
    seed([
      makeSetting({ id: id("gpu-hardware:hags"), displayName: "Hardware Scheduling", domain: "hardware", component: "gpu" }),
      makeSetting({ id: id("cpu:parking"), displayName: "Core Parking", domain: "hardware", component: "cpu" }),
    ]);
    render(<OptimizeTab />);
    await userEvent.click(header(/^Hardware/));

    expect(screen.queryByText("Hardware Scheduling")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Example GPU/ }));

    expect(screen.getByText("Hardware Scheduling")).toBeInTheDocument();
    expect(screen.queryByText("Core Parking")).not.toBeInTheDocument();
  });

  it("counts the not-optimized rows of the whole category on its own closed line", () => {
    seed([
      makeSetting({ id: id("gpu-hardware:hags"), domain: "hardware", component: "gpu" }),
      makeSetting({ id: id("cpu:parking"), domain: "hardware", component: "cpu" }),
      optimal({ id: id("cpu:boost"), domain: "hardware", component: "cpu" }),
    ]);
    render(<OptimizeTab />);

    expect(header(/^Hardware/)).toHaveAccessibleName("Hardware 2 of 3 not optimized");
  });
});

describe("Games is one section per game", () => {
  const MW4 = makeSetting({
    id: id("game_config:mw4:shadow_quality"),
    displayName: "Shadow Quality",
    groupId: "mw4",
    groupLabel: "Modern Warfare IV",
    groupOrder: 10,
  });
  const CS2 = makeSetting({
    id: id("game_config:cs2:fps_max"),
    displayName: "FPS Max",
    groupId: "cs2",
    groupLabel: "Counter-Strike 2",
    groupOrder: 12,
  });

  it("heads each section with the name the backend sent", async () => {
    seed([MW4, CS2]);
    render(<OptimizeTab />);
    await userEvent.click(header(/^Games/));

    expect(header(/^Modern Warfare IV/)).toBeInTheDocument();
    expect(header(/^Counter-Strike 2/)).toBeInTheDocument();
  });

  it("never writes two games' files for one game's Apply", async () => {
    seed([MW4, CS2]);
    render(<OptimizeTab />);
    await userEvent.click(header(/^Games/));

    await userEvent.click(screen.getByRole("button", { name: "Apply 1 tweaks: Modern Warfare IV" }));
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(runMock).toHaveBeenCalledWith("apply", ["game_config:mw4:shadow_quality"]);
  });

  it("says no game was found rather than claiming everything is applied", async () => {
    seed([makeSetting({ id: id("network:nagle") })]);
    render(<OptimizeTab />);
    await userEvent.click(header(/^Games/));

    expect(screen.getByText(/No supported game config was found/i)).toBeInTheDocument();
  });

  it("says it is reading while the game configs are still being read", async () => {
    seed([makeSetting({ id: id("network:nagle") })]);
    useStore.setState({ categoryDetectionStatus: { core: "loading" } } as never);
    render(<OptimizeTab />);
    await userEvent.click(header(/^Games/));

    expect(screen.getByText("Reading your game configs…")).toBeInTheDocument();
  });
});

describe("an advisory is shown, and counted into nothing that writes", () => {
  const fixable = makeSetting({ id: id("network:nagle"), displayName: "Nagle's Algorithm" });
  // The link-speed case: fpstune can read it and cannot write it.
  const advisory = makeSetting({
    id: id("network:link_capability"),
    displayName: "Link speed",
    isReadonly: true,
    currentValue: "negotiated_below_capability",
    recommendedValue: "at_capability",
  });

  it("keeps it behind 'Manual steps', out of the count and out of the Apply", async () => {
    seed([fixable, advisory]);
    render(<OptimizeTab />);
    expect(header(/^Software/)).toHaveAccessibleName("Software 1 of 1 not optimized");

    await userEvent.click(header(/^Software/));
    await userEvent.click(header(/^Network/));
    expect(screen.queryByText("Link speed")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Manual steps (1)" }));
    expect(screen.getByText("Link speed")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Apply 1 tweaks: Network" }));
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(runMock).toHaveBeenCalledWith("apply", ["network:nagle"]);
  });

  it("offers no Apply at all for a category that holds only advisories", async () => {
    seed([advisory]);
    render(<OptimizeTab />);
    await userEvent.click(header(/^Software/));

    expect(screen.queryByRole("button", { name: /^Apply \d+ tweaks/ })).not.toBeInTheDocument();
  });
});

describe("bulk apply stays inside the category it is pressed on", () => {
  it("applies only that category's rows, not the page's", async () => {
    seed([
      makeSetting({ id: id("network:nagle") }),
      makeSetting({ id: id("system:gamedvr"), category: "system" as Setting["category"] }),
    ]);
    render(<OptimizeTab />);
    await userEvent.click(header(/^Software/));

    await userEvent.click(screen.getByRole("button", { name: "Apply 1 tweaks: System Tuning" }));
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(runMock).toHaveBeenCalledWith("apply", ["system:gamedvr"]);
  });

  it("applies the whole of Software from its own line", async () => {
    seed([
      makeSetting({ id: id("network:nagle") }),
      makeSetting({ id: id("system:gamedvr"), category: "system" as Setting["category"] }),
      makeSetting({ id: id("game_config:mw4:shadow"), groupId: "mw4", groupLabel: "Modern Warfare IV" }),
    ]);
    render(<OptimizeTab />);

    await userEvent.click(screen.getByRole("button", { name: "Apply 2 tweaks: Software" }));
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(runMock).toHaveBeenCalledWith("apply", ["network:nagle", "system:gamedvr"]);
  });
});

describe("search", () => {
  it("replaces the closed categories with the matching rows, open", async () => {
    seed([
      makeSetting({ id: id("network:nagle"), displayName: "Nagle's Algorithm" }),
      makeSetting({ id: id("system:gamedvr"), displayName: "Game DVR", category: "system" as Setting["category"] }),
      makeSetting({ id: id("game_config:mw4:shadow"), displayName: "Shadow Quality", groupId: "mw4", groupLabel: "Modern Warfare IV" }),
    ]);
    render(<OptimizeTab />);

    await userEvent.type(screen.getByRole("searchbox"), "nagle");

    expect(screen.getByText("Nagle's Algorithm")).toBeInTheDocument();
    expect(screen.queryByText("Game DVR")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Software/ })).not.toBeInTheDocument();
  });

  it("says when nothing matches", async () => {
    seed([makeSetting({ id: id("network:nagle"), displayName: "Nagle's Algorithm" })]);
    render(<OptimizeTab />);

    await userEvent.type(screen.getByRole("searchbox"), "zzzz");

    expect(screen.getByText("No setting matches that search.")).toBeInTheDocument();
  });

  it("finds a game's line by its own name too", async () => {
    seed([makeSetting({ id: id("game_config:mw4:shadow"), displayName: "Shadow Quality", groupId: "mw4", groupLabel: "Modern Warfare IV" })]);
    render(<OptimizeTab />);

    await userEvent.type(screen.getByRole("searchbox"), "shadow");

    expect(screen.getByText("Shadow Quality")).toBeInTheDocument();
  });
});

describe("the bar at the foot of the page", () => {
  it("applies the rows in view by level, and nothing of an advisory", async () => {
    seed([
      makeSetting({ id: id("network:nagle"), scope: "essential" }),
      makeSetting({ id: id("system:gamedvr"), category: "system" as Setting["category"], scope: "complete" }),
    ]);
    const restore = vi.spyOn(api, "createRestorePoint").mockResolvedValue({ success: true, message: "" });
    render(<OptimizeTab />);

    await userEvent.click(screen.getByRole("button", { name: "Apply recommended (1)" }));
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));

    // A page-wide write offers a restore point first, and takes it before it runs.
    await waitFor(() => expect(runMock).toHaveBeenCalledWith("apply", ["network:nagle"]));
    expect(restore).toHaveBeenCalledTimes(1);
  });
});

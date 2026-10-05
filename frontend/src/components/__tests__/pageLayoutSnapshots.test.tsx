/**
 * Each page's layout, pinned at a phone width and at an ultrawide one.
 *
 * `responsiveLayout.test.tsx` asserts single classes on single containers, so a
 * page that quietly lost a column grid elsewhere, or gained a stray `hidden`,
 * passes it. These snapshots hold the whole layout skeleton of a page — every
 * landmark, column grid, width cap and wrap — as the stylesheet resolves it at
 * 390px and at 2560px, so any change to how a page spreads across the window
 * shows up as a diff to be read and either accepted or fixed.
 *
 * The window is set the way a browser would report it (`innerWidth`, and a
 * `matchMedia` that answers width queries). The layout itself is Tailwind's
 * mobile-first breakpoints, which jsdom cannot evaluate, so `layoutOutline`
 * resolves them from each element's own classes; see `test/layoutOutline.ts`.
 * Text, ids and numbers are deliberately left out of the outline: a re-worded
 * heading is not a layout change, and nothing time- or id-dependent may enter a
 * snapshot.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, unmeasuredHeadroom } from "../../test/utils";
import { layoutOutline, setViewport } from "../../test/layoutOutline";
import { makeRunner } from "../../test/runner";
import { HomeTab } from "../HomeTab";
import { SettingsTab } from "../SettingsTab";
import { GameTweaksTab } from "../GameTweaksTab";
import { HardwarePanel } from "../HardwarePanel";
import { HistoryTab } from "../HistoryTab";
import { useStore } from "../../store";
import { Settings as SettingsIcon } from "lucide-react";
import type { HardwareInfo, HistoryResponse } from "../../lib/api";
import type { CategoryMetadata, Setting } from "../../types/setting";

const NARROW = 390;
const WIDE = 2560;

const inventory: HardwareInfo = {
  cpu: {
    name: "Example CPU 8-Core",
    physical_cores: 8,
    logical_cores: 16,
    architecture: "x64",
  },
  gpus: [{ vendor: "NVIDIA", name: "Example GPU", driver: "570.00", vram_mb: 8192 }],
  monitors: [
    {
      name: "\\\\.\\DISPLAY1",
      friendly_name: "Example Monitor",
      width: 2560,
      height: 1440,
      refresh_rate_hz: 165,
      is_primary: true,
      is_active: true,
      setting_key: "mon0a1b2c3d4e",
    },
  ],
  network_adapters: [
    {
      name: "Ethernet",
      description: "Example Ethernet Connection",
      adapter_type: "Ethernet",
      status: "Up",
      is_enabled: true,
      is_connected: true,
      dns_servers: [],
      interface_index: 12,
      instance_id: "PCI\\VEN_8086&DEV_15BC\\3&11583659&0&FE",
      setting_key: "nic0a1b2c3d4e",
    },
  ],
  storage_drives: [],
  audio_devices: [
    {
      id: "{0.0.0.00000000}.{9f0aa154-2c14-4bd0-a1b0-000000000000}",
      name: "Speakers (High Definition Audio)",
      device_type: "Playback",
      is_default: true,
      is_enabled: true,
      loudness_eq_supported: false,
      loudness_eq_enabled: false,
    },
  ],
  detecting: false,
};

const history: HistoryResponse = {
  settings: [
    {
      setting_id: "network:nagle_algorithm",
      last_action: "apply",
      value: "disabled",
      at: 1_759_650_000,
      can_undo: true,
      original_value: "enabled",
    },
    {
      setting_id: "power:hibernation",
      last_action: "undo",
      value: "on",
      at: 1_759_630_000,
      can_undo: false,
      original_value: null,
    },
  ],
  entries: [],
};

vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: {
    hasData: () => true,
    subscribe: () => () => undefined,
    getCached: () => inventory,
    getHardware: () => Promise.resolve(inventory),
  },
}));
vi.mock("../hardware/useRefreshOnFocus", () => ({
  useRefreshOnFocus: () => undefined,
}));
vi.mock("../hardware/PowerProfileCard", () => ({ PowerProfileCard: () => null }));
vi.mock("../CleanupRunnerProvider", () => ({ CleanupRunnerProvider: () => null }));
vi.mock("../SelfCheckNotice", () => ({ SelfCheckNotice: () => null }));
vi.mock("../../hooks/useCleanupRunner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../hooks/useCleanupRunner")>()),
  useCleanupRunner: () => makeRunner(),
}));
vi.mock("../../hooks/useBulkApply", () => ({
  useBulkApply: () => ({ apply: vi.fn(), isApplying: false, lastResult: null }),
}));
vi.mock("../../hooks/useApplySingle", () => ({
  useApplySingle: () => ({ applySingle: vi.fn(), isPending: () => false }),
}));
vi.mock("../../hooks/useBulkStream", () => ({
  useBulkStream: () => ({ run: vi.fn(), stop: vi.fn(), isRunning: false }),
}));
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, getSystemInfo: () => Promise.resolve(undefined) },
    headroomApi: { list: () => Promise.resolve({ headroom: unmeasuredHeadroom() }) },
    historyApi: { get: () => Promise.resolve(history) },
  };
});

function makeSetting(over: Partial<Setting> & Pick<Setting, "id">): Setting {
  return {
    module: over.id.split(":")[0],
    domain: over.id.startsWith("game_config:") ? "game" : "software",
    name: over.id.split(":").slice(1).join(":"),
    displayName: "A Tweak",
    description: "Controls how the machine behaves. It matters for frame rate.",
    impactCategories: [],
    category: "system",
    valueType: "choice",
    choices: ["Off", "On"],
    defaultValue: "On",
    recommendedValue: "Off",
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
    currentValue: "On",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    ...over,
  } as Setting;
}

function pair(prefix: string, over: Partial<Setting> = {}): Setting[] {
  return [1, 2].map((n) =>
    makeSetting({
      id: `${prefix}_${n}` as `${string}:${string}`,
      displayName: `Tweak ${n}`,
      ...over,
    }),
  );
}

function setStore(settings: Setting[]) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    selectedSettingIds: new Set(),
    maintenanceSelection: {},
    cleanupResults: {},
    runSteps: [],
    operationStatus: {},
    categoryDetectionStatus: { core: "success" },
  } as never);
}

const SYSTEM_CATEGORY = {
  id: "system",
  displayName: "System",
  description: "System tweaks",
  icon: "Settings",
  order: 1,
} as CategoryMetadata;

interface Page {
  name: string;
  /**
   * Whether the page has a layout that depends on the window. History is one
   * list in the flow at every width; saying so here makes the day it gains a
   * column grid a deliberate edit rather than a silent one.
   */
  adapts: boolean;
  /** Fills the store and renders; resolves once the page has what it will show. */
  mount: () => Promise<ReturnType<typeof render>>;
}

const PAGES: Page[] = [
  {
    name: "Home",
    adapts: true,
    mount: async () => {
      setStore([
        ...pair("system:home"),
        ...pair("system:advisory", {
          isReadonly: true,
          effect: "Move the cable to a Cat 6 run",
        }),
        ...pair("cleanup:cache", {
          isAction: true,
          category: "maintenance",
          currentValue: "ready|800 MB",
          groupId: "windows",
          groupLabel: "Windows",
          groupOrder: 1,
        }),
      ]);
      const view = render(<HomeTab />);
      await screen.findByTestId("home-advisory-grid");
      return view;
    },
  },
  {
    name: "Software",
    adapts: true,
    mount: async () => {
      const settings = pair("system:software");
      setStore(settings);
      const view = render(
        <SettingsTab
          categoriesWithSettings={[{ category: SYSTEM_CATEGORY, settings }]}
          moduleMetaMap={new Map()}
          definitionsLoading={false}
          gpuCategoryStatus="done"
          hasGpuSettings={false}
          getIconByName={() => SettingsIcon}
        />,
      );
      await screen.findAllByTestId("tweak-rows");
      return view;
    },
  },
  {
    name: "Hardware",
    adapts: true,
    mount: async () => {
      setStore([]);
      const view = render(<HardwarePanel />);
      await screen.findByRole("region", { name: "Example Monitor" });
      return view;
    },
  },
  {
    name: "Games",
    adapts: true,
    mount: async () => {
      setStore(
        pair("game_config:mw4:quality", {
          category: "game_config",
          groupId: "mw4",
          groupLabel: "Modern Warfare IV",
          groupOrder: 10,
        }),
      );
      const view = render(<GameTweaksTab />);
      await screen.findAllByTestId("tweak-rows");
      return view;
    },
  },
  {
    name: "History",
    adapts: false,
    mount: async () => {
      setStore([]);
      const view = render(<HistoryTab />);
      await screen.findByText(/Still changed by fpstune/);
      return view;
    },
  },
];

beforeEach(() => {
  setStore([]);
});

describe.each(PAGES)("$name page layout", ({ mount, adapts }) => {
  it.each([
    ["narrow", NARROW],
    ["wide", WIDE],
  ])("at a %s window (%ipx)", async (_label, width) => {
    setViewport(width);
    const { container } = await mount();

    expect(layoutOutline(container, window.innerWidth)).toMatchSnapshot();
  });

  it(adapts ? "changes shape between the narrow and the wide window" : "is the same at every width", async () => {
    // A page declared responsive whose two outlines are identical is either not
    // responsive or not being resolved, and the snapshot pair above says nothing.
    setViewport(NARROW);
    const { container } = await mount();

    const narrow = layoutOutline(container, NARROW).split("\n").slice(1);
    const wide = layoutOutline(container, WIDE).split("\n").slice(1);
    if (adapts) expect(wide).not.toEqual(narrow);
    else expect(wide).toEqual(narrow);
  });
});

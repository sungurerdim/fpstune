/**
 * Every page uses the width it is given.
 *
 * Reported by the owner: on a wide screen the app laid content out in one
 * column and spread it down the page, so a 2560px window showed the same eighty
 * rows a 1280px one did, each with two thirds of its line empty to the right,
 * and everything below the first list pushed off the fold.
 *
 * What is pinned here is the *responsive contract*, one assertion per page: the
 * container that holds a page's repeating content declares a column count that
 * grows with the viewport, and still declares exactly one column at the narrow
 * end. jsdom computes no media queries, so this cannot assert the rendered
 * geometry — what it can do is stop the classes being dropped by a later
 * refactor without anyone noticing, which is how the single column came back
 * the first time. The narrow-end assertion (`grid-cols-1`) is half the point:
 * a change that widens the desktop layout by breaking the phone one fails here.
 *
 * The pages are asserted through their real containers rather than a snapshot,
 * so a renamed class fails loudly and a re-worded heading does not.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "../../test/utils";
import App from "../../App";
import { HomeTab } from "../HomeTab";
import { SettingsTab } from "../SettingsTab";
import { GameTweaksTab } from "../GameTweaksTab";
import { DiskCleanupTab } from "../DiskCleanupTab";
import { HardwarePanel } from "../HardwarePanel";
import { BenchmarksTab } from "../BenchmarksTab";
import { MaintenancePanel } from "../MaintenancePanel";
import { makeRunner } from "../../test/runner";
import { useStore } from "../../store";
import { Settings as SettingsIcon } from "lucide-react";
import type { CategoryMetadata, Setting } from "../../types/setting";

// The panels App hosts each open a detection pipeline; what is under test up
// there is the shell's own width.
vi.mock("../CleanupRunnerProvider", () => ({
  CleanupRunnerProvider: () => null,
}));
vi.mock("../ActivityLog", () => ({ ActivityLog: () => null }));
vi.mock("../HomeTab", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../HomeTab")>()),
}));

vi.mock("../../hooks/useCleanupRunner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../hooks/useCleanupRunner")>()),
  useCleanupRunner: () => makeRunner(),
}));

vi.mock("../../hooks/useBulkApply", () => ({
  useBulkApply: () => ({ apply: vi.fn(), isApplying: false, lastResult: null }),
}));

// Home mounts the whole device inventory; the hardware page asserts that itself.
vi.mock("../HardwarePanel", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../HardwarePanel")>()),
}));

// The benchmark panels each hold a query and an SSE client. The tab's own job is
// to place them, and that is what this file asks it.
vi.mock("../SuitePanel", () => ({ SuitePanel: () => <p>suite</p> }));
vi.mock("../VerifyPanel", () => ({ VerifyPanel: () => <p>verify</p> }));
vi.mock("../HeadroomPanel", () => ({ HeadroomPanel: () => <p>headroom</p> }));

// The hardware page's own children each probe a device; the columns are what is
// under test, and an unmocked probe would make this a network test.
vi.mock("../hardware/useRefreshOnFocus", () => ({
  useRefreshOnFocus: () => undefined,
}));
vi.mock("../hardware/MonitorCard", () => ({
  MonitorCard: () => null,
  DisplaysAutoAllButton: () => null,
}));
vi.mock("../hardware/NetworkAdapterCard", () => ({
  NetworkAdapterCard: () => null,
}));
vi.mock("../hardware/StorageDriveCard", () => ({ StorageDriveCard: () => null }));
vi.mock("../hardware/PowerProfileCard", () => ({ PowerProfileCard: () => null }));
vi.mock("../hardware/AudioSection", () => ({ AudioSection: () => null }));
vi.mock("../hardware/DeviceTweakList", () => ({ DeviceTweakList: () => null }));
vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: {
    hasData: () => true,
    subscribe: () => () => undefined,
    getCached: () => null,
    getHardware: () => Promise.resolve(null),
  },
}));

const SETTING_BASE = {
  description: "Controls how the machine behaves. It matters for frame rate.",
  impactCategories: [],
  valueType: "choice" as const,
  choices: ["Off", "On"],
  defaultValue: "On",
  recommendedValue: "Off",
  requiresReboot: false,
  isAction: false,
  scope: "recommended" as const,
  currentImpact: "",
  recommendedImpact: "",
  categoryOrder: 0,
  riskLevel: "low" as const,
  evidenceLevel: "likely" as const,
  sources: [],
  applicableConditions: {},
  isReadonly: false,
  currentValue: "On",
  status: "suboptimal" as const,
  executionStatus: "idle" as const,
  isOptimized: false,
  isApplicable: true,
};

function makeSetting(over: Partial<Setting> & Pick<Setting, "id">): Setting {
  return {
    ...SETTING_BASE,
    module: over.id.split(":")[0],
    name: over.id.split(":").slice(1).join(":"),
    displayName: "A Tweak",
    category: "system",
    ...over,
  } as Setting;
}

/** Two of a kind, so a one-per-line list has something to lay out. */
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

/**
 * The contract itself: one column when narrow, more than one further up.
 *
 * Written as a helper so every page states the same property, and so a page that
 * declares only the wide half — the regression that starts "it looks fine on my
 * monitor" — cannot pass by naming one class.
 */
function expectRespondsToWidth(element: HTMLElement, wideClass: string) {
  expect(element).toHaveClass("grid");
  expect(element).toHaveClass("grid-cols-1");
  expect(element).toHaveClass(wideClass);
}

beforeEach(() => {
  setStore([]);
});

describe("every page lays its content out across the width it is given", () => {
  it("Shell: the content column widens past 1920px instead of banking margin", () => {
    useStore.setState({ activeTab: "home", settings: new Map() } as never);

    render(<App />);

    const shell = screen.getByTestId("app-shell");
    // Each cap is one step of the same staircase; dropping the top one is what
    // left a 2560px window rendering a 1920px app.
    expect(shell).toHaveClass("max-w-7xl");
    expect(shell).toHaveClass("2xl:max-w-[120rem]");
    expect(shell).toHaveClass("3xl:max-w-[150rem]");
  });

  it("Home: a domain's outstanding tweaks tile instead of queueing down the page", () => {
    setStore(pair("system:home"));

    render(<HomeTab />);

    const rows = screen.getAllByTestId("tweak-group-rows");
    expect(rows.length).toBeGreaterThan(0);
    for (const group of rows) expectRespondsToWidth(group, "2xl:grid-cols-2");
  });

  it("Home: the advisories tile, since each is a self-contained finding", () => {
    setStore(
      pair("system:advisory", {
        isReadonly: true,
        isOptimized: false,
        effect: "Move the cable to a Cat 6 run",
      }),
    );

    render(<HomeTab />);

    const advisories = screen.getByTestId("home-advisory-grid");
    expectRespondsToWidth(advisories, "lg:grid-cols-2");
    expect(advisories).toHaveClass("2xl:grid-cols-3");
  });

  it("Home: the cleanup card tiles when it has the page, and not when it shares it", () => {
    // Its width depends on whether the tweak groups are beside it, and a column
    // count that ignored that would put three columns inside a third of the
    // page. Both halves are asserted, because only having one is the bug.
    const cleanups = pair("cleanup:cache", {
      isAction: true,
      category: "maintenance",
      currentValue: "ready|800 MB",
      groupId: "windows",
      groupLabel: "Windows",
      groupOrder: 1,
    });

    setStore(cleanups);
    const alone = render(<HomeTab />);
    const wide = alone.getByTestId("home-cleanup-rows");
    expect(wide).toHaveClass("grid-cols-1");
    expect(wide).toHaveClass("lg:grid-cols-2");
    alone.unmount();

    // Now with tweaks beside it, so the card is the narrow third of the row.
    setStore([...cleanups, ...pair("system:shared")]);
    const shared = render(<HomeTab />);
    const narrow = shared.getByTestId("home-cleanup-rows");
    expect(narrow).toHaveClass("grid-cols-1");
    expect(narrow).not.toHaveClass("lg:grid-cols-2");
  });

  it("Software Tweaks: the row list gains columns as the window widens", () => {
    const settings = pair("system:software");
    setStore(settings);
    const category: CategoryMetadata = {
      id: "system",
      displayName: "System",
      description: "System tweaks",
      icon: "Settings",
      order: 1,
    } as CategoryMetadata;

    render(
      <SettingsTab
        categoriesWithSettings={[{ category, settings }]}
        moduleMetaMap={new Map()}
        definitionsLoading={false}
        gpuCategoryStatus="done"
        hasGpuSettings={false}
        getIconByName={() => SettingsIcon}
      />,
    );

    const [list] = screen.getAllByTestId("tweak-rows");
    expectRespondsToWidth(list, "2xl:grid-cols-2");
    expect(list).toHaveClass("3xl:grid-cols-3");
  });

  it("Game Tweaks: a game's config lines use the same widening row list", () => {
    setStore(
      pair("game_config:mw4:quality", {
        category: "game_config",
        groupId: "mw4",
        groupLabel: "Modern Warfare IV",
        groupOrder: 10,
      }),
    );

    render(<GameTweaksTab />);

    const [list] = screen.getAllByTestId("tweak-rows");
    expectRespondsToWidth(list, "2xl:grid-cols-2");
  });

  it("Cleanup: the two panels split the width, and their rows split it again", () => {
    setStore(
      pair("cleanup:junk", {
        isAction: true,
        category: "maintenance",
        currentValue: "ready|1229 MB",
        groupId: "windows",
        groupLabel: "Windows",
        groupOrder: 1,
      }),
    );

    const { container } = render(<DiskCleanupTab />);

    const panels = container.querySelector(".grid.grid-cols-1.lg\\:grid-cols-2");
    expect(panels).not.toBeNull();

    const [group] = screen.getAllByTestId("cleanup-group-rows");
    expectRespondsToWidth(group, "3xl:grid-cols-2");
  });

  it("Cleanup: the two repairs sit side by side rather than stacked", () => {
    setStore(
      pair("maintenance:repair", {
        isAction: true,
        category: "maintenance",
        currentValue: "ready",
      }),
    );

    render(<MaintenancePanel />);

    expectRespondsToWidth(screen.getByTestId("maintenance-rows"), "lg:grid-cols-2");
  });

  it("Hardware: the sections form a third column instead of one long one", () => {
    render(<HardwarePanel />);

    const columns = screen.getByTestId("hardware-columns");
    expectRespondsToWidth(columns, "lg:grid-cols-2");
    // The step the split exists for: Connectivity stops being a stub beside a
    // column six sections deep and becomes a column of its own.
    expect(columns).toHaveClass("2xl:grid-cols-3");
  });

  it("Benchmarks: the result sits beside the instrument on a wide window", () => {
    render(<BenchmarksTab />);

    const columns = screen.getByTestId("benchmarks-columns");
    expect(columns).toHaveClass("grid");
    expect(columns).toHaveClass("grid-cols-1");
    expect(columns).toHaveClass("2xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]");
    // Order is load-bearing: the tool is what you press, so it stays first.
    expect(screen.getByText("suite").compareDocumentPosition(screen.getByText("headroom")))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });
});

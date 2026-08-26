/**
 * D6 GATE: Home is the superset — every applicable setting and every device
 * mutation is reachable from Home.
 *
 * The defect this guards: Home used to show a fraction of the product. All
 * five advisory findings, SFC and DISM, cleanups still measuring, the
 * already-optimal settings and all eleven hardware device mutations were
 * reachable only from detail tabs — a user who stayed on the landing page
 * never learned XMP was off. One representative per class walks the same
 * filters the real registry flows through; a class Home's filters drop makes
 * its representative disappear, and this file goes red.
 *
 * The device-mutation surface is asserted as the mounted HardwarePanel, whose
 * own tests cover the eleven actions; Home's obligation is that the surface
 * is reachable from it.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "../../test/utils";
import { HomeTab } from "../HomeTab";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";

vi.mock("../../hooks/useBulkApply", () => ({
  useBulkApply: () => ({ apply: vi.fn(), isApplying: false }),
}));

vi.mock("../../hooks/useApplySingle", () => ({
  useApplySingle: () => ({
    applySingle: vi.fn(),
    undoSingle: vi.fn(),
    isPending: () => false,
  }),
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

// The eleven device mutations live on this surface; its own tests cover them.
vi.mock("../HardwarePanel", () => ({
  HardwarePanel: () => <div data-testid="hardware-panel" />,
}));

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      getSelfCheck: vi.fn().mockResolvedValue({ ok: true, findings: [] }),
    },
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

/**
 * One representative per class of thing the registry can hold. Each
 * displayName is unique and asserted verbatim, so a class Home drops names
 * itself in the failure.
 */
const REPRESENTATIVES: Setting[] = [
  makeSetting({
    id: "system:tcp_ack" as `${string}:${string}`,
    displayName: "Software tweak representative",
  }),
  makeSetting({
    id: "display:mpo" as `${string}:${string}`,
    displayName: "Hardware tweak representative",
  }),
  makeSetting({
    id: "game_config:mw4:model_quality" as `${string}:${string}`,
    displayName: "Game tweak representative",
  }),
  makeSetting({
    id: "system:already_good" as `${string}:${string}`,
    displayName: "Already-optimal representative",
    status: "optimal",
    isOptimized: true,
  }),
  makeSetting({
    id: "system:xmp_expo" as `${string}:${string}`,
    displayName: "Advisory representative",
    isReadonly: true,
  }),
  makeSetting({
    id: "cleanup:temp_files" as `${string}:${string}`,
    displayName: "Measured cleanup representative",
    isAction: true,
    currentValue: "2.3 GB",
  }),
  makeSetting({
    id: "cleanup:browser_cache" as `${string}:${string}`,
    displayName: "Still-measuring cleanup representative",
    isAction: true,
    currentValue: "calculating...",
  }),
  makeSetting({
    id: "maintenance:sfc_scan" as `${string}:${string}`,
    displayName: "Maintenance action representative",
    isAction: true,
  }),
];

describe("D6: Home completeness", () => {
  beforeEach(() => {
    useStore.setState({
      settings: new Map(REPRESENTATIVES.map((s) => [s.id, s])),
      categories: new Map(),
      cleanupResults: {},
      operationStatus: {},
      _settingsVersion: 1,
    } as never);
  });

  it("every class of applicable setting is reachable from Home", () => {
    render(<HomeTab />);

    // The already-optimal class sits behind a fold Home owns; opening it is
    // still "reachable from Home".
    const fold = screen.queryByText(/Already optimized/);
    if (fold) fireEvent.click(fold);

    for (const setting of REPRESENTATIVES) {
      expect(
        screen.getByText(setting.displayName),
        `unreachable from Home: ${setting.id} (${setting.displayName})`,
      ).toBeInTheDocument();
    }
  });

  it("the device-mutation surface is reachable from Home", () => {
    render(<HomeTab />);
    expect(screen.getByTestId("hardware-panel")).toBeInTheDocument();
  });
});

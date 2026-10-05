/**
 * The Hardware page has a scope of its own: Apply, Undo and Windows default for
 * every hardware tweak its cards draw, at the top, where Software Tweaks keeps
 * its own. Before this the page had one set of buttons per card and nothing
 * for the page, so "apply everything on this machine's hardware" took one press
 * per device.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent } from "@testing-library/react";
import { render, screen, within } from "../../test/utils";
import { HardwarePanel } from "../HardwarePanel";
import { useStore } from "../../store";
import type { HardwareInfo } from "../../lib/api";
import type { Setting } from "../../types/setting";

const bulkRun = vi.fn();

const inventory: HardwareInfo = {
  cpu: { name: "Example CPU 8-Core", physical_cores: 8, logical_cores: 16, architecture: "x64" },
  gpus: [],
  monitors: [],
  network_adapters: [],
  storage_drives: [],
  audio_devices: [],
  detecting: false,
};

vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: {
    hasData: () => true,
    subscribe: () => () => undefined,
    getCached: () => inventory,
    getHardware: () => Promise.resolve(inventory),
  },
}));
vi.mock("../hardware/useRefreshOnFocus", () => ({ useRefreshOnFocus: () => undefined }));
vi.mock("../hardware/PowerProfileCard", () => ({ PowerProfileCard: () => null }));
vi.mock("../../hooks/useApplySingle", () => ({
  useApplySingle: () => ({ applySingle: vi.fn(), isPending: () => false }),
}));
vi.mock("../../hooks/useBulkStream", () => ({
  useBulkStream: () => ({
    run: (...a: unknown[]) => bulkRun(...a),
    stop: vi.fn(),
    isRunning: false,
  }),
}));
vi.mock("../../lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  api: { getSystemInfo: vi.fn().mockResolvedValue(undefined) },
}));

function setting(over: Partial<Setting> & { id: string }): Setting {
  return {
    module: over.id.split(":")[0],
    domain: "hardware",
    component: "cpu",
    name: "x",
    displayName: "A Tweak",
    description: "Does a thing.",
    category: "cpu",
    valueType: "choice",
    choices: ["off", "on"],
    defaultValue: "off",
    recommendedValue: "on",
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
    currentValue: "off",
    status: "suboptimal",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true,
    effect: "",
    ...over,
  } as Setting;
}

function setStore(settings: Setting[]) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    categories: new Map(),
    cleanupResults: {},
    selectedSettingIds: new Set(),
    categoryDetectionStatus: { core: "success" },
  } as never);
}

/** The page header's own button group: the one that is not inside a device card. */
function pageActions() {
  const header = screen.getByRole("heading", { level: 2, name: "Hardware" });
  return within(header.closest("[data-slot='scope-header']") as HTMLElement);
}

beforeEach(() => bulkRun.mockReset());

describe("the Hardware page's own scope", () => {
  it("applies every hardware tweak the cards draw, behind one confirmation", () => {
    setStore([setting({ id: "cpu:boost_mode" }), setting({ id: "cpu:core_parking" })]);
    render(<HardwarePanel />);

    fireEvent.click(pageActions().getByRole("button", { name: "Apply 2 tweaks: Hardware Tweaks" }));
    expect(bulkRun).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Apply" }));

    expect(bulkRun).toHaveBeenCalledWith(
      "apply",
      expect.arrayContaining(["cpu:boost_mode", "cpu:core_parking"]),
    );
  });

  it("leaves a software tweak out, whatever its category says", () => {
    setStore([
      setting({ id: "cpu:boost_mode" }),
      setting({ id: "system:game_dvr", domain: "software", component: undefined, category: "system" }),
    ]);
    render(<HardwarePanel />);

    expect(
      pageActions().getByRole("button", { name: "Apply 1 tweaks: Hardware Tweaks" }),
    ).toBeEnabled();
  });

  it("stays in the same place, disabled and naming why, when nothing is left to do", () => {
    setStore([]);
    render(<HardwarePanel />);

    expect(
      pageActions().getByRole("button", { name: "Apply: nothing to apply in Hardware Tweaks" }),
    ).toBeDisabled();
    expect(
      pageActions().getByRole("button", {
        name: "Windows default: already at the Windows default in Hardware Tweaks",
      }),
    ).toBeDisabled();
  });
});

/**
 * The Hardware category on the Optimize tab: a list of devices, each named once.
 *
 * Reported on the adapter, monitor and audio cards of the old Hardware page: the
 * heading said the name, and the first line of the card body said it again, so
 * every card read as a stutter. The device's header is now the one place its name
 * is written, and what a device opens to carries only what the header cannot
 * (status, link, mode, controls). The duplication only exists in the composition,
 * so these render the real page, with the real device cards under a device.
 *
 * Also the page's own scope: Apply for every hardware tweak, at the category's
 * line, never reaching a software one, and absent when there is nothing to do.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, within } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { OptimizeTab } from "../OptimizeTab";
import { useStore } from "../../store";
import type { HardwareInfo } from "../../lib/api";
import type { Setting } from "../../types/setting";

const run = vi.fn();

const inventory: HardwareInfo = {
  cpu: { name: "Example CPU 8-Core", physical_cores: 8, logical_cores: 16, architecture: "x64" },
  gpus: [],
  monitors: [
    {
      name: "\\\\.\\DISPLAY13",
      friendly_name: "Dell AW2725DF",
      hardware_id: "DEL4321",
      width: 2560,
      height: 1440,
      refresh_rate_hz: 300,
      is_primary: true,
      is_active: true,
      setting_key: "mon0a1b2c3d4e",
    },
    {
      // No EDID model: the header falls back to the device path.
      name: "\\\\.\\DISPLAY14",
      hardware_id: "SAM0F75",
      width: 1920,
      height: 1080,
      refresh_rate_hz: 60,
      is_primary: false,
      is_active: true,
      setting_key: "mon1f2e3d4c5b",
    },
  ],
  network_adapters: [
    {
      name: "Ethernet 3 (Office LAN)",
      description: "Intel(R) Ethernet Connection I219-V",
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
      loudness_eq_supported: true,
      loudness_eq_enabled: false,
    },
  ],
  detecting: false,
};

vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: {
    hasData: () => true,
    subscribe: () => () => undefined,
    getCached: () => inventory,
    getHardware: () => Promise.resolve(inventory),
    refreshNetworkAdapters: vi.fn().mockResolvedValue([]),
    refreshMonitors: vi.fn().mockResolvedValue([]),
    refreshAudioDevices: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock("../hardware/useRefreshOnFocus", () => ({ useRefreshOnFocus: () => undefined }));
vi.mock("../../hooks/useApply", () => ({
  useApply: () => ({
    apply: vi.fn(),
    run: (...args: unknown[]) => run(...args),
    reset: vi.fn(),
    stop: vi.fn(),
    pendingIds: new Set<string>(),
    isPending: () => false,
    isRunning: false,
  }),
}));
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    api: { ...actual.api, getSystemInfo: vi.fn().mockResolvedValue(undefined) },
  };
});

function setting(over: Partial<Setting> & { id: string }): Setting {
  return {
    module: over.id.split(":")[0],
    domain: "hardware",
    component: "cpu",
    name: "x",
    displayName: over.id,
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

function seed(settings: Setting[]) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    categories: new Map(),
    cleanupResults: {},
    selectedSettingIds: new Set(),
    operationStatus: {},
    operationError: {},
    categoryDetectionStatus: { core: "success" },
  } as never);
}

const category = () => screen.getByRole("heading", { level: 2, name: /^Hardware/ });
const section = () => category().closest<HTMLElement>('[data-testid="category-section"]')!;
const device = (name: RegExp) => screen.getByRole("button", { name });

beforeEach(() => {
  run.mockReset();
  // A machine with one tweak already right: the page is drawn, nothing to apply.
  seed([setting({ id: "cpu:boost_mode", isOptimized: true, status: "optimal", currentValue: "on" })]);
});

describe("a device is named once, in its header", () => {
  it("shows a network adapter's name once, and keeps its switch reachable by it", async () => {
    render(<OptimizeTab />);
    await userEvent.click(within(category()).getByRole("button"));
    await userEvent.click(device(/Ethernet 3 \(Office LAN\)/));

    const open = screen.getByRole("region", { name: /Ethernet 3 \(Office LAN\)/ });
    // The header carries the name; the card under it must not say it again.
    expect(screen.getAllByText("Ethernet 3 (Office LAN)")).toHaveLength(1);
    expect(within(open).queryByText("Ethernet 3 (Office LAN)")).not.toBeInTheDocument();
    expect(within(open).getByRole("switch", { name: "Ethernet 3 (Office LAN)" })).toBeInTheDocument();
  });

  it("shows a monitor's model once, with its device path and hardware id as detail", async () => {
    render(<OptimizeTab />);
    await userEvent.click(within(category()).getByRole("button"));
    await userEvent.click(device(/Dell AW2725DF/));

    expect(screen.getAllByText("Dell AW2725DF")).toHaveLength(1);
    // The detail line is information the header does not carry.
    const open = screen.getByRole("region", { name: /Dell AW2725DF/ });
    expect(within(open).getByText(/DISPLAY13/)).toBeInTheDocument();
    expect(within(open).getByText(/DEL4321/)).toBeInTheDocument();
  });

  it("shows a monitor without an EDID model by its device path once", async () => {
    render(<OptimizeTab />);
    await userEvent.click(within(category()).getByRole("button"));
    await userEvent.click(device(/DISPLAY14/));

    const open = screen.getByRole("region", { name: /DISPLAY14/ });
    expect(screen.getAllByText(/DISPLAY14/)).toHaveLength(1);
    expect(within(open).getByText(/SAM0F75/)).toBeInTheDocument();
  });

  it("names the audio device apart from its Output section, and shows each endpoint once", async () => {
    render(<OptimizeTab />);
    await userEvent.click(within(category()).getByRole("button"));
    await userEvent.click(screen.getByRole("button", { name: /^Audio/ }));

    // The device header and the section heading both read "Audio Output" before.
    expect(screen.getAllByText("Audio Output")).toHaveLength(1);
    expect(screen.getAllByText("Speakers (High Definition Audio)")).toHaveLength(1);
  });
});

describe("the Hardware category's own scope", () => {
  const openCategory = async () => {
    render(<OptimizeTab />);
    return within(section());
  };

  it("applies every hardware tweak under it, behind one confirmation", async () => {
    seed([setting({ id: "cpu:boost_mode" }), setting({ id: "cpu:core_parking" })]);
    const line = await openCategory();

    fireEvent.click(line.getByRole("button", { name: "Apply 2 tweaks: Hardware" }));
    expect(run).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Apply" }));

    expect(run).toHaveBeenCalledWith(
      "apply",
      expect.arrayContaining(["cpu:boost_mode", "cpu:core_parking"]),
    );
  });

  it("leaves a software tweak out, whatever its category says", async () => {
    seed([
      setting({ id: "cpu:boost_mode" }),
      setting({ id: "system:game_dvr", domain: "software", component: undefined, category: "system" }),
    ]);
    const line = await openCategory();

    expect(line.getByRole("button", { name: "Apply 1 tweaks: Hardware" })).toBeEnabled();
  });

  it("offers no Apply when nothing under it is left to do", async () => {
    seed([setting({ id: "cpu:boost_mode", isOptimized: true, status: "optimal", currentValue: "on" })]);
    const line = await openCategory();

    expect(line.queryByRole("button", { name: /^Apply/ })).not.toBeInTheDocument();
  });
});

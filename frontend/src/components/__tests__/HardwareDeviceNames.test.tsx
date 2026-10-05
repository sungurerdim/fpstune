/**
 * A device is named once on the Hardware page: in its card's heading.
 *
 * Reported on the adapter, monitor and audio cards: the heading said the name,
 * and the first line of the card body said it again, so every card read as a
 * stutter. The body keeps what the heading cannot carry (status, link, mode,
 * controls); the name is the heading's job alone.
 *
 * The cards are rendered through the real page, because the duplication only
 * exists in the composition — each card on its own showed its name once.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "../../test/utils";
import { HardwarePanel } from "../HardwarePanel";
import { useStore } from "../../store";
import type { HardwareInfo } from "../../lib/api";

const inventory: HardwareInfo = {
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
      // No EDID model: the heading falls back to the device path.
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
vi.mock("../hardware/useRefreshOnFocus", () => ({
  useRefreshOnFocus: () => undefined,
}));
vi.mock("../hardware/PowerProfileCard", () => ({ PowerProfileCard: () => null }));
vi.mock("../../hooks/useApplySingle", () => ({
  useApplySingle: () => ({ applySingle: vi.fn(), isPending: () => false }),
}));
vi.mock("../../hooks/useBulkStream", () => ({
  useBulkStream: () => ({ run: vi.fn(), stop: vi.fn(), isRunning: false }),
}));
vi.mock("../../lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  api: { getSystemInfo: vi.fn().mockResolvedValue(undefined) },
}));

beforeEach(() => {
  useStore.setState({
    settings: new Map(),
    categories: new Map(),
    cleanupResults: {},
    categoryDetectionStatus: { core: "success" },
  } as never);
});

describe("a device is named once, in its card heading", () => {
  it("shows a network adapter's name once, not again in its body", () => {
    render(<HardwarePanel />);

    const card = screen.getByRole("region", { name: "Ethernet 3 (Office LAN)" });
    expect(within(card).getAllByText("Ethernet 3 (Office LAN)")).toHaveLength(1);
    expect(screen.getAllByText("Ethernet 3 (Office LAN)")).toHaveLength(1);
  });

  it("keeps the adapter's switch reachable by its name", () => {
    render(<HardwarePanel />);

    expect(screen.getByRole("switch", { name: "Ethernet 3 (Office LAN)" })).toBeInTheDocument();
  });

  it("shows a monitor's model once, with its device path and hardware id as detail", () => {
    render(<HardwarePanel />);

    const card = screen.getByRole("region", { name: "Dell AW2725DF" });
    expect(within(card).getAllByText("Dell AW2725DF")).toHaveLength(1);
    // The detail line is information the heading does not carry.
    expect(within(card).getByText(/DISPLAY13/)).toBeInTheDocument();
    expect(within(card).getByText(/DEL4321/)).toBeInTheDocument();
  });

  it("shows a monitor without an EDID model by its device path once", () => {
    render(<HardwarePanel />);

    const card = screen.getByRole("heading", { name: /DISPLAY14/ }).closest("section")!;
    expect(within(card).getAllByText(/DISPLAY14/)).toHaveLength(1);
    expect(within(card).getByText(/SAM0F75/)).toBeInTheDocument();
  });

  it("names the audio card apart from its Output section, and shows each device once", () => {
    render(<HardwarePanel />);

    // The card heading and the section heading both read "Audio Output" before.
    expect(screen.getAllByText("Audio Output")).toHaveLength(1);
    expect(screen.getByRole("region", { name: "Audio" })).toBeInTheDocument();
    expect(screen.getAllByText("Speakers (High Definition Audio)")).toHaveLength(1);
  });
});

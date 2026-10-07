/**
 * The device list: hardware is a category, its devices are the items.
 *
 * It had been a wall of per-device cards, each carrying its own header, counts
 * and buttons, so which piece of hardware a tweak improves took reading the
 * whole page. The guards: devices appear in one fixed order (GPU, Monitor 1,
 * Monitor 2, NIC, storage), a device is one line, selecting one — with the
 * mouse or the keyboard — reveals exactly its own rows, and "N not optimized"
 * counts what the backend marked suboptimal, not what the frontend recomputes.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, within, fireEvent } from "../../../test/utils";
import userEvent from "@testing-library/user-event";
import { DeviceList } from "../DeviceList";
import { listDevices, tweaksOfDevice } from "../devices";
import { useStore } from "../../../store";
import type { HardwareInfo, MonitorInfo, NetworkAdapterInfo } from "../../../lib/api";
import type { Setting } from "../../../types/setting";
import { en } from "../../../i18n/en";

const t = ((key: keyof typeof en, vars?: Record<string, unknown>) =>
  String(en[key]).replace(/\{(\w+)\}/g, (_, k: string) => String(vars?.[k] ?? ""))) as never;

function setting(over: Partial<Setting> & { id: string }): Setting {
  return {
    module: over.id.split(":")[0],
    name: over.id,
    displayName: over.id,
    description: "Does a thing.",
    category: "gpu",
    valueType: "choice",
    choices: [],
    defaultValue: "off",
    recommendedValue: "on",
    categoryOrder: 0,
    isAction: false,
    isReadonly: false,
    currentValue: "off",
    status: "suboptimal",
    isOptimized: false,
    isApplicable: true,
    domain: "hardware",
    ...over,
  } as Setting;
}

const panel = (name: string, key: string, primary: boolean): MonitorInfo =>
  ({
    name,
    friendly_name: name,
    setting_key: key,
    is_primary: primary,
    width: 2560,
    height: 1440,
    refresh_rate_hz: 165,
    is_refresh_known: true,
    is_refresh_optimal: true,
  }) as MonitorInfo;

const HARDWARE = {
  gpus: [{ vendor: "NVIDIA", name: "Example GPU 1", vram_mb: 8192 }],
  monitors: [panel("Panel A", "monaaaa", true), panel("Panel B", "monbbbb", false)],
  network_adapters: [
    { name: "Wi-Fi 6 Adapter", adapter_type: "WiFi", setting_key: "nic1111", interface_index: 7 },
  ] as NetworkAdapterInfo[],
  storage_drives: [
    {
      drive_letter: "C",
      model: "Example NVMe 1TB",
      media_type: "SSD",
      size_gb: 931,
      trim_enabled: true,
      bus_type: "NVMe",
    },
  ],
  audio_devices: [],
  detecting: false,
} as unknown as HardwareInfo;

const GPU_ROW = setting({
  id: "gpu-hardware:msi_mode",
  displayName: "MSI Mode",
  component: "gpu",
});
const GPU_IDEAL = setting({
  id: "gpu-hardware:hags",
  displayName: "Hardware Scheduling",
  component: "gpu",
  status: "optimal",
  isOptimized: true,
  currentValue: "on",
});
const MONITOR_A_ROW = setting({
  id: "display:monaaaa:refresh",
  displayName: "Refresh Rate A",
  module: "display",
  component: "display",
  subject: "Panel A",
});
const MONITOR_B_ROW = setting({
  id: "display:monbbbb:refresh",
  displayName: "Refresh Rate B",
  module: "display",
  component: "display",
  subject: "Panel B",
});
const NIC_ROW = setting({
  id: "network:nic1111:eee",
  displayName: "Energy Efficient Ethernet",
  module: "network",
  component: "network_adapter",
  subject: "Wi-Fi 6 Adapter",
});
const STORAGE_ROW = setting({
  id: "storage:trim",
  displayName: "TRIM",
  module: "storage",
  component: "storage",
});
const ADVISORY = setting({
  id: "gpu-hardware:resizable_bar",
  displayName: "Resizable BAR",
  component: "gpu",
  isReadonly: true,
});

const ALL = [GPU_ROW, GPU_IDEAL, MONITOR_A_ROW, MONITOR_B_ROW, NIC_ROW, STORAGE_ROW, ADVISORY];

function seed(settings: Setting[]) {
  useStore.setState({
    settings: new Map(settings.map((s) => [s.id, s])),
    categories: new Map(),
    cleanupResults: {},
    categoryDetectionStatus: { core: "success" },
  } as never);
}

/** Rows are the caller's to draw; a list of names is enough to tell whose they are. */
const renderRows = (_device: unknown, rows: Setting[]) => (
  <ul>
    {rows.map((r) => (
      <li key={r.id}>{r.displayName}</li>
    ))}
  </ul>
);

const deviceButtons = () => within(screen.getByRole("list", { name: "Devices" })).getAllByRole("button");

describe("DeviceList", () => {
  beforeEach(() => seed(ALL));

  it("lists GPU, Monitor 1, Monitor 2, NIC and storage in that order, one under another", () => {
    render(<DeviceList hardware={HARDWARE} renderRows={renderRows} />);
    const names = deviceButtons().map((b) => b.textContent ?? "");
    const at = (needle: string) => names.findIndex((n) => n.includes(needle));
    const order = ["Example GPU 1", "Panel A", "Panel B", "Wi-Fi 6 Adapter", "Example NVMe 1TB"].map(at);
    expect(order.every((i) => i >= 0)).toBe(true);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it("shows no rows until a device is selected, then exactly that device's rows", () => {
    render(<DeviceList hardware={HARDWARE} renderRows={renderRows} />);
    expect(screen.queryByText("MSI Mode")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Panel B/ }));
    const panelB = screen.getByRole("region", { name: /Panel B/ });
    expect(within(panelB).getByText("Refresh Rate B")).toBeInTheDocument();
    expect(screen.queryByText("Refresh Rate A")).toBeNull();
    expect(screen.queryByText("MSI Mode")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Wi-Fi 6 Adapter/ }));
    expect(screen.getByText("Energy Efficient Ethernet")).toBeInTheDocument();
    expect(screen.queryByText("Refresh Rate B")).toBeNull();
  });

  it("selects with the keyboard and tells assistive tech what it opened", async () => {
    const user = userEvent.setup();
    render(<DeviceList hardware={HARDWARE} renderRows={renderRows} />);
    const gpu = screen.getByRole("button", { name: /Example GPU 1/ });
    expect(gpu).toHaveAttribute("aria-expanded", "false");

    await user.tab();
    const first = deviceButtons()[0];
    expect(first).toHaveFocus();
    await user.keyboard("{Tab}".repeat(deviceButtons().indexOf(gpu)));
    expect(gpu).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(gpu).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById(gpu.getAttribute("aria-controls") ?? "")).toContainElement(
      screen.getByText("MSI Mode"),
    );
    await user.keyboard(" ");
    expect(gpu).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("MSI Mode")).toBeNull();
  });

  it("counts what the backend marked suboptimal, and keeps advisories out of the count", () => {
    render(<DeviceList hardware={HARDWARE} renderRows={renderRows} />);
    // GPU: MSI Mode is suboptimal, Hardware Scheduling optimal, Resizable BAR a readonly advisory.
    const gpu = screen.getByRole("button", { name: /Example GPU 1/ });
    expect(within(gpu).getByText("1 not optimized")).toBeInTheDocument();
  });

  it("shows no count on a device whose tweaks are all optimized", () => {
    seed([GPU_IDEAL]);
    render(<DeviceList hardware={HARDWARE} renderRows={renderRows} />);
    const gpu = screen.getByRole("button", { name: /Example GPU 1/ });
    expect(within(gpu).queryByText(/not optimized/)).toBeNull();
  });

  it("says so when a selected device has nothing to tune", () => {
    render(<DeviceList hardware={HARDWARE} renderRows={renderRows} />);
    fireEvent.click(screen.getByRole("button", { name: /Example NVMe 1TB/ }));
    expect(screen.getByText("Nothing to do on this device.")).toBeInTheDocument();
  });

  it("leaves a machine-wide group out entirely when it holds no tweaks", () => {
    render(<DeviceList hardware={HARDWARE} renderRows={renderRows} />);
    expect(screen.queryByRole("button", { name: /All network adapters/ })).toBeNull();
    expect(screen.getByRole("button", { name: /All drives/ })).toBeInTheDocument();
  });

  it("can be driven from outside (controlled selection)", () => {
    const picked: Array<string | null> = [];
    render(
      <DeviceList
        hardware={HARDWARE}
        renderRows={renderRows}
        selectedKey="monitor-monaaaa"
        onSelect={(k) => picked.push(k)}
      />,
    );
    expect(screen.getByText("Refresh Rate A")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Panel A/ }));
    expect(picked).toEqual([null]);
  });
});

describe("tweaksOfDevice", () => {
  const devices = listDevices(HARDWARE, t);
  const device = (key: string) => {
    const found = devices.find((d) => d.deviceKey === key);
    if (!found) throw new Error(`no device ${key}`);
    return found;
  };

  it("ties each tweak to the one device it acts on", () => {
    const rows = ALL;
    expect(tweaksOfDevice(device("monitor-monaaaa"), rows).settings).toEqual([MONITOR_A_ROW]);
    expect(tweaksOfDevice(device("monitor-monbbbb"), rows).settings).toEqual([MONITOR_B_ROW]);
    expect(tweaksOfDevice(device("adapter-nic1111"), rows).settings).toEqual([NIC_ROW]);
    expect(tweaksOfDevice(device("storage"), rows).settings).toEqual([STORAGE_ROW]);
  });

  it("separates what fpstune fixes from what only the user can", () => {
    const gpu = tweaksOfDevice(device("gpu-0"), ALL);
    expect(gpu.settings).toHaveLength(3);
    expect(gpu.notOptimized).toBe(1);
    expect(gpu.advisories).toBe(1);
  });

  it("skips rows that are not applicable or have no reading", () => {
    const absent = setting({ id: "gpu-hardware:gone", component: "gpu", isApplicable: false });
    const unread = setting({ id: "gpu-hardware:unread", component: "gpu", currentValue: null });
    expect(tweaksOfDevice(device("gpu-0"), [absent, unread]).settings).toEqual([]);
  });

  it("keeps a read-only check that found nothing, or read nothing, on the device without counting it", () => {
    // The evidence a check ran: dropping it makes a silent detector look like a
    // missing one. Neither is a finding, so neither is in a count.
    const clear = setting({
      id: "gpu-hardware:rebar_ok",
      component: "gpu",
      isReadonly: true,
      status: "optimal",
      isOptimized: true,
    });
    const unread = setting({
      id: "gpu-hardware:link_unread",
      component: "gpu",
      isReadonly: true,
      currentValue: null,
      status: "default",
    });
    const gpu = tweaksOfDevice(device("gpu-0"), [clear, unread]);

    expect(gpu.settings).toEqual([clear, unread]);
    expect(gpu.notOptimized).toBe(0);
    expect(gpu.advisories).toBe(0);
  });

  it("is the same answer for the same input", () => {
    expect(tweaksOfDevice(device("gpu-0"), ALL)).toEqual(tweaksOfDevice(device("gpu-0"), ALL));
  });

  it("lists devices in order: GPU, Monitor 1, Monitor 2, NIC, storage", () => {
    const keys = devices.map((d) => d.deviceKey);
    const order = ["gpu-0", "monitor-monaaaa", "monitor-monbbbb", "adapter-nic1111", "drive-C"].map(
      (k) => keys.indexOf(k),
    );
    expect(order.every((i) => i >= 0)).toBe(true);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });
});

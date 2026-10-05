/**
 * Which card a tweak lands on. The failures these guard: two adapters or two
 * monitors sharing one list, a key re-derived from an interface index (C5), and
 * a machine-wide tweak pinned to one instance of its component.
 */

import { describe, it, expect } from "vitest";
import { describeDevices } from "../devices";
import type { HardwareInfo, MonitorInfo, NetworkAdapterInfo } from "../../../lib/api";
import type { Setting } from "../../../types/setting";
import { en } from "../../../i18n/en";

const t = ((key: keyof typeof en, vars?: Record<string, unknown>) =>
  String(en[key]).replace(/\{(\w+)\}/g, (_, k: string) => String(vars?.[k] ?? ""))) as never;

const row = (id: string, extra: Partial<Setting> = {}) =>
  ({ id, module: id.split(":")[0], domain: "hardware", ...extra }) as Setting;

const nic = (name: string, type: string, key: string): NetworkAdapterInfo =>
  ({ name, adapter_type: type, setting_key: key, interface_index: 7 }) as NetworkAdapterInfo;

const panel = (name: string, key: string, primary: boolean): MonitorInfo =>
  ({
    name,
    friendly_name: name,
    setting_key: key,
    is_primary: primary,
    width: 1920,
    height: 1080,
  }) as MonitorInfo;

const hw = {
  gpus: [],
  monitors: [panel("Example 27Q", "monaaaa", true), panel("Example 24", "monbbbb", false)],
  network_adapters: [nic("Wi-Fi", "WiFi", "nic1111"), nic("Ethernet", "Ethernet", "nic2222")],
  storage_drives: [],
  audio_devices: [],
  detecting: false,
} as HardwareInfo;

describe("describeDevices", () => {
  const devices = describeDevices(hw, t);
  const card = (key: string) => {
    const found = devices.find((d) => d.deviceKey === key);
    if (!found) throw new Error(`no card ${key}`);
    return found;
  };

  it("gives Wi-Fi and Ethernet a card each, matched on the backend's adapter key", () => {
    const eee = row("network:nic1111:eee", { component: "network_adapter", subject: "Wi-Fi" });
    expect(card("adapter-nic1111").kind).toBe("Wi-Fi");
    expect(card("adapter-nic2222").kind).toBe("Ethernet");
    expect(card("adapter-nic1111").match?.(eee)).toBe(true);
    expect(card("adapter-nic2222").match?.(eee)).toBe(false);
    expect(card("adapter-nic1111").match?.(row("network:7:eee"))).toBe(false);
  });

  it("gives each monitor its own card and labels primary and secondary", () => {
    expect(card("monitor-monaaaa").kind).toBe("Monitor 1 · primary");
    expect(card("monitor-monbbbb").kind).toBe("Monitor 2 · secondary");
    expect(card("monitor-monbbbb").match?.(row("display:monbbbb:mode"))).toBe(true);
    expect(card("monitor-monaaaa").match?.(row("display:monbbbb:mode"))).toBe(false);
  });

  it("puts a component's machine-wide tweak in its own card, not on one instance", () => {
    const wlan = row("power:wlan_power_saving", { component: "network_adapter" });
    expect(card("adapters").match?.(wlan)).toBe(true);
    expect(card("adapter-nic1111").match?.(wlan)).toBe(false);
    expect(card("buses").match?.(row("power:pcie_link_state", { component: "pcie" }))).toBe(true);
  });

  it("draws no card for a device that is not present", () => {
    expect(devices.some((d) => d.deviceKey.startsWith("gpu-"))).toBe(false);
    expect(devices.some((d) => d.deviceKey.startsWith("drive-"))).toBe(false);
  });
});

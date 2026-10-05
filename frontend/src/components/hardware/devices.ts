import {
  Cable,
  Cpu,
  EthernetPort,
  HardDrive,
  MemoryStick,
  Monitor,
  Network,
  ScreenShare,
  Speaker,
  Wifi,
  type LucideIcon,
} from "lucide-react";
import type {
  GpuDeviceInfo,
  HardwareInfo,
  MonitorInfo,
  NetworkAdapterInfo,
  StorageDriveInfo,
} from "../../lib/api";
import { isComponentTweak } from "../../lib/tweakDomain";
import type { Setting } from "../../types/setting";
import type { useT } from "../../i18n";


/** The DOM id of a device's card, so Home can open the Hardware page on it. */
export function deviceCardId(key: string): string {
  return `device-${key.replace(/[^A-Za-z0-9_-]/g, "-")}`;
}

type T = ReturnType<typeof useT>["t"];

/** What a device card shows besides its tweaks — the device's own information. */
export type DeviceBody =
  | { type: "cpu" }
  | { type: "memory" }
  | { type: "gpu"; gpu: GpuDeviceInfo }
  | { type: "monitor"; monitor: MonitorInfo; index: number }
  | { type: "drive"; drive: StorageDriveInfo }
  | { type: "adapter"; adapter: NetworkAdapterInfo }
  | { type: "audio" }
  | { type: "shared" };

/** One card: a physical device present on this machine, or a component's shared tweaks. */
export interface DeviceDescriptor {
  deviceKey: string;
  icon: LucideIcon;
  title: string;
  kind?: string;
  summary?: string;
  match?: (setting: Setting) => boolean;
  body: DeviceBody;
  /** A card for machine-wide tweaks only: shown when it holds any. */
  sharedOnly?: boolean;
}

/** Modules holding one vendor's driver tweaks; any other GPU tweak is vendor-neutral. */
const VENDOR_GPU_MODULES = ["gpu-nvidia", "gpu-amd"];

/**
 * Which settings module holds a vendor's driver tweaks.
 *
 * Returning a name no module uses is deliberate for an unknown vendor: an
 * unrecognised card shows no driver tweaks rather than someone else's.
 */
function gpuModuleFor(vendor: string | undefined | null): string {
  const v = (vendor ?? "").toLowerCase();
  if (v.includes("nvidia")) return "gpu-nvidia";
  if (v.includes("amd") || v.includes("radeon")) return "gpu-amd";
  return "gpu-unknown";
}

/**
 * Per-instance settings carry their device as `subject` (an adapter, a monitor);
 * a component's machine-wide ones (TRIM, MPO, Wi-Fi power saving) do not.
 */
const machineWide = (setting: Setting) => !setting.subject;

function monitorSummary(m: MonitorInfo): string {
  const mode = `${m.width}×${m.height}${m.refresh_rate_hz ? ` @ ${m.refresh_rate_hz} Hz` : ""}`;
  const target = m.max_refresh_rate_hz ?? m.native_refresh_rate_hz;
  return m.is_refresh_known && !m.is_refresh_optimal && target ? `${mode} → ${target} Hz` : mode;
}

/**
 * Every card the Hardware page draws, in component order, one per instance.
 *
 * The one list both the Hardware page and Home's compact cards read, so the two
 * can never disagree on which devices exist or which tweaks belong to each.
 * Devices that are not present get no card; a component's machine-wide tweaks
 * get a card of their own rather than being pinned to one instance of it.
 */
export function describeDevices(hardware: HardwareInfo | null, t: T): DeviceDescriptor[] {
  const out: DeviceDescriptor[] = [];
  const cpu = hardware?.cpu;
  out.push({
    deviceKey: "cpu",
    icon: Cpu,
    title: cpu?.name || t("hw.cpu"),
    kind: t("hw.cpu"),
    match: (s) => isComponentTweak(s, "cpu"),
    body: { type: "cpu" },
  });
  out.push({
    deviceKey: "memory",
    icon: MemoryStick,
    title: t("hw.memory"),
    match: (s) => isComponentTweak(s, "memory"),
    body: { type: "memory" },
  });

  (hardware?.gpus ?? []).forEach((gpu, i) => {
    out.push({
      deviceKey: `gpu-${i}`,
      icon: Monitor,
      title: gpu.name || t("hw.gpu"),
      kind: t("hw.gpu"),
      // Driver settings are matched by vendor so an AMD card never shows
      // NVIDIA's; the vendor-neutral ones (Resizable BAR, MSI mode, HAGS, TDR
      // delay) attach to the first card, the machine's primary GPU.
      match: (s) =>
        isComponentTweak(s, "gpu") &&
        (VENDOR_GPU_MODULES.includes(s.module) ? s.module === gpuModuleFor(gpu.vendor) : i === 0),
      body: { type: "gpu", gpu },
    });
  });

  const monitors = hardware?.monitors ?? [];
  monitors.forEach((monitor, i) => {
    const key = monitor.setting_key;
    out.push({
      deviceKey: `monitor-${key ?? i}`,
      icon: ScreenShare,
      title: monitor.friendly_name || monitor.name,
      kind: `${t("device.monitor", { n: i + 1 })} · ${t(monitor.is_primary ? "device.primary" : "device.secondary")}`,
      summary: monitorSummary(monitor),
      match: key ? (s) => s.id.startsWith(`display:${key}:`) : undefined,
      body: { type: "monitor", monitor, index: i },
    });
  });
  out.push({
    deviceKey: "displays",
    icon: ScreenShare,
    title: t("device.allDisplays"),
    match: (s) => isComponentTweak(s, "display") && machineWide(s),
    body: { type: "shared" },
    sharedOnly: true,
  });

  (hardware?.storage_drives ?? []).forEach((drive) => {
    out.push({
      deviceKey: `drive-${drive.drive_letter}`,
      icon: HardDrive,
      title: `${drive.drive_letter}: ${drive.model}`,
      kind: [drive.bus_type, drive.media_type].filter(Boolean).join(" "),
      body: { type: "drive", drive },
    });
  });
  out.push({
    deviceKey: "storage",
    icon: HardDrive,
    title: t("device.allDrives"),
    match: (s) => isComponentTweak(s, "storage"),
    body: { type: "shared" },
    sharedOnly: true,
  });

  (hardware?.network_adapters ?? []).forEach((adapter, i) => {
    const wifi = adapter.adapter_type === "WiFi";
    const key = adapter.setting_key;
    out.push({
      deviceKey: `adapter-${key ?? i}`,
      icon: wifi ? Wifi : adapter.adapter_type === "Ethernet" ? EthernetPort : Network,
      title: adapter.name,
      kind: t(wifi ? "device.wifi" : adapter.adapter_type === "Ethernet" ? "device.ethernet" : "device.adapter"),
      // A disabled adapter is never enumerated and has no per-adapter settings.
      match:
        adapter.interface_index != null && key
          ? (s) => s.id.startsWith(`network:${key}:`)
          : undefined,
      body: { type: "adapter", adapter },
    });
  });
  out.push({
    deviceKey: "adapters",
    icon: Network,
    title: t("device.allAdapters"),
    match: (s) => isComponentTweak(s, "network_adapter") && machineWide(s),
    body: { type: "shared" },
    sharedOnly: true,
  });

  out.push({
    deviceKey: "audio",
    icon: Speaker,
    title: t("hw.audioOutput"),
    // The audio settings act on every output at once (effects, sample rate,
    // exclusive access) or on Windows as a whole (ducking).
    match: (s) => isComponentTweak(s, "audio"),
    body: { type: "audio" },
  });
  out.push({
    deviceKey: "buses",
    icon: Cable,
    title: t("hw.buses"),
    // USB selective suspend and PCIe link power saving act on every device
    // behind the bus.
    match: (s) => isComponentTweak(s, "usb") || isComponentTweak(s, "pcie"),
    body: { type: "shared" },
    sharedOnly: true,
  });
  return out;
}

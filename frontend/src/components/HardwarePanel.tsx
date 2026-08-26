import { useState, useEffect, useSyncExternalStore, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Monitor,
  HardDrive,
  Cpu,
  ScreenShare,
  MemoryStick,
  ShieldCheck,
  ShieldAlert,
  Network,
} from "lucide-react";
import {
  api,
} from "../lib/api";
import { hardwareManager, HardwareInfo } from "../lib/hardware-manager";
import { isComponentTweak } from "../lib/tweakDomain";
import { cn } from "../lib/utils";
import { DisplaysAutoAllButton, MonitorCard } from "./hardware/MonitorCard";

import { HardwareSection, NotDetected } from "./hardware/shared";
import { isCategoryLoading, safeArray } from "./hardware/helpers";
import { useRefreshOnFocus } from "./hardware/useRefreshOnFocus";
import { DeviceTweakList } from "./hardware/DeviceTweakList";
import { NetworkAdapterCard } from "./hardware/NetworkAdapterCard";
import { AudioSection } from "./hardware/AudioSection";
import { StorageDriveCard } from "./hardware/StorageDriveCard";

// Loading indicator component (uses shared LoadingSpinner)
/**
 * Custom hook for hardware data using HardwareManager.
 * Uses useSyncExternalStore for reactive updates with deduplication.
 */
function useHardware(): { hardware: HardwareInfo | null; isLoading: boolean } {
  const [isLoading, setIsLoading] = useState(!hardwareManager.hasData());

  // Subscribe to hardware manager for updates
  const hardware = useSyncExternalStore(
    useCallback((onStoreChange) => {
      return hardwareManager.subscribe(onStoreChange);
    }, []),
    () => hardwareManager.getCached(),
    () => hardwareManager.getCached(),
  );

  // Initial fetch on mount
  useEffect(() => {
    let mounted = true;

    const fetchData = async () => {
      try {
        await hardwareManager.getHardware();
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    };

    if (!hardwareManager.hasData()) {
      fetchData();
    } else {
      setIsLoading(false);
    }

    return () => {
      mounted = false;
    };
  }, []);

  return { hardware, isLoading };
}

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

export function HardwarePanel() {
  const { hardware, isLoading } = useHardware();

  // A change made in the Windows Sound dialog or a vendor tool is invisible to us
  // until something re-reads; coming back to the window is when to do that.
  useRefreshOnFocus();

  const { data: systemInfo } = useQuery({
    queryKey: ["system"],
    queryFn: api.getSystemInfo,
    refetchOnWindowFocus: false,
  });

  return (
    <div className="bg-card rounded-lg border border-border p-4">
      <h3 className="font-medium mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2">
          <Monitor className="w-4 h-4" />
          Hardware
        </span>
        {systemInfo && (
          <span
            className={cn(
              "flex items-center gap-1 text-xs px-2 py-0.5 rounded",
              systemInfo.is_admin
                ? "bg-success/20 text-success"
                : "bg-warning/20 text-warning",
            )}
          >
            {systemInfo.is_admin ? (
              <>
                <ShieldCheck className="w-3 h-3" /> Admin
              </>
            ) : (
              <>
                <ShieldAlert className="w-3 h-3" /> Not Admin
              </>
            )}
          </span>
        )}
      </h3>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 text-sm">
        {/* Column 1: System Hardware */}
        <div className="space-y-1">
          {/* CPU */}
          <HardwareSection
            icon={<Cpu className="w-4 h-4" />}
            title="CPU"
            loading={isCategoryLoading(hardware, isLoading, "cpu")}
          >
            {hardware?.cpu ? (
              <div className="pl-3 border-l-2 border-primary/30">
                <p className="text-sm font-medium">{hardware.cpu.name}</p>
                <p className="text-xs text-muted-foreground">
                  {hardware.cpu.physical_cores}C/{hardware.cpu.logical_cores}T
                  {hardware.cpu.base_clock_mhz &&
                    ` • ${(hardware.cpu.base_clock_mhz / 1000).toFixed(1)} GHz`}
                  {hardware.cpu.cache_l3_mb
                    ? ` • ${hardware.cpu.cache_l3_mb} MB L3`
                    : ""}
                </p>
                {/* Thermal condition is a finding about this chip, not a system
                    setting. It had no home on this page at all. */}
                <DeviceTweakList match={(setting) => isComponentTweak(setting, "cpu")} />
              </div>
            ) : !isLoading ? (
              <NotDetected />
            ) : null}
          </HardwareSection>

          <div className="border-t border-border/50 my-2" />

          {/* RAM */}
          {systemInfo && (
            <>
              <HardwareSection
                icon={<MemoryStick className="w-4 h-4" />}
                title="Memory"
              >
                <div className="pl-3 border-l-2 border-primary/30">
                  <p className="text-sm font-medium">
                    {Math.round(systemInfo.ram_total_mb / 1024)} GB RAM
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {Math.round(systemInfo.ram_available_mb / 1024)} GB
                    available
                  </p>
                  {/* XMP/EXPO is the largest hardware finding fpstune makes and it
                      was filed as a software tweak, so it never appeared beside the
                      memory it is about. */}
                  <DeviceTweakList
                    match={(setting) => isComponentTweak(setting, "memory")}
                  />
                </div>
              </HardwareSection>
              <div className="border-t border-border/50 my-2" />
            </>
          )}

          {/* Power Profile managed in Software Tweaks tab */}

          {/* GPU */}
          <HardwareSection
            icon={<Monitor className="w-4 h-4" />}
            title="GPU"
            loading={isCategoryLoading(hardware, isLoading, "gpu")}
          >
            {safeArray(hardware?.gpus).length > 0 ? (
              <>
                {safeArray(hardware?.gpus).map((gpu, i) => (
                  <div key={i} className="pl-3 border-l-2 border-primary/30">
                    <p className="text-sm font-medium">
                      {gpu?.name || "Unknown"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {gpu?.vendor || ""} {gpu?.driver && `• ${gpu.driver}`}
                      {gpu?.vram_mb &&
                        ` • ${Math.round(gpu.vram_mb / 1024)} GB`}
                    </p>
                    {/* This GPU's own tweaks. Driver settings are matched by vendor
                        so an AMD card never shows NVIDIA's; the vendor-neutral
                        hardware ones (Resizable BAR, MSI mode, GPU assignment)
                        attach to the first card, since they are properties of the
                        machine's primary GPU rather than of every card present. */}
                    <DeviceTweakList
                      match={(setting) =>
                        setting.module === gpuModuleFor(gpu?.vendor) ||
                        (i === 0 && setting.module === "gpu-hardware")
                      }
                    />
                  </div>
                ))}
              </>
            ) : !isLoading && !hardware?.detecting ? (
              <NotDetected />
            ) : null}
          </HardwareSection>

          <div className="border-t border-border/50 my-2" />

          {/* Displays */}
          <HardwareSection
            icon={<ScreenShare className="w-4 h-4" />}
            title="Displays"
            count={safeArray(hardware?.monitors).length}
            loading={isCategoryLoading(hardware, isLoading, "monitors")}
          >
            {safeArray(hardware?.monitors).length > 0 ? (
              <div className="space-y-2">
                <DisplaysAutoAllButton monitors={safeArray(hardware?.monitors)} />
                {safeArray(hardware?.monitors).map((monitor, i) => (
                  <MonitorCard key={i} monitor={monitor} displayIndex={i} />
                ))}
                {/* Windowed flip model and MPO are properties of the display stack,
                    not of one panel, so they sit with the section. */}
                <DeviceTweakList match={(setting) => setting.module === "display"} />
              </div>
            ) : !isLoading ? (
              <NotDetected />
            ) : null}
          </HardwareSection>

          <div className="border-t border-border/50 my-2" />

          {/* Storage */}
          <HardwareSection
            icon={<HardDrive className="w-4 h-4" />}
            title="Storage"
            count={hardware?.storage_drives?.length}
            loading={isCategoryLoading(hardware, isLoading, "storage")}
          >
            {hardware?.storage_drives && hardware.storage_drives.length > 0 ? (
              <div className="space-y-2">
                {hardware.storage_drives.map((drive, i) => (
                  <StorageDriveCard key={i} drive={drive} />
                ))}
                {/* TRIM, 8.3 names and last-access are filesystem-wide, not
                    properties of one drive, so they belong to the section. */}
                <DeviceTweakList match={(setting) => setting.module === "storage"} />
              </div>
            ) : !isLoading ? (
              <NotDetected />
            ) : null}
          </HardwareSection>
        </div>

        {/* Column 2: Connectivity */}
        <div className="space-y-1">
          {/* Network */}
          <HardwareSection
            icon={<Network className="w-4 h-4" />}
            title="Network"
            count={hardware?.network_adapters?.length}
            loading={isCategoryLoading(hardware, isLoading, "network")}
          >
            {hardware?.network_adapters &&
            hardware.network_adapters.length > 0 ? (
              <div className="space-y-3">
                {hardware.network_adapters.map((adapter, i) => (
                  <NetworkAdapterCard key={i} adapter={adapter} />
                ))}
              </div>
            ) : !isLoading ? (
              <NotDetected />
            ) : null}
          </HardwareSection>

          <div className="border-t border-border/50 my-2" />

          {/* Audio - Split by Output/Input */}
          <AudioSection
            devices={hardware?.audio_devices}
            loading={isCategoryLoading(hardware, isLoading, "audio")}
          />
        </div>
      </div>
    </div>
  );
}


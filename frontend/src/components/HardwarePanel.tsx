import { useT } from "../i18n";
import { Card } from "./ui/Card";
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
import { api } from "../lib/api";
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
import { PowerProfileCard } from "./hardware/PowerProfileCard";
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
      } catch {
        // A failed probe leaves the cached (possibly null) inventory standing;
        // the sections render their own NotDetected. Uncaught, this rejection
        // is unhandled — fetchData is fired without an awaiter.
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    };

    // Unconditional, because getHardware() returns the cached inventory
    // immediately when it has one — so the branch that used to call
    // setIsLoading synchronously in the effect body is not needed, and that
    // call was a cascading render React would have had to bail out of.
    fetchData();

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
  const { t } = useT();
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
    <Card className="p-4">
      <h3 className="font-medium mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2">
          <Monitor className="w-4 h-4" />
          {t("hw.title")}
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
                <ShieldCheck className="w-3 h-3" /> {t("hw.admin")}
              </>
            ) : (
              <>
                <ShieldAlert className="w-3 h-3" /> {t("hw.notAdmin")}
              </>
            )}
          </span>
        )}
      </h3>

      {/* Three columns of sections, not two, once the window can hold them.
          The old split was System (six sections) beside Connectivity (two), so
          the right half ran out two thirds of the way down and the left half
          carried the rest alone. Connectivity spans the full row at `lg` and
          becomes the third column at `2xl`, so no width is left empty at either
          size. Column order is the reading order the single column had. */}
      <div
        data-testid="hardware-columns"
        className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-6 text-sm items-start"
      >
        {/* Column 1: the chip and what feeds it */}
        <div className="space-y-1">
          {/* CPU */}
          <HardwareSection
            icon={<Cpu className="w-4 h-4" />}
            title={t("hw.cpu")}
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
                <DeviceTweakList
                  match={(setting) => isComponentTweak(setting, "cpu")}
                />
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
                title={t("hw.memory")}
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

          {/* Power plan — the FPS Balanced profile's status and switch. */}
          <PowerProfileCard />

          {/* GPU */}
          <HardwareSection
            icon={<Monitor className="w-4 h-4" />}
            title={t("hw.gpu")}
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
        </div>

        {/* Column 2: what the frames come out on, and where they are stored */}
        <div className="space-y-1">
          {/* Displays */}
          <HardwareSection
            icon={<ScreenShare className="w-4 h-4" />}
            title={t("hw.displays")}
            count={safeArray(hardware?.monitors).length}
            loading={isCategoryLoading(hardware, isLoading, "monitors")}
          >
            {safeArray(hardware?.monitors).length > 0 ? (
              <div className="space-y-2">
                <DisplaysAutoAllButton
                  monitors={safeArray(hardware?.monitors)}
                />
                {safeArray(hardware?.monitors).map((monitor, i) => (
                  <MonitorCard key={i} monitor={monitor} displayIndex={i} />
                ))}
                {/* Windowed flip model and MPO are properties of the display stack,
                    not of one panel, so they sit with the section. */}
                <DeviceTweakList
                  match={(setting) => setting.module === "display"}
                />
              </div>
            ) : !isLoading ? (
              <NotDetected />
            ) : null}
          </HardwareSection>

          <div className="border-t border-border/50 my-2" />

          {/* Storage */}
          <HardwareSection
            icon={<HardDrive className="w-4 h-4" />}
            title={t("hw.storage")}
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
                <DeviceTweakList
                  match={(setting) => setting.module === "storage"}
                />
              </div>
            ) : !isLoading ? (
              <NotDetected />
            ) : null}
          </HardwareSection>
        </div>

        {/* Column 3: Connectivity. Full width at `lg`, where there is no third
            column for it to be; its own two sections split that width. */}
        <div className="space-y-1 lg:col-span-2 lg:grid lg:grid-cols-2 lg:gap-6 lg:space-y-0 2xl:col-span-1 2xl:block 2xl:space-y-1">
          {/* Network */}
          <HardwareSection
            icon={<Network className="w-4 h-4" />}
            title={t("hw.network")}
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

          {/* The rule that separates two stacked sections. Where they are side
              by side (`lg`) the gap already separates them, and a third grid
              item would take one of the two cells. */}
          <div className="border-t border-border/50 my-2 lg:hidden 2xl:block" />

          {/* Audio - Split by Output/Input */}
          <AudioSection
            devices={hardware?.audio_devices}
            loading={isCategoryLoading(hardware, isLoading, "audio")}
          />
        </div>
      </div>
    </Card>
  );
}

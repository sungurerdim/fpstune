import { useT } from "../i18n";
import { Card } from "./ui/Card";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Monitor, ShieldCheck, ShieldAlert, Loader2 } from "lucide-react";
import { api, type HardwareInfo, type SystemInfo } from "../lib/api";
import { useStore } from "../store";
import { isHardwareTweak } from "../lib/tweakDomain";
import { isTweakAdvisory, isTweakListable } from "../lib/tweakStatus";
import { ScopeActions } from "./ScopeActions";
import { Metric, MetricList, ScopeHeader } from "./ui/ScopeHeader";
import { DisplaysAutoAllButton, MonitorCard } from "./hardware/MonitorCard";
import { useRefreshOnFocus } from "./hardware/useRefreshOnFocus";
import { useHardware } from "./hardware/useHardware";
import { SelectionToolbar } from "./SelectionToolbar";
import { NetworkAdapterCard } from "./hardware/NetworkAdapterCard";
import { AudioSection } from "./hardware/AudioSection";
import { PowerProfileCard } from "./hardware/PowerProfileCard";
import { StorageDriveCard } from "./hardware/StorageDriveCard";
import { DeviceCard } from "./hardware/DeviceCard";
import { describeDevices, type DeviceDescriptor } from "./hardware/devices";

/**
 * The Hardware page: one card per piece of hardware, in component order.
 *
 * Each network adapter, monitor and drive is its own card, so Wi-Fi and
 * Ethernet — or two monitors — never share a list. A card carries the device's
 * information, its state in one line, its own Apply / Undo / Windows default
 * and its tweaks; a component's machine-wide tweaks (TRIM, MPO, USB and PCIe
 * power saving) sit in a card of their own. Two columns where the window has
 * room, one where it does not; the reading order is the column order.
 */
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

  const devices = useMemo(() => describeDevices(hardware, t), [hardware, t]);

  // The page's own scope: every hardware tweak some card on this page claims.
  const storeSettings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const pageSettings = useMemo(
    () =>
      [...storeSettings.values()].filter(
        (s) =>
          isHardwareTweak(s) &&
          (isTweakListable(s) || isTweakAdvisory(s)) &&
          devices.some((d) => d.match?.(s)),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
    [storeSettings, settingsVersion, devices],
  );

  return (
    <Card className="p-4">
      <ScopeHeader
        level={2}
        className="mb-3"
        icon={<Monitor className="h-4 w-4" aria-hidden />}
        title={t("hw.title")}
        metrics={
          systemInfo && (
            <MetricList>
              <Metric
                tone={systemInfo.is_admin ? "ok" : "attention"}
                label={systemInfo.is_admin ? t("hw.admin") : t("hw.notAdmin")}
                icon={
                  systemInfo.is_admin ? (
                    <ShieldCheck className="h-3 w-3" aria-hidden />
                  ) : (
                    <ShieldAlert className="h-3 w-3" aria-hidden />
                  )
                }
              />
            </MetricList>
          )
        }
        /* Page scope: exactly the tweaks the cards below draw. */
        actions={<ScopeActions settings={pageSettings} name={t("tab.hardware")} />}
      />

      {/* Power plan — the FPS Balanced profile's status and switch. */}
      <PowerProfileCard />

      {(isLoading || hardware?.detecting) && (
        <p className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
          {t("devices.reading")}
        </p>
      )}

      <div
        data-testid="hardware-columns"
        className="grid grid-cols-1 xl:grid-cols-2 gap-3 text-sm items-start"
      >
        {devices.map((device) => (
          <DeviceCard
            key={device.deviceKey}
            deviceKey={device.deviceKey}
            icon={device.icon}
            title={device.title}
            kind={device.kind}
            summary={device.summary}
            match={device.match}
            sharedOnly={device.sharedOnly}
          >
            <DeviceInfo device={device} hardware={hardware} systemInfo={systemInfo} />
          </DeviceCard>
        ))}
      </div>
      {/* Hardware rows are selectable like any other; the selection scope. */}
      <SelectionToolbar />
    </Card>
  );
}

/** The device's own information inside its card: measurements and its own controls. */
function DeviceInfo({
  device,
  hardware,
  systemInfo,
}: {
  device: DeviceDescriptor;
  hardware: HardwareInfo | null;
  systemInfo: SystemInfo | undefined;
}) {
  const { t } = useT();
  const body = device.body;
  switch (body.type) {
    case "cpu": {
      const cpu = hardware?.cpu;
      if (!cpu) return null;
      return (
        <p className="text-xs text-muted-foreground">
          {cpu.physical_cores}C/{cpu.logical_cores}T
          {cpu.base_clock_mhz && ` • ${(cpu.base_clock_mhz / 1000).toFixed(1)} GHz`}
          {cpu.cache_l3_mb ? ` • ${cpu.cache_l3_mb} MB L3` : ""}
        </p>
      );
    }
    case "memory":
      if (!systemInfo) return null;
      return (
        <p className="text-xs text-muted-foreground">
          {t("hw.ramSummary", {
            total: Math.round(systemInfo.ram_total_mb / 1024),
            available: Math.round(systemInfo.ram_available_mb / 1024),
          })}
        </p>
      );
    case "gpu":
      return (
        <p className="text-xs text-muted-foreground">
          {body.gpu.vendor || ""} {body.gpu.driver && `• ${body.gpu.driver}`}
          {body.gpu.vram_mb && ` • ${Math.round(body.gpu.vram_mb / 1024)} GB`}
        </p>
      );
    case "monitor":
      return (
        <>
          {body.index === 0 && (hardware?.monitors.length ?? 0) > 1 && (
            <DisplaysAutoAllButton monitors={hardware?.monitors ?? []} />
          )}
          <MonitorCard monitor={body.monitor} displayIndex={body.index} />
        </>
      );
    case "drive":
      return <StorageDriveCard drive={body.drive} />;
    case "adapter":
      return <NetworkAdapterCard adapter={body.adapter} />;
    case "audio":
      return <AudioSection devices={hardware?.audio_devices} loading={!hardware} />;
    case "shared":
      return null;
  }
}

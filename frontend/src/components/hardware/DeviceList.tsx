import { useId, useMemo, useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useT } from "../../i18n";
import { cn } from "../../lib/utils";
import type { HardwareInfo } from "../../lib/api";
import { useStore } from "../../store";
import type { Setting } from "../../types/setting";
import { DeviceHeader } from "./DeviceHeader";
import {
  deviceCardId,
  deviceSpec,
  listDevices,
  tweaksByDevice,
  type DeviceDescriptor,
} from "./devices";

/**
 * The machine's devices, one under another: GPU, Monitor 1, Monitor 2, adapters,
 * storage. Each is a single line; selecting one opens its tweaks beneath it.
 *
 * One device is open at a time. The row list is a slot (`renderRows`), so this
 * component knows which tweaks belong to a device and nothing about how a tweak
 * is drawn. Each header is a real button (Enter and Space select, `aria-expanded`
 * and `aria-controls` say what it opens), and a machine-wide group with no
 * tweaks is not listed at all.
 */
export function DeviceList({
  hardware,
  renderRows,
  selectedKey,
  onSelect,
}: {
  hardware: HardwareInfo | null;
  /** The device's tweaks, drawn by the caller. */
  renderRows: (device: DeviceDescriptor, settings: Setting[]) => ReactNode;
  /** Controlled selection; omit for an uncontrolled list that starts closed. */
  selectedKey?: string | null;
  onSelect?: (key: string | null) => void;
}) {
  const { t } = useT();
  const listId = useId();
  const [ownKey, setOwnKey] = useState<string | null>(null);
  const open = selectedKey !== undefined ? selectedKey : ownKey;
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const detecting = useStore((s) => s.isAnyCategoryLoading());

  const devices = useMemo(() => listDevices(hardware, t), [hardware, t]);
  const tweaks = useMemo(
    () => tweaksByDevice(devices, settings.values()),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
    [devices, settings, settingsVersion],
  );

  const select = (key: string) => {
    const next = open === key ? null : key;
    if (selectedKey === undefined) setOwnKey(next);
    onSelect?.(next);
  };

  return (
    <ul aria-label={t("devices.listLabel")} className="space-y-1">
      {devices.map((device) => {
        const set = tweaks.get(device.deviceKey);
        if (!set) return null;
        if (device.sharedOnly && set.settings.length === 0) return null;
        const isOpen = open === device.deviceKey;
        const buttonId = `${listId}-${device.deviceKey}-button`;
        const panelId = `${listId}-${device.deviceKey}-panel`;
        const Chevron = isOpen ? ChevronDown : ChevronRight;
        return (
          <li
            key={device.deviceKey}
            id={deviceCardId(device.deviceKey)}
            className="rounded-md border border-border bg-card"
          >
            <h3>
              <button
                type="button"
                id={buttonId}
                aria-expanded={isOpen}
                aria-controls={panelId}
                onClick={() => select(device.deviceKey)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left",
                  "hover:bg-muted/50",
                )}
              >
                <Chevron className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 flex-1">
                  <DeviceHeader
                    icon={device.icon}
                    name={device.title}
                    spec={deviceSpec(device)}
                    notOptimized={set.notOptimized}
                    reading={detecting && set.settings.length === 0}
                  />
                </span>
              </button>
            </h3>
            {isOpen && (
              <div
                id={panelId}
                role="region"
                aria-labelledby={buttonId}
                className="border-t border-border px-3 py-2"
              >
                {set.settings.length > 0 ? (
                  renderRows(device, set.settings)
                ) : (
                  <p className="text-xs text-muted-foreground">{t("device.nothingToDo")}</p>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

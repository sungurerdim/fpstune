import type { ReactNode } from "react";
import { ChevronRight, CircleCheck, CircleSlash, Wrench, type LucideIcon } from "lucide-react";
import { useT } from "../../i18n";
import { cn } from "../../lib/utils";
import { useStore } from "../../store";
import { useDeviceTweaks } from "../../hooks/useDeviceTweaks";
import type { Setting } from "../../types/setting";
import { ScopeActions } from "../ScopeActions";
import { TweakBands } from "../TweakBands";
import type { TweakRow } from "../TweakRows";
import { deviceCardId } from "./devices";

export interface DeviceCardProps {
  /** Stable per instance: the component, plus the adapter or monitor key. */
  deviceKey: string;
  icon: LucideIcon;
  /** The device in words: its model, or the component when there is one. */
  title: string;
  /** What kind of device, and which one ("Wi-Fi", "Monitor 2 · secondary"). */
  kind?: string;
  /** A state the device itself reports ("1920×1080 @ 60 Hz → 165 Hz"). */
  summary?: string;
  /** Which settings belong to this device. Absent: a device with nothing to tune. */
  match?: (setting: Setting) => boolean;
  /** The device's own information — model, measurements, its own controls. */
  children?: ReactNode;
  /** A card for a component's machine-wide tweaks: drawn only when it holds some. */
  sharedOnly?: boolean;
}

type Tone = "attention" | "ok" | "none";

/**
 * One piece of hardware: its icon and name, a one-line state, a coloured edge,
 * the device's own Apply / Undo / Windows default, then its tweaks.
 *
 * The edge is never the only signal (amber = something to do, green = ideal,
 * grey = nothing to tune here): the status line says the same thing in words
 * with its own icon, and every action names the device in its accessible name.
 */
export function DeviceCard({
  deviceKey,
  icon: Icon,
  title,
  kind,
  summary,
  match,
  children,
  sharedOnly,
}: DeviceCardProps) {
  const { t } = useT();
  const tweaks = useDeviceTweaks(match);
  const detecting = useStore((s) => s.isAnyCategoryLoading());
  const tone = toneOf(tweaks.toApply + tweaks.advisories, tweaks.settings.length);
  const headingId = `${deviceCardId(deviceKey)}-title`;
  const rows: TweakRow[] = tweaks.settings.map((setting) => ({ setting }));
  if (sharedOnly && tweaks.settings.length === 0) return null;

  return (
    <section
      id={deviceCardId(deviceKey)}
      aria-labelledby={headingId}
      data-tone={tone}
      className={cn(
        "rounded-lg border border-border border-l-4 bg-card p-3 space-y-2 scroll-mt-4",
        EDGE[tone],
      )}
    >
      <div className="flex flex-wrap items-start gap-2">
        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary/80" aria-hidden />
        <div className="min-w-0 flex-1">
          <h3 id={headingId} className="truncate text-sm font-medium" title={title}>
            {title}
          </h3>
          <p className="text-xs text-muted-foreground">
            {[kind, summary].filter(Boolean).join(" · ")}
          </p>
          <DeviceStatus
            tone={tone}
            toApply={tweaks.toApply}
            advisories={tweaks.advisories}
            reading={detecting && tweaks.settings.length === 0}
          />
        </div>
        <ScopeActions settings={tweaks.settings} name={title} />
      </div>
      {children && <div className="space-y-1 text-sm">{children}</div>}
      {rows.length > 0 && <TweakBands rows={rows} />}
      {rows.length === 0 && !detecting && match && (
        <p className="text-xs text-muted-foreground">{t("device.nothingToDo")}</p>
      )}
    </section>
  );
}

/**
 * Home's compact card: only devices with something to do, one Apply, and a way
 * to the full card on the Hardware page.
 */
export function DeviceCardCompact({
  deviceKey,
  icon: Icon,
  title,
  kind,
  match,
}: Pick<DeviceCardProps, "deviceKey" | "icon" | "title" | "kind" | "match">) {
  const { t } = useT();
  const tweaks = useDeviceTweaks(match);
  const setActiveTab = useStore((s) => s.setActiveTab);
  if (tweaks.toApply === 0) return null;

  const open = () => {
    setActiveTab("hardware");
    // The Hardware page mounts on the tab switch; scroll once it has.
    requestAnimationFrame(() =>
      document.getElementById(deviceCardId(deviceKey))?.scrollIntoView({ block: "start" }),
    );
  };

  return (
    <section
      aria-label={title}
      data-tone="attention"
      className={cn("flex flex-wrap items-center gap-2 rounded-lg border border-border border-l-4 bg-card px-3 py-2", EDGE.attention)}
    >
      <Icon className="h-4 w-4 shrink-0 text-primary/80" aria-hidden />
      <button
        type="button"
        onClick={open}
        aria-label={t("device.open", { name: title })}
        className="flex min-w-0 flex-1 items-center gap-1 text-left text-sm hover:underline"
      >
        <span className="truncate font-medium">{title}</span>
        {kind && <span className="shrink-0 text-xs text-muted-foreground">{kind}</span>}
        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
      </button>
      <span className="text-xs text-warning">{t("device.toApply", { count: tweaks.toApply })}</span>
      <ScopeActions settings={tweaks.settings} name={title} only={["apply"]} />
    </section>
  );
}

const EDGE: Record<Tone, string> = {
  attention: "border-l-warning",
  ok: "border-l-success",
  none: "border-l-border",
};

function toneOf(open: number, listed: number): Tone {
  if (open > 0) return "attention";
  return listed > 0 ? "ok" : "none";
}

function DeviceStatus({
  tone,
  toApply,
  advisories,
  reading,
}: {
  tone: Tone;
  toApply: number;
  advisories: number;
  reading: boolean;
}) {
  const { t } = useT();
  if (reading) return <p className="text-xs text-muted-foreground">{t("devices.reading")}</p>;
  if (tone === "none") {
    return (
      <p className="flex items-center gap-1 text-xs text-muted-foreground">
        <CircleSlash className="h-3 w-3" aria-hidden />
        {t("device.noTweaks")}
      </p>
    );
  }
  if (tone === "ok") {
    return (
      <p className="flex items-center gap-1 text-xs text-success">
        <CircleCheck className="h-3 w-3" aria-hidden />
        {t("device.ideal")}
      </p>
    );
  }
  return (
    <p className="flex flex-wrap items-center gap-x-2 text-xs text-warning">
      <Wrench className="h-3 w-3" aria-hidden />
      {toApply > 0 && <span>{t("device.toApply", { count: toApply })}</span>}
      {advisories > 0 && (
        <span title={t("devices.advisoryHint")}>{t("devices.needYou", { count: advisories })}</span>
      )}
    </p>
  );
}

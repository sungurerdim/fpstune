import { useT } from "../../i18n";
import { useMemo } from "react";
import { CircleCheck, Wrench } from "lucide-react";
import { useStore } from "../../store";
import { isTweakAdvisory, isTweakListable, isTweakSuboptimal } from "../../lib/tweakStatus";
import { StatusChip } from "../ui/StatusChip";
import { ScopeActions } from "../ScopeActions";
import { TweakBands } from "../TweakBands";
import type { TweakRow } from "../TweakRows";
import type { Setting } from "../../types/setting";

/**
 * The tweaks belonging to one device: a status line with the device's own
 * Apply / Undo / Windows default, then its rows in the shared bands.
 *
 * The rows are the same `TweakRows` the Software and Game pages use, so a
 * hardware tweak gets Reset, Undo, Verify and selection like any other — it used
 * to get a private row with Apply only. Three things this list still owes the
 * reader, each guarded by a test:
 *
 *  - nothing renders below `text-xs`; the page once mixed 9, 10 and 11px.
 *  - the summary is a chip with a background, so "6 to fix" and "all ideal" differ
 *    at a glance instead of on inspection.
 *  - advisories are listed. `isTweakListable` excludes `isReadonly`, so Resizable
 *    BAR, GPU assignment and a link under its own capability — the findings most
 *    likely to cost real frames — were once never shown on the page about
 *    hardware. They are counted apart from the fixable ones, because a single
 *    count spanning both would make Apply a claim about settings it will not touch.
 */
export function DeviceTweakList({
  match,
  name,
}: {
  /** Which settings belong to this device. Kept as a predicate so a card can key
   *  off whatever identifies its hardware — an adapter key, a vendor, a component. */
  match: (setting: Setting) => boolean;
  /** The device in words, carried into every action's accessible name. */
  name: string;
}) {
  const { t } = useT();
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const detecting = useStore((s) => s.isAnyCategoryLoading());

  const { rows, members, toFix, advisories } = useMemo(() => {
    const listed: Setting[] = [];
    for (const s of settings.values()) {
      if (match(s) && (isTweakListable(s) || isTweakAdvisory(s))) listed.push(s);
    }
    listed.sort((a, b) => a.categoryOrder - b.categoryOrder);
    return {
      rows: listed.map((setting): TweakRow => ({ setting })),
      members: listed,
      toFix: listed.filter(isTweakSuboptimal).length,
      advisories: listed.filter(isTweakAdvisory).length,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settings, settingsVersion, match]);

  // Nothing detected for this device yet: say so rather than implying it is clean.
  if (rows.length === 0) {
    if (!detecting) return null;
    return <p className="pl-4 pt-1 text-xs text-muted-foreground">{t("devices.reading")}</p>;
  }

  return (
    <div className="space-y-1.5 pl-4 pt-1.5">
      <div className="flex flex-wrap items-center gap-2">
        {toFix > 0 ? (
          <StatusChip tone="attention" icon={<Wrench className="h-3.5 w-3.5" />}>
            {t("devices.toFix", { count: toFix })}
          </StatusChip>
        ) : advisories === 0 ? (
          <StatusChip tone="ok" icon={<CircleCheck className="h-3.5 w-3.5" />}>
            {t("devices.allIdeal", { count: rows.length })}
          </StatusChip>
        ) : null}
        {advisories > 0 && (
          <StatusChip tone="advisory" title={t("devices.advisoryHint")}>
            {t("devices.needYou", { count: advisories })}
          </StatusChip>
        )}
        <ScopeActions settings={members} name={name} className="ml-auto" />
      </div>
      <TweakBands rows={rows} />
    </div>
  );
}

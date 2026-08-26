import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, Zap, CircleCheck, Wrench } from "lucide-react";
import { useStore } from "../../store";
import { cn } from "../../lib/utils";
import { isTweakAdvisory, isTweakListable, isTweakSuboptimal } from "../../lib/tweakStatus";
import { useApplySingle } from "../../hooks/useApplySingle";
import { useBulkApply } from "../../hooks/useBulkApply";
import { StatusChip } from "../ui/StatusChip";
import type { Setting } from "../../types/setting";

/**
 * The tweaks belonging to one device, in the shape the Hardware page already reads
 * well: `current -> ideal` on one line, amber when they differ.
 *
 * This is the answer to the Software Tweaks hierarchy, which buried a setting under
 * group -> category -> module card -> expand and showed six cards and zero actual
 * tweaks on a 1600px screen. Here a tweak sits next to the device it belongs to and
 * states what is wrong without anything being expanded.
 *
 * Rewritten after the page was described as unreadable — "status and urgency do not
 * read, the fonts are tiny, everything is collapsed, all of it is hard to see". Three
 * things changed, and each maps to one of those:
 *
 *  - nothing on this page renders below `text-xs` any more. It was a mix of 9, 10 and
 *    11px, which is below what the rest of the app uses and below what most people
 *    read comfortably at arm's length.
 *  - the summary is a chip with a background rather than grey text, so "6 to fix" and
 *    "all ideal" are different at a glance instead of on inspection.
 *  - advisories are listed. `isTweakListable` excludes `isReadonly`, and nothing else
 *    picked them up, so Resizable BAR, GPU assignment, the fan curve and a link
 *    running under its own capability — the findings most likely to cost real frames —
 *    were never shown on the page about hardware. They are listed separately from the
 *    fixable ones, because a single count spanning both would make Fix all a claim
 *    about settings it will not touch.
 */
export function DeviceTweakList({
  match,
  emptyLabel,
}: {
  /** Which settings belong to this device. Kept as a predicate so a card can key
   *  off whatever identifies its hardware — an interface index, a vendor, a module. */
  match: (setting: Setting) => boolean;
  /** Shown when the device has tweaks and all of them are already ideal. */
  emptyLabel?: string;
}) {
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const detecting = useStore((s) => s.isAnyCategoryLoading());
  const { applySingle, isPending } = useApplySingle();
  const { apply, isApplying } = useBulkApply();
  const [showAll, setShowAll] = useState(false);

  const { listable, suboptimal, advisories } = useMemo(() => {
    const all: Setting[] = [];
    const advice: Setting[] = [];
    for (const s of settings.values()) {
      if (!match(s)) continue;
      if (isTweakListable(s)) all.push(s);
      else if (isTweakAdvisory(s)) advice.push(s);
    }
    all.sort((a, b) => a.categoryOrder - b.categoryOrder);
    advice.sort((a, b) => a.categoryOrder - b.categoryOrder);
    return { listable: all, suboptimal: all.filter(isTweakSuboptimal), advisories: advice };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settings, settingsVersion, match]);

  // Nothing detected for this device yet: say so rather than implying it is clean.
  if (listable.length === 0 && advisories.length === 0) {
    if (!detecting) return null;
    return <p className="pl-4 pt-1 text-xs text-muted-foreground">Reading tweaks…</p>;
  }

  const rows = showAll ? listable : suboptimal;

  const applyAll = () => {
    const payload: Record<string, unknown> = {};
    for (const s of suboptimal) payload[s.id] = s.recommendedValue;
    if (Object.keys(payload).length > 0) apply(payload);
  };

  return (
    <div className="pl-4 pt-1.5 space-y-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setShowAll(!showAll)}
          aria-expanded={showAll}
          aria-label={
            showAll ? "Hide tweaks already ideal" : "Show tweaks already ideal"
          }
          className="flex items-center gap-1 rounded text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          disabled={listable.length === 0}
        >
          {showAll ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
          {suboptimal.length > 0 ? (
            <StatusChip tone="attention" icon={<Wrench className="h-3.5 w-3.5" />}>
              {suboptimal.length} to fix
            </StatusChip>
          ) : listable.length > 0 ? (
            <StatusChip tone="ok" icon={<CircleCheck className="h-3.5 w-3.5" />}>
              {emptyLabel ?? `All ${listable.length} ideal`}
            </StatusChip>
          ) : null}
        </button>

        {advisories.length > 0 && (
          <StatusChip
            tone="advisory"
            title="fpstune cannot change these — each row says where to."
          >
            {advisories.length} need you
          </StatusChip>
        )}

        {suboptimal.length > 0 && (
          <button
            onClick={applyAll}
            disabled={isApplying}
            className={cn(
              "ml-auto inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              isApplying
                ? "cursor-wait bg-muted text-muted-foreground"
                : "bg-warning/20 text-warning hover:bg-warning/30",
            )}
          >
            {isApplying ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Zap className="h-3.5 w-3.5" />
            )}
            Fix all
          </button>
        )}
      </div>

      {rows.map((setting) => (
        <TweakRow
          key={setting.id}
          setting={setting}
          pending={isPending(setting.id)}
          onApply={() => applySingle(setting, setting.recommendedValue)}
        />
      ))}

      {advisories.map((setting) => (
        <AdvisoryRow key={setting.id} setting={setting} />
      ))}
    </div>
  );
}

/** One tweak as `name  current -> ideal`, with the fix attached to the row. */
function TweakRow({
  setting,
  pending,
  onApply,
}: {
  setting: Setting;
  pending: boolean;
  onApply: () => void;
}) {
  const off = isTweakSuboptimal(setting);

  return (
    <div className="flex items-center gap-2 text-xs" title={setting.description}>
      <span className="truncate text-muted-foreground">{setting.displayName}</span>
      <span className={cn("font-medium", off ? "text-warning" : "text-success")}>
        {String(setting.currentValue)}
      </span>
      {off && (
        <>
          <span aria-hidden className="text-muted-foreground">
            →
          </span>
          <span className="font-medium text-success">
            {String(setting.recommendedValue)}
          </span>
          {setting.riskLevel === "advanced" && (
            <span
              title={setting.riskWarning}
              className="cursor-default rounded border border-warning/30 bg-warning/20 px-1 text-xs font-medium text-warning"
            >
              ADV
            </span>
          )}
          <button
            onClick={onApply}
            disabled={pending}
            aria-label={`Apply ${setting.displayName}`}
            className="ml-auto shrink-0 rounded-md bg-primary/15 px-2 py-1 text-xs font-medium text-primary transition-colors hover:bg-primary/25 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Fix"}
          </button>
        </>
      )}
    </div>
  );
}

/**
 * A finding fpstune cannot write.
 *
 * Deliberately shaped unlike a TweakRow: no arrow to an ideal value it cannot reach,
 * no Fix button that would do nothing. What it carries instead is the one thing the
 * user needs, which is where to go — `effect` on an advisory setting is written as
 * the instruction ("In BIOS, go to Advanced > PCI and set...").
 */
function AdvisoryRow({ setting }: { setting: Setting }) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <span className="truncate text-muted-foreground">{setting.displayName}</span>
      <span className="font-medium text-amber-400">{String(setting.currentValue)}</span>
      <span
        className="ml-auto max-w-[60%] shrink text-right leading-snug text-muted-foreground"
        title={setting.riskWarning ?? setting.effect}
      >
        {setting.effect}
      </span>
    </div>
  );
}

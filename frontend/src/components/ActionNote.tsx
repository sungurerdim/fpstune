import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, HardDrive, Loader2 } from "lucide-react";
import { useT } from "../i18n";
import { fmtMB } from "../lib/cleanupSize";
import { parseActionReading, type ActionReading } from "../lib/actionReading";
import { useStore, type RunStep } from "../store";
import type { Setting } from "../types/setting";

/**
 * What a cleanup row says on its one line, beside its name: what it can reclaim,
 * what it is doing, what it did.
 *
 * Three rules carry over from the card this replaces, all C11. A percentage
 * appears only for a command that printed one; a command that prints none shows
 * the seconds it has been running, which is a different measurement rather than
 * an invented one. A reclaimable size appears only once it was measured. And the
 * freed figure is whatever the backend measured (before − after, in bytes), never
 * a claim from the registry. A failure is not repeated here: the row's own status
 * mark carries it and its reason.
 */
export function ActionNote({ setting }: { setting: Setting }) {
  const result = useStore((s) => s.cleanupResults[setting.id]);
  const step = useStore((s) => s.runSteps.find((r) => r.id === setting.id));
  const reading = parseActionReading(setting.currentValue);
  const running = step?.status === "running";

  return (
    <span className="flex min-w-0 max-w-[60%] shrink items-center gap-1.5 text-xs">
      {running && step ? (
        <Progress step={step} />
      ) : (
        result?.success && <Outcome sized={result.sized} freedMB={result.freedMB} />
      )}
      <ReadingBadge reading={reading} />
    </span>
  );
}

/**
 * What this action's last detection read, as the kind of thing it read.
 *
 * A cleanup reports a reclaimable size, the SSD retrim reports how long its
 * upkeep has been overdue, and the two are not interchangeable: every reading
 * used to go through the size parser, so `overdue|never` put the word "never"
 * in a badge with a hard-drive icon. An action that reports nothing readable — a
 * repair, or a payload this build cannot account for — gets no badge at all
 * rather than a figure that would read as a measurement.
 */
function ReadingBadge({ reading }: { reading: ActionReading | null }) {
  const { t } = useT();
  if (reading === null) return null;
  const badge = "flex min-w-0 items-center gap-1 rounded px-1.5 py-0.5";
  if (reading.kind === "overdue") {
    const text =
      reading.detail === "never"
        ? t("cleanup.trimOverdueNever")
        : t("cleanup.trimOverdueDays", { days: reading.detail.days });
    return (
      <span title={text} className={`${badge} bg-warning/10 font-medium text-warning`}>
        <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
        <span className="min-w-0 truncate">{text}</span>
      </span>
    );
  }
  if (reading.kind === "ok") {
    // Muted: upkeep that is current is context for the row, not a call to act.
    const text =
      reading.days === 0
        ? t("cleanup.trimLastUnderDay")
        : t("cleanup.trimLastDays", { days: reading.days });
    return (
      <span title={text} className={`${badge} bg-muted text-muted-foreground`}>
        <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden="true" />
        <span className="min-w-0 truncate">{text}</span>
      </span>
    );
  }
  if (reading.size === "calculating") {
    return (
      <span className={`${badge} bg-muted text-muted-foreground`}>
        <Loader2 className="h-3 w-3 shrink-0 animate-spin" aria-hidden="true" />
        <span className="min-w-0 truncate">{t("cleanup.calculating")}</span>
      </span>
    );
  }
  if (reading.size === "unavailable") {
    return (
      <span
        title={t("cleanup.serviceDown")}
        className={`${badge} bg-warning/10 text-warning`}
      >
        <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
        <span className="min-w-0 truncate">{t("cleanup.unavailable")}</span>
      </span>
    );
  }
  return (
    <span title={reading.size} className={`${badge} bg-primary/10 font-medium text-primary`}>
      <HardDrive className="h-3 w-3 shrink-0" aria-hidden="true" />
      <span className="min-w-0 truncate">{reading.size}</span>
    </span>
  );
}

/** What the last run of this action did, once it succeeded. */
function Outcome({ sized, freedMB }: { sized: boolean; freedMB: number | null }) {
  const { t } = useT();
  // Succeeded but nothing measured a byte count — a repair, or a cleanup whose
  // new size never came back. It says what it knows and no more (C11 rule 3).
  if (!sized || freedMB === null) {
    return (
      <span className="flex shrink-0 items-center gap-1 text-success">
        <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
        {t("cleanup.done")}
      </span>
    );
  }
  return (
    <span className="shrink-0 whitespace-nowrap font-medium text-primary">
      {t("cleanup.freed", { amount: fmtMB(freedMB) })}
    </span>
  );
}

/**
 * The live account of a running action: how far it has got, or how long it has
 * been going, with the command it runs and its newest line on hover.
 *
 * The tick is the only thing moving during a command that prints nothing for
 * minutes: without it, "no output yet" and "hung" look identical.
 */
function Progress({ step }: { step: RunStep }) {
  const { t } = useT();
  const elapsed = useElapsed(step);
  const latest = step.lines.length > 0 ? step.lines[step.lines.length - 1] : "";
  const detail = [step.command, latest].filter(Boolean).join("\n");

  return (
    <span
      title={detail || undefined}
      className="min-w-0 truncate tabular-nums text-muted-foreground"
    >
      {step.percent !== null
        ? t("run.percent", { value: Math.round(step.percent) })
        : t("run.elapsed", { seconds: elapsed })}
    </span>
  );
}

/** Seconds a step has been running, ticking while it runs. */
function useElapsed(step: RunStep): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (step.status !== "running") return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [step.status]);

  if (!step.startedAt) return 0;
  return Math.max(0, Math.round(((step.endedAt ?? now) - step.startedAt) / 1000));
}

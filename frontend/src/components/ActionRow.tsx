import { useEffect, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  HardDrive,
  Info,
  Loader2,
  MinusCircle,
  Trash2,
  Wrench,
  XCircle,
} from "lucide-react";
import { useT } from "../i18n";
import { localizedDescription, localizedName } from "../i18n/settings";
import { Button } from "./ui/Button";
import { Progress } from "./ui/Feedback";
import { cn } from "../lib/utils";
import { fmtMB } from "../lib/cleanupSize";
import { parseActionReading, type ActionReading } from "../lib/actionReading";
import { useStore, type RunStep } from "../store";
import { isDockerCleanup, type CleanupRunner } from "../hooks/useCleanupRunner";
import type { Setting } from "../types/setting";

/**
 * The one card for an action setting: a cleanup, a game-cache purge, a repair.
 *
 * Before this existed an action had two places on screen at once. Pressing Run
 * opened a separate "running" panel that listed a *copy* of every selected
 * action, while the originals stayed in the list below — so a single cleanup
 * appeared twice, its size in one place and its progress in another, and the
 * user had to match them up by name. Everything an action can say now says it
 * here: what it can reclaim, what it is doing, and what it did.
 *
 * Two rules carry over from the panel this replaces, both C11. A percentage bar
 * appears only for a command that printed a percentage — a command that prints
 * none shows the seconds it has been running, which is a different measurement
 * rather than an invented one. And the freed figure is whatever the backend
 * measured (before − after, in bytes), never a claim from the registry.
 */
export function ActionRow({
  setting,
  runner,
  selectable = false,
  accent = "primary",
}: {
  setting: Setting;
  runner: CleanupRunner;
  /** Render the shared maintenance-selection checkbox, for the bulk Run. */
  selectable?: boolean;
  /** `warning` marks the repair actions, which are not cleanups. */
  accent?: "primary" | "warning";
}) {
  const { t } = useT();
  const result = useStore((s) => s.cleanupResults[setting.id]);
  const step = useStore((s) => s.runSteps.find((r) => r.id === setting.id));
  const selected = useStore(
    (s) => s.maintenanceSelection[setting.id] ?? false,
  );
  const toggleSelection = useStore((s) => s.toggleMaintenanceSelection);

  const name = localizedName(setting);
  const reading = parseActionReading(setting.currentValue);
  const isRepair = accent === "warning";
  const RunIcon = isRepair ? Wrench : Trash2;

  return (
    <div
      className={cn(
        "flex items-start gap-3 p-3 rounded-md border transition-colors",
        selected
          ? isRepair
            ? "border-warning bg-warning/5"
            : "border-primary bg-primary/5"
          : "border-border hover:border-muted-foreground/50",
      )}
    >
      {selectable && (
        <input
          type="checkbox"
          checked={selected}
          onChange={() => toggleSelection(setting.id)}
          aria-label={name}
          className={cn(
            "mt-1 h-4 w-4 rounded border-border",
            isRepair ? "text-warning" : "text-primary",
          )}
        />
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm wrap-break-word min-w-0">
            {name}
          </span>
          <ReadingBadge reading={reading} />
          {setting.durationEstimate && (
            <span className="text-xs text-muted-foreground">
              ({setting.durationEstimate})
            </span>
          )}
        </div>

        <p className="text-sm text-muted-foreground mt-1">
          {localizedDescription(setting)}
        </p>

        {setting.name === "dism_cleanup" && (
          <Warning>{t("cleanup.dismWarning")}</Warning>
        )}
        {/* Docker prune compacts the WSL2 vhdx so space truly returns — which
            restarts Docker and every WSL distro. */}
        {isDockerCleanup(setting) && (
          <Warning>{t("cleanup.dockerShutdownWarning")}</Warning>
        )}
        {setting.name === "wsl_compact" && (
          <Warning>{t("cleanup.wslWarning")}</Warning>
        )}
        {/* A precondition, not a restatement: the repair may need to download. */}
        {setting.name === "dism_health" && (
          <Warning>{t("maintenance.dismHealthWarning")}</Warning>
        )}

        {/* What running this does, present-tense. Suppressed for the repairs:
            for SFC and DISM "what it does" and "what running it does" are the
            same sentence, so the effect line printed the description twice. */}
        {!isRepair && setting.effect && (
          <div className="flex items-start gap-1.5 mt-2 text-xs text-muted-foreground">
            <Info className="w-3.5 h-3.5 mt-0.5 shrink-0" aria-hidden="true" />
            <span>{setting.effect}</span>
          </div>
        )}

        {/* A step that has finished and reported its outcome has nothing left
            to say that the outcome line below does not say better; while it is
            queued, running, failed or skipped, this is the only account of it
            there is. */}
        {step && (step.status !== "done" || !result) && (
          <ActionProgress step={step} />
        )}

        {result && (
          <div className="mt-1.5">
            <Outcome
              success={result.success}
              sized={result.sized}
              freedMB={result.freedMB}
              error={result.error}
            />
          </div>
        )}
      </div>

      <Button
        className="shrink-0"
        variant={isRepair ? "warning" : "primary"}
        busy={runner.isRunning}
        icon={<RunIcon className="w-3.5 h-3.5" aria-hidden="true" />}
        onClick={() => runner.run([setting.id])}
      >
        {t("action.run")}
      </Button>
    </div>
  );
}

/** A one-line caution the user should read before pressing Run. */
function Warning({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-1.5 mt-2 text-xs text-warning">
      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}

/**
 * What this action's last detection read, as the kind of thing it read.
 *
 * A cleanup reports a reclaimable size, the SSD retrim reports how long its
 * upkeep has been overdue, and the two are not interchangeable: every reading
 * used to go through the size parser, so `overdue|never` put the word "never"
 * in a badge with a hard-drive icon. An action that reports nothing readable —
 * a repair, or a payload this build cannot account for — gets no badge at all
 * rather than a figure that would read as a measurement.
 */
function ReadingBadge({ reading }: { reading: ActionReading | null }) {
  const { t } = useT();
  if (reading === null) return null;
  if (reading.kind === "overdue") {
    return (
      <span className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-warning/10 text-warning font-medium">
        <AlertTriangle className="w-3 h-3" aria-hidden="true" />
        {reading.detail === "never"
          ? t("cleanup.trimOverdueNever")
          : t("cleanup.trimOverdueDays", { days: reading.detail.days })}
      </span>
    );
  }
  if (reading.kind === "ok") {
    // Muted: upkeep that is current is context for the row, not a call to act.
    return (
      <span className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
        <CheckCircle2 className="w-3 h-3" aria-hidden="true" />
        {reading.days === 0
          ? t("cleanup.trimLastUnderDay")
          : t("cleanup.trimLastDays", { days: reading.days })}
      </span>
    );
  }
  const size = reading.size;
  if (size === "calculating") {
    return (
      <span className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
        <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />
        {t("cleanup.calculating")}
      </span>
    );
  }
  if (size === "unavailable") {
    return (
      <span
        title={t("cleanup.serviceDown")}
        className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-warning/10 text-warning"
      >
        <AlertTriangle className="w-3 h-3" aria-hidden="true" />
        {t("cleanup.unavailable")}
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">
      <HardDrive className="w-3 h-3" aria-hidden="true" />
      {size}
    </span>
  );
}

/** What the last run of this action did, in the row that ran it. */
function Outcome({
  success,
  sized,
  freedMB,
  error,
}: {
  success: boolean;
  sized: boolean;
  freedMB: number | null;
  error?: string;
}) {
  const { t } = useT();
  if (!success) {
    return (
      <div className="flex items-start gap-1.5 text-xs text-destructive">
        <XCircle className="w-3 h-3 mt-0.5 shrink-0" aria-hidden="true" />
        <span className="wrap-break-word">
          {t("cleanup.failed")}
          {error ? `: ${error}` : ""}
        </span>
      </div>
    );
  }
  // Succeeded but nothing measured a byte count — a repair, or a cleanup whose
  // new size never came back. It says what it knows and no more (C11 rule 3).
  if (!sized || freedMB === null) {
    return (
      <span className="flex items-center gap-1 text-xs text-success">
        <CheckCircle2 className="w-3 h-3" aria-hidden="true" />
        {t("cleanup.done")}
      </span>
    );
  }
  return (
    <span className="text-xs text-primary font-medium">
      {t("cleanup.freed", { amount: fmtMB(freedMB) })}
    </span>
  );
}

const STATUS_ICON = {
  queued: () => (
    <MinusCircle
      className="w-3.5 h-3.5 text-muted-foreground/50 shrink-0"
      aria-hidden="true"
    />
  ),
  running: () => (
    <Loader2
      className="w-3.5 h-3.5 animate-spin text-primary shrink-0"
      aria-hidden="true"
    />
  ),
  done: () => (
    <CheckCircle2 className="w-3.5 h-3.5 text-success shrink-0" aria-hidden="true" />
  ),
  skipped: () => (
    <MinusCircle
      className="w-3.5 h-3.5 text-muted-foreground shrink-0"
      aria-hidden="true"
    />
  ),
  failed: () => (
    <XCircle className="w-3.5 h-3.5 text-destructive shrink-0" aria-hidden="true" />
  ),
} as const;

/**
 * The live account of this action, in the row that started it.
 *
 * A DISM repair runs for half an hour, and without this it is one spinner —
 * indistinguishable from a wedged one. Four things make the difference: the
 * command verbatim, how far it has got, the newest line it printed, and the
 * seconds it has been going.
 */
function ActionProgress({ step }: { step: RunStep }) {
  const { t } = useT();
  const [showOutput, setShowOutput] = useState(false);
  const elapsed = useElapsed(step);

  const Icon = STATUS_ICON[step.status];
  const isRunning = step.status === "running";
  // The latest line is the stage the command is at; the ones before it are the
  // log. A redrawn progress bar is one line, so this is genuinely the newest
  // thing the command said rather than the newest redraw of an old one.
  const latest = step.lines.length > 0 ? step.lines[step.lines.length - 1] : "";

  return (
    <div className="mt-2 space-y-1.5">
      <div className="flex items-center gap-2 text-xs tabular-nums">
        <Icon />
        <StepState step={step} elapsed={elapsed} />
      </div>

      {(isRunning || step.status === "failed") && (
        <div className="space-y-1.5 pl-5">
          {step.command && (
            // The command verbatim. Not a paraphrase: this is the record of
            // what fpstune ran on the machine, and it is the reason the row
            // above it can be trusted.
            <p
              className="text-xs font-mono text-muted-foreground/80 wrap-break-word"
              title={t("run.commandLabel")}
            >
              {step.command}
            </p>
          )}
          {isRunning && step.percent !== null && (
            <Progress
              value={step.percent}
              label={t("run.stepProgress", { name: step.name })}
            />
          )}
          {isRunning && latest && (
            <p className="text-xs text-muted-foreground wrap-break-word">
              {latest}
            </p>
          )}
          {step.error && (
            <p className="text-xs text-destructive wrap-break-word">
              {step.error}
            </p>
          )}
          {step.lines.length > 0 && (
            <button
              type="button"
              onClick={() => setShowOutput((open) => !open)}
              aria-expanded={showOutput}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {showOutput ? (
                <ChevronDown className="w-3 h-3" aria-hidden="true" />
              ) : (
                <ChevronRight className="w-3 h-3" aria-hidden="true" />
              )}
              {showOutput ? t("run.hideOutput") : t("run.showOutput")}
            </button>
          )}
          {showOutput && (
            // Complete, but folded: everything the command printed is here for
            // the user who wants it, without a wall of it for the user who does
            // not. Newest last, the way a terminal reads.
            <pre className="max-h-40 overflow-auto rounded bg-muted/60 p-2 text-xs font-mono whitespace-pre-wrap wrap-break-word">
              {step.lines.join("\n") || t("run.noOutputYet")}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/** Where this step is, in one short phrase. */
function StepState({ step, elapsed }: { step: RunStep; elapsed: number }) {
  const { t } = useT();
  if (step.status === "queued")
    return <span className="text-muted-foreground/60">{t("run.queued")}</span>;
  if (step.status === "skipped")
    return <span className="text-muted-foreground">{t("run.skipped")}</span>;
  if (step.status === "failed")
    return <span className="text-destructive">{t("cleanup.failed")}</span>;
  if (step.status === "done")
    return <span className="text-success">{t("cleanup.done")}</span>;
  // A percentage when the command prints one; otherwise the seconds it has been
  // running, which is a measurement too — just a different one.
  return step.percent !== null ? (
    <span className="text-primary">
      {t("run.percent", { value: Math.round(step.percent) })}
    </span>
  ) : (
    <span className="text-muted-foreground">
      {t("run.elapsed", { seconds: elapsed })}
    </span>
  );
}

/**
 * Seconds this step has been running, ticking while it runs.
 *
 * The tick exists because it is the only thing moving during a command that
 * prints nothing for minutes: without it, "no output yet" and "hung" look
 * identical, which is the complaint this whole row answers.
 */
function useElapsed(step: RunStep): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (step.status !== "running") return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [step.status]);

  if (!step.startedAt) return 0;
  const end = step.endedAt ?? now;
  return Math.max(0, Math.round((end - step.startedAt) / 1000));
}

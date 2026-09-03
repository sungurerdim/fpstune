import { useEffect, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Loader2,
  MinusCircle,
  Terminal,
  XCircle,
} from "lucide-react";
import { useT } from "../i18n";
import { Card } from "./ui/Card";
import { Progress } from "./ui/Feedback";
import { cn } from "../lib/utils";
import { fmtMB } from "../lib/cleanupSize";
import { useStore, type RunStep } from "../store";

/**
 * What the app is doing right now, one row per action, in run order.
 *
 * This replaces a spinner that said nothing for up to half an hour: a DISM
 * repair ran with no name, no command, no progress and no way to tell it from a
 * wedged one. A row here carries all four — and the queue behind it, and the
 * outcome in front of it, which a raw console pane could not.
 *
 * Two rules keep it honest. A percentage bar appears only for a command that
 * prints a percentage (C11: no number an instrument did not produce), and the
 * freed figure is read from `cleanupResults` — the one place a before/after
 * difference is computed — rather than copied into a second place to drift.
 */
export function RunPanel() {
  const { t } = useT();
  const steps = useStore((s) => s.runSteps);

  if (steps.length === 0) return null;

  const finished = steps.filter(
    (s) => s.status === "done" || s.status === "failed" || s.status === "skipped",
  ).length;
  const active = steps.some((s) => s.status === "running");

  return (
    <Card>
      <div className="flex items-center gap-2 p-3 border-b border-border">
        <Terminal className="w-4 h-4 text-primary shrink-0" aria-hidden="true" />
        <h3 className="font-semibold text-sm">{t("run.title")}</h3>
        {/* A count, not a guess: how many of the selected actions have finished.
            This is the one aggregate progress the app can state as a fact. */}
        <span className="ml-auto text-xs text-muted-foreground tabular-nums">
          {t("run.progress", { done: finished, total: steps.length })}
        </span>
        {active && (
          <Loader2
            className="w-3.5 h-3.5 animate-spin text-primary"
            aria-hidden="true"
          />
        )}
      </div>
      <div className="divide-y divide-border/60">
        {steps.map((step) => (
          <StepRow key={step.id} step={step} />
        ))}
      </div>
    </Card>
  );
}

const STATUS_ICON = {
  queued: () => (
    <MinusCircle
      className="w-3.5 h-3.5 text-muted-foreground/50"
      aria-hidden="true"
    />
  ),
  running: () => (
    <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" aria-hidden="true" />
  ),
  done: () => (
    <CheckCircle2 className="w-3.5 h-3.5 text-success" aria-hidden="true" />
  ),
  skipped: () => (
    <MinusCircle className="w-3.5 h-3.5 text-muted-foreground" aria-hidden="true" />
  ),
  failed: () => <XCircle className="w-3.5 h-3.5 text-destructive" aria-hidden="true" />,
} as const;

function StepRow({ step }: { step: RunStep }) {
  const { t } = useT();
  const [showOutput, setShowOutput] = useState(false);
  const result = useStore((s) => s.cleanupResults[step.id]);
  const elapsed = useElapsed(step);

  const Icon = STATUS_ICON[step.status];
  const isRunning = step.status === "running";
  // The latest line is the stage the command is at; the ones before it are the
  // log. A redrawn progress bar is one line, so this is genuinely the newest
  // thing the command said rather than the newest redraw of an old one.
  const latest = step.lines.length > 0 ? step.lines[step.lines.length - 1] : "";

  return (
    <div className="px-3 py-2">
      <div className="flex items-center gap-2 min-w-0">
        <Icon />
        <span
          className={cn(
            "text-sm truncate",
            step.status === "queued" && "text-muted-foreground",
          )}
        >
          {step.name}
        </span>
        {step.durationEstimate && isRunning && (
          <span className="text-xs text-muted-foreground shrink-0">
            ({step.durationEstimate})
          </span>
        )}
        <span className="ml-auto shrink-0 text-xs tabular-nums whitespace-nowrap">
          <StepRight step={step} elapsed={elapsed} />
        </span>
      </div>

      {(isRunning || step.status === "failed") && (
        <div className="mt-1.5 pl-5 space-y-1.5">
          {step.command && (
            // The command verbatim. Not a paraphrase: this is the record of what
            // fpstune ran on the machine, and it is the reason the user can
            // trust the row above it.
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
            <p className="text-xs text-muted-foreground wrap-break-word">{latest}</p>
          )}
          {step.error && (
            <p className="text-xs text-destructive wrap-break-word">{step.error}</p>
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

      {result?.sized && result.freedMB !== null && (
        <p className="mt-0.5 pl-5 text-xs text-primary font-medium">
          {t("cleanup.freed", { amount: fmtMB(result.freedMB) })}
        </p>
      )}
    </div>
  );
}

/** The right-hand column: what this step is, in one short phrase. */
function StepRight({ step, elapsed }: { step: RunStep; elapsed: number }) {
  const { t } = useT();
  if (step.status === "queued")
    return <span className="text-muted-foreground/60">{t("run.queued")}</span>;
  if (step.status === "skipped")
    return <span className="text-muted-foreground">{t("run.skipped")}</span>;
  if (step.status === "failed")
    return <span className="text-destructive">{t("cleanup.failed")}</span>;
  if (step.status === "running") {
    // A percentage when the command prints one; otherwise the seconds it has
    // been running, which is a measurement too — just a different one.
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
  return <span className="text-success">{t("cleanup.done")}</span>;
}

/**
 * Seconds this step has been running, ticking while it runs.
 *
 * The tick exists because it is the only thing moving during a command that
 * prints nothing for minutes: without it, "no output yet" and "hung" look
 * identical, which is the complaint this whole panel answers.
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

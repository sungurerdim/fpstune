import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, ArrowRight, Gauge, Loader2, Play } from "lucide-react";
import { useT } from "../i18n";
import { cn } from "../lib/utils";
import { formatAge } from "../lib/formatAge";
import {
  benchmarkApi,
  type BenchLedger,
  type LedgerArea,
  type LedgerRunSummary,
} from "../lib/api";
import {
  benchLabel,
  formatDelta,
  formatReading,
  jobStep,
  verdictOf,
  type AreaVerdict,
} from "../lib/ledger";
import { LEDGER_QUERY_KEY, useBenchLedger } from "../hooks/useBenchLedger";
import { Button } from "./ui/Button";
import { Card, CardHeader } from "./ui/Card";

/**
 * Did any of that help — answered per area, by one instrument each.
 *
 * The screen fpstune has got wrong three times is this one, and each time the
 * mistake was the same shape: a single headline number produced by adding
 * things up. `"GAINED -683ms LATENCY"` summed four unrelated clocks;
 * `"Gained +28-45% FPS"` summed claims nobody had measured. So there is no
 * total here, no overall figure, and no arithmetic between two rows — one row
 * per area, each carrying the reading its own instrument took (C11 rule 1).
 *
 * The other half is the honest half. An area with no pair renders the ledger's
 * own sentence saying why, never a zero and never "no change" (rule 3) — and on
 * this build two areas say that permanently, because a frame rate needs a game
 * rendering and nothing here samples temperature around a bench.
 *
 * Both surfaces read the same query. Home gets the tiles, the Benchmarks tab
 * gets the full table with the runs behind it and the button that asks for a
 * new one; neither keeps a copy, so they cannot drift apart.
 */

/** How a verdict is coloured. Never a colour the server did not justify. */
const TONE: Record<AreaVerdict, string> = {
  improved: "text-success",
  worse: "text-destructive",
  // Past the noise floor, but which way is up is the server's judgement and it
  // did not say — so the size is shown and no winner is named.
  changed: "text-foreground",
  within_noise: "text-muted-foreground",
  unmeasured: "text-muted-foreground",
};

const VERDICT_LABEL = {
  improved: "ledger.improved",
  worse: "ledger.worse",
  changed: "ledger.changed",
} as const;

/** The machine's own variation for this metric, or that it is not known. */
function useNoiseText(area: LedgerArea): string {
  const { t } = useT();
  return area.noise === null
    ? t("ledger.noiseUnknown")
    : t("ledger.noise", { noise: area.noise.toFixed(2), unit: area.unit });
}

function VerdictText({ area }: { area: LedgerArea }) {
  const { t } = useT();
  const verdict = verdictOf(area);
  const noiseText = useNoiseText(area);

  if (verdict === "unmeasured") return null;

  if (verdict === "within_noise") {
    return (
      <span className="text-muted-foreground">
        {area.noise === null
          ? `${t("ledger.withinNoiseShort")} — ${noiseText}`
          : t("ledger.withinNoise", {
              noise: area.noise.toFixed(2),
              unit: area.unit,
            })}
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1.5 flex-wrap">
      <span className={cn("font-medium", TONE[verdict])}>
        {t(VERDICT_LABEL[verdict])}
      </span>
      {area.percent_change !== null && (
        <span className="tabular-nums">
          {area.percent_change > 0 ? "+" : ""}
          {area.percent_change.toFixed(1)}%
        </span>
      )}
      <span className="text-muted-foreground">{noiseText}</span>
    </span>
  );
}

/** How many readings each side got, when the ledger says. Never invented. */
function SampleCount({ area }: { area: LedgerArea }) {
  const { t } = useT();
  if (
    area.samples_before === null ||
    area.samples_before === undefined ||
    area.samples_after === null ||
    area.samples_after === undefined
  ) {
    return null;
  }
  return (
    <span className="text-xs text-muted-foreground">
      {t("ledger.samples", {
        before: area.samples_before,
        after: area.samples_after,
      })}
    </span>
  );
}

/** One area as a tile: what moved, by how much, or why nothing is known. */
function AreaTile({ area }: { area: LedgerArea }) {
  const verdict = verdictOf(area);

  return (
    <div
      data-testid={`measured-area-${area.area}`}
      className="p-3 rounded-md border border-border"
    >
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-medium text-sm">{area.label}</span>
        <span className="text-xs text-muted-foreground font-mono">
          {area.instrument}
        </span>
      </div>

      {verdict === "unmeasured" ? (
        // The reason, and nothing else. A zero here would read as a measurement.
        <p className="text-xs text-muted-foreground mt-1">{area.reason}</p>
      ) : (
        <>
          <div className="mt-1 text-sm flex items-center gap-1.5 flex-wrap tabular-nums">
            <span>{formatReading(area.before, area.unit)}</span>
            <ArrowRight
              className="w-3 h-3 text-muted-foreground"
              aria-hidden="true"
            />
            <span>{formatReading(area.after, area.unit)}</span>
            <span className={cn("font-medium", TONE[verdict])}>
              {formatDelta(area.delta, area.unit)}
            </span>
          </div>
          <div className="text-xs mt-1">
            <VerdictText area={area} />
          </div>
          <SampleCount area={area} />
        </>
      )}
    </div>
  );
}

/**
 * What the background scheduler is doing, in one line.
 *
 * A job that is queued rather than running is waiting on a guard — an idle
 * machine, a game that is still open — and saying so is the difference between
 * a product that looks stuck and one that is waiting on purpose.
 */
function JobStatusLine({ ledger }: { ledger: BenchLedger }) {
  const { t } = useT();
  const job = ledger.job;

  if (job && (job.status === "running" || job.status === "queued" || job.status === "failed")) {
    const what = t(
      job.trigger === "baseline"
        ? "ledger.triggerBaseline"
        : job.trigger === "after"
          ? "ledger.triggerAfter"
          : "ledger.triggerManual",
    );
    const { step, total } = jobStep(job);
    const text =
      job.status === "running"
        ? t("ledger.jobRunning", {
            what,
            step,
            total,
            bench: benchLabel(ledger.areas, job.current_bench),
          })
        : job.status === "queued"
          ? t("ledger.jobQueued", { what })
          : t("ledger.jobFailed", { what });

    return (
      <p
        data-testid="ledger-job-status"
        className="text-xs text-muted-foreground flex items-center gap-2"
      >
        {job.status === "running" && (
          <Loader2
            className="w-3.5 h-3.5 animate-spin text-primary"
            aria-hidden="true"
          />
        )}
        {text}
      </p>
    );
  }

  return (
    <p
      data-testid="ledger-job-status"
      className="text-xs text-muted-foreground"
    >
      {ledger.bulk_apply_pending ? t("ledger.bulkPending") : t("ledger.jobIdle")}
    </p>
  );
}

/** Loading and unreachable, said rather than rendered as an empty panel. */
function LedgerNotice({ text }: { text: string }) {
  return <p className="text-sm text-muted-foreground">{text}</p>;
}

/**
 * Home's card: the measured counterpart to the claims above it.
 *
 * It is rendered even when nothing has been measured, because seven rows each
 * saying what they are waiting for is a plan, and an absent card is a promise
 * nobody made.
 */
export function HomeMeasuredCard() {
  const { t } = useT();
  const { data, isLoading, isError } = useBenchLedger();

  return (
    <Card data-testid="home-measured">
      <CardHeader
        icon={<Gauge className="w-4 h-4 text-primary" aria-hidden="true" />}
        title={t("ledger.homeTitle")}
      >
        <span className="text-xs text-muted-foreground hidden sm:inline">
          {t("ledger.homeHint")}
        </span>
      </CardHeader>

      <div className="p-3 space-y-2">
        {isLoading && <LedgerNotice text={t("ledger.loading")} />}
        {isError && <LedgerNotice text={t("ledger.unreachable")} />}
        {data && (
          <>
            <JobStatusLine ledger={data} />
            <div
              data-testid="home-measured-grid"
              className="grid grid-cols-1 gap-2 items-start lg:grid-cols-2 2xl:grid-cols-3"
            >
              {data.areas.map((area) => (
                <AreaTile key={area.area} area={area} />
              ))}
            </div>
            {data.areas.length === 0 && (
              <LedgerNotice text={t("ledger.noAreas")} />
            )}
          </>
        )}
      </div>
    </Card>
  );
}

/** One stored run, in its own words, with how long ago it was taken. */
function RunLine({
  labelKey,
  run,
}: {
  labelKey: "ledger.baselineRun" | "ledger.afterRun";
  run: LedgerRunSummary;
}) {
  const { t } = useT();
  return (
    <p className="text-xs text-muted-foreground">
      {t(labelKey, {
        summary: run.summary,
        age: formatAge(run.started_at),
      })}
    </p>
  );
}

/**
 * The Benchmarks tab's full table, and the one button that asks for a run.
 *
 * The button queues rather than measures. The suite takes minutes and the
 * guards that decide when it may run — an idle machine, no game open — live in
 * the scheduler; a button that ran the benches directly would be a second
 * measurement pipeline, which is how two screens come to disagree.
 */
export function LedgerPanel() {
  const { t } = useT();
  const { data, isLoading, isError } = useBenchLedger();
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState("");

  const queue = useMutation({
    mutationFn: benchmarkApi.runLedgerJob,
    onSuccess: (result) => {
      setNotice(result.queued ? t("ledger.queued") : t("ledger.alreadyRunning"));
      void queryClient.invalidateQueries({ queryKey: LEDGER_QUERY_KEY });
    },
    onError: () => setNotice(t("ledger.queueFailed")),
  });

  return (
    <Card className="p-4 space-y-3" data-testid="ledger-panel">
      <div className="flex items-start gap-3 flex-wrap">
        <div className="flex-1 min-w-[16rem]">
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Activity className="w-4 h-4" aria-hidden="true" />
            {t("ledger.panelTitle")}
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            {t("ledger.panelHint")}
          </p>
        </div>
        <div className="space-y-1">
          <Button
            size="md"
            busy={queue.isPending}
            icon={<Play className="w-4 h-4" aria-hidden="true" />}
            onClick={() => queue.mutate()}
          >
            {t("ledger.measureNow")}
          </Button>
          <p className="text-xs text-muted-foreground max-w-xs">
            {t("ledger.measureNowHint")}
          </p>
          {notice && <p className="text-xs text-muted-foreground">{notice}</p>}
        </div>
      </div>

      {isLoading && <LedgerNotice text={t("ledger.loading")} />}
      {isError && <LedgerNotice text={t("ledger.unreachable")} />}

      {data && (
        <>
          <JobStatusLine ledger={data} />

          {data.baseline || data.after ? (
            <div className="space-y-0.5">
              {data.baseline && (
                <RunLine labelKey="ledger.baselineRun" run={data.baseline} />
              )}
              {data.after && (
                <RunLine labelKey="ledger.afterRun" run={data.after} />
              )}
            </div>
          ) : (
            <LedgerNotice text={t("ledger.noRunYet")} />
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="ledger-area-table">
              <thead>
                <tr className="text-xs text-muted-foreground text-left">
                  <th className="py-1 pr-3">{t("ledger.area")}</th>
                  <th className="py-1 pr-3">{t("ledger.instrument")}</th>
                  <th className="py-1 pr-3 text-right">{t("ledger.before")}</th>
                  <th className="py-1 pr-3 text-right">{t("ledger.after")}</th>
                  <th className="py-1 pr-3 text-right">{t("ledger.change")}</th>
                  <th className="py-1">{t("ledger.verdict")}</th>
                </tr>
              </thead>
              <tbody>
                {data.areas.map((area) => {
                  const verdict = verdictOf(area);
                  return (
                    <tr
                      key={area.area}
                      data-testid={`ledger-row-${area.area}`}
                      className="border-t border-border/50 align-top"
                    >
                      <td className="py-1.5 pr-3">{area.label}</td>
                      <td className="py-1.5 pr-3 font-mono text-xs text-muted-foreground">
                        {area.instrument}
                      </td>
                      {verdict === "unmeasured" ? (
                        // Four columns of numbers replaced by the one sentence
                        // that says why there are none.
                        <td
                          className="py-1.5 text-xs text-muted-foreground"
                          colSpan={4}
                        >
                          {area.reason}
                        </td>
                      ) : (
                        <>
                          <td className="py-1.5 pr-3 text-right tabular-nums">
                            {formatReading(area.before, area.unit)}
                          </td>
                          <td className="py-1.5 pr-3 text-right tabular-nums">
                            {formatReading(area.after, area.unit)}
                          </td>
                          <td
                            className={cn(
                              "py-1.5 pr-3 text-right tabular-nums",
                              TONE[verdict],
                            )}
                          >
                            {formatDelta(area.delta, area.unit)}
                          </td>
                          <td className="py-1.5 text-xs">
                            <VerdictText area={area} />
                            <SampleCount area={area} />
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  );
}

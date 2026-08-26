import { useT } from "../i18n";
import type { MessageKey } from "../i18n/en";
import { Button } from "./ui/Button";
import { Card } from "./ui/Card";
import { Meter } from "./ui/Feedback";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Play,
  RotateCcw,
} from "lucide-react";
import {
  suiteApi,
  type SuiteBench,
  type SuiteCatalogue,
  type SuiteComparison,
  type SuiteMeasurement,
  type SuiteRun,
} from "../lib/api";
import { createLogger } from "../lib/logger";
import { useStore } from "../store";

const log = createLogger("suite");

/**
 * One button: measure this machine, change something, press it again.
 *
 * This panel used to ask for three decisions before it would do anything —
 * which of five instruments to tick, how many repeats, and then *which* of three
 * buttons ("measure as before", "measure as after", "compare") applied right
 * now. Every one of those has a right answer almost every time, and the user's
 * report was that the screen was unreadable because of it: "there is a lot here,
 * what we need is to measure everything including before/after with one press".
 *
 * So the decisions have defaults and the button knows what it is for. Before any
 * measurement it takes a baseline; after one it measures again and compares
 * without being asked, because a second measurement has no other purpose. The
 * instrument list and the repeat count are still there, behind a fold, for the
 * times the answer is not the default one.
 *
 * What did not change is what the comparison says. Both runs live in the
 * browser, and a difference smaller than the machine's own variation still reads
 * as "within noise" rather than as a small win — on an idle machine the small
 * win is free and always available.
 */

type Phase = "idle" | "running";

interface RunState {
  run: SuiteRun | null;
  /** Which bench is being measured right now, for the progress line. */
  active: string;
  progress: number;
}

const EMPTY: RunState = { run: null, active: "", progress: 0 };

export function SuitePanel() {
  const { t } = useT();
  const [catalogue, setCatalogue] = useState<SuiteCatalogue | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [repeats, setRepeats] = useState(3);
  const [phase, setPhase] = useState<Phase>("idle");
  const [target, setTarget] = useState<"before" | "after">("before");
  const [before, setBefore] = useState<RunState>(EMPTY);
  const [after, setAfter] = useState<RunState>(EMPTY);
  const [comparison, setComparison] = useState<SuiteComparison | null>(null);
  const [failure, setFailure] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  // Published so Verify can judge the settings' claims against this same pair,
  // rather than asking the user to measure the machine a second time.
  const setSuiteRun = useStore((state) => state.setSuiteRun);
  const cancelRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let live = true;
    suiteApi
      .catalogue()
      .then((data) => {
        if (!live) return;
        setCatalogue(data);
        setRepeats(data.default_repeats);
        setSelected(new Set(data.default_keys));
      })
      .catch((err) => log.error("suite catalogue failed", err));
    return () => {
      live = false;
      cancelRef.current?.();
    };
  }, []);

  const toggle = (key: string) =>
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const compareRuns = useCallback(
    async (first: SuiteRun, second: SuiteRun) => {
      try {
        setComparison(await suiteApi.compare(first, second));
        setFailure("");
      } catch (err) {
        log.error("suite compare failed", err);
        setFailure("the two runs could not be compared");
      }
    },
    [],
  );

  const start = useCallback(
    (label: "before" | "after") => {
      if (phase === "running" || selected.size === 0) return;

      const setRun = label === "before" ? setBefore : setAfter;
      setRun({ run: null, active: "", progress: 0 });
      setComparison(null);
      setFailure("");
      setTarget(label);
      setPhase("running");

      cancelRef.current = suiteApi.run(
        { benches: [...selected], label, repeats },
        (event) => {
          const kind = event.event as string;
          if (kind === "running") {
            setRun((current) => ({ ...current, active: String(event.label ?? event.bench) }));
          } else if (kind === "measured" || kind === "skipped") {
            setRun((current) => ({ ...current, progress: Number(event.progress ?? 0) }));
          } else if (kind === "failed") {
            setFailure(String(event.reason ?? "the run could not start"));
          } else if (kind === "done") {
            const finished = event.run as SuiteRun;
            setRun({ run: finished, active: "", progress: 100 });
            setSuiteRun(label, finished);
            // The second run has no other purpose than to be compared against
            // the first, so asking for one more press to say so was a step that
            // could only ever be answered one way.
            if (label === "after" && before.run) void compareRuns(before.run, finished);
          }
        },
        () => setPhase("idle"),
      );
    },
    [before.run, compareRuns, phase, repeats, selected, setSuiteRun],
  );

  const reset = useCallback(() => {
    cancelRef.current?.();
    setBefore(EMPTY);
    setAfter(EMPTY);
    setComparison(null);
    setFailure("");
    setPhase("idle");
    setSuiteRun("before", null);
    setSuiteRun("after", null);
  }, [setSuiteRun]);

  if (!catalogue) {
    return (
      <Card className="p-4 text-sm text-muted-foreground">
        {t("suite.loading")}
      </Card>
    );
  }

  const running = phase === "running";
  const hasBaseline = before.run !== null;
  const primaryLabel = hasBaseline
    ? t("suite.measureAgain")
    : t("suite.measureThis");

  return (
    <div className="space-y-4">
      <Card className="p-4 space-y-4">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Activity className="w-4 h-4" />
            {t("suite.title")}
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            {hasBaseline ? t("suite.baselineTaken") : t("suite.takesBaseline")}
          </p>
        </div>

        <div className="flex gap-2 flex-wrap items-center">
          <Button
            size="md"
            busy={running}
            disabled={selected.size === 0}
            icon={<Play className="w-4 h-4" />}
            onClick={() => start(hasBaseline ? "after" : "before")}
          >
            {running ? `Measuring the ${target} run…` : primaryLabel}
          </Button>

          {(hasBaseline || running) && (
            <button
              onClick={reset}
              className="flex items-center gap-2 px-3 py-2 rounded-md text-sm bg-muted hover:bg-muted/80"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              {t("suite.startOver")}
            </button>
          )}

          {/* A count rather than a list: the list is one fold away, and the
              number is what tells you the button will do something. */}
          <span className="text-xs text-muted-foreground">
            {t("suite.selectionSummary", {
              selected: selected.size,
              total: catalogue.benches.length,
              repeats,
            })}
          </span>
        </div>

        {running && (
          <Progress state={target === "before" ? before : after} label={target} />
        )}

        {failure && (
          <p className="text-xs text-destructive flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5" />
            {failure}
          </p>
        )}

        {(before.run || after.run) && (
          <div className="grid sm:grid-cols-2 gap-3">
            <RunSummary title={t("suite.before")} state={before} />
            <RunSummary title={t("suite.after")} state={after} />
          </div>
        )}

        <div className="border-t border-border pt-3">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            {showAdvanced ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )}
            {t("suite.whichInstruments")}
          </button>

          {showAdvanced && (
            <div className="mt-3 space-y-3">
              <div className="space-y-2">
                {catalogue.benches.map((bench) => (
                  <BenchRow
                    key={bench.key}
                    bench={bench}
                    checked={selected.has(bench.key)}
                    disabled={running}
                    onToggle={() => toggle(bench.key)}
                  />
                ))}
              </div>

              <div className="flex items-center gap-3 flex-wrap">
                <label className="text-xs text-muted-foreground flex items-center gap-2">
                  Repeats
                  <input
                    type="number"
                    min={catalogue.min_repeats}
                    max={catalogue.max_repeats}
                    value={repeats}
                    disabled={running}
                    onChange={(e) => setRepeats(Number(e.target.value))}
                    className="w-16 bg-muted rounded px-2 py-1 text-foreground"
                  />
                </label>
                {/* Stated rather than left to be discovered: below two there is no
                    spread to compare against, so nothing can be called a change. */}
                <span className="text-xs text-muted-foreground">
                  {t("suite.minRepeats", { min: catalogue.min_repeats })}
                </span>
              </div>
            </div>
          )}
        </div>
      </Card>

      {comparison && <ComparisonTable comparison={comparison} />}
    </div>
  );
}

function BenchRow({
  bench,
  checked,
  disabled,
  onToggle,
}: {
  bench: SuiteBench;
  checked: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  const { t } = useT();
  return (
    <label
      className={`flex items-start gap-3 text-sm rounded-md px-2 py-1.5 ${
        bench.available ? "hover:bg-muted/50" : "opacity-60"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled || !bench.available}
        onChange={onToggle}
        className="mt-1"
      />
      <span className="flex-1">
        <span className="font-medium">{bench.label}</span>
        {/* The cost is on the row rather than in a confirmation dialog: a user
            deciding whether to tick a box should know what ticking it spends
            before they tick it, not after. */}
        {bench.costs && (
          <span className="ml-2 text-xs text-amber-500">{bench.costs}</span>
        )}
        {!bench.in_default_run && (
          <span className="ml-2 text-xs text-muted-foreground">{t("suite.notInRunAll")}</span>
        )}
        <span className="block text-xs text-muted-foreground">
          {/* "Cannot run, and here is what to arrange" — never a silent absence. */}
          {bench.available ? bench.requires : bench.reason}
        </span>
      </span>
    </label>
  );
}

function Progress({ state, label }: { state: RunState; label: string }) {
  const { t } = useT();
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>
          {state.active
            ? t("suite.measuringBench", { bench: state.active })
            : t("suite.startingRun", { label })}
        </span>
        <span>{state.progress}%</span>
      </div>
      <div className="h-1.5 bg-muted rounded overflow-hidden">
        <div
          className="h-full bg-primary transition-all"
          style={{ width: `${state.progress}%` }}
        />
      </div>
    </div>
  );
}

function RunSummary({ title, state }: { title: string; state: RunState }) {
  const { t } = useT();
  return (
    <div className="rounded-md border border-border p-3">
      <div className="text-xs font-semibold text-muted-foreground">{title}</div>
      {state.run ? (
        <>
          <div className="text-sm mt-1">{state.run.summary}</div>
          {/* Every bench that could not run, with its reason. A run of five that
              silently became a run of three is the failure this suite exists to
              make impossible, so the shortfall is shown and not just counted. */}
          {state.run.results
            .filter((result) => !result.ran)
            .map((result) => (
              <div key={result.bench} className="text-xs text-muted-foreground mt-1">
                {result.label}: {result.reason}
              </div>
            ))}
        </>
      ) : (
        <div className="text-sm mt-1 text-muted-foreground">
          {t("suite.notMeasuredYet")}
        </div>
      )}
    </div>
  );
}

/**
 * How a category is named to a reader, in the order they matter for a game.
 *
 * The keys are the backend's, from `impact_categories.py`; the labels are the
 * UI's. `thermal` reads as "Heat & wear" because that is what it buys — a GPU
 * arriving at the match with headroom rather than at its limit.
 */
const CATEGORY_KEY: Record<string, MessageKey> = {
  latency: "suiteCat.latency",
  fps: "suiteCat.fps",
  thermal: "suiteCat.thermal",
  network: "suiteCat.network",
  resources: "suiteCat.resources",
  storage: "suiteCat.storage",
};

const CATEGORY_ORDER = [
  "latency",
  "fps",
  "thermal",
  "network",
  "resources",
  "storage",
];

function groupByCategory(measurements: SuiteMeasurement[]) {
  const groups = new Map<string, SuiteMeasurement[]>();
  for (const m of measurements) {
    // Bench-only metrics keep their own group rather than being dropped or
    // filed under a category they do not belong to.
    const key = m.category ?? "other";
    groups.set(key, [...(groups.get(key) ?? []), m]);
  }

  const ordered = [...groups.keys()].sort((a, b) => {
    const ai = CATEGORY_ORDER.indexOf(a);
    const bi = CATEGORY_ORDER.indexOf(b);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  return ordered.map((key) => ({
    key,
    labelKey: CATEGORY_KEY[key] ?? null,
    rows: groups.get(key) ?? [],
  }));
}

function ComparisonTable({ comparison }: { comparison: SuiteComparison }) {
  const { t } = useT();
  const groups = groupByCategory(comparison.measurements);

  return (
    <Card className="p-4 space-y-4">
      <h3 className="text-sm font-semibold">{comparison.summary}</h3>

      {/* Grouped by what kind of gain it is, so a reader can see where the
          benefit landed rather than reading a flat list of metric names. The
          grouping comes from the server: the settings' own category map decides
          it, and a copy of that map here would be a second answer. */}
      {groups.map((group) => (
        <div key={group.key} className="space-y-1">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {group.labelKey ? t(group.labelKey) : t("suite.otherMeasurements")}
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground text-left">
                  <th className="py-1 pr-3">{t("suite.metric")}</th>
                  <th className="py-1 pr-3 text-right">{t("suite.before")}</th>
                  <th className="py-1 pr-3 text-right">{t("suite.after")}</th>
                  <th className="py-1 pr-3 text-right">{t("suite.change")}</th>
                  <th className="py-1">{t("suite.verdict")}</th>
                </tr>
              </thead>
              <tbody>
                {group.rows.map((m) => {
                  // Bars scale within the group, so a 40% improvement and a
                  // 0.3% one stop looking identical (E5). The number stays;
                  // the bar only restates it.
                  const groupMax = Math.max(
                    ...group.rows.map((row) => Math.abs(row.percent_change)),
                    1,
                  );
                  return (
                  <tr key={m.metric} className="border-t border-border/50">
                    <td className="py-1.5 pr-3 font-mono text-xs">{m.metric}</td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">
                      {m.before.toFixed(2)}
                      {m.unit}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">
                      {m.after.toFixed(2)}
                      {m.unit}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums">
                      {m.delta > 0 ? "+" : ""}
                      {m.delta.toFixed(2)}
                      {m.unit}
                      <Meter
                        className="mt-0.5 w-20 ml-auto"
                        value={Math.abs(m.percent_change)}
                        max={groupMax}
                        // No green/red: which direction is an improvement
                        // depends on the metric, and that judgement lives
                        // server-side with the verdicts (C11). The bar only
                        // sizes the change; "within noise" stays a sentence.
                        tone="primary"
                        label={t("suite.deltaBarLabel", { metric: m.metric, pct: Math.abs(m.percent_change).toFixed(1) })}
                      />
                    </td>
                    <td className="py-1.5 text-xs">
                      {m.exceeds_noise ? (
                        <span className="flex items-center gap-1">
                          <ArrowRight className="w-3 h-3" />
                          {m.percent_change > 0 ? "+" : ""}
                          {m.percent_change.toFixed(1)}%
                        </span>
                      ) : (
                        /* Not "no change": the machine varies by this much on
                           its own, so nothing can be concluded either way. */
                        <span className="text-muted-foreground">
                          {t("suite.withinNoise", {
                            noise: m.noise === null ? "?" : m.noise.toFixed(2),
                            unit: m.unit,
                          })}
                        </span>
                      )}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {comparison.unpaired.length > 0 && (
        <div className="text-xs text-muted-foreground space-y-1">
          <div className="font-semibold">{t("suite.notCompared")}</div>
          {comparison.unpaired.map((entry) => (
            <div key={entry.metric}>
              <span className="font-mono">{entry.metric}</span> — {entry.reason}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

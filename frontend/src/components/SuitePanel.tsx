import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Loader2,
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
      <div className="bg-card rounded-lg border border-border p-4 text-sm text-muted-foreground">
        Loading the instrument list…
      </div>
    );
  }

  const running = phase === "running";
  const hasBaseline = before.run !== null;
  const primaryLabel = hasBaseline ? "Measure again and compare" : "Measure this machine";

  return (
    <div className="space-y-4">
      <div className="bg-card rounded-lg border border-border p-4 space-y-4">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-2">
            <Activity className="w-4 h-4" />
            Measure what changed
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            {hasBaseline
              ? "Baseline taken. Apply the tweaks you want, then press again — the two runs are compared for you."
              : "Takes a baseline of this machine. Nothing is changed and nothing is written."}
          </p>
        </div>

        <div className="flex gap-2 flex-wrap items-center">
          <button
            onClick={() => start(hasBaseline ? "after" : "before")}
            disabled={running || selected.size === 0}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40"
          >
            {running ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            {running ? `Measuring the ${target} run…` : primaryLabel}
          </button>

          {(hasBaseline || running) && (
            <button
              onClick={reset}
              className="flex items-center gap-2 px-3 py-2 rounded-md text-sm bg-muted hover:bg-muted/80"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Start over
            </button>
          )}

          {/* A count rather than a list: the list is one fold away, and the
              number is what tells you the button will do something. */}
          <span className="text-xs text-muted-foreground">
            {selected.size} of {catalogue.benches.length} instruments · {repeats} repeats
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
            <RunSummary title="Before" state={before} />
            <RunSummary title="After" state={after} />
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
            Which instruments, and how many repeats
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
                  {catalogue.min_repeats} or more — a single reading has no noise floor
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

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
          <span className="ml-2 text-xs text-muted-foreground">(not in “run all”)</span>
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
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>
          {state.active ? `Measuring ${state.active}…` : `Starting the ${label} run…`}
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
        <div className="text-sm mt-1 text-muted-foreground">Not measured yet</div>
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
const CATEGORY_LABEL: Record<string, string> = {
  latency: "Latency",
  fps: "Frame rate",
  thermal: "Heat & wear",
  network: "Network",
  resources: "Memory & CPU",
  storage: "Storage",
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
    label: CATEGORY_LABEL[key] ?? "Other measurements",
    rows: groups.get(key) ?? [],
  }));
}

function ComparisonTable({ comparison }: { comparison: SuiteComparison }) {
  const groups = groupByCategory(comparison.measurements);

  return (
    <div className="bg-card rounded-lg border border-border p-4 space-y-4">
      <h3 className="text-sm font-semibold">{comparison.summary}</h3>

      {/* Grouped by what kind of gain it is, so a reader can see where the
          benefit landed rather than reading a flat list of metric names. The
          grouping comes from the server: the settings' own category map decides
          it, and a copy of that map here would be a second answer. */}
      {groups.map((group) => (
        <div key={group.key} className="space-y-1">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {group.label}
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground text-left">
                  <th className="py-1 pr-3">Metric</th>
                  <th className="py-1 pr-3 text-right">Before</th>
                  <th className="py-1 pr-3 text-right">After</th>
                  <th className="py-1 pr-3 text-right">Change</th>
                  <th className="py-1">Verdict</th>
                </tr>
              </thead>
              <tbody>
                {group.rows.map((m) => (
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
                          within noise (±
                          {m.noise === null ? "?" : m.noise.toFixed(2)}
                          {m.unit})
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {comparison.unpaired.length > 0 && (
        <div className="text-xs text-muted-foreground space-y-1">
          <div className="font-semibold">Not compared</div>
          {comparison.unpaired.map((entry) => (
            <div key={entry.metric}>
              <span className="font-mono">{entry.metric}</span> — {entry.reason}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

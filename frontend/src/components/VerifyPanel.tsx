import { Meter } from "./ui/Feedback";
import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  Loader2,
  Scale,
  XCircle,
} from "lucide-react";
import { verifyApi } from "../lib/api";
import type {
  SuiteRun,
  UnmeasurableClaim,
  VerifyReport,
  VerifyStatus,
} from "../lib/api";
import { useStore } from "../store";

/**
 * The evidence engine, in the browser.
 *
 * The panel is laid out in the order the backend answers, and that order is the
 * point. Coverage comes first — before anything is measured — because the useful
 * half of the answer is usually the half that says "start a match first" or
 * "nothing here measures that". A panel that led with a Run button would invite
 * the reading that whatever it printed afterwards was the whole story.
 *
 * Two things are deliberately not done here. Samples are not converted from an
 * instrument's own field names to claim metrics — the server does that, because
 * the two quantities are only the same thing where sources.py says they are.
 * And nothing here decides a verdict; this renders what run_round concluded.
 */

const STATUS_STYLE: Record<
  VerifyStatus,
  { icon: typeof CheckCircle2; className: string; label: string }
> = {
  verified: {
    icon: CheckCircle2,
    className: "text-emerald-500",
    label: "Verified",
  },
  contradicted: {
    icon: XCircle,
    className: "text-red-500",
    label: "Contradicted",
  },
  inconclusive: {
    icon: CircleSlash,
    className: "text-amber-500",
    label: "Lost in the noise",
  },
  unmeasured: {
    icon: CircleSlash,
    className: "text-muted-foreground",
    label: "Not measured",
  },
  not_attributable: {
    icon: AlertTriangle,
    className: "text-amber-500",
    label: "Not attributable",
  },
};

/** How many readings a side wants before its median means anything. */
const SAMPLES_WANTED = 3;

/**
 * A collapsed list of claims that will not be judged, with the reason each.
 *
 * Rendered twice with different titles rather than once with a mixed list. The
 * two groups mean opposite things — one is work a release can do, the other is
 * a category of claim no release ever closes — and a single count of both reads
 * as a backlog a third of which is imaginary.
 */
function ClaimList({
  claims,
  title,
}: {
  claims: UnmeasurableClaim[];
  title: string;
}) {
  if (claims.length === 0) return null;

  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-muted-foreground">
        {claims.length} claim{claims.length === 1 ? "" : "s"} {title}
      </summary>
      <ul className="mt-2 space-y-1">
        {claims.map((claim, index) => (
          <li
            key={`${claim.setting_id}-${claim.metric}-${index}`}
            className="text-muted-foreground"
          >
            <code className="text-xs">{claim.setting_id}</code> {claim.metric} (
            {claim.claimed}) — {claim.reason}
          </li>
        ))}
      </ul>
    </details>
  );
}

type Samples = Record<string, number[]>;

function countReadings(samples: Samples): number {
  return Math.max(0, ...Object.values(samples).map((v) => v.length));
}

/**
 * A suite run, in the shape `verify/round` takes: metric name to its samples.
 *
 * Benches that could not run contribute nothing rather than an empty list — a
 * metric with zero readings on one side would be judged as a missing pair,
 * which is a different statement from "that instrument did not run".
 */
function samplesOf(run: SuiteRun | null): Samples {
  if (!run) return {};
  const samples: Samples = {};
  for (const result of run.results) {
    if (!result.ran) continue;
    for (const [metric, reading] of Object.entries(result.readings)) {
      if (reading.samples.length > 0) samples[metric] = reading.samples;
    }
  }
  return samples;
}

export function VerifyPanel() {
  const selectedIds = useStore((s) => s.selectedSettingIds);
  const settingIds = useMemo(() => Array.from(selectedIds), [selectedIds]);

  // The suite's own runs. Verify used to collect a second before/after through
  // its own buttons, from two of the five instruments — so answering "did
  // anything change" and "was the claim true" about one change meant measuring
  // the machine twice, with different instruments, and the two answers could
  // disagree for no reason the user could see.
  const suiteBefore = useStore((s) => s.suiteBefore);
  const suiteAfter = useStore((s) => s.suiteAfter);
  const before = useMemo(() => samplesOf(suiteBefore), [suiteBefore]);
  const after = useMemo(() => samplesOf(suiteAfter), [suiteAfter]);
  const [report, setReport] = useState<VerifyReport | null>(null);

  const { data: coverage, isFetching: coverageLoading } = useQuery({
    queryKey: ["verify-coverage", settingIds],
    queryFn: () => verifyApi.coverage(settingIds),
    enabled: settingIds.length > 0,
  });

  const roundMutation = useMutation({
    mutationFn: () =>
      verifyApi.round({ setting_ids: settingIds, before, after }),
    onSuccess: (result) => {
      setReport(result);
    },
  });

  const beforeCount = countReadings(before);
  const afterCount = countReadings(after);
  const canJudge = beforeCount > 0 && afterCount > 0 && settingIds.length > 0;

  if (settingIds.length === 0) {
    return (
      <div className="space-y-2">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Scale className="w-5 h-5" />
          Verify a claim
        </h3>
        <p className="text-sm text-muted-foreground">
          Select the settings you are about to change, on the Settings tab. A
          round is only meaningful about settings it knows changed — so this
          asks which ones rather than guessing from what is applied.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Scale className="w-5 h-5" />
          Verify a claim
        </h3>
        <p className="text-sm text-muted-foreground">
          {settingIds.length} setting{settingIds.length === 1 ? "" : "s"}{" "}
          selected. Measure, apply them, measure again, and this judges what the
          settings claimed against what the machine did.
        </p>
      </div>

      {/* 1 — what a round could show at all, answered before anything runs */}
      <section className="space-y-2" aria-labelledby="verify-coverage-heading">
        <h4 id="verify-coverage-heading" className="font-medium">
          What this could show
        </h4>
        {coverageLoading && (
          <p className="text-sm text-muted-foreground flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> Reading the claims…
          </p>
        )}
        {coverage && (
          <>
            <p className="text-sm">{coverage.summary}</p>
            {coverage.required_conditions.length > 0 && (
              <div className="text-sm text-muted-foreground">
                <span className="font-medium">You would need: </span>
                {coverage.required_conditions.join("; ")}
              </div>
            )}
            {/* Two lists, not one, and the split is the point. The gaps are
                things a release can close; the rest are claims about privacy,
                audibility or what a player can tell apart, which no instrument
                settles. Shown together they read as one long to-do, and a third
                of it could never be done. */}
            <ClaimList
              claims={coverage.unmeasurable.filter((claim) => claim.judgeable)}
              title="nothing here can check yet, and why"
            />
            <ClaimList
              claims={coverage.unmeasurable.filter((claim) => !claim.judgeable)}
              title="no measurement settles — real claims, not gaps"
            />
          </>
        )}
      </section>

      {/* 2 — what the suite measured, which is where the readings come from */}
      <section className="space-y-2" aria-labelledby="verify-samples-heading">
        <h4 id="verify-samples-heading" className="font-medium">
          Readings
        </h4>
        {beforeCount === 0 && afterCount === 0 ? (
          <p className="text-sm text-muted-foreground">
            No measurements yet. Take a baseline on the Measure tab, apply these
            settings, and measure again — this judges the claims against that
            same pair rather than asking for a second one.
          </p>
        ) : (
          <>
            <p className="text-sm">
              From the measurement suite: {beforeCount} reading
              {beforeCount === 1 ? "" : "s"} before, {afterCount} after, across{" "}
              {Object.keys({ ...before, ...after }).length} metrics.
            </p>
            <p className="text-sm text-muted-foreground">
              {beforeCount < SAMPLES_WANTED || afterCount < SAMPLES_WANTED
                ? `Fewer than ${SAMPLES_WANTED} readings a side. Two runs of the same measurement on an idle machine differ, and without knowing by how much, a small change cannot be told from nothing happening — raise the repeat count on the Measure tab.`
                : "Enough readings on both sides for the noise floor to mean something."}
            </p>
          </>
        )}
      </section>

      {/* 3 — the verdict, which is the backend's to give */}
      <section className="space-y-2" aria-labelledby="verify-round-heading">
        <h4 id="verify-round-heading" className="font-medium">
          Judge
        </h4>
        <button
          onClick={() => roundMutation.mutate()}
          disabled={!canJudge || roundMutation.isPending}
          className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium bg-primary text-primary-foreground disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {roundMutation.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Scale className="w-4 h-4" />
          )}
          Judge these claims
        </button>
        {!canJudge && (
          <p className="text-sm text-muted-foreground">
            Needs a reading on each side, and a setting selected. One side of a
            pair is not a small result, it is no result.
          </p>
        )}
        {roundMutation.isError && (
          <p className="text-sm text-red-500">
            {(roundMutation.error as Error).message}
          </p>
        )}

        {report && (
          <div className="space-y-3 pt-2">
            <p className="text-sm font-medium">{report.summary}</p>
            {report.notes.length > 0 && (
              <ul className="text-sm text-muted-foreground space-y-1">
                {report.notes.map((note, index) => (
                  <li key={index}>{note}</li>
                ))}
              </ul>
            )}
            <ul className="space-y-1">
              {report.verdicts.map((verdict, index) => {
                const style = STATUS_STYLE[verdict.status];
                const Icon = style.icon;
                return (
                  <li
                    key={`${verdict.setting_id}-${verdict.metric}-${index}`}
                    className="flex items-start gap-2 text-sm"
                  >
                    <Icon
                      className={`w-4 h-4 mt-0.5 shrink-0 ${style.className}`}
                      aria-hidden="true"
                    />
                    <span>
                      <span className="sr-only">{style.label}: </span>
                      <code className="text-xs">{verdict.setting_id}</code>{" "}
                      claimed {verdict.claimed} for {verdict.metric} —{" "}
                      <span className={style.className}>{style.label}</span>
                      {verdict.measured && (
                        <>
                          {" "}
                          ({verdict.measured.before} →{" "}
                          {verdict.measured.after} {verdict.measured.unit},{" "}
                          {verdict.measured.percent_change}%, noise{" "}
                          {verdict.measured.noise})
                        </>
                      )}
                      {verdict.reason && (
                        <span className="text-muted-foreground">
                          {" "}
                          — {verdict.reason}
                        </span>
                      )}
                      {/* The change and the machine's own variation on one
                          axis (E5): a change whose bar does not clear the
                          noise bar is not a finding, and now looks like one. */}
                      {verdict.measured && verdict.measured.noise !== null && (
                        <span className="block mt-1 max-w-xs space-y-0.5">
                          <Meter
                            value={Math.abs(
                              verdict.measured.after - verdict.measured.before,
                            )}
                            max={
                              Math.max(
                                Math.abs(
                                  verdict.measured.after -
                                    verdict.measured.before,
                                ),
                                verdict.measured.noise,
                              ) * 1.1
                            }
                            tone="primary"
                            label={`Measured change: ${Math.abs(verdict.measured.after - verdict.measured.before).toFixed(2)} ${verdict.measured.unit}`}
                          />
                          <Meter
                            value={verdict.measured.noise}
                            max={
                              Math.max(
                                Math.abs(
                                  verdict.measured.after -
                                    verdict.measured.before,
                                ),
                                verdict.measured.noise,
                              ) * 1.1
                            }
                            tone="warning"
                            label={`This machine's own variation (noise floor): ${verdict.measured.noise.toFixed(2)} ${verdict.measured.unit}`}
                          />
                        </span>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}

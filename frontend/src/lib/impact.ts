/**
 * What the settings *claim*, counted — never added up into a result.
 *
 * This module used to produce the home screen's headline: every setting's
 * claimed fps midpoint summed under an invented decay curve (first five at
 * full weight, next five at 0.7, the rest at 0.5), then spread across an
 * invented range (×0.7 to ×1.1) to look like a measurement. On a real machine
 * it read **"Gained +28-45% FPS"** while the product's own `headroom.json`
 * measured that machine at 57.4 fps against a 297 fps target — 19%.
 *
 * Nothing in the arithmetic was wrong. The inputs were: `impact_scores` is
 * what a setting claims, it came from vendor documentation and somebody else's
 * hardware, and no total of it is a fact about the machine reading it. That is
 * C11 rule 1, and this file is the reason the rule exists — it is the third
 * time the same mistake shipped, after the summed `-683ms` latency and
 * `dns_security`'s invented `-12 ms`.
 *
 * So what is left here counts and never totals:
 *
 * - **`score`** is how many settings sit at their recommended value. A count of
 *   states, not a sum of claims.
 * - **`latencyTweaks`** and **`ramTweaks`** are how many settings carry that
 *   kind of claim. The per-setting figure still appears on the row itself, via
 *   `formatBenefit`, which is the one place it has a referent.
 * - **`cleanupReclaimableMB`** does add up, and is the exception that shows the
 *   rule: those bytes were counted on this disk by the cleanup scan. Measured
 *   quantities add. Claimed ones do not.
 *
 * A gain figure belongs to `benchmark/`, which measures.
 */

import type { Setting } from "../types/setting";
import { parseSizeToMB } from "./cleanupSize";

export interface ImpactSummary {
  score: { optimized: number; total: number; percentage: number };
  potential: {
    /**
     * How many tweaks carry a latency effect — deliberately a count, not a sum.
     *
     * This used to be `latencyReduction`, the arithmetic total of every
     * setting's `latency_ms`, and on a real machine it rendered as "GAINED
     * -683ms LATENCY". That number cannot mean anything: DNS lookup time, mouse
     * polling interval, timer resolution and NIC buffering are different clocks
     * measuring different events, and adding them produces a figure no
     * measurement could ever confirm.
     */
    latencyTweaks: number;
    /**
     * How many tweaks claim to free memory, for the same reason.
     *
     * This was the first setting's `ram_saved` string shown under the label
     * "RAM", which read as a total for the whole list while being one row's
     * claim picked arbitrarily.
     */
    ramTweaks: number;
  };
  gained: { latencyTweaks: number; ramTweaks: number; count: number };
}

/** A tweak whose state we score: applicable, settable, already detected. */
function isScorable(s: Setting): boolean {
  return (
    s.isApplicable && !s.isAction && s.currentValue !== null && !s.isReadonly
  );
}

/**
 * A tweak that recommends exactly what the system ships with.
 *
 * 54 of the shipped settings are this shape, and they are not pointless: a
 * machine drifts, whether by another "optimizer" or by hand, and these detect
 * the drift and put it back. That is why they are neither deleted nor made
 * readonly.
 *
 * What they cannot do is contribute to `gained`. A gain is measured against a
 * counterfactual — the state the machine would be in without the tweak — and
 * for these the counterfactual *is* the machine's factory state. Counting them
 * inflated the headline on every machine, forever, with a benefit no user ever
 * received. `potential` is unaffected: if such a setting has drifted, fixing it
 * really does recover something.
 *
 * Same class as the invented `-12 ms` on dns_security and the summed latency
 * total: a number that no measurement could ever confirm.
 */
function isFactoryDefault(s: Setting): boolean {
  return (
    s.recommendedValue !== null &&
    s.recommendedValue !== undefined &&
    s.defaultValue !== null &&
    s.defaultValue !== undefined &&
    String(s.recommendedValue) === String(s.defaultValue)
  );
}

/**
 * How many tweaks are where they should be, and how many carry which kind of
 * claim. No scope filtering — all applicable tweaks count.
 */
export function summarizeImpact(settings: Iterable<Setting>): ImpactSummary {
  let optimized = 0;
  let total = 0;

  let potLatency = 0;
  let potRam = 0;
  let gainLatency = 0;
  let gainRam = 0;
  let gainCount = 0;

  for (const s of settings) {
    if (!isScorable(s)) continue;
    total++;

    const scores = s.impactScores;
    const hasLatency =
      typeof scores?.latency_ms === "number" && scores.latency_ms !== 0;
    const hasRam = typeof scores?.ram_saved === "string";

    if (s.isOptimized) {
      optimized++;
      // The score still counts it — "this setting is at its ideal value" is
      // true and worth showing. Only the *gain* is withheld, and only for
      // settings that were never anywhere else. See isFactoryDefault.
      if (!isFactoryDefault(s)) {
        gainCount++;
        if (hasLatency) gainLatency++;
        if (hasRam) gainRam++;
      }
    } else {
      if (hasLatency) potLatency++;
      if (hasRam) potRam++;
    }
  }

  return {
    score: {
      optimized,
      total,
      percentage: total > 0 ? Math.round((optimized / total) * 100) : 0,
    },
    potential: { latencyTweaks: potLatency, ramTweaks: potRam },
    gained: {
      latencyTweaks: gainLatency,
      ramTweaks: gainRam,
      count: gainCount,
    },
  };
}

/** Short benefit string for a tweak list row, e.g. "+3-5% FPS · −0.5ms". */
export function formatBenefit(setting: Setting): string {
  const scores = setting.impactScores;
  if (!scores) return "";
  const parts: string[] = [];

  // The setting's own words, verbatim. Not parsed into a number, because the
  // only reason to parse one was to add it to the others — which is the thing
  // this file no longer does.
  if (typeof scores.fps === "string" && !/^\+?0%?$/.test(scores.fps.trim())) {
    parts.push(`${scores.fps} FPS`);
  }
  if (typeof scores.latency_ms === "number" && scores.latency_ms !== 0) {
    const ms = scores.latency_ms;
    parts.push(`${ms > 0 ? "+" : "−"}${Math.abs(ms)}ms`);
  }
  if (typeof scores.ram_saved === "string") {
    parts.push(`${scores.ram_saved} RAM`);
  }
  return parts.join(" · ");
}

/** Total reclaimable disk (MB) across cleanup + game_cleanup action settings. */
export function cleanupReclaimableMB(settings: Iterable<Setting>): number {
  let total = 0;
  // docker_prune and docker_prune_all reclaim the SAME underlying docker space
  // (prune-all is a superset of prune) — they're alternative actions, not
  // additive. Count the docker family once (the larger) so the headline total
  // doesn't double-count it.
  let dockerMax = 0;
  for (const s of settings) {
    if (!s.isAction || !s.isApplicable) continue;
    if (s.module !== "cleanup" && s.module !== "game_cleanup") continue;
    const mb = parseSizeToMB(s.currentValue);
    if (mb === null) continue;
    if (s.name === "docker_prune" || s.name === "docker_prune_all") {
      dockerMax = Math.max(dockerMax, mb);
      continue;
    }
    total += mb;
  }
  return total + dockerMax;
}

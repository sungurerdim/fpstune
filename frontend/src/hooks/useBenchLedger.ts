/**
 * The measurement ledger, kept current while something is measuring.
 *
 * Two rates rather than one. A job in flight moves through its plan a bench at
 * a time and the panel showing "step 3 of 7" is worthless a minute late, so it
 * is polled at the rate the step line needs. With nothing in flight the answer
 * changes only when the scheduler opens a job, which is a background daemon
 * decision minutes apart — polling that at fifteen seconds would be four
 * requests a minute to be told nothing happened, all session.
 *
 * `staleTime` stays at the 5 s C7 gives dynamic data: it is what makes a second
 * mount of the card (Home and the Benchmarks tab both read this) reuse the
 * answer the first one already has instead of asking again.
 */

import { useQuery } from "@tanstack/react-query";
import { benchmarkApi, type BenchLedger } from "../lib/api";

/** In flight: the step line has to keep up with the plan. */
export const LEDGER_POLL_ACTIVE_MS = 15_000;
/** Idle: only the scheduler can change the answer, and it does so rarely. */
export const LEDGER_POLL_IDLE_MS = 60_000;

export const LEDGER_QUERY_KEY = ["bench-ledger"] as const;

/**
 * Which of the two rates this payload wants.
 *
 * Exported because it is the whole switching rule, and a rule inside a query
 * option is a rule no test can reach without waiting a real minute for it.
 */
export function ledgerPollInterval(data: BenchLedger | undefined): number {
  const status = data?.job?.status;
  // "queued" polls at the fast rate too: the job is waiting on a guard — an
  // idle machine, a game closing — and the moment it starts is the moment the
  // status line stops being true.
  return status === "running" || status === "queued"
    ? LEDGER_POLL_ACTIVE_MS
    : LEDGER_POLL_IDLE_MS;
}

export function useBenchLedger() {
  return useQuery({
    queryKey: LEDGER_QUERY_KEY,
    queryFn: benchmarkApi.ledger,
    staleTime: 5_000,
    refetchInterval: (query) => ledgerPollInterval(query.state.data),
  });
}

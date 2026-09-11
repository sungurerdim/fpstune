/**
 * The ledger is polled at the rate the screen it feeds actually needs.
 *
 * A job in flight moves a bench at a time and the line saying "step 3 of 7" is
 * worthless a minute late; with nothing in flight only the background scheduler
 * can change the answer, and polling that every fifteen seconds is four
 * requests a minute, all session, to be told nothing happened.
 *
 * Both halves are asserted: the rule on its own, and that the hook wires the
 * rule to the query rather than a constant. The second one is checked by
 * advancing the clock, because a `refetchInterval` that ignored the job status
 * would still make the first half green.
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import React from "react";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../test/mocks/server";
import {
  LEDGER_POLL_ACTIVE_MS,
  LEDGER_POLL_IDLE_MS,
  ledgerPollInterval,
  useBenchLedger,
} from "../useBenchLedger";
import type { BenchLedger, LedgerJob } from "../../lib/api";

function job(over: Partial<LedgerJob> = {}): LedgerJob {
  return {
    id: "job-1",
    trigger: "baseline",
    label: "baseline",
    status: "running",
    plan: ["timing", "disk_io"],
    step_index: 0,
    current_bench: "timing",
    remaining: ["timing", "disk_io"],
    attempts: {},
    created_at: 1_757_500_000,
    updated_at: 1_757_500_030,
    ...over,
  };
}

function ledger(over: Partial<BenchLedger> = {}): BenchLedger {
  return {
    job: null,
    baseline: null,
    after: null,
    areas: [],
    bulk_apply_pending: false,
    poll_interval_seconds: 60,
    ...over,
  };
}

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

afterEach(() => {
  vi.useRealTimers();
});

describe("the poll rate follows the job", () => {
  it("polls fast while a job is running or queued", () => {
    expect(ledgerPollInterval(ledger({ job: job({ status: "running" }) }))).toBe(
      LEDGER_POLL_ACTIVE_MS,
    );
    // Queued counts as in flight: it is waiting on a guard, and the moment it
    // starts is the moment the status line stops being true.
    expect(ledgerPollInterval(ledger({ job: job({ status: "queued" }) }))).toBe(
      LEDGER_POLL_ACTIVE_MS,
    );
  });

  it("falls back to the slow rate with nothing in flight", () => {
    expect(ledgerPollInterval(ledger())).toBe(LEDGER_POLL_IDLE_MS);
    expect(ledgerPollInterval(ledger({ job: job({ status: "done" }) }))).toBe(
      LEDGER_POLL_IDLE_MS,
    );
    expect(ledgerPollInterval(ledger({ job: job({ status: "failed" }) }))).toBe(
      LEDGER_POLL_IDLE_MS,
    );
    // Before the first response there is no job to read, and the answer must
    // still be a number rather than undefined.
    expect(ledgerPollInterval(undefined)).toBe(LEDGER_POLL_IDLE_MS);
  });

  it("the two rates are different, or the rule does nothing", () => {
    expect(LEDGER_POLL_ACTIVE_MS).toBeLessThan(LEDGER_POLL_IDLE_MS);
  });
});

describe("useBenchLedger", () => {
  it("returns what the route answered", async () => {
    server.use(
      http.get("/api/benchmark/ledger", () =>
        HttpResponse.json(ledger({ bulk_apply_pending: true })),
      ),
    );

    const { result } = renderHook(() => useBenchLedger(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.bulk_apply_pending).toBe(true);
  });

  it("refetches on the fast interval while a job runs", async () => {
    let calls = 0;
    server.use(
      http.get("/api/benchmark/ledger", () => {
        calls += 1;
        return HttpResponse.json(ledger({ job: job({ status: "running" }) }));
      }),
    );

    // Real time still advances, so the fetch promises this drives can settle.
    vi.useFakeTimers({ shouldAdvanceTime: true });

    const { result } = renderHook(() => useBenchLedger(), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(calls).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(LEDGER_POLL_ACTIVE_MS + 200);
    });

    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(2));
    // The idle rate would still be waiting at this point in the clock.
    expect(LEDGER_POLL_ACTIVE_MS + 200).toBeLessThan(LEDGER_POLL_IDLE_MS);
  });
});

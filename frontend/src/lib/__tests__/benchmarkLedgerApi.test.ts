/**
 * The two ledger routes are actually called, at the paths the backend serves.
 *
 * The path is the whole contract here: `/benchmark/ledger` against
 * `/benchmark/suite` is one word, and a typo produces a 404 the panel renders
 * as "could not be read" — indistinguishable from a machine that has measured
 * nothing. Asserting the request the client makes, not a mocked return value,
 * is what makes that failure visible here instead of on someone's screen.
 */

import { describe, it, expect } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../test/mocks/server";
import { benchmarkApi } from "../api";
import { verdictOf, formatDelta, formatReading, benchLabel, jobStep } from "../ledger";
import type { LedgerArea } from "../api";

function area(over: Partial<LedgerArea> = {}): LedgerArea {
  return {
    area: "disk",
    label: "Disk",
    instrument: "disk_io",
    metric: "storage_performance",
    measured: true,
    reason: "",
    before: 1240.5,
    after: 1310.25,
    delta: 69.75,
    percent_change: 5.62,
    unit: "MB/s",
    noise: 12.5,
    exceeds_noise: true,
    ...over,
  };
}

describe("benchmarkApi talks to the ledger routes", () => {
  it("reads the ledger from GET /api/benchmark/ledger", async () => {
    const seen: string[] = [];
    server.use(
      http.get("/api/benchmark/ledger", ({ request }) => {
        seen.push(`${request.method} ${new URL(request.url).pathname}`);
        return HttpResponse.json({
          job: null,
          baseline: null,
          after: null,
          areas: [area()],
          bulk_apply_pending: false,
          poll_interval_seconds: 60,
        });
      }),
    );

    const ledger = await benchmarkApi.ledger();

    expect(seen).toEqual(["GET /api/benchmark/ledger"]);
    expect(ledger.areas[0].label).toBe("Disk");
  });

  it("queues a run with POST /api/benchmark/ledger/run", async () => {
    const seen: string[] = [];
    server.use(
      http.post("/api/benchmark/ledger/run", ({ request }) => {
        seen.push(`${request.method} ${new URL(request.url).pathname}`);
        return HttpResponse.json({ queued: true, job: null });
      }),
    );

    const result = await benchmarkApi.runLedgerJob();

    expect(seen).toEqual(["POST /api/benchmark/ledger/run"]);
    expect(result.queued).toBe(true);
  });

  it("surfaces a failed read rather than returning an empty ledger", async () => {
    server.use(
      http.get("/api/benchmark/ledger", () =>
        HttpResponse.text("ledger unreadable", { status: 500 }),
      ),
    );

    await expect(benchmarkApi.ledger()).rejects.toThrow(/500/);
  });
});

describe("an area is read without inventing a direction", () => {
  it("calls a change past the noise floor 'changed' when nothing says which way is up", () => {
    // The payload carries no `improves_upward` and no `verdict`, so naming a
    // winner would be the frontend guessing at the metric's direction.
    expect(verdictOf(area())).toBe("changed");
  });

  it("names improved and worse from the server's own direction", () => {
    expect(verdictOf(area({ improves_upward: true }))).toBe("improved");
    expect(verdictOf(area({ improves_upward: false }))).toBe("worse");
    expect(
      verdictOf(area({ delta: -40, percent_change: -3.2, improves_upward: true })),
    ).toBe("worse");
    expect(
      verdictOf(area({ delta: -40, percent_change: -3.2, improves_upward: false })),
    ).toBe("improved");
  });

  it("prefers the server's own verdict over deriving one", () => {
    expect(verdictOf(area({ verdict: "worse", improves_upward: true }))).toBe("worse");
  });

  it("calls a change inside the machine's own variation neither way", () => {
    expect(verdictOf(area({ exceeds_noise: false }))).toBe("within_noise");
  });

  it("calls an area with no pair unmeasured, whatever else the payload holds", () => {
    const unpaired = area({
      measured: false,
      reason: "The disk benchmark has not run on both sides of a change yet.",
      before: null,
      after: null,
      delta: null,
      percent_change: null,
      noise: null,
      exceeds_noise: false,
    });
    expect(verdictOf(unpaired)).toBe("unmeasured");
  });

  it("keeps the instrument's own unit and the sign of the change", () => {
    expect(formatReading(1240.5, "MB/s")).toBe("1240.50MB/s");
    expect(formatDelta(69.75, "MB/s")).toBe("+69.75MB/s");
    expect(formatDelta(-2.4, "ms")).toBe("-2.40ms");
    // A null reading renders as nothing at all; a zero would be a measurement.
    expect(formatReading(null, "ms")).toBe("");
    expect(formatDelta(null, "ms")).toBe("");
  });

  it("names a running bench with the backend's own label, and never re-titles one", () => {
    const areas = [area(), area({ area: "network", label: "Network", instrument: "network" })];
    expect(benchLabel(areas, "disk_io")).toBe("Disk");
    // A bench no area claims keeps its key: identifying the step honestly beats
    // a label invented in the frontend (C9).
    expect(benchLabel(areas, "frame_pacing")).toBe("frame_pacing");
    expect(benchLabel(areas, null)).toBe("");
  });

  it("counts the step a human counts, and never past the end of the plan", () => {
    const job = {
      id: "j1",
      trigger: "baseline",
      label: "baseline",
      status: "running",
      plan: ["timing", "disk_io", "network"],
      step_index: 2,
      current_bench: "network",
      remaining: ["network"],
      attempts: {},
      created_at: 0,
      updated_at: 0,
    };
    expect(jobStep(job)).toEqual({ step: 3, total: 3 });
    expect(jobStep({ ...job, step_index: 3, current_bench: null })).toEqual({
      step: 3,
      total: 3,
    });
    expect(jobStep({ ...job, step_index: 0 })).toEqual({ step: 1, total: 3 });
  });
});

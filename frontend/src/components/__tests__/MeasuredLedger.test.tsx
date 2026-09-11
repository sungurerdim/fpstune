/**
 * What fpstune changed, measured — and what it must never say instead.
 *
 * This screen is the one the product has got wrong three times, always the same
 * way: a single headline produced by adding unrelated things up
 * (`"GAINED -683ms LATENCY"`, `"Gained +28-45% FPS"`). So the assertions here
 * are as much about absence as presence — one row per area with its own
 * instrument's reading, no total anywhere, and an area with no pair carrying
 * its reason and no number at all (C11 rules 1 and 3).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { render, screen, waitFor, within } from "../../test/utils";
import { server } from "../../test/mocks/server";
import { HomeMeasuredCard, LedgerPanel } from "../MeasuredLedger";
import { HomeTab } from "../HomeTab";
import { useStore } from "../../store";
import type { BenchLedger, LedgerArea, LedgerJob } from "../../lib/api";

vi.mock("../HardwarePanel", () => ({ HardwarePanel: () => null }));
vi.mock("../MaintenancePanel", () => ({ MaintenancePanel: () => null }));
vi.mock("../SelfCheckNotice", () => ({ SelfCheckNotice: () => null }));
vi.mock("../../hooks/useBulkApply", () => ({
  useBulkApply: () => ({ apply: vi.fn(), isApplying: false }),
}));
vi.mock("../../hooks/useCleanupRunner", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../hooks/useCleanupRunner")>()),
  useCleanupRunner: () => ({
    selectedIds: [],
    selectedCount: 0,
    hasSelection: false,
    isRunning: false,
    run: vi.fn(),
    confirmIds: null,
    confirmRun: vi.fn(),
    cancelConfirm: vi.fn(),
  }),
}));

/** A disk read that improved by more than this machine's own variation. */
const DISK: LedgerArea = {
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
  improves_upward: true,
};

/** A network latency that went the wrong way, by more than the noise. */
const NETWORK: LedgerArea = {
  area: "network",
  label: "Network",
  instrument: "network",
  metric: "latency_ms",
  measured: true,
  reason: "",
  before: 18.4,
  after: 20.9,
  delta: 2.5,
  percent_change: 13.59,
  unit: "ms",
  noise: 0.9,
  exceeds_noise: true,
  improves_upward: false,
};

/** Inside the machine's own variation, which is not the same as "no change". */
const TIMING: LedgerArea = {
  area: "timing",
  label: "Timer and scheduling",
  instrument: "timing",
  metric: "latency_spike_ms",
  measured: true,
  reason: "",
  before: 0.42,
  after: 0.45,
  delta: 0.03,
  percent_change: 7.14,
  unit: "ms",
  noise: 0.11,
  exceeds_noise: false,
  improves_upward: false,
};

/** No instrument on the performance path, permanently, and it says so. */
const FPS: LedgerArea = {
  area: "fps",
  label: "Frame rate",
  instrument: "presentmon",
  metric: "fps",
  measured: false,
  reason:
    "A frame rate needs a game rendering to measure. fpstune captures one automatically while you play — see Frame-rate headroom.",
  before: null,
  after: null,
  delta: null,
  percent_change: null,
  unit: "",
  noise: null,
  exceeds_noise: false,
};

const RUNNING_JOB: LedgerJob = {
  id: "job-7",
  trigger: "baseline",
  label: "baseline",
  status: "running",
  plan: ["timing", "disk_io", "network"],
  step_index: 2,
  current_bench: "network",
  remaining: ["network"],
  attempts: {},
  created_at: 1_757_500_000,
  updated_at: 1_757_500_120,
};

function ledger(over: Partial<BenchLedger> = {}): BenchLedger {
  return {
    job: null,
    baseline: null,
    after: null,
    areas: [DISK, NETWORK, TIMING, FPS],
    bulk_apply_pending: false,
    poll_interval_seconds: 60,
    ...over,
  };
}

function serveLedger(payload: BenchLedger) {
  server.use(
    http.get("/api/benchmark/ledger", () => HttpResponse.json(payload)),
  );
}

beforeEach(() => {
  useStore.setState({
    settings: new Map(),
    selectedSettingIds: new Set(),
    maintenanceSelection: {},
    cleanupResults: {},
    runSteps: [],
    operationStatus: {},
    categoryDetectionStatus: { core: "done" },
  } as never);
});

describe("Home: what fpstune changed, measured", () => {
  it("shows a measured area's before, after and change in its own unit", async () => {
    serveLedger(ledger());

    render(<HomeMeasuredCard />);

    const tile = await screen.findByTestId("measured-area-disk");
    expect(within(tile).getByText("1240.50MB/s")).toBeInTheDocument();
    expect(within(tile).getByText("1310.25MB/s")).toBeInTheDocument();
    expect(within(tile).getByText("+69.75MB/s")).toBeInTheDocument();
    // The direction is the server's: this metric improves upward, so a rise is
    // an improvement and the row is allowed to say so.
    expect(within(tile).getByText("Improved")).toBeInTheDocument();
    // The noise floor travels with the number that beat it.
    expect(within(tile).getByText(/noise 12\.50MB\/s/)).toBeInTheDocument();
  });

  it("says a change inside the machine's own variation concludes nothing", async () => {
    serveLedger(ledger());

    render(<HomeMeasuredCard />);

    const tile = await screen.findByTestId("measured-area-timing");
    expect(
      within(tile).getByText(/Within this machine's own variation of 0\.11ms/),
    ).toBeInTheDocument();
    // Not "no change", and not an improvement either.
    expect(within(tile).queryByText("Improved")).toBeNull();
    expect(within(tile).queryByText("Worse")).toBeNull();
  });

  it("gives an unmeasured area its reason and no number at all", async () => {
    serveLedger(ledger());

    render(<HomeMeasuredCard />);

    const tile = await screen.findByTestId("measured-area-fps");
    expect(within(tile).getByText(/needs a game rendering to measure/)).toBeInTheDocument();
    // A zero here would read as a measurement of zero, which is the failure
    // this rule exists to prevent.
    expect(tile.textContent ?? "").not.toMatch(/\d/);
  });

  it("never adds two areas together into a headline", async () => {
    serveLedger(ledger());

    render(<HomeMeasuredCard />);
    const card = await screen.findByTestId("home-measured");
    // Wait for the readings themselves: an empty card trivially has no total.
    await screen.findByTestId("measured-area-disk");

    // No number in this card may be one no instrument produced, and the
    // classic invented number is the sum: 69.75 + 2.50 + 0.03 MB/s and ms
    // added together, which is four units in one figure and means nothing.
    const text = card.textContent ?? "";
    expect(text).not.toContain("72.28");
    // And no headline wording that would imply one. "Gained +28-45% FPS" is
    // the exact sentence this product shipped and had to withdraw.
    expect(text.toLowerCase()).not.toMatch(/total|overall|combined|gained/);
    // Every area still speaks for itself.
    expect(screen.getAllByTestId(/^measured-area-/)).toHaveLength(4);
  });

  it("says which step the background job is on, in the backend's own words", async () => {
    serveLedger(ledger({ job: RUNNING_JOB }));

    render(<HomeMeasuredCard />);

    const status = await screen.findByTestId("ledger-job-status");
    // "network" is the bench key; "Network" is the label the ledger itself
    // gave that instrument, and the frontend re-titles nothing.
    expect(status).toHaveTextContent("Baseline running: step 3/3 — Network");
  });

  it("says a queued job is waiting for the machine rather than looking stuck", async () => {
    serveLedger(
      ledger({ job: { ...RUNNING_JOB, status: "queued", trigger: "after" } }),
    );

    render(<HomeMeasuredCard />);

    const status = await screen.findByTestId("ledger-job-status");
    expect(status).toHaveTextContent(/waiting for the machine to be idle/);
  });

  it("says a bulk apply is still unmeasured when nothing is in flight", async () => {
    serveLedger(ledger({ bulk_apply_pending: true }));

    render(<HomeMeasuredCard />);

    const status = await screen.findByTestId("ledger-job-status");
    expect(status).toHaveTextContent(/Tweaks were applied since the last measurement/);
  });

  it("says the ledger could not be read instead of rendering an empty card", async () => {
    server.use(
      http.get("/api/benchmark/ledger", () =>
        HttpResponse.text("nope", { status: 500 }),
      ),
    );

    render(<HomeMeasuredCard />);

    expect(
      await screen.findByText("The measurement ledger could not be read."),
    ).toBeInTheDocument();
  });

  it("is mounted on Home, laid out across the width it is given", async () => {
    serveLedger(ledger());

    render(<HomeTab />);

    expect(await screen.findByTestId("home-measured")).toBeInTheDocument();
    const grid = await screen.findByTestId("home-measured-grid");
    expect(grid).toHaveClass("grid");
    expect(grid).toHaveClass("grid-cols-1");
    expect(grid).toHaveClass("lg:grid-cols-2");
    expect(grid).toHaveClass("2xl:grid-cols-3");
  });
});

describe("Benchmarks: the ledger panel", () => {
  it("puts every area in the table, measured or explained", async () => {
    serveLedger(ledger());

    render(<LedgerPanel />);

    await screen.findByTestId("ledger-area-table");
    const diskRow = screen.getByTestId("ledger-row-disk");
    expect(within(diskRow).getByText("disk_io")).toBeInTheDocument();
    expect(within(diskRow).getByText("1310.25MB/s")).toBeInTheDocument();

    const fpsRow = screen.getByTestId("ledger-row-fps");
    expect(within(fpsRow).getByText(/needs a game rendering/)).toBeInTheDocument();
    expect(fpsRow.textContent ?? "").not.toMatch(/\d/);
  });

  it("names the runs it is comparing, so a reload no longer loses them", async () => {
    serveLedger(
      ledger({
        baseline: {
          label: "baseline",
          started_at: Math.floor(Date.now() / 1000) - 3600,
          summary: "All 5 benches ran",
          bench_count: 5,
          ran_count: 5,
          metrics: ["storage_performance", "latency_ms"],
        },
      }),
    );

    render(<LedgerPanel />);

    expect(
      await screen.findByText(/Baseline: All 5 benches ran/),
    ).toBeInTheDocument();
  });

  it("says nothing has been measured yet rather than showing a blank panel", async () => {
    serveLedger(ledger({ areas: [] }));

    render(<LedgerPanel />);

    expect(
      await screen.findByText("Nothing has been measured on this machine yet."),
    ).toBeInTheDocument();
  });

  it("queues a run when Measure now is pressed, and says it queued", async () => {
    serveLedger(ledger());
    const posts: string[] = [];
    server.use(
      http.post("/api/benchmark/ledger/run", ({ request }) => {
        posts.push(new URL(request.url).pathname);
        return HttpResponse.json({ queued: true, job: RUNNING_JOB });
      }),
    );

    render(<LedgerPanel />);
    await screen.findByTestId("ledger-area-table");

    await userEvent.click(screen.getByRole("button", { name: /Measure now/i }));

    await waitFor(() => expect(posts).toEqual(["/api/benchmark/ledger/run"]));
    expect(await screen.findByText("Queued.")).toBeInTheDocument();
    // The button promises a queue, not a measurement: the guards live in the
    // scheduler and the helper text has to say so.
    expect(
      screen.getByText(/fpstune measures it once the machine is idle/),
    ).toBeInTheDocument();
  });

  it("reports a job already in flight instead of opening a second one", async () => {
    serveLedger(ledger({ job: RUNNING_JOB }));
    server.use(
      http.post("/api/benchmark/ledger/run", () =>
        HttpResponse.json({ queued: false, job: RUNNING_JOB }),
      ),
    );

    render(<LedgerPanel />);
    await screen.findByTestId("ledger-area-table");

    await userEvent.click(screen.getByRole("button", { name: /Measure now/i }));

    expect(
      await screen.findByText("A measurement is already in flight."),
    ).toBeInTheDocument();
  });
});

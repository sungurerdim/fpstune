/**
 * The panel must not be more confident than the engine behind it.
 *
 * Every defect worth guarding here is the same shape: the browser presenting a
 * measurement as more than it is. So these assert the refusals rather than the
 * happy path — that it will not judge one side of a pair, that it says what a
 * round cannot show before it says what it can, and that a verdict's status
 * reaches a screen reader instead of living in an icon's colour.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "../../test/utils";
import { VerifyPanel } from "../VerifyPanel";
import { useStore } from "../../store";
import { verifyApi } from "../../lib/api";
import type { VerifyCoverage, VerifySources } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  verifyApi: {
    coverage: vi.fn(),
    sources: vi.fn(),
    sample: vi.fn(),
    round: vi.fn(),
  },
}));

const mocked = vi.mocked(verifyApi);

const SOURCES: VerifySources = {
  sources: [
    {
      name: "dpc",
      requires: "nothing — it measures the machine as it is",
      metrics: ["latency_spike_ms"],
      units: { latency_spike_ms: "ms" },
      runnable: true,
    },
    {
      name: "presentmon",
      requires: "a game running and rendering frames",
      metrics: ["fps"],
      units: {},
      runnable: false,
    },
  ],
  no_instrument: { ram_saved: "no sampler for working set" },
};

const COVERAGE: VerifyCoverage = {
  summary: "1 of 3 claims can be measured here; 2 cannot",
  total_claims: 3,
  measurable: [
    {
      setting_id: "power:usb_selective_suspend",
      metric: "latency_ms",
      claimed: "-1.5",
      source: "network",
      requires: "a reachable host to measure against",
    },
  ],
  unmeasurable: [
    {
      setting_id: "power:usb_selective_suspend",
      metric: "ram_saved",
      claimed: "50MB",
      reason: "no sampler for working set",
      judgeable: true,
    },
    // A claim no instrument settles, so the panel must not list it beside the
    // one above as though somebody had merely not got round to it.
    {
      setting_id: "privacy:telemetry",
      metric: "privacy",
      claimed: "improved",
      reason: "what leaves the machine, which is a question about data",
      judgeable: false,
    },
  ],
  measurable_count: 1,
  gap_count: 1,
  not_judgeable_count: 1,
  required_conditions: ["a reachable host to measure against"],
};

function select(ids: string[]) {
  useStore.setState({ selectedSettingIds: new Set(ids) } as never);
}

/** A suite run carrying `count` readings of one metric, as the suite would. */
function suiteRun(label: string, value: number, count = 3) {
  return {
    label,
    started_at: 0,
    summary: `${label} run`,
    results: [
      {
        bench: "timing",
        label: "Timing",
        ran: true,
        reason: "",
        readings: {
          latency_spike_ms: {
            metric: "latency_spike_ms",
            samples: Array.from({ length: count }, () => value),
            median: value,
            noise: 0.1,
            unit: "ms",
            improves_upward: false,
          },
        },
        detail: {},
        duration_seconds: 1,
      },
      // A bench that did not run contributes nothing rather than an empty
      // metric, which would be judged as a missing pair.
      {
        bench: "presentmon",
        label: "In-game frame rate",
        ran: false,
        reason: "start a game first",
        readings: {},
        detail: {},
        duration_seconds: 0,
      },
    ],
  };
}

/** Put a measured pair where the suite would have left it. */
function measured(beforeValue = 10, afterValue = 30, count = 3) {
  useStore.setState({
    suiteBefore: suiteRun("before", beforeValue, count),
    suiteAfter: suiteRun("after", afterValue, count),
  } as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocked.sources.mockResolvedValue(SOURCES);
  mocked.coverage.mockResolvedValue(COVERAGE);
  select(["power:usb_selective_suspend"]);
  useStore.setState({ suiteBefore: null, suiteAfter: null } as never);
});

describe("VerifyPanel before anything is measured", () => {
  it("asks for a selection rather than guessing which settings changed", async () => {
    // A round's whole claim to meaning is that it knows how many things moved.
    select([]);
    render(<VerifyPanel />);

    expect(await screen.findByText(/Select the settings/i)).toBeInTheDocument();
    expect(mocked.coverage).not.toHaveBeenCalled();
  });

  it("leads with what a round could not show, not with a Run button", async () => {
    render(<VerifyPanel />);

    expect(
      await screen.findByText(/1 of 3 claims can be measured here/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/2 cannot/i)).toBeInTheDocument();
  });

  it("names what the user would have to arrange", async () => {
    render(<VerifyPanel />);

    expect(
      await screen.findByText(/a reachable host to measure against/i),
    ).toBeInTheDocument();
  });

  it("carries the reason with every claim it cannot check", async () => {
    // A coverage figure without reasons is a number nobody can act on.
    render(<VerifyPanel />);

    fireEvent.click(
      await screen.findByText(/nothing here can check yet, and why/i),
    );
    expect(
      await screen.findByText(/no sampler for working set/i),
    ).toBeInTheDocument();
  });

  it("keeps the claims no measurement settles out of the to-do list", async () => {
    // The two groups mean opposite things. A missing sampler is work a release
    // can do; "what leaves the machine" is not a stopwatch question and never
    // becomes one. Listed together, a third of the backlog is imaginary.
    render(<VerifyPanel />);

    const gaps = await screen.findByText(/nothing here can check yet, and why/i);
    const qualitative = await screen.findByText(
      /no measurement settles . real claims, not gaps/i,
    );

    expect(gaps).toHaveTextContent("1 claim");
    expect(qualitative).toHaveTextContent("1 claim");

    fireEvent.click(qualitative);
    expect(
      await screen.findByText(/what leaves the machine/i),
    ).toBeInTheDocument();
  });
});

describe("VerifyPanel readings", () => {
  it("refuses to judge until both sides have a reading", async () => {
    render(<VerifyPanel />);

    const judge = await screen.findByRole("button", {
      name: /Judge these claims/i,
    });
    expect(judge).toBeDisabled();
    expect(
      screen.getByText(/One side of a pair is not a small result/i),
    ).toBeInTheDocument();
  });

  it("sends the user to the one place that measures, rather than measuring again", async () => {
    // Verify used to collect its own before/after from two of the five
    // instruments, so one change needed two measurement passes that could
    // disagree for no reason a user could see.
    render(<VerifyPanel />);

    expect(await screen.findByText(/No measurements yet/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Take a baseline on the Measure tab/i),
    ).toBeInTheDocument();
    // And none of the old per-instrument buttons survive.
    expect(screen.queryByRole("button", { name: /^dpc/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /presentmon/i })).not.toBeInTheDocument();
  });

  it("counts what the suite actually recorded", async () => {
    measured();
    render(<VerifyPanel />);

    expect(
      await screen.findByText(/3 readings before, 3 after/i),
    ).toBeInTheDocument();
  });

  it("says why one reading per side is not enough", async () => {
    // The noise floor is the reason, and a panel that just said "take more"
    // would be asking for obedience rather than explaining a measurement.
    measured(10, 30, 1);
    render(<VerifyPanel />);

    expect(
      await screen.findByText(/Fewer than 3 readings a side/i),
    ).toBeInTheDocument();
  });

  it("ignores a bench that could not run", async () => {
    // An instrument that declined has no readings; counting it as zero would
    // read as a metric measured on one side only.
    measured();
    render(<VerifyPanel />);

    expect(await screen.findByText(/across 1 metrics/i)).toBeInTheDocument();
  });
});

describe("VerifyPanel verdicts", () => {
  const REPORT = {
    settings_changed: 1,
    summary: "0 of 1 claims verified, 1 contradicted",
    verified: 0,
    contradicted: 1,
    unverified: 1,
    verdicts: [
      {
        setting_id: "power:usb_selective_suspend",
        metric: "latency_ms",
        claimed: "-1.5",
        status: "contradicted" as const,
        reason: "moved the other way by more than noise",
        measured: {
          before: 10,
          after: 30,
          delta: 20,
          percent_change: 200,
          unit: "ms",
          noise: 0.4,
        },
      },
    ],
    notes: ["jitter_ms: measured on only one side, so it was not judged"],
  };

  async function judgeWithBothSides() {
    mocked.round.mockResolvedValue(REPORT);
    measured();
    render(<VerifyPanel />);

    const judge = await screen.findByRole("button", {
      name: /Judge these claims/i,
    });
    await waitFor(() => expect(judge).toBeEnabled());
    fireEvent.click(judge);
  }

  it("reports a contradiction as loudly as a confirmation", async () => {
    // The result that makes the whole feature worth having.
    await judgeWithBothSides();

    expect(
      await screen.findByText(/0 of 1 claims verified, 1 contradicted/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Contradicted")).toBeInTheDocument();
  });

  it("puts the verdict in text, not only in an icon's colour", async () => {
    // Colour alone fails the same a11y check that already caught row state
    // being carried by an aria-hidden tick.
    await judgeWithBothSides();

    expect(await screen.findByText("Contradicted:")).toBeInTheDocument();
  });

  it("shows the noise the change had to beat", async () => {
    // Without it, a reader cannot tell a result from a machine idling.
    await judgeWithBothSides();

    expect(await screen.findByText(/noise 0.4/i)).toBeInTheDocument();
  });

  it("keeps a metric measured on only one side visible", async () => {
    await judgeWithBothSides();

    expect(
      await screen.findByText(/measured on only one side/i),
    ).toBeInTheDocument();
  });
});

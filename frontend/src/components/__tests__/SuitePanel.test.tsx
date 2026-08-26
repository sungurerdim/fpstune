/**
 * One button, and it knows which measurement it is taking.
 *
 * Reported by the user: "the benchmark system is too complicated, there is a lot
 * here — what we need is to measure everything including before/after with one
 * press". The panel asked for three decisions before it would do anything: which
 * of five instruments, how many repeats, and which of three buttons ("measure as
 * before", "measure as after", "compare") applied right now.
 *
 * Every one of those has a right answer almost every time. These tests pin the
 * flow that follows from that — a first press takes the baseline, a second one
 * measures again *and compares without being asked*, because a second run has no
 * other purpose — and pin that the options did not disappear, only moved behind
 * a fold.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { SuitePanel } from "../SuitePanel";

const catalogue = {
  benches: [
    {
      key: "frame_pacing",
      label: "Frame pacing",
      requires: "nothing — runs on this machine",
      available: true,
      costs: "",
      in_default_run: true,
    },
    {
      key: "network_load",
      label: "Network under load",
      requires: "a working connection",
      available: true,
      costs: "downloads about 25 MB",
      in_default_run: false,
    },
  ],
  default_keys: ["frame_pacing"],
  default_repeats: 3,
  min_repeats: 2,
  max_repeats: 9,
};

const compare = vi.fn();
const run = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    suiteApi: {
      catalogue: () => Promise.resolve(catalogue),
      run: (...args: unknown[]) => run(...args),
      compare: (...args: unknown[]) => compare(...args),
    },
  };
});

/** Drive the SSE callback the way the real stream would, to completion. */
function completeRun(label: string) {
  return (
    _request: unknown,
    onEvent: (event: Record<string, unknown>) => void,
    onDone: () => void,
  ) => {
    onEvent({ event: "started", label });
    onEvent({ event: "running", bench: "frame_pacing", label: "Frame pacing" });
    onEvent({ event: "measured", progress: 100 });
    onEvent({
      event: "done",
      run: { label, summary: `${label} run: 1 instrument`, results: [] },
    });
    onDone();
    return () => {};
  };
}

describe("SuitePanel", () => {
  beforeEach(() => {
    run.mockReset();
    compare.mockReset();
    compare.mockResolvedValue({ summary: "nothing moved", measurements: [], unpaired: [] });
  });

  it("opens with one button and no decisions to make", async () => {
    render(<SuitePanel />);

    expect(await screen.findByRole("button", { name: /measure this machine/i })).toBeInTheDocument();
    // The three-button flow, gone.
    expect(screen.queryByRole("button", { name: /measure as/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^compare$/i })).not.toBeInTheDocument();
  });

  it("keeps the instrument list, one fold away", async () => {
    render(<SuitePanel />);
    await screen.findByRole("button", { name: /measure this machine/i });

    // Not on screen by default...
    expect(screen.queryByText("Network under load")).not.toBeInTheDocument();
    // ...but the count says what the button will run.
    expect(screen.getByText(/1 of 2 instruments · 3 repeats/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /which instruments/i }));
    expect(screen.getByText("Network under load")).toBeInTheDocument();
    expect(screen.getByText("downloads about 25 MB")).toBeInTheDocument();
  });

  it("takes the baseline on the first press", async () => {
    run.mockImplementation(completeRun("before"));
    render(<SuitePanel />);

    await userEvent.click(await screen.findByRole("button", { name: /measure this machine/i }));

    expect(run).toHaveBeenCalledTimes(1);
    expect(run.mock.calls[0][0]).toMatchObject({ label: "before", repeats: 3 });
    expect(await screen.findByText(/before run: 1 instrument/)).toBeInTheDocument();
  });

  it("compares on the second press without being asked", async () => {
    run.mockImplementation(completeRun("before"));
    render(<SuitePanel />);
    await userEvent.click(await screen.findByRole("button", { name: /measure this machine/i }));

    run.mockImplementation(completeRun("after"));
    await userEvent.click(
      await screen.findByRole("button", { name: /measure again and compare/i }),
    );

    await waitFor(() => expect(compare).toHaveBeenCalledTimes(1));
    expect(run.mock.calls[1][0]).toMatchObject({ label: "after" });
    expect(await screen.findByText("nothing moved")).toBeInTheDocument();
  });

  it("says what the next press is for, once a baseline exists", async () => {
    run.mockImplementation(completeRun("before"));
    render(<SuitePanel />);
    await userEvent.click(await screen.findByRole("button", { name: /measure this machine/i }));

    expect(
      await screen.findByText(/Apply the tweaks you want, then press again/i),
    ).toBeInTheDocument();
  });

  it("can throw the baseline away and start again", async () => {
    run.mockImplementation(completeRun("before"));
    render(<SuitePanel />);
    await userEvent.click(await screen.findByRole("button", { name: /measure this machine/i }));

    await userEvent.click(await screen.findByRole("button", { name: /start over/i }));

    expect(
      await screen.findByRole("button", { name: /measure this machine/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/before run: 1 instrument/)).not.toBeInTheDocument();
  });
});

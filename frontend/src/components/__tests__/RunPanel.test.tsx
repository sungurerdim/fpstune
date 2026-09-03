/**
 * What a long run tells the user while it runs.
 *
 * A DISM repair takes half an hour, and until this panel existed it was one
 * spinner for all of it — no name, no command, no progress, and no way to tell
 * it from a wedged one. These tests hold the four things a row must carry, and
 * the one thing it must never invent.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RunPanel } from "../RunPanel";
import { useStore, type RunStep } from "../../store";

function step(overrides: Partial<RunStep> = {}): RunStep {
  return {
    id: "maintenance:dism_health",
    name: "DISM Health Check",
    status: "running",
    command: "Dism.exe /online /Cleanup-Image /RestoreHealth",
    percent: null,
    reportsProgress: false,
    durationEstimate: "",
    lines: [],
    startedAt: Date.now(),
    endedAt: null,
    ...overrides,
  };
}

describe("RunPanel", () => {
  beforeEach(() => {
    useStore.setState({ runSteps: [], cleanupResults: {} });
  });

  it("renders nothing before anything has been run", () => {
    const { container } = render(<RunPanel />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the command that is actually running, verbatim", () => {
    useStore.setState({ runSteps: [step()] });

    render(<RunPanel />);

    // Not a paraphrase: this is the record of what fpstune ran on the machine.
    expect(
      screen.getByText("Dism.exe /online /Cleanup-Image /RestoreHealth"),
    ).toBeInTheDocument();
  });

  it("draws a bar from the percentage the command printed", () => {
    useStore.setState({
      runSteps: [step({ percent: 42, reportsProgress: true })],
    });

    render(<RunPanel />);

    const bar = screen.getByRole("progressbar", {
      name: /DISM Health Check/,
    });
    expect(bar).toHaveAttribute("aria-valuenow", "42");
  });

  it("draws no bar for a command that reports no percentage (C11)", () => {
    // A folder delete prints no progress. Elapsed time is shown instead of a
    // number nothing measured.
    useStore.setState({
      runSteps: [step({ name: "Temp Files", percent: null })],
    });

    render(<RunPanel />);

    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("shows the latest output line as the current stage", () => {
    useStore.setState({
      runSteps: [
        step({
          lines: ["Version: 10.0.26200.1", "The operation is 42% complete"],
        }),
      ],
    });

    render(<RunPanel />);

    expect(screen.getByText("The operation is 42% complete")).toBeInTheDocument();
    // The earlier lines are the log, not the headline: they are behind the toggle.
    expect(screen.queryByText("Version: 10.0.26200.1")).not.toBeInTheDocument();
  });

  it("keeps the whole output one keystroke away", async () => {
    useStore.setState({
      runSteps: [step({ lines: ["Version: 10.0.26200.1", "Working"] })],
    });

    render(<RunPanel />);
    await userEvent.click(screen.getByRole("button", { expanded: false }));

    expect(screen.getByText(/Version: 10\.0\.26200\.1/)).toBeInTheDocument();
  });

  it("counts what has finished against what was selected", () => {
    useStore.setState({
      runSteps: [
        step({ id: "cleanup:temp_files", name: "Temp Files", status: "done" }),
        step({ id: "cleanup:prefetch", name: "Prefetch", status: "running" }),
        step({ id: "cleanup:wer_reports", name: "WER", status: "queued" }),
      ],
    });

    render(<RunPanel />);

    // A count of finished steps is a fact; a percentage across steps of unknown
    // length would not be.
    expect(screen.getByText("1 / 3 operations")).toBeInTheDocument();
  });

  it("shows the freed figure the cleanup bookkeeping produced", () => {
    useStore.setState({
      runSteps: [
        step({ id: "cleanup:temp_files", name: "Temp Files", status: "done" }),
      ],
      cleanupResults: {
        "cleanup:temp_files": {
          id: "cleanup:temp_files",
          name: "Temp Files",
          success: true,
          sized: true,
          freedMB: 2048,
        },
      },
    });

    render(<RunPanel />);

    expect(screen.getByText("Freed 2.0 GB")).toBeInTheDocument();
  });

  it("names the failure on the row that failed", () => {
    useStore.setState({
      runSteps: [
        step({
          status: "failed",
          error: "PowerShell command timed out after 300s",
        }),
      ],
    });

    render(<RunPanel />);

    expect(
      screen.getByText("PowerShell command timed out after 300s"),
    ).toBeInTheDocument();
  });
});

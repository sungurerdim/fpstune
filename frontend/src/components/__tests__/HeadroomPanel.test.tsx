/**
 * The panel that has to survive not having a measurement.
 *
 * A frame rate cannot be measured with nothing rendering, so the state this
 * component spends most of its life in is "nothing to show yet" — and that is
 * exactly the state a normal empty-state panel gets wrong. The guards here are
 * the three ways it could lie:
 *
 * *Hiding the games it has not measured*, which turns the list into "the games
 * that exist" and leaves the button meaningless.
 *
 * *Blanking a reading because the newest attempt declined.* The game being
 * closed is a reason, not an erasure, and the old number plus the reason is
 * strictly more information than neither.
 *
 * *Showing a frame rate without what it permits.* The number decides whether a
 * sharper image is on offer; printed bare, it invites the opposite reading.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "../../test/utils";
import { HeadroomPanel } from "../HeadroomPanel";
import { headroomApi } from "../../lib/api";
import type { GameHeadroom } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  headroomApi: {
    list: vi.fn(),
    measure: vi.fn(),
  },
}));

const mocked = vi.mocked(headroomApi);

function game(overrides: Partial<GameHeadroom> = {}): GameHeadroom {
  return {
    game: "mw4",
    label: "Modern Warfare IV",
    is_running: false,
    is_measured: false,
    measured_fps: null,
    fps_1_percent_low: null,
    target_fps: null,
    achievement_percent: null,
    tier: "unknown",
    bottleneck: "unknown",
    cpu_busy_ms: null,
    gpu_time_ms: null,
    input_latency_ms: null,
    present_mode: null,
    measured_at: null,
    ...overrides,
  };
}

/** The measured case this feature came from: 57.4 fps on a 300 Hz panel. */
const MEASURED = game({
  is_measured: true,
  is_running: true,
  measured_fps: 57.4,
  fps_1_percent_low: 36.4,
  target_fps: 297,
  achievement_percent: 19,
  tier: "critical",
  bottleneck: "both",
  measured_at: Date.now() / 1000 - 120,
});

beforeEach(() => {
  vi.clearAllMocks();
  mocked.list.mockResolvedValue({
    poll_interval_seconds: 60,
    games: [game(), game({ game: "mw3", label: "Modern Warfare III" })],
  });
});

describe("HeadroomPanel before anything is measured", () => {
  it("lists the games it has not measured rather than showing an empty panel", async () => {
    render(<HeadroomPanel />);

    expect(await screen.findByText("Modern Warfare IV")).toBeInTheDocument();
    expect(screen.getByText("Modern Warfare III")).toBeInTheDocument();
  });

  it("says why nothing that costs frames will be recommended", async () => {
    render(<HeadroomPanel />);

    expect(
      await screen.findAllByText(/silence is not evidence/i),
    ).not.toHaveLength(0);
  });

  it("tells the user what a measurement needs", async () => {
    render(<HeadroomPanel />);

    expect(
      await screen.findByText(/needs something rendering to measure/i),
    ).toBeInTheDocument();
  });
});

describe("HeadroomPanel with a measurement", () => {
  beforeEach(() => {
    mocked.list.mockResolvedValue({
      poll_interval_seconds: 60,
      games: [MEASURED],
    });
  });

  it("shows the frame rate against what the display could have shown", async () => {
    render(<HeadroomPanel />);

    expect(await screen.findByText("57.4")).toBeInTheDocument();
    expect(screen.getByText(/297 fps target/)).toBeInTheDocument();
    expect(screen.getByText(/19%/)).toBeInTheDocument();
  });

  it("draws the ratio as a gauge, so 19% and 97% cannot look alike (E5)", async () => {
    render(<HeadroomPanel />);

    const gauge = await screen.findByRole("meter", {
      name: /measured frame rate against the display's 297 fps target/,
    });
    expect(gauge).toHaveAttribute("aria-valuenow", "57.4");
    expect(gauge).toHaveAttribute("aria-valuemax", "297");
  });

  it("never prints the number without what it permits", async () => {
    render(<HeadroomPanel />);

    expect(await screen.findByText("Far short")).toBeInTheDocument();
    expect(
      screen.getByText(/a sharper image is not on offer/i),
    ).toBeInTheDocument();
  });

  it("says which side the frame waited on, because it changes what is worth doing", async () => {
    render(<HeadroomPanel />);

    expect(
      await screen.findByText(/graphics settings alone will not close the gap/i),
    ).toBeInTheDocument();
  });

  it("reports the 1% low next to the average rather than instead of it", async () => {
    render(<HeadroomPanel />);

    expect(await screen.findByText(/36.4 at the 1% low/)).toBeInTheDocument();
  });

  it("shows PresentMon's present mode verbatim, as a fact and not a score", async () => {
    mocked.list.mockResolvedValue({
      poll_interval_seconds: 60,
      games: [game({ ...MEASURED, present_mode: "Hardware: Independent Flip" })],
    });
    render(<HeadroomPanel />);

    expect(
      await screen.findByText("Present mode: Hardware: Independent Flip"),
    ).toBeInTheDocument();
  });

  it("says nothing about the present mode when the capture had none", async () => {
    render(<HeadroomPanel />);

    await screen.findByText("57.4");
    expect(screen.queryByText(/Present mode/)).not.toBeInTheDocument();
  });
});

describe("HeadroomPanel measuring on demand", () => {
  it("asks the backend which game is running rather than making the user say", async () => {
    mocked.measure.mockResolvedValue({
      measured: true,
      outcome: "measured",
      detail: "Modern Warfare IV measured against this panel's 297 fps target",
      game: "mw4",
      headroom: MEASURED,
    });

    render(<HeadroomPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /measure now/i }));

    await waitFor(() => expect(mocked.measure).toHaveBeenCalledWith());
  });

  it("shows the reason a measurement declined instead of an error", async () => {
    mocked.measure.mockResolvedValue({
      measured: false,
      outcome: "no_game_running",
      detail:
        "No game fpstune knows is running. Start one and measure again — a frame rate needs something rendering.",
      game: null,
      headroom: null,
    });

    render(<HeadroomPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /measure now/i }));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(/Start one and measure again/);
  });

  it("keeps the last reading on screen when the newest attempt declines", async () => {
    mocked.list.mockResolvedValue({
      poll_interval_seconds: 60,
      games: [MEASURED],
    });
    mocked.measure.mockResolvedValue({
      measured: false,
      outcome: "presentmon_missing",
      detail: "PresentMon is not installed.",
      game: "mw4",
      headroom: MEASURED,
    });

    render(<HeadroomPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /measure now/i }));

    await screen.findByRole("status");
    expect(screen.getByText("57.4")).toBeInTheDocument();
  });
});

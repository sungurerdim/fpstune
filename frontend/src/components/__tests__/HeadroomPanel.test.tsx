/**
 * The panel that has to survive not having a measurement.
 *
 * Until the fixed scene landed, a frame rate could only be measured while a
 * game was rendering, so the state this component spent most of its life in was
 * "nothing to show yet" — and that is exactly the state a normal empty-state
 * panel gets wrong. The scene makes a first reading reachable from this screen,
 * but not free: it is a 1.3 GB one-time download, so the empty state still has
 * to be honest about what pressing the button involves.
 *
 * The guards here are the four ways it could lie:
 *
 * *Showing nothing at all before the first run*, which leaves the button with
 * no explanation of what it will do.
 *
 * *Hiding the download*, which turns a one-time 1.3 GB decision into a surprise
 * taken on the user's behalf.
 *
 * *Blanking a reading because the newest attempt declined.* A game being open
 * is a reason, not an erasure, and the old number plus the reason is strictly
 * more information than neither.
 *
 * *Showing a frame rate without what it permits.* The number decides whether a
 * sharper image is on offer; printed bare, it invites the opposite reading.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "../../test/utils";
import { HeadroomPanel } from "../HeadroomPanel";
import { gpuSceneApi, headroomApi } from "../../lib/api";
import type { MachineHeadroom } from "../../lib/api";
import { useStore } from "../../store";

vi.mock("../../lib/api", () => ({
  headroomApi: {
    list: vi.fn(),
    measure: vi.fn(),
  },
  gpuSceneApi: {
    status: vi.fn(),
    install: vi.fn(),
  },
}));

const mocked = vi.mocked(headroomApi);
const mockedGpuScene = vi.mocked(gpuSceneApi);

function reading(overrides: Partial<MachineHeadroom> = {}): MachineHeadroom {
  return {
    is_measured: false,
    measured_fps: null,
    fps_1_percent_low: null,
    target_fps: null,
    achievement_percent: null,
    tier: "unknown",
    bottleneck: "unknown",
    present_mode: null,
    width: null,
    height: null,
    measured_at: null,
    ...overrides,
  };
}

/** The live product run of 2026-09-11: fps_avg median 197 on a 297 fps target. */
const MEASURED = reading({
  is_measured: true,
  measured_fps: 197.0,
  fps_1_percent_low: 120.4,
  target_fps: 297,
  achievement_percent: 66,
  tier: "short",
  bottleneck: "gpu",
  width: 2560,
  height: 1440,
  measured_at: Date.now() / 1000 - 120,
});

beforeEach(() => {
  vi.clearAllMocks();
  useStore.setState({ notifications: [] });
  mocked.list.mockResolvedValue({ headroom: reading() });
  mockedGpuScene.status.mockResolvedValue({
    installed: false,
    download_size: "1.3 GB",
    licence_note:
      "Unigine Superposition Basic, downloaded from Unigine's own server for personal, non-commercial use under its own licence; fpstune bundles none of it and modifies nothing.",
  });
});

describe("HeadroomPanel before anything is measured", () => {
  it("says why nothing that costs frames will be recommended", async () => {
    render(<HeadroomPanel />);

    expect(
      await screen.findAllByText(/silence is not evidence/i),
    ).not.toHaveLength(0);
  });

  it("says the scene takes the measurement, not a game the user has to start", async () => {
    render(<HeadroomPanel />);

    expect(
      await screen.findByText(/renders a fixed test scene when the machine is idle/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/start a game/i)).not.toBeInTheDocument();
  });

  it("says what installing the scene costs before the button is pressed", async () => {
    render(<HeadroomPanel />);

    expect(await screen.findByText(/1\.3 GB one-time download/i)).toBeInTheDocument();
  });

  it("shows the install button and the licence sentence once the scene is confirmed missing", async () => {
    render(<HeadroomPanel />);

    expect(
      await screen.findByRole("button", { name: /install the scene \(1\.3 gb download\)/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/downloaded from unigine's own server/i),
    ).toBeInTheDocument();
  });

  it("never shows the install button once the scene is already installed", async () => {
    mockedGpuScene.status.mockResolvedValue({
      installed: true,
      download_size: "1.3 GB",
      licence_note: "Unigine Superposition Basic, downloaded from Unigine's own server.",
    });

    render(<HeadroomPanel />);

    await screen.findByText(/1\.3 GB one-time download/i);
    expect(
      screen.queryByRole("button", { name: /install the scene/i }),
    ).not.toBeInTheDocument();
  });
});

describe("HeadroomPanel installing the scene", () => {
  it("downloads and installs on the user's own press, then re-fetches the reading", async () => {
    let resolveInstall!: (value: { installed: boolean; reason: string }) => void;
    mockedGpuScene.install.mockReturnValue(
      new Promise((resolve) => {
        resolveInstall = resolve;
      }),
    );
    mocked.list
      .mockResolvedValueOnce({ headroom: reading() })
      .mockResolvedValue({ headroom: MEASURED });

    render(<HeadroomPanel />);
    const button = await screen.findByRole("button", {
      name: /install the scene \(1\.3 gb download\)/i,
    });
    fireEvent.click(button);

    expect(await screen.findByText(/installing the scene/i)).toBeInTheDocument();
    expect(button).toBeDisabled();
    await waitFor(() => expect(mockedGpuScene.install).toHaveBeenCalledWith());

    resolveInstall({ installed: true, reason: "" });

    await waitFor(() => expect(mocked.list).toHaveBeenCalledTimes(2));
    expect(useStore.getState().notifications).toHaveLength(0);
  });

  it("is refused while another fpstune operation holds the machine, and reports it as a notification rather than silently failing", async () => {
    mockedGpuScene.install.mockRejectedValue(
      new Error(
        "API error: 409 Conflict - Another fpstune operation is running; the 1.3 GB install waits until it is done.",
      ),
    );

    render(<HeadroomPanel />);
    const button = await screen.findByRole("button", {
      name: /install the scene \(1\.3 gb download\)/i,
    });
    fireEvent.click(button);

    await waitFor(() => expect(mockedGpuScene.install).toHaveBeenCalled());
    await waitFor(() =>
      expect(useStore.getState().notifications.some((n) => n.type === "error")).toBe(true),
    );
    expect(useStore.getState().notifications[0].message).toMatch(
      /1\.3 GB install waits until it is done/,
    );
    // The button must be usable again, not stuck disabled after a refusal.
    expect(button).not.toBeDisabled();
  });
});

describe("HeadroomPanel with a measurement", () => {
  beforeEach(() => {
    mocked.list.mockResolvedValue({ headroom: MEASURED });
  });

  it("shows the frame rate against what the display could have shown", async () => {
    render(<HeadroomPanel />);

    expect(await screen.findByText("197.0")).toBeInTheDocument();
    expect(screen.getByText(/297 fps target/)).toBeInTheDocument();
    expect(screen.getByText(/66%/)).toBeInTheDocument();
  });

  it("draws the ratio as a gauge, so 19% and 97% cannot look alike (E5)", async () => {
    render(<HeadroomPanel />);

    const gauge = await screen.findByRole("meter", {
      name: /measured frame rate against the display's 297 fps target/i,
    });
    expect(gauge).toHaveAttribute("aria-valuenow", "197");
    expect(gauge).toHaveAttribute("aria-valuemax", "297");
  });

  it("never prints the number without what it permits", async () => {
    render(<HeadroomPanel />);

    expect(await screen.findByText("Short")).toBeInTheDocument();
    expect(
      screen.getByText(/anything the player needs to see is not/i),
    ).toBeInTheDocument();
  });

  it("says which side the frame waited on, because it changes what is worth doing", async () => {
    render(<HeadroomPanel />);

    expect(
      await screen.findByText(/graphics settings are where the frames are/i),
    ).toBeInTheDocument();
  });

  it("says nothing about a side the run never established", async () => {
    mocked.list.mockResolvedValue({
      headroom: { ...MEASURED, bottleneck: "unknown" },
    });
    render(<HeadroomPanel />);

    await screen.findByText("197.0");
    expect(screen.queryByText(/-bound/i)).not.toBeInTheDocument();
  });

  it("reports the 1% low next to the average rather than instead of it", async () => {
    render(<HeadroomPanel />);

    expect(await screen.findByText(/120.4 at the 1% low/)).toBeInTheDocument();
  });

  it("says the scene rendered at this panel's own resolution", async () => {
    /* The band compares a frame rate to this display's ceiling, so a reading
       taken in a smaller window would be a different machine's answer. */
    render(<HeadroomPanel />);

    expect(
      await screen.findByText(/2560×1440, this display's own resolution/),
    ).toBeInTheDocument();
  });

  it("shows PresentMon's present mode verbatim, as a fact and not a score", async () => {
    mocked.list.mockResolvedValue({
      headroom: { ...MEASURED, present_mode: "Composed: Copy with GPU GDI" },
    });
    render(<HeadroomPanel />);

    expect(
      await screen.findByText("Present mode: Composed: Copy with GPU GDI"),
    ).toBeInTheDocument();
  });

  it("says nothing about the present mode when the capture had none", async () => {
    render(<HeadroomPanel />);

    await screen.findByText("197.0");
    expect(screen.queryByText(/Present mode/)).not.toBeInTheDocument();
  });

  it("drops the download notice once the scene has produced a number", async () => {
    render(<HeadroomPanel />);

    await screen.findByText("197.0");
    expect(screen.queryByText(/1\.3 GB/)).not.toBeInTheDocument();
  });
});

describe("HeadroomPanel measuring on demand", () => {
  it("asks the backend to run the scene, with nothing for the user to pick", async () => {
    mocked.measure.mockResolvedValue({
      measured: true,
      outcome: "measured",
      detail: "This machine measured against the panel's 297 fps target",
      headroom: MEASURED,
    });

    render(<HeadroomPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /measure now/i }));

    await waitFor(() => expect(mocked.measure).toHaveBeenCalledWith());
  });

  it("shows the reason a measurement declined instead of an error", async () => {
    mocked.measure.mockResolvedValue({
      measured: false,
      outcome: "scene_unavailable",
      detail:
        "Modern Warfare IV is running. The scene renders at full speed and would take the card away from the game, so it waits until you are done.",
      headroom: reading(),
    });

    render(<HeadroomPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /measure now/i }));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(/waits until you are done/);
  });

  it("keeps the last reading on screen when the newest attempt declines", async () => {
    mocked.list.mockResolvedValue({ headroom: MEASURED });
    mocked.measure.mockResolvedValue({
      measured: false,
      outcome: "measure_failed",
      detail: "The scene engine would not start.",
      headroom: MEASURED,
    });

    render(<HeadroomPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /measure now/i }));

    await screen.findByRole("status");
    expect(screen.getByText("197.0")).toBeInTheDocument();
  });
});

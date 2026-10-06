/**
 * The audio switches used to be named after the action they would perform next
 * ("Disable device" / "Enable device"). With role="switch" that is wrong twice
 * over: the on/off fact already travels in aria-checked, and a name that flips
 * with the state means the control a screen-reader user just toggled is no
 * longer findable under the name it had a moment ago — every toggle turned it
 * into a different control. The name must be the stable subject of the switch,
 * which for these rows is the device the backend reported.
 */

import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "../../test/utils";
import { AudioSection } from "../hardware/AudioSection";
import { api, type AudioDeviceInfo } from "../../lib/api";
import { hardwareManager } from "../../lib/hardware-manager";
import { useStore } from "../../store";

vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: { refreshAudioDevices: vi.fn().mockResolvedValue([]) },
}));


function device(overrides: Partial<AudioDeviceInfo> = {}): AudioDeviceInfo {
  return {
    id: "{0.0.0.00000000}.{9f0aa154-2c14-4bd0-a1b0-000000000000}",
    name: "Speakers (High Definition Audio)",
    device_type: "Playback",
    is_default: true,
    is_enabled: true,
    loudness_eq_supported: true,
    loudness_eq_enabled: false,
    ...overrides,
  };
}

describe("the device switch is named after the device", () => {
  it("is findable by the device's own name", () => {
    render(<AudioSection devices={[device()]} loading={false} />);

    // Role AND name: getByRole("switch") alone passed on the version whose
    // name was the action.
    expect(
      screen.getByRole("switch", { name: "Speakers (High Definition Audio)" }),
    ).toBeInTheDocument();
  });

  it("keeps the same name across a state flip; only aria-checked moves", () => {
    const { rerender } = render(
      <AudioSection devices={[device({ is_enabled: true })]} loading={false} />,
    );

    const name = "Speakers (High Definition Audio)";
    expect(screen.getByRole("switch", { name })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    rerender(
      <AudioSection devices={[device({ is_enabled: false })]} loading={false} />,
    );

    expect(screen.getByRole("switch", { name })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });
});

describe("a truncated device name stays readable", () => {
  it("carries the full name as its title, since the visible text is clipped", () => {
    // 390px clips the row to "SteelSeries Sonar - Chat …" with an ellipsis and
    // no way to see which of the Sonar mixes it is.
    const name = "SteelSeries Sonar - Chat (SteelSeries Sonar Virtual Audio Device)";
    render(<AudioSection devices={[device({ name })]} loading={false} />);

    const label = screen.getAllByText(name).find((el) => el.classList.contains("truncate"));
    expect(label).toBeDefined();
    expect(label).toHaveAttribute("title", name);
    // `min-w-0` is what lets a flex child shrink below its text so that
    // `truncate` has something to clip; without it the row overflows instead.
    expect(label).toHaveClass("min-w-0");
  });
});

describe("the Loudness EQ switch is named by its visible label", () => {
  it("keeps 'Loudness EQ' as its name while aria-checked flips", () => {
    const { rerender } = render(
      <AudioSection
        devices={[device({ loudness_eq_enabled: false })]}
        loading={false}
      />,
    );

    expect(screen.getByRole("switch", { name: "Loudness EQ" })).toHaveAttribute(
      "aria-checked",
      "false",
    );

    rerender(
      <AudioSection
        devices={[device({ loudness_eq_enabled: true })]}
        loading={false}
      />,
    );

    expect(screen.getByRole("switch", { name: "Loudness EQ" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });
});

describe("a Loudness EQ change says when it is heard", () => {
  it("tells the user a playing app hears it after a restart", async () => {
    // Windows reads the switch when a stream opens. Without this, a toggle that
    // worked reads as "nothing happened" to someone with music already playing.
    useStore.setState({ notifications: [] });
    vi.spyOn(api, "setLoudnessEq").mockResolvedValue({
      success: true,
    } as Awaited<ReturnType<typeof api.setLoudnessEq>>);
    render(<AudioSection devices={[device()]} loading={false} />);

    fireEvent.click(screen.getByRole("switch", { name: "Loudness EQ" }));

    await waitFor(() =>
      expect(
        useStore
          .getState()
          .notifications.some(
            (n) => n.type === "info" && /when its app restarts/.test(n.message),
          ),
      ).toBe(true),
    );
  });

  it("re-reads the device after a refused write so the switch shows the truth", async () => {
    vi.mocked(hardwareManager.refreshAudioDevices).mockClear();
    vi.spyOn(api, "setLoudnessEq").mockRejectedValue(new Error("refused"));
    render(<AudioSection devices={[device()]} loading={false} />);

    fireEvent.click(screen.getByRole("switch", { name: "Loudness EQ" }));

    await waitFor(() => expect(hardwareManager.refreshAudioDevices).toHaveBeenCalled());
  });
});

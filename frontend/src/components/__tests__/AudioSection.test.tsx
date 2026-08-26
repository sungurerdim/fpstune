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
import { render, screen } from "../../test/utils";
import { AudioSection } from "../hardware/AudioSection";
import type { AudioDeviceInfo } from "../../lib/api";

vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: { refreshAudioDevices: vi.fn().mockResolvedValue([]) },
}));

// The section-level tweak list reads the store; these tests are about the
// device switches, so it stays out of the tree.
vi.mock("../hardware/DeviceTweakList", () => ({
  DeviceTweakList: () => null,
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

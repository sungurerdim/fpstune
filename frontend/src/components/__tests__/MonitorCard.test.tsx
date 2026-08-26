/**
 * A monitor running below its native mode must be fixable, not just described.
 *
 * The panel detected the state and rendered "120Hz -> 300Hz" in amber, and nothing
 * anywhere could act on it. Three things pointed at each other:
 *   - registry.py: display settings are "handled in Hardware panel"
 *   - HardwarePanel.tsx: display optimization is "managed in Optimizations tab"
 *   - `_discover_display_settings()` was commented out
 * while POST /display/{index}/auto and `api.setDisplayToAuto` both existed with no
 * caller. Telling a user something is wrong with no way to fix it is worse than
 * saying nothing.
 *
 * These tests cannot be replaced by looking at the running app: the dev machine is
 * now at its native 300Hz, so the affordance correctly does not render there.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { MonitorCard } from "../hardware/MonitorCard";
import { api } from "../../lib/api";
import type { MonitorInfo } from "../../lib/api";

vi.mock("../../lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  api: { setDisplayToAuto: vi.fn().mockResolvedValue({ success: true }) },
}));

vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: { refreshMonitors: vi.fn().mockResolvedValue([]) },
}));

/** A 300 Hz panel that Windows is driving at 120 Hz — the dev machine's real state. */
function monitor(overrides: Partial<MonitorInfo> = {}): MonitorInfo {
  return {
    name: "DISPLAY13",
    friendly_name: "AW2725DF",
    width: 2560,
    height: 1440,
    refresh_rate_hz: 120,
    native_width: 2560,
    native_height: 1440,
    native_refresh_rate_hz: 300,
    max_refresh_rate_hz: 300,
    is_primary: true,
    is_active: true,
    is_resolution_known: true,
    is_refresh_known: true,
    is_resolution_optimal: true,
    is_refresh_optimal: false,
    supports_vrr: true,
    ...overrides,
  } as MonitorInfo;
}

const nativeButton = () => screen.queryByRole("button", { name: /native mode/i });

describe("MonitorCard native-mode affordance", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("offers the fix when the refresh rate is below native", () => {
    render(<MonitorCard monitor={monitor()} displayIndex={0} />);
    expect(nativeButton()).toBeInTheDocument();
  });

  it("still shows what is wrong alongside the fix", () => {
    render(<MonitorCard monitor={monitor()} displayIndex={0} />);
    expect(screen.getByText("120Hz")).toBeInTheDocument();
    expect(screen.getByText("300Hz")).toBeInTheDocument();
  });

  it("applies to the display it is rendered for, not display 0", async () => {
    render(<MonitorCard monitor={monitor()} displayIndex={2} />);
    await userEvent.click(nativeButton()!);
    await waitFor(() => expect(api.setDisplayToAuto).toHaveBeenCalledWith(2));
  });

  it("does not offer a fix when the display is already at native", () => {
    render(
      <MonitorCard
        monitor={monitor({ refresh_rate_hz: 300, is_refresh_optimal: true })}
        displayIndex={0}
      />,
    );
    expect(nativeButton()).not.toBeInTheDocument();
  });

  it("offers the fix when only the resolution is below native", () => {
    render(
      <MonitorCard
        monitor={monitor({
          refresh_rate_hz: 300,
          is_refresh_optimal: true,
          width: 1920,
          height: 1080,
          is_resolution_optimal: false,
        })}
        displayIndex={0}
      />,
    );
    expect(nativeButton()).toBeInTheDocument();
  });

  it("stays quiet on a disconnected display", () => {
    // Nothing read from a dark output can be trusted, so offering to "fix" it
    // would act on values that mean nothing.
    render(
      <MonitorCard monitor={monitor({ is_active: false })} displayIndex={0} />,
    );
    expect(nativeButton()).not.toBeInTheDocument();
  });

  it("stays quiet when the refresh rate could not be read", () => {
    render(
      <MonitorCard
        monitor={monitor({ is_refresh_known: false, is_resolution_optimal: true })}
        displayIndex={0}
      />,
    );
    expect(nativeButton()).not.toBeInTheDocument();
  });
});

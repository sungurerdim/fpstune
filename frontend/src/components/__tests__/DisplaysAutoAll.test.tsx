/**
 * Fixing every display below native should be one action, not one per card.
 *
 * And the two controls have to agree: the per-card button and this one share
 * `isDisplaySuboptimal`, because two copies of that predicate would eventually
 * disagree and one control would then offer a fix the other calls unnecessary —
 * the same shape as a detect that observes less than its apply writes.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "../../test/utils";
import userEvent from "@testing-library/user-event";
import { DisplaysAutoAllButton } from "../hardware/MonitorCard";
import { isDisplaySuboptimal } from "../../lib/displayStatus";
import { api } from "../../lib/api";
import type { MonitorInfo } from "../../lib/api";

vi.mock("../../lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  api: { setDisplayToAuto: vi.fn().mockResolvedValue({ success: true }) },
}));

vi.mock("../../lib/hardware-manager", () => ({
  hardwareManager: { refreshMonitors: vi.fn().mockResolvedValue([]) },
}));

function display(overrides: Partial<MonitorInfo> = {}): MonitorInfo {
  return {
    name: "DISPLAY1",
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

const optimal = () => display({ refresh_rate_hz: 300, is_refresh_optimal: true });
const allButton = () => screen.queryByRole("button", { name: /all \d+ displays/i });

describe("DisplaysAutoAllButton", () => {
  beforeEach(() => vi.clearAllMocks());

  it("stays hidden for a single display, whose own card already offers the fix", () => {
    render(<DisplaysAutoAllButton monitors={[display()]} />);
    expect(allButton()).not.toBeInTheDocument();
  });

  it("stays hidden when only one of several displays needs fixing", () => {
    render(<DisplaysAutoAllButton monitors={[display(), optimal(), optimal()]} />);
    expect(allButton()).not.toBeInTheDocument();
  });

  it("appears when two or more displays are below native, and says how many", () => {
    render(<DisplaysAutoAllButton monitors={[display(), display(), optimal()]} />);
    expect(screen.getByRole("button", { name: /all 2 displays/i })).toBeInTheDocument();
  });

  it("applies to exactly the displays that need it, by their real index", async () => {
    render(
      <DisplaysAutoAllButton monitors={[optimal(), display(), display(), optimal()]} />,
    );
    await userEvent.click(allButton()!);

    await waitFor(() => expect(api.setDisplayToAuto).toHaveBeenCalledTimes(2));
    expect(api.setDisplayToAuto).toHaveBeenCalledWith(1);
    expect(api.setDisplayToAuto).toHaveBeenCalledWith(2);
    expect(api.setDisplayToAuto).not.toHaveBeenCalledWith(0);
    expect(api.setDisplayToAuto).not.toHaveBeenCalledWith(3);
  });

  it("ignores displays whose values could not be read", () => {
    // A disconnected output and an unreadable mode are not problems to fix; acting
    // on them would apply values that mean nothing.
    render(
      <DisplaysAutoAllButton
        monitors={[
          display({ is_active: false }),
          display({ is_refresh_known: false }),
          display(),
        ]}
      />,
    );
    expect(allButton()).not.toBeInTheDocument();
  });
});

describe("isDisplaySuboptimal", () => {
  it("is true when the refresh rate is below native", () => {
    expect(isDisplaySuboptimal(display())).toBe(true);
  });

  it("is true when only the resolution is below native", () => {
    expect(
      isDisplaySuboptimal(
        display({
          refresh_rate_hz: 300,
          is_refresh_optimal: true,
          width: 1920,
          height: 1080,
          is_resolution_optimal: false,
        }),
      ),
    ).toBe(true);
  });

  it("is false for a display already at native", () => {
    expect(isDisplaySuboptimal(optimal())).toBe(false);
  });

  it("is false for a disconnected display", () => {
    expect(isDisplaySuboptimal(display({ is_active: false }))).toBe(false);
  });

  it("is false when the reading is unknown, even if the flag says suboptimal", () => {
    expect(isDisplaySuboptimal(display({ is_refresh_known: false }))).toBe(false);
  });
});

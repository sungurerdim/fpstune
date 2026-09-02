/**
 * Returning to the window may re-read hardware. It may not flood the machine.
 *
 * From a real log, during a two-minute DISM cleanup:
 *
 *   POST /api/audio/refresh   -> 200 (1409ms)
 *   POST /api/display/refresh -> 200 (1164ms)
 *   POST /api/network/refresh -> 200 (6106ms)
 *   POST /api/audio/refresh   -> 200 (3160ms)
 *   ... and again, and again
 *
 * Three PowerShell-backed detections per focus event, on hardware nobody had
 * touched, while a cleanup was using the same PowerShell. Three things had to
 * be true and were not: the interval had to be longer than a cycle, a cycle
 * already running had to block another, and an apply in progress had to stop
 * the reads entirely.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useRefreshOnFocus } from "../useRefreshOnFocus";
import { hardwareManager } from "../../../lib/hardware-manager";
import { useStore } from "../../../store";

vi.mock("../../../lib/hardware-manager", () => ({
  hardwareManager: {
    refreshAudioDevices: vi.fn().mockResolvedValue(undefined),
    refreshMonitors: vi.fn().mockResolvedValue(undefined),
    refreshNetworkAdapters: vi.fn().mockResolvedValue(undefined),
  },
}));

const manager = vi.mocked(hardwareManager) as unknown as {
  refreshAudioDevices: ReturnType<typeof vi.fn>;
  refreshMonitors: ReturnType<typeof vi.fn>;
  refreshNetworkAdapters: ReturnType<typeof vi.fn>;
};

/** One full cycle = one call to each of the three readers. */
function cycles(): number {
  return manager.refreshAudioDevices.mock.calls.length;
}

async function focusAndSettle(): Promise<void> {
  window.dispatchEvent(new Event("focus"));
  // Let the async cycle run to completion.
  await vi.waitFor(() =>
    expect(manager.refreshNetworkAdapters).toHaveBeenCalled(),
  );
  await Promise.resolve();
}

describe("hardware is re-read on focus, sparingly", () => {
  let now = 0;

  beforeEach(() => {
    now = 0;
    vi.spyOn(performance, "now").mockImplementation(() => now);
    manager.refreshAudioDevices.mockClear();
    manager.refreshMonitors.mockClear();
    manager.refreshNetworkAdapters.mockClear();
    useStore.setState({ isApplying: false } as never);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reads all three the first time the window is focused", async () => {
    renderHook(() => useRefreshOnFocus());
    await focusAndSettle();

    expect(manager.refreshAudioDevices).toHaveBeenCalledTimes(1);
    expect(manager.refreshMonitors).toHaveBeenCalledTimes(1);
    expect(manager.refreshNetworkAdapters).toHaveBeenCalledTimes(1);
  });

  it("does not read again a few seconds later", async () => {
    renderHook(() => useRefreshOnFocus());
    await focusAndSettle();

    now = 30_000; // half a minute: hardware does not change this fast
    window.dispatchEvent(new Event("focus"));
    await Promise.resolve();

    expect(cycles()).toBe(1);
  });

  it("counts the interval from when the cycle ended, not when it began", async () => {
    // The measured cycle takes about ten seconds, most of it the network read,
    // so the clock is advanced from inside it. Stamped at the start, an interval
    // shorter than the cycle is no interval at all — which is how alt-tabbing
    // during a long cleanup produced back-to-back runs.
    manager.refreshNetworkAdapters.mockImplementationOnce(async () => {
      now = 10_000;
    });
    renderHook(() => useRefreshOnFocus());
    await focusAndSettle();

    now = 65_000; // 65 s after the cycle began, only 55 s after it ended
    window.dispatchEvent(new Event("focus"));
    await Promise.resolve();

    expect(cycles()).toBe(1);
  });

  it("reads again once the window has really been quiet", async () => {
    renderHook(() => useRefreshOnFocus());
    await focusAndSettle();

    now = 120_000;
    window.dispatchEvent(new Event("focus"));
    await vi.waitFor(() => expect(cycles()).toBe(2));
  });

  it("never starts a second cycle while one is still running", async () => {
    let release: () => void = () => {};
    manager.refreshAudioDevices.mockImplementationOnce(
      () => new Promise<void>((resolve) => (release = resolve)),
    );
    renderHook(() => useRefreshOnFocus());

    window.dispatchEvent(new Event("focus"));
    now = 200_000; // long past the interval, but the first cycle has not finished
    window.dispatchEvent(new Event("focus"));
    await Promise.resolve();

    expect(cycles()).toBe(1);
    release();
  });

  it("reads nothing at all while an apply is running", async () => {
    // The log above: refreshes firing during a two-minute cleanup, competing for
    // the same PowerShell the cleanup was using.
    useStore.setState({ isApplying: true } as never);
    renderHook(() => useRefreshOnFocus());

    window.dispatchEvent(new Event("focus"));
    await Promise.resolve();

    expect(cycles()).toBe(0);
    expect(manager.refreshNetworkAdapters).not.toHaveBeenCalled();
  });

  it("ignores a visibility change while the document is hidden", async () => {
    renderHook(() => useRefreshOnFocus());
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");

    document.dispatchEvent(new Event("visibilitychange"));
    await Promise.resolve();

    expect(cycles()).toBe(0);
  });
});

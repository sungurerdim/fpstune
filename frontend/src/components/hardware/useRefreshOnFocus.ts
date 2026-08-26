import { useEffect, useRef } from "react";
import { hardwareManager } from "../../lib/hardware-manager";

/** Don't re-read on every alt-tab; hardware does not change that fast. */
const MIN_INTERVAL_MS = 5000;

/**
 * Re-read hardware state when the window regains focus.
 *
 * Without this the panel only refreshed after one of its own mutations, so a change
 * made anywhere else — the Windows Sound dialog, a vendor tool, Device Manager —
 * left it showing the cached value indefinitely. That reads as a wrong UI even
 * though every number in it was faithfully reported when it was read, which is
 * exactly the confusion this caused in practice.
 *
 * Only the granular refreshes are used (~200-500 ms each) rather than the full
 * 8 s hardware scan, and they are throttled, because coming back to the window is
 * a hint that something may have changed — not evidence that it did.
 */
export function useRefreshOnFocus(): void {
  const lastRun = useRef(0);

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "hidden") return;
      const now = performance.now();
      if (now - lastRun.current < MIN_INTERVAL_MS) return;
      lastRun.current = now;

      // Sequential, not concurrent. Each of these is a PowerShell-backed detection
      // on the backend, and firing three at once is the contention the detect work
      // already measured — concurrent PowerShell starts inflate each other, and a
      // refresh that loses that race can come back empty. Awaited in turn, and each
      // failure swallowed, because a refresh that does not land must never stop the
      // panel from showing what it already has.
      void (async () => {
        // Each failure is swallowed here rather than aborting the rest: the manager
        // already logs it, and one adapter query failing should not stop the audio
        // and monitor readings from being refreshed.
        try {
          await hardwareManager.refreshAudioDevices();
        } catch {
          /* logged by the manager */
        }
        try {
          await hardwareManager.refreshMonitors();
        } catch {
          /* logged by the manager */
        }
        try {
          await hardwareManager.refreshNetworkAdapters();
        } catch {
          /* logged by the manager */
        }
      })();
    };

    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);
}

import { useEffect, useRef } from "react";
import { hardwareManager } from "../../lib/hardware-manager";
import { useStore } from "../../store";

/**
 * How long a reading is trusted before returning to the window re-reads it.
 *
 * Was 5 seconds, which is not a claim anyone would defend about hardware: the
 * project's own cache policy gives monitor info a five-minute lifetime. Worse,
 * a full cycle takes longer than the old interval — the network read alone
 * measured 6 to 7 seconds against the running app — so a focus event arriving
 * right after a cycle ended always passed the check, and alt-tabbing during a
 * two-minute DISM cleanup produced a back-to-back run of PowerShell queries
 * about hardware nobody had touched.
 */
const MIN_INTERVAL_MS = 60_000;

/**
 * Re-read hardware state when the window regains focus.
 *
 * Without this the panel only refreshed after one of its own mutations, so a change
 * made anywhere else — the Windows Sound dialog, a vendor tool, Device Manager —
 * left it showing the cached value indefinitely. That reads as a wrong UI even
 * though every number in it was faithfully reported when it was read, which is
 * exactly the confusion this caused in practice.
 *
 * Three things keep it from becoming noise. The interval is the one above. A
 * cycle already in flight is never joined by a second one. And nothing is read
 * while an apply is running: those detections compete for the same PowerShell
 * the apply is using, and a refresh cannot tell anyone anything the apply is
 * about to change anyway.
 */
export function useRefreshOnFocus(): void {
  // Negative infinity, not 0: 0 is a timestamp a cycle can legitimately finish
  // at, and using it as the "never ran" sentinel makes the very first interval
  // never apply. Caught by the test below rather than in the wild, where
  // performance.now() happens not to be 0 at that moment.
  const lastRun = useRef(Number.NEGATIVE_INFINITY);
  const inFlight = useRef(false);

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "hidden") return;
      // Reading the store imperatively rather than subscribing: this hook must
      // not re-render the panel every time an apply starts or finishes.
      if (useStore.getState().isApplying) return;
      if (inFlight.current) return;
      const now = performance.now();
      if (now - lastRun.current < MIN_INTERVAL_MS) return;
      inFlight.current = true;

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
        // Stamped at the end, not the start: the interval is meant to be quiet
        // time between reads, and a cycle that itself takes ten seconds would
        // otherwise spend most of the window running.
        lastRun.current = performance.now();
        inFlight.current = false;
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

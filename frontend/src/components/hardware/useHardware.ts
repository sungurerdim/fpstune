import { useState, useEffect, useSyncExternalStore, useCallback } from "react";
import { hardwareManager, HardwareInfo } from "../../lib/hardware-manager";

/**
 * Custom hook for hardware data using HardwareManager.
 * Uses useSyncExternalStore for reactive updates with deduplication.
 */
export function useHardware(): { hardware: HardwareInfo | null; isLoading: boolean } {
  const [isLoading, setIsLoading] = useState(!hardwareManager.hasData());

  // Subscribe to hardware manager for updates
  const hardware = useSyncExternalStore(
    useCallback((onStoreChange) => {
      return hardwareManager.subscribe(onStoreChange);
    }, []),
    () => hardwareManager.getCached(),
    () => hardwareManager.getCached(),
  );

  // Initial fetch on mount
  useEffect(() => {
    let mounted = true;

    const fetchData = async () => {
      try {
        await hardwareManager.getHardware();
      } catch {
        // A failed probe leaves the cached (possibly null) inventory standing;
        // the sections render their own NotDetected. Uncaught, this rejection
        // is unhandled — fetchData is fired without an awaiter.
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    };

    // Unconditional, because getHardware() returns the cached inventory
    // immediately when it has one — so the branch that used to call
    // setIsLoading synchronously in the effect body is not needed, and that
    // call was a cascading render React would have had to bail out of.
    fetchData();

    return () => {
      mounted = false;
    };
  }, []);

  return { hardware, isLoading };
}

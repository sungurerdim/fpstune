import { useMemo } from "react";
import { useStore } from "../store";
import { summarizeImpact, type ImpactSummary } from "../lib/impact";

/**
 * Subscribe to the settings Map + its version counter and return the rolled-up
 * impact summary. Following the established pattern (App.tsx, MaintenanceActions)
 * we never use a selector that returns a fresh array — we read the Map and
 * recompute inside useMemo, keyed by the version counter.
 */
export function useImpactSummary(): ImpactSummary {
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);

  return useMemo(
    () => summarizeImpact(settings.values()),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
    [settings, settingsVersion],
  );
}

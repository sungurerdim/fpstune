import { useMemo } from "react";
import { Wrench, AlertTriangle, RefreshCw } from "lucide-react";
import { useStore } from "../store";
import { cn } from "../lib/utils";
import { useCleanupRunner } from "../hooks/useCleanupRunner";
import { CleanupResults } from "./CleanupResults";
import type { Setting } from "../types/setting";

/**
 * The repair actions — SFC and DISM — with their Run button in their own header.
 *
 * Three things were wrong with the previous layout and all three were visible only
 * on screen. The Run button and the results readout lived in a separate top band
 * that floated to the right of an empty half-screen, so the control said "Select
 * items below" while the items sat at the bottom left. The panel collapsed itself,
 * on the tab where it is the only content. And each action printed its purpose
 * twice — "Scan and repair Windows system files." and then, with an info icon,
 * "Scans and repairs corrupted Windows system files" — because `effect` restates
 * `description` for an action, where "what it does" and "what running it does" are
 * the same sentence.
 */
export function MaintenancePanel() {
  const settings = useStore((state) => state.settings);
  const settingsVersion = useStore((state) => state._settingsVersion);
  const selection = useStore((state) => state.maintenanceSelection);
  const toggleSelection = useStore((state) => state.toggleMaintenanceSelection);
  const runner = useCleanupRunner({ modules: ["maintenance"] });

  const maintenanceSettings = useMemo(() => {
    const result: Setting[] = [];
    for (const setting of settings.values()) {
      if (
        setting.module === "maintenance" &&
        setting.isAction &&
        setting.isApplicable
      ) {
        result.push(setting);
      }
    }
    return result.sort((a, b) => a.categoryOrder - b.categoryOrder);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings, settingsVersion]);

  if (maintenanceSettings.length === 0) {
    return null;
  }

  return (
    <div className="bg-card rounded-lg border border-border">
      <div className="flex items-center gap-3 p-4 border-b border-border flex-wrap">
        <Wrench className="w-5 h-5 text-warning shrink-0" />
        <div className="min-w-0">
          <h3 className="font-semibold">System Maintenance</h3>
          <p className="text-xs text-muted-foreground">
            Repair and troubleshoot Windows system issues.
          </p>
        </div>
        <div className="ml-auto flex items-center gap-3 min-w-0">
          <div className="w-48 max-w-full min-w-0">
            <CleanupResults compact />
          </div>
          <button
            className={cn(
              "shrink-0 flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors",
              runner.hasSelection
                ? "bg-primary text-primary-foreground hover:bg-primary/90"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
            disabled={!runner.hasSelection || runner.isRunning}
            onClick={() => runner.run()}
          >
            {runner.isRunning ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Wrench className="w-4 h-4" />
                Run{runner.hasSelection && ` (${runner.selectedCount})`}
              </>
            )}
          </button>
        </div>
      </div>

      <div className="p-4 space-y-3">
        {maintenanceSettings.map((setting) => (
          <label
            key={setting.id}
            className={cn(
              "flex items-start gap-3 p-3 rounded-md border cursor-pointer transition-colors",
              selection[setting.id]
                ? "border-warning bg-warning/5"
                : "border-border hover:border-muted-foreground/50",
            )}
          >
            <input
              type="checkbox"
              checked={selection[setting.id] ?? false}
              onChange={() => toggleSelection(setting.id)}
              className="mt-1 h-4 w-4 rounded border-border text-warning focus:ring-warning"
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-sm">
                  {setting.displayName}
                </span>
                {setting.durationEstimate && (
                  <span className="text-xs text-muted-foreground">
                    ({setting.durationEstimate})
                  </span>
                )}
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                {setting.description}
              </p>
              {/* Kept: this one is a precondition, not a restatement. */}
              {setting.name === "dism_health" && (
                <div className="flex items-start gap-1.5 mt-2 text-xs text-warning">
                  <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  <span>
                    May require internet connection to download repair files.
                  </span>
                </div>
              )}
            </div>
          </label>
        ))}
      </div>
    </div>
  );
}

import { Button } from "./ui/Button";
import {
  Trash2,
  Loader2,
  HardDrive,
  AlertTriangle,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { useStore } from "../store";
import { parseCleanupSize, fmtMB } from "../lib/cleanupSize";
import { isDockerCleanup, type CleanupRunner } from "../hooks/useCleanupRunner";
import type { Setting } from "../types/setting";

/**
 * One cleanup opportunity row: name, description, reclaimable-size badge, and a
 * per-row Run that delegates to the shared runner (so docker rows get the same
 * confirm gate as Run All). Result/pending state comes from cleanupResults.
 */
export function CleanupListRow({
  setting,
  runner,
}: {
  setting: Setting;
  runner: CleanupRunner;
}) {
  const result = useStore((s) => s.cleanupResults[setting.id]);
  const size = parseCleanupSize(setting.currentValue);

  const sizeBadge = () => {
    if (size === "calculating" || !size) {
      return (
        <span className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
          <Loader2 className="w-3 h-3 animate-spin" />
          Calculating...
        </span>
      );
    }
    if (size === "unavailable") {
      return (
        <span
          title="Service not running and could not be started. Start it, then reopen this tab."
          className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-warning/10 text-warning"
        >
          <AlertTriangle className="w-3 h-3" />
          Unavailable
        </span>
      );
    }
    return (
      <span className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">
        <HardDrive className="w-3 h-3" />
        {size}
      </span>
    );
  };

  const status = () => {
    if (!result) return null;
    if (!result.success)
      return (
        <span className="flex items-center gap-1 text-xs text-destructive">
          <XCircle className="w-3 h-3" /> Failed
        </span>
      );
    if (!result.sized)
      return (
        <span className="flex items-center gap-1 text-xs text-success">
          <CheckCircle2 className="w-3 h-3" /> Done
        </span>
      );
    if (result.freedMB === null)
      return <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />;
    return (
      <span className="text-xs text-primary font-medium">
        Freed {fmtMB(result.freedMB)}
      </span>
    );
  };

  return (
    <div className="flex items-start gap-3 p-3 rounded-md border border-border hover:border-muted-foreground/50 transition-colors">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm break-words min-w-0">
            {setting.displayName}
          </span>
          {sizeBadge()}
          {setting.durationEstimate && (
            <span className="text-xs text-muted-foreground">
              ({setting.durationEstimate})
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">
          {setting.description}
        </p>
        {isDockerCleanup(setting) && (
          <div className="flex items-start gap-1.5 mt-1.5 text-xs text-warning">
            <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
            <span>
              Restarts Docker Desktop and all WSL distributions to compact the
              virtual disk; can take several minutes.
            </span>
          </div>
        )}
        <div className="mt-1.5">{status()}</div>
      </div>
      <Button
        className="shrink-0"
        busy={runner.isRunning}
        icon={<Trash2 className="w-3.5 h-3.5" />}
        onClick={() => runner.run([setting.id])}
      >
        Run
      </Button>
    </div>
  );
}

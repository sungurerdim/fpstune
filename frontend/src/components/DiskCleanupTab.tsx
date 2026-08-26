import { Gamepad2, Trash2, Loader2 } from "lucide-react";
import { cn } from "../lib/utils";
import { useCleanupRunner } from "../hooks/useCleanupRunner";
import { CleanupPanel } from "./CleanupPanel";
import { CleanupResults } from "./CleanupResults";
import { MaintenancePanel } from "./MaintenancePanel";
import { DockerConfirmModal } from "./DockerConfirmModal";

/**
 * Cleanup & Repair — the System and Game cleanup panels with one Run across both,
 * plus the Windows repair actions. Docker prune is gated behind the restart confirm.
 *
 * Repair used to be a top-level tab of its own holding two checkboxes, while this
 * tab already drove the same action runner. It keeps its own Run because its
 * actions are not cleanups: SFC and DISM reclaim nothing and take minutes, so
 * folding them into "Run Cleanup" would hide a long repair behind a button whose
 * label promises disk space.
 */
export function DiskCleanupTab() {
  const runner = useCleanupRunner({ modules: ["cleanup", "game_cleanup"] });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="w-72 max-w-full min-w-0">
          <CleanupResults compact />
        </div>
        <button
          onClick={() => runner.run()}
          disabled={!runner.hasSelection || runner.isRunning}
          className={cn(
            "shrink-0 flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium transition-colors",
            runner.hasSelection
              ? "bg-primary text-primary-foreground hover:bg-primary/90"
              : "bg-muted text-muted-foreground cursor-not-allowed",
          )}
        >
          {runner.isRunning ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Running...
            </>
          ) : (
            <>
              <Trash2 className="w-4 h-4" />
              Run Cleanup
              {runner.hasSelection && ` (${runner.selectedCount})`}
            </>
          )}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CleanupPanel initialCollapsed={false} />
        <CleanupPanel
          initialCollapsed={false}
          module="game_cleanup"
          title="Game Maintenance"
          icon={Gamepad2}
          description="Clear game, GPU shader, and launcher caches. Deleted files cannot be recovered; games and drivers rebuild caches on next launch."
        />
      </div>

      <MaintenancePanel />

      <DockerConfirmModal
        open={runner.confirmIds !== null}
        onConfirm={runner.confirmRun}
        onCancel={runner.cancelConfirm}
      />
    </div>
  );
}

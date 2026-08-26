import { Button } from "./ui/Button";
import { Gamepad2, Trash2 } from "lucide-react";
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
        <Button
          size="md"
          className="shrink-0"
          busy={runner.isRunning}
          disabled={!runner.hasSelection}
          icon={<Trash2 className="w-4 h-4" />}
          onClick={() => runner.run()}
        >
          {runner.isRunning
            ? "Running..."
            : `Run Cleanup${runner.hasSelection ? ` (${runner.selectedCount})` : ""}`}
        </Button>
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

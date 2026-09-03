import { useT } from "../i18n";
import { Button } from "./ui/Button";
import { Gamepad2, Trash2 } from "lucide-react";
import { useCleanupRunner } from "../hooks/useCleanupRunner";
import { CleanupPanel } from "./CleanupPanel";
import { CleanupResults } from "./CleanupResults";
import { MaintenancePanel } from "./MaintenancePanel";
import { RunPanel } from "./RunPanel";
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
  const { t } = useT();
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
            ? t("maintenance.running")
            : runner.hasSelection
              ? t("cleanup.runCleanupCount", { count: runner.selectedCount })
              : t("cleanup.runCleanup")}
        </Button>
      </div>

      {/* Directly under the Run button, above the lists: while something is
          running this is the only thing on the page the user is waiting on, and
          it is the answer to "what is it doing right now". */}
      <RunPanel />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CleanupPanel initialCollapsed={false} />
        <CleanupPanel
          initialCollapsed={false}
          module="game_cleanup"
          title={t("cleanup.gameTitle")}
          icon={Gamepad2}
          description={t("cleanup.gameDescription")}
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

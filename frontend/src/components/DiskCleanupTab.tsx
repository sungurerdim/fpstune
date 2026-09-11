import { useMemo } from "react";
import { useT } from "../i18n";
import { Button } from "./ui/Button";
import { Gamepad2, Trash2 } from "lucide-react";
import { useCleanupRunner } from "../hooks/useCleanupRunner";
import { useStore } from "../store";
import { fmtMB } from "../lib/cleanupSize";
import { CleanupPanel } from "./CleanupPanel";
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
 *
 * What a run is doing, and what it did, is no longer a band of its own up here:
 * a separate "running" panel listed a copy of every selected cleanup while the
 * originals stayed in the lists below, so each one appeared twice. Every row
 * now carries its own progress and its own outcome. All that is left at the top
 * is the session total — the one number the rows cannot state between them.
 */
export function DiskCleanupTab() {
  const { t } = useT();
  const runner = useCleanupRunner({ modules: ["cleanup", "game_cleanup"] });
  const cleanupResults = useStore((s) => s.cleanupResults);

  // Every addend is a byte count the backend measured either side of a cleanup
  // it ran, so this total is a measurement rather than a sum of claims (C11
  // rule 1). A run that freed nothing measurable contributes nothing.
  const freedMB = useMemo(
    () =>
      Object.values(cleanupResults).reduce(
        (sum, r) => (r.success && r.freedMB !== null ? sum + r.freedMB : sum),
        0,
      ),
    [cleanupResults],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        {freedMB > 0 && (
          <p className="text-sm text-primary font-medium">
            {t("cleanup.freed", { amount: fmtMB(freedMB) })}
          </p>
        )}
        <Button
          size="md"
          className="ml-auto shrink-0"
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CleanupPanel runner={runner} initialCollapsed={false} />
        <CleanupPanel
          runner={runner}
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

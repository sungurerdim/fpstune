/**
 * SelectionToolbar — sticky bottom toolbar for bulk apply/reset via SSE streaming.
 * Appears when ≥1 setting is selected; tracks per-setting operation status in store.
 */

import { useT } from "../i18n";
import { Button } from "./ui/Button";
import { useState } from "react";
import { X, Zap, RotateCcw, Loader2, AlertTriangle } from "lucide-react";
import { cn } from "../lib/utils";
import { useStore } from "../store";
import { useBulkStream } from "../hooks/useBulkStream";
import { ConfirmDialog } from "./ui/ConfirmDialog";

export function SelectionToolbar() {
  const { t } = useT();
  const selectedSettingIds = useStore((s) => s.selectedSettingIds);
  const clearSelection = useStore((s) => s.clearSelection);
  const settings = useStore((s) => s.settings);
  const { run, stop, isRunning } = useBulkStream();

  const [pendingAction, setPendingAction] = useState<"apply" | "reset" | null>(
    null,
  );

  if (selectedSettingIds.size === 0) return null;

  const selectedSettings = [...selectedSettingIds]
    .map((id) => settings.get(id as `${string}:${string}`))
    .filter(Boolean);

  const hasAdvanced = selectedSettings.some((s) => s?.riskLevel === "advanced");

  const runBulk = (action: "apply" | "reset") => run(action, [...selectedSettingIds]);

  const handleAction = (action: "apply" | "reset") => {
    if (hasAdvanced && action === "apply") {
      setPendingAction(action);
    } else {
      runBulk(action);
    }
  };

  const handleCancel = stop;

  return (
    <>
      {/* Advanced warning confirmation */}
      <ConfirmDialog
        open={pendingAction !== null}
        title={t("toolbar.advancedTitle")}
        confirmLabel={t("toolbar.applyAnyway")}
        onConfirm={() => {
          if (pendingAction) runBulk(pendingAction);
          setPendingAction(null);
        }}
        onCancel={() => setPendingAction(null)}
      >
        {t("toolbar.advancedBody")}
      </ConfirmDialog>

      {/* Sticky toolbar */}
      <div
        className={cn(
          "fixed bottom-0 left-0 right-0 z-50",
          "bg-card/95 backdrop-blur-xs border-t border-border",
          "px-6 py-3 flex items-center gap-3 shadow-lg",
        )}
      >
        <span className="text-sm font-medium text-foreground">
          {t("toolbar.selected", { count: selectedSettingIds.size })}
        </span>

        <button
          onClick={clearSelection}
          disabled={isRunning}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
        >
          <X className="w-3.5 h-3.5" />
          {t("toolbar.clear")}
        </button>

        {isRunning && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            {t("toolbar.processing")}
          </span>
        )}

        <div className="ml-auto flex items-center gap-2">
          {isRunning ? (
            <button
              onClick={handleCancel}
              className="px-3 py-1.5 text-xs rounded border border-border hover:bg-muted transition-colors"
            >
              {t("toolbar.stop")}
            </button>
          ) : (
            <>
              <button
                onClick={() => handleAction("reset")}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded border border-border hover:bg-muted text-foreground transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                {t("toolbar.resetSelected")}
              </button>
              <Button
                variant={hasAdvanced ? "confirm" : "primary"}
                icon={<Zap className="w-3.5 h-3.5" />}
                onClick={() => handleAction("apply")}
              >
                {t("toolbar.applySelected")}
                {hasAdvanced && <AlertTriangle className="w-3 h-3 ml-0.5" />}
              </Button>
            </>
          )}
        </div>
      </div>
    </>
  );
}

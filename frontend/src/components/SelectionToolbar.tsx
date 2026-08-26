/**
 * SelectionToolbar — sticky bottom toolbar for bulk apply/reset via SSE streaming.
 * Appears when ≥1 setting is selected; tracks per-setting operation status in store.
 */

import { useT } from "../i18n";
import { Button } from "./ui/Button";
import { useState } from "react";
import { X, Zap, RotateCcw, Loader2, AlertTriangle } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "../lib/utils";
import { settingsApi } from "../lib/api";
import { useStore } from "../store";
import { valuesEqual } from "../types/setting";
import { ConfirmDialog } from "./ui/ConfirmDialog";

export function SelectionToolbar() {
  const { t } = useT();
  const queryClient = useQueryClient();
  const selectedSettingIds = useStore((s) => s.selectedSettingIds);
  const clearSelection = useStore((s) => s.clearSelection);
  const setOperationStatus = useStore((s) => s.setOperationStatus);
  const clearOperationStatus = useStore((s) => s.clearOperationStatus);
  const setSettingDetectionResult = useStore((s) => s.setSettingDetectionResult);
  const settings = useStore((s) => s.settings);

  const [isRunning, setIsRunning] = useState(false);
  const [cancelFn, setCancelFn] = useState<(() => void) | null>(null);
  const [pendingAction, setPendingAction] = useState<"apply" | "reset" | null>(
    null,
  );

  if (selectedSettingIds.size === 0) return null;

  const selectedSettings = [...selectedSettingIds]
    .map((id) => settings.get(id as `${string}:${string}`))
    .filter(Boolean);

  const hasAdvanced = selectedSettings.some((s) => s?.riskLevel === "advanced");

  const runBulk = (action: "apply" | "reset") => {
    clearOperationStatus();
    const ids = [...selectedSettingIds];
    ids.forEach((id) => setOperationStatus(id, "queued"));
    setIsRunning(true);

    const streamFn =
      action === "apply"
        ? settingsApi.bulkStreamApply
        : settingsApi.bulkStreamReset;

    const cancel = streamFn(
      ids,
      (event) => {
        const id = event.id as string | undefined;
        if (!id) return;
        if (event.event === "started") {
          setOperationStatus(id, "running");
        } else if (event.event === "applied") {
          setOperationStatus(id, "running");
        } else if (event.event === "verified") {
          setOperationStatus(id, "verified");
          // Update store directly from SSE payload — no extra API round-trip
          const currentValue = (event as Record<string, unknown>).current_value;
          const setting = settings.get(id as `${string}:${string}`);
          if (setting !== undefined && currentValue !== undefined) {
            const isOptimized = valuesEqual(currentValue, setting.recommendedValue);
            setSettingDetectionResult(
              id as `${string}:${string}`,
              currentValue,
              isOptimized,
              true,
            );
          }
        } else if (event.event === "failed") {
          setOperationStatus(id, "failed");
        }
      },
      () => {
        setIsRunning(false);
        setCancelFn(null);
        queryClient.invalidateQueries({ queryKey: ["activity"] });
      },
    );
    setCancelFn(() => cancel);
  };

  const handleAction = (action: "apply" | "reset") => {
    if (hasAdvanced && action === "apply") {
      setPendingAction(action);
    } else {
      runBulk(action);
    }
  };

  const handleCancel = () => {
    cancelFn?.();
    setIsRunning(false);
    setCancelFn(null);
    clearOperationStatus();
  };

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
          "bg-card/95 backdrop-blur-sm border-t border-border",
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
                {hasAdvanced && (
                  <AlertTriangle className="w-3 h-3 ml-0.5" />
                )}
              </Button>
            </>
          )}
        </div>
      </div>
    </>
  );
}

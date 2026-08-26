import { useT } from "../../i18n";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, Sparkles, XCircle } from "lucide-react";
import { useState } from "react";
import { api, type StorageDriveInfo } from "../../lib/api";
import { createLogger } from "../../lib/logger";
import { cn } from "../../lib/utils";

const log = createLogger("StorageDriveCard");

/**
 * Storage drive card — readout plus the UI's first per-drive action (D3).
 *
 * The button runs whatever pass this drive's own media type calls for
 * (retrim on an SSD, defrag on an HDD — the backend decides from
 * `MediaType`, never from this card). Unknown media gets no button: the
 * backend would refuse with 409, so offering the click would be offering
 * an error.
 */
export function StorageDriveCard({ drive }: { drive: StorageDriveInfo }) {
  const { t } = useT();
  const usedPercent =
    drive.free_gb !== undefined && drive.size_gb > 0
      ? Math.round(((drive.size_gb - drive.free_gb) / drive.size_gb) * 100)
      : null;
  const isLowSpace = usedPercent !== null && usedPercent > 90;

  const [lastResult, setLastResult] = useState<string | null>(null);
  const optimizeMutation = useMutation({
    mutationFn: () => api.optimizeDrive(drive.drive_letter),
    onSuccess: (result) => setLastResult(result.message),
    onError: (error: Error) => {
      log.error(
        `Failed to optimize drive ${drive.drive_letter}:`,
        error.message,
      );
      setLastResult(`Failed: ${error.message}`);
    },
  });

  const actionLabel =
    drive.media_type === "SSD" ? t("storage.retrim") : t("storage.defrag");
  const canOptimize =
    drive.media_type === "SSD" || drive.media_type === "HDD";

  return (
    <div className="pl-3 border-l-2 border-border">
      <p className="font-medium text-xs truncate" title={drive.model}>
        {drive.drive_letter}: {drive.model}
      </p>
      <p className="text-xs text-muted-foreground">
        {drive.bus_type && <span>{drive.bus_type} </span>}
        {drive.media_type}
        {drive.free_gb !== undefined ? (
          <span className="ml-1">
            •{" "}
            <span className={isLowSpace ? "text-warning" : ""}>
              {drive.free_gb}/{drive.size_gb} GB free
            </span>
          </span>
        ) : (
          <span className="ml-1">• {drive.size_gb} GB</span>
        )}
        {drive.media_type === "SSD" && (
          <span className="ml-1">
            • TRIM:{" "}
            {drive.trim_enabled ? (
              <CheckCircle2 className="w-3 h-3 inline text-success" />
            ) : (
              <XCircle className="w-3 h-3 inline text-warning" />
            )}
          </span>
        )}
      </p>
      {/* Space usage bar */}
      {usedPercent !== null && (
        <div className="mt-1 h-1 bg-muted rounded-full overflow-hidden">
          <div
            className={cn(
              "h-full transition-all",
              isLowSpace ? "bg-warning" : "bg-primary/50",
            )}
            style={{ width: `${usedPercent}%` }}
          />
        </div>
      )}
      {canOptimize && (
        <div className="mt-1 flex items-center gap-2">
          <button
            onClick={() => optimizeMutation.mutate()}
            disabled={optimizeMutation.isPending}
            className={cn(
              "flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors",
              optimizeMutation.isPending
                ? "bg-muted text-muted-foreground cursor-wait"
                : "border border-border text-muted-foreground hover:bg-muted",
            )}
          >
            {optimizeMutation.isPending ? (
              <RefreshCw className="w-3 h-3 animate-spin" />
            ) : (
              <Sparkles className="w-3 h-3" />
            )}
            {optimizeMutation.isPending
              ? t("storage.running", { action: actionLabel })
              : actionLabel}
          </button>
          {lastResult && (
            <span
              className={cn(
                "text-xs",
                lastResult.startsWith("Failed")
                  ? "text-warning"
                  : "text-success",
              )}
            >
              {lastResult}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

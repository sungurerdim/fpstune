import {
  CheckCircle2, XCircle, } from "lucide-react";
import {
  type StorageDriveInfo, } from "../../lib/api";
import { cn } from "../../lib/utils";


/**
 * Storage drive card
 */
export function StorageDriveCard({ drive }: { drive: StorageDriveInfo }) {
  const usedPercent =
    drive.free_gb !== undefined && drive.size_gb > 0
      ? Math.round(((drive.size_gb - drive.free_gb) / drive.size_gb) * 100)
      : null;
  const isLowSpace = usedPercent !== null && usedPercent > 90;

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
    </div>
  );
}

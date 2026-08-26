import { useT } from "../i18n";
import { HardDrive, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { useStore } from "../store";
import { fmtMB } from "../lib/cleanupSize";

/**
 * CleanupResults — compact aggregate of the latest cleanup/maintenance run.
 *
 * Rendered in the top band (Maintenance tab) beside the unified Run Cleanup
 * button. Shows the measured freed space per operation (before − after size)
 * plus a session total. The `compact` prop is accepted for call-site clarity;
 * the component always renders the compact band layout.
 */
export function CleanupResults({ compact: _compact = true }: { compact?: boolean }) {
  const { t } = useT();
  const cleanupResults = useStore((s) => s.cleanupResults);

  const results = Object.values(cleanupResults);
  const totalFreed = results.reduce(
    (sum, r) => sum + (r.success && r.freedMB ? r.freedMB : 0),
    0,
  );
  const anyCalculating = results.some(
    (r) => r.success && r.sized && r.freedMB === null,
  );
  const failedCount = results.filter((r) => !r.success).length;

  return (
    <div className="flex flex-col gap-1.5 min-w-0">
      <div className="flex items-center gap-2 pr-1">
        <HardDrive className="w-4 h-4 text-primary shrink-0" />
        <span className="text-sm font-semibold">{t("cleanup.results")}</span>
        {results.length > 0 && (
          <span className="ml-auto flex items-center gap-2 shrink-0 whitespace-nowrap">
            {failedCount > 0 && (
              <span className="text-xs text-destructive">{t("cleanup.failedCount", { count: failedCount })}</span>
            )}
            <span className="text-xs text-primary font-medium">
              {anyCalculating ? t("cleanup.calculating") : t("cleanup.freed", { amount: fmtMB(totalFreed) })}
            </span>
          </span>
        )}
      </div>

      {results.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {t("cleanup.resultsEmpty")}
        </p>
      ) : (
        <div className="flex flex-col gap-0.5 max-h-20 overflow-y-auto pr-1">
          {results.map((r) => (
            <div
              key={r.id}
              className="flex items-center gap-2 text-xs min-w-0"
              title={!r.success && r.error ? r.error : undefined}
            >
              {r.success ? (
                <CheckCircle2 className="w-3 h-3 text-success shrink-0" />
              ) : (
                <XCircle className="w-3 h-3 text-destructive shrink-0" />
              )}
              <span className="truncate text-muted-foreground">{r.name}</span>
              <span className="ml-auto shrink-0 whitespace-nowrap">
                {!r.success ? (
                  <span className="text-destructive">{t("cleanup.failed")}</span>
                ) : !r.sized ? (
                  <span className="text-success">{t("cleanup.done")}</span>
                ) : r.freedMB === null ? (
                  <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
                ) : (
                  <span className="text-primary font-medium">{fmtMB(r.freedMB)}</span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

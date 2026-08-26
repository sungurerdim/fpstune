import { useT } from "../i18n";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ScrollText,
  X,
  CheckCircle2,
  AlertCircle,
  XCircle,
  Info,
} from "lucide-react";
import { api } from "../lib/api";
import { cn } from "../lib/utils";

const levelIcons = {
  success: <CheckCircle2 className="w-3.5 h-3.5 text-success" />,
  warning: <AlertCircle className="w-3.5 h-3.5 text-warning" />,
  error: <XCircle className="w-3.5 h-3.5 text-destructive" />,
  info: <Info className="w-3.5 h-3.5 text-primary" />,
};

/**
 * ActivityLog — a compact bar button that opens the recent activity in a
 * right-side slide-in panel (replaces the old bottom sticky log). Self-contained:
 * the button lives in the top bar; the panel is a fixed overlay, closed by default.
 */
export function ActivityLog() {
  const { t } = useT();
  const [open, setOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["activity"],
    queryFn: () => api.getActivityLog(20),
    // Poll briskly while the panel is open; back off when closed (the closed
    // button only needs the error dot refreshed occasionally) to cut idle load.
    refetchInterval: open ? 30000 : 120000,
  });

  const hasError = data?.entries?.some((e) => e.level === "error") ?? false;

  // Close on Escape while the panel is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        title={t("activity.open")}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-muted/60 text-muted-foreground hover:bg-muted transition-colors"
      >
        <ScrollText className="w-3.5 h-3.5" />
        <span className="hidden md:inline">Activity</span>
        {hasError && (
          <span className="w-1.5 h-1.5 rounded-full bg-destructive" aria-hidden />
        )}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex justify-end"
          role="dialog"
          aria-label={t("activity.title")}
        >
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div className="relative w-full max-w-md h-full bg-card border-l border-border shadow-xl flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <ScrollText className="w-4 h-4 text-primary" />
                <h3 className="font-semibold text-sm">Activity Log</h3>
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label={t("activity.close")}
                className="p-1 rounded hover:bg-muted text-muted-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-2">
              {isLoading ? (
                <div className="space-y-2 py-2">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="flex items-start gap-2 py-1">
                      <span className="w-14 h-4 bg-muted rounded animate-pulse" />
                      <span className="w-4 h-4 bg-muted rounded animate-pulse" />
                      <span className="flex-1 h-4 bg-muted rounded animate-pulse" />
                    </div>
                  ))}
                </div>
              ) : !data || data.entries.length === 0 ? (
                <p className="text-xs text-muted-foreground py-3">
                  No recent activity
                </p>
              ) : (
                <div className="space-y-1 py-1">
                  {data.entries.map((entry, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 text-xs py-1.5 border-b border-border/30 last:border-0"
                    >
                      <span className="text-muted-foreground/60 font-mono shrink-0">
                        {entry.timestamp}
                      </span>
                      {levelIcons[entry.level as keyof typeof levelIcons] ||
                        levelIcons.info}
                      <span
                        className={cn(
                          entry.level === "error" && "text-destructive",
                          entry.level === "warning" && "text-warning",
                          entry.level === "success" && "text-success",
                        )}
                      >
                        {entry.message}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, X } from "lucide-react";
import { useT } from "../i18n";
import { api } from "../lib/api";

/**
 * "Windows was updated since fpstune last ran" — once, on Home.
 *
 * Updates put settings back to Windows' own values, which is the drift the
 * guards exist to catch. The scan that runs at every start already re-read the
 * machine against the new build; this only says why rows applied weeks ago may
 * show as changed. The backend records the build on its first answer, so the
 * next start shows nothing until the next update. Informational, so it stays
 * light: no colour of alarm, dismissible, and absent when nothing changed.
 */
export function OsUpdateNotice() {
  const { t } = useT();
  const [dismissed, setDismissed] = useState(false);
  const { data } = useQuery({
    queryKey: ["os-build"],
    queryFn: () => api.getOsBuildChange(),
    staleTime: Infinity,
    retry: false,
  });

  if (dismissed || !data?.changed || !data.previous || !data.current) return null;

  return (
    <div
      role="status"
      className="rounded-lg border border-border bg-muted/40 p-3 flex items-start gap-2"
    >
      <RefreshCw className="w-4 h-4 mt-0.5 text-primary shrink-0" aria-hidden="true" />
      <p className="text-sm text-foreground/80">
        {t("osUpdate.body", { previous: data.previous, current: data.current })}
      </p>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        aria-label={t("osUpdate.dismiss")}
        className="ml-auto p-1 rounded text-muted-foreground hover:bg-muted transition-colors"
      >
        <X className="w-3.5 h-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}

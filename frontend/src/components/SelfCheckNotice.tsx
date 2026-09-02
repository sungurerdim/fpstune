import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, ShieldAlert } from "lucide-react";
import { useT } from "../i18n";
import { api } from "../lib/api";

/**
 * The detection self-check's disagreements, on Home (A12 → D3).
 *
 * Every detector is cross-checked against an independent source before the
 * first apply; the report was persisted and reachable by nothing — a machine
 * whose monitor map disagreed with WMI looked identical to a healthy one.
 * A clean report renders nothing: agreement is the expected state, and a
 * permanent "all good" banner would train the eye to skip this spot.
 */
export function SelfCheckNotice() {
  const { t } = useT();
  const queryClient = useQueryClient();
  const { data: report } = useQuery({
    queryKey: ["self-check"],
    queryFn: () => api.getSelfCheck(),
    staleTime: Infinity,
    retry: false,
  });

  const recheck = useMutation({
    mutationFn: () => api.getSelfCheck(true),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["self-check"], fresh);
    },
  });

  if (!report || report.ok) return null;

  const disagreements = report.findings.filter((finding) => !finding.agrees);

  return (
    <div className="rounded-lg border border-warning/40 bg-warning/6 p-3 space-y-2">
      <div className="flex items-center gap-2">
        <ShieldAlert className="w-4 h-4 text-warning" aria-hidden="true" />
        <p className="text-sm font-medium text-warning">
          {disagreements.length === 1
            ? t("selfCheck.disagreementsOne")
            : t("selfCheck.disagreementsMany", {
                count: disagreements.length,
              })}
        </p>
        <button
          onClick={() => recheck.mutate()}
          disabled={recheck.isPending}
          className="ml-auto flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium border border-border text-muted-foreground hover:bg-muted transition-colors disabled:cursor-wait"
        >
          <RefreshCw
            className={
              recheck.isPending ? "w-3 h-3 animate-spin" : "w-3 h-3"
            }
            aria-hidden="true"
          />
          {recheck.isPending ? t("selfCheck.checking") : t("selfCheck.recheck")}
        </button>
      </div>
      <ul className="list-disc pl-6 space-y-0.5 text-xs text-muted-foreground">
        {disagreements.map((finding) => (
          <li key={`${finding.area}:${finding.name}`}>
            <span className="font-medium">{finding.area}</span> — {finding.detail}
          </li>
        ))}
      </ul>
    </div>
  );
}

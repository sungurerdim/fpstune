import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, RotateCcw } from "lucide-react";
import { useT, getLocale } from "../i18n";
import { localizedName } from "../i18n/settings";
import { errorMessage, historyApi, type HistorySetting } from "../lib/api";
import { useBulkStream } from "../hooks/useBulkStream";
import { useStore } from "../store";
import type { Setting, SettingId } from "../types/setting";
import { ScopeActions } from "./ScopeActions";
import { Metric, MetricList, ScopeHeader } from "./ui/ScopeHeader";
import { defaultKindKey } from "../lib/tweakDomain";
import { Card } from "./ui/Card";

/**
 * What fpstune changed on this machine during this session, and the one way
 * back from each change: Reset to default, which writes the setting's own
 * default (Windows', the driver's or the game's). Nothing here is stored — the
 * list is the backend's memory of this run and goes with it. Resets run through
 * the same streamed bulk path as every other surface, so one row or fifty report
 * the same way and Stop works.
 */
export function HistoryTab() {
  const { t } = useT();
  const { run, isRunning } = useBulkStream();
  const settings = useStore((s) => s.settings);
  const operationStatus = useStore((s) => s.operationStatus);
  const operationError = useStore((s) => s.operationError);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data, isLoading, error } = useQuery({
    queryKey: ["history"],
    queryFn: historyApi.get,
    staleTime: 5000,
  });

  const rows = useMemo(() => data?.settings ?? [], [data]);
  const active = rows.filter((r) => r.last_action === "apply");
  const reverted = rows.filter((r) => r.last_action !== "apply");
  const activeSettings = useMemo(
    () =>
      active
        .map((r) => settings.get(r.setting_id as SettingId))
        .filter((s): s is Setting => s !== undefined),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `active` derives from rows
    [rows, settings],
  );

  const nameOf = (id: string): string => {
    const setting = settings.get(id as SettingId);
    return setting ? localizedName(setting) : id;
  };

  const kindOf = (id: string): string | undefined => {
    const setting = settings.get(id as SettingId);
    return setting ? t(defaultKindKey(setting)) : undefined;
  };

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const selectedIds = active.map((r) => r.setting_id).filter((id) => selected.has(id));
  const startReset = (ids: string[]) => {
    run("reset", ids);
    setSelected(new Set());
  };

  if (isLoading) {
    return (
      <p className="text-sm text-muted-foreground flex items-center gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> {t("history.loading")}
      </p>
    );
  }
  if (error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {t("history.error", { reason: errorMessage(error) })}
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="p-4 space-y-2">
        <ScopeHeader
          level={2}
          title={t("history.title")}
          /* Page scope: every setting fpstune still has applied, with the
              same Reset to default every other page offers. */
          actions={
            <ScopeActions
              settings={activeSettings}
              name={t("tab.history")}
              only={["reset"]}
            />
          }
        />
        <p className="text-sm text-muted-foreground">{t("history.intro")}</p>
      </Card>

      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("history.empty")}</p>
      ) : (
        <>
          <section aria-labelledby="history-active" className="space-y-2">
            <ScopeHeader
              headingId="history-active"
              title={t("history.active")}
              metrics={
                <MetricList>
                  <Metric value={active.length} label={t("metric.settings")} />
                </MetricList>
              }
              actions={
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className="rounded-md bg-muted px-3 py-1.5 text-xs hover:bg-muted/80"
                    onClick={() =>
                      setSelected(
                        selectedIds.length === active.length
                          ? new Set()
                          : new Set(active.map((r) => r.setting_id)),
                      )
                    }
                    disabled={active.length === 0}
                  >
                    {t("history.selectAll")}
                  </button>
                  <button
                    type="button"
                    className="flex items-center gap-1.5 rounded-md bg-muted px-3 py-1.5 text-xs hover:bg-muted/80 disabled:opacity-50"
                    disabled={isRunning || selectedIds.length === 0}
                    onClick={() => startReset(selectedIds)}
                  >
                    <RotateCcw className="h-3 w-3" />
                    {t("history.resetSelected", { count: selectedIds.length })}
                  </button>
                </div>
              }
            />
            <ul className="space-y-1">
              {active.map((row) => (
                <HistoryRow
                  key={row.setting_id}
                  row={row}
                  name={nameOf(row.setting_id)}
                  selectable
                  selected={selected.has(row.setting_id)}
                  onToggle={() => toggle(row.setting_id)}
                  busy={isRunning}
                  status={operationStatus[row.setting_id]}
                  statusError={operationError[row.setting_id]}
                  kindLabel={kindOf(row.setting_id)}
                  onReset={() => startReset([row.setting_id])}
                />
              ))}
            </ul>
          </section>

          {reverted.length > 0 && (
            <section aria-labelledby="history-reverted" className="space-y-2">
              <ScopeHeader
                headingId="history-reverted"
                title={t("history.reverted")}
                metrics={
                  <MetricList>
                    <Metric value={reverted.length} label={t("metric.settings")} />
                  </MetricList>
                }
              />
              <ul className="space-y-1">
                {reverted.map((row) => (
                  <HistoryRow
                    key={row.setting_id}
                    row={row}
                    name={nameOf(row.setting_id)}
                    busy={isRunning}
                    status={operationStatus[row.setting_id]}
                    statusError={operationError[row.setting_id]}
                  />
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}

interface HistoryRowProps {
  row: HistorySetting;
  name: string;
  selectable?: boolean;
  selected?: boolean;
  onToggle?: () => void;
  busy: boolean;
  status?: string;
  statusError?: string;
  /** Which default a reset writes ("Windows default"), when the setting is known. */
  kindLabel?: string;
  onReset?: () => void;
}

function HistoryRow({
  row,
  name,
  selectable = false,
  selected = false,
  onToggle,
  busy,
  status,
  statusError,
  kindLabel,
  onReset,
}: HistoryRowProps) {
  const { t } = useT();
  const when = new Date(row.at * 1000).toLocaleString(getLocale());
  const actionLabel = {
    apply: t("history.action.apply"),
    reset: t("history.action.reset"),
    revert: t("history.action.revert"),
  }[row.last_action];

  return (
    <li className="flex items-center gap-3 rounded-md border border-border/60 px-3 py-2 flex-wrap">
      {selectable && (
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={t("history.selectNamed", { name })}
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium truncate" title={name}>
          {name}
        </div>
        <div className="text-xs text-muted-foreground wrap-break-word">
          {actionLabel} · {t("history.value", { value: String(row.value) })} · {when}
        </div>
        {status === "failed" && statusError && (
          <div role="status" className="text-xs text-destructive wrap-break-word">
            {t("row.statusFailedBecause", { reason: statusError })}
          </div>
        )}
        {status === "verified" && (
          <div role="status" className="text-xs text-success">
            {t("row.statusVerified")}
          </div>
        )}
      </div>
      {onReset && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="px-2.5 py-1 text-xs rounded-md bg-muted hover:bg-muted/80 flex items-center gap-1"
            disabled={busy}
            title={kindLabel}
            aria-label={t("history.resetNamed", { name })}
            onClick={onReset}
          >
            <RotateCcw className="w-3 h-3" /> {t("action.reset")}
          </button>
        </div>
      )}
    </li>
  );
}

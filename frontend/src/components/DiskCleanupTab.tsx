import { useMemo, useState } from "react";
import { Loader2, Square, Trash2 } from "lucide-react";
import { useT } from "../i18n";
import type { MessageKey } from "../i18n/en";
import { localizedName } from "../i18n/settings";
import { useApply } from "../hooks/useApply";
import { isDockerCleanup } from "../store/actionRun";
import { fmtMB, parseCleanupSize, parseSizeToMB } from "../lib/cleanupSize";
import { useStore } from "../store";
import type { Setting, SettingId } from "../types/setting";
import { ActionNote } from "./ActionNote";
import { CategorySection } from "./CategorySection";
import { DockerConfirmModal } from "./DockerConfirmModal";
import { Button } from "./ui/Button";

/** The modules whose settings are actions: what a cleanup reclaims, what a repair fixes. */
const ACTION_MODULES = new Set(["cleanup", "game_cleanup", "maintenance"]);

/**
 * The words an action owes the user before it runs. They sit behind the row's
 * (i), where every other warning does, instead of on a card of their own.
 */
const WARNING_KEYS: Record<string, MessageKey> = {
  dism_cleanup: "cleanup.dismWarning",
  dism_health: "maintenance.dismHealthWarning",
  docker_prune: "cleanup.dockerShutdownWarning",
  docker_prune_all: "cleanup.dockerShutdownWarning",
  wsl_compact: "cleanup.wslWarning",
};

/** One heading's worth of actions: the games, the shader caches, the repairs. */
interface ActionGroup {
  id: string;
  label: string;
  order: number;
  rows: Setting[];
}

const bySize = (a: Setting, b: Setting) => {
  const mbA = parseSizeToMB(a.currentValue);
  const mbB = parseSizeToMB(b.currentValue);
  if (mbA !== null && mbB !== null) return mbB - mbA;
  if (mbA !== null) return -1;
  if (mbB !== null) return 1;
  return a.categoryOrder - b.categoryOrder;
};

/**
 * Cleanup — every action that gives something back, on the one row the rest of
 * the app uses, under the heading the backend gave it (`group_label`).
 *
 * The first scan answers `ready|calculating` for every cleanup, including ones
 * whose software is not installed, and the next scan answers "not installed"
 * for those. Listing them as finished rows made twelve of them appear and then
 * vanish; they wait in a "Measuring" line instead, which reads as the answer it
 * is (nothing to reclaim) when a name leaves it.
 *
 * Every number here was measured on this disk (C11): a group's reclaimable total
 * adds up scan readings only, a row's size is its own reading, and "Freed" is
 * the backend's before-and-after pair for runs that happened — an action that
 * reclaims nothing (a repair) says "Done" and no figure.
 *
 * Repairs (SFC, DISM) are actions of the same kind and sit in their own group
 * rather than their own tab: they reclaim nothing and take minutes, which their
 * row says as it runs.
 */
export function DiskCleanupTab() {
  const { t } = useT();
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const selection = useStore((s) => s.maintenanceSelection);
  const setSelection = useStore((s) => s.setMaintenanceSelection);
  const toggleSelection = useStore((s) => s.toggleMaintenanceSelection);
  const operationStatus = useStore((s) => s.operationStatus);
  const operationError = useStore((s) => s.operationError);
  const cleanupResults = useStore((s) => s.cleanupResults);
  const { run, stop, isRunning } = useApply();
  const [confirmIds, setConfirmIds] = useState<string[] | null>(null);

  const { groups, measuring } = useMemo(() => {
    const byGroup = new Map<string, ActionGroup>();
    const pending: Setting[] = [];

    for (const raw of settings.values()) {
      if (!raw.isAction || !raw.isApplicable || !ACTION_MODULES.has(raw.module)) continue;
      if (parseCleanupSize(raw.currentValue) === "calculating") {
        pending.push(raw);
        continue;
      }
      // The backend groups cleanups; a repair has no group of its own and is
      // listed under the maintenance heading. A cleanup with neither is a
      // backend that shipped one without a table entry (its own red test): it is
      // listed under "Other" rather than dropped.
      const repair = raw.module === "maintenance";
      const id = raw.groupId ?? (repair ? "maintenance" : "other");
      let group = byGroup.get(id);
      if (!group) {
        group = {
          id,
          label:
            raw.groupLabel ?? t(repair ? "maintenance.title" : "cleanup.groupOther"),
          order: raw.groupOrder ?? Number.MAX_SAFE_INTEGER,
          rows: [],
        };
        byGroup.set(id, group);
      }
      const warningKey = WARNING_KEYS[raw.name];
      group.rows.push(warningKey ? { ...raw, riskWarning: t(warningKey) } : raw);
    }

    for (const group of byGroup.values()) group.rows.sort(bySize);
    pending.sort((a, b) => a.categoryOrder - b.categoryOrder);
    return {
      groups: [...byGroup.values()].sort(
        (a, b) => a.order - b.order || a.label.localeCompare(b.label),
      ),
      measuring: pending,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts the cache
  }, [settings, settingsVersion, t]);

  const rowIds = useMemo(() => groups.flatMap((g) => g.rows.map((r) => r.id)), [groups]);
  const selectedIds = useMemo(() => rowIds.filter((id) => selection[id]), [rowIds, selection]);
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

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

  const launch = (ids: string[]) => {
    run("apply", ids);
    // What was just sent is no longer waiting to be run.
    setSelection(ids, false);
  };

  const start = (ids: string[]) => {
    if (ids.length === 0 || isRunning) return;
    // Pruning Docker shuts down Docker Desktop and every WSL distribution.
    const needsConfirm = ids.some((id) => {
      const setting = settings.get(id as SettingId);
      return setting !== undefined && isDockerCleanup(setting);
    });
    if (needsConfirm) {
      setConfirmIds(ids);
      return;
    }
    launch(ids);
  };

  if (groups.length === 0 && measuring.length === 0) return null;

  return (
    <div className="min-w-0 space-y-3">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        {freedMB > 0 && (
          <p className="text-sm font-medium text-primary">
            {t("cleanup.freed", { amount: fmtMB(freedMB) })}
          </p>
        )}
        <div className="ml-auto flex shrink-0 items-center gap-2">
          {isRunning && (
            <Button
              size="md"
              variant="outline"
              icon={<Square className="h-4 w-4" aria-hidden="true" />}
              onClick={stop}
            >
              {t("toolbar.stop")}
            </Button>
          )}
          <Button
            size="md"
            busy={isRunning}
            disabled={selectedIds.length === 0}
            icon={<Trash2 className="h-4 w-4" aria-hidden="true" />}
            onClick={() => start(selectedIds)}
          >
            {isRunning
              ? t("maintenance.running")
              : selectedIds.length > 0
                ? t("cleanup.runCleanupCount", { count: selectedIds.length })
                : t("cleanup.runCleanup")}
          </Button>
        </div>
      </div>

      <div className="min-w-0 space-y-2">
        {groups.map((group) => (
          <CategorySection
            key={group.id}
            title={group.label}
            settings={group.rows}
            onApply={(setting) => start([setting.id])}
            onReset={() => undefined}
            actions={<GroupActions group={group} selectedSet={selectedSet} setSelection={setSelection} />}
            selectedIds={selectedSet}
            onSelect={(setting) => toggleSelection(setting.id)}
            statuses={operationStatus}
            errors={operationError}
            rowNote={(setting) => <ActionNote setting={setting} />}
          />
        ))}
      </div>

      {measuring.length > 0 && (
        <div className="rounded-md border border-dashed border-border/70 p-3">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            <span>{t("cleanup.measuringMore", { count: measuring.length })}</span>
          </div>
          <p className="mt-1 wrap-break-word text-xs text-muted-foreground/70">
            {measuring.map((setting) => localizedName(setting)).join(", ")}
          </p>
          <p className="mt-1 text-xs text-muted-foreground/60">
            {t("cleanup.measuringFootnote")}
          </p>
        </div>
      )}

      <DockerConfirmModal
        open={confirmIds !== null}
        onConfirm={() => {
          if (confirmIds) launch(confirmIds);
          setConfirmIds(null);
        }}
        onCancel={() => setConfirmIds(null)}
      />
    </div>
  );
}

/**
 * A group header's own controls: how much it holds, and one checkbox for all of it.
 *
 * The size total is the sum of what the scan measured on this disk — the one
 * place in the product where adding numbers up is a measurement rather than a
 * claim, because each addend is a byte count an instrument returned.
 */
function GroupActions({
  group,
  selectedSet,
  setSelection,
}: {
  group: ActionGroup;
  selectedSet: ReadonlySet<string>;
  setSelection: (ids: string[], selected: boolean) => void;
}) {
  const { t } = useT();
  const ids = group.rows.map((s) => s.id);
  const selectedCount = ids.filter((id) => selectedSet.has(id)).length;
  const allSelected = selectedCount === ids.length && ids.length > 0;
  // Docker prune and prune-all reclaim the same layers, and the WSL compact
  // touches the same Docker Desktop disks. Adding them turns a 12.7 GB choice
  // into a 20.9 GB promise; the group's ceiling is the largest alternative,
  // not their sum. Ordinary Windows cleanups stay additive.
  const overlapping = group.rows.some((s) =>
    ["cleanup:docker_prune", "cleanup:docker_prune_all", "cleanup:wsl_compact"].includes(s.id),
  );
  const sizes = group.rows.map((s) => parseSizeToMB(s.currentValue) ?? 0);
  const totalMB = overlapping ? Math.max(0, ...sizes) : sizes.reduce((sum, mb) => sum + mb, 0);

  return (
    <span className="flex items-center gap-2">
      {totalMB > 0 && <span className="text-xs text-primary/80">{fmtMB(totalMB)}</span>}
      <input
        type="checkbox"
        checked={allSelected}
        // Some but not all: the box shows neither state, so it says so rather
        // than reading as "none selected".
        ref={(el) => {
          if (el) el.indeterminate = selectedCount > 0 && !allSelected;
        }}
        onChange={() => setSelection(ids, !allSelected)}
        aria-label={t("cleanup.selectGroup", { group: group.label })}
        className="h-4 w-4 cursor-pointer accent-primary"
      />
    </span>
  );
}

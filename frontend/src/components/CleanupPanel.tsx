import { useT } from "../i18n";
import { localizedName } from "../i18n/settings";
import { Card } from "./ui/Card";
import { useState, useMemo } from "react";
import {
  Trash2,
  ChevronDown,
  ChevronRight,
  Loader2,
  type LucideIcon,
} from "lucide-react";
import { useStore } from "../store";
import { parseCleanupSize, parseSizeToMB, fmtMB } from "../lib/cleanupSize";
import { ActionRow } from "./ActionRow";
import type { CleanupRunner } from "../hooks/useCleanupRunner";
import type { Setting } from "../types/setting";

/** One heading's worth of cleanups: the games, the shader caches, the dev tools. */
interface CleanupGroup {
  id: string;
  label: string;
  order: number;
  rows: Setting[];
}

/**
 * Dynamic cleanup panel that reads action settings of a given module from the
 * store. No hardcoded options - all settings come from backend SSOT. Used for
 * both "System Cleanup" (module: cleanup) and "Game Maintenance" (module:
 * game_cleanup).
 *
 * Selection is shared via the store (maintenanceSelection) so the single
 * unified "Run Cleanup" button in the top band applies every selected action
 * across all panels. Each row is an <ActionRow/>, the one card an action has:
 * this panel groups and orders them and owns nothing about how one renders.
 *
 * The runner is passed in rather than built here, so the tab's Run button, the
 * per-row Run and the docker confirm are all one run — two runners would each
 * hold their own busy flag and their own modal.
 */
export function CleanupPanel({
  runner,
  initialCollapsed = true,
  module = "cleanup",
  title,
  icon: HeaderIcon = Trash2,
  description,
}: {
  runner: CleanupRunner;
  initialCollapsed?: boolean;
  module?: string;
  title?: string;
  icon?: LucideIcon;
  description?: string;
}) {
  const { t } = useT();
  const resolvedTitle = title ?? t("cleanup.systemTitle");
  const resolvedDescription = description ?? t("cleanup.systemDescription");
  const [isCollapsed, setIsCollapsed] = useState(initialCollapsed);
  const settings = useStore((state) => state.settings);
  const settingsVersion = useStore((state) => state._settingsVersion);

  // Cleanups whose size is known, largest first — and separately the ones still
  // being measured.
  //
  // They are split because the first scan answers `ready|calculating` for every
  // cleanup, including ones whose software is not installed, and the next scan
  // answers `not_available` for those — so twelve full rows used to appear and then
  // vanish. The backend is truthful at every step: it genuinely does not know yet.
  // What was wrong was presenting "not known" as a finished row. A name leaving a
  // group labelled "Measuring" reads as the answer it is (nothing to reclaim);
  // a row leaving the list reads as a glitch.
  //
  // Grouped, because a flat list put a Rust registry beside a Windows event log
  // beside a Modern Warfare crash dump and asked the user to tell them apart by
  // name. The heading is the backend's `groupLabel`, the same field the Game
  // Tweaks tab reads — a game's name is written down once, in Python.
  const { groups, measuring, readyCount } = useMemo(() => {
    const byGroup = new Map<string, { label: string; order: number; rows: Setting[] }>();
    const pending: Setting[] = [];
    let ready = 0;

    for (const setting of settings.values()) {
      if (setting.module !== module || !setting.isAction || !setting.isApplicable)
        continue;
      if (parseCleanupSize(setting.currentValue) === "calculating") {
        pending.push(setting);
        continue;
      }
      ready++;
      // A cleanup with no group is a backend that shipped one without a table
      // entry (its own red test). It is listed under "Other" rather than dropped.
      const groupId = setting.groupId ?? "other";
      let group = byGroup.get(groupId);
      if (!group) {
        group = {
          label: setting.groupLabel ?? "Other",
          order: setting.groupOrder ?? Number.MAX_SAFE_INTEGER,
          rows: [],
        };
        byGroup.set(groupId, group);
      }
      group.rows.push(setting);
    }

    const bySize = (a: Setting, b: Setting) => {
      const mbA = parseSizeToMB(a.currentValue);
      const mbB = parseSizeToMB(b.currentValue);
      if (mbA !== null && mbB !== null) return mbB - mbA;
      if (mbA !== null) return -1;
      if (mbB !== null) return 1;
      return a.categoryOrder - b.categoryOrder;
    };
    for (const group of byGroup.values()) group.rows.sort(bySize);
    pending.sort((a, b) => a.categoryOrder - b.categoryOrder);

    return {
      groups: Array.from(byGroup, ([id, group]) => ({ id, ...group })).sort(
        (a, b) => a.order - b.order || a.label.localeCompare(b.label),
      ),
      measuring: pending,
      readyCount: ready,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings, settingsVersion, module]);

  // If no cleanup settings, don't render
  if (readyCount === 0 && measuring.length === 0) {
    return null;
  }

  return (
    <Card>
      {/* Collapsible Header */}
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="w-full flex items-center justify-between p-4 hover:bg-muted/50 transition-colors rounded-lg"
      >
        <div className="flex items-center gap-2">
          <HeaderIcon className="w-5 h-5 text-primary" />
          <h3 className="font-semibold">{resolvedTitle}</h3>
        </div>
        {isCollapsed ? (
          <ChevronRight className="w-5 h-5 text-muted-foreground" />
        ) : (
          <ChevronDown className="w-5 h-5 text-muted-foreground" />
        )}
      </button>

      {/* Collapsible Content */}
      {!isCollapsed && (
        <div className="px-4 pb-4 flex flex-col max-h-[calc(100vh-12rem)]">
          <p className="text-sm text-muted-foreground mb-4">{resolvedDescription}</p>

          <div className="space-y-4 overflow-y-auto flex-1 pr-1">
            {groups.map((group) => (
              <section key={group.id} className="space-y-2">
                <GroupHeader group={group} />
                {/* Two panels already share the tab's width, so a row only gets a
                    neighbour once the window is wide enough for the half-panel to
                    hold two of them. */}
                <div
                  data-testid="cleanup-group-rows"
                  className="grid grid-cols-1 gap-2 items-start 3xl:grid-cols-2"
                >
                  {group.rows.map((setting) => (
                    <ActionRow
                      key={setting.id}
                      setting={setting}
                      runner={runner}
                      selectable
                    />
                  ))}
                </div>
              </section>
            ))}

            {measuring.length > 0 && (
              <div className="rounded-md border border-dashed border-border/70 p-3">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>
                    {t("cleanup.measuringMore", {
                      count: measuring.length,
                    })}
                  </span>
                </div>
                <p className="mt-1 text-xs text-muted-foreground/70">
                  {measuring.map((setting) => localizedName(setting)).join(", ")}
                </p>
                <p className="mt-1 text-xs text-muted-foreground/60">
                  {t("cleanup.measuringFootnote")}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

/**
 * A group's heading: what it is, how much it holds, and one checkbox for all of it.
 *
 * The size total is the sum of what the scan measured on this disk — the one place
 * in the product where adding numbers up is a measurement rather than a claim,
 * because each addend is a byte count an instrument returned.
 */
function GroupHeader({ group }: { group: CleanupGroup }) {
  const selection = useStore((state) => state.maintenanceSelection);
  const setSelection = useStore((state) => state.setMaintenanceSelection);

  const ids = group.rows.map((s) => s.id);
  const selectedCount = ids.filter((id) => selection[id]).length;
  const allSelected = selectedCount === ids.length && ids.length > 0;

  let totalMB = 0;
  let measured = 0;
  for (const setting of group.rows) {
    const mb = parseSizeToMB(setting.currentValue);
    if (mb === null) continue;
    totalMB += mb;
    measured++;
  }

  return (
    <div className="flex items-center gap-2 pt-1">
      <input
        type="checkbox"
        checked={allSelected}
        // Some but not all: the box shows neither state, so it says so rather
        // than reading as "none selected".
        ref={(el) => {
          if (el) el.indeterminate = selectedCount > 0 && !allSelected;
        }}
        onChange={() => setSelection(ids, !allSelected)}
        aria-label={`Select all in ${group.label}`}
        className="h-3.5 w-3.5 rounded border-border text-primary"
      />
      <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
        {group.label}
      </h4>
      <span className="text-xs text-muted-foreground/60">{group.rows.length}</span>
      {measured > 0 && totalMB > 0 && (
        <span className="text-xs text-primary/80">{fmtMB(totalMB)}</span>
      )}
      <div className="flex-1 h-px bg-border" />
    </div>
  );
}

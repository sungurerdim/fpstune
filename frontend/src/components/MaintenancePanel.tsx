import { useT } from "../i18n";
import { Button } from "./ui/Button";
import { Card } from "./ui/Card";
import { useMemo } from "react";
import { Wrench } from "lucide-react";
import { useStore } from "../store";
import { useCleanupRunner } from "../hooks/useCleanupRunner";
import { ActionRow } from "./ActionRow";
import type { Setting } from "../types/setting";

/**
 * The repair actions — SFC and DISM — with their Run button in their own header.
 *
 * Three things were wrong with the previous layout and all three were visible only
 * on screen. The Run button and the results readout lived in a separate top band
 * that floated to the right of an empty half-screen, so the control said "Select
 * items below" while the items sat at the bottom left. The panel collapsed itself,
 * on the tab where it is the only content. And each action printed its purpose
 * twice — "Scan and repair Windows system files." and then, with an info icon,
 * "Scans and repairs corrupted Windows system files" — because `effect` restates
 * `description` for an action, where "what it does" and "what running it does" are
 * the same sentence. <ActionRow/> keeps that third one fixed: it suppresses the
 * effect line under the `warning` accent, which is what marks a repair.
 *
 * The results readout is gone from the header too, and not because it was
 * unwanted: each repair now reports its own outcome in its own row, so a second
 * list of copies beside them said the same thing twice. Repairs free nothing,
 * so there is no total to keep.
 *
 * `excludeIds` is the other half of that rule, across panels rather than within
 * one. Home lists maintenance that is *overdue* in its own to-do card — an SSD
 * retrim that has not run is something to do, not something to look up — and a
 * page holding both surfaces would otherwise carry that action twice, with two
 * Run buttons and two checkboxes under one name. The page that already listed
 * it says so; the Cleanup & Repair tab passes nothing and lists everything.
 */
export function MaintenancePanel({
  excludeIds = [],
}: {
  /** Action ids this page has already listed elsewhere. */
  excludeIds?: readonly string[];
} = {}) {
  const { t } = useT();
  const settings = useStore((state) => state.settings);
  const settingsVersion = useStore((state) => state._settingsVersion);
  const runner = useCleanupRunner({ modules: ["maintenance"] });

  const excluded = useMemo(() => new Set(excludeIds), [excludeIds]);

  const maintenanceSettings = useMemo(() => {
    const result: Setting[] = [];
    for (const setting of settings.values()) {
      if (
        setting.module === "maintenance" &&
        setting.isAction &&
        setting.isApplicable &&
        !excluded.has(setting.id)
      ) {
        result.push(setting);
      }
    }
    return result.sort((a, b) => a.categoryOrder - b.categoryOrder);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings, settingsVersion, excluded]);

  if (maintenanceSettings.length === 0) {
    return null;
  }

  return (
    <Card>
      <div className="flex items-center gap-3 p-4 border-b border-border flex-wrap">
        <Wrench className="w-5 h-5 text-warning shrink-0" />
        <div className="min-w-0">
          <h3 className="font-semibold">{t("maintenance.title")}</h3>
          <p className="text-xs text-muted-foreground">
            {t("maintenance.description")}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-3 min-w-0">
          <Button
            size="md"
            className="shrink-0"
            busy={runner.isRunning}
            disabled={!runner.hasSelection}
            icon={<Wrench className="w-4 h-4" />}
            onClick={() => runner.run()}
          >
            {runner.isRunning
              ? t("maintenance.running")
              : runner.hasSelection
                ? t("maintenance.runCount", { count: runner.selectedCount })
                : t("maintenance.run")}
          </Button>
        </div>
      </div>

      {/* SFC and DISM are two self-contained cards; on a wide window they sat one
          under the other with the whole right half empty. */}
      <div
        data-testid="maintenance-rows"
        className="p-4 grid grid-cols-1 gap-3 items-start lg:grid-cols-2"
      >
        {maintenanceSettings.map((setting) => (
          <ActionRow
            key={setting.id}
            setting={setting}
            runner={runner}
            selectable
            accent="warning"
          />
        ))}
      </div>
    </Card>
  );
}

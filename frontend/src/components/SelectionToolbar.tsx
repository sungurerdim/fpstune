/**
 * SelectionToolbar — sticky bottom bar for the selection scope.
 * Appears when ≥1 setting is selected; its actions are the same `ScopeActions`
 * every other scope uses, so Apply and Reset to default read and confirm
 * the same way here as on a device card or a page header.
 */

import { useT } from "../i18n";
import { useMemo } from "react";
import { X } from "lucide-react";
import { cn } from "../lib/utils";
import { useStore } from "../store";
import { useBulkStream } from "../hooks/useBulkStream";
import type { Setting, SettingId } from "../types/setting";
import { ScopeActions } from "./ScopeActions";

export function SelectionToolbar() {
  const { t } = useT();
  const selectedSettingIds = useStore((s) => s.selectedSettingIds);
  const clearSelection = useStore((s) => s.clearSelection);
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const { isRunning } = useBulkStream();

  const selected = useMemo(
    () =>
      [...selectedSettingIds]
        .map((id) => settings.get(id as SettingId))
        .filter((s): s is Setting => s !== undefined),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
    [selectedSettingIds, settings, settingsVersion],
  );

  if (selectedSettingIds.size === 0) return null;
  const label = t("toolbar.selected", { count: selectedSettingIds.size });

  return (
    <div
      className={cn(
        "fixed bottom-0 left-0 right-0 z-50",
        "bg-card/95 backdrop-blur-xs border-t border-border",
        "px-6 py-3 flex flex-wrap items-center gap-3 shadow-lg",
      )}
    >
      <span className="text-sm font-medium text-foreground">{label}</span>

      <button
        onClick={clearSelection}
        disabled={isRunning}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
      >
        <X className="w-3.5 h-3.5" />
        {t("toolbar.clear")}
      </button>

      <ScopeActions settings={selected} name={label} className="ml-auto" />
    </div>
  );
}

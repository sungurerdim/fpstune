/**
 * TweakRowList — a run of rows with its read-only ones folded away.
 *
 * Writable rows list as they come; the read-only ones (things fpstune can
 * measure but only the user can change) wait behind a trailing "Manual steps
 * (N)", closed, and have no checkbox. Rows keep the order the caller gives
 * them: a row that moves after Apply puts the next click on a different setting.
 *
 * Presentational: settings and callbacks come in, nothing is read from the store.
 */

import { useId, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { useT } from "../i18n";
import { cn } from "../lib/utils";
import type { Setting } from "../types/setting";
import { TweakRow, type RowStatus } from "./TweakRow";

export interface TweakRowListProps {
  settings: readonly Setting[];
  onApply: (setting: Setting, value: unknown) => void;
  onReset: (setting: Setting) => void;
  selectedIds?: ReadonlySet<string>;
  /** Omit and the rows have no checkbox. */
  onSelect?: (setting: Setting) => void;
  statuses?: Readonly<Record<string, RowStatus>>;
  errors?: Readonly<Record<string, string>>;
  /** Extra text a row carries on its line, from the page that owns what it means. */
  rowNote?: (setting: Setting) => ReactNode;
}

export function TweakRowList({
  settings,
  onApply,
  onReset,
  selectedIds,
  onSelect,
  statuses,
  errors,
  rowNote,
}: TweakRowListProps) {
  const { t } = useT();
  const [manualOpen, setManualOpen] = useState(false);
  const manualId = useId();

  const rows = settings.filter((s) => !s.isReadonly);
  const manual = settings.filter((s) => s.isReadonly);

  const renderRow = (setting: Setting, selectable: boolean) => (
    <TweakRow
      key={setting.id}
      setting={setting}
      onApply={(value) => onApply(setting, value)}
      onReset={() => onReset(setting)}
      selected={selectedIds?.has(setting.id) ?? false}
      onSelect={selectable && onSelect ? () => onSelect(setting) : undefined}
      status={statuses?.[setting.id]}
      error={errors?.[setting.id]}
      note={rowNote?.(setting)}
    />
  );

  return (
    <>
      {rows.map((setting) => renderRow(setting, true))}

      {manual.length > 0 && (
        <div className="min-w-0 border-t border-border/40">
          <button
            type="button"
            aria-expanded={manualOpen}
            aria-controls={manualOpen ? manualId : undefined}
            onClick={() => setManualOpen((was) => !was)}
            className="flex w-full min-w-0 items-center gap-2 overflow-hidden px-2 py-1 text-left text-xs text-muted-foreground"
          >
            <ChevronRight
              className={cn(
                "h-3.5 w-3.5 shrink-0 transition-transform",
                manualOpen && "rotate-90",
              )}
              aria-hidden
            />
            <span className="min-w-0 truncate">
              {t("category.manualSteps", { count: manual.length })}
            </span>
          </button>
          {manualOpen && (
            <div id={manualId} className="min-w-0">
              {manual.map((setting) => renderRow(setting, false))}
            </div>
          )}
        </div>
      )}
    </>
  );
}

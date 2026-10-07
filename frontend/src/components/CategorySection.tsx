/**
 * CategorySection — a category folded to one line until it is asked for.
 *
 * Closed, it answers the first question on its own: "3 of 12 not optimized",
 * with the category's bulk action beside it. Open, it lists its rows (one line
 * each) and ends with a collapsed "Manual steps (N)" for the read-only rows —
 * things fpstune can measure but only the user can change — which are not
 * tweaks and so are not in the count.
 *
 * Presentational: settings and callbacks come in, nothing is read from the
 * store. Rows keep the order the caller gives them, because a row that moves
 * after Apply puts the next click on a different setting.
 */

import { useId, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { useT } from "../i18n";
import { cn } from "../lib/utils";
import type { Setting } from "../types/setting";
import { TweakRow, type RowStatus } from "./TweakRow";

export interface CategorySectionProps {
  /** The category's name, already in the active language. */
  title: string;
  settings: readonly Setting[];
  onApply: (setting: Setting, value: unknown) => void;
  onReset: (setting: Setting) => void;
  /** The header's bulk action. Sits beside the toggle, never inside it. */
  actions?: ReactNode;
  /** Closed unless the page has a reason to open it. */
  defaultOpen?: boolean;
  selectedIds?: ReadonlySet<string>;
  /** Omit and the rows have no checkbox. */
  onSelect?: (setting: Setting) => void;
  statuses?: Readonly<Record<string, RowStatus>>;
  errors?: Readonly<Record<string, string>>;
  /** Extra text a row carries on its line, from the page that owns what it means. */
  rowNote?: (setting: Setting) => ReactNode;
}

/**
 * What the header counts: tweaks that were read and apply to this machine.
 * A read-only row is a manual step, a cleanup is an action, a setting still
 * being read has no answer yet, and one that does not apply here cannot be
 * optimized — none of those is "not optimized".
 */
function categoryCounts(settings: readonly Setting[]) {
  let total = 0;
  let notOptimized = 0;
  let reading = 0;
  for (const s of settings) {
    if (s.isReadonly || s.isAction || !s.isApplicable) continue;
    if (s.status === "loading" && s.currentValue === null) {
      reading += 1;
      continue;
    }
    total += 1;
    if (!s.isOptimized) notOptimized += 1;
  }
  return { total, notOptimized, reading };
}

export function CategorySection({
  title,
  settings,
  onApply,
  onReset,
  actions,
  defaultOpen = false,
  selectedIds,
  onSelect,
  statuses,
  errors,
  rowNote,
}: CategorySectionProps) {
  const { t } = useT();
  const [open, setOpen] = useState(defaultOpen);
  const [manualOpen, setManualOpen] = useState(false);
  const headerId = useId();
  const bodyId = useId();
  const manualId = useId();

  const rows = settings.filter((s) => !s.isReadonly);
  const manual = settings.filter((s) => s.isReadonly);
  const { total, notOptimized, reading } = categoryCounts(settings);

  const summary =
    total > 0
      ? notOptimized > 0
        ? t("category.notOptimized", { count: notOptimized, total })
        : t("category.allOptimized", { total })
      : reading > 0
        ? t("category.detecting")
        : null;

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
    <div
      data-testid="category-section"
      data-open={String(open)}
      className="min-w-0 rounded-md border border-border"
    >
      <div className="flex min-w-0 items-center gap-2 px-2 py-1.5">
        <h3 className="min-w-0 flex-1 text-sm">
          <button
            type="button"
            id={headerId}
            aria-expanded={open}
            aria-controls={open ? bodyId : undefined}
            onClick={() => setOpen((was) => !was)}
            className="flex w-full min-w-0 items-center gap-2 overflow-hidden text-left"
          >
            <ChevronRight
              className={cn(
                "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
                open && "rotate-90",
              )}
              aria-hidden
            />
            <span className="min-w-0 truncate font-medium" title={title}>
              {title}
            </span>
            {/* The gap between the name and the count is CSS, which the
                accessible name does not see: without this text node it reads
                "Network2 of 3 not optimized". */}
            {" "}
            {summary && (
              <span
                data-testid="category-count"
                data-not-optimized={notOptimized}
                className={cn(
                  "shrink-0 text-xs whitespace-nowrap",
                  notOptimized > 0 ? "text-warning" : "text-muted-foreground",
                )}
              >
                {summary}
              </span>
            )}
          </button>
        </h3>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>

      {open && (
        <div
          id={bodyId}
          role="group"
          aria-labelledby={headerId}
          className="min-w-0 border-t border-border/40"
        >
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
        </div>
      )}
    </div>
  );
}

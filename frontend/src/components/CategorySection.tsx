/**
 * CategorySection — a category folded to one line until it is asked for.
 *
 * Closed, it answers the first question on its own: "3 of 12 not optimized",
 * with the category's bulk action beside it. Open, it lists its rows (one line
 * each) and ends with a collapsed "Manual steps (N)" for the read-only rows —
 * things fpstune can measure but only the user can change — which are not
 * tweaks and so are not in the count.
 *
 * A category made of groups rather than rows (Software's categories, Hardware's
 * devices, Games' games) passes them as `children`: the body then draws those,
 * and the count and the bulk action still read `settings` — every row inside.
 * `level` says which heading it is in the page's outline.
 *
 * Presentational: settings and callbacks come in, nothing is read from the
 * store. Rows keep the order the caller gives them, because a row that moves
 * after Apply puts the next click on a different setting.
 */

import { useId, useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { useT } from "../i18n";
import { tweakCounts } from "../lib/tweakStatus";
import { cn } from "../lib/utils";
import type { Setting } from "../types/setting";
import type { RowStatus } from "./TweakRow";
import { TweakRowList } from "./TweakRowList";

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
  /** Heading level in the page's outline: 3 under a page section, 2 for the section itself. */
  level?: 2 | 3;
  /** Groups to draw in the body instead of `settings`' own rows. */
  children?: ReactNode;
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
  level = 3,
  children,
}: CategorySectionProps) {
  const { t } = useT();
  const [open, setOpen] = useState(defaultOpen);
  const headerId = useId();
  const bodyId = useId();
  const Heading = level === 2 ? "h2" : "h3";
  const { total, notOptimized, reading } = tweakCounts(settings);

  const summary =
    total > 0
      ? notOptimized > 0
        ? t("category.notOptimized", { count: notOptimized, total })
        : t("category.allOptimized", { total })
      : reading > 0
        ? t("category.detecting")
        : null;

  return (
    <div
      data-testid="category-section"
      data-open={String(open)}
      className="min-w-0 rounded-md border border-border"
    >
      <div className="flex min-w-0 items-center gap-2 px-2 py-1.5">
        <Heading className="min-w-0 flex-1 text-sm">
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
            <span
              className={cn("min-w-0 truncate", level === 2 ? "font-semibold" : "font-medium")}
              title={title}
            >
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
        </Heading>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>

      {open && (
        <div
          id={bodyId}
          role="group"
          aria-labelledby={headerId}
          className={cn(
            "min-w-0 border-t border-border/40",
            children !== undefined && "space-y-1 p-1",
          )}
        >
          {children !== undefined ? (
            children
          ) : (
            <TweakRowList
              settings={settings}
              onApply={onApply}
              onReset={onReset}
              selectedIds={selectedIds}
              onSelect={onSelect}
              statuses={statuses}
              errors={errors}
              rowNote={rowNote}
            />
          )}
        </div>
      )}
    </div>
  );
}

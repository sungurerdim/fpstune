import { useT } from "../i18n";
import { localizedDescription, localizedName } from "../i18n/settings";
import { useState, useMemo } from "react";
import { Loader2, Search, type LucideIcon } from "lucide-react";
import { SelectionToolbar } from "./SelectionToolbar";
import { type TweakRow } from "./TweakRows";
import { TweakBands } from "./TweakBands";
import { ScopeActions } from "./ScopeActions";
import { Metric, MetricList, ScopeHeader } from "./ui/ScopeHeader";
import { isSoftwareTweak } from "../lib/tweakDomain";
import { isTweakSuboptimal } from "../lib/tweakStatus";
import { DetectionNotice } from "./DetectionNotice";
import { cn } from "../lib/utils";
import type { Setting, CategoryMetadata, ModuleMetadata } from "../types/setting";

interface SettingsTabProps {
  categoriesWithSettings: Array<{
    category: CategoryMetadata;
    settings: Setting[];
  }>;
  moduleMetaMap: Map<string, ModuleMetadata>;
  definitionsLoading: boolean;
  gpuCategoryStatus: string | undefined;
  hasGpuSettings: boolean;
  getIconByName: (name: string) => LucideIcon;
}

/** One category heading's worth of rows, after search and filter. */
interface CategoryGroup {
  category: CategoryMetadata;
  rows: TweakRow[];
  settings: Setting[];
  toFix: number;
}

/**
 * Software Tweaks — rows under category headings, each stating `current -> ideal`
 * with its fix attached to the row.
 *
 * One filter bar: a search and one row of category chips. The impact of a row
 * (latency, fps, heat) is a label on the row itself rather than a second filter,
 * so there is one way to narrow the page and the headings still say where a row
 * belongs. Each heading carries its own Apply / Reset to default; the page
 * header carries the same three over exactly the rows the filters leave on screen.
 *
 * Advisory (`is_readonly`) settings live in the same list. They are the settings
 * fpstune can observe and cannot write, and a diagnostic nobody can find is the
 * same as no diagnostic; the row carries an "Advisory" badge in place of a control.
 */
export function SettingsTab({
  categoriesWithSettings,
  moduleMetaMap,
  definitionsLoading,
  gpuCategoryStatus,
  hasGpuSettings,
  getIconByName,
}: SettingsTabProps) {
  const { t } = useT();
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");

  const { groups, chips, total } = useMemo(() => {
    const visible: CategoryGroup[] = [];
    // Counted over what the search admits, so a chip never offers a filter that
    // would empty the list.
    const options: Array<{ category: CategoryMetadata; count: number }> = [];
    let all = 0;
    const q = searchQuery.trim().toLowerCase();

    for (const { category, settings } of categoriesWithSettings) {
      // Actions have no state to be ideal or not; they live in Maintenance.
      if (category.isActionOnly) continue;
      // A machine with no GPU settings should not show an empty GPU section, but
      // only once detection has finished — before that, absence is not an answer.
      if (category.id === "gpu" && gpuCategoryStatus === "done" && !hasGpuSettings) continue;

      const CategoryIcon = getIconByName(category.icon);
      const rows: TweakRow[] = [];
      for (const s of settings) {
        if (!s.isApplicable || s.isAction) continue;
        // Games and hardware are their own tabs. Excluded by the domain
        // predicate rather than by category, because the category is what a
        // setting *is* and this is a question about which screen owns it.
        if (!isSoftwareTweak(s)) continue;
        // Nothing read yet: "ideal or not" is unknown, and putting it in either
        // band would assert a result the app does not have.
        if (s.currentValue === null) continue;
        if (
          q &&
          !s.displayName.toLowerCase().includes(q) &&
          !s.name.toLowerCase().includes(q) &&
          !s.description.toLowerCase().includes(q) &&
          !localizedName(s).toLowerCase().includes(q) &&
          !localizedDescription(s).toLowerCase().includes(q)
        )
          continue;

        // The heading names the category; the row adds the module only where
        // it says something the heading does not.
        const moduleLabel = moduleMetaMap.get(s.module)?.displayName ?? s.module;
        const sameAsHeading = moduleLabel === category.displayName;
        rows.push({
          setting: s,
          contextLabel: sameAsHeading ? undefined : moduleLabel,
          // Nothing is created here: getIconByName is a lookup into a fixed
          // table of lucide components, so CategoryIcon is a stable reference and
          // remounts nothing. The rule cannot see through the indirection.
          contextIcon: sameAsHeading ? undefined : (
            // eslint-disable-next-line react-hooks/static-components -- a lookup, not a definition
            <CategoryIcon className="w-3 h-3 text-primary/70 shrink-0" />
          ),
        });
      }
      if (rows.length === 0) continue;

      options.push({ category, count: rows.length });
      all += rows.length;
      if (categoryFilter !== "all" && category.id !== categoryFilter) continue;
      const members = rows.map((r) => r.setting);
      visible.push({
        category,
        rows,
        settings: members,
        toFix: members.filter(isTweakSuboptimal).length,
      });
    }

    return { groups: visible, chips: options, total: all };
  }, [
    categoriesWithSettings,
    moduleMetaMap,
    getIconByName,
    searchQuery,
    categoryFilter,
    gpuCategoryStatus,
    hasGpuSettings,
  ]);
  const visibleSettings = useMemo(() => groups.flatMap((g) => g.settings), [groups]);

  const chipClass = (active: boolean) =>
    cn(
      "text-xs px-2 py-0.5 rounded-full border transition-colors",
      active
        ? "bg-primary/15 text-primary border-primary/40"
        : "text-muted-foreground border-border hover:border-muted-foreground/50",
    );

  return (
    <div className="space-y-4 pb-16">
      <DetectionNotice owns={isSoftwareTweak} />
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="search"
            placeholder={t("settings.searchPlaceholder")}
            aria-label={t("settings.search")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-muted border border-border rounded-md text-foreground placeholder:text-muted-foreground"
          />
        </div>
        {definitionsLoading && <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />}
        {/* Page scope: exactly the rows the filters leave on screen. */}
        <ScopeActions settings={visibleSettings} name={t("tab.software")} className="ml-auto" />
      </div>

      {chips.length > 0 && (
        <div
          className="flex items-center gap-1.5 flex-wrap"
          role="group"
          aria-label={t("settings.filterByCategory")}
        >
          <button
            type="button"
            onClick={() => setCategoryFilter("all")}
            aria-pressed={categoryFilter === "all"}
            className={chipClass(categoryFilter === "all")}
          >
            {t("settings.allCategories")}
            <span className="ml-1 opacity-60">{total}</span>
          </button>
          {chips.map(({ category, count }) => (
            <button
              key={category.id}
              type="button"
              onClick={() =>
                setCategoryFilter(categoryFilter === category.id ? "all" : category.id)
              }
              aria-pressed={categoryFilter === category.id}
              className={chipClass(categoryFilter === category.id)}
            >
              {category.displayName}
              <span className="ml-1 opacity-60">{count}</span>
            </button>
          ))}
        </div>
      )}

      {definitionsLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-12 bg-muted rounded-md animate-pulse" />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("bands.nothingToDo")}</p>
      ) : (
        groups.map((group) => (
          <CategorySection
            key={group.category.id}
            group={group}
            icon={getIconByName(group.category.icon)}
          />
        ))
      )}

      <SelectionToolbar />
    </div>
  );
}

/** One category: heading, its own scope actions, then its rows in the shared bands. */
function CategorySection({ group, icon: Icon }: { group: CategoryGroup; icon: LucideIcon }) {
  const { t } = useT();
  const headingId = `settings-category-${group.category.id}`;
  return (
    <section
      aria-labelledby={headingId}
      className={cn(
        "rounded-lg border p-4 space-y-3",
        group.toFix > 0 ? "border-warning/30 bg-warning/4" : "border-border",
      )}
    >
      <ScopeHeader
        level={2}
        headingId={headingId}
        icon={<Icon className="h-4 w-4 text-primary/80" aria-hidden />}
        title={group.category.displayName}
        metrics={
          <MetricList>
            <Metric
              tone={group.toFix > 0 ? "attention" : "ok"}
              value={group.toFix}
              label={t("metric.toFix")}
            />
            <Metric value={group.rows.length} label={t("metric.total")} />
          </MetricList>
        }
        actions={<ScopeActions settings={group.settings} name={group.category.displayName} />}
      />
      <TweakBands rows={group.rows} />
    </section>
  );
}

import { useT } from "../i18n";
import { localizedDescription, localizedName } from "../i18n/settings";
import { useState, useMemo } from "react";
import {
  Loader2,
  Search,
  type LucideIcon,
} from "lucide-react";
import { SelectionToolbar } from "./SelectionToolbar";
import { type TweakRow } from "./TweakRows";
import { TweakBands } from "./TweakBands";
import { ScopeActions } from "./ScopeActions";
import { isSoftwareTweak } from "../lib/tweakDomain";
import { DetectionNotice } from "./DetectionNotice";
import { cn } from "../lib/utils";
import { IMPACT_CATEGORY_META } from "../types/setting";
import type {
  Setting,
  CategoryMetadata,
  ImpactCategory,
  ModuleMetadata,
} from "../types/setting";

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

/**
 * Software Tweaks — a flat list of tweaks, each stating `current -> ideal` with its
 * fix attached to the row.
 *
 * The previous shape put four levels between the user and a setting: band ->
 * category -> module card -> expand. On a 1600px screen that showed six module
 * cards and zero actual tweaks, three of the cards wrapping a single card each,
 * and the same module appearing in both bands. This is the Hardware page's shape
 * instead: read the row, see what is wrong, press Fix.
 *
 * Advisory (`is_readonly`) settings live in the same list rather than a separate
 * screen. They are the settings fpstune can observe and cannot write — a link
 * negotiated below the adapter's capability, an XMP profile left off — and a
 * diagnostic nobody can find is the same as no diagnostic. The row simply carries
 * an "Advisory" badge in place of a control.
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
  // Filters by the kind of gain rather than the subsystem. "Which of these are
  // actually latency tweaks?" was unanswerable from this screen even though the
  // dashboard header counted them.
  const [impactFilter, setImpactFilter] = useState<ImpactCategory | "all">(
    "all",
  );

  const { rows, categoryOptions, impactCounts } = useMemo(() => {
    const listed: TweakRow[] = [];
    const options: CategoryMetadata[] = [];
    const q = searchQuery.trim().toLowerCase();
    // Counted over everything the other filters admit, so a chip never offers a
    // filter that would empty the list.
    const counts = new Map<ImpactCategory, number>();

    for (const { category, settings } of categoriesWithSettings) {
      // Actions have no state to be ideal or not; they live in Maintenance.
      if (category.isActionOnly) continue;
      // A machine with no GPU settings should not show an empty GPU section, but
      // only once detection has finished — before that, absence is not an answer.
      if (
        category.id === "gpu" &&
        gpuCategoryStatus === "done" &&
        !hasGpuSettings
      )
        continue;

      options.push(category);
      if (categoryFilter !== "all" && category.id !== categoryFilter) continue;

      const CategoryIcon = getIconByName(category.icon);

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

        // Defaulted rather than assumed: a Setting rehydrated from a cache
        // written by an older build has no impactCategories, and an undefined
        // here would take down the whole tab rather than drop one tag.
        const impacts = s.impactCategories ?? [];
        for (const c of impacts) counts.set(c, (counts.get(c) ?? 0) + 1);
        if (impactFilter !== "all" && !impacts.includes(impactFilter)) continue;

        const moduleLabel =
          moduleMetaMap.get(s.module)?.displayName ?? s.module;
        const row: TweakRow = {
          setting: s,
          contextLabel:
            moduleLabel === category.displayName
              ? category.displayName
              : `${category.displayName} · ${moduleLabel}`,
          // Nothing is created here: getIconByName is a lookup into lucide's
          // own module exports, so CategoryIcon is a stable reference and
          // remounts nothing. The rule cannot see through the indirection.
          contextIcon: (
            // eslint-disable-next-line react-hooks/static-components -- a lookup, not a definition
            <CategoryIcon className="w-3 h-3 text-primary/70 shrink-0" />
          ),
        };
        listed.push(row);
      }
    }

    return {
      rows: listed,
      categoryOptions: options,
      impactCounts: counts,
    };
  }, [
    impactFilter,
    categoriesWithSettings,
    moduleMetaMap,
    getIconByName,
    searchQuery,
    categoryFilter,
    gpuCategoryStatus,
    hasGpuSettings,
  ]);
  const visibleSettings = useMemo(() => rows.map((r) => r.setting), [rows]);

  return (
    <div className="space-y-4 pb-16">
      <DetectionNotice owns={isSoftwareTweak} />
      {/* Filter bar: the only navigation this screen needs now that the rows are flat. */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="search"
            placeholder="Search settings..."
            aria-label="Search settings"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-muted border border-border rounded-md text-foreground placeholder:text-muted-foreground"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          aria-label="Filter by category"
          className="py-1.5 px-2 text-xs bg-muted border border-border rounded-md text-foreground"
        >
          <option value="all">All categories</option>
          {categoryOptions.map((c) => (
            <option key={c.id} value={c.id}>
              {c.displayName}
            </option>
          ))}
        </select>
        {definitionsLoading && (
          <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
        )}
        {/* Page scope: exactly the rows the filters leave on screen. */}
        <ScopeActions
          settings={visibleSettings}
          name={t("tab.software")}
          className="ml-auto"
        />
      </div>

      {impactCounts.size > 0 && (
        <div
          className="flex items-center gap-1.5 flex-wrap"
          role="group"
          aria-label="Filter by impact"
        >
          <button
            type="button"
            onClick={() => setImpactFilter("all")}
            aria-pressed={impactFilter === "all"}
            className={cn(
              "text-xs px-2 py-0.5 rounded-full border transition-colors",
              impactFilter === "all"
                ? "bg-primary/15 text-primary border-primary/40"
                : "text-muted-foreground border-border hover:border-muted-foreground/50",
            )}
          >
            All impacts
          </button>
          {/* Driven by IMPACT_CATEGORY_META order, not by Map insertion order,
              so the chips do not reshuffle as detection fills in. */}
          {(Object.keys(IMPACT_CATEGORY_META) as ImpactCategory[]).map((c) =>
            impactCounts.has(c) ? (
              <button
                key={c}
                type="button"
                data-category={c}
                onClick={() => setImpactFilter(impactFilter === c ? "all" : c)}
                aria-pressed={impactFilter === c}
                className={cn(
                  "text-xs px-2 py-0.5 rounded-full border transition-colors",
                  impactFilter === c
                    ? IMPACT_CATEGORY_META[c].className
                    : "text-muted-foreground border-border hover:border-muted-foreground/50",
                )}
              >
                {t(IMPACT_CATEGORY_META[c].labelKey)}
                <span className="ml-1 opacity-60">{impactCounts.get(c)}</span>
              </button>
            ) : null,
          )}
        </div>
      )}

      {definitionsLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-12 bg-muted rounded-md animate-pulse" />
          ))}
        </div>
      ) : (
        <TweakBands rows={rows} />
      )}

      <SelectionToolbar />
    </div>
  );
}

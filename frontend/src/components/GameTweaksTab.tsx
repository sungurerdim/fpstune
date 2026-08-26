import { useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Gamepad2,
  Loader2,
  Search,
  Zap,
} from "lucide-react";
import { SelectionToolbar } from "./SelectionToolbar";
import { TweakRows, type TweakRow } from "./TweakRows";
import { useBulkApply } from "../hooks/useBulkApply";
import { useStore } from "../store";
import { isGameTweak } from "../lib/tweakDomain";
import { cn } from "../lib/utils";
import type { Setting } from "../types/setting";

/** One game's settings, split by whether they are already where they should be. */
interface GameSection {
  id: string;
  label: string;
  order: number;
  needs: TweakRow[];
  optimized: TweakRow[];
}

/**
 * Game Tweaks — the settings that live in a game's own config file, one section
 * per game.
 *
 * These 181 settings used to sit inside Software Tweaks under a single "Game
 * Configs" category, which is all the backend could say about them: `module` is
 * the first segment of the id, so every game collapses to `game_config`. The
 * heading a section renders now comes from the setting's own `groupLabel`, which
 * the backend resolves from the one place a game's name is written down — so
 * adding a game adds a section here with no frontend change at all.
 *
 * Sections rather than a flat list because these settings are only comparable
 * within one game: "Shadow Quality" means a different thing, in a different
 * config file, in each of them, and a bulk apply that spanned two games would
 * write two files for one press.
 */
export function GameTweaksTab() {
  const settings = useStore((state) => state.settings);
  const settingsVersion = useStore((state) => state._settingsVersion);
  const detecting = useStore((state) => state.isAnyCategoryLoading());
  const [searchQuery, setSearchQuery] = useState("");
  const [gameFilter, setGameFilter] = useState("all");

  const { sections, gameOptions, hiddenBySearch } = useMemo(() => {
    const byGame = new Map<string, GameSection>();
    const options = new Map<string, string>();
    const q = searchQuery.trim().toLowerCase();
    let hidden = 0;

    for (const s of settings.values() as Iterable<Setting>) {
      if (!isGameTweak(s) || !s.isApplicable || s.isAction) continue;
      // Nothing read yet: "ideal or not" is unknown, and putting it in either
      // band would assert a result the app does not have.
      if (s.currentValue === null) continue;

      // A game with no group would be a backend that shipped a game without a
      // label; it is listed under its own id rather than dropped, because a
      // setting the user cannot find is worse than an ugly heading.
      const groupId = s.groupId ?? s.module;
      const groupLabel = s.groupLabel ?? groupId;
      options.set(groupId, groupLabel);
      if (gameFilter !== "all" && groupId !== gameFilter) continue;

      if (
        q &&
        !s.displayName.toLowerCase().includes(q) &&
        !s.name.toLowerCase().includes(q) &&
        !s.description.toLowerCase().includes(q)
      ) {
        hidden++;
        continue;
      }

      let section = byGame.get(groupId);
      if (!section) {
        section = {
          id: groupId,
          label: groupLabel,
          order: s.groupOrder ?? Number.MAX_SAFE_INTEGER,
          needs: [],
          optimized: [],
        };
        byGame.set(groupId, section);
      }
      (s.isOptimized ? section.optimized : section.needs).push({ setting: s });
    }

    const ordered = Array.from(byGame.values()).sort(
      (a, b) => a.order - b.order || a.label.localeCompare(b.label),
    );
    for (const section of ordered) {
      const byName = (a: TweakRow, b: TweakRow) =>
        a.setting.categoryOrder - b.setting.categoryOrder ||
        a.setting.displayName.localeCompare(b.setting.displayName);
      section.needs.sort(byName);
      section.optimized.sort(byName);
    }

    return {
      sections: ordered,
      gameOptions: Array.from(options, ([id, label]) => ({ id, label })).sort(
        (a, b) => a.label.localeCompare(b.label),
      ),
      hiddenBySearch: hidden,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settings, settingsVersion, searchQuery, gameFilter]);

  return (
    <div className="space-y-4 pb-16">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="search"
            placeholder="Search game settings..."
            aria-label="Search game settings"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-muted border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground"
          />
        </div>
        <select
          value={gameFilter}
          onChange={(e) => setGameFilter(e.target.value)}
          aria-label="Filter by game"
          className="py-1.5 px-2 text-xs bg-muted border border-border rounded-md focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
        >
          <option value="all">All games</option>
          {gameOptions.map((game) => (
            <option key={game.id} value={game.id}>
              {game.label}
            </option>
          ))}
        </select>
        {detecting && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Reading your game configs…
          </span>
        )}
      </div>

      {sections.length === 0 ? (
        // Three different states, and saying the wrong one is a false claim: still
        // reading, filtered to nothing, or no supported game installed.
        <p className="text-sm text-muted-foreground">
          {detecting
            ? "Reading your game configs…"
            : hiddenBySearch > 0
              ? "No game setting matches that search."
              : "No supported game config was found on this machine. fpstune reads a game's config only where the game is installed."}
        </p>
      ) : (
        sections.map((section) => (
          <GameSectionCard key={section.id} section={section} />
        ))
      )}

      <SelectionToolbar />
    </div>
  );
}

/**
 * One game: what still needs applying, with an apply scoped to that game alone,
 * and its already-correct settings behind a fold.
 */
function GameSectionCard({ section }: { section: GameSection }) {
  const { apply, isApplying, lastResult } = useBulkApply();
  const [showOptimized, setShowOptimized] = useState(false);

  // Advisory rows are reported, never applied: fpstune can read the state and
  // cannot write it, so counting them into "Apply all" would promise a write.
  const fixable = section.needs.filter((r) => !r.setting.isReadonly);

  const applyAll = () => {
    const payload: Record<string, unknown> = {};
    for (const { setting } of fixable) payload[setting.id] = setting.recommendedValue;
    if (Object.keys(payload).length > 0) apply(payload);
  };

  return (
    <section className="rounded-lg border border-border bg-card p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <Gamepad2 className="w-4 h-4 text-primary" />
        <h2 className="text-sm font-bold">{section.label}</h2>
        <span
          className={cn(
            "text-xs",
            section.needs.length > 0 ? "text-warning" : "text-success",
          )}
        >
          {section.needs.length > 0
            ? `${section.needs.length} to apply`
            : "all applied"}
        </span>
        <span className="text-xs text-muted-foreground/60">
          · {section.needs.length + section.optimized.length} settings
        </span>
        {lastResult && (
          <span className="text-xs text-muted-foreground">
            {lastResult.success} applied
            {lastResult.error > 0 && (
              <span className="text-destructive"> · {lastResult.error} failed</span>
            )}
          </span>
        )}
        {fixable.length > 0 && (
          <button
            type="button"
            onClick={applyAll}
            disabled={isApplying}
            className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium bg-warning/15 text-warning hover:bg-warning/25 disabled:opacity-50 transition-colors"
          >
            {isApplying ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Zap className="w-3.5 h-3.5" />
            )}
            Apply all {fixable.length}
          </button>
        )}
      </div>

      {section.needs.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-3.5 h-3.5 text-warning" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-warning">
              Needs optimization
            </h3>
          </div>
          <TweakRows rows={section.needs} />
        </div>
      )}

      {section.optimized.length > 0 && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setShowOptimized(!showOptimized)}
            className="flex items-center gap-2 w-full text-left"
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-success" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-success">
              Optimized
            </h3>
            <span className="text-xs text-muted-foreground/60">
              ({section.optimized.length})
            </span>
            <span className="ml-auto text-muted-foreground">
              {showOptimized ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </span>
          </button>
          {showOptimized && <TweakRows rows={section.optimized} />}
        </div>
      )}
    </section>
  );
}

import { useT } from "../i18n";
import { localizedDescription, localizedName } from "../i18n/settings";
import { useMemo, useState } from "react";
import { Gamepad2, Loader2, Search } from "lucide-react";
import { SelectionToolbar } from "./SelectionToolbar";
import { type TweakRow } from "./TweakRows";
import { TweakBands } from "./TweakBands";
import { ScopeActions } from "./ScopeActions";
import { Metric, MetricList, ScopeHeader } from "./ui/ScopeHeader";
import { useStore } from "../store";
import { DetectionNotice } from "./DetectionNotice";
import { isGameTweak } from "../lib/tweakDomain";
import { isTweakSuboptimal } from "../lib/tweakStatus";
import { cn } from "../lib/utils";
import type { Setting } from "../types/setting";

/** One game's settings, in the order its config file's own copy ranks them. */
interface GameSection {
  id: string;
  label: string;
  order: number;
  rows: TweakRow[];
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
  const { t } = useT();
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
        !s.description.toLowerCase().includes(q) &&
        !localizedName(s).toLowerCase().includes(q) &&
        !localizedDescription(s).toLowerCase().includes(q)
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
          rows: [],
        };
        byGame.set(groupId, section);
      }
      section.rows.push({ setting: s });
    }

    const ordered = Array.from(byGame.values()).sort(
      (a, b) => a.order - b.order || a.label.localeCompare(b.label),
    );
    for (const section of ordered) {
      section.rows.sort(
        (a, b) =>
          a.setting.categoryOrder - b.setting.categoryOrder ||
          a.setting.displayName.localeCompare(b.setting.displayName),
      );
    }

    return {
      sections: ordered,
      gameOptions: Array.from(options, ([id, label]) => ({ id, label })).sort((a, b) =>
        a.label.localeCompare(b.label),
      ),
      hiddenBySearch: hidden,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settings, settingsVersion, searchQuery, gameFilter]);
  const visibleSettings = useMemo(
    () => sections.flatMap((section) => section.rows.map((r) => r.setting)),
    [sections],
  );

  const chipClass = (active: boolean) =>
    cn(
      "text-xs px-2 py-0.5 rounded-full border transition-colors",
      active
        ? "bg-primary/15 text-primary border-primary/40"
        : "text-muted-foreground border-border hover:border-muted-foreground/50",
    );

  return (
    <div className="space-y-4 pb-16">
      <DetectionNotice owns={isGameTweak} />
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="search"
            placeholder={t("games.searchPlaceholder")}
            aria-label={t("games.searchLabel")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-muted border border-border rounded-md text-foreground placeholder:text-muted-foreground"
          />
        </div>
        {detecting && (
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            {t("games.reading")}
          </span>
        )}
        {/* Page scope: exactly the games and rows the filters leave on screen. */}
        <ScopeActions settings={visibleSettings} name={t("tab.games")} className="ml-auto" />
      </div>

      {gameOptions.length > 1 && (
        <div className="flex items-center gap-1.5 flex-wrap" role="group" aria-label={t("games.filterGame")}>
          <button
            type="button"
            onClick={() => setGameFilter("all")}
            aria-pressed={gameFilter === "all"}
            className={chipClass(gameFilter === "all")}
          >
            {t("games.allGames")}
          </button>
          {gameOptions.map((game) => (
            <button
              key={game.id}
              type="button"
              onClick={() => setGameFilter(gameFilter === game.id ? "all" : game.id)}
              aria-pressed={gameFilter === game.id}
              className={chipClass(gameFilter === game.id)}
            >
              {game.label}
            </button>
          ))}
        </div>
      )}

      {sections.length === 0 ? (
        // Three different states, and saying the wrong one is a false claim: still
        // reading, filtered to nothing, or no supported game installed.
        <p className="text-sm text-muted-foreground">
          {detecting
            ? t("games.reading")
            : hiddenBySearch > 0
              ? t("games.noMatch")
              : t("games.noneFound")}
        </p>
      ) : (
        sections.map((section) => <GameSectionCard key={section.id} section={section} />)
      )}

      <SelectionToolbar />
    </div>
  );
}

/**
 * One game: its heading and count, Apply / Undo / Windows default scoped to that
 * game alone — a press never writes two games' files — then its rows.
 */
function GameSectionCard({ section }: { section: GameSection }) {
  const { t } = useT();
  const members = section.rows.map((r) => r.setting);
  const toApply = members.filter(isTweakSuboptimal).length;
  const headingId = `game-${section.id}`;

  return (
    <section
      aria-labelledby={headingId}
      className={cn(
        "rounded-lg border border-border border-l-4 bg-card p-4 space-y-3",
        toApply > 0 ? "border-l-warning" : "border-l-success",
      )}
    >
      <ScopeHeader
        level={2}
        headingId={headingId}
        icon={<Gamepad2 className="h-4 w-4 text-primary" aria-hidden />}
        title={section.label}
        metrics={
          <MetricList>
            <Metric
              tone={toApply > 0 ? "attention" : "ok"}
              value={toApply}
              label={t("metric.toFix")}
            />
            <Metric value={members.length} label={t("metric.total")} />
          </MetricList>
        }
        actions={<ScopeActions settings={members} name={section.label} />}
      />
      <TweakBands rows={section.rows} />
    </section>
  );
}

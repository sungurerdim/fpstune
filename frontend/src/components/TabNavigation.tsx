import { setLocale, useT } from "../i18n";
import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import { useMemo, useRef, type KeyboardEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Home,
  Settings,
  HardDrive,
  Monitor,
  Gamepad2,
  Gauge,
  Activity,
  ShieldCheck,
  ShieldAlert,
} from "lucide-react";
import { cn } from "../lib/utils";
import { api } from "../lib/api";
import { useStore, type TabId } from "../store";
import { isGameTweak, isHardwareTweak } from "../lib/tweakDomain";
import { ActivityLog } from "./ActivityLog";
import { tabButtonId, tabPanelId } from "./ui/tabIds";

// Order follows what the user does, not what the app builds: tune the software,
// then the hardware it runs on, then the games themselves, then clean up, then
// measure the result. "Optimizations" said nothing about what was being
// optimized, which left the Hardware tab looking like a different kind of thing
// rather than its pair.
//
// Game Tweaks is its own tab because it is its own domain, not a category of
// software: those settings are written into a game's file rather than into
// Windows, and there are more of them than of everything on the Software tab.
import type { MessageKey } from "../i18n/en";

const tabs: Array<{ id: TabId; labelKey: MessageKey; icon: typeof Settings }> = [
  { id: "home", labelKey: "tab.home", icon: Home },
  { id: "settings", labelKey: "tab.software", icon: Settings },
  { id: "hardware", labelKey: "tab.hardware", icon: Monitor },
  { id: "games", labelKey: "tab.games", icon: Gamepad2 },
  { id: "cleanup", labelKey: "tab.cleanup", icon: HardDrive },
  { id: "benchmarks", labelKey: "tab.benchmarks", icon: Gauge },
];

export function TabNavigation() {
  const activeTab = useStore((state) => state.activeTab);
  const setActiveTab = useStore((state) => state.setActiveTab);
  const settingsMap = useStore((state) => state.settings);
  const settingsVersion = useStore((state) => state._settingsVersion);

  const { t, locale } = useT();
  const { data: systemInfo } = useQuery({
    queryKey: ["system"],
    queryFn: api.getSystemInfo,
    staleTime: Infinity, // OS/admin info doesn't change during session
  });

  const tabRefs = useRef(new Map<TabId, HTMLButtonElement | null>());

  // `role="tab"` is a promise of arrow-key navigation, and the strip made it
  // without keeping it: assistive technology announced "tab 1 of 6" over six
  // buttons where only Tab moved. Kept rather than dropped because these really
  // are one tab strip over one panel — what was missing was the contract, not
  // the semantics.
  //
  // Selection follows focus (the APG default): the panels render from settings
  // already in the store, so arrowing across them costs nothing a click would
  // not, and manual activation would leave the strip behaving unlike its own
  // mouse behaviour.
  const selectTab = (id: TabId) => {
    setActiveTab(id);
    tabRefs.current.get(id)?.focus();
  };

  const handleTabKeys = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = tabs.length - 1;
    let target: number | null = null;
    if (event.key === "ArrowRight") target = index === last ? 0 : index + 1;
    else if (event.key === "ArrowLeft") target = index === 0 ? last : index - 1;
    else if (event.key === "Home") target = 0;
    else if (event.key === "End") target = last;
    if (target === null) return;
    event.preventDefault();
    selectTab(tabs[target].id);
  };

  // One badge per tab that owns tweaks, counted with the same predicates the tabs
  // themselves use. A single total on Software Tweaks counted hardware and game
  // settings the user could not reach from that tab — the number said "18 here"
  // about a list holding four.
  const badges = useMemo(() => {
    const counts: Partial<Record<TabId, number>> = {};
    for (const s of settingsMap.values()) {
      if (
        !s.isApplicable ||
        s.isAction ||
        s.isReadonly ||
        s.currentValue === null ||
        s.status !== "suboptimal"
      )
        continue;
      const tab: TabId = isGameTweak(s)
        ? "games"
        : isHardwareTweak(s)
          ? "hardware"
          : "settings";
      counts[tab] = (counts[tab] ?? 0) + 1;
    }
    return counts;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settingsMap, settingsVersion]);

  return (
    <div className="sticky top-0 z-10 bg-background border-b border-border">
      <div className="max-w-7xl 2xl:max-w-[120rem] mx-auto px-6 flex items-center justify-between gap-3">
        {/* Brand + tabs */}
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex items-center gap-1.5 pr-2 shrink-0">
            <Activity className="w-5 h-5 text-primary" />
            <span className="text-sm font-bold hidden sm:inline">fpstune</span>
          </div>
          <nav className="flex gap-1 overflow-x-auto" role="tablist">
            {tabs.map((tab, index) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              const count = badges[tab.id] ?? 0;
              const badge = count > 0 ? count : null;

              return (
                <button
                  key={tab.id}
                  ref={(node) => {
                    tabRefs.current.set(tab.id, node);
                  }}
                  type="button"
                  role="tab"
                  id={tabButtonId(tab.id)}
                  aria-selected={isActive}
                  // Only the selected tab's panel is in the tree, so only it has
                  // an element to point at; naming an absent id would be a
                  // broken reference on the other five.
                  aria-controls={isActive ? tabPanelId(tab.id) : undefined}
                  // Roving tabindex: one Tab press enters the strip, arrows move
                  // within it, one more Tab press leaves for the panel.
                  tabIndex={isActive ? 0 : -1}
                  onKeyDown={(event) => handleTabKeys(event, index)}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "flex items-center gap-2 px-3 py-3 text-sm font-medium transition-colors relative whitespace-nowrap",
                    "hover:text-foreground",
                    isActive ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  <Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
                  {/* Hidden from the eye below md, never from the reader:
                      `hidden` is display:none, which took the tab's only
                      accessible name away on a narrow window and left six
                      unnamed buttons. */}
                  <span className="sr-only md:not-sr-only md:inline">
                    {t(tab.labelKey)}
                  </span>
                  {badge !== null && (
                    <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-destructive text-destructive-foreground text-xs font-bold flex items-center justify-center">
                      {badge > 99 ? "99+" : badge}
                    </span>
                  )}
                  {isActive && (
                    <div className="absolute bottom-0 left-2 right-2 h-[3px] bg-primary rounded-t" />
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Chrome: activity, admin, OS */}
        <div className="flex items-center gap-2.5 shrink-0">
          <ActivityLog />
          <div
            className={cn(
              "flex items-center gap-1 text-xs",
              systemInfo?.is_admin ? "text-success" : "text-warning",
            )}
          >
            {systemInfo?.is_admin ? (
              <>
                <ShieldCheck className="w-3.5 h-3.5" />
                <span className="hidden lg:inline">Admin</span>
              </>
            ) : (
              <>
                <ShieldAlert className="w-3.5 h-3.5" />
                <span className="hidden lg:inline">Not Admin</span>
              </>
            )}
          </div>
          <span className="text-xs text-muted-foreground hidden xl:block">
            {systemInfo?.os_edition}
            {systemInfo?.os_display_version &&
              ` ${systemInfo.os_display_version}`}
          </span>
          {/* The locale switch (F1). Two locales, one button: it names the
              language it would switch TO, in that language, so a user who
              cannot read the current one can still find their way home. */}
          <button
            onClick={() => setLocale(locale === "en" ? "tr" : "en")}
            className="text-xs px-1.5 py-0.5 rounded border border-border text-muted-foreground hover:bg-muted transition-colors"
            aria-label={locale === "en" ? tr["locale.switch"] : en["locale.switch"]}
          >
            {locale === "en" ? "TR" : "EN"}
          </button>
        </div>
      </div>
    </div>
  );
}

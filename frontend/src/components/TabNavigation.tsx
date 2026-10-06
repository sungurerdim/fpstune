import { setLocale, useT } from "../i18n";
import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Home,
  Settings,
  HardDrive,
  Monitor,
  Gamepad2,
  Gauge,
  History,
  Activity,
  ShieldCheck,
  ShieldAlert,
} from "lucide-react";
import { cn } from "../lib/utils";
import { api } from "../lib/api";
import { useStore, type TabId } from "../store";
import { isGameTweak, isHardwareTweak } from "../lib/tweakDomain";
import { ActivityLog } from "./ActivityLog";
import { UpdateControl } from "./UpdateControl";
import { ThemeToggle } from "./ThemeToggle";
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
  // Last: what fpstune changed, and the way back from each change.
  { id: "history", labelKey: "tab.history", icon: History },
];

/**
 * Which ends of the tab strip have more tabs past them.
 *
 * The strip scrolls rather than wraps (a wrapped label turned a 44px tab into
 * 84px and cut "Ölçüm" mid-word), and a scroll area with its scrollbar hidden says
 * nothing about what lies beyond the edge. This is the measurement behind the
 * fade-and-chevron cue: true on a side only while tabs are actually hidden there.
 * Read from the element on scroll and on every size change of the strip or of a
 * tab (a locale switch changes tab widths without changing the strip's own box).
 */
function useScrollEdges() {
  const ref = useRef<HTMLElement | null>(null);
  const [edges, setEdges] = useState({ start: false, end: false });

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const start = el.scrollLeft > 1;
    const end = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
    setEdges((prev) => (prev.start === start && prev.end === end ? prev : { start, end }));
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    const observer =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(el);
    for (const child of Array.from(el.children)) observer?.observe(child);
    return () => {
      el.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      observer?.disconnect();
    };
  }, [update]);

  return { ref, edges };
}

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
  const { ref: stripRef, edges } = useScrollEdges();

  // The selected tab is never left behind the edge of a scrolled strip: a tab
  // restored from an earlier session, or reached by a shortcut, scrolls into view.
  useEffect(() => {
    const el = tabRefs.current.get(activeTab);
    if (typeof el?.scrollIntoView === "function") {
      el.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }, [activeTab]);

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
      {/* Two rows until the window is wide enough for brand, seven labelled tabs
          and the chrome on one line (about 1920px: the Turkish labels alone are
          1031px). Squeezed onto one row below that, the tabs were what gave way:
          their labels wrapped to three lines and the strip outgrew its box. */}
      <div className="max-w-7xl 2xl:max-w-[120rem] mx-auto px-6 flex flex-wrap items-center justify-between gap-x-3">
        {/* Brand */}
        <div className="order-1 flex items-center gap-1.5 pr-2 py-2 3xl:py-0 shrink-0">
          <Activity className="w-5 h-5 text-primary" />
          <span className="text-sm font-bold hidden sm:inline">fpstune</span>
        </div>

        {/* Tabs: a row of their own below 3xl, scrolling (never wrapping) when
            even that row is too narrow, with a cue at each edge that hides more. */}
        <div
          data-testid="tab-strip"
          className="order-3 basis-full min-w-0 relative 3xl:order-2 3xl:basis-0 3xl:flex-1"
        >
          <nav
            ref={stripRef}
            className="flex gap-1 min-w-0 overflow-x-auto [scrollbar-width:none]"
            role="tablist"
          >
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
                  // The accessible name is the label whether or not it is drawn
                  // (below lg only the icon is), and the tooltip gives a sighted
                  // user of the icon-only strip the same name.
                  title={t(tab.labelKey)}
                  className={cn(
                    "flex shrink-0 items-center gap-2 px-3 py-3 text-sm font-medium transition-colors relative whitespace-nowrap",
                    "hover:text-foreground",
                    isActive ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  <Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
                  {/* Hidden from the eye below lg, never from the reader:
                      `hidden` is display:none, which took the tab's only
                      accessible name away on a narrow window and left six
                      unnamed buttons. `max-lg:sr-only` rather than
                      `sr-only lg:not-sr-only`: not-sr-only resets
                      `white-space` to normal, which let the button's own
                      nowrap lapse and wrapped every label onto 2-3 lines. */}
                  <span className="max-lg:sr-only">{t(tab.labelKey)}</span>
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
          {edges.start && (
            <span
              aria-hidden="true"
              data-testid="tab-strip-more-start"
              className="pointer-events-none absolute inset-y-0 left-0 flex w-8 items-center bg-linear-to-r from-background to-transparent text-muted-foreground"
            >
              <ChevronLeft className="w-4 h-4" />
            </span>
          )}
          {edges.end && (
            <span
              aria-hidden="true"
              data-testid="tab-strip-more-end"
              className="pointer-events-none absolute inset-y-0 right-0 flex w-8 items-center justify-end bg-linear-to-l from-background to-transparent text-muted-foreground"
            >
              <ChevronRight className="w-4 h-4" />
            </span>
          )}
        </div>

        {/* Chrome: activity, admin, OS */}
        <div className="order-2 ml-auto flex items-center gap-2.5 py-2 3xl:order-3 3xl:py-0 shrink-0">
          <UpdateControl />
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
                <span className="hidden lg:inline">{t("header.admin")}</span>
              </>
            ) : (
              <>
                <ShieldAlert className="w-3.5 h-3.5" />
                <span className="hidden lg:inline">{t("header.notAdmin")}</span>
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
          <ThemeToggle />
        </div>
      </div>
    </div>
  );
}

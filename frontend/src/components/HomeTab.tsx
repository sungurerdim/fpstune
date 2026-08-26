import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Zap,
  Trash2,
  Gauge,
  Timer,
  HardDrive,
  MemoryStick,
  CheckCircle2,
  Loader2,
  Cpu,
  Gamepad2,
} from "lucide-react";
import { cn } from "../lib/utils";
import { useStore } from "../store";
import { useImpactSummary } from "../hooks/useImpactSummary";
import { useBulkApply } from "../hooks/useBulkApply";
import { useCleanupRunner } from "../hooks/useCleanupRunner";
import { cleanupReclaimableMB } from "../lib/impact";
import { headroomApi } from "../lib/api";
import { isGameTweak, isHardwareTweak } from "../lib/tweakDomain";
import { parseSizeToMB, fmtMB } from "../lib/cleanupSize";
import { TweakListRow } from "./TweakListRow";
import { CleanupListRow } from "./CleanupListRow";
import { DockerConfirmModal } from "./DockerConfirmModal";
import { DetectionNotice } from "./DetectionNotice";
import type { Setting } from "../types/setting";

/**
 * Home — the default landing tab. Plain, actionable lists: which tweaks still
 * need optimizing (left) and how much disk you can reclaim (right), with a
 * headline of total potential and one-click Apply All / Run All.
 */
export function HomeTab() {
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const categories = useStore((s) => s.categories);
  const detecting = useStore((s) => s.isAnyCategoryLoading());
  const summary = useImpactSummary();

  // The one number here that is a measurement rather than a claim: what a game
  // actually reached on this machine, against what the panel can show. If no
  // game has been measured, this says so instead of substituting an estimate.
  const { data: headroom } = useQuery({
    queryKey: ["headroom"],
    queryFn: headroomApi.list,
    staleTime: 30_000,
  });
  const measured = useMemo(
    () => headroom?.games.filter((game) => game.is_measured) ?? [],
    [headroom],
  );

  const { apply, isApplying } = useBulkApply();
  const cleanupRunner = useCleanupRunner({
    modules: ["cleanup", "game_cleanup"],
  });

  const categoryLabel = (id: string) => categories.get(id)?.displayName ?? id;

  // True while any cleanup size is still being computed in the background.
  const sizesCalculating = useMemo(() => {
    for (const s of settings.values()) {
      if (!s.isAction || !s.isApplicable) continue;
      if (s.module !== "cleanup" && s.module !== "game_cleanup") continue;
      const v = s.currentValue;
      if (typeof v === "string" && v.includes("calculating")) return true;
    }
    return false;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settings, settingsVersion]);

  const suboptimal = useMemo(() => {
    const rows: Setting[] = [];
    for (const s of settings.values()) {
      if (
        s.isApplicable &&
        !s.isAction &&
        !s.isReadonly &&
        s.currentValue !== null &&
        s.status === "suboptimal"
      ) {
        rows.push(s);
      }
    }
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settings, settingsVersion]);

  const cleanups = useMemo(() => {
    const rows: Setting[] = [];
    for (const s of settings.values()) {
      if (!s.isAction || !s.isApplicable) continue;
      if (s.module !== "cleanup" && s.module !== "game_cleanup") continue;
      if (parseSizeToMB(s.currentValue) === null) continue;
      rows.push(s);
    }
    return rows.sort(
      (a, b) =>
        (parseSizeToMB(b.currentValue) ?? 0) -
        (parseSizeToMB(a.currentValue) ?? 0),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settings, settingsVersion]);

  const reclaimableMB = useMemo(
    () => cleanupReclaimableMB(settings.values()),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
    [settings, settingsVersion],
  );

  // Split by where the tweak lives, using the same predicates the Hardware and
  // Game pages use so the screens cannot disagree about which domain a tweak
  // belongs to. Software is what is left over, so every tweak lands in exactly
  // one group and no group can double-count.
  const hardwareSuboptimal = useMemo(
    () => suboptimal.filter(isHardwareTweak),
    [suboptimal],
  );
  const gameSuboptimal = useMemo(
    () => suboptimal.filter(isGameTweak),
    [suboptimal],
  );
  const softwareSuboptimal = useMemo(
    () => suboptimal.filter((s) => !isHardwareTweak(s) && !isGameTweak(s)),
    [suboptimal],
  );

  const applyGroup = async (group: Setting[]) => {
    const payload: Record<string, unknown> = {};
    for (const s of group) payload[s.id] = s.recommendedValue;
    if (Object.keys(payload).length === 0) return;
    await apply(payload);
  };

  const runAllCleanups = () => {
    cleanupRunner.run(cleanups.map((s) => s.id));
  };

  return (
    <div className="space-y-4 pb-8">
      {/* Home owns the whole product, so its notice owns every setting. */}
      <DetectionNotice />
      {/* The headline, and what it deliberately does not say.
          This block used to open with "Gained +28-45% FPS", produced by summing
          every setting's claimed fps midpoint under an invented decay curve. No
          instrument produced that number and none could have confirmed it — the
          machine it rendered on was measuring 19% of its own frame-rate target
          at the time. What is left counts: how many settings are where they
          should be, how many carry a latency or memory claim, and how many bytes
          the cleanup scan actually found on this disk. The only *gain* shown is
          the one something measured. */}
      {(() => {
        const hasPotential =
          summary.potential.latencyTweaks > 0 ||
          summary.potential.ramTweaks > 0 ||
          reclaimableMB > 0;
        // How many of the settings sitting at their ideal value got there
        // because fpstune wrote them, and how many were already correct.
        //
        // These used to be two chips on opposite sides of the screen — one
        // labelled "optimized", one "tweaks active" — with nothing saying the
        // second was a subset of the first. Read side by side, "367/367" and
        // "226" look like a contradiction rather than a whole and its part.
        const changed = summary.gained.count;
        const alreadyStock = Math.max(summary.score.optimized - changed, 0);
        return (
          <div className="flex flex-wrap items-stretch gap-3">
            <Stat
              icon={<CheckCircle2 className="w-4 h-4 text-success" />}
              value={`${summary.score.optimized}/${summary.score.total}`}
              label="settings at their ideal value"
              hint={
                summary.score.optimized > 0
                  ? `${changed} fpstune changed · ${alreadyStock} were already correct` +
                    (summary.score.guardsStanding > 0
                      ? ` · ${summary.score.guardsStanding} drift guards standing watch`
                      : "")
                  : undefined
              }
            />

            {measured.length > 0 ? (
              <Group label="Measured" tone="success">
                {measured.map((game) => {
                  // The one number on this screen an instrument produced. It is
                  // written as a sentence rather than a ratio because "57/297"
                  // reads like a count of things, and it is a frame rate against
                  // what this panel can display.
                  const fps = Math.round(game.measured_fps ?? 0);
                  const pct = game.target_fps
                    ? Math.round(((game.measured_fps ?? 0) / game.target_fps) * 100)
                    : null;
                  return (
                    <Stat
                      key={game.game}
                      icon={<Gauge className="w-4 h-4 text-success" />}
                      value={`${fps} fps`}
                      label={game.label}
                      hint={
                        pct !== null
                          ? `${pct}% of the ${game.target_fps} fps this display can show`
                          : "no display target — panel refresh unknown"
                      }
                    />
                  );
                })}
              </Group>
            ) : (
              /* Not a zero and not an estimate. Nothing has measured a frame
                 rate on this machine yet, and saying so is the honest headline
                 — with where to go to change that. */
              <Group label="Measured" tone="muted">
                <Stat
                  icon={<Gauge className="w-4 h-4 text-muted-foreground" />}
                  value="—"
                  label="no frame rate measured yet — start a game, or open Benchmarks"
                />
              </Group>
            )}

            {hasPotential && (
              <Group label="Claimed by settings not yet applied" tone="warning">
                {summary.potential.latencyTweaks > 0 && (
                  <Stat
                    icon={<Timer className="w-4 h-4 text-warning" />}
                    value={`${summary.potential.latencyTweaks}`}
                    label="latency tweaks"
                  />
                )}
                {summary.potential.ramTweaks > 0 && (
                  <Stat
                    icon={<MemoryStick className="w-4 h-4 text-purple-500" />}
                    value={`${summary.potential.ramTweaks}`}
                    label="memory tweaks"
                  />
                )}
                {/* This one does add up, and is the exception that shows the
                    rule: the cleanup scan counted these bytes on this disk. */}
                {reclaimableMB > 0 && (
                  <Stat
                    icon={<HardDrive className="w-4 h-4 text-primary" />}
                    value={fmtMB(reclaimableMB)}
                    label="disk to reclaim"
                  />
                )}
              </Group>
            )}

          </div>
        );
      })()}

      {/* One progress line, not two. The cleanup half already spins in its own
          header and says what it is measuring, so a second global line saying the
          same thing was two indicators for one wait. */}
      {detecting && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
          <span>
            Detecting your settings — the lists and totals fill in as results
            arrive…
          </span>
        </div>
      )}

      {/* Two columns only when both halves have something in them. A fixed split
          gave an empty card with a disabled button half of a 1600px screen while
          the other half scrolled eighteen rows. */}
      <div
        className={cn(
          "grid gap-4 items-start",
          suboptimal.length > 0 && cleanups.length > 0 && "lg:grid-cols-2",
        )}
      >
        {/* LEFT: what still needs applying, split by where it lives.
            Two groups rather than one list, because a single "Apply All" mixed a GPU
            driver setting with a game config file and a Windows service — a user has
            to know what a button is about before pressing it. */}
        <div className="space-y-4">
          <TweakGroup
            title="Hardware tweaks"
            subtitle="GPU, display, adapters, storage, audio"
            icon={<Cpu className="w-4 h-4 text-warning" />}
            settings={hardwareSuboptimal}
            detecting={detecting}
            isApplying={isApplying}
            onApplyAll={() => applyGroup(hardwareSuboptimal)}
            categoryLabel={categoryLabel}
          />
          <TweakGroup
            title="Software tweaks"
            subtitle="Windows, services, launchers"
            icon={<Zap className="w-4 h-4 text-warning" />}
            settings={softwareSuboptimal}
            detecting={detecting}
            isApplying={isApplying}
            onApplyAll={() => applyGroup(softwareSuboptimal)}
            categoryLabel={categoryLabel}
          />
          <TweakGroup
            title="Game tweaks"
            subtitle="Settings inside a game's own config file"
            icon={<Gamepad2 className="w-4 h-4 text-warning" />}
            settings={gameSuboptimal}
            detecting={detecting}
            isApplying={isApplying}
            onApplyAll={() => applyGroup(gameSuboptimal)}
            categoryLabel={categoryLabel}
          />
        </div>

        {/* RIGHT: cleanup opportunities */}
        <section className="bg-card rounded-lg border border-border flex flex-col">
          <div className="flex items-center justify-between p-3 border-b border-border">
            <div className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-primary" />
              <h2 className="font-semibold text-sm">
                Available disk cleanup actions
              </h2>
              <span className="text-xs text-muted-foreground">
                {cleanups.length}
              </span>
              {sizesCalculating && (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
              )}
            </div>
            <button
              onClick={runAllCleanups}
              disabled={cleanupRunner.isRunning || cleanups.length === 0}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-colors",
                cleanups.length === 0
                  ? "bg-muted text-muted-foreground/50 cursor-not-allowed"
                  : "bg-primary text-primary-foreground hover:bg-primary/90",
              )}
            >
              {cleanupRunner.isRunning ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Trash2 className="w-3.5 h-3.5" />
              )}
              Run All
            </button>
          </div>
          {/* No inner scroll: a scrollable region inside a scrollable page means
              the wheel does something different depending on where the pointer is. */}
          <div className="p-3 space-y-2">
            {cleanups.length === 0 ? (
              // The old copy said "Calculating… or nothing to reclaim", admitting in
              // one sentence that it did not know which state it was in — while
              // `sizesCalculating` knew all along.
              <p className="text-xs text-muted-foreground text-center py-2">
                {sizesCalculating
                  ? "Measuring what can be reclaimed…"
                  : "Nothing to reclaim right now."}
              </p>
            ) : (
              cleanups.map((s) => (
                <CleanupListRow key={s.id} setting={s} runner={cleanupRunner} />
              ))
            )}
          </div>
        </section>
      </div>

      <DockerConfirmModal
        open={cleanupRunner.confirmIds !== null}
        onConfirm={cleanupRunner.confirmRun}
        onCancel={cleanupRunner.cancelConfirm}
      />
    </div>
  );
}

/**
 * One domain's outstanding tweaks: a count, a bulk apply scoped to that domain, and
 * the rows themselves.
 *
 * A group with nothing outstanding collapses to a single line instead of an empty
 * card, so a fully optimized machine does not show two large boxes saying nothing.
 */
function TweakGroup({
  title,
  subtitle,
  icon,
  settings,
  detecting,
  isApplying,
  onApplyAll,
  categoryLabel,
}: {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  settings: Setting[];
  detecting: boolean;
  isApplying: boolean;
  onApplyAll: () => void;
  categoryLabel: (id: string) => string;
}) {
  return (
    <section className="bg-card rounded-lg border border-border flex flex-col">
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2 min-w-0">
          {icon}
          <h2 className="font-semibold text-sm">{title}</h2>
          <span className="text-xs text-muted-foreground">{settings.length}</span>
          {detecting && (
            <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
          )}
          <span className="text-[10px] text-muted-foreground truncate hidden sm:inline">
            {subtitle}
          </span>
        </div>
        {settings.length > 0 && (
          <button
            onClick={onApplyAll}
            disabled={isApplying}
            className={cn(
              "shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md font-medium transition-colors",
              "bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50",
            )}
          >
            {isApplying ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Zap className="w-3.5 h-3.5" />
            )}
            Apply all {settings.length}
          </button>
        )}
      </div>
      {settings.length === 0 ? (
        // An empty group means two different things, and saying the wrong one is a
        // false claim: while detection runs nothing has been read yet, so "already
        // optimized" would assert a result the app does not have.
        <p className="text-xs text-muted-foreground px-3 py-2">
          {detecting
            ? "Reading your current settings…"
            : "Everything applicable is already optimized."}
        </p>
      ) : (
        <div className="p-3 space-y-2">
          {settings.map((s) => (
            <TweakListRow
              key={s.id}
              setting={s}
              categoryLabel={categoryLabel(s.category)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

/** A labelled, tinted container that visually groups related Stat chips. */
function Group({
  label,
  tone,
  children,
}: {
  label: string;
  /** `muted` is for a group that has nothing to report and says so. */
  tone: "warning" | "success" | "muted";
  children: React.ReactNode;
}) {
  const border =
    tone === "warning"
      ? "border-warning/30 bg-warning/[0.05]"
      : tone === "success"
        ? "border-success/30 bg-success/[0.05]"
        : "border-border bg-muted/30";
  const text =
    tone === "warning"
      ? "text-warning/80"
      : tone === "success"
        ? "text-success/80"
        : "text-muted-foreground";

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border pl-2 pr-2.5 py-1.5",
        border,
      )}
    >
      <span
        className={cn("text-[9px] font-bold uppercase tracking-wider", text)}
      >
        {label}
      </span>
      {children}
    </div>
  );
}

function Stat({
  icon,
  value,
  label,
  hint,
}: {
  icon: React.ReactNode;
  value: string;
  label: string;
  /** What the number is *of*, in plain words. A figure whose referent the reader
   *  has to reconstruct is one they will read as wrong. */
  hint?: string;
}) {
  return (
    <div className="bg-card rounded-md border border-border px-2.5 py-1.5 inline-flex items-center gap-2">
      {icon}
      <div className="min-w-0">
        <p className="text-sm font-semibold leading-tight truncate">{value}</p>
        <p className="text-[10px] text-muted-foreground uppercase tracking-wider leading-tight">
          {label}
        </p>
        {hint && (
          <p className="text-[10px] text-muted-foreground/70 leading-tight">
            {hint}
          </p>
        )}
      </div>
    </div>
  );
}

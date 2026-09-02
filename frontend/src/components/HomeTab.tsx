import { useMemo, useState } from "react";
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
  Flame,
  ChevronDown,
  ChevronRight,
  Info,
  AlertTriangle,
  HelpCircle,
} from "lucide-react";
import { cn } from "../lib/utils";
import { useStore } from "../store";
import { useImpactSummary } from "../hooks/useImpactSummary";
import { useBulkApply } from "../hooks/useBulkApply";
import { useCleanupRunner } from "../hooks/useCleanupRunner";
import { cleanupReclaimableMB } from "../lib/impact";
import { api, headroomApi } from "../lib/api";
import { useT } from "../i18n";
import {
  localizedDescription,
  localizedEffect,
  localizedName,
} from "../i18n/settings";
import { isGameTweak, isHardwareTweak } from "../lib/tweakDomain";
import { describeFinding } from "../lib/finding";
import { parseSizeToMB, fmtMB } from "../lib/cleanupSize";
import { TweakListRow } from "./TweakListRow";
import { CleanupListRow } from "./CleanupListRow";
import { DockerConfirmModal } from "./DockerConfirmModal";
import { DetectionNotice } from "./DetectionNotice";
import { FirstRunNotice } from "./FirstRunNotice";
import { SelfCheckNotice } from "./SelfCheckNotice";
import { MaintenancePanel } from "./MaintenancePanel";
import { HardwarePanel } from "./HardwarePanel";
import { SettingInfoTooltip } from "./SettingInfoTooltip";
import { SettingValueState } from "./SettingStateDisplay";
import { Button } from "./ui/Button";
import { Card } from "./ui/Card";
import { Progress } from "./ui/Feedback";
import { ConfirmDialog } from "./ui/ConfirmDialog";
import type { Setting } from "../types/setting";

/**
 * Home — the default landing tab. Plain, actionable lists: which tweaks still
 * need optimizing (left) and how much disk you can reclaim (right), with a
 * headline of total potential and one-click Apply All / Run All.
 */
export function HomeTab() {
  const { t } = useT();
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const categories = useStore((s) => s.categories);
  const detecting = useStore((s) => s.isAnyCategoryLoading());
  const categoryStatus = useStore((s) => s.categoryDetectionStatus);
  const categoriesTotal = Object.keys(categoryStatus).length;
  const categoriesDone = Object.values(categoryStatus).filter(
    (status) => status === "done",
  ).length;
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

  // Cleanups whose size scan has not finished. Dropping them entirely made a
  // cleanup that was still measuring indistinguishable from one that does not
  // exist (D6): the row is on screen, named, and says it is not ready.
  const measuringCleanups = useMemo(() => {
    const rows: Setting[] = [];
    for (const s of settings.values()) {
      if (!s.isAction || !s.isApplicable) continue;
      if (s.module !== "cleanup" && s.module !== "game_cleanup") continue;
      if (parseSizeToMB(s.currentValue) !== null) continue;
      rows.push(s);
    }
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settings, settingsVersion]);

  // Advisory findings: things fpstune can detect but only the user can change
  // (BIOS toggles, physical facts). is_readonly kept them out of every Home
  // list — XMP off, the largest hardware finding the product makes, was
  // invisible from the landing page.
  //
  // Split by whether the finding is *actionable*, because an advisory that
  // reports "nothing wrong" and one that reports a 25x loss are not the same
  // row. Measured on a real machine: `network:link_capability` found an
  // Ethernet link negotiated at 100 Mbps on an adapter that does 2500 — the
  // single largest ceiling loss on that box, and it sat under a heading counted
  // together with five findings that were fine.
  //
  // The actionable ones render above the fold; the clear ones stay below, where
  // "we checked and it is fine" belongs. Neither is dropped: a check with no
  // finding is still evidence the check ran.
  //
  // Three buckets, not two. A check that could not read anything is not a
  // finding: `isOptimized` is false whenever the current value does not equal
  // the ideal, and a value that was never read does not equal anything — so a
  // detector that failed, timed out, or is still running was landing under
  // "needs your attention" and warning about a state nobody had measured. That
  // is the one thing an advisory must never do, and it is C11's rule 3 on this
  // surface: what could not be measured says so.
  const [actionableAdvisories, clearAdvisories, unreadAdvisories] =
    useMemo(() => {
      const actionable: Setting[] = [];
      const clear: Setting[] = [];
      const unread: Setting[] = [];
      for (const s of settings.values()) {
        if (!s.isApplicable || s.isAction || !s.isReadonly) continue;
        if (s.currentValue === null || s.currentValue === undefined) {
          unread.push(s);
        } else {
          (s.isOptimized ? clear : actionable).push(s);
        }
      }
      return [actionable, clear, unread];
      // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
    }, [settings, settingsVersion]);

  // The settings already at their ideal value, behind a fold: Home's headline
  // counts them, and a count whose members cannot be seen is a claim.
  const [showOptimized, setShowOptimized] = useState(false);
  const optimized = useMemo(() => {
    const rows: Setting[] = [];
    for (const s of settings.values()) {
      if (
        s.isApplicable &&
        !s.isAction &&
        !s.isReadonly &&
        s.status === "optimal"
      ) {
        rows.push(s);
      }
    }
    return rows;
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

  // The two buttons (D2). They are the scope enum made visible: Competitive Max
  // is essential + recommended — the most frames without touching what the
  // player can see or hear — and Absolute Max adds `complete`, whose cost is
  // stated on screen, in each setting's own perceptible_cost sentence, before
  // anything runs. Neither runs unconfirmed.
  const addNotification = useStore((s) => s.addNotification);
  const [pendingButton, setPendingButton] = useState<
    "competitive" | "absolute" | null
  >(null);
  const [restoreFirst, setRestoreFirst] = useState(true);
  const competitiveTargets = useMemo(
    () => suboptimal.filter((s) => s.scope !== "complete"),
    [suboptimal],
  );
  const absoluteTargets = suboptimal;
  const absoluteCosts = useMemo(() => {
    const costs = new Set<string>();
    for (const s of absoluteTargets) {
      if (s.perceptibleCost) costs.add(s.perceptibleCost);
    }
    return [...costs];
  }, [absoluteTargets]);

  const runScope = async (targets: Setting[]) => {
    setPendingButton(null);
    if (restoreFirst) {
      try {
        const result = await api.createRestorePoint();
        if (!result.success) throw new Error(result.message);
      } catch (error) {
        // The user asked for the safety net; applying without it would honour
        // the button and betray the checkbox.
        addNotification(
          `Restore point failed — nothing was applied. ${
            error instanceof Error ? error.message : ""
          }`.trim(),
          "error",
        );
        return;
      }
    }
    await applyGroup(targets);
  };

  const restoreFirstCheckbox = (
    <label className="flex items-center gap-2 pt-1 text-xs">
      <input
        type="checkbox"
        checked={restoreFirst}
        onChange={(event) => setRestoreFirst(event.target.checked)}
      />
      {t("scope.restoreFirst")}
    </label>
  );

  const runAllCleanups = () => {
    cleanupRunner.run(cleanups.map((s) => s.id));
  };

  return (
    <div className="space-y-4 pb-8">
      {/* What this is and that nothing has been touched — once, first. */}
      <FirstRunNotice />
      {/* Home owns the whole product, so its notice owns every setting. */}
      <DetectionNotice />
      {/* And its self-check owns every detector (A12): a disagreement between
          independent sources is a Home-page fact, not a buried report. */}
      <SelfCheckNotice />

      {/* The two buttons: each applies exactly its category, and says so. */}
      {suboptimal.length > 0 && (
        <Card className="p-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <Button
            size="md"
            className="font-semibold"
            icon={<Zap className="w-4 h-4" aria-hidden="true" />}
            onClick={() => setPendingButton("competitive")}
            disabled={isApplying || competitiveTargets.length === 0}
          >
            {t("scope.competitive")}
            <span className="font-normal opacity-80">
              · {competitiveTargets.length}
            </span>
          </Button>
          <span className="text-xs text-muted-foreground">
            {t("scope.competitiveHint")}
          </span>
          <Button
            size="md"
            variant="outline"
            className="font-semibold border-warning/60 text-warning hover:bg-warning/10 hover:text-warning"
            icon={<Flame className="w-4 h-4" aria-hidden="true" />}
            onClick={() => setPendingButton("absolute")}
            disabled={isApplying || absoluteTargets.length === 0}
          >
            {t("scope.absolute")}
            <span className="font-normal opacity-80">
              · {absoluteTargets.length}
            </span>
          </Button>
          <span className="text-xs text-muted-foreground">
            {t("scope.absoluteHint")}
          </span>
        </Card>
      )}
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
              label={t("home.statIdeal")}
              hint={
                summary.score.optimized > 0
                  ? t("home.statIdealHint", {
                      changed,
                      stock: alreadyStock,
                    }) +
                    (summary.score.guardsStanding > 0
                      ? t("home.statGuards", {
                          count: summary.score.guardsStanding,
                        })
                      : "")
                  : undefined
              }
            />

            {measured.length > 0 ? (
              <Group label={t("home.measured")} tone="success">
                {measured.map((game) => {
                  // The one number on this screen an instrument produced. It is
                  // written as a sentence rather than a ratio because "57/297"
                  // reads like a count of things, and it is a frame rate against
                  // what this panel can display.
                  const fps = Math.round(game.measured_fps ?? 0);
                  const pct = game.target_fps
                    ? Math.round(
                        ((game.measured_fps ?? 0) / game.target_fps) * 100,
                      )
                    : null;
                  return (
                    <Stat
                      key={game.game}
                      icon={<Gauge className="w-4 h-4 text-success" />}
                      value={`${fps} fps`}
                      label={game.label}
                      hint={
                        pct !== null
                          ? t("home.ofTarget", {
                              pct,
                              target: game.target_fps ?? 0,
                            })
                          : t("home.noTarget")
                      }
                    />
                  );
                })}
              </Group>
            ) : (
              /* Not a zero and not an estimate. Nothing has measured a frame
                 rate on this machine yet, and saying so is the honest headline
                 — with where to go to change that. */
              <Group label={t("home.measured")} tone="muted">
                <Stat
                  icon={<Gauge className="w-4 h-4 text-muted-foreground" />}
                  value="—"
                  label={t("home.noMeasurement")}
                />
              </Group>
            )}

            {hasPotential && (
              <Group label={t("home.claimed")} tone="warning">
                {summary.potential.latencyTweaks > 0 && (
                  <Stat
                    icon={<Timer className="w-4 h-4 text-warning" />}
                    value={`${summary.potential.latencyTweaks}`}
                    label={t("home.latencyTweaks")}
                  />
                )}
                {summary.potential.ramTweaks > 0 && (
                  <Stat
                    icon={<MemoryStick className="w-4 h-4 text-purple-500" />}
                    value={`${summary.potential.ramTweaks}`}
                    label={t("home.memoryTweaks")}
                  />
                )}
                {/* This one does add up, and is the exception that shows the
                    rule: the cleanup scan counted these bytes on this disk. */}
                {reclaimableMB > 0 && (
                  <Stat
                    icon={<HardDrive className="w-4 h-4 text-primary" />}
                    value={fmtMB(reclaimableMB)}
                    label={t("home.diskToReclaim")}
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
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
            <span>
              {t("home.detecting", {
                done: categoriesDone,
                total: categoriesTotal,
              })}
            </span>
          </div>
          <Progress
            className="max-w-md"
            value={
              categoriesTotal > 0 ? (categoriesDone / categoriesTotal) * 100 : 0
            }
            label={t("home.detectingProgress")}
          />
        </div>
      )}

      {/* Advisories with something to report, above the tweak lists.
          fpstune cannot press these — a BIOS toggle, a cable — which is exactly
          why they need to be *read*, and why burying them under everything the
          product can do itself gets the priority backwards. Measured: an
          Ethernet link at 100 Mbps on a 2500 Mbps adapter is a bigger ceiling
          loss than every registry tweak above it combined, and it was the sixth
          section down. */}
      {actionableAdvisories.length > 0 && (
        <Card className="border-warning/40" data-testid="home-advisories">
          <div className="flex items-center gap-2 p-3 border-b border-warning/30 bg-warning/10">
            <AlertTriangle
              className="w-4 h-4 text-warning"
              aria-hidden="true"
            />
            <h2 className="font-semibold text-sm text-warning">
              {t("home.advisories")}
            </h2>
            <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-warning/15 text-warning">
              {actionableAdvisories.length}
            </span>
            <span className="text-xs text-muted-foreground hidden sm:inline">
              {t("home.advisoriesHint")}
            </span>
          </div>
          <div className="p-3 space-y-2">
            {actionableAdvisories.map((s) => (
              <div
                key={s.id}
                className="p-3 rounded-md border border-warning/30 border-l-4 border-l-warning bg-warning/[0.06]"
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-sm">
                    {localizedName(s)}
                  </span>
                  <SettingInfoTooltip setting={s} />
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {localizedDescription(s)}
                </p>
                {/* The current state — the measured numbers when the detector
                    produced them: "Link running at 100 Mbps; the adapter
                    supports 2.5 Gbps." */}
                <div className="mt-1" data-testid="advisory-finding">
                  <SettingValueState setting={s} />
                </div>
                {/* The finding names a problem; this names the move. A cable to
                    change, a band to switch to — the one line the user came for.
                    A measured finding carries its own, sized to the numbers
                    (the cable class the ceiling needs); otherwise the static one. */}
                {(describeFinding(s)?.advice || localizedEffect(s)) && (
                  <p className="text-xs mt-1.5" data-testid="advisory-advice">
                    <span className="font-semibold text-warning">
                      {t("home.whatToDo")}
                    </span>{" "}
                    {describeFinding(s)?.advice || localizedEffect(s)}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Two columns only when both halves have something in them. A fixed split
          gave an empty card with a disabled button half of a 1600px screen while
          the other half scrolled eighteen rows. */}
      <div
        className={cn(
          "grid gap-4 items-start",
          suboptimal.length > 0 &&
            cleanups.length > 0 &&
            "lg:grid-cols-2 2xl:grid-cols-[2fr,1fr]",
        )}
      >
        {/* LEFT: what still needs applying, split by where it lives.
            Two groups rather than one list, because a single "Apply All" mixed a GPU
            driver setting with a game config file and a Windows service — a user has
            to know what a button is about before pressing it. */}
        <div className="space-y-4">
          <TweakGroup
            accent="hardware"
            title={t("home.hardwareTweaks")}
            subtitle={t("home.hardwareSubtitle")}
            icon={
              <Cpu
                className="w-4 h-4 text-domain-hardware"
                aria-hidden="true"
              />
            }
            settings={hardwareSuboptimal}
            detecting={detecting}
            isApplying={isApplying}
            onApplyAll={() => applyGroup(hardwareSuboptimal)}
            categoryLabel={categoryLabel}
          />
          <TweakGroup
            accent="software"
            title={t("home.softwareTweaks")}
            subtitle={t("home.softwareSubtitle")}
            icon={
              <Zap
                className="w-4 h-4 text-domain-software"
                aria-hidden="true"
              />
            }
            settings={softwareSuboptimal}
            detecting={detecting}
            isApplying={isApplying}
            onApplyAll={() => applyGroup(softwareSuboptimal)}
            categoryLabel={categoryLabel}
          />
          <TweakGroup
            accent="game"
            title={t("home.gameTweaks")}
            subtitle={t("home.gameSubtitle")}
            icon={
              <Gamepad2
                className="w-4 h-4 text-domain-game"
                aria-hidden="true"
              />
            }
            settings={gameSuboptimal}
            detecting={detecting}
            isApplying={isApplying}
            onApplyAll={() => applyGroup(gameSuboptimal)}
            categoryLabel={categoryLabel}
          />
        </div>

        {/* RIGHT: cleanup opportunities */}
        <Card className="flex flex-col">
          <div className="flex items-center justify-between p-3 border-b border-border">
            <div className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-primary" />
              <h2 className="font-semibold text-sm">
                {t("home.cleanupTitle")}
              </h2>
              <span className="text-xs text-muted-foreground">
                {cleanups.length}
              </span>
              {sizesCalculating && (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
              )}
            </div>
            <Button
              onClick={runAllCleanups}
              disabled={cleanups.length === 0}
              busy={cleanupRunner.isRunning}
              icon={<Trash2 className="w-3.5 h-3.5" />}
            >
              Run All
            </Button>
          </div>
          {/* No inner scroll: a scrollable region inside a scrollable page means
              the wheel does something different depending on where the pointer is. */}
          <div className="p-3 space-y-2">
            {cleanups.length === 0 && measuringCleanups.length === 0 ? (
              // The old copy said "Calculating… or nothing to reclaim", admitting in
              // one sentence that it did not know which state it was in — while
              // `sizesCalculating` knew all along.
              <p className="text-xs text-muted-foreground text-center py-2">
                {sizesCalculating
                  ? t("home.measuringReclaim")
                  : t("home.nothingToReclaim")}
              </p>
            ) : (
              <>
                {cleanups.map((s) => (
                  <CleanupListRow
                    key={s.id}
                    setting={s}
                    runner={cleanupRunner}
                  />
                ))}
                {/* Named while still measuring: a scan in progress is a
                    different fact from nothing to reclaim. */}
                {measuringCleanups.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center gap-2 p-2 rounded-md border border-border/50 text-xs text-muted-foreground"
                  >
                    <Loader2 className="w-3 h-3 animate-spin shrink-0" />
                    <span className="font-medium">{localizedName(s)}</span>
                    <span>{t("home.rowMeasuring")}</span>
                  </div>
                ))}
              </>
            )}
          </div>
        </Card>
      </div>

      {/* The advisories that found nothing. Kept on the page rather than
          hidden: "we checked your RAM speed and it is at its rated profile" is
          the evidence the check ran, and dropping it makes a silent detector
          indistinguishable from a missing one. Below the fold, because a clear
          result is not something to act on. */}
      {/* Checks that produced no reading. Rendered, never silently dropped: a
          detector that could not answer and a detector that was never wired
          look identical once you stop showing the first. The row says what it
          could not read, and asserts nothing about the machine. */}
      {unreadAdvisories.length > 0 && (
        <Card data-testid="home-unread-advisories">
          <div className="flex items-center gap-2 p-3 border-b border-border">
            <HelpCircle className="w-4 h-4 text-muted-foreground" />
            <h2 className="font-semibold text-sm">
              {t("home.advisoriesUnread")}
            </h2>
            <span className="text-xs text-muted-foreground">
              {unreadAdvisories.length}
            </span>
            <span className="text-xs text-muted-foreground hidden sm:inline">
              {t("home.advisoriesUnreadHint")}
            </span>
          </div>
          <div className="p-3 space-y-2">
            {unreadAdvisories.map((s) => (
              <div
                key={s.id}
                className="p-3 rounded-md border border-border border-l-2 border-l-muted-foreground/40"
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-sm">
                    {localizedName(s)}
                  </span>
                  <SettingInfoTooltip setting={s} />
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {s.detectionError
                    ? t("home.advisoryUnreadReason", {
                        reason: s.detectionError,
                      })
                    : t("home.advisoryUnreadNoReason")}
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {clearAdvisories.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 p-3 border-b border-border">
            <Info className="w-4 h-4 text-muted-foreground" />
            <h2 className="font-semibold text-sm">
              {t("home.advisoriesClear")}
            </h2>
            <span className="text-xs text-muted-foreground">
              {clearAdvisories.length}
            </span>
            <span className="text-xs text-muted-foreground hidden sm:inline">
              {t("home.advisoriesClearHint")}
            </span>
          </div>
          <div className="p-3 space-y-2">
            {clearAdvisories.map((s) => (
              <div
                key={s.id}
                className="p-3 rounded-md border border-border border-l-2 border-l-success/60"
              >
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-medium text-sm">
                    {localizedName(s)}
                  </span>
                  <SettingInfoTooltip setting={s} />
                </div>
                <div className="mt-1">
                  <SettingValueState setting={s} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* The already-optimal settings, behind a fold Home owns: the headline
          counts them, and a count whose members cannot be listed is a claim. */}
      {optimized.length > 0 && (
        <Card>
          <button
            onClick={() => setShowOptimized((open) => !open)}
            aria-expanded={showOptimized}
            className="w-full flex items-center gap-2 p-3 text-left hover:bg-muted/30 transition-colors"
          >
            {showOptimized ? (
              <ChevronDown className="w-4 h-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="w-4 h-4 text-muted-foreground" />
            )}
            <CheckCircle2 className="w-4 h-4 text-success" />
            <h2 className="font-semibold text-sm">
              {t("home.alreadyOptimized")}
            </h2>
            <span className="text-xs text-muted-foreground">
              {optimized.length}
            </span>
          </button>
          {showOptimized && (
            <div className="p-3 pt-0 space-y-2">
              {optimized.map((s) => (
                <TweakListRow
                  key={s.id}
                  setting={s}
                  categoryLabel={categoryLabel(s.category)}
                />
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Repair actions (SFC, DISM) — the panel renders nothing when the
          registry holds no maintenance action. */}
      <MaintenancePanel />

      {/* The device inventory and its eleven mutations. The Hardware tab
          remains the focused view; Home is the door that always opens. */}
      <HardwarePanel />

      <DockerConfirmModal
        open={cleanupRunner.confirmIds !== null}
        onConfirm={cleanupRunner.confirmRun}
        onCancel={cleanupRunner.cancelConfirm}
      />

      <ConfirmDialog
        open={pendingButton === "competitive"}
        title={t("scope.competitiveConfirmTitle", {
          count: competitiveTargets.length,
        })}
        confirmLabel={t("scope.apply")}
        onConfirm={() => void runScope(competitiveTargets)}
        onCancel={() => setPendingButton(null)}
      >
        <div className="space-y-2">
          <p>{t("scope.competitiveConfirmBody")}</p>
          {restoreFirstCheckbox}
        </div>
      </ConfirmDialog>

      <ConfirmDialog
        open={pendingButton === "absolute"}
        title={t("scope.absoluteConfirmTitle", {
          count: absoluteTargets.length,
        })}
        confirmLabel={t("scope.spendIt")}
        onConfirm={() => void runScope(absoluteTargets)}
        onCancel={() => setPendingButton(null)}
      >
        <div className="space-y-2">
          <p>
            {t("scope.absoluteConfirmBody")}
            {absoluteCosts.length > 0 && ` ${t("scope.whatYouGiveUp")}`}
          </p>
          {/* Each sentence is the setting's own perceptible_cost — the cost is
              on screen before anything runs, never discovered afterwards. */}
          {absoluteCosts.length > 0 && (
            <ul className="list-disc pl-4 space-y-1 max-h-48 overflow-y-auto">
              {absoluteCosts.map((cost) => (
                <li key={cost}>{cost}</li>
              ))}
            </ul>
          )}
          {restoreFirstCheckbox}
        </div>
      </ConfirmDialog>
    </div>
  );
}

/** The three places a tweak can live. Each has a colour, and the colour is the
 *  first thing that separates the groups — before the heading is read. */
type DomainAccent = "hardware" | "software" | "game";

const DOMAIN_STYLE: Record<
  DomainAccent,
  { card: string; header: string; title: string; count: string }
> = {
  hardware: {
    card: "border-l-4 border-l-domain-hardware",
    header: "bg-domain-hardware/10 border-domain-hardware/20",
    title: "text-domain-hardware",
    count: "bg-domain-hardware/15 text-domain-hardware",
  },
  software: {
    card: "border-l-4 border-l-domain-software",
    header: "bg-domain-software/10 border-domain-software/20",
    title: "text-domain-software",
    count: "bg-domain-software/15 text-domain-software",
  },
  game: {
    card: "border-l-4 border-l-domain-game",
    header: "bg-domain-game/10 border-domain-game/20",
    title: "text-domain-game",
    count: "bg-domain-game/15 text-domain-game",
  },
};

/**
 * One domain's outstanding tweaks: a count, a bulk apply scoped to that domain, and
 * the rows themselves.
 *
 * A group with nothing outstanding collapses to a single line instead of an empty
 * card, so a fully optimized machine does not show two large boxes saying nothing.
 *
 * The three groups used to differ by heading text alone, in the same grey as
 * everything else; the owner read them as one list. The accent — a coloured left
 * edge, a tinted header, a coloured count — is what makes them three.
 */
function TweakGroup({
  accent,
  title,
  subtitle,
  icon,
  settings,
  detecting,
  isApplying,
  onApplyAll,
  categoryLabel,
}: {
  accent: DomainAccent;
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  settings: Setting[];
  detecting: boolean;
  isApplying: boolean;
  onApplyAll: () => void;
  categoryLabel: (id: string) => string;
}) {
  const { t } = useT();
  const style = DOMAIN_STYLE[accent];
  return (
    <Card className={cn("flex flex-col", style.card)} data-domain={accent}>
      <div
        className={cn(
          "flex items-center justify-between p-3 border-b border-border",
          style.header,
        )}
      >
        <div className="flex items-center gap-2 min-w-0">
          {icon}
          <h2 className={cn("font-semibold text-sm", style.title)}>{title}</h2>
          <span
            className={cn(
              "text-xs font-semibold px-1.5 py-0.5 rounded",
              style.count,
            )}
          >
            {settings.length}
          </span>
          {detecting && (
            <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
          )}
          <span className="text-xs text-muted-foreground truncate hidden sm:inline">
            {subtitle}
          </span>
        </div>
        {settings.length > 0 && (
          <Button
            className="shrink-0"
            busy={isApplying}
            icon={<Zap className="w-3.5 h-3.5" />}
            onClick={onApplyAll}
          >
            {t("home.applyAll", { count: settings.length })}
          </Button>
        )}
      </div>
      {settings.length === 0 ? (
        // An empty group means two different things, and saying the wrong one is a
        // false claim: while detection runs nothing has been read yet, so "already
        // optimized" would assert a result the app does not have.
        <p className="text-xs text-muted-foreground px-3 py-2">
          {detecting ? t("home.readingSettings") : t("home.allOptimized")}
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
    </Card>
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
      <span className={cn("text-xs font-bold uppercase tracking-wider", text)}>
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
        <p className="text-xs text-muted-foreground uppercase tracking-wider leading-tight">
          {label}
        </p>
        {hint && (
          <p className="text-xs text-muted-foreground/70 leading-tight">
            {hint}
          </p>
        )}
      </div>
    </div>
  );
}

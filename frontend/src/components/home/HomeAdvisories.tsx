import { AlertTriangle, HelpCircle, Info } from "lucide-react";
import { useT } from "../../i18n";
import { localizedDescription, localizedEffect, localizedName } from "../../i18n/settings";
import { describeFinding } from "../../lib/finding";
import type { Setting } from "../../types/setting";
import { Card } from "../ui/Card";
import { SettingInfoTooltip } from "../SettingInfoTooltip";
import { SettingValueState } from "../SettingStateDisplay";

/**
 * Advisories with something to report, above the tweak lists. fpstune cannot
 * press these — a BIOS toggle, a cable — which is exactly why they need to be
 * *read*. Measured: an Ethernet link at 100 Mbps on a 2500 Mbps adapter is a
 * bigger ceiling loss than every registry tweak combined.
 */
export function ActionableAdvisories({ settings: actionableAdvisories }: { settings: Setting[] }) {
  const { t } = useT();
  if (actionableAdvisories.length === 0) return null;
  return (
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
        <div
          data-testid="home-advisory-grid"
          className="p-3 grid grid-cols-1 gap-2 items-start lg:grid-cols-2 2xl:grid-cols-3"
        >
          {actionableAdvisories.map((s) => (
            <div
              key={s.id}
              className="p-3 rounded-md border border-warning/30 border-l-4 border-l-warning bg-warning/6"
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
  );
}

/**
 * Checks that produced no reading. Rendered, never silently dropped: a detector
 * that could not answer and one that was never wired look identical once you
 * stop showing the first. The row says what it could not read, nothing more.
 */
export function UnreadAdvisories({
  settings: unreadAdvisories,
  isAdmin,
}: {
  settings: Setting[];
  isAdmin: boolean | undefined;
}) {
  const { t } = useT();
  if (unreadAdvisories.length === 0) return null;
  return (
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
        <div className="p-3 grid grid-cols-1 gap-2 items-start lg:grid-cols-2 2xl:grid-cols-3">
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
                  : isAdmin === false
                    ? t("home.advisoryUnreadNeedsAdmin")
                    : t("home.advisoryUnreadNoReason")}
              </p>
            </div>
          ))}
        </div>
      </Card>
  );
}

/**
 * The advisories that found nothing: the evidence each check ran. Dropping them
 * makes a silent detector indistinguishable from a missing one.
 */
export function ClearAdvisories({ settings: clearAdvisories }: { settings: Setting[] }) {
  const { t } = useT();
  if (clearAdvisories.length === 0) return null;
  return (
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
        <div className="p-3 grid grid-cols-1 gap-2 items-start lg:grid-cols-2 2xl:grid-cols-3">
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
  );
}

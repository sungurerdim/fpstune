/**
 * "12 min ago" rather than a raw epoch, for a reading whose whole value is how
 * current it is.
 *
 * A headroom figure taken before a dozen tweaks were applied says nothing about
 * the machine now, and a bare number invites the reader to treat a stale one as
 * fresh. The panel refetches every 30 seconds and the backend measures whenever
 * a game appears, so the interesting distances here are minutes and hours —
 * a day-grained "today" would erase exactly the difference the reader needs.
 *
 * No "stale" badge, deliberately: that would need a threshold nobody has
 * measured. The age is the indication, and the reader owns the judgement.
 *
 * @param measuredAt Unix epoch seconds, or null when nothing was measured.
 */
import { t } from "../i18n";

export function formatAge(
  measuredAt: number | null,
  nowMs: number = Date.now(),
): string {
  if (measuredAt === null) return "";
  // Clamped rather than signed: a backend clock running ahead of the browser's
  // is a clock disagreement, not a measurement from the future, and "-2 min ago"
  // would read as a bug in the app rather than in the clock.
  const seconds = Math.max(0, nowMs / 1000 - measuredAt);
  if (seconds < 90) return t("age.justNow");
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return t("age.minutes", { count: minutes });
  const hours = Math.round(minutes / 60);
  if (hours < 36) return t("age.hours", { count: hours });
  return t("age.days", { count: Math.round(hours / 24) });
}

import { useT } from "../i18n";
import type { MessageKey } from "../i18n/en";
import { Card } from "./ui/Card";
import { Meter } from "./ui/Feedback";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gauge, Loader2, RefreshCw } from "lucide-react";
import { headroomApi } from "../lib/api";
import type { GameHeadroom } from "../lib/api";
import { formatAge } from "../lib/formatAge";

/**
 * What this machine actually reaches, and therefore what it can afford.
 *
 * The number here is not decoration. It is the input to a decision the product
 * makes on the user's behalf: raising image quality is only a tweak while the
 * machine is already at its frame-rate ceiling, and below it the same change
 * lowers the ceiling. So the panel shows the measurement *and* what it permits,
 * because a bare "57 fps" invites the user to draw the opposite conclusion.
 *
 * Three things it deliberately does:
 *
 * **It shows unmeasured games.** "Not measured yet" is the state that makes the
 * button make sense. A list filtered down to what has been measured looks like
 * the list of games that exist.
 *
 * **It never blanks a reading.** A measurement that could not be taken — the
 * game closed, PresentMon missing — leaves the last one on screen and explains
 * why there is no newer one. Losing information because the newest attempt
 * declined is a worse answer than the old number plus a reason.
 *
 * **It keeps no history.** One current entry per game, and the backend
 * overwrites it in place. There is nothing here to page through.
 */

/** What each band permits, said in the user's terms rather than the code's. */
const TIER_COPY: Record<
  GameHeadroom["tier"],
  { labelKey: MessageKey; meaningKey: MessageKey; className: string; tone: "primary" | "success" | "warning" | "destructive" }
> = {
  met: {
    labelKey: "headroom.tierMet",
    meaningKey: "headroom.tierMetMeaning",
    className: "text-success",
    tone: "success" as const,
  },
  near: {
    labelKey: "headroom.tierNear",
    meaningKey: "headroom.tierNearMeaning",
    className: "text-primary",
    tone: "primary" as const,
  },
  short: {
    labelKey: "headroom.tierShort",
    meaningKey: "headroom.tierShortMeaning",
    className: "text-warning",
    tone: "warning" as const,
  },
  critical: {
    labelKey: "headroom.tierCritical",
    meaningKey: "headroom.tierCriticalMeaning",
    className: "text-destructive",
    tone: "destructive" as const,
  },
  unknown: {
    labelKey: "headroom.tierUnknown",
    meaningKey: "headroom.tierUnknownMeaning",
    className: "text-muted-foreground",
    tone: "primary" as const,
  },
};

/** Which side the frame waited on. Changes which tweak is worth anything. */
const BOTTLENECK_KEY: Record<string, MessageKey | null> = {
  gpu: "headroom.gpuBound",
  cpu: "headroom.cpuBound",
  both: "headroom.bothBound",
  unknown: null,
};

function GameRow({ game }: { game: GameHeadroom }) {
  const { t } = useT();
  const tier = TIER_COPY[game.tier] ?? TIER_COPY.unknown;
  const bottleneckKey = BOTTLENECK_KEY[game.bottleneck] ?? null;

  return (
    <li className="py-3 first:pt-0 last:pb-0 border-b border-border last:border-b-0">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <span className="font-medium">
          {game.label}
          {game.is_running && (
            <span className="ml-2 text-xs font-normal text-success">
              {t("headroom.runningNow")}
            </span>
          )}
        </span>
        <span className={`text-sm font-medium ${tier.className}`}>
          {t(tier.labelKey)}
        </span>
      </div>

      {game.is_measured ? (
        <>
          <p className="text-sm mt-1">
            <span className="font-semibold tabular-nums">
              {game.measured_fps?.toFixed(1)}
            </span>{" "}
            fps
            {game.fps_1_percent_low !== null && (
              <span className="text-muted-foreground">
                {" "}
                {t("headroom.onePercentLow", {
                  value: game.fps_1_percent_low.toFixed(1),
                })}
              </span>
            )}
            {game.target_fps !== null && (
              <span className="text-muted-foreground">
                {" "}
                {t("headroom.againstTarget", { target: game.target_fps })}
                {game.achievement_percent !== null &&
                  ` — ${game.achievement_percent}%`}
              </span>
            )}
          </p>
          {/* The ratio as a picture (E5): "19%" and "97%" should not look
              the same size. The meter says the same thing the sentence above
              says — never more, never a number of its own. */}
          {game.target_fps !== null && game.measured_fps !== null && (
            <Meter
              className="mt-1.5 max-w-md"
              value={game.measured_fps}
              max={game.target_fps}
              tone={tier.tone}
              label={t("headroom.gaugeLabel", { game: game.label, target: game.target_fps ?? 0 })}
            />
          )}
          <p className="text-sm text-muted-foreground mt-1">{t(tier.meaningKey)}</p>
          {bottleneckKey && (
            <p className="text-sm text-muted-foreground mt-1">
              {t(bottleneckKey)}
            </p>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            {t("headroom.measuredAgo", { age: formatAge(game.measured_at) })}
          </p>
        </>
      ) : (
        <p className="text-sm text-muted-foreground mt-1">{t(tier.meaningKey)}</p>
      )}
    </li>
  );
}

export function HeadroomPanel() {
  const { t } = useT();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["headroom"],
    queryFn: headroomApi.list,
    // The backend measures on its own when a game appears, so the browser has
    // to look again periodically or the panel would show a number that went
    // stale the moment the user alt-tabbed out of a match.
    refetchInterval: 30_000,
  });

  const measure = useMutation({
    mutationFn: () => headroomApi.measure(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["headroom"] });
    },
  });

  const games = data?.games ?? [];
  const anyMeasured = games.some((game) => game.is_measured);

  return (
    <Card
      className="p-4 space-y-3"
      aria-labelledby="headroom-heading"
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3
            id="headroom-heading"
            className="text-lg font-semibold flex items-center gap-2"
          >
            <Gauge className="w-5 h-5" />
            {t("headroom.title")}
          </h3>
          <p className="text-sm text-muted-foreground">
            {t("headroom.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => measure.mutate()}
          disabled={measure.isPending}
          className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium bg-muted hover:bg-muted/80 disabled:opacity-60"
        >
          {measure.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          {measure.isPending ? t("headroom.measuring") : t("headroom.measureNow")}
        </button>
      </div>

      {/* A declined measurement is not an error. It is a true statement about
          the machine, and the reason is the part the user can act on. */}
      {measure.data && !measure.data.measured && (
        <p role="status" className="text-sm text-amber-500">
          {measure.data.detail}
        </p>
      )}
      {measure.isError && (
        <p role="status" className="text-sm text-red-500">
          {t("headroom.startFailed")}
        </p>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> {t("headroom.readingLast")}
        </p>
      ) : (
        <ul className="text-sm">
          {games.map((game) => (
            <GameRow key={game.game} game={game} />
          ))}
        </ul>
      )}

      {!isLoading && !anyMeasured && (
        <p className="text-sm text-muted-foreground">
          {t("headroom.needsGame")}
        </p>
      )}
    </Card>
  );
}

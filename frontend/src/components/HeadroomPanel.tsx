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
  { label: string; meaning: string; className: string; tone: "primary" | "success" | "warning" | "destructive" }
> = {
  met: {
    label: "At its ceiling",
    meaning:
      "This machine is reaching what the display can show, so there are frames spare to spend on image quality.",
    className: "text-success",
    tone: "success" as const,
  },
  near: {
    label: "Close",
    meaning:
      "Nearly there. Small savings finish the job; anything that costs frames does not.",
    className: "text-primary",
    tone: "primary" as const,
  },
  short: {
    label: "Short",
    meaning:
      "Meaningfully under what the display can show. Decoration is worth spending; anything the player needs to see is not.",
    className: "text-warning",
    tone: "warning" as const,
  },
  critical: {
    label: "Far short",
    meaning:
      "Under half of what the display can show. Everything that is not information is worth spending, and a sharper image is not on offer.",
    className: "text-destructive",
    tone: "destructive" as const,
  },
  unknown: {
    label: "Not measured",
    meaning:
      "Nothing has been measured for this game yet, and silence is not evidence — so nothing that costs frames will be recommended.",
    className: "text-muted-foreground",
    tone: "primary" as const,
  },
};

/** Which side the frame waited on. Changes which tweak is worth anything. */
const BOTTLENECK_COPY: Record<string, string> = {
  gpu: "GPU-bound — graphics settings are where the frames are",
  cpu: "CPU-bound — graphics settings will not move this much",
  both: "Both sides saturated — graphics settings alone will not close the gap",
  unknown: "",
};

function GameRow({ game }: { game: GameHeadroom }) {
  const tier = TIER_COPY[game.tier] ?? TIER_COPY.unknown;
  const bottleneck = BOTTLENECK_COPY[game.bottleneck] ?? "";

  return (
    <li className="py-3 first:pt-0 last:pb-0 border-b border-border last:border-b-0">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <span className="font-medium">
          {game.label}
          {game.is_running && (
            <span className="ml-2 text-xs font-normal text-success">
              running now
            </span>
          )}
        </span>
        <span className={`text-sm font-medium ${tier.className}`}>
          {tier.label}
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
                ({game.fps_1_percent_low.toFixed(1)} at the 1% low)
              </span>
            )}
            {game.target_fps !== null && (
              <span className="text-muted-foreground">
                {" "}
                against this panel&rsquo;s {game.target_fps} fps target
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
              label={`${game.label}: measured frame rate against the display's ${game.target_fps} fps target`}
            />
          )}
          <p className="text-sm text-muted-foreground mt-1">{tier.meaning}</p>
          {bottleneck && (
            <p className="text-sm text-muted-foreground mt-1">{bottleneck}</p>
          )}
          <p className="text-xs text-muted-foreground mt-1">
            Measured {formatAge(game.measured_at)}
          </p>
        </>
      ) : (
        <p className="text-sm text-muted-foreground mt-1">{tier.meaning}</p>
      )}
    </li>
  );
}

export function HeadroomPanel() {
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
            What this machine reaches
          </h3>
          <p className="text-sm text-muted-foreground">
            Measured against what the display could show. This is what decides
            whether there are frames spare to spend on image quality.
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
          {measure.isPending ? "Measuring…" : "Measure now"}
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
          The measurement could not be started.
        </p>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> Reading the last result…
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
          A frame rate needs something rendering to measure. Start a game and
          fpstune will take a reading on its own — or press Measure now while it
          is open.
        </p>
      )}
    </Card>
  );
}

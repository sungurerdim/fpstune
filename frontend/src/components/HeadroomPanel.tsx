import { useT } from "../i18n";
import type { MessageKey } from "../i18n/en";
import { Card } from "./ui/Card";
import { Meter } from "./ui/Feedback";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Gauge, Loader2, RefreshCw } from "lucide-react";
import { headroomApi } from "../lib/api";
import type { MachineHeadroom } from "../lib/api";
import { formatAge } from "../lib/formatAge";

/**
 * What this machine actually reaches, and therefore what it can afford.
 *
 * The number here is not decoration. It is the input to a decision the product
 * makes on the user's behalf: raising image quality is only a tweak while the
 * machine is already at its frame-rate ceiling, and below it the same change
 * lowers the ceiling. So the panel shows the measurement *and* what it permits,
 * because a bare "197 fps" invites the user to draw the opposite conclusion.
 *
 * One reading, not one per game (owner's decision, 2026-09-11). It used to list
 * every known title, each waiting to be played before it could say anything.
 * The fixed scene renders the same frames in the same order every run, so the
 * number describes the machine — and a machine nobody has played on still has
 * an answer.
 *
 * Three things it deliberately does:
 *
 * **It says what it has not measured.** "Not measured yet" is the state that
 * makes the button make sense, and it carries what pressing the button costs.
 *
 * **It never blanks a reading.** A measurement that could not be taken — a game
 * running, the scene not installed — leaves the last one on screen and explains
 * why there is no newer one. Losing information because the newest attempt
 * declined is a worse answer than the old number plus a reason.
 *
 * **It keeps no history.** One current entry, and the backend overwrites it in
 * place. There is nothing here to page through.
 */

/** What each band permits, said in the user's terms rather than the code's. */
const TIER_COPY: Record<
  MachineHeadroom["tier"],
  {
    labelKey: MessageKey;
    meaningKey: MessageKey;
    className: string;
    tone: "primary" | "success" | "warning" | "destructive";
  }
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

function Reading({ headroom }: { headroom: MachineHeadroom }) {
  const { t } = useT();
  const tier = TIER_COPY[headroom.tier] ?? TIER_COPY.unknown;
  const bottleneckKey = BOTTLENECK_KEY[headroom.bottleneck] ?? null;

  if (!headroom.is_measured) {
    return (
      <p className="text-sm text-muted-foreground">{t(tier.meaningKey)}</p>
    );
  }

  return (
    <div>
      <p className="text-sm">
        <span className={`font-medium ${tier.className}`}>
          {t(tier.labelKey)}
        </span>
        {" — "}
        <span className="font-semibold tabular-nums">
          {headroom.measured_fps?.toFixed(1)}
        </span>{" "}
        fps
        {headroom.fps_1_percent_low !== null && (
          <span className="text-muted-foreground">
            {" "}
            {t("headroom.onePercentLow", {
              value: headroom.fps_1_percent_low.toFixed(1),
            })}
          </span>
        )}
        {headroom.target_fps !== null && (
          <span className="text-muted-foreground">
            {" "}
            {t("headroom.againstTarget", { target: headroom.target_fps })}
            {headroom.achievement_percent !== null &&
              ` — ${headroom.achievement_percent}%`}
          </span>
        )}
      </p>

      {/* The ratio as a picture (E5): "19%" and "97%" should not look
          the same size. The meter says the same thing the sentence above
          says — never more, never a number of its own. */}
      {headroom.target_fps !== null && headroom.measured_fps !== null && (
        <Meter
          className="mt-1.5 max-w-md"
          value={headroom.measured_fps}
          max={headroom.target_fps}
          tone={tier.tone}
          label={t("headroom.gaugeLabel", { target: headroom.target_fps })}
        />
      )}
      <p className="text-sm text-muted-foreground mt-1">
        {t(tier.meaningKey)}
      </p>
      {bottleneckKey && (
        <p className="text-sm text-muted-foreground mt-1">{t(bottleneckKey)}</p>
      )}
      {/* PresentMon's own word for the path frames took to the screen. It
          is the one observable that proves the scene is flipping rather
          than being composed, so it is shown as a fact, unscored. */}
      {headroom.present_mode && (
        <p className="text-sm text-muted-foreground mt-1">
          {t("headroom.presentMode", { mode: headroom.present_mode })}
        </p>
      )}
      {/* The band compares a frame rate to this panel's ceiling, so it only
          means anything if the scene rendered at the panel's own size. */}
      {headroom.width !== null && headroom.height !== null && (
        <p className="text-xs text-muted-foreground mt-1">
          {t("headroom.renderedAt", {
            width: headroom.width,
            height: headroom.height,
          })}
        </p>
      )}
      <p className="text-xs text-muted-foreground mt-1">
        {t("headroom.measuredAgo", { age: formatAge(headroom.measured_at) })}
      </p>
    </div>
  );
}

export function HeadroomPanel() {
  const { t } = useT();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["headroom"],
    queryFn: headroomApi.list,
    // The backend measures on its own when the machine goes idle, so the
    // browser has to look again periodically or the panel would keep showing
    // the reading from before the last bulk apply.
    refetchInterval: 30_000,
  });

  const measure = useMutation({
    mutationFn: () => headroomApi.measure(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["headroom"] });
    },
  });

  const headroom = data?.headroom;

  return (
    <Card className="p-4 space-y-3" aria-labelledby="headroom-heading">
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
          {measure.isPending
            ? t("headroom.measuring")
            : t("headroom.measureNow")}
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
          <Loader2 className="w-4 h-4 animate-spin" />{" "}
          {t("headroom.readingLast")}
        </p>
      ) : (
        headroom && <Reading headroom={headroom} />
      )}

      {/* What pressing the button involves, said before it is pressed: the
          scene is a one-time 1.3 GB download and fpstune never starts it
          unasked. Only while there is nothing measured — once there is a
          number, the engine is already here. */}
      {!isLoading && !headroom?.is_measured && (
        <>
          <p className="text-sm text-muted-foreground">
            {t("headroom.needsScene")}
          </p>
          <p className="text-sm text-muted-foreground">
            {t("headroom.needsDownload")}
          </p>
        </>
      )}
    </Card>
  );
}

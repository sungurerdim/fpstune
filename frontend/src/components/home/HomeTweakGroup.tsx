import { Loader2 } from "lucide-react";
import { useT } from "../../i18n";
import { cn } from "../../lib/utils";
import type { Setting } from "../../types/setting";
import { Card } from "../ui/Card";
import { Metric, MetricList, ScopeHeader } from "../ui/ScopeHeader";
import { ScopeActions } from "../ScopeActions";
import { TweakListRow } from "../TweakListRow";

export type DomainAccent = "hardware" | "software" | "game";

const DOMAIN_STYLE: Record<
  DomainAccent,
  { card: string; header: string; title: string }
> = {
  hardware: {
    card: "border-l-4 border-l-domain-hardware",
    header: "bg-domain-hardware/10 border-domain-hardware/20",
    title: "text-domain-hardware",
  },
  software: {
    card: "border-l-4 border-l-domain-software",
    header: "bg-domain-software/10 border-domain-software/20",
    title: "text-domain-software",
  },
  game: {
    card: "border-l-4 border-l-domain-game",
    header: "bg-domain-game/10 border-domain-game/20",
    title: "text-domain-game",
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
export function TweakGroup({
  accent,
  title,
  subtitle,
  icon,
  settings,
  detecting,
  categoryLabel,
  children,
}: {
  accent: DomainAccent;
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  settings: Setting[];
  detecting: boolean;
  categoryLabel: (id: string) => string;
  /** Replaces the row list — the hardware group lists its devices instead. */
  children?: React.ReactNode;
}) {
  const { t } = useT();
  const style = DOMAIN_STYLE[accent];
  return (
    <Card className={cn("flex flex-col", style.card)} data-domain={accent}>
      <ScopeHeader
        level={2}
        icon={icon}
        title={title}
        titleClassName={style.title}
        kind={subtitle}
        className={cn("border-b border-border p-3", style.header)}
        metrics={
          <MetricList>
            <Metric
              tone={settings.length > 0 ? "attention" : "neutral"}
              value={settings.length}
              label={t("metric.toApply")}
            />
            {detecting && (
              <Metric
                label={t("devices.reading")}
                icon={<Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
              />
            )}
          </MetricList>
        }
        /* The same Apply every scope has, counted and confirmed the same way. */
        actions={<ScopeActions settings={settings} name={title} only={["apply"]} />}
      />
      {settings.length === 0 ? (
        // An empty group means two different things, and saying the wrong one is a
        // false claim: while detection runs nothing has been read yet, so "already
        // optimized" would assert a result the app does not have.
        <p className="text-xs text-muted-foreground px-3 py-2">
          {detecting ? t("home.readingSettings") : t("home.allOptimized")}
        </p>
      ) : children ? (
        <div className="p-3 grid grid-cols-1 gap-2 items-start 2xl:grid-cols-2">{children}</div>
      ) : (
        <div
          data-testid="tweak-group-rows"
          className="p-3 grid grid-cols-1 gap-2 items-start 2xl:grid-cols-2"
        >
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


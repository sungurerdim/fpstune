import type { ReactNode } from "react";
import { cn } from "../../lib/utils";
import { StatusChip, type ChipTone } from "./StatusChip";

/**
 * The one header every scope wears: a device card, a Home group, a category, a
 * game, a page, a history list.
 *
 * Before this existed each of those drew its own title row, and the device
 * card ran its model name, its kind and its counts together into one
 * unpunctuated stream ("NVIDIA GeForce RTX 3070 Laptop GPU", the kind, "to apply
 * 9", "1 needs you", all on one line). Three levels now, and each is a
 * different thing to look at:
 *
 *   1. the title — a real heading, the largest text in the block;
 *   2. the kind — muted, on its own line directly under the title;
 *   3. the metrics — labelled chips, one fact each, below the title row.
 *
 * The actions slot is the right edge of the title row, and nothing else ever
 * goes there, so Apply / Undo sit in the same place on every page.
 */
export function ScopeHeader({
  title,
  level = 3,
  headingId,
  icon,
  kind,
  metrics,
  actions,
  className,
  titleClassName,
}: {
  /** What the scope is: a model name, a category, a game. A node so a card can make it a link. */
  title: ReactNode;
  /** The heading level, so the page outline holds (a page is 2, a card inside it 3). */
  level?: 2 | 3 | 4;
  headingId?: string;
  icon?: ReactNode;
  /** What kind of thing it is, or the one-line state it reports — never a count. */
  kind?: ReactNode;
  /** A `MetricList`: counts and states, one labelled chip each. */
  metrics?: ReactNode;
  /** A `ScopeActions` (or buttons) — the right edge of the title row. */
  actions?: ReactNode;
  className?: string;
  /** Colours the title, for a scope that carries an accent. */
  titleClassName?: string;
}) {
  const Heading = `h${level}` as "h2" | "h3" | "h4";
  return (
    <div
      data-slot="scope-header"
      className={cn("flex flex-wrap items-start gap-x-3 gap-y-2", className)}
    >
      <div className="flex min-w-0 flex-1 basis-56 items-start gap-2">
        {icon && <span className="mt-0.5 shrink-0">{icon}</span>}
        <div className="min-w-0">
          <Heading
            id={headingId}
            data-slot="scope-title"
            className={cn("truncate text-sm font-semibold leading-snug", titleClassName)}
            title={typeof title === "string" ? title : undefined}
          >
            {title}
          </Heading>
          {kind && (
            <p data-slot="scope-kind" className="text-xs text-muted-foreground">
              {kind}
            </p>
          )}
        </div>
      </div>
      {actions && (
        <div data-slot="scope-actions" className="ml-auto shrink-0">
          {actions}
        </div>
      )}
      {metrics && <div className="basis-full">{metrics}</div>}
    </div>
  );
}

/** The chips of one header, as the list they are: a screen reader hears "list, 2 items". */
export function MetricList({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <ul
      data-slot="scope-metrics"
      aria-label={label}
      className="m-0 flex list-none flex-wrap items-center gap-1.5 p-0"
    >
      {children}
    </ul>
  );
}

/**
 * One fact: a number set apart in bold, then what it counts ("9  to apply"), or
 * a bare state when there is no number ("Ideal"). The colour is the tone's, and
 * the words say the same thing, so the colour is never the only signal.
 */
export function Metric({
  value,
  label,
  tone = "neutral",
  icon,
  title,
  testId,
}: {
  value?: number | string;
  label: string;
  tone?: ChipTone;
  icon?: ReactNode;
  /** Native tooltip: the chip carries the count, the title the why. */
  title?: string;
  testId?: string;
}) {
  return (
    <li data-testid={testId}>
      <StatusChip tone={tone} icon={icon} title={title}>
        {value !== undefined && (
          <>
            <span className="font-bold tabular-nums">{value}</span>{" "}
          </>
        )}
        <span>{label}</span>
      </StatusChip>
    </li>
  );
}

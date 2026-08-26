import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "../../lib/utils";

/**
 * The one card surface (E2). Its class recipe was retyped 13 times across 7
 * files before this existed — the exact decay a primitive prevents.
 */
export function Card({
  className,
  ...rest
}: HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn("bg-card rounded-lg border border-border", className)}
      {...rest}
    />
  );
}

/**
 * A card's title row: icon, heading, optional count, and whatever actions
 * belong on the right. The heading is a real <h2> so the page outline holds.
 */
export function CardHeader({
  icon,
  title,
  count,
  children,
  className,
}: {
  icon?: ReactNode;
  title: string;
  count?: number;
  /** Right-hand side: buttons, chips, spinners. */
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 p-3 border-b border-border",
        className,
      )}
    >
      {icon}
      <h2 className="font-semibold text-sm">{title}</h2>
      {count !== undefined && (
        <span className="text-xs text-muted-foreground">{count}</span>
      )}
      {children && (
        <div className="ml-auto flex items-center gap-2">{children}</div>
      )}
    </div>
  );
}

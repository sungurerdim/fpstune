import type { HTMLAttributes } from "react";
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

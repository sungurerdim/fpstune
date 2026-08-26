import type { HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

/**
 * A small labelled state (E2). Tones are the app's semantic tokens; a badge
 * that needs a colour outside this list is describing a state the design
 * system does not have yet — add the tone, never inline the colour.
 */
const TONES = {
  primary: "bg-primary/15 text-primary border-primary/30",
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/15 text-warning border-warning/30",
  destructive: "bg-destructive/15 text-destructive border-destructive/30",
  muted: "bg-muted text-muted-foreground border-border",
} as const;

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: keyof typeof TONES;
}

export function Badge({ tone = "muted", className, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-xs font-medium",
        TONES[tone],
        className,
      )}
      {...rest}
    />
  );
}

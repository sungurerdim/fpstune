import type { HTMLAttributes, ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { cn } from "../../lib/utils";

/**
 * The feedback primitives (E2): EmptyState, Skeleton, Progress, Meter, Alert.
 * One spelling each for "nothing here", "still loading", "this far along",
 * "this much of that", and "read this first" — the app had five loading
 * treatments and three error colours before these existed.
 */

/** Nothing to show, and why — never a blank region. */
export function EmptyState({
  icon,
  title,
  hint,
  className,
}: {
  icon?: ReactNode;
  title: string;
  /** What would put something here, when that is worth saying. */
  hint?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-1 py-6 text-center",
        className,
      )}
    >
      {icon}
      <p className="text-sm text-muted-foreground">{title}</p>
      {hint && <p className="text-xs text-muted-foreground/70">{hint}</p>}
    </div>
  );
}

/** A placeholder for content that is on its way. */
export function Skeleton({
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded bg-muted", className)}
      {...rest}
    />
  );
}

/** Determinate progress toward done. Indeterminate work wants Skeleton. */
export function Progress({
  value,
  label,
  className,
}: {
  /** 0..100 */
  value: number;
  /** What is progressing — becomes the accessible name. */
  label: string;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-1.5 bg-muted rounded-full overflow-hidden", className)}
    >
      <div
        className="h-full bg-primary transition-all"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

/** How much of a capacity is used — a fact, not progress toward anything. */
export function Meter({
  value,
  max,
  label,
  tone = "primary",
  className,
}: {
  value: number;
  max: number;
  /** What is being measured — becomes the accessible name. */
  label: string;
  tone?: "primary" | "success" | "warning" | "destructive";
  className?: string;
}) {
  const fraction = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  const fill = {
    primary: "bg-primary/60",
    success: "bg-success/70",
    warning: "bg-warning/70",
    destructive: "bg-destructive/70",
  }[tone];
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      className={cn("h-1 bg-muted rounded-full overflow-hidden", className)}
    >
      <div
        className={cn("h-full transition-all", fill)}
        style={{ width: `${fraction * 100}%` }}
      />
    </div>
  );
}

const ALERT_TONES = {
  info: {
    frame: "border-primary/40 bg-primary/[0.06]",
    text: "text-primary",
    icon: Info,
    role: "status" as const,
  },
  success: {
    frame: "border-success/40 bg-success/[0.06]",
    text: "text-success",
    icon: CheckCircle2,
    role: "status" as const,
  },
  warning: {
    frame: "border-warning/40 bg-warning/[0.06]",
    text: "text-warning",
    icon: AlertTriangle,
    role: "alert" as const,
  },
  error: {
    frame: "border-destructive/40 bg-destructive/[0.06]",
    text: "text-destructive",
    icon: XCircle,
    role: "alert" as const,
  },
};

/** A message the user should read before the content below it. */
export function Alert({
  tone,
  title,
  children,
  className,
}: {
  tone: keyof typeof ALERT_TONES;
  title: string;
  children?: ReactNode;
  className?: string;
}) {
  const spec = ALERT_TONES[tone];
  const Icon = spec.icon;
  return (
    <div
      role={spec.role}
      className={cn("rounded-lg border p-3 space-y-1", spec.frame, className)}
    >
      <p className={cn("flex items-center gap-2 text-sm font-medium", spec.text)}>
        <Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
        {title}
      </p>
      {children && (
        <div className="text-xs text-muted-foreground pl-6">{children}</div>
      )}
    </div>
  );
}

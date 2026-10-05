import { cn } from "../../lib/utils";

/** A labelled, tinted container that visually groups related Stat chips. */
export function Group({
  label,
  tone,
  children,
}: {
  label: string;
  /** `muted` is for a group that has nothing to report and says so. */
  tone: "warning" | "success" | "muted";
  children: React.ReactNode;
}) {
  const border =
    tone === "warning"
      ? "border-warning/30 bg-warning/5"
      : tone === "success"
        ? "border-success/30 bg-success/5"
        : "border-border bg-muted/30";
  const text =
    tone === "warning"
      ? "text-warning/80"
      : tone === "success"
        ? "text-success/80"
        : "text-muted-foreground";

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg border pl-2 pr-2.5 py-1.5",
        border,
      )}
    >
      <span className={cn("text-xs font-bold uppercase tracking-wider", text)}>
        {label}
      </span>
      {children}
    </div>
  );
}

export function Stat({
  icon,
  value,
  label,
  hint,
}: {
  icon: React.ReactNode;
  value: string;
  label: string;
  /** What the number is *of*, in plain words. A figure whose referent the reader
   *  has to reconstruct is one they will read as wrong. */
  hint?: string;
}) {
  return (
    <div className="bg-card rounded-md border border-border px-2.5 py-1.5 inline-flex items-center gap-2">
      {icon}
      <div className="min-w-0">
        <p className="text-sm font-semibold leading-tight truncate">{value}</p>
        <p className="text-xs text-muted-foreground uppercase tracking-wider leading-tight">
          {label}
        </p>
        {hint && (
          <p className="text-xs text-muted-foreground/70 leading-tight">
            {hint}
          </p>
        )}
      </div>
    </div>
  );
}

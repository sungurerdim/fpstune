import { useState } from "react";
import { History, Loader2, RotateCcw, Square, Zap } from "lucide-react";
import { useT } from "../i18n";
import { cn } from "../lib/utils";
import { useScopedActions } from "../hooks/useScopedActions";
import type { BulkAction } from "../store";
import type { Setting } from "../types/setting";
import { ConfirmDialog } from "./ui/ConfirmDialog";

/**
 * Apply, Undo and Windows default for one scope — a device, a category, a game,
 * a page or a selection — with the same labels, counts and confirmation
 * everywhere.
 *
 * Anything wider than one row asks first and names the count, because a
 * page-wide Windows default is not a thing to press by accident. Undo appears
 * only when something in the scope has a recorded original: offering it without
 * one would either do nothing or quietly become a reset, which is the wrong
 * promise kept (C6).
 */
export function ScopeActions({
  settings,
  name,
  className,
}: {
  settings: readonly Setting[];
  /** The scope in words ("Wi-Fi", "Network", "Software Tweaks"), read by screen readers. */
  name: string;
  className?: string;
}) {
  const { t } = useT();
  const { targets, start, stop, isRunning } = useScopedActions(settings);
  const [pending, setPending] = useState<BulkAction | null>(null);

  if (isRunning) {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" aria-hidden />
        <button
          type="button"
          onClick={stop}
          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs hover:bg-muted"
        >
          <Square className="h-3 w-3" aria-hidden />
          {t("toolbar.stop")}
        </button>
      </div>
    );
  }

  const counts = {
    apply: targets.apply.length,
    undo: targets.undo.length,
    reset: targets.reset.length,
  };
  if (counts.apply + counts.undo + counts.reset === 0) return null;

  const hasAdvanced = targets.apply.some((s) => s.riskLevel === "advanced");
  // Anything marked Advanced keeps its own question: the gate is named for
  // what it guards, and its answer is "apply anyway", not a plain yes.
  const advancedGate = pending === "apply" && hasAdvanced;
  const title = advancedGate
    ? t("toolbar.advancedTitle")
    : pending
      ? t(`actions.confirm.${pending}`, { count: counts[pending], name })
      : "";
  const body = advancedGate
    ? t("toolbar.advancedBody")
    : pending
      ? t(`actions.confirmBody.${pending}`)
      : "";
  const confirmLabel = advancedGate
    ? t("toolbar.applyAnyway")
    : pending
      ? t(`actions.${pending}Short`)
      : "";

  const buttonBase =
    "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors disabled:opacity-50";

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      <ConfirmDialog
        open={pending !== null}
        title={title}
        confirmLabel={confirmLabel}
        onConfirm={() => {
          if (pending) start(pending);
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      >
        {body}
      </ConfirmDialog>
      {counts.apply > 0 && (
        <button
          type="button"
          onClick={() => setPending("apply")}
          aria-label={t("actions.aria.apply", { count: counts.apply, name })}
          className={cn(buttonBase, "bg-warning/15 text-warning hover:bg-warning/25")}
        >
          <Zap className="h-3.5 w-3.5" aria-hidden />
          {t("actions.apply", { count: counts.apply })}
        </button>
      )}
      {counts.undo > 0 && (
        <button
          type="button"
          onClick={() => setPending("undo")}
          aria-label={t("actions.aria.undo", { count: counts.undo, name })}
          className={cn(buttonBase, "border border-border text-foreground hover:bg-muted")}
        >
          <History className="h-3.5 w-3.5" aria-hidden />
          {t("actions.undo", { count: counts.undo })}
        </button>
      )}
      {counts.reset > 0 && (
        <button
          type="button"
          onClick={() => setPending("reset")}
          aria-label={t("actions.aria.reset", { count: counts.reset, name })}
          className={cn(buttonBase, "border border-border text-muted-foreground hover:bg-muted hover:text-foreground")}
        >
          <RotateCcw className="h-3.5 w-3.5" aria-hidden />
          {t("actions.reset", { count: counts.reset })}
        </button>
      )}
    </div>
  );
}

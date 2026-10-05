import { useState, type ReactNode } from "react";
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
 *
 * Apply and Windows default are always drawn, so the group sits in the same spot
 * on every page and a scope with nothing to do does not shift the layout. A
 * button with nothing to act on is disabled and says why in its accessible name
 * and tooltip, rather than vanishing and leaving the reader to wonder whether it
 * exists.
 */
export function ScopeActions({
  settings,
  name,
  only,
  className,
}: {
  settings: readonly Setting[];
  /** Limit the group to these actions (Home's compact device card shows Apply only). */
  only?: readonly BulkAction[];
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

  const shown = (action: BulkAction) => !only || only.includes(action);
  const counts = {
    apply: shown("apply") ? targets.apply.length : 0,
    undo: shown("undo") ? targets.undo.length : 0,
    reset: shown("reset") ? targets.reset.length : 0,
  };

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
      {shown("apply") && (
        <ActionButton
          action="apply"
          count={counts.apply}
          name={name}
          idleLabel={t("actions.none.apply", { name })}
          icon={<Zap className="h-3.5 w-3.5" aria-hidden />}
          className="bg-warning/15 text-warning hover:bg-warning/25"
          onPress={() => setPending("apply")}
        />
      )}
      {counts.undo > 0 && (
        <ActionButton
          action="undo"
          count={counts.undo}
          name={name}
          icon={<History className="h-3.5 w-3.5" aria-hidden />}
          className="border border-border text-foreground hover:bg-muted"
          onPress={() => setPending("undo")}
        />
      )}
      {shown("reset") && (
        <ActionButton
          action="reset"
          count={counts.reset}
          name={name}
          idleLabel={t("actions.none.reset", { name })}
          icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}
          className="border border-border text-muted-foreground hover:bg-muted hover:text-foreground"
          onPress={() => setPending("reset")}
        />
      )}
    </div>
  );
}

const BUTTON_BASE =
  "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";

/** One action of the group: live with a count, or disabled and naming why. */
function ActionButton({
  action,
  count,
  name,
  idleLabel,
  icon,
  className,
  onPress,
}: {
  action: BulkAction;
  count: number;
  name: string;
  /** Why the button is disabled; absent for an action that is hidden when it has nothing to do. */
  idleLabel?: string;
  icon: ReactNode;
  className: string;
  onPress: () => void;
}) {
  const { t } = useT();
  const idle = count === 0;
  const label = idle && idleLabel ? idleLabel : t(`actions.aria.${action}`, { count, name });
  return (
    <button
      type="button"
      disabled={idle}
      onClick={onPress}
      aria-label={label}
      title={idle ? label : undefined}
      className={cn(BUTTON_BASE, className)}
    >
      {icon}
      {t(`actions.${action}`, { count })}
    </button>
  );
}

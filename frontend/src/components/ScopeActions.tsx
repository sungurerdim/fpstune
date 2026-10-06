import { useState, type ReactNode } from "react";
import { Loader2, RotateCcw, Square, Zap } from "lucide-react";
import { useT } from "../i18n";
import { cn } from "../lib/utils";
import { useScopedActions } from "../hooks/useScopedActions";
import { scopeDomain } from "../lib/tweakDomain";
import type { BulkAction } from "../store";
import type { Setting } from "../types/setting";
import { ConfirmDialog } from "./ui/ConfirmDialog";

/**
 * Apply and Reset to default for one scope — a device, a category, a game, a
 * page or a selection — with the same labels, counts and confirmation
 * everywhere.
 *
 * Anything wider than one row asks first and names the count, because a
 * page-wide reset is not a thing to press by accident.
 *
 * Two buttons, both always drawn so the group sits in the same spot on every
 * page and a scope with nothing to do does not shift the layout: with nothing to
 * act on a button is disabled and says why in its accessible name and tooltip.
 * Reset to default is the one way back, and it names the default by domain —
 * the Windows default, the driver default or the game default — in its tooltip,
 * accessible name and confirmation.
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
  const resetDomain = scopeDomain(targets.reset);

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
      ? pending === "reset"
        ? t(`actions.confirmBody.reset.${resetDomain}`)
        : t("actions.confirmBody.apply")
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
          label={t("actions.aria.apply", { count: counts.apply, name })}
          idleLabel={t("actions.none.apply", { name })}
          icon={<Zap className="h-3.5 w-3.5" aria-hidden />}
          className="bg-warning/15 text-warning hover:bg-warning/25"
          onPress={() => setPending("apply")}
        />
      )}
      {shown("reset") && (
        <ActionButton
          action="reset"
          count={counts.reset}
          idleLabel={t("actions.none.reset", { name })}
          label={t(`actions.aria.reset.${resetDomain}`, { count: counts.reset, name })}
          icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}
          className="border border-border text-foreground hover:bg-muted"
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
  label,
  idleLabel,
  icon,
  className,
  onPress,
}: {
  action: BulkAction;
  count: number;
  /** The accessible name and tooltip of a live button. */
  label: string;
  /** Why the button is disabled. */
  idleLabel: string;
  icon: ReactNode;
  className: string;
  onPress: () => void;
}) {
  const { t } = useT();
  const idle = count === 0;
  const name = idle ? idleLabel : label;
  return (
    <button
      type="button"
      disabled={idle}
      onClick={onPress}
      aria-label={name}
      title={name}
      className={cn(BUTTON_BASE, className)}
    >
      {icon}
      {t(`actions.${action}`, { count })}
    </button>
  );
}

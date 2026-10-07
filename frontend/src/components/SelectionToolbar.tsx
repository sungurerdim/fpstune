/**
 * SelectionToolbar — the one bulk bar: sticky at the bottom, every bulk change
 * of the machine starts here.
 *
 * Two groups, one confirmation, one run (`useApply().run`, the single SSE path):
 * - the selection: "Apply selected" / "Reset selected to default", shown while
 *   at least one row is ticked;
 * - the scope (when the page hands over the rows it shows): "Apply essential",
 *   "Apply recommended" — the primary one — and "Apply complete", each writing
 *   the not-optimized rows up to that level (`levelTargets`).
 *
 * Anything wider than one row asks first and names the count; a target marked
 * Advanced keeps its own question, whose answer is "apply anyway".
 */

import { useMemo, useState, type ReactNode } from "react";
import { Loader2, RotateCcw, Square, X, Zap } from "lucide-react";
import { useT } from "../i18n";
import { cn } from "../lib/utils";
import { useStore, type BulkAction } from "../store";
import { useApply } from "../hooks/useApply";
import { levelTargets, scopeTargets, type ScopeLevel } from "../lib/bulkStream";
import { scopeDomain } from "../lib/tweakDomain";
import type { Setting, SettingId } from "../types/setting";
import { Button, type ButtonProps } from "./ui/Button";
import { ConfirmDialog } from "./ui/ConfirmDialog";

const LEVELS: readonly ScopeLevel[] = ["essential", "recommended", "complete"];

/** The question a button has opened: what it would do, to which rows. */
interface Pending {
  action: BulkAction;
  targets: Setting[];
  /** The scope in words, for the question's title. */
  scopeName: string;
}

export interface SelectionToolbarProps {
  /**
   * The rows the scope buttons act on — the page, category or device in view.
   * Omitted, the bar is selection-only and appears with the first ticked row.
   */
  settings?: readonly Setting[];
  /** The scope in words ("Software", "Network"), read by screen readers. */
  name?: string;
}

export function SelectionToolbar({ settings: scope, name = "" }: SelectionToolbarProps) {
  const { t } = useT();
  const selectedSettingIds = useStore((s) => s.selectedSettingIds);
  const clearSelection = useStore((s) => s.clearSelection);
  const settings = useStore((s) => s.settings);
  const settingsVersion = useStore((s) => s._settingsVersion);
  const { run, stop, isRunning } = useApply();
  const [pending, setPending] = useState<Pending | null>(null);

  const selected = useMemo(
    () =>
      [...selectedSettingIds]
        .map((id) => settings.get(id as SettingId))
        .filter((s): s is Setting => s !== undefined),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
    [selectedSettingIds, settings, settingsVersion],
  );
  const selectionTargets = useMemo(() => scopeTargets(selected), [selected]);
  const levels = useMemo(
    () =>
      scope === undefined
        ? null
        : Object.fromEntries(LEVELS.map((level) => [level, levelTargets(scope, level)])) as Record<
            ScopeLevel,
            Setting[]
          >,
    [scope],
  );

  if (isRunning) {
    return (
      <Bar>
        <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" aria-hidden />
        <button
          type="button"
          onClick={stop}
          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs hover:bg-muted"
        >
          <Square className="h-3 w-3" aria-hidden />
          {t("toolbar.stop")}
        </button>
      </Bar>
    );
  }

  const hasSelection = selectedSettingIds.size > 0;
  if (!hasSelection && levels === null) return null;
  const selectionName = t("toolbar.selected", { count: selectedSettingIds.size });

  const advanced = pending?.action === "apply" && pending.targets.some((s) => s.riskLevel === "advanced");
  const resetDomain = scopeDomain(pending?.targets ?? []);
  const title = pending === null
    ? ""
    : advanced
      ? t("toolbar.advancedTitle")
      : t(`actions.confirm.${pending.action}`, { count: pending.targets.length, name: pending.scopeName });
  const body = pending === null
    ? ""
    : advanced
      ? t("toolbar.advancedBody")
      : pending.action === "reset"
        ? t(`actions.confirmBody.reset.${resetDomain}`)
        : t("actions.confirmBody.apply");
  const confirmLabel = pending === null
    ? ""
    : advanced
      ? t("toolbar.applyAnyway")
      : t(`actions.${pending.action}Short`);

  return (
    <Bar>
      <ConfirmDialog
        open={pending !== null}
        title={title}
        confirmLabel={confirmLabel}
        onConfirm={() => {
          if (pending) {
            run(
              pending.action,
              pending.targets.map((s) => s.id),
            );
          }
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      >
        {body}
      </ConfirmDialog>

      {hasSelection && (
        <>
          <span className="text-sm font-medium text-foreground">{selectionName}</span>
          <button
            type="button"
            onClick={clearSelection}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="w-3.5 h-3.5" />
            {t("toolbar.clear")}
          </button>
          <BarButton
            count={selectionTargets.apply.length}
            text={t("toolbar.applySelected", { count: selectionTargets.apply.length })}
            title={
              selectionTargets.apply.length === 0
                ? t("toolbar.none.apply", { name: selectionName })
                : t("actions.aria.apply", { count: selectionTargets.apply.length, name: selectionName })
            }
            icon={<Zap className="h-3.5 w-3.5" aria-hidden />}
            variant="warning"
            onPress={() =>
              setPending({ action: "apply", targets: selectionTargets.apply, scopeName: selectionName })
            }
          />
          <BarButton
            count={selectionTargets.reset.length}
            text={t("toolbar.resetSelected", { count: selectionTargets.reset.length })}
            title={
              selectionTargets.reset.length === 0
                ? t("toolbar.none.reset", { name: selectionName })
                : t(`actions.aria.reset.${scopeDomain(selectionTargets.reset)}`, {
                    count: selectionTargets.reset.length,
                    name: selectionName,
                  })
            }
            icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}
            variant="outline"
            onPress={() =>
              setPending({ action: "reset", targets: selectionTargets.reset, scopeName: selectionName })
            }
          />
        </>
      )}

      {levels !== null && (
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {LEVELS.map((level) => {
            const targets = levels[level];
            const primary = level === "recommended";
            return (
              <BarButton
                key={level}
                count={targets.length}
                text={t(`toolbar.apply.${level}`, { count: targets.length })}
                title={
                  targets.length === 0
                    ? t("toolbar.none.apply", { name })
                    : t("actions.aria.apply", { count: targets.length, name })
                }
                icon={primary ? <Zap className="h-3.5 w-3.5" aria-hidden /> : undefined}
                variant={primary ? "primary" : "outline"}
                onPress={() => setPending({ action: "apply", targets, scopeName: name })}
              />
            );
          })}
        </div>
      )}
    </Bar>
  );
}

function Bar({ children }: { children: ReactNode }) {
  return (
    <div
      className={cn(
        "fixed bottom-0 left-0 right-0 z-50",
        "bg-card/95 backdrop-blur-xs border-t border-border",
        "px-6 py-3 flex flex-wrap items-center gap-3 shadow-lg",
      )}
    >
      {children}
    </div>
  );
}

/** One button of the bar: live with its count, or disabled and naming why. */
function BarButton({
  count,
  text,
  title,
  icon,
  variant,
  onPress,
}: {
  count: number;
  /** The visible words, which are also the accessible name. */
  text: string;
  /** What a live button will do, or why a disabled one cannot: the tooltip and description. */
  title: string;
  icon?: ReactNode;
  variant: NonNullable<ButtonProps["variant"]>;
  onPress: () => void;
}) {
  return (
    <Button
      size="xs"
      variant={variant}
      icon={icon}
      disabled={count === 0}
      onClick={onPress}
      title={title}
    >
      {text}
    </Button>
  );
}

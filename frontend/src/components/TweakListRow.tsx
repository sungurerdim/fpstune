import { Button } from "./ui/Button";
import { RotateCcw, Zap } from "lucide-react";
import { useT } from "../i18n";
import { localizedDescription, localizedName } from "../i18n/settings";
import { cn } from "../lib/utils";
import { formatBenefit } from "../lib/impact";
import { useApplySingle } from "../hooks/useApplySingle";
import { SettingInfoTooltip } from "./SettingInfoTooltip";
import {
  ImpactCategoryTags,
  RiskWarningBadge,
  SettingValueState,
} from "./SettingStateDisplay";
import type { Setting } from "../types/setting";
import { canResetSetting } from "../types/setting";
import { valueLabel } from "../lib/finding";
import { defaultKindKey } from "../lib/tweakDomain";

/**
 * Compact one-line tweak row for the Home "needs optimization" list: name,
 * description, expected benefit, an advanced-risk pill, and a per-row Apply that
 * sets the recommended value.
 */
export function TweakListRow({
  setting,
  categoryLabel,
}: {
  setting: Setting;
  categoryLabel?: string;
}) {
  const { t } = useT();
  const { applySingle, resetSingle, isPending } = useApplySingle();
  const pending = isPending(setting.id);
  const benefit = formatBenefit(setting);
  // A change made from Home must be reversible from Home — the one screen a
  // new user stays on. The predicate is shared rather than copied: it decides
  // whether a control that rewrites a value appears at all, and two versions of
  // that rule is one too many.
  const canReset = canResetSetting(setting);
  const kind = t(defaultKindKey(setting));
  const resetValue = valueLabel(setting, setting.defaultValue);

  return (
    <div
      data-testid="tweak-list-row"
      data-optimal={String(setting.isOptimized)}
      className={cn(
        "flex items-start gap-3 p-3 rounded-md border border-l-2 transition-colors",
        "border-border hover:border-muted-foreground/50",
        // Same accent language as the full tweak row, so a setting looks the
        // same whether you meet it on Home or in the category list.
        setting.isOptimized
          ? "border-l-success/70 bg-success/8"
          : "border-l-destructive/70 bg-destructive/8",
      )}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          {categoryLabel && (
            <span
              className="text-xs px-1.5 py-0.5 bg-primary/10 text-primary rounded max-w-full truncate"
              title={categoryLabel}
            >
              {categoryLabel}
            </span>
          )}
          <span className="font-medium text-sm wrap-break-word min-w-0">
            {localizedName(setting)}
          </span>
          <RiskWarningBadge setting={setting} />
          <SettingInfoTooltip setting={setting} />
        </div>
        <p className="text-xs text-muted-foreground mt-0.5 wrap-break-word">
          {localizedDescription(setting)}
        </p>
        <div className="flex items-center gap-2 flex-wrap mt-1">
          <SettingValueState setting={setting} />
          <ImpactCategoryTags setting={setting} />
        </div>
        {benefit && (
          <p className="text-xs text-primary mt-1 font-medium">{benefit}</p>
        )}
      </div>
      {canReset && (
        <button
          type="button"
          onClick={() => resetSingle(setting)}
          disabled={pending}
          aria-label={t("row.resetNamedValue", {
            name: setting.displayName,
            kind,
            value: resetValue,
          })}
          title={t("row.resetKindValue", { kind, value: resetValue })}
          className={cn(
            "shrink-0 flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-md font-medium transition-colors",
            "border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50",
            "disabled:opacity-50",
          )}
        >
          <RotateCcw className="w-3.5 h-3.5" aria-hidden />
          {t("action.reset")}
        </button>
      )}
      {/* Home renders one of these per setting that needs changing — thirty on
          a fresh machine. Without the setting's name in here, a screen reader
          announces "Apply, Apply, Apply" and there is no way to tell which one
          is about to change the CPU's minimum clock. */}
      <Button
        className="shrink-0"
        busy={pending}
        icon={<Zap className="w-3.5 h-3.5" />}
        aria-label={t("row.applyNamed", { name: setting.displayName })}
        onClick={() => applySingle(setting, setting.recommendedValue)}
      >
        {t("action.apply")}
      </Button>
    </div>
  );
}

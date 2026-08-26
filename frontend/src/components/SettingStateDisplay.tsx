import { Check } from "lucide-react";
import { cn } from "../lib/utils";
import {
  IMPACT_CATEGORY_META,
  formatSettingValue,
  type Setting,
} from "../types/setting";

/**
 * Shows where a setting actually sits relative to its ideal.
 *
 * Rows used to show only the value you could change it to, so "is this machine
 * already right?" could not be answered by looking at a row — the same question
 * the whole product exists to answer. Optimal collapses to a tick plus the
 * current value; drifted shows current, an arrow, and the ideal.
 */
export function SettingValueState({
  setting,
  className,
}: {
  setting: Setting;
  className?: string;
}) {
  // Actions (cleanup, shader cache) have no "current vs ideal" — they run or
  // they do not, and rendering an arrow between two booleans would be noise.
  if (setting.isAction) return null;

  const isLoading = setting.status === "loading" && setting.currentValue === null;
  if (isLoading) return null;

  const label = (value: unknown) => {
    const formatted = formatSettingValue(value);
    const hint = setting.valueHints?.[String(value)];
    return hint && hint !== formatted ? `${formatted} (${hint})` : formatted;
  };

  if (setting.isOptimized) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 text-xs font-medium text-success",
          className,
        )}
        data-testid="setting-value-state"
        data-state="optimal"
      >
        <Check className="w-3 h-3 shrink-0" aria-hidden />
        {/*
          The tick is decorative and green is a colour, so without this the most
          important fact about a row — is this machine already right? — reached a
          screen reader as the bare number "5", and reached a red/green
          colour-blind user as nothing distinguishable either.
        */}
        <span className="sr-only">Already at the recommended value: </span>
        <span className="truncate">{label(setting.currentValue)}</span>
      </span>
    );
  }

  return (
    <span
      className={cn("inline-flex items-center gap-1 text-xs", className)}
      data-testid="setting-value-state"
      data-state="drifted"
    >
      {/* "100→5" read aloud is "one hundred five". */}
      <span className="sr-only">Currently </span>
      <span className="font-medium text-destructive truncate">
        {label(setting.currentValue)}
      </span>
      <span className="text-muted-foreground/70 shrink-0" aria-hidden>
        →
      </span>
      <span className="sr-only">, recommended value is </span>
      <span className="font-medium text-success truncate">
        {label(setting.recommendedValue)}
      </span>
    </span>
  );
}

/**
 * The kinds of gain a setting delivers. The dashboard header counts "latency
 * tweaks"; these tags are what let you trace that number to the rows behind it.
 */
export function ImpactCategoryTags({
  setting,
  className,
  max,
}: {
  setting: Setting;
  className?: string;
  max?: number;
}) {
  const categories = setting.impactCategories ?? [];
  if (categories.length === 0) return null;

  const shown = max ? categories.slice(0, max) : categories;
  const hidden = categories.length - shown.length;

  return (
    <span
      className={cn("inline-flex items-center gap-1 flex-wrap", className)}
      data-testid="impact-category-tags"
    >
      {shown.map((c) => (
        <span
          key={c}
          data-category={c}
          className={cn(
            "text-xs leading-none px-1.5 py-0.5 rounded border font-medium",
            IMPACT_CATEGORY_META[c].className,
          )}
        >
          {IMPACT_CATEGORY_META[c].label}
        </span>
      ))}
      {hidden > 0 && (
        <span className="text-xs text-muted-foreground/70">+{hidden}</span>
      )}
    </span>
  );
}

/**
 * Risk warning pill.
 *
 * Two defects it fixes: the label read `ADV`, three pixels from a separate
 * `Advisory` state that means something else entirely (detect-only, no Apply);
 * and it only rendered for `advanced`, so the warnings written for 29
 * moderate/low settings were never shown to anyone.
 */
export function RiskWarningBadge({
  setting,
  className,
}: {
  setting: Setting;
  className?: string;
}) {
  if (!setting.riskWarning) return null;

  const isAdvanced = setting.riskLevel === "advanced";

  return (
    <span
      title={setting.riskWarning}
      data-testid="risk-warning-badge"
      data-risk={setting.riskLevel}
      className={cn(
        "text-xs px-1 rounded border shrink-0 cursor-default",
        isAdvanced
          ? "bg-warning/20 text-warning border-warning/30"
          : "bg-muted/60 text-muted-foreground border-border",
        className,
      )}
    >
      {isAdvanced ? "RISK" : "NOTE"}
    </span>
  );
}

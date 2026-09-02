import { Check } from "lucide-react";
import { useT } from "../i18n";
import { advisoryChoiceLabel, describeFinding } from "../lib/finding";
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
  const { t } = useT();
  // Actions (cleanup, shader cache) have no "current vs ideal" — they run or
  // they do not, and rendering an arrow between two booleans would be noise.
  if (setting.isAction) return null;

  const isLoading = setting.status === "loading" && setting.currentValue === null;
  if (isLoading) return null;

  // An advisory that measured something states the measurement as its current
  // state — "Link running at 100 Mbps; the adapter supports 2.5 Gbps." — on
  // every surface that shows the row. The arrow form would only repeat the
  // state name the measurement already explains.
  const measured = setting.isReadonly ? describeFinding(setting) : null;
  if (measured) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 text-xs font-medium",
          setting.isOptimized ? "text-success" : "text-warning",
          className,
        )}
        data-testid="setting-value-state"
        data-state={setting.isOptimized ? "optimal" : "drifted"}
      >
        {setting.isOptimized && <Check className="w-3 h-3 shrink-0" aria-hidden />}
        <span className="sr-only">
          {setting.isOptimized ? t("sr.optimal") : t("sr.currently")}
        </span>
        <span>{measured.summary}</span>
      </span>
    );
  }

  const label = (value: unknown) => {
    // An advisory's value is a state name for the comparison code; the user
    // reads "Below the adapter's maximum", never `below_capability`.
    if (setting.isReadonly) {
      const words = advisoryChoiceLabel(value);
      if (words) return words;
    }
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
        <span className="sr-only">{t("sr.optimal")}</span>
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
      <span className="sr-only">{t("sr.currently")}</span>
      <span className="font-medium text-destructive truncate">
        {label(setting.currentValue)}
      </span>
      <span className="text-muted-foreground/70 shrink-0" aria-hidden>
        →
      </span>
      <span className="sr-only">{t("sr.recommendedIs")}</span>
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
  const { t } = useT();
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
          {t(IMPACT_CATEGORY_META[c].labelKey)}
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
  const { t } = useT();
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
      {isAdvanced ? t("badge.risk") : t("badge.note")}
    </span>
  );
}

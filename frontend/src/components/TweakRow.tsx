/**
 * TweakRow — one setting, one line: ☐ name · current → recommended · Apply · (i).
 *
 * The page answers two questions — what is not optimized, and how do I fix it
 * — so the row is built for scanning: a row that needs work is tinted and
 * carries Apply; a row that is already right is quiet and carries nothing to
 * press. Everything else (why, risk, cost, the way back) is behind the (i).
 *
 * One line at every width: the name and the value text truncate, with their
 * full text in `title` and again in the detail, and nothing wraps. The value
 * text is labelled with the value itself ("Off → On"), never "enabled/disabled".
 *
 * Presentational: the setting and its callbacks come in; no store, no hook that
 * talks to the backend. Whether a row is optimized is the backend's word
 * (`setting.isOptimized`), never recomputed here.
 */

import { Check, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useT } from "../i18n";
import { localizedName } from "../i18n/settings";
import {
  describeFinding,
  explainsWithFinding,
  valueLabel,
} from "../lib/finding";
import { cn } from "../lib/utils";
import { valuesEqual, type Setting } from "../types/setting";
import { Button } from "./ui/Button";
import { TweakDetail } from "./TweakDetail";

/** What a bulk or single run is doing with this row right now. */
export type RowStatus = "queued" | "running" | "verified" | "failed" | "skipped";

export interface TweakRowProps {
  setting: Setting;
  /** Write a value: the recommended one from Apply, a picked one from the choice. */
  onApply: (value: unknown) => void;
  /** Write the setting's own default back: the one way back. */
  onReset: () => void;
  /** Omit `onSelect` and the row has no checkbox. */
  selected?: boolean;
  onSelect?: () => void;
  status?: RowStatus;
  /** Why the last run of this row failed. */
  error?: string;
}

/** A choice of three or more is picked in the row; fewer is just Apply. */
function picksInline(setting: Setting): boolean {
  return (
    setting.valueType === "choice" &&
    setting.choices.length > 2 &&
    setting.isApplicable &&
    !setting.isReadonly &&
    !setting.isAction
  );
}

function ValuePicker({
  setting,
  name,
  disabled,
  onPick,
}: {
  setting: Setting;
  name: string;
  disabled: boolean;
  onPick: (value: string) => void;
}) {
  const { t } = useT();
  const options = setting.choices;
  // The choice the machine is on, found the way the backend compares values:
  // a number that arrived as text is still the same choice.
  const current =
    options.find((choice) => valuesEqual(choice, setting.currentValue)) ?? "";

  return (
    <select
      aria-label={t("row.chooseNamed", { name })}
      value={current}
      disabled={disabled}
      onChange={(event) => onPick(event.target.value)}
      className="min-w-0 max-w-full truncate rounded border border-border bg-background px-1 py-0.5 text-xs text-foreground disabled:opacity-50"
    >
      {current === "" && (
        <option value="" disabled hidden>
          {t("row.notRead")}
        </option>
      )}
      {options.map((choice) => (
        <option key={choice} value={choice}>
          {valueLabel(setting, choice)}
        </option>
      ))}
    </select>
  );
}

function RowState({
  setting,
  name,
  busy,
  onPick,
}: {
  setting: Setting;
  name: string;
  busy: boolean;
  onPick: (value: string) => void;
}) {
  const { t } = useT();
  const optimized = setting.isOptimized;

  if (setting.status === "loading" && setting.currentValue === null) {
    return (
      <span className="inline-flex shrink-0 items-center text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
        <span className="sr-only">{t("row.detecting")}</span>
      </span>
    );
  }
  if (!setting.isApplicable) {
    return (
      <span className="shrink-0 text-xs text-muted-foreground">
        {t("row.notApplicable")}
      </span>
    );
  }
  // A cleanup runs or it does not: an arrow between two of its values is noise.
  if (setting.isAction) return null;

  const hasCurrent =
    setting.currentValue !== null && setting.currentValue !== undefined;
  // An advisory that measured something states the measurement as its state;
  // the arrow form would only repeat the state name the measurement explains.
  const measured = explainsWithFinding(setting) ? describeFinding(setting) : null;
  const from = measured
    ? measured.summary
    : hasCurrent
      ? valueLabel(setting, setting.currentValue)
      : t("row.notRead");
  const to = valueLabel(setting, setting.recommendedValue);

  if (picksInline(setting)) {
    return (
      <span className="inline-flex min-w-0 max-w-[60%] items-center gap-1 text-xs">
        <ValuePicker
          setting={setting}
          name={name}
          disabled={busy}
          onPick={onPick}
        />
        {!optimized && (
          <>
            <span aria-hidden className="shrink-0 text-muted-foreground/70">
              →
            </span>
            <span className="sr-only">{t("sr.recommendedIs")}</span>
            <span className="min-w-0 truncate font-medium text-success" title={to}>
              {to}
            </span>
          </>
        )}
      </span>
    );
  }

  if (optimized || measured) {
    return (
      <span
        className={cn(
          "inline-flex min-w-0 max-w-[55%] items-center gap-1 text-xs",
          optimized ? "text-muted-foreground" : "font-medium text-warning",
        )}
        title={from}
      >
        {optimized && (
          <Check className="h-3 w-3 shrink-0 text-success" aria-hidden />
        )}
        <span className="sr-only">
          {optimized ? t("sr.optimal") : t("sr.currently")}
        </span>
        <span className="min-w-0 truncate">{from}</span>
      </span>
    );
  }

  return (
    <span
      className="inline-flex min-w-0 max-w-[55%] items-center gap-1 text-xs"
      title={`${from} → ${to}`}
    >
      <span className="sr-only">{t("sr.currently")}</span>
      <span className="min-w-0 truncate font-medium text-warning">{from}</span>
      <span aria-hidden className="shrink-0 text-muted-foreground/70">
        →
      </span>
      <span className="sr-only">{t("sr.recommendedIs")}</span>
      <span className="min-w-0 truncate font-medium text-success">{to}</span>
    </span>
  );
}

function RowStatusMark({
  status,
  error,
}: {
  status: RowStatus;
  error?: string;
}) {
  const { t } = useT();
  switch (status) {
    case "queued":
      return (
        <span className="shrink-0 rounded bg-muted/50 px-1 text-xs text-muted-foreground">
          {t("row.queued")}
        </span>
      );
    case "running":
      return (
        <Loader2
          role="img"
          aria-label={t("row.statusRunning")}
          className="h-3.5 w-3.5 shrink-0 animate-spin text-primary"
        />
      );
    case "verified":
      return (
        <CheckCircle2
          role="img"
          aria-label={t("row.statusVerified")}
          className="h-3.5 w-3.5 shrink-0 text-success"
        />
      );
    case "failed":
      return (
        <span
          role="img"
          aria-label={
            error
              ? t("row.statusFailedBecause", { reason: error })
              : t("row.statusFailed")
          }
          title={error}
          className="shrink-0"
        >
          <XCircle className="h-3.5 w-3.5 text-destructive" aria-hidden />
        </span>
      );
    case "skipped":
      return (
        <span className="shrink-0 rounded bg-muted/50 px-1 text-xs text-muted-foreground">
          {t("row.skipped")}
        </span>
      );
  }
}

export function TweakRow({
  setting,
  onApply,
  onReset,
  selected = false,
  onSelect,
  status,
  error,
}: TweakRowProps) {
  const { t } = useT();
  const name = localizedName(setting);

  const loading = setting.status === "loading" && setting.currentValue === null;
  const optimized = setting.isOptimized;
  const running = status === "running";
  const needsWork = setting.isApplicable && !loading && !optimized;
  const canApply = needsWork && !setting.isReadonly;
  const advanced = setting.riskLevel === "advanced";

  const tone = !setting.isApplicable
    ? "border-l-transparent opacity-60"
    : loading
      ? "border-l-muted-foreground/30"
      : optimized
        ? "border-l-transparent hover:bg-muted/30"
        : "border-l-warning bg-warning/8 hover:bg-warning/12";

  return (
    <div
      data-testid="tweak-row"
      data-optimal={setting.isApplicable && !loading ? String(optimized) : undefined}
      className={cn(
        "min-w-0 border-l-2 transition-colors",
        tone,
        selected && "ring-1 ring-primary/40 ring-inset",
      )}
    >
      <TweakDetail
        setting={setting}
        onReset={onReset}
        busy={running}
        error={error}
      >
        {(trigger) => (
          <div className="flex min-w-0 items-center gap-2 px-2 py-1">
            {onSelect && !setting.isReadonly && (
              <input
                type="checkbox"
                checked={selected}
                disabled={!setting.isApplicable}
                onChange={onSelect}
                aria-label={t("row.selectNamed", { name })}
                className="h-4 w-4 shrink-0 cursor-pointer accent-primary"
              />
            )}

            <span
              className={cn(
                "min-w-0 flex-1 truncate text-sm",
                optimized || !setting.isApplicable
                  ? "text-muted-foreground"
                  : "font-medium",
              )}
              title={name}
            >
              {name}
            </span>

            {advanced && (
              <span
                data-testid="risk-chip"
                title={setting.riskWarning}
                className="shrink-0 rounded border border-warning/30 bg-warning/20 px-1 text-xs text-warning"
              >
                {t("badge.risk")}
              </span>
            )}

            <RowState
              setting={setting}
              name={name}
              busy={running}
              onPick={onApply}
            />

            {status && !(canApply && running) && (
              <RowStatusMark status={status} error={error} />
            )}

            {canApply && (
              <Button
                size="xs"
                className="shrink-0"
                busy={running}
                aria-label={t("row.applyNamed", { name })}
                onClick={() => onApply(setting.recommendedValue)}
              >
                {t("action.apply")}
              </Button>
            )}

            {trigger}
          </div>
        )}
      </TweakDetail>
    </div>
  );
}

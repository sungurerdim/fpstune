/**
 * TweakSetting - Single setting row with inline value-type control.
 *
 * Renders appropriate control based on setting's valueType:
 * - choice (2 options): ToggleSwitch
 * - choice (3+ options): PillSelector
 * - int: ToggleSwitch (set to recommended or reset)
 * - bool: ToggleSwitch
 * - string: Read-only text
 *
 * Row background: green = at recommended target, red = not at target.
 */

import { Loader2, RotateCcw, ShieldCheck, CheckCircle2, XCircle, Undo2 } from "lucide-react";
import { cn } from "../lib/utils";
import type { Setting } from "../types/setting";
import { canUndoSetting, formatSettingValue } from "../types/setting";
import { SettingInfoTooltip } from "./SettingInfoTooltip";
import {
  ImpactCategoryTags,
  RiskWarningBadge,
  SettingValueState,
} from "./SettingStateDisplay";
import { ToggleSwitch } from "./ui/ToggleSwitch";
import { PillSelector } from "./ui/PillSelector";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";
import type { OperationStatus } from "../store";

interface TweakSettingProps {
  setting: Setting;
  isPending: boolean;
  isModuleLoading: boolean;
  onApplyValue: (value: unknown) => void;
  /** Write the Windows stock value. Not the same as undoing fpstune. */
  onReset: () => void;
  /** Put the setting back to what this machine held before fpstune touched it.
   *  Offered only when `setting.originalValue` says there is such a value and it
   *  differs from the current one — otherwise the action would be a no-op or,
   *  worse, silently fall through to a reset. */
  onUndo?: () => void;
  onVerify?: () => void;
  isSelected?: boolean;
  onSelect?: () => void;
  operationStatus?: OperationStatus;
  /** Where this row came from, e.g. "Network · Adapters". Carried by the flat
   *  list, which has no category card around the row to say it. */
  contextLabel?: string;
  contextIcon?: React.ReactNode;
}

export function TweakSetting({
  setting,
  isPending,
  isModuleLoading,
  onApplyValue,
  onReset,
  onUndo,
  onVerify,
  isSelected = false,
  onSelect,
  operationStatus,
  contextLabel,
  contextIcon,
}: TweakSettingProps) {
  // Only show loading if never detected (initial load). Re-detect keeps previous value visible.
  const isInitialLoading =
    setting.status === "loading" && setting.currentValue === null;
  const isOptimal = setting.isOptimized;
  const isDisabled = !setting.isApplicable;
  const profileTarget = setting.recommendedValue;

  // See `canUndoSetting`: undo and reset are different promises, and the rule
  // that decides whether this control appears is shared with Home's row.
  const canUndo = onUndo !== undefined && canUndoSetting(setting);

  // Tints are deliberately lighter than they were (/15 and /20 -> /8): with an
  // accent bar carrying the state, the fill only has to be enough to group the
  // row, and 80 saturated rows in a list read as an error report.
  const rowBgClass = isDisabled
    ? "bg-muted/40"
    : isInitialLoading
      ? "bg-muted/20"
      : isOptimal
        ? "bg-success/[0.08] hover:bg-success/[0.14]"
        : "bg-destructive/[0.08] hover:bg-destructive/[0.14]";

  // The bar is what the eye follows down a long list, so it is drawn for BOTH
  // states. Only marking the bad ones left "everything here is fine" as an
  // absence of colour, which reads the same as "not detected yet".
  const accentClass = isDisabled
    ? "border-l-transparent"
    : isInitialLoading
      ? "border-l-muted-foreground/30"
      : isOptimal
        ? "border-l-success/70"
        : "border-l-destructive/70";

  return (
    <div
      data-testid="tweak-row"
      data-optimal={!isDisabled && !isInitialLoading ? String(isOptimal) : undefined}
      className={cn(
        "py-2 px-3 rounded transition-colors border-l-2",
        rowBgClass,
        accentClass,
        isDisabled && "opacity-50",
        isSelected && "ring-1 ring-primary/40",
      )}
    >
      {/* Row 1: Name + badges + control */}
      <div className="flex items-center gap-2 flex-wrap">
        {onSelect && (
          <input
            type="checkbox"
            checked={isSelected}
            onChange={onSelect}
            onClick={(e) => e.stopPropagation()}
            className="w-3.5 h-3.5 shrink-0 accent-primary cursor-pointer"
            aria-label={`Select ${setting.displayName}`}
          />
        )}
        <SettingInfoTooltip setting={setting} />

        <div className="flex items-center gap-1.5 min-w-0 flex-shrink">
          <span
            className={cn(
              "text-xs font-medium leading-tight",
              isDisabled && "text-muted-foreground",
            )}
            style={{ wordBreak: "break-word" }}
          >
            {"shortName" in setting && setting.shortName
              ? setting.shortName
              : setting.displayName}
          </span>
          {setting.evidenceLevel === "proven" && (
            <TooltipProvider>
              <Tooltip delayDuration={300}>
                <TooltipTrigger asChild>
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 shrink-0 cursor-default" />
                </TooltipTrigger>
                <TooltipContent side="top">
                  Proven: 3+ independent sources
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
          {setting.evidenceLevel === "experimental" && (
            <TooltipProvider>
              <Tooltip delayDuration={300}>
                <TooltipTrigger asChild>
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-orange-400 shrink-0 cursor-default" />
                </TooltipTrigger>
                <TooltipContent side="top">
                  Experimental: safe but unproven on modern systems
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
          {setting.requiresReboot && (
            <TooltipProvider>
              <Tooltip delayDuration={300}>
                <TooltipTrigger asChild>
                  <span className="text-[10px] text-warning shrink-0 cursor-default">
                    (R)
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">
                  Requires system restart
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
          {setting.riskWarning && (
            <TooltipProvider>
              <Tooltip delayDuration={200}>
                <TooltipTrigger asChild>
                  <RiskWarningBadge setting={setting} />
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs">
                  {setting.riskWarning}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
          <ImpactCategoryTags setting={setting} max={3} />
        </div>

        <div className="shrink-0 ml-auto flex items-center gap-1">
          {/* SSE bulk operation status badge */}
          {operationStatus === "queued" && (
            <span className="text-[10px] text-muted-foreground/60 px-1 rounded bg-muted/50">
              queued
            </span>
          )}
          {operationStatus === "running" && (
            <Loader2 className="w-3.5 h-3.5 animate-spin text-primary shrink-0" />
          )}
          {operationStatus === "verified" && (
            <CheckCircle2 className="w-3.5 h-3.5 text-success shrink-0" />
          )}
          {operationStatus === "failed" && (
            <XCircle className="w-3.5 h-3.5 text-destructive shrink-0" />
          )}
          {isDisabled ? (
            <span className="text-muted-foreground/30 text-[10px]">N/A</span>
          ) : isInitialLoading ? (
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          ) : setting.isReadonly ? (
            <span
              className={cn(
                "text-[10px] font-medium px-2 py-0.5 rounded border",
                isOptimal
                  ? "text-success border-success/30 bg-success/10"
                  : "text-warning border-warning/30 bg-warning/10",
              )}
            >
              {isOptimal ? "OK" : "Advisory"}
            </span>
          ) : (
            <>
              <SettingValueState setting={setting} className="mr-1 max-w-[14rem]" />
              <InlineControl
                setting={setting}
                profileTarget={profileTarget}
                isOptimal={isOptimal}
                isPending={isPending}
                isModuleLoading={isModuleLoading}
                onApplyValue={onApplyValue}
                onReset={onReset}
              />
              {onVerify && (
                <TooltipProvider>
                  <Tooltip delayDuration={300}>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={onVerify}
                        disabled={isPending || isModuleLoading}
                        className="p-0.5 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
                        aria-label="Verify current value"
                      >
                        <ShieldCheck className="w-3.5 h-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      Verify current value
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
              {canUndo && (
                <TooltipProvider>
                  <Tooltip delayDuration={300}>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={onUndo}
                        disabled={isPending || isModuleLoading}
                        className="p-0.5 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
                        aria-label={`Undo fpstune's change, back to ${String(setting.originalValue)}`}
                      >
                        <Undo2 className="w-3.5 h-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      Undo fpstune's change — back to {String(setting.originalValue)}, what this
                      machine had before
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
              {!isOptimal && (
                <TooltipProvider>
                  <Tooltip delayDuration={300}>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={onReset}
                        disabled={isPending || isModuleLoading}
                        className="p-0.5 rounded hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
                        aria-label="Restore the Windows default"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      Restore the Windows default
                      {setting.defaultValue !== undefined && ` (${String(setting.defaultValue)})`}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
            </>
          )}
        </div>
      </div>

      {/* Row 2: Value labels */}
      {!isDisabled && !isInitialLoading && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 mt-1 ml-7 text-xs">
          {contextLabel && (
            <span className="flex items-center gap-1 min-w-0 text-[10px] text-muted-foreground/70">
              {contextIcon}
              <span className="truncate">{contextLabel}</span>
            </span>
          )}
          <span className="flex items-center gap-1 min-w-0">
            <span className="text-muted-foreground/50 text-[10px] shrink-0">
              Default
            </span>
            <span className="text-muted-foreground font-medium break-words min-w-0">
              {setting.valueHints?.[String(setting.defaultValue)] ?? formatSettingValue(setting.defaultValue)}
            </span>
          </span>
          <span className="flex items-center gap-1 min-w-0">
            <span className="text-muted-foreground/50 text-[10px] shrink-0">
              Current
            </span>
            <span
              className={cn(
                "font-medium break-words min-w-0",
                isOptimal ? "text-success" : "text-warning",
              )}
            >
              {setting.currentValue !== null && setting.valueHints?.[String(setting.currentValue)]
                ? setting.valueHints[String(setting.currentValue)]
                : formatSettingValue(setting.currentValue)}
            </span>
          </span>
          <span className="flex items-center gap-1 min-w-0">
            <span className="text-muted-foreground/50 text-[10px] shrink-0">Target</span>
            <span className="text-primary font-medium break-words min-w-0">
              {setting.valueHints?.[String(profileTarget)] ?? formatSettingValue(profileTarget)}
            </span>
          </span>
        </div>
      )}

      {/* Row 3: Last error banner */}
      {setting.lastError && (
        <p className="mt-1 ml-7 text-[11px] text-destructive leading-tight">
          {setting.lastError}
        </p>
      )}
    </div>
  );
}

function InlineControl({
  setting,
  profileTarget,
  isOptimal,
  isPending,
  isModuleLoading,
  onApplyValue,
  onReset,
}: {
  setting: Setting;
  profileTarget: unknown;
  isOptimal: boolean;
  isPending: boolean;
  isModuleLoading: boolean;
  onApplyValue: (value: unknown) => void;
  onReset: () => void;
}) {
  const disabled = isPending || isModuleLoading;

  // Every choice is a real one. This used to filter out "not_available",
  // because settings listed sentinels among their choices — and it only knew
  // one of the four spellings, so a setting carrying "not_installed" rendered a
  // three-option dropdown where a toggle belonged. The backend no longer offers
  // a sentinel as a choice at all (test_sentinel_contract.py enforces it).
  const userChoices = setting.choices;

  // CHOICE with exactly 2 options → ToggleSwitch
  if (setting.valueType === "choice" && userChoices.length === 2) {
    const targetStr = String(profileTarget);
    const isAtTarget = isOptimal;

    return (
      <TooltipProvider>
        <Tooltip delayDuration={300}>
          <TooltipTrigger asChild>
            <span>
              <ToggleSwitch
                enabled={isAtTarget}
                onToggle={() => {
                  if (isAtTarget) {
                    onReset();
                  } else {
                    onApplyValue(profileTarget);
                  }
                }}
                isPending={isPending}
                size="sm"
                disabled={disabled}
                title={setting.displayName}
              />
            </span>
          </TooltipTrigger>
          <TooltipContent side="top">
            {isAtTarget
              ? `${setting.choices[0]} (reset)`
              : `Set to ${targetStr}`}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // CHOICE with 3+ options → PillSelector
  if (setting.valueType === "choice" && userChoices.length > 2) {
    return (
      <PillSelector
        options={userChoices}
        value={setting.currentValue as string}
        targetValue={profileTarget}
        onChange={(val) => onApplyValue(val)}
        disabled={disabled}
        isPending={isPending}
        valueHints={setting.valueHints}
      />
    );
  }

  // INT → ToggleSwitch (set to recommended or reset to default)
  if (setting.valueType === "int") {
    return (
      <TooltipProvider>
        <Tooltip delayDuration={300}>
          <TooltipTrigger asChild>
            <span>
              <ToggleSwitch
                enabled={isOptimal}
                onToggle={() => {
                  if (isOptimal) {
                    onReset();
                  } else {
                    onApplyValue(profileTarget);
                  }
                }}
                isPending={isPending}
                size="sm"
                disabled={disabled}
                title={setting.displayName}
              />
            </span>
          </TooltipTrigger>
          <TooltipContent side="top">
            {isOptimal
              ? `Reset to ${setting.defaultValue}`
              : `Set to ${profileTarget}`}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // BOOL → ToggleSwitch
  if (setting.valueType === "bool") {
    const isOn =
      setting.currentValue === true || setting.currentValue === "true";
    return (
      <ToggleSwitch
        enabled={isOn}
        onToggle={() => onApplyValue(!isOn)}
        isPending={isPending}
        size="sm"
        disabled={disabled}
        title={setting.displayName}
      />
    );
  }

  // STRING / fallback → read-only text with current value indicator
  return (
    <span
      className={cn(
        "text-xs font-mono px-2 py-0.5 rounded bg-muted",
        isOptimal ? "text-success" : "text-warning",
      )}
    >
      {String(setting.currentValue ?? "-")}
    </span>
  );
}

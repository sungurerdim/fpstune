/**
 * TweakDetail — everything a one-line row leaves out, behind its (i).
 *
 * The row says what is wrong and offers the fix; this says why, what it costs,
 * and the way back. It opens in place under the row (full width, so a 360 px
 * window reads it as easily as a wide one) and closes with Escape, returning
 * focus to the (i) it came from.
 *
 * Presentational: the setting and one callback come in, nothing is read from
 * the store. The (i) has to sit inside the row's line while its panel opens
 * under the whole row, so the component takes the line as a function and hands
 * it the (i) to place.
 */

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Info, RotateCcw } from "lucide-react";
import { useT } from "../i18n";
import {
  localizedDescription,
  localizedEffect,
  localizedName,
} from "../i18n/settings";
import { describeFinding, valueLabel } from "../lib/finding";
import { cn } from "../lib/utils";
import { defaultKindKey } from "../lib/tweakDomain";
import {
  canResetSetting,
  IMPACT_CATEGORY_META,
  type Setting,
} from "../types/setting";
import { Button } from "./ui/Button";

/** The host of a source link; a malformed URL is shown as written, not thrown. */
function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

interface DetailPanelProps {
  setting: Setting;
  /** Matches the `aria-controls` of the (i) that opened it. */
  id: string;
  onReset: () => void;
  busy: boolean;
  error?: string;
}

/**
 * The measured fact behind an advisory, or the current → recommended pair.
 *
 * Split out of the panel so each rule keeps its own branch count (P-KISS): the
 * panel was one 43-branch function, and none of the branches were about the
 * panel's own job of laying the sections out.
 */
function StateLine({ setting }: { setting: Setting }) {
  const { t } = useT();
  const optimized = setting.isOptimized;
  const finding = describeFinding(setting);
  const hasCurrent =
    setting.currentValue !== null && setting.currentValue !== undefined;

  if (!setting.isApplicable || setting.isAction) return null;

  if (finding) {
    return (
      <p className="wrap-break-word">
        <span>{finding.summary}</span>
        {finding.advice && (
          <span className="text-muted-foreground"> {finding.advice}</span>
        )}
      </p>
    );
  }
  return (
    <p className="wrap-break-word">
      <span className="text-muted-foreground">{t("tooltip.current")} </span>
      <span className={cn("font-medium", !optimized && "text-warning")}>
        {hasCurrent
          ? valueLabel(setting, setting.currentValue, { withRawValue: true })
          : t("row.notRead")}
      </span>
      {!optimized && !setting.isReadonly && (
        <>
          <span className="text-muted-foreground">
            {" · "}
            {t("tooltip.recommended")}{" "}
          </span>
          <span className="font-medium text-success">
            {valueLabel(setting, setting.recommendedValue, {
              withRawValue: true,
            })}
          </span>
        </>
      )}
    </p>
  );
}

/** What the setting claims, in its own words: never added up (C11 rule 1). */
function ClaimsRow({ setting }: { setting: Setting }) {
  const { t } = useT();
  const claims = Object.entries(setting.impactScores ?? {});
  const categories = setting.impactCategories ?? [];
  if (claims.length === 0 && categories.length === 0) return null;

  return (
    <div className="flex min-w-0 flex-wrap gap-1">
      {categories.map((c) => (
        <span
          key={c}
          data-category={c}
          className={cn(
            "rounded border px-1.5 py-0.5 leading-none font-medium",
            IMPACT_CATEGORY_META[c].className,
          )}
        >
          {t(IMPACT_CATEGORY_META[c].labelKey)}
        </span>
      ))}
      {claims.map(([key, value]) => (
        <span
          key={key}
          className="inline-flex min-w-0 items-center rounded bg-muted px-1.5 py-0.5"
        >
          <span className="capitalize">{key.replace(/_/g, " ")}:</span>
          <span className="ml-1 font-medium text-primary">{value}</span>
        </span>
      ))}
    </div>
  );
}

/** The risk sentence, with the chip naming whether it is a warning or a note. */
function RiskRow({ setting }: { setting: Setting }) {
  const { t } = useT();
  if (!setting.riskWarning) return null;
  const isAdvanced = setting.riskLevel === "advanced";

  return (
    <div className="flex min-w-0 items-start gap-1.5">
      <span
        data-testid="detail-risk-chip"
        data-risk={setting.riskLevel}
        className={cn(
          "shrink-0 rounded border px-1",
          isAdvanced
            ? "border-warning/30 bg-warning/20 text-warning"
            : "border-border bg-muted/60 text-muted-foreground",
        )}
      >
        {isAdvanced ? t("badge.risk") : t("badge.note")}
      </span>
      <p className="min-w-0 flex-1 wrap-break-word">{setting.riskWarning}</p>
    </div>
  );
}

/** What "Reset to default" writes back, and whose stock that is (C6). */
function DefaultRow({
  setting,
  onReset,
  busy,
}: {
  setting: Setting;
  onReset: () => void;
  busy: boolean;
}) {
  const { t } = useT();
  const name = localizedName(setting);
  // The same predicate every surface asks, so the button appears exactly when
  // there is something to write back.
  const canReset = canResetSetting(setting);
  const hasDefault =
    setting.isApplicable &&
    !setting.isAction &&
    !setting.isReadonly &&
    setting.defaultValue !== null &&
    setting.defaultValue !== undefined;
  if (!hasDefault) return null;

  const kind = t(defaultKindKey(setting));
  const defaultLabel = valueLabel(setting, setting.defaultValue);

  return (
    <div className="flex min-w-0 items-center gap-2">
      <p className="min-w-0 flex-1 text-muted-foreground wrap-break-word">
        {t("detail.defaultIs", { kind, value: defaultLabel })}
      </p>
      {canReset && (
        <Button
          variant="outline"
          size="xs"
          className="shrink-0"
          busy={busy}
          icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}
          aria-label={t("row.resetNamedValue", {
            name,
            kind,
            value: defaultLabel,
          })}
          title={t("row.resetKindValue", { kind, value: defaultLabel })}
          onClick={onReset}
        >
          {t("action.reset")}
        </Button>
      )}
    </div>
  );
}

/** Where the claim comes from, as hostnames a person can read. */
function SourcesRow({ setting }: { setting: Setting }) {
  const { t } = useT();
  if (setting.sources.length === 0) return null;

  return (
    <div className="flex min-w-0 flex-wrap gap-x-3 gap-y-0.5">
      <span className="font-medium text-muted-foreground">
        {t("tooltip.sources")}
      </span>
      {setting.sources.map((url) => (
        <a
          key={url}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          title={url}
          className="min-w-0 truncate text-primary/80 hover:text-primary"
        >
          {hostOf(url)}
        </a>
      ))}
    </div>
  );
}

function DetailPanel({ setting, id, onReset, busy, error }: DetailPanelProps) {
  const { t } = useT();
  const name = localizedName(setting);
  const description = localizedDescription(setting);
  const effect = localizedEffect(setting);

  const optimized = setting.isOptimized;
  const failure = error ?? setting.lastError;
  // A readonly row has no Apply: its `effect` is written as the instruction,
  // so it is labelled as one.
  const showImpact = !optimized || setting.isReadonly;

  return (
    <div
      id={id}
      role="region"
      aria-label={t("tooltip.ariaInfo", { name })}
      data-testid="tweak-detail"
      className="min-w-0 space-y-1.5 border-t border-border/40 bg-muted/20 py-2 pr-3 pl-3 text-xs"
    >
      <p className="text-sm font-medium wrap-break-word">{name}</p>

      {description && (
        <p className="text-muted-foreground wrap-break-word">{description}</p>
      )}

      <StateLine setting={setting} />

      {!optimized && setting.currentImpact && (
        <p className="text-muted-foreground wrap-break-word">
          {setting.currentImpact}
        </p>
      )}
      {setting.recommendedImpact && (
        <p className="text-success/90 wrap-break-word">
          {setting.recommendedImpact}
        </p>
      )}

      {effect && showImpact && (
        <p className="wrap-break-word">
          <span className="font-medium text-primary">
            {setting.isReadonly ? t("tooltip.howToChange") : t("tooltip.effect")}{" "}
          </span>
          <span className="text-muted-foreground">{effect}</span>
        </p>
      )}

      <ClaimsRow setting={setting} />
      <RiskRow setting={setting} />

      {setting.perceptibleCost && (
        <p className="wrap-break-word">
          <span className="font-medium">{t("detail.cost")} </span>
          <span className="text-muted-foreground">{setting.perceptibleCost}</span>
        </p>
      )}

      {setting.requiresReboot && (
        <p className="text-warning wrap-break-word">
          {t("tooltip.requiresRestart")}
        </p>
      )}

      {setting.isReadonly && (
        <p className="text-muted-foreground wrap-break-word">
          {t("tooltip.monitorOnly")}
        </p>
      )}

      <DefaultRow setting={setting} onReset={onReset} busy={busy} />
      <SourcesRow setting={setting} />

      {!setting.isApplicable && (
        <p className="text-destructive wrap-break-word">
          {setting.applicableReason || t("detection.absentFallback")}
        </p>
      )}

      {setting.detectionError && (
        <p className="text-destructive wrap-break-word">
          {setting.detectionError}
        </p>
      )}

      {failure && (
        <p className="text-destructive wrap-break-word">{failure}</p>
      )}
    </div>
  );
}

interface TweakDetailProps {
  setting: Setting;
  /** Write the setting's own default back: the one way back. */
  onReset: () => void;
  /** The reset is running: the button is busy and cannot be pressed twice. */
  busy?: boolean;
  /** The last failure this session, when the row's own `lastError` is older. */
  error?: string;
  /**
   * The row's line. It receives the (i) to place wherever it belongs in the
   * line; the panel opens under whatever it returns. Without it, the (i) is
   * all there is.
   */
  children?: (trigger: ReactNode) => ReactNode;
}

/**
 * The (i) and the panel it opens, as one disclosure.
 *
 * Escape closes it from anywhere inside — the (i), the Apply beside it, a
 * control in the panel — and puts focus back on the (i). Without that, a
 * keyboard user who tabbed into the panel and pressed Escape would lose their
 * place when the focused button unmounted with it.
 */
export function TweakDetail({
  setting,
  onReset,
  busy = false,
  error,
  children,
}: TweakDetailProps) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const name = localizedName(setting);

  // Escape closes the detail from anywhere inside it. On the document in the
  // capture phase, not on a div: a div with an interactive key handler is not
  // keyboard-operable, and jsx-a11y rejects one. Capture also keeps the key to
  // this disclosure, so a dialog around the list does not close with it.
  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const root = rootRef.current;
      if (!root || !(event.target instanceof Node) || !root.contains(event.target)) {
        return;
      }
      event.stopPropagation();
      setOpen(false);
      triggerRef.current?.focus();
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [open]);

  const trigger = (
    <button
      ref={triggerRef}
      type="button"
      onClick={() => setOpen((was) => !was)}
      aria-expanded={open}
      // Only while the panel exists: an id that points at nothing is an
      // invalid reference, and a closed disclosure has nothing to point at.
      aria-controls={open ? panelId : undefined}
      aria-label={t("tooltip.ariaInfo", { name })}
      className={cn(
        "shrink-0 rounded p-1 transition-colors",
        "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
        open && "bg-muted/50 text-foreground",
      )}
    >
      <Info className="h-4 w-4" aria-hidden />
    </button>
  );

  return (
    <div ref={rootRef} className="min-w-0">
      {children ? children(trigger) : trigger}
      {open && (
        <DetailPanel
          id={panelId}
          setting={setting}
          onReset={onReset}
          busy={busy}
          error={error}
        />
      )}
    </div>
  );
}

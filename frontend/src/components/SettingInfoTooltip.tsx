/**
 * Setting Info Tooltip Component
 *
 * Displays detailed information about a setting on hover.
 * Shows description, current/recommended impact, and applicability status.
 */

import { Info, Eye } from "lucide-react";
import { cn } from "../lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";
import type { Setting } from "../types/setting";

interface SettingInfoTooltipProps {
  setting: Setting;
  className?: string;
  variant?: "info" | "hint" | "warning";
}

const VARIANT_COLORS: Record<string, string> = {
  info: "text-muted-foreground hover:text-foreground",
  hint: "text-primary/70 hover:text-primary",
  warning: "text-warning hover:text-warning/80",
};

export function SettingInfoTooltip({
  setting,
  className = "",
  variant = "info",
}: SettingInfoTooltipProps) {
  return (
    <TooltipProvider>
      <Tooltip delayDuration={200}>
        <TooltipTrigger asChild>
          <button
            type="button"
            className={`p-0.5 rounded hover:bg-muted/50 transition-colors ${className}`}
            aria-label={`Information about ${setting.displayName}`}
          >
            <Info className={`h-4 w-4 ${VARIANT_COLORS[variant]}`} />
          </button>
        </TooltipTrigger>
        <TooltipContent
          side="right"
          align="start"
          className="max-w-sm p-3 space-y-2"
        >
          {/* Title and badges */}
          <div className="flex items-start justify-between gap-2">
            <p className="font-medium text-sm">{setting.displayName}</p>
            <div className="flex gap-1">
              <span
                className={cn(
                  "text-xs px-1.5 py-0.5 rounded bg-muted",
                  setting.evidenceLevel === "proven" && "text-green-500",
                  setting.evidenceLevel === "experimental" && "text-orange-400",
                  setting.evidenceLevel === "likely" && "text-muted-foreground",
                )}
              >
                {setting.evidenceLevel === "proven"
                  ? "Proven"
                  : setting.evidenceLevel === "experimental"
                    ? "Experimental"
                    : "Likely"}
              </span>
            </div>
          </div>

          {/* Description */}
          <p className="text-sm text-muted-foreground leading-relaxed">
            {setting.description}
          </p>

          {/* What the machine is actually at, and what the other state means.
              `currentImpact` is not a readout — per C3 it is a static line
              describing the un-optimised state. Labelling it "Current setting:"
              unconditionally told a machine that was already optimal that it was
              still at the default, directly contradicting the green tick on the
              same row. So "Current" now follows the detected state. */}
          {setting.isOptimized ? (
            // Confirmation, not persuasion. A setting already at its ideal does
            // not need the case for changing it — that argument is only useful
            // while there is still a decision to make.
            setting.recommendedImpact && (
              <div className="text-xs space-y-0.5">
                <span className="font-medium text-success">Current:</span>
                <p className="text-success/80">{setting.recommendedImpact}</p>
              </div>
            )
          ) : (
            <>
              {setting.currentImpact && (
                <div className="text-xs space-y-0.5">
                  <span className="font-medium text-muted-foreground">
                    Current:
                  </span>
                  <p className="text-muted-foreground/80">
                    {setting.currentImpact}
                  </p>
                </div>
              )}
              {setting.recommendedImpact && (
                <div className="text-xs space-y-0.5">
                  <span className="font-medium text-success">Recommended:</span>
                  <p className="text-success/80">{setting.recommendedImpact}</p>
                </div>
              )}
            </>
          )}

          {/* Advisory notice */}
          {setting.isReadonly && (
            <div className="flex items-start gap-1.5 text-xs pt-1.5 mt-1.5 border-t border-border/30 text-warning">
              <Eye className="w-3 h-3 mt-0.5 shrink-0" />
              <span>
                FPSTune cannot apply this automatically — monitor only.
              </span>
            </div>
          )}

          {/* Effect and its numbers are the argument for applying, so they are
              shown while there is still something to apply. An advisory setting
              keeps them regardless: it has no Apply button, so this block is the
              only place that says what to do about it. */}
          {setting.effect && (!setting.isOptimized || setting.isReadonly) && (
            <div className="text-xs pt-1.5 mt-1.5 border-t border-border/30 space-y-1">
              <span
                className={cn(
                  "font-medium",
                  setting.isReadonly ? "text-warning" : "text-primary",
                )}
              >
                {setting.isReadonly ? "How to change:" : "Effect:"}
              </span>
              <p className="text-muted-foreground">{setting.effect}</p>
              {setting.impactScores &&
                Object.keys(setting.impactScores).length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {Object.entries(setting.impactScores).map(
                      ([key, value]) => (
                        <span
                          key={key}
                          className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-muted"
                        >
                          <span className="capitalize">
                            {key.replace(/_/g, " ")}:
                          </span>
                          <span className="ml-1 font-medium text-primary">
                            {value}
                          </span>
                        </span>
                      ),
                    )}
                  </div>
                )}
            </div>
          )}

          {/* Sources back the recommendation. Once the machine is already there,
              they are evidence for a decision nobody still has to make. */}
          {setting.sources &&
            setting.sources.length > 0 &&
            (!setting.isOptimized || setting.isReadonly) && (
            <div className="text-xs pt-1 mt-1 border-t border-border/30 space-y-0.5">
              <span className="text-muted-foreground font-medium">
                Sources:
              </span>
              {setting.sources.map((url, i) => {
                const domain = new URL(url).hostname.replace("www.", "");
                return (
                  <a
                    key={i}
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-primary/70 hover:text-primary truncate"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {domain}
                  </a>
                );
              })}
            </div>
          )}

          {/* Requires reboot warning */}
          {setting.requiresReboot && (
            <div className="text-xs text-warning flex items-center gap-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-warning" />
              Requires system restart
            </div>
          )}

          {/* Not applicable warning */}
          {!setting.isApplicable && (
            <div className="text-xs text-destructive flex items-center gap-1 pt-1 border-t border-destructive/20">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-destructive" />
              {setting.applicableReason || "Not applicable to this system"}
            </div>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

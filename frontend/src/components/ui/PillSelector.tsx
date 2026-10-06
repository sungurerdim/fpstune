import { Loader2 } from "lucide-react";
import { useT } from "../../i18n";
import { cn } from "../../lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./tooltip";

interface PillSelectorProps {
  options: string[];
  value: string | null;
  targetValue: unknown;
  onChange: (value: string) => void;
  disabled?: boolean;
  isPending?: boolean;
  /** The text of an option: the caller's one value formatter (`valueLabel`). */
  labelFor: (option: string) => string;
}

export function PillSelector({
  options,
  value,
  targetValue,
  onChange,
  disabled = false,
  isPending = false,
  labelFor,
}: PillSelectorProps) {
  const { t } = useT();
  if (isPending) {
    return <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />;
  }

  return (
    <div className="flex flex-wrap gap-0.5 bg-muted/50 rounded-md p-0.5">
      {options.map((option) => {
        const isActive =
          value !== null &&
          String(value).toLowerCase() === option.toLowerCase();
        const isTarget =
          String(targetValue).toLowerCase() === option.toLowerCase();

        const label = labelFor(option);
        const btn = (
          <button
            key={option}
            onClick={() => !disabled && onChange(option)}
            disabled={disabled}
            className={cn(
              "px-2 py-0.5 text-xs rounded transition-all font-medium",
              isActive
                ? "bg-primary text-primary-foreground shadow-xs"
                : isTarget
                  ? "text-primary bg-primary/10 ring-1 ring-primary/30"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted",
              disabled && "opacity-50 cursor-not-allowed",
            )}
          >
            {label}
          </button>
        );

        if (isTarget && !isActive) {
          return (
            <TooltipProvider key={option}>
              <Tooltip delayDuration={300}>
                <TooltipTrigger asChild>{btn}</TooltipTrigger>
                <TooltipContent side="top">{t("row.target")}: {label}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          );
        }
        return btn;
      })}
    </div>
  );
}

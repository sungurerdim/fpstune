import { Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";

interface ToggleSwitchProps {
  enabled: boolean;
  onToggle: () => void;
  isPending?: boolean;
  disabled?: boolean;
  size?: "xs" | "sm" | "md";
  /**
   * The switch's accessible name as well as its hover tooltip. The button has
   * no text content, so without this a screen reader announces "switch" and
   * nothing else — pass the same text that labels the control visually in the
   * row, never a phrase invented for the tooltip alone.
   */
  title?: string;
  /**
   * Id of the element that says why the switch is in the state it is in — the
   * adapter card's "Not controllable" badge, for instance. The reason has to
   * travel as a description rather than as part of the name: the name is the
   * thing the switch controls, and a reason rendered merely *beside* a disabled
   * control is only met after the control has already been passed over.
   */
  describedBy?: string;
}

const sizeConfig = {
  xs: {
    track: "w-4 h-2.5",
    thumb: "w-1.5 h-1.5",
    translate: "translate-x-1.5",
    spinner: "w-2.5 h-2.5",
  },
  sm: {
    track: "w-5 h-3",
    thumb: "w-2 h-2",
    translate: "translate-x-2",
    spinner: "w-3 h-3",
  },
  md: {
    track: "w-6 h-3.5",
    thumb: "w-2.5 h-2.5",
    translate: "translate-x-2.5",
    spinner: "w-3.5 h-3.5",
  },
};

/**
 * Shared toggle switch component for consistent UI across the app.
 * Replaces duplicate inline toggle implementations.
 */
export function ToggleSwitch({
  enabled,
  onToggle,
  isPending = false,
  disabled = false,
  size = "md",
  title,
  describedBy,
}: ToggleSwitchProps) {
  const sizeClasses = sizeConfig[size];

  if (isPending) {
    // The switch leaves the tree entirely while an operation is in flight, so
    // there is no half-working control to activate a second time.
    return (
      <Loader2
        role="status"
        aria-label={title}
        className={cn(
          "animate-spin text-muted-foreground",
          sizeClasses.spinner,
        )}
      />
    );
  }

  return (
    <button
      onClick={onToggle}
      disabled={disabled}
      className="shrink-0 rounded-full"
      title={title}
      aria-label={title}
      aria-describedby={describedBy}
      role="switch"
      aria-checked={enabled}
      type="button"
    >
      <div
        className={cn(
          sizeClasses.track,
          "rounded-full transition-colors flex items-center px-0.5",
          enabled ? "bg-success" : "bg-muted",
          disabled && "opacity-50 cursor-not-allowed",
        )}
      >
        <div
          className={cn(
            sizeClasses.thumb,
            "rounded-full bg-white shadow-sm transition-transform",
            enabled ? sizeClasses.translate : "translate-x-0",
          )}
        />
      </div>
    </button>
  );
}

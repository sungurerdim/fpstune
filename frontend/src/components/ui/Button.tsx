import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";

/**
 * The one button (E2). Before this existed, the primary recipe was retyped 13
 * times and the small-button recipe 12 — thirteen places for a hover shade to
 * drift apart, and none of them handled the busy state the same way.
 *
 * `busy` is the working state: it disables the button, swaps the icon for a
 * spinner, and sets aria-busy, so a caller cannot show a spinner while
 * leaving the button clickable.
 */

const VARIANTS = {
  /** The main action of a surface. */
  primary:
    "bg-primary text-primary-foreground hover:bg-primary/90 font-medium",
  /** An action that changes something the user should look at first. */
  warning: "bg-warning/15 text-warning hover:bg-warning/25 font-medium",
  /** The affirmative button of a confirmation — loud on purpose. */
  confirm:
    "bg-warning text-warning-foreground hover:bg-warning/80 font-medium",
  /** A secondary action beside a louder one. */
  outline:
    "border border-border text-muted-foreground hover:text-foreground hover:bg-muted/50",
  /** An action that should not compete for attention until hovered. */
  ghost: "text-muted-foreground hover:text-foreground hover:bg-muted/50",
} as const;

const SIZES = {
  xs: "px-2 py-1 text-xs gap-1 rounded",
  sm: "px-3 py-1.5 text-xs gap-1.5 rounded-md",
  md: "px-4 py-2 text-sm gap-1.5 rounded-md",
} as const;

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof VARIANTS;
  size?: keyof typeof SIZES;
  /** Working: disabled + spinner + aria-busy, as one state. */
  busy?: boolean;
  /** Leading icon; replaced by the spinner while busy. */
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "primary",
      size = "sm",
      busy = false,
      icon,
      className,
      children,
      disabled,
      ...rest
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type="button"
        disabled={disabled || busy}
        aria-busy={busy}
        className={cn(
          "inline-flex items-center justify-center transition-colors disabled:opacity-50",
          VARIANTS[variant],
          SIZES[size],
          className,
        )}
        {...rest}
      >
        {busy ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
        ) : (
          icon
        )}
        {children}
      </button>
    );
  },
);

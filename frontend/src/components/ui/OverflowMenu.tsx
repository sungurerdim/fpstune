import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { MoreHorizontal } from "lucide-react";
import { cn } from "../../lib/utils";

export interface OverflowMenuItem {
  id: string;
  /** The words on the item. */
  label: string;
  icon?: ReactNode;
  /** Spoken name when it must say more than the label (a count, a scope). */
  ariaLabel?: string;
  /** Present and true: the item stays reachable but does nothing, and `ariaLabel` says why. */
  disabled?: boolean;
  onSelect: () => void;
}

/**
 * A "⋯" button that opens a small menu of the actions kept out of the way.
 *
 * Built to the ARIA menu-button pattern, because a menu that only works with a
 * pointer is a control that is missing for everyone else:
 *
 *   - the trigger is a button with `aria-haspopup="menu"` and `aria-expanded`;
 *     Enter, Space, click and ArrowDown open it, ArrowUp opens it on the last item;
 *   - the open menu is `role="menu"` of `role="menuitem"` buttons, focus moves
 *     into it, ArrowUp/ArrowDown/Home/End move within it and wrap;
 *   - Escape closes it and puts focus back on the trigger; Tab and a press
 *     outside close it;
 *   - choosing an item closes the menu with focus back on the trigger *before*
 *     the action runs, so a confirmation the action opens remembers the trigger
 *     — not a menu item that no longer exists — as where to return.
 *
 * A disabled item keeps `aria-disabled` and stays in the arrow-key order: it is
 * announced with its reason instead of silently vanishing from the list.
 */
export function OverflowMenu({
  label,
  items,
  side = "bottom",
  className,
}: {
  /** The trigger's accessible name ("More actions: Network"). */
  label: string;
  items: readonly OverflowMenuItem[];
  /** Which way the menu opens: a bar fixed to the bottom of the window opens upward. */
  side?: "bottom" | "top";
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [startAt, setStartAt] = useState<"first" | "last">("first");
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  const itemButtons = () =>
    Array.from(rootRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);

  // Focus enters the menu as it opens: the first item, or the last for ArrowUp.
  useEffect(() => {
    if (!open) return;
    const buttons = itemButtons();
    (startAt === "last" ? buttons[buttons.length - 1] : buttons[0])?.focus();
  }, [open, startAt]);

  // A press anywhere else closes it. Focus stays where the user put it.
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const openAt = (where: "first" | "last") => {
    setStartAt(where);
    setOpen(true);
  };

  const closeToTrigger = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const onTriggerKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      openAt("first");
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openAt("last");
    }
  };

  const onMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const buttons = itemButtons();
    const at = buttons.indexOf(document.activeElement as HTMLElement);
    const focusAt = (index: number) => {
      event.preventDefault();
      buttons[(index + buttons.length) % buttons.length]?.focus();
    };
    switch (event.key) {
      case "ArrowDown":
        focusAt(at + 1);
        break;
      case "ArrowUp":
        focusAt(at - 1);
        break;
      case "Home":
        focusAt(0);
        break;
      case "End":
        focusAt(buttons.length - 1);
        break;
      case "Escape":
        // One layer per press: a menu inside a dialog must not close the dialog too.
        event.stopPropagation();
        event.preventDefault();
        closeToTrigger();
        break;
      case "Tab":
        setOpen(false);
        break;
    }
  };

  if (items.length === 0) return null;

  return (
    <div ref={rootRef} className={cn("relative inline-flex", className)}>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={label}
        title={label}
        onClick={() => (open ? setOpen(false) : openAt("first"))}
        onKeyDown={onTriggerKeyDown}
        className="inline-flex items-center rounded-md border border-border p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <MoreHorizontal className="h-3.5 w-3.5" aria-hidden />
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKeyDown}
          className={cn(
            "absolute right-0 z-dropdown min-w-max rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-overlay",
            side === "top" ? "bottom-full mb-1" : "top-full mt-1",
          )}
        >
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              tabIndex={-1}
              aria-disabled={item.disabled ? true : undefined}
              aria-label={item.ariaLabel}
              title={item.disabled ? item.ariaLabel : undefined}
              onClick={() => {
                if (item.disabled) return;
                closeToTrigger();
                item.onSelect();
              }}
              className={cn(
                "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors hover:bg-muted",
                item.disabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
              )}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

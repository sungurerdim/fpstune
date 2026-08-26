import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle } from "lucide-react";

/**
 * The parts of a confirmation that a `position: fixed` div does not supply.
 *
 * Both of this app's confirmations gate something the user cannot take back — a
 * bulk apply of advanced tweaks, a Docker and WSL shutdown — and both shipped as
 * a bare overlay: no role, no focus trap, no Escape. The page behind stayed in
 * the tab order and in the accessibility tree, so the question could be tabbed
 * past instead of answered, which is the one thing a confirmation must not
 * allow.
 *
 * Rendered into `document.body` rather than in place, because marking
 * everything outside the dialog `inert` is only possible while the dialog is
 * not itself inside the subtree being marked.
 */

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

export interface ConfirmDialogProps {
  open: boolean;
  /** Names the dialog. Rendered as its heading and pointed at by `aria-labelledby`. */
  title: string;
  /** The explanation, pointed at by `aria-describedby`. */
  children: ReactNode;
  /** The affirmative button's words. Cancel is always "Cancel". */
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;

    const trigger = document.activeElement as HTMLElement | null;

    // The first control is Cancel, and that is deliberate: an Enter pressed
    // before the question has been read must not be the answer to it.
    panel.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus();

    // `inert` is the browser's own trap. The Tab handler below repeats the job
    // because jsdom and older engines parse the attribute without honouring it.
    // An element that already carries either attribute is left alone — its
    // state belongs to whoever set it.
    const silenced = Array.from(document.body.children).filter(
      (element) =>
        !element.contains(panel) &&
        !element.hasAttribute("inert") &&
        !element.hasAttribute("aria-hidden"),
    );
    for (const element of silenced) {
      element.setAttribute("inert", "");
      element.setAttribute("aria-hidden", "true");
    }

    return () => {
      for (const element of silenced) {
        element.removeAttribute("inert");
        element.removeAttribute("aria-hidden");
      }
      trigger?.focus();
    };
  }, [open]);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      // Stopped here so a dialog opened from inside another Escape-aware
      // surface closes one layer per press.
      event.stopPropagation();
      onCancel();
      return;
    }
    if (event.key !== "Tab") return;

    const focusable = Array.from(
      panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? [],
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const leavingAtEdge = event.shiftKey
      ? document.activeElement === first
      : document.activeElement === last;
    if (!leavingAtEdge) return;
    event.preventDefault();
    (event.shiftKey ? last : first).focus();
  };

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onKeyDown={handleKeyDown}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="bg-card border border-border rounded-lg p-5 max-w-sm mx-4 space-y-3"
      >
        <div className="flex items-center gap-2 text-amber-400">
          <AlertTriangle className="w-5 h-5 shrink-0" aria-hidden="true" />
          <h2 id={titleId} className="font-semibold text-sm">
            {title}
          </h2>
        </div>
        <p id={descriptionId} className="text-xs text-muted-foreground">
          {children}
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 text-xs rounded border border-border hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-3 py-1.5 text-xs rounded bg-amber-500 text-black font-medium hover:bg-amber-400 transition-colors"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

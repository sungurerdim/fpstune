import { useT } from "../../i18n";
import type { MessageKey } from "../../i18n/en";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import type { KeyboardEvent } from "react";
import { useStore, type Notification } from "../../store";
import { cn } from "../../lib/utils";

/**
 * The screen for the store's `notifications` array.
 *
 * The array had producers and no reader: "cannot reach the backend" and every
 * failed cleanup operation were pushed, capped and never rendered, so the two
 * conditions the app decided a user must be told about were the two it told
 * nobody. Both are actionable — start the backend, retry the prune — which is
 * why they are notifications rather than log lines.
 *
 * Nothing here auto-dismisses. A message that names a failure the user has to
 * act on must not expire while they are reading it, and there is no timing
 * fallback that makes a vanished error recoverable.
 */

/** Which live region a message belongs in, and how it is drawn. */
const TYPE_CONFIG: Record<
  Notification["type"],
  {
    /** Read to a screen reader in place of the icon's colour and shape. */
    labelKey: MessageKey;
    urgent: boolean;
    icon: typeof Info;
    accent: string;
  }
> = {
  error: {
    labelKey: "toast.error",
    urgent: true,
    icon: XCircle,
    accent: "border-l-destructive text-destructive",
  },
  warning: {
    labelKey: "toast.warning",
    urgent: true,
    icon: AlertTriangle,
    accent: "border-l-warning text-warning",
  },
  success: {
    labelKey: "toast.success",
    urgent: false,
    icon: CheckCircle2,
    accent: "border-l-success text-success",
  },
  info: {
    labelKey: "toast.info",
    urgent: false,
    icon: Info,
    accent: "border-l-primary text-primary",
  },
};

function Toast({
  notification,
  onDismiss,
}: {
  notification: Notification;
  onDismiss: (id: string) => void;
}) {
  const { t } = useT();
  const config = TYPE_CONFIG[notification.type];
  const Icon = config.icon;

  // Escape dismisses whichever toast the keyboard is currently inside. Reaching
  // the button and pressing it works too; this is the shortcut for a user who
  // arrived here by tabbing and does not want to read the rest of the stack.
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    onDismiss(notification.id);
  };

  return (
    <div
      onKeyDown={handleKeyDown}
      className={cn(
        "pointer-events-auto flex items-start gap-2 rounded-lg border border-border border-l-4 bg-card px-3 py-2 shadow-lg",
        config.accent,
      )}
    >
      <Icon className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
      <p className="text-xs text-foreground flex-1 wrap-break-word">
        {/* Severity travels as a word as well as a colour: the icon is
            decorative and the accent is invisible to a screen reader. */}
        <span className="sr-only">{t(config.labelKey)}: </span>
        {notification.message}
      </p>
      <button
        type="button"
        onClick={() => onDismiss(notification.id)}
        aria-label={`Dismiss: ${notification.message}`}
        className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
      >
        <X className="w-3.5 h-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}

export function NotificationToasts() {
  const { t } = useT();
  const notifications = useStore((state) => state.notifications);
  const removeNotification = useStore((state) => state.removeNotification);

  const urgent = notifications.filter((n) => TYPE_CONFIG[n.type].urgent);
  const routine = notifications.filter((n) => !TYPE_CONFIG[n.type].urgent);

  return (
    // Both regions are mounted for the whole session, empty or not: a live
    // region created in the same tick as its first child is announced
    // unreliably, which for the backend-unreachable message means not at all.
    // Neither ever takes focus — the user keeps whatever they were doing and
    // reaches a toast by tabbing to it.
    <div className="pointer-events-none fixed top-4 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
      {/* `log` rather than `alert` or `status`: both of those are atomic, so a
          second failure re-reads every message already on screen. A log is
          append-only, which is what a stack of them actually is. */}
      <div
        role="log"
        aria-live="assertive"
        aria-label={t("toast.errorsRegion")}
        className="flex flex-col gap-2"
      >
        {urgent.map((notification) => (
          <Toast
            key={notification.id}
            notification={notification}
            onDismiss={removeNotification}
          />
        ))}
      </div>
      <div
        role="log"
        aria-live="polite"
        aria-label={t("toast.region")}
        className="flex flex-col gap-2"
      >
        {routine.map((notification) => (
          <Toast
            key={notification.id}
            notification={notification}
            onDismiss={removeNotification}
          />
        ))}
      </div>
    </div>
  );
}

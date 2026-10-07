import { Wrench, type LucideIcon } from "lucide-react";
import { useT } from "../../i18n";

/**
 * One device on one line: icon · name · key spec · "N not optimized".
 *
 * Purely presentational. The name and the spec truncate (the full text is in the
 * title attribute) so a long model string never wraps the row; the count is the
 * only part that never shrinks, and says what it is in words with its own icon,
 * never colour alone. A device with nothing to optimize shows no count at all.
 */
export function DeviceHeader({
  icon: Icon,
  name,
  spec,
  notOptimized,
  reading = false,
}: {
  icon: LucideIcon;
  name: string;
  spec?: string;
  /** Rows the backend reports as not optimized; 0 hides the count. */
  notOptimized: number;
  /** Tweaks for this device are still being read. */
  reading?: boolean;
}) {
  const { t } = useT();
  return (
    <span className="flex min-w-0 items-center gap-2 text-sm">
      <Icon className="h-4 w-4 shrink-0 text-primary/80" aria-hidden />
      <span className="truncate font-medium text-foreground" title={name}>
        {name}
      </span>
      {spec && (
        <span className="truncate text-xs text-muted-foreground" title={spec}>
          {spec}
        </span>
      )}
      <span className="ml-auto flex shrink-0 items-center gap-1 whitespace-nowrap text-xs">
        {reading ? (
          <span className="text-muted-foreground">{t("devices.reading")}</span>
        ) : (
          notOptimized > 0 && (
            <span className="flex items-center gap-1 text-warning">
              <Wrench className="h-3 w-3" aria-hidden />
              {t("device.notOptimized", { count: notOptimized })}
            </span>
          )
        )}
      </span>
    </span>
  );
}

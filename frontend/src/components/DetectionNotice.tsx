import { useMemo, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight, EyeOff } from "lucide-react";
import { useT } from "../i18n";
import { localizedName } from "../i18n/settings";
import { useStore } from "../store";
import type { Setting } from "../types/setting";

/**
 * "Could not read" must never look like "not present".
 *
 * Every list surface filters `isApplicable === false` rows out before
 * rendering, which is right for settings that genuinely do not exist on this
 * machine — but detection *failures* used to vanish through the same filter,
 * so a machine where half the detection failed looked identical to one that
 * was already optimal. This notice sits above the filter: failures render as a
 * warning with each setting's own error, and the genuinely-absent rows are
 * countable behind a quiet disclosure with the reason detection recorded.
 */
export function DetectionNotice({
  owns,
}: {
  /** Which settings this surface owns; the notice reports only those. */
  owns?: (setting: Setting) => boolean;
}) {
  const { t } = useT();
  const settingsMap = useStore((state) => state.settings);
  const settingsVersion = useStore((state) => state._settingsVersion);
  const [failuresOpen, setFailuresOpen] = useState(false);
  const [absentOpen, setAbsentOpen] = useState(false);

  const { failures, absent } = useMemo(() => {
    const failed: Setting[] = [];
    const notPresent: Setting[] = [];
    for (const setting of settingsMap.values()) {
      if (owns && !owns(setting)) continue;
      if (setting.detectionError) {
        failed.push(setting);
      } else if (!setting.isApplicable) {
        notPresent.push(setting);
      }
    }
    return { failures: failed, absent: notPresent };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- settingsVersion busts cache
  }, [settingsMap, settingsVersion, owns]);

  if (failures.length === 0 && absent.length === 0) return null;

  return (
    <div className="space-y-1">
      {failures.length > 0 && (
        <div className="rounded border border-warning/40 bg-warning/10 px-3 py-2">
          <button
            onClick={() => setFailuresOpen((open) => !open)}
            className="flex w-full items-center gap-1.5 text-left text-xs font-medium text-warning"
            aria-expanded={failuresOpen}
          >
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
            {failures.length === 1
              ? t("detection.failedOne")
              : t("detection.failedMany", { count: failures.length })}
            {failuresOpen ? (
              <ChevronDown className="ml-auto h-3 w-3" />
            ) : (
              <ChevronRight className="ml-auto h-3 w-3" />
            )}
          </button>
          {failuresOpen && (
            <ul className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">
              {failures.map((setting) => (
                <li key={setting.id}>
                  <span className="text-foreground">{localizedName(setting)}</span>
                  {" — "}
                  {setting.detectionError}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {absent.length > 0 && (
        <div className="px-3 py-1">
          <button
            onClick={() => setAbsentOpen((open) => !open)}
            className="flex w-full items-center gap-1.5 text-left text-xs text-muted-foreground"
            aria-expanded={absentOpen}
          >
            <EyeOff className="h-3 w-3 flex-shrink-0" />
            {absent.length === 1
              ? t("detection.absentOne")
              : t("detection.absentMany", { count: absent.length })}
            {absentOpen ? (
              <ChevronDown className="ml-auto h-3 w-3" />
            ) : (
              <ChevronRight className="ml-auto h-3 w-3" />
            )}
          </button>
          {absentOpen && (
            <ul className="mt-1.5 space-y-0.5 text-xs text-muted-foreground">
              {absent.map((setting) => (
                <li key={setting.id}>
                  <span className="text-foreground/80">{localizedName(setting)}</span>
                  {" — "}
                  {setting.applicableReason || t("detection.absentFallback")}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

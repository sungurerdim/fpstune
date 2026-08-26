import type { MonitorInfo } from "./api";

/**
 * Whether a display is running below what it can do, and we trust the reading.
 *
 * Lives here rather than beside the components so the per-display button and the
 * all-displays action share one definition. Two copies of this predicate would
 * eventually disagree, and then one control would offer a fix the other says is
 * unnecessary — the UI version of a detect that observes less than its apply
 * writes.
 *
 * "Unknown" is not "suboptimal": a disconnected output or a mode that could not be
 * read must not produce an offer to fix it, because acting on those values would
 * apply numbers that mean nothing.
 */
export function isDisplaySuboptimal(monitor: MonitorInfo): boolean {
  if (!(monitor.is_active ?? true)) return false;

  const refreshOff =
    (monitor.is_refresh_known ?? false) &&
    !monitor.is_refresh_optimal &&
    !!(monitor.native_refresh_rate_hz || monitor.max_refresh_rate_hz);

  const resolutionOff =
    (monitor.is_resolution_known ?? false) &&
    !monitor.is_resolution_optimal &&
    !!(monitor.native_width && monitor.native_height);

  return refreshOff || resolutionOff;
}

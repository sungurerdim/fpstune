import { useCleanupSizePolling } from "../hooks/useCleanupRunner";

/**
 * Always-rendered, headless host for the cleanup size polling + freed-space
 * resolution side-effects. Mounted once in App so a cleanup started on any tab
 * keeps resolving its freed space even after the user navigates elsewhere.
 */
export function CleanupRunnerProvider() {
  useCleanupSizePolling();
  return null;
}

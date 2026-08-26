import { useMutation } from "@tanstack/react-query";
import { ScreenShare, CheckCircle2, RefreshCw, Zap } from "lucide-react";
import { useState } from "react";
import { api, type MonitorInfo } from "../../lib/api";
import { hardwareManager } from "../../lib/hardware-manager";
import { createLogger } from "../../lib/logger";
import { cn } from "../../lib/utils";
import { isDisplaySuboptimal } from "../../lib/displayStatus";
import { ConfirmDialog } from "../ui/ConfirmDialog";

const log = createLogger("MonitorCard");

/**
 * Format monitor device name for display (removes \\.\\ prefix)
 */
function formatMonitorDeviceName(name: string): string {
  // Remove \\.\\ prefix from Windows device path
  return name.replace(/^\\\\\.\\/g, "").replace(/^\\\\\.\\/, "");
}

/**
 * Monitor/Display card with resolution and refresh rate controls
 * Layout: Monitor info (left) | G-Sync optimization (right)
 */
/**
 * One action for every display that is below native, for multi-monitor setups
 * where fixing them one card at a time is busywork.
 *
 * Applied sequentially rather than concurrently: each call is a real mode change,
 * and overlapping mode changes across displays is how a driver ends up with a
 * layout nobody asked for.
 */
export function DisplaysAutoAllButton({ monitors }: { monitors: MonitorInfo[] }) {
  const targets = monitors
    .map((monitor, index) => ({ monitor, index }))
    .filter(({ monitor }) => isDisplaySuboptimal(monitor));

  // Every real mode write starts a backend revert timer: unless the change is
  // kept, the prior mode comes back — so an unreadable panel can never be
  // stranded in a mode nobody can see to undo.
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [revertS, setRevertS] = useState(15);

  const mutation = useMutation({
    mutationFn: async () => {
      let revert: number | null = null;
      for (const { index } of targets) {
        const res = await api.setDisplayToAuto(index);
        if (res.requires_confirmation) revert = res.revert_timeout_s ?? 15;
      }
      return revert;
    },
    onSuccess: async (revert) => {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      await hardwareManager.refreshMonitors();
      if (revert !== null) {
        setRevertS(revert);
        setConfirmOpen(true);
      }
    },
    onError: (error: Error) => {
      log.error("Failed to set all displays to native mode:", error.message);
      alert(`Could not change every display: ${error.message}`);
    },
  });

  const keepAll = async () => {
    setConfirmOpen(false);
    for (const { index } of targets) {
      try {
        await api.confirmDisplayChange(index);
      } catch (error) {
        // A 404 means that display's timer already fired and it reverted.
        log.error(`Could not keep display ${index}:`, (error as Error).message);
      }
    }
  };

  const letRevert = () => {
    setConfirmOpen(false);
    setTimeout(
      () => {
        void hardwareManager.refreshMonitors();
      },
      (revertS + 2) * 1000,
    );
  };

  // Pointless when there is one display — its own card already carries the button.
  if (targets.length < 2) return null;

  return (
    <>
      <button
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
        className={cn(
          "flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium transition-colors",
          mutation.isPending
            ? "bg-muted text-muted-foreground cursor-wait"
            : "bg-warning/15 text-warning hover:bg-warning/25",
        )}
      >
        {mutation.isPending ? (
          <RefreshCw className="w-3 h-3 animate-spin" />
        ) : (
          <Zap className="w-3 h-3" />
        )}
        {mutation.isPending
          ? "Applying…"
          : `Use native mode on all ${targets.length} displays`}
      </button>
      <ConfirmDialog
        open={confirmOpen}
        title="Keep these display modes?"
        confirmLabel="Keep"
        onConfirm={() => void keepAll()}
        onCancel={letRevert}
      >
        Every changed display goes back to its previous mode in {revertS} seconds
        unless you keep it — so a mode your screen cannot show fixes itself.
      </ConfirmDialog>
    </>
  );
}

export function MonitorCard({
  monitor,
  displayIndex,
}: {
  monitor: MonitorInfo;
  displayIndex: number;
}) {
  // Handle disconnected displays (width/height might be 0)
  const isActive = monitor.is_active ?? true;
  const currentRes =
    monitor.width > 0 && monitor.height > 0
      ? `${monitor.width}x${monitor.height}`
      : `${monitor.native_width || 0}x${monitor.native_height || 0}`;
  const currentHz = monitor.refresh_rate_hz || 0;

  // Use API-provided detection status (no fallbacks - trust only detected values)
  const isResolutionKnown = monitor.is_resolution_known ?? false;
  const isRefreshKnown = monitor.is_refresh_known ?? false;

  // Native values - only use if detection succeeded
  const nativeRes =
    isResolutionKnown && monitor.native_width && monitor.native_height
      ? `${monitor.native_width}x${monitor.native_height}`
      : null;
  // The panel's ceiling: mode-list max first, EDID preferred rate as fallback —
  // a high-refresh panel's EDID often prefers 60 Hz while its modes reach 300.
  const nativeHz = isRefreshKnown
    ? monitor.max_refresh_rate_hz || monitor.native_refresh_rate_hz || 0
    : null;

  // Optimal status - only trust if detection succeeded (disconnected displays can't be optimal)
  const isResOptimal =
    isActive && isResolutionKnown && monitor.is_resolution_optimal;
  const isRefreshOptimal =
    isActive && isRefreshKnown && monitor.is_refresh_optimal;

  // Applying the fix this card has always only *described*.
  //
  // The panel detected a monitor running below its native mode and rendered
  // "120Hz -> 300Hz" in amber, but nothing anywhere could act on it: the registry
  // comment said display settings were "handled in Hardware panel", this file's
  // comment said they were "managed in Software Tweaks tab", and
  // `_discover_display_settings()` was commented out. Meanwhile
  // POST /display/{index}/auto and `api.setDisplayToAuto` both existed and had no
  // caller. Telling the user something is wrong with no way to fix it is worse
  // than staying quiet.
  // The backend reverts the change unless it is kept (A10's second guard), so
  // a mode this panel cannot show fixes itself even if the user sees nothing.
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [revertS, setRevertS] = useState(15);

  const autoMutation = useMutation({
    mutationFn: () => api.setDisplayToAuto(displayIndex),
    onSuccess: async (data) => {
      // Windows needs a moment to settle a mode change before it reports the new
      // values, and the monitor cache has to be invalidated or the card would
      // keep showing the old rate and look like the click did nothing.
      await new Promise((resolve) => setTimeout(resolve, 1200));
      await hardwareManager.refreshMonitors();
      if (data.requires_confirmation) {
        setRevertS(data.revert_timeout_s ?? 15);
        setConfirmOpen(true);
      }
    },
    onError: (error: Error) => {
      log.error(`Failed to set display ${displayIndex} to native mode:`, error.message);
      alert(`Could not change the display mode: ${error.message}`);
    },
  });

  const keepMode = async () => {
    setConfirmOpen(false);
    try {
      await api.confirmDisplayChange(displayIndex);
    } catch (error) {
      // A 404 means the timer already fired and the display reverted.
      log.error(`Could not keep display ${displayIndex}:`, (error as Error).message);
      void hardwareManager.refreshMonitors();
    }
  };

  const letModeRevert = () => {
    setConfirmOpen(false);
    setTimeout(
      () => {
        void hardwareManager.refreshMonitors();
      },
      (revertS + 2) * 1000,
    );
  };

  // Same predicate the all-displays action uses, so the two controls cannot
  // disagree about whether this display needs anything.
  const canOptimize = isDisplaySuboptimal(monitor);

  // Determine border color based on status
  const getBorderColor = () => {
    if (!isActive) return "border-muted-foreground/20"; // Disconnected
    if (!isResolutionKnown && !isRefreshKnown)
      return "border-muted-foreground/30"; // Unknown
    if (isResOptimal && isRefreshOptimal) return "border-primary/30"; // Optimal
    return "border-warning/50"; // Suboptimal
  };

  return (
    <div
      className={cn(
        "pl-3 border-l-2 py-1.5 space-y-1",
        getBorderColor(),
        !isActive && "opacity-60",
      )}
    >
      {/* Header: icon + name + badges */}
      <div className="flex items-center gap-1.5">
        <ScreenShare
          className={cn(
            "w-3 h-3 flex-shrink-0",
            isActive ? "text-muted-foreground" : "text-muted-foreground/50",
          )}
        />
        <span
          className={cn(
            "text-xs font-medium truncate",
            !isActive && "text-muted-foreground",
          )}
        >
          {monitor.friendly_name ||
            formatMonitorDeviceName(monitor.name) ||
            `Display ${displayIndex + 1}`}
        </span>
        {!isActive && (
          <span className="text-xs px-1 py-0.5 rounded bg-muted text-muted-foreground font-medium flex-shrink-0">
            Disconnected
          </span>
        )}
        {monitor.is_primary && (
          <span className="text-xs px-1 py-0.5 rounded bg-primary/20 text-primary font-medium flex-shrink-0">
            Primary
          </span>
        )}
        {monitor.supports_vrr && (
          <span className="text-xs px-1 py-0.5 rounded bg-success/20 text-success font-medium flex-shrink-0">
            VRR
          </span>
        )}
      </div>

      {/* Device name and hardware ID (secondary) */}
      {(monitor.friendly_name || monitor.hardware_id) && (
        <div className="text-xs text-muted-foreground truncate pl-4">
          {formatMonitorDeviceName(monitor.name)}
          {monitor.hardware_id && (
            <span className="ml-1 text-muted-foreground/60">
              ({monitor.hardware_id})
            </span>
          )}
        </div>
      )}

      {/* Resolution row */}
      <div className="flex items-center gap-1 text-xs pl-4">
        <span className="text-muted-foreground w-14">Resolution:</span>
        <span
          className={cn(
            "font-medium",
            !isResolutionKnown
              ? "text-muted-foreground"
              : isResOptimal
                ? "text-success"
                : "text-warning",
          )}
        >
          {currentRes}
        </span>
        {isResolutionKnown ? (
          isResOptimal ? (
            <CheckCircle2 className="w-3 h-3 text-success" />
          ) : (
            nativeRes && (
              <>
                <span className="text-muted-foreground">→</span>
                <span className="text-success font-medium">{nativeRes}</span>
              </>
            )
          )
        ) : (
          <span className="text-xs text-muted-foreground italic">(?)</span>
        )}
      </div>

      {/* Refresh rate row */}
      <div className="flex items-center gap-1 text-xs pl-4">
        <span className="text-muted-foreground w-14">Refresh:</span>
        <span
          className={cn(
            "font-medium",
            !isRefreshKnown
              ? "text-muted-foreground"
              : isRefreshOptimal
                ? "text-success"
                : "text-warning",
          )}
        >
          {currentHz}Hz
        </span>
        {isRefreshKnown ? (
          isRefreshOptimal ? (
            <CheckCircle2 className="w-3 h-3 text-success" />
          ) : (
            nativeHz !== null && (
              <>
                <span className="text-muted-foreground">→</span>
                <span className="text-success font-medium">{nativeHz}Hz</span>
              </>
            )
          )
        ) : (
          <span className="text-xs text-muted-foreground italic">(?)</span>
        )}
      </div>

      {canOptimize && (
        <div className="pl-4 pt-0.5">
          <button
            onClick={() => autoMutation.mutate()}
            disabled={autoMutation.isPending}
            className={cn(
              "flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium transition-colors",
              autoMutation.isPending
                ? "bg-muted text-muted-foreground cursor-wait"
                : "bg-warning/15 text-warning hover:bg-warning/25",
            )}
          >
            {autoMutation.isPending ? (
              <RefreshCw className="w-3 h-3 animate-spin" />
            ) : (
              <Zap className="w-3 h-3" />
            )}
            {autoMutation.isPending ? "Applying…" : "Use native mode"}
          </button>
        </div>
      )}
      <ConfirmDialog
        open={confirmOpen}
        title="Keep this display mode?"
        confirmLabel="Keep"
        onConfirm={() => void keepMode()}
        onCancel={letModeRevert}
      >
        This display goes back to its previous mode in {revertS} seconds unless
        you keep it — so a mode your screen cannot show fixes itself.
      </ConfirmDialog>
    </div>
  );
}


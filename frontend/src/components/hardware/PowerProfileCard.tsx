import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BatteryCharging, CheckCircle2, RefreshCw, Zap } from "lucide-react";
import { api } from "../../lib/api";
import { createLogger } from "../../lib/logger";
import { cn } from "../../lib/utils";
import { HardwareSection } from "./shared";

const log = createLogger("PowerProfileCard");

/**
 * The FPS Balanced power plan: full power when a game wants it, zero waste
 * when it does not (heat is a performance category — consequence 4).
 *
 * The three routes this calls existed before any surface did; the old comment
 * here said the profile was "managed in Software Tweaks tab", which managed
 * nothing (D3). Activate creates the plan if missing; revert goes back to
 * Windows' own Balanced plan.
 */
export function PowerProfileCard() {
  const queryClient = useQueryClient();
  const { data: status } = useQuery({
    queryKey: ["power-profile"],
    queryFn: api.getPowerProfileStatus,
    staleTime: 30_000,
    retry: false,
  });

  const refetch = () =>
    queryClient.invalidateQueries({ queryKey: ["power-profile"] });

  const activateMutation = useMutation({
    mutationFn: api.activatePowerProfile,
    onSuccess: refetch,
    onError: (error: Error) => {
      log.error("Failed to activate FPS Balanced plan:", error.message);
      alert(`Could not activate the power plan: ${error.message}`);
    },
  });

  const revertMutation = useMutation({
    mutationFn: api.revertPowerProfile,
    onSuccess: refetch,
    onError: (error: Error) => {
      log.error("Failed to revert power plan:", error.message);
      alert(`Could not revert the power plan: ${error.message}`);
    },
  });

  if (!status) return null;

  const pending = activateMutation.isPending || revertMutation.isPending;

  return (
    <>
      <HardwareSection
        icon={<BatteryCharging className="w-4 h-4" />}
        title="Power plan"
      >
        <div className="pl-3 border-l-2 border-primary/30 space-y-1">
          <p className="text-sm font-medium flex items-center gap-1.5">
            {status.active_plan}
            {status.fps_balanced_active && (
              <CheckCircle2 className="w-3.5 h-3.5 text-success" />
            )}
          </p>
          <p className="text-xs text-muted-foreground">
            {status.fps_balanced_active
              ? "FPS Balanced is active — full power when a game asks, idle cores allowed to clock down."
              : "FPS Balanced gives full power under load and lets idle cores clock down — less heat for the same frames."}
          </p>
          <div className="flex items-center gap-2 pt-0.5">
            {status.fps_balanced_active ? (
              <button
                onClick={() => revertMutation.mutate()}
                disabled={pending}
                className="px-2 py-1 rounded text-xs font-medium border border-border text-muted-foreground hover:bg-muted transition-colors disabled:cursor-wait"
              >
                {revertMutation.isPending
                  ? "Reverting…"
                  : "Revert to Windows Balanced"}
              </button>
            ) : (
              <button
                onClick={() => activateMutation.mutate()}
                disabled={pending}
                className={cn(
                  "flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium transition-colors",
                  pending
                    ? "bg-muted text-muted-foreground cursor-wait"
                    : "bg-warning/15 text-warning hover:bg-warning/25",
                )}
              >
                {activateMutation.isPending ? (
                  <RefreshCw className="w-3 h-3 animate-spin" />
                ) : (
                  <Zap className="w-3 h-3" />
                )}
                Activate FPS Balanced
              </button>
            )}
          </div>
        </div>
      </HardwareSection>
      <div className="border-t border-border/50 my-2" />
    </>
  );
}

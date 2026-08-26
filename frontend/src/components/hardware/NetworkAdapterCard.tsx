import { useT } from "../../i18n";
import { useMutation } from "@tanstack/react-query";
import {
  Wifi, Signal, Network, RefreshCw, Unplug, Plug,
} from "lucide-react";
import { useId } from "react";
import {
  api, type NetworkAdapterInfo, } from "../../lib/api";
import { hardwareManager } from "../../lib/hardware-manager";
import { createLogger } from "../../lib/logger";
import { cn } from "../../lib/utils";
import { ToggleSwitch } from "../ui/ToggleSwitch";
import { CopyableText } from "./shared";
import { DeviceTweakList } from "./DeviceTweakList";

const log = createLogger("hardware");

/**
 * Network adapter card with full details
 */
export function NetworkAdapterCard({ adapter }: { adapter: NetworkAdapterInfo }) {
  const { t } = useT();
  const isWiFi = adapter.adapter_type === "WiFi";
  // Phantom device = physically not connected (can't be enabled/disabled)
  const isPhantom = adapter.status === "NotConnected";
  // Check if we have a valid identifier for enable/disable operations
  const hasValidId = !!(
    adapter.instance_id ||
    (adapter.interface_index !== null && adapter.interface_index !== undefined)
  );
  const canToggle = !isPhantom && hasValidId;
  const lacksIdentifier = !isPhantom && !hasValidId;

  // Ids for the badges that say why the switch is inert, so the switch can
  // point at them. Every card on the page renders the same two badges, so the
  // ids have to be per-instance or `aria-describedby` would resolve to the
  // first card's text on every card. `aria-describedby` is a list, and the two
  // reasons are only mutually exclusive because the phantom badge already
  // answers the question — a join keeps the switch correct if that changes.
  const cardId = useId();
  const phantomReasonId = `${cardId}-phantom`;
  const identifierReasonId = `${cardId}-uncontrollable`;
  const reasonIds = [
    isPhantom && phantomReasonId,
    lacksIdentifier && identifierReasonId,
  ]
    .filter((id): id is string => typeof id === "string")
    .join(" ");

  // Toggle adapter enabled/disabled mutation
  const toggleMutation = useMutation({
    mutationFn: async () => {
      if (isPhantom) {
        throw new Error("Device is not physically connected");
      }
      const action = adapter.is_enabled ? "disable" : "enable";
      // Prefer instance_id (works for all adapters including disabled)
      // Fall back to interface_index for active adapters without instance_id
      const params = new URLSearchParams();
      if (adapter.instance_id) {
        params.set("instance_id", adapter.instance_id);
      } else if (
        adapter.interface_index !== null &&
        adapter.interface_index !== undefined
      ) {
        params.set("interface_index", String(adapter.interface_index));
      } else {
        throw new Error("No valid identifier available for this adapter");
      }
      const response = await fetch(`/api/network/adapter/${action}?${params}`, {
        method: "POST",
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Failed to toggle adapter");
      }
      return response.json();
    },
    onSuccess: async () => {
      // Wait for Windows to update adapter status before refreshing
      // Network adapter state changes can take 500-1000ms to propagate
      await new Promise((resolve) => setTimeout(resolve, 800));
      // Granular refresh: only network adapters (~500ms vs 8s full refresh)
      await hardwareManager.refreshNetworkAdapters();
    },
    onError: (error: Error) => {
      log.error(`Failed to toggle adapter "${adapter.name}":`, error.message);
      alert(`Failed to toggle adapter: ${error.message}`);
    },
  });

  // Toggle connection (connect/disconnect without disabling hardware)
  const connectionMutation = useMutation({
    mutationFn: async () => {
      const action = adapter.is_connected ? "disconnect" : "connect";
      return api.toggleNetworkConnection(adapter.name, action);
    },
    onSuccess: () => {
      // Granular refresh: only network adapters (~500ms vs 8s full refresh)
      hardwareManager.refreshNetworkAdapters();
    },
    onError: (error: Error) => {
      log.error(
        `Failed to toggle connection for "${adapter.name}":`,
        error.message,
      );
      alert(
        `Failed to ${adapter.is_connected ? "disconnect" : "connect"}: ${error.message}`,
      );
    },
  });

  // Format speed display
  const speedDisplay = adapter.speed_mbps
    ? adapter.speed_mbps >= 1000
      ? `${(adapter.speed_mbps / 1000).toFixed(1)} Gbps`
      : `${adapter.speed_mbps} Mbps`
    : null;

  return (
    <div
      className={cn(
        "pl-3 border-l-2 space-y-1 py-1",
        adapter.is_enabled && adapter.is_connected
          ? "border-primary/30"
          : "border-border",
        (!adapter.is_enabled || !canToggle) && "opacity-60",
      )}
    >
      {/* Header row: toggle (left) + icon + name + status badges */}
      <div className="flex items-center gap-1.5">
        {/* Enable/Disable toggle - LEFT SIDE (disabled for phantom/no-id devices).
            Named after the adapter, not the action or the reason it is inert:
            aria-checked carries on/off, and a name that changed with the state
            made the same control read as a new one after every toggle. */}
        <ToggleSwitch
          enabled={adapter.is_enabled && canToggle}
          onToggle={() => canToggle && toggleMutation.mutate()}
          isPending={toggleMutation.isPending}
          size="sm"
          title={adapter.name}
          disabled={!canToggle}
          describedBy={reasonIds || undefined}
        />

        {isWiFi ? (
          <Wifi className="w-3 h-3 text-primary flex-shrink-0" />
        ) : (
          <Network className="w-3 h-3 text-muted-foreground flex-shrink-0" />
        )}
        <CopyableText
          value={adapter.name}
          className="text-xs font-medium flex-1 truncate"
        />

        {/* Connect/Disconnect button - only when adapter is enabled and controllable */}
        {adapter.is_enabled && canToggle && (
          <button
            onClick={() => connectionMutation.mutate()}
            disabled={connectionMutation.isPending}
            className={cn(
              "p-1 rounded transition-colors flex-shrink-0",
              adapter.is_connected
                ? "text-warning hover:bg-warning/10"
                : "text-success hover:bg-success/10",
              connectionMutation.isPending && "opacity-50 cursor-not-allowed",
            )}
            aria-label={adapter.is_connected ? t("adapter.disconnect") : t("adapter.connect")}
            title={
              adapter.is_connected
                ? t("adapter.disconnectTitle")
                : t("adapter.connectTitle")
            }
          >
            {connectionMutation.isPending ? (
              <RefreshCw className="w-3 h-3 animate-spin" />
            ) : adapter.is_connected ? (
              <>
                <Unplug className="w-3 h-3" />
                <span className="text-xs ml-0.5">{t("adapter.off")}</span>
              </>
            ) : (
              <>
                <Plug className="w-3 h-3" />
                <span className="text-xs ml-0.5">{t("adapter.on")}</span>
              </>
            )}
          </button>
        )}

        {/* Status badge. It doubles as the switch's description when the
            adapter is phantom — "Not Connected" is the reason the switch is
            inert, and the switch has to carry it rather than leave a reader to
            find it after the control it explains. */}
        <span
          id={isPhantom ? phantomReasonId : undefined}
          className={cn(
            "text-xs px-1 py-0.5 rounded flex-shrink-0",
            isPhantom
              ? "bg-destructive/20 text-destructive"
              : adapter.is_connected
                ? "bg-primary/20 text-primary"
                : "bg-muted text-muted-foreground",
          )}
        >
          {isPhantom
            ? t("adapter.notConnected")
            : adapter.is_connected
              ? t("adapter.connected")
              : t("adapter.disconnected")}
        </span>

        {/* Why the switch is inert, in the same badge shape as "Not Connected".
            A phantom adapter's badge already says it; this is the other case —
            Windows returned neither an instance id nor an interface index, so
            there is nothing to address an enable/disable call to. It has to be
            text rather than the switch's title, which now carries the adapter's
            name and cannot say two things at once. */}
        {lacksIdentifier && (
          <span
            id={identifierReasonId}
            className="text-xs px-1 py-0.5 rounded flex-shrink-0 bg-warning/20 text-warning"
          >
            Not controllable
          </span>
        )}
      </div>

      {/* WiFi: Connected network info (first line for WiFi) */}
      {isWiFi && adapter.ssid && (
        <div className="flex items-center gap-1.5 text-xs flex-wrap">
          <Wifi className="w-3 h-3 text-primary" />
          <span className="font-medium text-foreground">{adapter.ssid}</span>
          {adapter.radio_type && (
            <span className="bg-primary/20 text-primary px-1 rounded text-xs">
              {adapter.radio_type}
            </span>
          )}
          {adapter.channel && (
            <span className="text-muted-foreground">CH {adapter.channel}</span>
          )}
          {adapter.frequency_ghz && adapter.frequency_ghz > 0 && (
            <span className="text-muted-foreground">
              ({adapter.frequency_ghz} GHz)
            </span>
          )}
          {adapter.signal_percent !== undefined &&
            adapter.signal_percent > 0 && (
              <span
                className={cn(
                  "flex items-center gap-0.5",
                  adapter.signal_percent >= 70
                    ? "text-success"
                    : adapter.signal_percent >= 40
                      ? "text-warning"
                      : "text-destructive",
                )}
              >
                <Signal className="w-3 h-3" />
                {adapter.signal_percent}%
              </span>
            )}
          {adapter.auth_type && (
            <span className="bg-muted px-1 rounded text-xs">
              {adapter.auth_type}
            </span>
          )}
        </div>
      )}

      {/* IP Address + Speed */}
      {adapter.ipv4_address && (
        <div className="text-xs flex items-center gap-2">
          <span className="text-muted-foreground">IP:</span>
          <CopyableText
            value={adapter.ipv4_address}
            className="text-foreground"
          />
          {speedDisplay && (
            <span className="text-muted-foreground">• {speedDisplay}</span>
          )}
        </div>
      )}

      {/* Gateway */}
      {adapter.gateway && (
        <div className="text-xs flex items-center gap-2">
          <span className="text-muted-foreground">GW:</span>
          <span className="font-mono text-muted-foreground">
            {adapter.gateway}
          </span>
        </div>
      )}

      {/* DNS Servers */}
      {adapter.dns_servers && adapter.dns_servers.length > 0 && (
        <div className="text-xs flex items-center gap-2">
          <span className="text-muted-foreground">DNS:</span>
          <span className="font-mono text-muted-foreground">
            {adapter.dns_servers.slice(0, 2).join(", ")}
            {adapter.dns_servers.length > 2 &&
              ` +${adapter.dns_servers.length - 2}`}
          </span>
        </div>
      )}

      {/* MAC Address */}
      {adapter.mac_address && (
        <div className="text-xs flex items-center gap-2">
          <span className="text-muted-foreground">MAC:</span>
          <CopyableText
            value={adapter.mac_address}
            className="text-muted-foreground text-xs"
          />
        </div>
      )}

      {/* This adapter's own tweaks, next to the adapter they belong to.
          Matching on the interface index is what makes them this adapter's: the
          registry names per-adapter settings `network:<ifindex>:<name>`, and the
          index is the identifier fpstune stores precisely because adapter names are
          localised. An adapter with no index (disabled, so never enumerated) has no
          per-adapter settings to show. */}
      {adapter.interface_index != null && (
        <DeviceTweakList
          match={(setting) =>
            setting.id.startsWith(`network:${adapter.interface_index}:`)
          }
        />
      )}
    </div>
  );
}


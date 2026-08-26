import { useMutation } from "@tanstack/react-query";
import {
  Volume2, Mic, } from "lucide-react";
import {
  api, type AudioDeviceInfo,
} from "../../lib/api";
import { hardwareManager } from "../../lib/hardware-manager";
import { createLogger } from "../../lib/logger";
import { cn } from "../../lib/utils";
import { ToggleSwitch } from "../ui/ToggleSwitch";
import { HardwareSection, NotDetected } from "./shared";
import { DeviceTweakList } from "./DeviceTweakList";

const log = createLogger("hardware");

/**
 * Audio section with output/input grouping
 */
export function AudioSection({
  devices,
  loading,
}: {
  devices: AudioDeviceInfo[] | undefined;
  loading: boolean;
}) {
  // Filter output devices: Playback type AND not a virtual microphone loopback
  // Some virtual audio software (SteelSeries Sonar, Voicemeeter) creates playback endpoints
  // with "Microphone" in the name - these are loopback devices, not real outputs
  const isMicrophoneDevice = (name: string) => /microphone|mic\b/i.test(name);

  const outputDevices =
    devices?.filter(
      (d) => d.device_type === "Playback" && !isMicrophoneDevice(d.name),
    ) ?? [];

  // Input devices: Recording type OR playback devices that are actually microphone loopbacks
  const inputDevices =
    devices?.filter(
      (d) =>
        d.device_type === "Recording" ||
        (d.device_type === "Playback" && isMicrophoneDevice(d.name)),
    ) ?? [];

  return (
    <div className="space-y-3">
      {/* Output Devices */}
      <HardwareSection
        icon={<Volume2 className="w-3 h-3" />}
        title="Audio Output"
        count={outputDevices.length}
        loading={loading}
      >
        {outputDevices.length > 0 ? (
          <div className="space-y-2">
            {outputDevices.map((device, i) => (
              <AudioDeviceCard key={`out-${device.id}-${i}`} device={device} />
            ))}
            {/* Enhancements, exclusive mode and communications ducking are
                system-wide audio policy rather than one endpoint's setting, so they
                belong to the section instead of a device card. */}
            <DeviceTweakList match={(setting) => setting.module === "audio"} />
          </div>
        ) : !loading ? (
          <NotDetected />
        ) : null}
      </HardwareSection>

      {/* Separator between output and input */}
      {(outputDevices.length > 0 || inputDevices.length > 0) && (
        <div className="border-t border-border/50 my-2" />
      )}

      {/* Input Devices */}
      <HardwareSection
        icon={<Mic className="w-3 h-3" />}
        title="Audio Input"
        count={inputDevices.length}
        loading={loading}
      >
        {inputDevices.length > 0 ? (
          <div className="space-y-2">
            {inputDevices.map((device, i) => (
              <AudioDeviceCard key={`in-${device.id}-${i}`} device={device} />
            ))}
          </div>
        ) : !loading ? (
          <NotDetected />
        ) : null}
      </HardwareSection>
    </div>
  );
}

/**
 * Audio device card with enable/disable toggle and volume normalization
 */
function AudioDeviceCard({ device }: { device: AudioDeviceInfo }) {
  // Toggle device enabled state
  const toggleEnabledMutation = useMutation({
    mutationFn: async () => {
      return api.setAudioDeviceEnabled(device.id, !device.is_enabled);
    },
    onSuccess: () => {
      // Granular refresh: only audio devices (~300ms vs 8s full refresh)
      hardwareManager.refreshAudioDevices();
    },
    onError: (error: Error) => {
      log.error(
        `Failed to toggle audio device "${device.name}":`,
        error.message,
      );
      alert(`Failed to toggle device: ${error.message}`);
    },
  });

  // Toggle loudness EQ mutation
  const toggleLeqMutation = useMutation({
    mutationFn: async () => {
      return api.setLoudnessEq(device.id, !device.loudness_eq_enabled);
    },
    onSuccess: () => {
      // Granular refresh: only audio devices (~300ms vs 8s full refresh)
      hardwareManager.refreshAudioDevices();
    },
    onError: (error: Error) => {
      log.error(
        `Failed to toggle loudness EQ for "${device.name}":`,
        error.message,
      );
      alert(`Failed to toggle volume normalization: ${error.message}`);
    },
  });

  const isToggling = toggleEnabledMutation.isPending;
  const showVolNorm =
    device.device_type === "Playback" && device.loudness_eq_supported;

  return (
    <div
      className={cn(
        "pl-3 border-l-2 py-1.5",
        device.is_default
          ? "border-primary bg-primary/5"
          : device.is_enabled
            ? "border-primary/30"
            : "border-border opacity-60",
      )}
    >
      {/* Main row: Enable/Disable toggle + Device name + Active badge */}
      <div className="flex items-center gap-1.5">
        {/* Enable/Disable toggle. Named after the device, not the action: the
            on/off half travels in aria-checked, and a name that flipped with the
            state made the control read as a different one after every toggle. */}
        <ToggleSwitch
          enabled={device.is_enabled}
          onToggle={() => toggleEnabledMutation.mutate()}
          isPending={isToggling}
          size="sm"
          title={device.name}
        />

        <span
          className={cn(
            "text-xs font-medium flex-1 truncate",
            !device.is_enabled && "text-muted-foreground",
          )}
        >
          {device.name}
        </span>

        {device.is_default && (
          <span className="text-xs px-1 py-0.5 rounded bg-primary/20 text-primary font-medium">
            Default
          </span>
        )}
      </div>

      {/* Volume Normalization - separate row for playback devices that support it */}
      {showVolNorm && device.is_enabled && (
        <div className="flex items-center gap-1.5 mt-1.5 ml-7 pl-2 border-l border-border/50">
          <Volume2 className="w-3 h-3 text-muted-foreground" />
          <span className="text-xs text-muted-foreground">Loudness EQ</span>
          <div className="ml-auto">
            <ToggleSwitch
              enabled={device.loudness_eq_enabled}
              onToggle={() => toggleLeqMutation.mutate()}
              isPending={toggleLeqMutation.isPending}
              size="xs"
              title="Loudness EQ"
            />
          </div>
        </div>
      )}

      {/* Show "Not supported" hint for playback devices without loudness EQ */}
      {device.device_type === "Playback" &&
        !device.loudness_eq_supported &&
        device.is_enabled && (
          <div className="flex items-center gap-1.5 mt-1 ml-7 text-xs text-muted-foreground/60">
            <Volume2 className="w-3 h-3" />
            <span>Loudness EQ not supported by this device</span>
          </div>
        )}
    </div>
  );
}


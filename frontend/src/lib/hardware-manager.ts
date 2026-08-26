/**
 * HardwareManager - Singleton for centralized hardware detection.
 *
 * Features:
 * - Single source of truth for hardware data
 * - Promise-based deduplication: concurrent requests share the same promise
 * - Automatic polling for GPU detection (when detecting=true)
 *
 * Usage:
 *   const hardware = await hardwareManager.getHardware()
 *   hardwareManager.startPolling() // For GPU detection progress
 *   hardwareManager.stopPolling()
 */

import { api, HardwareInfo, MonitorInfo } from "./api";
import { createLogger } from "./logger";

const log = createLogger("HardwareManager");

type HardwareListener = (hardware: HardwareInfo | null) => void;

class HardwareManager {
  private static instance: HardwareManager;

  // Current hardware data
  private hardware: HardwareInfo | null = null;

  // Promise for in-flight request (deduplication)
  private fetchPromise: Promise<HardwareInfo> | null = null;

  // Polling state
  private pollingInterval: ReturnType<typeof setInterval> | null = null;
  private pollingActive = false;

  // Listeners for reactive updates
  private listeners: Set<HardwareListener> = new Set();

  private constructor() {}

  static getInstance(): HardwareManager {
    if (!HardwareManager.instance) {
      HardwareManager.instance = new HardwareManager();
    }
    return HardwareManager.instance;
  }

  /**
   * Get hardware data with deduplication.
   * If a fetch is already in progress, returns the same promise.
   */
  async getHardware(forceRefresh = false): Promise<HardwareInfo> {
    // Return cached data if not forcing refresh and we have data
    if (!forceRefresh && this.hardware && !this.hardware.detecting) {
      return this.hardware;
    }

    // If fetch is in progress, wait for it
    if (this.fetchPromise) {
      return this.fetchPromise;
    }

    // Start new fetch
    this.fetchPromise = this.fetchHardware();

    try {
      const result = await this.fetchPromise;
      return result;
    } finally {
      this.fetchPromise = null;
    }
  }

  /**
   * Force refresh hardware data.
   */
  async refresh(): Promise<HardwareInfo> {
    return this.getHardware(true);
  }

  /**
   * Refresh only monitor data (fast, ~200ms vs 8s for full refresh).
   * Updates monitors in cached hardware and notifies listeners.
   */
  async refreshMonitors(): Promise<MonitorInfo[]> {
    try {
      log.info("Refreshing monitors only...");
      const response = await api.refreshDisplays();

      if (response.success && this.hardware) {
        // Update only monitors in cached hardware
        this.hardware = {
          ...this.hardware,
          monitors: response.monitors,
        };
        this.notifyListeners();
        log.info("Monitors refreshed:", response.monitors.length);
      }

      return response.monitors;
    } catch (error) {
      log.error("Monitor refresh failed:", error);
      throw error;
    }
  }

  /**
   * Refresh only network adapter data (fast, ~500ms vs 8s for full refresh).
   * Updates network_adapters in cached hardware and notifies listeners.
   */
  async refreshNetworkAdapters(): Promise<void> {
    try {
      log.info("Refreshing network adapters only...");
      const response = await api.refreshNetworkAdapters();

      // An empty list with success=true is indistinguishable at this layer from a
      // detection that timed out, and overwriting good data with nothing makes the
      // panel report "Not detected" for hardware that is plainly present. Keeping
      // the previous reading is the safe answer: stale beats absent, and the next
      // refresh corrects it.
      if (response.success && this.hardware) {
        if (response.network_adapters.length === 0) {
          log.warn("Network refresh returned no adapters; keeping previous data");
          return;
        }
        this.hardware = {
          ...this.hardware,
          network_adapters: response.network_adapters,
        };
        this.notifyListeners();
        log.info(
          "Network adapters refreshed:",
          response.network_adapters.length,
        );
      }
    } catch (error) {
      log.error("Network adapter refresh failed:", error);
      throw error;
    }
  }

  /**
   * Refresh only audio device data (fast, ~300ms vs 8s for full refresh).
   * Updates audio_devices in cached hardware and notifies listeners.
   */
  async refreshAudioDevices(): Promise<void> {
    try {
      log.info("Refreshing audio devices only...");
      const response = await api.refreshAudioDevices();

      // Same rule as the network refresh: an empty list is not evidence that the
      // devices went away, so it must not erase what we already read.
      if (response.success && this.hardware) {
        if (response.audio_devices.length === 0) {
          log.warn("Audio refresh returned no devices; keeping previous data");
          return;
        }
        this.hardware = {
          ...this.hardware,
          audio_devices: response.audio_devices,
        };
        this.notifyListeners();
        log.info("Audio devices refreshed:", response.audio_devices.length);
      }
    } catch (error) {
      log.error("Audio device refresh failed:", error);
      throw error;
    }
  }

  /**
   * Get current cached hardware data without fetching.
   */
  getCached(): HardwareInfo | null {
    return this.hardware;
  }

  /**
   * Start polling for hardware updates (used during GPU detection).
   */
  startPolling(intervalMs = 1000): void {
    if (this.pollingActive) return;

    this.pollingActive = true;
    log.info("Starting polling...");

    this.pollingInterval = setInterval(async () => {
      try {
        await this.getHardware(true);

        // Stop polling if detection is complete
        if (this.hardware && !this.hardware.detecting) {
          log.info("Detection complete, stopping polling");
          this.stopPolling();
        }
      } catch (error) {
        log.error("Polling error:", error);
      }
    }, intervalMs);
  }

  /**
   * Stop polling for hardware updates.
   */
  stopPolling(): void {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
    }
    this.pollingActive = false;
  }

  /**
   * Subscribe to hardware updates.
   */
  subscribe(listener: HardwareListener): () => void {
    this.listeners.add(listener);
    // Immediately call with current data
    listener(this.hardware);
    // Return unsubscribe function
    return () => this.listeners.delete(listener);
  }

  /**
   * Check if hardware is currently being detected.
   */
  isDetecting(): boolean {
    return this.hardware?.detecting ?? false;
  }

  /**
   * Check if data is available.
   */
  hasData(): boolean {
    return this.hardware !== null;
  }

  private async fetchHardware(): Promise<HardwareInfo> {
    try {
      log.info("Fetching hardware...");
      const data = await api.getHardware();
      this.hardware = data;

      // Notify listeners
      this.notifyListeners();

      // Auto-start polling if still detecting
      if (data.detecting && !this.pollingActive) {
        this.startPolling();
      }

      log.info("Hardware fetched:", {
        cpu: data.cpu?.name,
        gpus: data.gpus?.length ?? 0,
        monitors: data.monitors?.length ?? 0,
        network: data.network_adapters?.length ?? 0,
        storage: data.storage_drives?.length ?? 0,
        audio: data.audio_devices?.length ?? 0,
        detecting: data.detecting,
      });

      // Log any hardware detection issues for debugging
      this.logHardwareIssues(data);

      return data;
    } catch (error) {
      log.error("Fetch failed:", error);
      throw error;
    }
  }

  private notifyListeners(): void {
    for (const listener of this.listeners) {
      try {
        listener(this.hardware);
      } catch (error) {
        log.error("Listener error:", error);
      }
    }
  }

  /**
   * Log warnings/errors for hardware items with unknown or incomplete values.
   * Helps debug detection issues in the browser console.
   */
  private logHardwareIssues(data: HardwareInfo): void {
    const issues: string[] = [];
    const warnings: string[] = [];

    // Check monitors for unknown values
    if (data.monitors) {
      for (const monitor of data.monitors) {
        // Check resolution detection
        if (
          monitor.is_resolution_known === false ||
          (monitor.native_width === 0 && monitor.native_height === 0)
        ) {
          warnings.push(`Monitor "${monitor.name}": native resolution unknown`);
        }
        // Check refresh rate detection
        if (
          monitor.is_refresh_known === false ||
          monitor.max_refresh_rate_hz === 0 ||
          monitor.max_refresh_rate_hz === undefined
        ) {
          warnings.push(`Monitor "${monitor.name}": max refresh rate unknown`);
        }
        // Check current values
        if (monitor.width === 0 || monitor.height === 0) {
          issues.push(`Monitor "${monitor.name}": current resolution is 0x0`);
        }
        if (!monitor.refresh_rate_hz || monitor.refresh_rate_hz === 0) {
          issues.push(
            `Monitor "${monitor.name}": current refresh rate is 0 Hz`,
          );
        }
      }
    }

    // Check GPUs
    if (data.gpus) {
      for (const gpu of data.gpus) {
        if (!gpu.name) {
          warnings.push(`GPU (${gpu.vendor}): name unknown`);
        }
        if (!gpu.driver) {
          warnings.push(`GPU "${gpu.name || gpu.vendor}": driver unknown`);
        }
        if (!gpu.vram_mb) {
          warnings.push(`GPU "${gpu.name || gpu.vendor}": VRAM unknown`);
        }
      }
    }

    // Check CPU
    if (!data.cpu) {
      issues.push("CPU: not detected");
    } else if (!data.cpu.name) {
      warnings.push("CPU: name unknown");
    }

    // Check storage drives
    if (data.storage_drives) {
      for (const drive of data.storage_drives) {
        if (!drive.model || drive.model === "Unknown") {
          warnings.push(`Drive ${drive.drive_letter}: model unknown`);
        }
        if (!drive.media_type || drive.media_type === "Unknown") {
          warnings.push(
            `Drive ${drive.drive_letter}: media type unknown (SSD/HDD)`,
          );
        }
      }
    }

    // Log issues as errors, warnings as warnings
    if (issues.length > 0) {
      log.error("Hardware detection errors:", issues);
    }
    if (warnings.length > 0) {
      log.warn("Hardware with unknown values:", warnings);
    }
  }
}

export const hardwareManager = HardwareManager.getInstance();

/**
 * React hook for hardware data with automatic updates.
 */
export function useHardwareManager(): HardwareManager {
  return hardwareManager;
}

// Re-export for convenience
export type { HardwareInfo } from "./api";

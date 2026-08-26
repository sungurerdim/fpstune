import { createLogger } from "./logger";
import type {
  CategoryMetadataResponse,
  ModuleMetadataResponse,
  SettingDefinition,
} from "../types/setting";

const API_BASE = "/api";
const log = createLogger("API");

export interface NetworkAdapterInfo {
  name: string;
  description: string;
  adapter_type: string;
  status: string;
  is_enabled: boolean; // Admin status: whether adapter is enabled
  is_connected: boolean; // Media status: whether cable/signal connected
  mac_address?: string;
  speed_mbps?: number;
  ipv4_address?: string;
  ipv6_address?: string;
  gateway?: string;
  dns_servers: string[];
  // System identifiers (for API operations - use these instead of name)
  interface_index?: number | null; // NetAdapter InterfaceIndex (for active adapters)
  instance_id?: string | null; // PnpDevice InstanceId (for all adapters, including disabled)
  // WiFi-specific fields
  ssid?: string;
  channel?: number;
  frequency_ghz?: number;
  radio_type?: string; // 802.11ac, 802.11ax (WiFi 6), etc.
  signal_percent?: number;
  auth_type?: string;
}

export interface StorageDriveInfo {
  drive_letter: string;
  model: string;
  media_type: string;
  size_gb: number;
  free_gb?: number;
  trim_enabled: boolean;
  bus_type?: string; // NVMe, SATA, etc.
}

export interface AudioDeviceInfo {
  id: string; // Device GUID from registry
  name: string; // Friendly name: "Speakers (Realtek)", "SteelSeries Engine"
  device_type: string; // Playback, Recording
  is_default: boolean;
  is_enabled: boolean;
  driver?: string;
  loudness_eq_supported: boolean; // Whether device supports volume normalization
  loudness_eq_enabled: boolean; // Current state of volume normalization
}

export interface VrrOptimizationInfo {
  monitor_name: string;
  monitor_refresh_hz: number;
  // Tri-state on purpose: null means the EDID could not be read, and "could
  // not read" must never render as "does not support".
  supports_vrr: boolean | null;
  recommended_fps_limit: number;
  recommended_vrr_mode: string;
  recommended_vsync: string;
  current_fps_limit: number;
  current_vrr_mode: string;
  current_vsync: string;
  is_optimized: boolean;
  explanation: string;
  warning?: string | null;
}

export interface PowerProfileStatus {
  active_plan: string;
  active_guid: string;
  fps_balanced_exists: boolean;
  fps_balanced_active: boolean;
  optimizations: string[];
}

export interface SelfCheckFinding {
  area: string;
  name: string;
  agrees: boolean;
  detail: string;
}

export interface SelfCheckReport {
  ok: boolean;
  findings: SelfCheckFinding[];
}

export interface GpuDeviceInfo {
  vendor: string;
  name?: string;
  driver?: string;
  vram_mb?: number;
}

export interface CpuInfo {
  name: string;
  physical_cores: number;
  logical_cores: number;
  // The rated clock WMI reports; no boost field exists (nothing measures one)
  base_clock_mhz?: number;
  sockets?: number;
  // P/E topology; is_hybrid null = could not be read (unknown, not "no")
  p_cores?: number;
  e_cores?: number;
  is_hybrid?: boolean | null;
  architecture: string;
  cache_l3_mb?: number;
}

export interface MonitorInfo {
  name: string;
  width: number;
  height: number;
  refresh_rate_hz?: number;
  is_primary: boolean;
  // Monitor brand/model from EDID (e.g., "ASUS VG27AQ1A", "Dell U2722D")
  friendly_name?: string;
  // Native values from EDID preferred timing (optimal settings)
  native_width?: number;
  native_height?: number;
  native_refresh_rate_hz?: number; // From EDID DTD calculation
  // Maximum values from EnumDisplaySettings (may include OC modes)
  max_refresh_rate_hz?: number;
  // Detection status - false means we couldn't detect (don't assume optimal)
  is_resolution_known?: boolean;
  is_refresh_known?: boolean;
  // Optimal status (only trust if corresponding _known is true)
  is_resolution_optimal?: boolean;
  is_refresh_optimal?: boolean;
  // VRR (G-Sync/FreeSync) support — the EDID's declaration; null = unknown
  supports_vrr?: boolean | null;
  // Is display active (attached to desktop) or disconnected via Windows settings
  is_active?: boolean;
  // Hardware ID for matching (e.g., "DEL4265", "SAM0F75")
  hardware_id?: string;
}

export interface HardwareInfo {
  cpu?: CpuInfo;
  gpus: GpuDeviceInfo[];
  monitors: MonitorInfo[];
  network_adapters: NetworkAdapterInfo[];
  storage_drives: StorageDriveInfo[];
  audio_devices: AudioDeviceInfo[];
  detecting: boolean;
}

export interface SystemInfo {
  os_platform: string;
  os_version: string;
  os_build: string;
  os_edition: string;
  os_display_version?: string; // e.g., "24H2", "23H2"
  is_supported: boolean;
  is_admin: boolean;
  cpu_name: string;
  cpu_cores: number;
  ram_total_mb: number;
  ram_available_mb: number;
  gpu_vendor: string;
  gpu_name?: string;
  gpu_driver?: string;
  gpu_vram_mb?: number;
  gpu_detecting?: boolean;
}

export interface ActivityLogEntry {
  timestamp: string;
  message: string;
  level: string;
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const fullUrl = `${API_BASE}${url}`;
  const method = options?.method || "GET";

  log.info(`${method} ${fullUrl}`);

  try {
    const response = await fetch(fullUrl, {
      headers: {
        "Content-Type": "application/json",
      },
      ...options,
    });

    if (!response.ok) {
      const errorText = await response.text();
      log.error(`${response.status} ${response.statusText}`, errorText);
      throw new Error(
        `API error: ${response.status} ${response.statusText} - ${errorText}`,
      );
    }

    const data = await response.json();

    // Log success with appropriate color based on response content
    if (data?.success === false || data?.error_count > 0) {
      log.warn(`${response.status} (with errors)`, data);
    } else {
      log.success(`${response.status} OK`, data);
    }

    return data;
  } catch (error) {
    log.error("Request failed:", error);
    throw error;
  }
}

/**
 * POST a JSON body and read the SSE stream that comes back.
 *
 * Server-Sent Events over POST, so `EventSource` cannot be used: it only ever
 * issues a GET. Returns the cancel function every caller needs, because a stream
 * abandoned by a navigation keeps the backend running the work it describes.
 *
 * `label` names the stream in the log, so a parse failure says which one broke.
 */
function postEventStream(
  path: string,
  body: unknown,
  label: string,
  onEvent: (event: Record<string, unknown>) => void,
  onDone?: () => void,
): () => void {
  const controller = new AbortController();
  (async () => {
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      if (!res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        // A read can split an event in half, so the trailing fragment is held
        // back until the next chunk completes it.
        const chunks = buf.split("\n\n");
        buf = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const dataLine = chunk
            .split("\n")
            .find((l) => l.startsWith("data: "));
          if (dataLine) {
            try {
              onEvent(JSON.parse(dataLine.slice(6)));
            } catch (err) {
              log.error(`${label} stream parse error`, err);
            }
          }
        }
      }
      onDone?.();
    } catch (err) {
      if ((err as Error).name !== "AbortError") log.error(`${label} error`, err);
    }
  })();
  return () => controller.abort();
}

export const api = {
  getSystemInfo: () => fetchJson<SystemInfo>("/system"),

  getHardware: () => fetchJson<HardwareInfo>("/hardware"),

  getActivityLog: (limit = 50) =>
    fetchJson<{ entries: ActivityLogEntry[] }>(`/activity?limit=${limit}`),

  // Audio device loudness equalization toggle
  setLoudnessEq: (deviceId: string, enabled: boolean) =>
    fetchJson<{
      success: boolean;
      device_id: string;
      enabled: boolean;
      message: string;
    }>(
      `/audio/device/${encodeURIComponent(deviceId)}/loudness-eq?enabled=${enabled}`,
      {
      method: "POST",
    }),

  // Audio device enable/disable toggle
  setAudioDeviceEnabled: (deviceId: string, enabled: boolean) =>
    fetchJson<{
      success: boolean;
      device_id: string;
      enabled: boolean;
      message: string;
    }>(
      `/audio/device/${encodeURIComponent(deviceId)}/enabled?enabled=${enabled}`,
      {
      method: "POST",
    }),

  // Display/Monitor settings
  setDisplayToAuto: (displayIndex: number) =>
    fetchJson<{
      success: boolean;
      display_index: number;
      resolution: string;
      refresh_rate: number;
      message: string;
      // A real write awaits confirmation: unless confirmDisplayChange arrives
      // within revert_timeout_s the backend restores the prior mode.
      requires_confirmation: boolean;
      revert_timeout_s: number | null;
    }>(`/display/${displayIndex}/auto`, { method: "POST" }),

  createRestorePoint: () =>
    fetchJson<{ success: boolean; message: string }>("/restore-point", {
      method: "POST",
    }),

  // G-Sync/VRR driver tuning (NVIDIA today; other vendors report the gap).
  getVrrOptimization: (displayIndex: number) =>
    fetchJson<VrrOptimizationInfo>(
      `/display/vrr-optimization?display_index=${displayIndex}`,
    ),

  applyVrrOptimization: (request: {
    fps_limit: number;
    vrr_mode: string;
    vsync: string;
  }) =>
    fetchJson<{ success: boolean; message: string }>(
      "/display/vrr-optimization/apply",
      { method: "POST", body: JSON.stringify(request) },
    ),

  resetVrrOptimization: () =>
    fetchJson<{ success: boolean; message: string }>(
      "/display/vrr-optimization/reset",
      { method: "POST" },
    ),

  // FPS Balanced power plan: full power when a game wants it, none wasted idle.
  getPowerProfileStatus: () =>
    fetchJson<PowerProfileStatus>("/power-profile/status"),

  activatePowerProfile: () =>
    fetchJson<{ success: boolean; message: string }>("/power-profile/activate", {
      method: "POST",
    }),

  revertPowerProfile: () =>
    fetchJson<{ success: boolean; message: string }>("/power-profile/revert", {
      method: "POST",
    }),

  // Every detector cross-checked against an independent source (A12).
  getSelfCheck: (refresh = false) =>
    fetchJson<SelfCheckReport>(`/self-check${refresh ? "?refresh=true" : ""}`),

  // The drive's own media type picks the pass: retrim on SSD, defrag on HDD.
  optimizeDrive: (driveLetter: string) =>
    fetchJson<{
      success: boolean;
      drive_letter: string;
      media_type: string;
      action: string;
      message: string;
    }>(`/storage/${encodeURIComponent(driveLetter)}/optimize`, {
      method: "POST",
    }),

  confirmDisplayChange: (displayIndex: number) =>
    fetchJson<{ success: boolean; message: string }>(
      `/display/${displayIndex}/confirm`,
      { method: "POST" },
    ),

  refreshDisplays: () =>
    fetchJson<{ success: boolean; monitors: MonitorInfo[] }>(
      "/display/refresh",
      { method: "POST" },
    ),

  // Granular refresh endpoints (fast, ~300-500ms each)
  refreshNetworkAdapters: () =>
    fetchJson<{ success: boolean; network_adapters: NetworkAdapterInfo[] }>(
      "/network/refresh",
      { method: "POST" },
    ),

  refreshAudioDevices: () =>
    fetchJson<{ success: boolean; audio_devices: AudioDeviceInfo[] }>(
      "/audio/refresh",
      { method: "POST" },
    ),

  // Network adapter connection toggle (connect/disconnect without disabling hardware)
  toggleNetworkConnection: (
    adapterName: string,
    action: "connect" | "disconnect",
  ) =>
    fetchJson<{
      success: boolean;
      adapter_name: string;
      adapter_type: string;
      is_connected: boolean;
      profile: string | null;
      message: string;
    }>(
      `/network/adapter/${encodeURIComponent(adapterName)}/connection/${action}`,
      { method: "POST" },
    ),
};

// =============================================================================
// Settings API Types (new SettingExecutor architecture)
// =============================================================================
// The definition and metadata response shapes live in `types/setting.ts`
// (imported above): a second copy here drifted to nine fields behind the
// backend before it was noticed, and the store was already importing the
// canonical one.

export interface DetectionResultResponse {
  setting_id: string;
  value: unknown | null;
  error: string | null;
  time_ms: number;
  success: boolean;
  is_optimized: boolean;
  is_applicable: boolean;
  applicable_reason: string;
  recommended_value?: unknown;
  /**
   * What this machine held when fpstune first saw the setting, or null/absent
   * when nothing was recorded. Null means there is nothing to undo, which is a
   * different state from "the original equals the current value" — offer the
   * undo action only when this is present and differs from `value`.
   */
  original_value?: unknown;
}

export interface DetectRequest {
  setting_ids?: string[];
  category?: string;
}

export interface DetectResponse {
  results: Record<string, DetectionResultResponse>;
  total_time_ms: number;
  success_count: number;
  error_count: number;
}

export interface ApplyResponse {
  setting_id: string;
  success: boolean;
  error: string | null;
  new_value: unknown | null;
  requires_reboot: boolean;
  skipped?: boolean; // True if setting was not applicable (not counted as error)
  // Verification outcome, kept distinct from `success` so a skipped check is
  // never read as a passed one (mirrors schemas.ApplyResponse):
  //   true  — value was read back and matched the request
  //   false — value was read back and did not match (success is false too)
  //   null  — no check was possible (action, advisory/read-only, or not run)
  verified: boolean | null;
}

export interface BulkApplyResponse {
  results: Record<string, ApplyResponse>;
  success_count: number;
  error_count: number;
  requires_reboot: boolean;
}

export interface VerifyResponse {
  setting_id: string;
  matches: boolean;
  current_value: unknown;
  expected_value: unknown;
  // Which question was answered — echoed so a caller that assumed a different
  // target cannot read a correct machine as a failed operation.
  target: "recommended" | "default" | "original";
  error?: string | null;
}

// =============================================================================
// Settings API Methods (new SettingExecutor architecture)
// =============================================================================

export const settingsApi = {
  /**
   * Get all setting definitions (instant, no detection)
   * Use this for initial store population
   */
  getDefinitions: () =>
    fetchJson<SettingDefinition[]>("/settings/definitions"),

  /**
   * Detect multiple settings in parallel (single request, no polling)
   * Pass setting_ids for specific settings, category for all in category, or empty for all
   */
  detect: (request: DetectRequest = {}) =>
    fetchJson<DetectResponse>("/settings/detect", {
      method: "POST",
      body: JSON.stringify(request),
    }),

  /**
   * Apply a single setting value
   */
  applySetting: (settingId: string, value: unknown) =>
    fetchJson<ApplyResponse>(`/settings/${settingId}/apply`, {
      method: "POST",
      body: JSON.stringify({ value }),
    }),

  /**
   * Put a setting back to what this machine held when fpstune first saw it.
   *
   * Fails with 409 when nothing was recorded, rather than falling back to the
   * stock value: quietly doing a reset under the name "undo" is the conflation
   * this exists to end. Callers should offer it only when a detection result
   * carries an original_value.
   */
  undoSetting: (settingId: string) =>
    fetchJson<ApplyResponse>(`/settings/${settingId}/undo`, {
      method: "POST",
    }),

  /**
   * Write the curated Windows-stock value (C6's other promise).
   *
   * A different endpoint from undo on purpose: reset writes what stock
   * Windows holds, undo writes what this machine held. The row used to fake
   * this by posting `/apply` with `defaultValue` — same write, but the
   * backend never knew it was a reset, so the activity log called it an
   * apply and the dedicated route sat uncalled.
   */
  resetSetting: (settingId: string) =>
    fetchJson<ApplyResponse>(`/settings/${settingId}/reset`, {
      method: "POST",
    }),

  /**
   * Detect only — which question is being asked is named by `target`
   * and echoed back in the response.
   */
  verifySetting: (settingId: string) =>
    fetchJson<VerifyResponse>(`/settings/${settingId}/verify`, {
      method: "POST",
    }),

  /**
   * Apply multiple settings at once
   */
  bulkApply: (settings: Record<string, unknown>) =>
    fetchJson<BulkApplyResponse>("/settings/bulk/apply", {
      method: "POST",
      body: JSON.stringify({ settings }),
    }),

  /**
   * Sequential SSE bulk apply — streams per-setting events as each completes.
   * Returns a cancel function; call it to abort mid-stream.
   */
  bulkStreamApply: (
    ids: string[],
    onEvent: (event: Record<string, unknown>) => void,
    onDone?: () => void,
  ): (() => void) =>
    postEventStream(
      "/settings/bulk/stream-apply",
      { ids },
      "bulkStreamApply",
      onEvent,
      onDone,
    ),

  /**
   * Sequential SSE bulk reset — streams per-setting events as each completes.
   * Returns a cancel function; call it to abort mid-stream.
   */
  bulkStreamReset: (
    ids: string[],
    onEvent: (event: Record<string, unknown>) => void,
    onDone?: () => void,
  ): (() => void) =>
    postEventStream(
      "/settings/bulk/stream-reset",
      { ids },
      "bulkStreamReset",
      onEvent,
      onDone,
    ),

  /**
   * Get full category metadata for UI rendering (SSOT)
   */
  getCategoriesMetadata: () =>
    fetchJson<CategoryMetadataResponse[]>("/settings/categories/metadata"),

  /**
   * Get module metadata for UI rendering (SSOT)
   * Replaces hardcoded MODULE_DISPLAY_NAMES and MODULE_DESCRIPTIONS in frontend
   */
  getModulesMetadata: () =>
    fetchJson<ModuleMetadataResponse[]>("/settings/modules/metadata"),

  /**
   * Get background-computed cleanup sizes.
   * Poll while any entry has status="calculating" (every 3s).
   */
  getCleanupSizes: () =>
    fetchJson<
      Record<
        string,
        {
          bytes: number;
          status: "ready" | "calculating" | "unavailable" | "not_installed";
        }
      >
    >("/settings/cleanup-sizes"),
};

// ---------------------------------------------------------------------------
// The evidence engine
// ---------------------------------------------------------------------------
// Types mirror what `benchmark/sources.py` and `benchmark/verify_round.py`
// return, and nothing here reproduces their judgement. In particular the
// instrument-field -> claim-metric mapping is fetched rather than written down
// again: a second copy in TypeScript drifts from the first the moment an
// instrument gains a field, and the failure it produces is a verdict comparing
// two different quantities, which reads exactly like a real one.

export interface VerifySource {
  name: string;
  requires: string;
  metrics: string[];
  units: Record<string, string>;
  runnable: boolean;
}

export interface VerifySources {
  sources: VerifySource[];
  no_instrument: Record<string, string>;
}

export interface MeasurableClaim {
  setting_id: string;
  metric: string;
  claimed: string;
  source: string;
  requires: string;
}

export interface UnmeasurableClaim {
  setting_id: string;
  metric: string;
  claimed: string;
  reason: string;
  /**
   * Whether a measurement could settle this at all.
   *
   * False for claims about privacy, audibility, or what a player can tell
   * apart — real claims that no instrument adjudicates and none ever will.
   * Listing them beside the genuine gaps turns a third of the registry into a
   * to-do list nothing can take them off.
   */
  judgeable: boolean;
}

export interface VerifyCoverage {
  summary: string;
  total_claims: number;
  measurable: MeasurableClaim[];
  unmeasurable: UnmeasurableClaim[];
  measurable_count: number;
  /** Claims a measurement could settle and this build does not. The real to-do. */
  gap_count: number;
  /** Claims no measurement settles. Not a shortfall, and not a to-do. */
  not_judgeable_count: number;
  required_conditions: string[];
}

export interface VerifySample {
  instrument: string;
  requires: string;
  metrics: Record<string, number>;
}

export type VerifyStatus =
  | "verified"
  | "contradicted"
  | "inconclusive"
  | "unmeasured"
  | "not_attributable";

export interface Verdict {
  setting_id: string;
  metric: string;
  claimed: string;
  status: VerifyStatus;
  reason: string;
  measured: {
    before: number;
    after: number;
    delta: number;
    percent_change: number;
    unit: string;
    noise: number;
  } | null;
}

/**
 * What one round concluded. Returned, never filed.
 *
 * There was a `report_html` here, and a list endpoint beside it, because every
 * round wrote a JSON and an HTML file. Ninety of them had accumulated, each
 * describing a machine state that no longer existed. A verdict about the
 * machine as it is now has exactly one current answer, so this is the answer
 * and there is no shelf.
 */
export interface VerifyReport {
  settings_changed: number;
  summary: string;
  verified: number;
  contradicted: number;
  unverified: number;
  verdicts: Verdict[];
  notes: string[];
}

/** One bench, and whether it can run on this machine. */
export interface SuiteBench {
  key: string;
  label: string;
  requires: string;
  /** What running it spends, beyond time. Empty when it spends only time. */
  costs: string;
  available: boolean;
  /** Why it cannot run. Empty when it can. */
  reason: string;
  /** Whether "run everything" includes it — false for anything that costs. */
  in_default_run: boolean;
}

export interface SuiteCatalogue {
  benches: SuiteBench[];
  default_keys: string[];
  min_repeats: number;
  default_repeats: number;
  max_repeats: number;
}

export interface SuiteReading {
  metric: string;
  samples: number[];
  median: number;
  /** Null when there is only one sample, so the spread is unknown. */
  noise: number | null;
  unit: string;
  improves_upward: boolean | null;
}

export interface SuiteResult {
  bench: string;
  label: string;
  ran: boolean;
  reason: string;
  readings: Record<string, SuiteReading>;
  detail: Record<string, unknown>;
  duration_seconds: number;
}

/**
 * One set of measurements under one label.
 *
 * Held in the browser rather than on disk. A comparison needs a "before" taken
 * minutes ago, and the server-side version of that is how the old verify round
 * accumulated ninety files describing machines that no longer existed.
 */
export interface SuiteRun {
  label: string;
  started_at: number;
  summary: string;
  results: SuiteResult[];
}

export interface SuiteMeasurement {
  metric: string;
  before: number;
  after: number;
  delta: number;
  percent_change: number;
  unit: string;
  noise: number | null;
  /** False means the change is inside the machine's own variation. */
  exceeds_noise: boolean;
  /**
   * Which kind of gain this is — fps, latency, thermal, network, resources,
   * storage — decided by the same map the settings use, server-side.
   *
   * Null for metrics the benches named for themselves and no setting claims,
   * like `pacing_p999_ms`. Shown on its own rather than filed under a category
   * it does not belong to.
   */
  category: string | null;
}

export interface SuiteComparison {
  before_label: string;
  after_label: string;
  summary: string;
  measurements: SuiteMeasurement[];
  /** Measured on one side only, or with no known direction. Never dropped. */
  unpaired: { metric: string; reason: string }[];
}

export const suiteApi = {
  /** What exists, what can run, and why the rest cannot — before anything runs. */
  catalogue: () => fetchJson<SuiteCatalogue>("/benchmark/suite"),

  /**
   * Run the suite, streaming one event per bench.
   *
   * The whole run arrives on the `done` event; nothing here reassembles one
   * from the per-bench events, because a dropped message would then produce a
   * run quietly missing a bench.
   */
  run: (
    payload: { benches?: string[] | null; label: string; repeats: number },
    onEvent: (event: Record<string, unknown>) => void,
    onDone?: () => void,
  ): (() => void) =>
    postEventStream(
      "/benchmark/suite/run",
      payload,
      "suite run",
      onEvent,
      onDone,
    ),

  /** Judge two runs against each other. Nothing is stored on either side. */
  compare: (before: SuiteRun, after: SuiteRun) =>
    fetchJson<SuiteComparison>("/benchmark/suite/compare", {
      method: "POST",
      body: JSON.stringify({ before, after }),
    }),
};

export const verifyApi = {
  /** What a round over these settings could and could not show, before anything runs. */
  coverage: (settingIds: string[]) =>
    fetchJson<VerifyCoverage>("/benchmark/verify/coverage", {
      method: "POST",
      body: JSON.stringify({ setting_ids: settingIds }),
    }),

  /** Which instrument speaks to which metric, and why nothing speaks to the rest. */
  sources: () => fetchJson<VerifySources>("/benchmark/verify/sources"),

  /** One reading from one instrument, already keyed by claim metric. */
  sample: (instrument: "dpc" | "network", targetName = "") =>
    fetchJson<VerifySample>("/benchmark/verify/sample", {
      method: "POST",
      body: JSON.stringify({ instrument, target_name: targetName }),
    }),

  /** Judge the settings' own claims against a before/after pair. */
  round: (payload: {
    setting_ids: string[];
    before: Record<string, number[]>;
    after: Record<string, number[]>;
    notes?: string[];
  }) =>
    fetchJson<VerifyReport>("/benchmark/verify/round", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

/**
 * What one game last reached on this machine, against what its panel could show.
 *
 * `tier` is the band the ratio falls in, and it is what decides whether raising
 * image quality is a tweak or a way of lowering the ceiling. `null` everywhere
 * means unmeasured, which is a real answer and not an empty state: the product
 * treats silence as "no room", so an unmeasured game is one that will not be
 * offered a sharper image.
 */
export interface GameHeadroom {
  game: string;
  label: string;
  is_running: boolean;
  is_measured: boolean;
  measured_fps: number | null;
  fps_1_percent_low: number | null;
  target_fps: number | null;
  achievement_percent: number | null;
  tier: "met" | "near" | "short" | "critical" | "unknown";
  bottleneck: string;
  cpu_busy_ms: number | null;
  gpu_time_ms: number | null;
  input_latency_ms: number | null;
  measured_at: number | null;
}

/** Why a measurement did not happen. Each one implies a different next step. */
export type MeasureOutcome =
  | "measured"
  | "already_fresh"
  | "no_game_running"
  | "presentmon_missing"
  | "panel_unknown"
  | "probe_failed";

export interface MeasureResult {
  measured: boolean;
  outcome: MeasureOutcome;
  detail: string;
  game: string | null;
  headroom: GameHeadroom | null;
}

export const headroomApi = {
  /**
   * Every known game's current reading. Always answerable, including before
   * anything has been measured — no history is kept, only the last result.
   */
  list: () =>
    fetchJson<{ poll_interval_seconds: number; games: GameHeadroom[] }>(
      "/benchmark/headroom",
    ),

  /**
   * Measure now. Omitting the game measures whichever one is running, because
   * the user pressing this knows what they have open.
   */
  measure: (game?: string) =>
    fetchJson<MeasureResult>("/benchmark/headroom/measure", {
      method: "POST",
      body: JSON.stringify({ game: game ?? null }),
    }),
};

/**
 * Centralized Setting Entity Types
 *
 * Single Source of Truth for setting interfaces.
 * Used by store, components, and API client.
 */

/** Module prefix for display settings — used to trigger monitor refresh after changes. */
export const DISPLAY_MODULE_PREFIX = "display:";

/** Check if a setting ID belongs to the display module. */
export function isDisplaySetting(settingId: string): boolean {
  return settingId.startsWith(DISPLAY_MODULE_PREFIX);
}

/**
 * Unique setting identifier: `{moduleName}:{settingName}`
 * Examples: "timer:hpet", "power:power_plan", "network:nagle_algorithm"
 */
export type SettingId = `${string}:${string}`;

// =============================================================================
// Category Metadata (from backend - SSOT)
// =============================================================================

/**
 * Category metadata from backend API.
 * This is the SSOT for category UI - frontend should not hardcode any of this.
 */
export interface CategoryMetadata {
  id: string;
  displayName: string;
  description: string;
  icon: string; // Lucide icon name: "Clock", "Zap", "Wifi"
  color: string; // Tailwind class: "text-blue-500"
  isActionOnly: boolean; // True for categories shown in Maintenance tab only
  order: number;
}

/**
 * Category metadata response from API (snake_case)
 */
export interface CategoryMetadataResponse {
  id: string;
  display_name: string;
  description: string;
  icon: string;
  color: string;
  order: number;
  is_action_only: boolean;
}

/**
 * Convert API response to CategoryMetadata
 */
export function categoryResponseToMetadata(
  response: CategoryMetadataResponse,
): CategoryMetadata {
  return {
    id: response.id,
    displayName: response.display_name,
    description: response.description,
    icon: response.icon,
    color: response.color,
    isActionOnly: response.is_action_only,
    order: response.order,
  };
}

// =============================================================================
// Module Metadata (from backend - SSOT)
// =============================================================================

/**
 * Module metadata from backend API.
 * This is the SSOT for module UI - frontend should not hardcode any of this.
 * Replaces hardcoded MODULE_DISPLAY_NAMES and MODULE_DESCRIPTIONS.
 */
export interface ModuleMetadata {
  id: string;
  displayName: string;
  description: string;
  order: number;
}

/**
 * Module metadata response from API (snake_case)
 */
export interface ModuleMetadataResponse {
  id: string;
  display_name: string;
  description: string;
  order: number;
}

/**
 * Convert API response to ModuleMetadata
 */
export function moduleResponseToMetadata(
  response: ModuleMetadataResponse,
): ModuleMetadata {
  return {
    id: response.id,
    displayName: response.display_name,
    description: response.description,
    order: response.order,
  };
}

/**
 * Value types for settings
 */
export type SettingValueType = "bool" | "int" | "float" | "string" | "choice";

/**
 * Kind of gain a setting delivers. Mirrors CATEGORY_ORDER in
 * `settings/impact_categories.py`; the backend derives the values, this type
 * only names them for display.
 */
export type ImpactCategory =
  | "latency"
  | "fps"
  | "thermal"
  | "network"
  | "resources"
  | "storage"
  | "privacy"
  | "visual";

/** Display metadata per impact category. Order matches the backend's. */
export const IMPACT_CATEGORY_META: Record<
  ImpactCategory,
  { label: string; className: string }
> = {
  latency: { label: "Latency", className: "text-sky-300 border-sky-400/25 bg-sky-400/10" },
  fps: { label: "FPS", className: "text-emerald-300 border-emerald-400/25 bg-emerald-400/10" },
  // "Heat & wear", not "Thermal": what this buys is a frame rate that still
  // holds in minute forty, which "Thermal" reads as a fan-noise concern.
  thermal: { label: "Heat & wear", className: "text-orange-300 border-orange-400/25 bg-orange-400/10" },
  network: { label: "Network", className: "text-indigo-300 border-indigo-400/25 bg-indigo-400/10" },
  resources: { label: "Resources", className: "text-violet-300 border-violet-400/25 bg-violet-400/10" },
  storage: { label: "Storage", className: "text-teal-300 border-teal-400/25 bg-teal-400/10" },
  privacy: { label: "Privacy", className: "text-rose-300 border-rose-400/25 bg-rose-400/10" },
  visual: { label: "Visual", className: "text-amber-300 border-amber-400/25 bg-amber-400/10" },
};

/**
 * Setting status based on current vs recommended value
 */
export type SettingStatus =
  | "loading"
  | "optimal"
  | "suboptimal"
  | "default"
  | "error";

/**
 * Execution status for apply/revert operations
 */
export type ExecutionStatus = "idle" | "pending" | "success" | "error";

/**
 * Category for grouping settings in UI.
 * String type allows backend to define new categories without frontend changes.
 */
export type SettingCategory = string;

/**
 * Optimization scope for profile filtering.
 * Settings are categorized by impact level, not risk.
 */
export type SettingScope = "essential" | "recommended" | "complete";

/**
 * Centralized Setting entity - Single Source of Truth
 * Combines static metadata with runtime state
 */
export interface Setting {
  // === Identity ===
  id: SettingId; // "timer:hpet"
  module: string; // "timer"
  name: string; // "hpet"

  // === Display Metadata (static) ===
  displayName: string; // "HPET (High Precision Event Timer)"
  description: string; // "Windows timer source..."
  category: SettingCategory; // "core"

  // === Value Schema (static) ===
  valueType: SettingValueType; // "choice"
  choices: string[]; // ["enabled", "disabled", "default"]
  defaultValue: unknown; // "enabled"
  recommendedValue: unknown; // "disabled"

  // === Behavior (static) ===
  requiresReboot: boolean; // true
  isAction: boolean; // false (true for cleanup operations)

  // === Profile System (static) ===
  scope: SettingScope; // "essential", "recommended", "complete"

  // === Impact Documentation (static) ===
  currentImpact: string; // "When enabled, system uses slower..."
  recommendedImpact: string; // "Disabled forces modern TSC..."
  effect?: string; // Combined summary: "Reduces input latency by 0.1-0.5ms"
  impactScores?: Record<string, string | number>; // {"fps": "+3%", "latency_ms": -0.5}
  /**
   * Kind of gain this setting delivers, e.g. ["latency", "fps"].
   * Derived on the backend from impactScores — never assembled here, so the tag
   * on a row and the number in the header cannot disagree.
   */
  impactCategories: ImpactCategory[];

  // === Display (static) ===
  shortName?: string; // Optional abbreviated name for compact UI
  icon?: string; // Lucide icon name (from backend)
  color?: string; // Tailwind color class (from backend)
  categoryOrder: number; // Sort order within category
  minValue?: number; // Minimum value for INT/FLOAT types
  maxValue?: number; // Maximum value for INT/FLOAT types

  // === Maintenance-specific (static) ===
  durationEstimate?: string; // "5-15 min" for maintenance actions
  supportsStreaming?: boolean; // True for actions with live console output
  progressPattern?: string | null; // Regex to extract progress from output

  // === Risk (static) ===
  riskLevel: "safe" | "low" | "moderate" | "advanced";
  riskWarning?: string;

  // === Evidence (static) ===
  evidenceLevel: "proven" | "likely" | "experimental"; // Research-backed classification
  sources: string[]; // Research/benchmark URLs backing evidence level

  // === Applicability (static) ===
  applicableConditions: Record<string, unknown>; // Conditions for applicability

  // === Advisory / Read-only ===
  isReadonly: boolean; // True for detect-only settings (fan curve, rebar, etc.)

  // === Value Hints ===
  valueHints?: Record<string, string>; // Raw value hints per choice label, e.g. { "enabled": "1" }

  // === Grouping (static) ===
  // Whose setting this is inside the list that owns it: which game, which kind of
  // cleanup. Undefined for a list that renders flat. The label is never spelled
  // here — it arrives from the backend, which already holds the one copy of a
  // game's name (C9).
  groupId?: string;
  groupLabel?: string;
  groupOrder?: number;

  // === Runtime State (dynamic) ===
  currentValue: unknown | null; // "enabled" | null (if loading)
  originalValue?: unknown; // Value before any changes (for revert)
  status: SettingStatus; // Computed from current vs recommended
  executionStatus: ExecutionStatus; // For UI feedback during apply/revert
  lastError?: string; // Error message if operation failed
  lastModified?: string; // ISO timestamp of last change

  // === Computed from backend (dynamic) ===
  isOptimized: boolean; // True if current == recommended (computed once on detection)
  isApplicable: boolean; // False if setting doesn't apply to this hardware
  applicableReason?: string; // Human-readable reason when not applicable
}

/**
 * Minimal definition from API (no runtime state)
 * New format: id is "{category}:{name}" (e.g., "power:usb_selective_suspend")
 */
export interface SettingDefinition {
  id: string;
  category: string;
  display_name: string;
  description: string;
  value_type: string;
  choices: string[];
  default_value: unknown;
  recommended_value: unknown;
  requires_reboot: boolean;
  is_action: boolean;
  current_impact: string;
  recommended_impact: string;
  scope: string;
  short_name?: string;
  icon?: string;
  color?: string;
  category_order?: number;
  applicable_conditions: Record<string, unknown>;
  // Evidence level: "proven", "likely", "experimental"
  evidence_level?: string;
  // Research sources (URLs)
  sources?: string[];
  // Effect fields
  effect?: string;
  impact_scores?: Record<string, string | number>;
  impact_categories?: string[];
  // Numeric range
  min_value?: number;
  max_value?: number;
  // MaintenanceExecutor fields
  duration_estimate?: string;
  supports_streaming?: boolean;
  progress_pattern?: string | null;
  // Advisory/detect-only
  is_readonly?: boolean;
  // UI value hints: choice label → raw value string
  value_hints?: Record<string, string>;
  // Group heading this setting renders under, resolved by the backend
  group_id?: string | null;
  group_label?: string | null;
  group_order?: number | null;
  // Risk level
  risk_level?: string;
  risk_warning?: string;
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Parse setting ID into module and name
 */
export function parseSettingId(id: SettingId): {
  module: string;
  name: string;
} {
  const colonIndex = id.indexOf(":");
  if (colonIndex === -1) {
    throw new Error(`Invalid setting ID: ${id}`);
  }
  return {
    module: id.slice(0, colonIndex),
    name: id.slice(colonIndex + 1),
  };
}

/**
 * Whether there is genuinely something of fpstune's to undo on this setting.
 *
 * Undo and reset are different promises: reset writes the Windows stock value,
 * undo writes what *this machine* held the first time fpstune saw it. Offering
 * undo without a recorded original would either do nothing or fall through to a
 * reset, which is the wrong promise silently kept.
 *
 * Lives here rather than inside a row because two rows ask it — the full
 * settings row and the compact one on Home — and the rule that decides whether
 * a destructive-looking control appears is not a thing to have two copies of.
 */
export function canUndoSetting(setting: Setting): boolean {
  return (
    setting.originalValue !== undefined &&
    setting.originalValue !== null &&
    !valuesEqual(setting.currentValue, setting.originalValue)
  );
}

/**
 * Read a value as a number, or null when it is not one.
 *
 * The empty string is excluded deliberately: `Number("")` is 0, which would make
 * an unset audio device compare equal to a volume of zero.
 *
 * Non-numeric shapes that merely contain digits — `2560x1440`, `Auto:300.000`,
 * `aniso 16x` — return null and fall through to string comparison, which is the
 * correct answer for them.
 */
function toComparableNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function toComparableBoolean(value: unknown): boolean | null {
  if (typeof value === "boolean") return value;
  if (typeof value !== "string") return null;
  const lowered = value.trim().toLowerCase();
  if (lowered === "true") return true;
  if (lowered === "false") return false;
  return null;
}

/**
 * Compare two setting values the way the backend does.
 *
 * This is the mirror of `applicability.values_equal`, and it has to be: the game
 * configs write `0.500000` where a slider sends `0.5`, and the API carries a
 * recommendation as a string beside a detected value that arrived as a number.
 * Strict equality reads those as different, so a setting that had been applied
 * correctly kept rendering as drifted and its Apply badge never cleared.
 *
 * Numbers are compared numerically across types, booleans across `true`/`"true"`,
 * and everything else case-insensitively as text.
 */
export function valuesEqual(a: unknown, b: unknown): boolean {
  if (a === null || a === undefined || b === null || b === undefined) {
    return false;
  }

  // Before the numeric branch: `Number(true)` is 1, so a boolean would other-
  // wise compare equal to the number 1.
  const boolA = toComparableBoolean(a);
  const boolB = toComparableBoolean(b);
  if (boolA !== null && boolB !== null) return boolA === boolB;
  if (boolA !== null || boolB !== null) return false;

  const numA = toComparableNumber(a);
  const numB = toComparableNumber(b);
  if (numA !== null && numB !== null) return Math.abs(numA - numB) < 0.001;

  return String(a).toLowerCase() === String(b).toLowerCase();
}

/**
 * Convert API definition to Setting entity
 */
export function definitionToSetting(def: SettingDefinition): Setting {
  // Parse id to get module and name (e.g., "power:usb_selective_suspend" -> module="power", name="usb_selective_suspend")
  const parsed = parseSettingId(def.id as SettingId);

  return {
    id: def.id as SettingId,
    module: parsed.module,
    name: parsed.name,
    displayName: def.display_name,
    description: def.description,
    category: def.category as SettingCategory,
    valueType: def.value_type as SettingValueType,
    choices: def.choices,
    defaultValue: def.default_value,
    recommendedValue: def.recommended_value,
    requiresReboot: def.requires_reboot,
    isAction: def.is_action,
    scope: (def.scope || "recommended") as SettingScope,
    currentImpact: def.current_impact,
    recommendedImpact: def.recommended_impact,
    effect: def.effect,
    impactScores: def.impact_scores,
    // Filtered against the known set rather than cast: a backend that adds a
    // category before the frontend knows it should render one tag fewer, not
    // an unstyled tag with no label.
    impactCategories: (def.impact_categories ?? []).filter(
      (c): c is ImpactCategory => c in IMPACT_CATEGORY_META,
    ),
    shortName: def.short_name,
    icon: def.icon,
    color: def.color,
    categoryOrder: def.category_order ?? 0,
    minValue: def.min_value,
    maxValue: def.max_value,
    durationEstimate: def.duration_estimate,
    supportsStreaming: def.supports_streaming,
    progressPattern: def.progress_pattern,
    riskLevel: (def.risk_level || "low") as
      | "safe"
      | "low"
      | "moderate"
      | "advanced",
    riskWarning: def.risk_warning,
    evidenceLevel: (def.evidence_level || "likely") as
      | "proven"
      | "likely"
      | "experimental",
    sources: def.sources || [],
    applicableConditions: def.applicable_conditions || {},
    isReadonly: def.is_readonly ?? false,
    valueHints: def.value_hints,
    groupId: def.group_id ?? undefined,
    groupLabel: def.group_label ?? undefined,
    groupOrder: def.group_order ?? undefined,
    // Runtime state (initialized)
    currentValue: null,
    status: "loading",
    executionStatus: "idle",
    isOptimized: false,
    isApplicable: true, // Assume applicable until detection says otherwise
  };
}

/**
 * Format a setting value for display
 */
export function formatSettingValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "boolean") {
    return value ? "Enabled" : "Disabled";
  }

  // Numbers are normalised whether they arrived as numbers or as text, because
  // the two sides of a row routinely disagree about which: game configs store
  // `0.500000`, a slider sends `0.5`, and rendering both verbatim showed a row
  // as "0.5 → 0.500000" — the same value, displayed as a difference.
  //
  // Trailing zeros go, and the value is not padded either: `1.000000` reads as
  // `1`, which is what a person would write.
  const numeric = toComparableNumber(value);
  if (numeric !== null) {
    if (Number.isInteger(numeric)) return String(numeric);
    // Four places is past anything these settings distinguish (comparison
    // tolerance is 0.001) and drops the float noise a longer form exposes.
    return String(Number(numeric.toFixed(4)));
  }

  return String(value);
}



/**
 * MSW request handlers for API mocking.
 */

import { http, HttpResponse } from "msw";

// Sample data for tests
const sampleSystemInfo = {
  os_platform: "win32",
  os_edition: "Windows 11 Pro",
  os_version: "10.0.22621",
  os_display_version: "23H2",
  cpu_name: "AMD Ryzen 9 5900X",
  cpu_cores: 12,
  cpu_threads: 24,
  ram_gb: 32,
  gpu_vendor: "nvidia",
  gpu_name: "NVIDIA GeForce RTX 4080",
  gpu_driver_version: "555.42",
  is_admin: true,
};

// Current SettingExecutor-based API shapes (SettingDefinitionResponse[])
const sampleSettingsDefinitions = [
  {
    id: "core:hpet",
    category: "core",
    display_name: "HPET",
    description: "High Precision Event Timer. Controls system timer source.",
    value_type: "choice",
    choices: ["enabled", "disabled"],
    default_value: "enabled",
    recommended_value: "disabled",
    requires_reboot: true,
    is_action: false,
    current_impact: "Enabled: higher timer latency",
    recommended_impact: "Disabled: -2ms timer latency",
    scope: "recommended",
    applicable_conditions: {},
  },
];

const sampleCategoriesMetadata = [
  {
    id: "core",
    display_name: "Core",
    description: "Core system optimizations",
    icon: "cpu",
    color: "#3b82f6",
    order: 0,
    is_action_only: false,
  },
];

export const handlers = [
  // Setting definitions (SettingExecutor architecture)
  http.get("/api/settings/definitions", () => {
    return HttpResponse.json(sampleSettingsDefinitions);
  }),

  // Category metadata
  http.get("/api/settings/categories/metadata", () => {
    return HttpResponse.json(sampleCategoriesMetadata);
  }),

  // Parallel detection (single request, no polling)
  http.post("/api/settings/detect", () => {
    return HttpResponse.json({
      results: {},
      total_time_ms: 0,
      success_count: 0,
      error_count: 0,
    });
  }),

  // System info
  http.get("/api/system", () => {
    return HttpResponse.json(sampleSystemInfo);
  }),

  // The measurement ledger: nothing measured yet, which is a real answer and
  // not an empty state. Every surface that mounts the ledger card gets this
  // unless the test overrides it with server.use().
  http.get("/api/benchmark/ledger", () => {
    return HttpResponse.json({
      job: null,
      baseline: null,
      after: null,
      areas: [],
      bulk_apply_pending: false,
      poll_interval_seconds: 60,
    });
  }),
];

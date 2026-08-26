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

const sampleStatus = {
  modules: [
    {
      name: "timer",
      display_name: "Timer Resolution",
      description: "System timer optimizations",
      status: "not_applied",
      is_available: true,
      requires_reboot: true,
      message: "",
      details: [],
      settings: [
        {
          name: "hpet",
          display_name: "HPET",
          description: "High Precision Event Timer",
          current_value: "enabled",
          recommended_value: "disabled",
          default_value: "enabled",
          value_type: "choice",
          choices: ["enabled", "disabled"],
          requires_reboot: true,
          is_action: false,
        },
      ],
    },
    {
      name: "priority",
      display_name: "CPU/GPU Priority",
      description: "Process priority settings",
      status: "applied",
      is_available: true,
      requires_reboot: false,
      message: "",
      details: [],
      settings: [
        {
          name: "gpu_priority",
          display_name: "GPU Priority",
          description: "GPU scheduling priority",
          current_value: 8,
          recommended_value: 8,
          default_value: 8,
          value_type: "int",
          requires_reboot: false,
          is_action: false,
        },
      ],
    },
  ],
  applied_count: 1,
  total_count: 2,
  loading: false,
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

  // Category list
  http.get("/api/settings/categories", () => {
    return HttpResponse.json(["core"]);
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

  // Status
  http.get("/api/status", () => {
    return HttpResponse.json(sampleStatus);
  }),

  // Health check
  http.get("/api/health", () => {
    return HttpResponse.json({ status: "healthy" });
  }),

  // Benchmark status
  http.get("/api/benchmark/status", () => {
    return HttpResponse.json({
      running: false,
      results: null,
    });
  }),

  // Cleanup status
  http.get("/api/cleanup/status", () => {
    return HttpResponse.json({
      temp_files_mb: 1024,
      browser_cache_mb: 512,
    });
  }),
];

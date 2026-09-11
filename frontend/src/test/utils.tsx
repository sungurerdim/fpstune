/**
 * Test utilities for rendering components with providers.
 */

import React, { ReactElement } from "react";
import { render, RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { MachineHeadroom } from "../lib/api";

/**
 * The reading a machine has before the test scene has ever run.
 *
 * Here rather than copied into each Home test because it is the *default* state
 * of the product — a machine fpstune has just been installed on — and a mock of
 * it that drifts from the real shape makes every test that uses it agree with a
 * payload the backend never sends.
 */
export function unmeasuredHeadroom(
  overrides: Partial<MachineHeadroom> = {},
): MachineHeadroom {
  return {
    is_measured: false,
    measured_fps: null,
    fps_1_percent_low: null,
    target_fps: null,
    achievement_percent: null,
    tier: "unknown",
    bottleneck: "unknown",
    present_mode: null,
    width: null,
    height: null,
    measured_at: null,
    ...overrides,
  };
}

// Create a new QueryClient for each test
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

interface WrapperProps {
  children: React.ReactNode;
}

function createWrapper() {
  const queryClient = createTestQueryClient();

  return function Wrapper({ children }: WrapperProps) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

function customRender(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">,
) {
  return render(ui, { wrapper: createWrapper(), ...options });
}

// Re-export everything
// eslint-disable-next-line react-refresh/only-export-components -- test utility re-exports
export * from "@testing-library/react";
// Explicit re-exports for TypeScript
export { screen, fireEvent, waitFor } from "@testing-library/react";
export { customRender as render };
export { createTestQueryClient };

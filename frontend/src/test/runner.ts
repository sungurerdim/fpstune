import { vi } from "vitest";
import type { CleanupRunner } from "../hooks/useCleanupRunner";

/**
 * A stand-in for the cleanup runner, so a row or a panel can be rendered
 * without a live mutation behind it.
 *
 * One helper rather than one per test file: the runner's shape is what every
 * action surface is written against, and three private copies of it drift the
 * moment a field is added — the surfaces would then be tested against a
 * contract the product no longer has.
 */
export function makeRunner(
  overrides: Partial<CleanupRunner> = {},
): CleanupRunner {
  return {
    selectedIds: [],
    selectedCount: 0,
    hasSelection: false,
    isRunning: false,
    run: vi.fn(),
    confirmIds: null,
    confirmRun: vi.fn(),
    cancelConfirm: vi.fn(),
    ...overrides,
  };
}

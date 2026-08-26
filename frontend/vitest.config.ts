/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    // Worker threads, not forked processes (#29).
    //
    // `testTimeout` is a wall-clock budget, and `@vitest/runner`'s `withTimeout`
    // spends it twice: a `setTimeout` for async bodies, and — after a *synchronous*
    // body has already run to completion with every assertion passing — a
    // `now() - startTime >= timeout` check that fails the test anyway. So a test
    // whose body costs about a millisecond of CPU is failed as "Test timed out in
    // 5000ms" purely because its process was descheduled. No query, `waitFor` or
    // `userEvent` rewrite can reach that: the body ran and passed.
    //
    // Vitest 4 defaults to `pool: 'forks'`, which with `isolate` spawns a node
    // process per test file — the most expensive thing Windows can be asked to do
    // repeatedly, and the thing that starves the other workers. Measured over full
    // suite runs with the machine held at 100% CPU by 16 busy loops: forks failed
    // 6 of 14 runs with 1-5 of these phantom timeouts each, in a different file
    // every time; threads failed 0 of 14, over 344 tests. Nothing is paid for it:
    // alternating the two pools back to back on the same machine, threads ran the
    // full suite in 23.5s and 24.5s against forks' 27.0s and 27.7s.
    //
    // This is a determinism fix, not a speed one — capping `maxWorkers` was tried
    // first and left 3 of 5 runs red, so it is deliberately not part of the fix.
    pool: 'threads',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/test/**',
        'src/**/*.d.ts',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
      thresholds: {
        lines: 60,
        functions: 60,
        branches: 60,
        statements: 60,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})

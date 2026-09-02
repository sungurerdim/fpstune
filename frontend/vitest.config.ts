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
    // Forked processes, not worker threads — and this reverses #29, which chose
    // threads on its own measurement. Both notes are kept, because the reason it
    // reversed is the toolchain moving underneath the earlier one.
    //
    // What #29 measured, on the previous vitest: `testTimeout` is a wall-clock
    // budget, and `@vitest/runner`'s `withTimeout` spent it twice — a
    // `setTimeout` for async bodies, and, after a *synchronous* body had already
    // run to completion with every assertion passing, a
    // `now() - startTime >= timeout` check that failed the test anyway. Under a
    // machine held at 100% CPU, forks failed 6 of 14 runs with those phantom
    // timeouts and threads failed 0 of 14.
    //
    // What the current vitest does instead is fail to start its workers at all:
    // `[vitest-pool]: Failed to start threads worker ... Timeout waiting for
    // worker to respond`. Measured here, six full-suite runs per pool on the
    // upgraded toolchain:
    //
    //   threads  started all 57 suites in 3 of 6 runs; fully green in 2 of 6.
    //            The bad runs started 12, 17 and 47 suites — and two of them
    //            reported zero failing tests while running a fraction of the
    //            suite, which is a gate that looks passed without having run.
    //   forks    started all 57 suites in 6 of 6; fully green in 5 of 6, the
    //            sixth a single flaky test rather than a missing suite.
    //
    // A suite that never starts is the failure worth avoiding, so the pool that
    // always starts wins. Capping `maxWorkers` is still not part of this — #29
    // tried it and it left 3 of 5 runs red.
    pool: 'forks',
    // Four workers, not one per core.
    //
    // Even alone on this 16-core machine, and even after the rest of the
    // pre-commit hook had finished, vitest kept losing workers to
    // `Timeout waiting for worker to respond` — the handshake with a freshly
    // spawned process, not the tests. Measured, three full-suite runs each:
    // 8 workers started all 57 suites once (55, 53, 57), 4 workers started all
    // 57 every time. #29 rejected a worker cap, but that was against the old
    // vitest and a different failure — phantom test timeouts, not workers that
    // never answer.
    maxWorkers: 4,
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

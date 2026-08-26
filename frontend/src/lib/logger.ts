/**
 * Structured logger for the frontend.
 *
 * Usage:
 *   import { createLogger } from '../lib/logger'
 *   const log = createLogger('MyComponent')
 *   log.info('Loaded', { count: 5 })
 *
 * In production builds (import.meta.env.PROD) debug and info calls are
 * silenced. Warn and error always reach the console.
 */

const STYLES = {
  debug: "color: #6b7280", // gray
  info: "color: #3b82f6", // blue
  success: "color: #22c55e", // green
  warn: "color: #f59e0b", // amber
  error: "color: #ef4444", // red
} as const;

type Level = "debug" | "info" | "warn" | "error";

const isProd = import.meta.env.PROD;

export interface Logger {
  debug(msg: string, ...args: unknown[]): void;
  info(msg: string, ...args: unknown[]): void;
  /** Alias for info — visually styled green in dev console. */
  success(msg: string, ...args: unknown[]): void;
  warn(msg: string, ...args: unknown[]): void;
  error(msg: string, ...args: unknown[]): void;
}

function write(
  scope: string,
  level: Level,
  style: string,
  msg: string,
  args: unknown[],
): void {
  if (isProd && (level === "debug" || level === "info")) return;

  const fn =
    level === "warn"
      ? console.warn
      : level === "error"
        ? console.error
        : console.log;
  fn(`%c[${scope}] ${msg}`, style, ...args);
}

export function createLogger(scope: string): Logger {
  return {
    debug: (msg, ...args) => write(scope, "debug", STYLES.debug, msg, args),
    info: (msg, ...args) => write(scope, "info", STYLES.info, msg, args),
    success: (msg, ...args) => write(scope, "info", STYLES.success, msg, args),
    warn: (msg, ...args) => write(scope, "warn", STYLES.warn, msg, args),
    error: (msg, ...args) => write(scope, "error", STYLES.error, msg, args),
  };
}

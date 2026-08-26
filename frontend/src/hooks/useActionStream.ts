/**
 * SSE hook for streaming maintenance action output.
 *
 * Connects to the SSE endpoint and streams live console output
 * from maintenance actions like DISM cleanup, SFC scan, etc.
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { createLogger } from "../lib/logger";

const API_BASE = "/api";
const log = createLogger("useActionStream");

export interface ActionEvent {
  type: "output" | "progress" | "complete" | "error";
  line: string;
  progress: number;
  success: boolean;
  error: string;
}

export interface UseActionStreamResult {
  /** Output lines (most recent 10) */
  output: string[];
  /** Whether action is currently running */
  isRunning: boolean;
  /** Error message if any */
  error: string | null;
  /** Whether action completed successfully */
  success: boolean | null;
  /** Execute the action */
  execute: () => void;
  /** Stop/cancel the action */
  stop: () => void;
  /** Clear output and reset state */
  reset: () => void;
}

const MAX_OUTPUT_LINES = 10;

export function useActionStream(settingId: string): UseActionStreamResult {
  const [output, setOutput] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<boolean | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const execute = useCallback(() => {
    // Reset state
    setOutput([]);
    setIsRunning(true);
    setError(null);
    setSuccess(null);

    // Close any existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    // Create new EventSource connection
    const url = `${API_BASE}/settings/actions/${encodeURIComponent(settingId)}/execute`;
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      try {
        const data: ActionEvent = JSON.parse(event.data);

        switch (data.type) {
          case "output":
            setOutput((prev) => {
              const newOutput = [...prev, data.line];
              // Keep only last N lines
              return newOutput.slice(-MAX_OUTPUT_LINES);
            });
            break;

          case "progress":
            // Could be used for progress bar if needed
            break;

          case "complete":
            setIsRunning(false);
            setSuccess(data.success);
            if (!data.success && data.error) {
              setError(data.error);
            }
            eventSource.close();
            break;

          case "error":
            setIsRunning(false);
            setSuccess(false);
            setError(data.error || "Unknown error");
            eventSource.close();
            break;
        }
      } catch (e) {
        log.error("Failed to parse SSE event:", e, event.data);
      }
    };

    eventSource.onerror = (e) => {
      log.error("SSE connection error:", e);
      setIsRunning(false);
      setSuccess(false);
      setError("Connection lost");
      eventSource.close();
    };
  }, [settingId]);

  const stop = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsRunning(false);
  }, []);

  const reset = useCallback(() => {
    stop();
    setOutput([]);
    setError(null);
    setSuccess(null);
  }, [stop]);

  // An unmounted component cannot press stop. Without this, switching tabs
  // mid-DISM leaves the connection open and the browser keeps reconnecting to a
  // stream whose events land in a component that no longer exists — one leaked
  // socket per action started, for the life of the page.
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
  }, []);

  return {
    output,
    isRunning,
    error,
    success,
    execute,
    stop,
    reset,
  };
}

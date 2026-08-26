/**
 * ActionConsole Component
 *
 * Displays live streaming output from maintenance actions.
 * Shows a mini console with scrolling output lines (last 10).
 */

import { Play, Square, RotateCcw, Check, X, Loader2 } from "lucide-react";
import { cn } from "../lib/utils";
import { useActionStream } from "../hooks/useActionStream";
import type { Setting } from "../types/setting";

interface ActionConsoleProps {
  setting: Setting;
  className?: string;
}

export function ActionConsole({ setting, className = "" }: ActionConsoleProps) {
  const { output, isRunning, error, success, execute, stop, reset } =
    useActionStream(setting.id);

  const hasOutput = output.length > 0 || isRunning || error || success !== null;

  return (
    <div className={cn("space-y-2", className)}>
      {/* Header with action name and controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm">{setting.displayName}</span>
          {success === true && <Check className="w-4 h-4 text-success" />}
          {success === false && <X className="w-4 h-4 text-destructive" />}
        </div>

        <div className="flex items-center gap-1">
          {/* Reset button (only show when completed) */}
          {hasOutput && !isRunning && (
            <button
              onClick={reset}
              className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
              title="Clear output"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          )}

          {/* Run/Stop button */}
          <button
            onClick={isRunning ? stop : execute}
            disabled={false}
            className={cn(
              "px-3 py-1 rounded text-sm font-medium transition-colors flex items-center gap-1.5",
              isRunning
                ? "bg-destructive/10 text-destructive hover:bg-destructive/20"
                : "bg-primary text-primary-foreground hover:bg-primary/90",
            )}
          >
            {isRunning ? (
              <>
                <Square className="w-3.5 h-3.5" />
                Stop
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                Run
              </>
            )}
          </button>
        </div>
      </div>

      {/* Console output */}
      {hasOutput && (
        <div className="bg-black/90 text-green-400 font-mono text-xs p-3 rounded-lg h-40 overflow-y-auto border border-border/30">
          {output.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap break-all">
              {line}
            </div>
          ))}

          {/* Running indicator */}
          {isRunning && (
            <div className="flex items-center gap-2 text-muted-foreground mt-1">
              <Loader2 className="w-3 h-3 animate-spin" />
              <span className="animate-pulse">Running...</span>
            </div>
          )}

          {/* Error display */}
          {error && (
            <div className="text-red-400 mt-2 pt-2 border-t border-red-400/30">
              Error: {error}
            </div>
          )}

          {/* Success message */}
          {success === true && !isRunning && (
            <div className="text-green-400 mt-2 pt-2 border-t border-green-400/30">
              Completed successfully
            </div>
          )}
        </div>
      )}

      {/* Description when no output */}
      {!hasOutput && (
        <p className="text-xs text-muted-foreground">{setting.description}</p>
      )}
    </div>
  );
}

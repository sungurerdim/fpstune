import React, { Component, ErrorInfo, ReactNode, useEffect } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { detectionManager } from "./lib/detection-manager";
import { hardwareManager } from "./lib/hardware-manager";
import { createLogger } from "./lib/logger";
import { useStore } from "./store";
import "./index.css";

const log = createLogger("App");

// Error Boundary to catch React errors
interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    log.error("ErrorBoundary caught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-background flex items-center justify-center p-6">
          <div className="bg-card rounded-lg border border-destructive p-6 max-w-md">
            <h1 className="text-xl font-bold text-destructive mb-2">
              Something went wrong
            </h1>
            <p className="text-muted-foreground mb-4">
              {this.state.error?.message || "An unexpected error occurred"}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90"
            >
              Reload Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchOnMount: false,
      retry: 1,
      retryDelay: 1000,
    },
  },
});

// Main app wrapper. The UI shell renders immediately; data loads in the
// background and streams into the store, so a slow or unreachable backend never
// produces a blank screen — sections show their own loading/empty states and
// fill in as soon as data arrives.
// eslint-disable-next-line react-refresh/only-export-components -- entry point helper
function AppWithDetection() {
  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let notifiedOffline = false;

    const init = async (attempt: number) => {
      try {
        // Load definitions into the store. App is already rendered and reacts
        // as the store fills — this never blocks first paint.
        await detectionManager.initializeStore();
        if (cancelled) return;

        // Hardware + detections run fire-and-forget in the background.
        hardwareManager.getHardware().catch((err) =>
          log.error("Hardware fetch failed:", err),
        );
        detectionManager.detectAll();
      } catch (err) {
        if (cancelled) return;
        log.error("Initialization failed (retrying in background):", err);
        if (!notifiedOffline) {
          notifiedOffline = true;
          useStore
            .getState()
            .addNotification(
              "Cannot reach the backend — retrying in the background.",
              "error",
            );
        }
        // Exponential backoff capped at 15s so data flows in automatically
        // once the backend becomes reachable.
        const delay = Math.min(1000 * 2 ** attempt, 15000);
        retryTimer = setTimeout(() => init(attempt + 1), delay);
      }
    };

    init(0);

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      detectionManager.stopAll();
      hardwareManager.stopPolling();
    };
  }, []);

  return <App />;
}

// Prevent double-rendering during HMR
const container = document.getElementById("root")!;
// Store root reference on window for HMR persistence
declare global {
  interface Window {
    __REACT_ROOT__?: ReactDOM.Root;
  }
}

if (!window.__REACT_ROOT__) {
  window.__REACT_ROOT__ = ReactDOM.createRoot(container);
}

window.__REACT_ROOT__.render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AppWithDetection />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);

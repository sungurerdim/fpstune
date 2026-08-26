import { Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";

interface LoadingSpinnerProps {
  size?: "xs" | "sm" | "md" | "lg";
  className?: string;
}

const sizeMap = {
  xs: "w-3 h-3",
  sm: "w-4 h-4",
  md: "w-5 h-5",
  lg: "w-6 h-6",
};

/**
 * Shared loading spinner component for consistent UI across the app.
 * Replaces duplicate <Loader2 className="animate-spin" /> patterns.
 */
export function LoadingSpinner({
  size = "sm",
  className = "",
}: LoadingSpinnerProps) {
  return (
    <Loader2
      className={cn(
        sizeMap[size],
        "animate-spin text-muted-foreground",
        className,
      )}
    />
  );
}

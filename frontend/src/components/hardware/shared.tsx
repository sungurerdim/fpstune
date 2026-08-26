import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "../../lib/utils";
import { LoadingSpinner } from "../ui/LoadingSpinner";

export function LoadingDot() {
  return <LoadingSpinner size="xs" className="inline ml-1" />;
}

// Check if a category is still loading

// Safe array access helper


/**
 * Reusable hardware section wrapper
 */
export function HardwareSection({
  icon,
  title,
  count,
  loading,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  count?: number;
  loading?: boolean;
  children: React.ReactNode;
}) {
  // A section heading was the same size and colour as the specs underneath it, so
  // the page read as one undifferentiated column. It is now the largest thing in
  // its own block, which is what makes the eye able to skip by device.
  return (
    <section aria-label={title}>
      <h4 className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold text-foreground">
        {icon} {title}
        {count !== undefined && count > 0 && (
          <span className="font-normal text-muted-foreground">({count})</span>
        )}
        {loading && <LoadingDot />}
      </h4>
      {children}
    </section>
  );
}

/**
 * Not detected placeholder
 */
export function NotDetected() {
  return (
    <div className="border-l-2 border-border pl-3 text-xs text-muted-foreground">
      Not detected
    </div>
  );
}

/**
 * Copyable text with icon
 */
export function CopyableText({
  value,
  className,
}: {
  value: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Fallback for older browsers
      const textArea = document.createElement("textarea");
      textArea.value = value;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <span className={cn("inline-flex items-center gap-1 group", className)}>
      <span className="font-mono">{value}</span>
      <button
        onClick={handleCopy}
        className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:bg-muted rounded"
        title="Copy to clipboard"
      >
        {copied ? (
          <Check className="w-3 h-3 text-success" />
        ) : (
          <Copy className="w-3 h-3 text-muted-foreground" />
        )}
      </button>
    </span>
  );
}


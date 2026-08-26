import { cn } from "../../lib/utils";

/**
 * The one way this app says "this is fine" / "this needs doing" / "this needs you".
 *
 * The Hardware page said all three in the same 10px muted grey, so a device with six
 * problems and a device with none were the same shape at a glance — you had to read
 * every line to find out which. A chip carries a background, so the answer survives
 * peripheral vision.
 *
 * `attention` and `advisory` are separate tones on purpose. Both mean "not ideal",
 * but only one of them is something a button can fix; painting them the same colour
 * would promise a Fix that does not exist for half of them.
 */
export type ChipTone = "ok" | "attention" | "advisory" | "neutral";

const TONE_CLASS: Record<ChipTone, string> = {
  ok: "bg-success/15 text-success border-success/25",
  attention: "bg-warning/20 text-warning border-warning/40",
  advisory: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  neutral: "bg-muted text-muted-foreground border-border",
};

export function StatusChip({
  tone,
  icon,
  children,
  className,
  title,
}: {
  tone: ChipTone;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  /** Native tooltip. Chips carry counts; the title carries the why. */
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        // text-xs is the floor. Everything on this page used to sit below it.
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium",
        TONE_CLASS[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

/** Helpers for cleanup size strings of the form "ready|4244 MB". */

/** Parse cleanup detection value "ready|4244 MB" → "4244 MB" (or "calculating"). */
export function parseCleanupSize(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const parts = value.split("|");
  return parts.length >= 2 ? parts[1].trim() : null;
}

/** Convert a size string "4244 MB" or "2 GB" to a number of MB (null if unparseable). */
export function parseSizeToMB(value: unknown): number | null {
  const s = parseCleanupSize(value);
  if (!s) return null;
  const m = s.match(/^([\d.]+)\s*(MB|GB)/i);
  if (!m) return null;
  const n = parseFloat(m[1]);
  return m[2].toUpperCase() === "GB" ? n * 1024 : n;
}

/** Format a size in MB as MB or GB. */
export function fmtMB(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${Math.round(mb)} MB`;
}

/**
 * The English catalogue — the reference locale (F1).
 *
 * Every user-facing string the UI owns lives here, keyed by surface. The
 * Turkish catalogue's type is derived from this object, so a key missing
 * from either side is a compile error, not a runtime fallback: the parity
 * gate is the type-checker itself.
 *
 * Setting copy (description, effect, risk_warning, perceptible_cost) stays
 * English in the backend per C4 and is translated at the edge by
 * `settingCopyTr` — see i18n/settingsTr.ts.
 */
export const en = {
  // First run
  "firstRun.title": "Welcome to fpstune",
  "firstRun.what":
    "fpstune tunes this machine for the best gaming experience it is capable of — frame rate first, derived from your own hardware, never from a generic preset.",
  "firstRun.nothingChanged": "Nothing has been changed yet.",
  "firstRun.nothingChangedBody":
    "Opening the app only reads your current settings. Every change waits for your click, every change can be undone from the same row, and the bulk buttons offer a System Restore point first.",
  "firstRun.admin":
    "The shield in the top corner shows whether fpstune is running as Administrator. Windows requires it for most tweaks — without it you can look at everything, but most Apply buttons will not work.",
  "firstRun.dismiss": "Got it — show me the machine",

  // The two buttons
  "scope.competitive": "Competitive Max",
  "scope.competitiveHint":
    "The most frames without touching what you can see or hear.",
  "scope.absolute": "Absolute Max",
  "scope.absoluteHint":
    "Every setting to its frame-rate extreme — quality is spent, and the cost is listed before anything runs.",
  "scope.competitiveConfirmTitle": "Apply Competitive Max? ({count} settings)",
  "scope.competitiveConfirmBody":
    "Applies every essential and recommended tweak — the most frames this machine can reach without changing anything you can see or hear in-game. Settings that spend visual or audio quality are left alone.",
  "scope.absoluteConfirmTitle": "Apply Absolute Max? ({count} settings)",
  "scope.absoluteConfirmBody":
    "Pushes every setting to its frame-rate extreme, including the ones that spend picture and sound quality.",
  "scope.whatYouGiveUp": "What you give up:",
  "scope.apply": "Apply",
  "scope.spendIt": "Spend it",
  "scope.restoreFirst": "Create a System Restore point first (recommended)",

  // Tabs
  "tab.home": "Home",
  "tab.software": "Software Tweaks",
  "tab.hardware": "Hardware Tweaks",
  "tab.games": "Game Tweaks",
  "tab.cleanup": "Cleanup & Repair",
  "tab.benchmarks": "Benchmarks",

  // Detection notice
  "detection.failedOne": "1 setting could not be checked on this machine",
  "detection.failedMany":
    "{count} settings could not be checked on this machine",
  "detection.absentOne": "1 setting doesn't apply to this hardware",
  "detection.absentMany": "{count} settings don't apply to this hardware",
  "detection.absentFallback": "Not applicable to this system",

  // Self-check notice
  "selfCheck.disagreementsOne":
    "Detection self-check found 1 disagreement — the values below may be wrong on this machine.",
  "selfCheck.disagreementsMany":
    "Detection self-check found {count} disagreements — the values below may be wrong on this machine.",
  "selfCheck.recheck": "Re-check",
  "selfCheck.checking": "Checking…",

  // Locale switch — names the language it would switch TO, in that language.
  "locale.switch": "Switch to English",

  // Common actions
  "action.apply": "Apply",
  "action.cancel": "Cancel",
  "action.run": "Run",
  "action.runAll": "Run All",
  "action.undo": "Undo",
  "action.reset": "Reset",
  "action.verify": "Verify",
  "action.keep": "Keep",

  // Row surface
  "row.ok": "OK",
  "row.advisory": "Advisory",
  "row.verify": "Verify current value",
  "row.undo": "Undo fpstune's change, back to {value}",
  "row.undoNamed": "Undo fpstune's change to {name}, back to {value}",
  "row.undoTooltip":
    "Undo fpstune's change — back to {value}, what this machine had before",
  "row.resetDefault": "Restore the Windows default",
  "row.target": "Target",
  "row.applyNamed": "Apply {name}",
  "sr.optimal": "Already at the recommended value: ",
  "sr.currently": "Currently ",
  "sr.recommendedIs": ", recommended value is ",
  "badge.risk": "RISK",
  "badge.note": "NOTE",

  // Impact categories ("Heat & wear", not "Thermal": what it buys is a frame
  // rate that still holds in minute forty)
  "impact.latency": "Latency",
  "impact.fps": "FPS",
  "impact.thermal": "Heat & wear",
  "impact.network": "Network",
  "impact.resources": "Resources",
  "impact.storage": "Storage",
  "impact.privacy": "Privacy",
  "impact.visual": "Visual",
} as const;

export type MessageKey = keyof typeof en;

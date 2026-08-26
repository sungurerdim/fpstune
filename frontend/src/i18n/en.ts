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

  // Home
  "home.hardwareTweaks": "Hardware tweaks",
  "home.hardwareSubtitle": "GPU, display, adapters, storage, audio",
  "home.softwareTweaks": "Software tweaks",
  "home.softwareSubtitle": "Windows, services, launchers",
  "home.gameTweaks": "Game tweaks",
  "home.gameSubtitle": "Settings inside a game's own config file",
  "home.applyAll": "Apply all {count}",
  "home.readingSettings": "Reading your current settings…",
  "home.allOptimized": "Everything applicable is already optimized.",
  "home.cleanupTitle": "Available disk cleanup actions",
  "home.measuringReclaim": "Measuring what can be reclaimed…",
  "home.nothingToReclaim": "Nothing to reclaim right now.",
  "home.rowMeasuring": "— measuring what can be reclaimed…",
  "home.advisories": "Advisories",
  "home.advisoriesHint": "findings fpstune can detect but only you can change",
  "home.alreadyOptimized": "Already optimized",
  "home.detecting":
    "Detecting your settings — {done}/{total} categories read, the lists and totals fill in as results arrive…",
  "home.detectingProgress": "Detection progress across setting categories",
  "home.statIdeal": "settings at their ideal value",
  "home.statIdealHint":
    "{changed} fpstune changed · {stock} were already correct",
  "home.statGuards": " · {count} drift guards standing watch",
  "home.measured": "Measured",
  "home.noMeasurement":
    "no frame rate measured yet — start a game, or open Benchmarks",
  "home.ofTarget": "{pct}% of the {target} fps this display can show",
  "home.noTarget": "no display target — panel refresh unknown",
  "home.claimed": "Claimed by settings not yet applied",
  "home.latencyTweaks": "latency tweaks",
  "home.memoryTweaks": "memory tweaks",
  "home.diskToReclaim": "disk to reclaim",

  // Cleanup & maintenance surfaces
  "cleanup.systemTitle": "System Cleanup",
  "cleanup.systemDescription":
    "Select which items to clean. Deleted files cannot be recovered.",
  "cleanup.gameTitle": "Game Maintenance",
  "cleanup.gameDescription":
    "Clear game, GPU shader, and launcher caches. Deleted files cannot be recovered; games and drivers rebuild caches on next launch.",
  "cleanup.results": "Cleanup Results",
  "cleanup.resultsEmpty":
    "Select items below and run a cleanup to see freed space here.",
  "cleanup.calculating": "Calculating…",
  "cleanup.freed": "Freed {amount}",
  "cleanup.failedCount": "{count} failed",
  "cleanup.failed": "Failed",
  "cleanup.done": "Done",
  "cleanup.serviceDown":
    "Service not running and could not be started. Start it, then reopen this tab.",
  "cleanup.runCleanup": "Run Cleanup",
  "cleanup.runCleanupCount": "Run Cleanup ({count})",
  "maintenance.title": "System Maintenance",
  "maintenance.description": "Repair and troubleshoot Windows system issues.",
  "maintenance.running": "Running...",
  "maintenance.run": "Run",
  "maintenance.runCount": "Run ({count})",
  "docker.title": "Restart Docker & WSL?",
  "docker.confirm": "Prune & compact",
  "docker.body":
    "Docker Desktop and all WSL distributions will be shut down and restarted so their virtual disk can be compacted and the space truly returned. This can take several minutes. Save your work first.",

  // Selection toolbar
  "toolbar.advancedTitle": "Advanced tweaks selected",
  "toolbar.applyAnyway": "Apply anyway",
  "toolbar.advancedBody":
    "Your selection includes settings marked Advanced. These are experimental and may behave differently depending on your hardware. Proceed?",
  "toolbar.selected": "{count} selected",
  "toolbar.clear": "Clear",
  "toolbar.processing": "Processing…",
  "toolbar.stop": "Stop",
  "toolbar.resetSelected": "Reset Selected",
  "toolbar.applySelected": "Apply Selected",
  "toolbar.resetToDefaults": "Reset to Defaults ({count})",

  // Hardware surfaces
  "hw.title": "Hardware",
  "hw.admin": "Admin",
  "hw.notAdmin": "Not Admin",
  "hw.cpu": "CPU",
  "hw.memory": "Memory",
  "hw.gpu": "GPU",
  "hw.displays": "Displays",
  "hw.storage": "Storage",
  "hw.network": "Network",
  "hw.powerPlan": "Power plan",
  "hw.audioOutput": "Audio Output",
  "hw.audioInput": "Audio Input",
  "hw.loudnessEq": "Loudness EQ",
  "hw.loudnessNotSupported": "Loudness EQ not supported by this device",
  "hw.notDetected": "Not detected",
  "hw.copy": "Copy to clipboard",
  "devices.reading": "Reading tweaks…",
  "devices.showIdeal": "Show tweaks already ideal",
  "devices.hideIdeal": "Hide tweaks already ideal",
  "devices.advisoryHint": "fpstune cannot change these — each row says where to.",

  // Monitor card
  "monitor.applying": "Applying…",
  "monitor.useNative": "Use native mode",
  "monitor.useNativeAll": "Use native mode on all {count} displays",
  "monitor.keepTitle": "Keep this display mode?",
  "monitor.keepAllTitle": "Keep these display modes?",
  "monitor.revertBody":
    "This display goes back to its previous mode in {seconds} seconds unless you keep it — so a mode your screen cannot show fixes itself.",
  "monitor.revertAllBody":
    "Every changed display goes back to its previous mode in {seconds} seconds unless you keep it — so a mode your screen cannot show fixes itself.",
  "monitor.resolution": "Resolution:",
  "monitor.refresh": "Refresh:",
  "monitor.primary": "Primary",
  "monitor.disconnected": "Disconnected",
  "monitor.noCap": "no cap",
  "monitor.fpsCap": "{count} fps cap",
  "monitor.recommendedPrefix": "recommended:",
  "monitor.unknown": "unknown",
  "monitor.notApplicable": "not applicable",
  "monitor.optimizeGsync": "Optimize G-Sync",
  "monitor.resetDriver": "Reset to driver defaults",
  "monitor.resetting": "Resetting…",

  // Network adapter card
  "adapter.connect": "Connect",
  "adapter.disconnect": "Disconnect",
  "adapter.connectTitle": "Connect to network",
  "adapter.disconnectTitle": "Disconnect from network",
  "adapter.on": "On",
  "adapter.off": "Off",
  "adapter.connected": "Connected",
  "adapter.disconnected": "Disconnected",
  "adapter.notConnected": "Not Connected",

  // Power plan card
  "power.activeHint":
    "FPS Balanced is active — full power when a game asks, idle cores allowed to clock down.",
  "power.inactiveHint":
    "FPS Balanced gives full power under load and lets idle cores clock down — less heat for the same frames.",
  "power.activate": "Activate FPS Balanced",
  "power.revert": "Revert to Windows Balanced",
  "power.reverting": "Reverting…",

  // Storage card
  "storage.retrim": "Retrim",
  "storage.defrag": "Defrag",
  "storage.running": "{action} running…",
} as const;

export type MessageKey = keyof typeof en;

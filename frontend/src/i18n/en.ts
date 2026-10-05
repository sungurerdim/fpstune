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
  // Single apply / reset / undo outcomes
  "apply.applied": "Applied {name}",
  "apply.applyFailed": "Could not apply {name}: {reason}",
  "apply.reset": "Reset {name} to the Windows default",
  "apply.resetFailed": "Could not reset {name}: {reason}",
  "apply.undone": "Undid {name}",
  "apply.undoFailed": "Could not undo {name}: {reason}",
  "apply.unknownError": "the reason was not reported",
  "bulk.summary": "{applied} applied, {failed} failed.",
  "bulk.requestFailed": "Nothing was applied: {reason}",
  "hw.displaysFailed": "Could not change every display: {reason}",
  "hw.gsyncApplyFailed": "Could not apply the G-Sync settings: {reason}",
  "hw.gsyncResetFailed": "Could not reset the G-Sync settings: {reason}",
  "hw.displayModeFailed": "Could not change the display mode: {reason}",
  "hw.adapterToggleFailed": "Could not switch the adapter: {reason}",
  "hw.adapterRestartNote": "Changing these settings reconnects the adapter once, a few seconds after the last change.",
  "hw.connectFailed": "Could not connect: {reason}",
  "hw.disconnectFailed": "Could not disconnect: {reason}",
  "hw.audioDeviceFailed": "Could not switch the audio device: {reason}",
  "hw.loudnessFailed": "Could not change loudness equalization: {reason}",
  "hw.powerPlanActivateFailed": "Could not activate the power plan: {reason}",
  "hw.powerPlanRevertFailed": "Could not revert the power plan: {reason}",
  // Version and update (header)
  "update.version": "v{version}",
  "update.check": "Check for updates",
  "update.checking": "Checking…",
  "update.upToDate": "fpstune {version} is the latest release.",
  "update.available": "fpstune {latest} is available (you have {current}).",
  "update.install": "Update to {latest}",
  "update.installing": "Downloading and verifying…",
  "update.unreachable": "Could not check for updates: {reason}",
  "header.admin": "Admin",
  "header.notAdmin": "Not Admin",
  "tab.home": "Home",
  "tab.software": "Software Tweaks",
  "tab.hardware": "Hardware Tweaks",
  "tab.games": "Game Tweaks",
  "tab.cleanup": "Cleanup & Repair",
  "tab.benchmarks": "Benchmarks",
  "tab.history": "History",

  // Display mode confirmation
  "displayConfirm.title": "Keep the new display mode?",
  "displayConfirm.body":
    "{count} monitor(s) switched to their native mode. If the picture looks right, keep it; otherwise it goes back on its own in {seconds} s.",
  "displayConfirm.keep": "Keep",
  "displayConfirm.dontKeep": "Don't keep",

  // Change history
  "history.title": "What fpstune changed",
  "history.intro":
    "Every setting fpstune changed on this machine, in this run and earlier ones. Undo puts back what this machine held before fpstune touched it; Windows default writes the stock value instead.",
  "history.loading": "Reading the history…",
  "history.error": "Could not read the history: {reason}",
  "history.empty": "fpstune has not changed anything on this machine yet.",
  "history.active": "Still changed by fpstune ({count})",
  "history.reverted": "Already put back ({count})",
  "history.action.apply": "Applied",
  "history.action.reset": "Reset to the Windows default",
  "history.action.undo": "Undone",
  "history.value": "set to {value}",
  "history.was": "was {value} before",
  "history.noOriginal":
    "No earlier value is on record for this setting, so only the Windows default can be restored.",
  "history.undo": "Undo",
  "history.reset": "Windows default",
  "history.undoNamed": "Undo fpstune's change to {name}",
  "history.resetNamed": "Restore the Windows default for {name}",
  "history.selectNamed": "Select {name}",
  "history.selectAll": "Select all",
  "history.undoSelected": "Undo selected ({count})",
  "history.resetSelected": "Windows default for selected ({count})",

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
  "osUpdate.body":
    "Windows was updated since fpstune last ran (build {previous} → {current}). Updates can put settings back to Windows' own values; the scan below was taken on the new build.",
  "osUpdate.dismiss": "Dismiss",

  // Locale switch — names the language it would switch TO, in that language.
  "locale.switch": "Switch to English",

  // Common actions
  "action.apply": "Apply",
  "action.cancel": "Cancel",
  "action.run": "Run",
  "action.runAll": "Run All",
  "action.undo": "Undo",
  "action.keep": "Keep",

  // Row surface
  "row.ok": "OK",
  "row.advisory": "Advisory",
  "row.notRead": "Not read",
  "row.verify": "Verify current value",
  "row.undo": "Undo fpstune's change, back to {value}",
  "row.undoNamed": "Undo fpstune's change to {name}, back to {value}",
  "row.undoTooltip":
    "Undo fpstune's change — back to {value}, what this machine had before",
  "row.resetDefault": "Restore the Windows default",
  "row.target": "Target",
  "row.applyNamed": "Apply {name}",
  "row.selectNamed": "Select {name}",
  "row.default": "Default",
  "row.current": "Current",
  "row.skipped": "skipped",
  "row.statusRunning": "Running",
  "row.statusVerified": "Applied and verified",
  "row.statusFailed": "Failed",
  "row.statusFailedBecause": "Failed: {reason}",
  "toolbar.streamFailed": "The bulk run stopped: {reason}",
  "toolbar.doneSummary": "{done} done, {failed} failed.",
  "toolbar.stopped": "Stopped. Settings not yet started were left as they were.",
  "row.queued": "queued",
  "row.notApplicable": "N/A",
  "row.setTo": "Set to {value}",
  "row.resetTo": "Reset to {value}",
  "row.resetChoice": "{value} (reset)",
  "sr.optimal": "Already at the recommended value: ",
  "sr.currently": "Currently ",
  "sr.recommendedIs": ", recommended value is ",
  // Advisory findings: the measured numbers, then the one move (lib/finding.ts)
  "finding.linkSpeed.below":
    "Link running at {linked}; the adapter supports {ceiling}.",
  "finding.linkSpeed.atCeiling":
    "Link running at {linked}, the adapter's maximum.",
  "finding.linkSpeed.adviceCable":
    "Use a {cable} or better cable, and check the router or switch port also does {ceiling}.",
  "finding.linkSpeed.adviceFarEnd":
    "Check the cable and that the router or switch port does {ceiling}.",
  "finding.wifi.onBand": "Signal {signal}% on the {band} GHz band{radio}.",
  "finding.wifi.bandUnknown": "Signal {signal}%; band not reported{radio}.",
  "finding.wifi.adviceSignal":
    "Move closer to the router or clear what stands between; a cable beats any radio.",
  "finding.wifi.adviceBand":
    "Join the router's 5 GHz or 6 GHz network; 2.4 GHz is slower and more crowded.",
  "finding.wifiSecurity.legacyCipher":
    "{auth} with the {cipher} cipher: the radio is held to 802.11g speeds.",
  "finding.wifiSecurity.wpa3Available":
    "{auth} with {cipher}; this adapter and the router both support WPA3.",
  "finding.wifiSecurity.good": "{auth} with {cipher}.",
  "finding.wifiSecurity.adviceCipher":
    "In the router, set the Wi-Fi security to WPA2 or WPA3 with AES; then forget this network in Windows and reconnect.",
  "finding.wifiSecurity.adviceWpa3":
    "Forget this network in Windows and reconnect, so the profile is created as WPA3. Speed stays the same; the password becomes far harder to crack.",
  "finding.thermal.zoneReads": "the thermal zone reads {celsius}°C",
  "finding.thermal.noReading": "no temperature was reported",
  "finding.thermal.notThrottling":
    "Not thermally throttled right now; {reading}.",
  "finding.thermal.throttling":
    "The firmware is holding clocks down to stay cool; {reading}.",
  "finding.thermal.advice":
    "Clear dust from the heatsinks and fans, and replace thermal paste older than three years.",
  "finding.powerDcRail.drift":
    "On battery this reads {dc}; Windows' own battery value is {stock}.",
  "finding.powerDcRail.advice":
    "fpstune tunes the plugged-in value only; applying puts the battery value back to Windows' own.",
  "finding.startupApps.none": "No third-party app starts with Windows.",
  "finding.startupApps.one": "1 app starts with Windows: {names}.",
  "finding.startupApps.many": "{count} apps start with Windows: {names}.",
  "finding.startupApps.more": "{names} and {rest} more",
  "finding.startupApps.advice":
    "Turn off the ones you don't need in Task Manager > Startup apps; security software is not listed.",
  "finding.displayMode.native": "Running at its native {width}×{height} @ {hz} Hz.",
  "finding.displayMode.lowRefresh":
    "Running at {hz} Hz; this panel can show {max} Hz. At {max} Hz each frame stays on screen {newMs} ms instead of {oldMs} ms: smoother motion and less input delay.",
  "finding.displayMode.lowResolution":
    "Running at {width}×{height}; the panel's native resolution is {nativeWidth}×{nativeHeight}. Below native, Windows scales the image and it looks soft.",
  "finding.displayMode.secondary":
    "Secondary monitor, so optional: the game's frame rate does not depend on it.",
  "finding.displayMode.advice":
    "Applying sets the native mode; it goes back on its own after 15 seconds unless you keep it.",
  // Advisory values, in words
  "choice.native": "Native",
  "choice.not_native": "Below native",
  "choice.at_capability": "At the adapter's maximum",
  "choice.below_capability": "Below the adapter's maximum",
  "choice.good": "Good",
  "choice.weak_signal": "Weak signal",
  "choice.on_2_4ghz": "On 2.4 GHz",
  "choice.legacy_cipher": "Legacy cipher",
  "choice.wpa3_available": "WPA3 available",
  "choice.not_throttling": "Not throttling",
  "choice.throttling": "Throttling",
  "choice.none_at_startup": "None at startup",
  "choice.apps_at_startup": "Apps at startup",
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
  // The same card, once maintenance that is overdue is in it: a TRIM run
  // reclaims nothing, so the cleanup-only heading would misname its own rows.
  "home.cleanupUpkeepTitle": "Disk cleanup and upkeep",
  "home.measuringReclaim": "Measuring what can be reclaimed…",
  "home.nothingToReclaim": "Nothing to reclaim right now.",
  "home.rowMeasuring": "— measuring what can be reclaimed…",
  "home.advisories": "Needs your attention",
  "home.advisoriesHint": "findings fpstune can detect but only you can change",
  "home.advisoriesClear": "Checked, nothing to change",
  "home.advisoriesClearHint":
    "hardware fpstune checked and found already correct",
  "home.whatToDo": "What you can do:",
  "home.advisoriesUnread": "Could not be checked",
  "home.advisoriesUnreadHint":
    "these say nothing about this machine either way",
  "home.advisoryUnreadReason": "Nothing was read: {reason}",
  "home.advisoryUnreadNeedsAdmin":
    "Nothing was read. fpstune is not running as Administrator, which several checks need.",
  "home.advisoryUnreadNoReason":
    "Nothing was read, so there is no finding here to act on.",
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
    "no frame rate measured yet — open Benchmarks to run the test scene",
  "home.sceneLabel": "Test scene, at this display's resolution",
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
  "run.percent": "{value}%",
  "run.queued": "queued",
  "run.skipped": "Not applicable",
  "run.elapsed": "{seconds}s elapsed",
  "run.showOutput": "show output",
  "run.hideOutput": "hide output",
  "run.commandLabel": "Command being run",
  "run.stepProgress": "Progress of {name}",
  "run.noOutputYet": "No output yet.",
  "cleanup.calculating": "Calculating…",
  "cleanup.freed": "Freed {amount}",
  "cleanup.failed": "Failed",
  "cleanup.done": "Done",
  "cleanup.serviceDown":
    "Service not running and could not be started. Start it, then reopen this tab.",
  "cleanup.unavailable": "Unavailable",
  // The readings `maintenance:ssd_retrim` reports. Named for TRIM because
  // that is what the reading is of: a second action answering `overdue|` would
  // bring its own copy rather than borrow this.
  "cleanup.trimOverdueNever": "TRIM overdue: never run",
  "cleanup.trimOverdueDays": "TRIM overdue: {days} days ago",
  "cleanup.trimLastDays": "Last TRIM: {days} days ago",
  // Under a day is what the backend rounds to 0, and "0 days ago" reads as
  // nonsense on the row the user is watching finish.
  "cleanup.trimLastUnderDay": "Last TRIM: less than a day ago",
  "cleanup.dismWarning":
    "Takes 5-15 minutes. Cannot uninstall updates removed by ResetBase. Reported size is reclaimable component store — actual free disk space may only appear after a reboot.",
  "cleanup.dockerShutdownWarning":
    "Shuts down Docker Desktop and all WSL distributions to compact the virtual disk and return real disk space. Can take several minutes; save your work first.",
  "cleanup.wslWarning":
    'Runs "wsl --shutdown" first, immediately closing all running WSL distributions and Docker Desktop (WSL backend). Save your work before running. Reported size is the current disk footprint, not the exact reclaimable amount.',
  "cleanup.measuringMore": "Measuring {count} more…",
  "cleanup.measuringFootnote":
    "Anything not listed above once this finishes has nothing to reclaim, or its software is not installed.",
  "cleanup.runCleanup": "Run Cleanup",
  "cleanup.runCleanupCount": "Run Cleanup ({count})",
  "maintenance.title": "System Maintenance",
  "maintenance.description": "Repair and troubleshoot Windows system issues.",
  "maintenance.running": "Running...",
  "maintenance.dismHealthWarning":
    "May require internet connection to download repair files.",
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
  "toolbar.stop": "Stop",

  // Hardware surfaces
  "hw.title": "Hardware",
  "hw.admin": "Admin",
  "hw.notAdmin": "Not Admin",
  "hw.cpu": "CPU",
  "hw.memory": "Memory",
  "hw.gpu": "GPU",
  "hw.displays": "Displays",
  "hw.buses": "USB & PCIe",
  "hw.storage": "Storage",
  "hw.network": "Network",
  "hw.powerPlan": "Power plan",
  "hw.audioOutput": "Audio Output",
  "hw.audioInput": "Audio Input",
  "hw.loudnessEq": "Loudness EQ",
  "hw.loudnessNotSupported": "No Windows loudness EQ: this device's driver loads no Microsoft effects",
  "hw.loudnessNextStream": "Loudness EQ changed. Sound that is already playing changes when its app restarts.",
  "hw.audioDefault": "Default",
  "hw.notDetected": "Not detected",
  "hw.copy": "Copy to clipboard",
  "devices.toFix": "{count} to fix",
  "devices.allIdeal": "All {count} ideal",
  "devices.needYou": "{count} need you",
  "devices.reading": "Reading tweaks…",
  "devices.advisoryHint":
    "fpstune cannot change these — each row says where to.",

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
  "storage.trimUnknown": "TRIM state could not be read",
  "storage.running": "{action} running…",

  // Time distance (formatAge)
  "age.justNow": "just now",
  "age.minutes": "{count} min ago",
  "age.hours": "{count} h ago",
  "age.days": "{count} d ago",

  // Headroom panel
  "headroom.title": "What this machine reaches",
  "headroom.subtitle":
    "A fixed test scene, rendered at this display's own resolution and measured against what the display could show. This is what decides whether there are frames spare to spend on image quality.",
  "headroom.measureNow": "Measure now",
  "headroom.measuring": "Measuring…",
  "headroom.startFailed": "The measurement could not be started.",
  "headroom.readingLast": "Reading the last result…",
  "headroom.needsScene":
    "Nothing has been measured yet. fpstune renders a fixed test scene when the machine is idle, so no game has to be running — or press Measure now, which takes about a minute.",
  "headroom.needsDownload":
    "The test scene is Unigine Superposition Basic, a 1.3 GB one-time download. fpstune never starts it on its own.",
  "headroom.installScene": "Install the scene (1.3 GB download)",
  "headroom.installing": "Installing the scene — this can take about a minute…",
  "headroom.installStartFailed": "The scene could not be installed.",
  "headroom.installFailed": "The scene could not be installed: {reason}",
  "headroom.onePercentLow": "({value} at the 1% low)",
  "headroom.againstTarget": "against this panel's {target} fps target",
  "headroom.measuredAgo": "Measured {age}",
  "headroom.renderedAt": "Rendered at {width}×{height}, this display's own resolution",
  "headroom.gaugeLabel":
    "Measured frame rate against the display's {target} fps target",
  "headroom.tierMet": "At its ceiling",
  "headroom.tierMetMeaning":
    "This machine is reaching what the display can show, so there are frames spare to spend on image quality.",
  "headroom.tierNear": "Close",
  "headroom.tierNearMeaning":
    "Nearly there. Small savings finish the job; anything that costs frames does not.",
  "headroom.tierShort": "Short",
  "headroom.tierShortMeaning":
    "Meaningfully under what the display can show. Decoration is worth spending; anything the player needs to see is not.",
  "headroom.tierCritical": "Far short",
  "headroom.tierCriticalMeaning":
    "Under half of what the display can show. Everything that is not information is worth spending, and a sharper image is not on offer.",
  "headroom.tierUnknown": "Not measured",
  "headroom.tierUnknownMeaning":
    "Nothing has been measured on this machine yet, and silence is not evidence — so nothing that costs frames will be recommended.",
  "headroom.gpuBound": "GPU-bound — graphics settings are where the frames are",
  "headroom.cpuBound": "CPU-bound — graphics settings will not move this much",
  "headroom.bothBound":
    "Both sides saturated — graphics settings alone will not close the gap",
  "headroom.presentMode": "Present mode: {mode}",

  // Benchmarks tab
  "bench.measure": "Measure",
  "bench.verifyClaims": "Verify claims",

  // Measure (suite) panel
  "suite.loading": "Loading the instrument list…",
  "suite.title": "Measure what changed",
  "suite.baselineTaken":
    "Baseline taken. Apply the tweaks you want, then press again — the two runs are compared for you.",
  "suite.takesBaseline":
    "Takes a baseline of this machine. Nothing is changed and nothing is written.",
  "suite.measureAgain": "Measure again and compare",
  "suite.measureThis": "Measure this machine",
  "suite.startOver": "Start over",
  "suite.selectionSummary":
    "{selected} of {total} instruments · {repeats} repeats",
  "suite.before": "Before",
  "suite.after": "After",
  "suite.notMeasuredYet": "Not measured yet",
  "suite.whichInstruments": "Which instruments, and how many repeats",
  "suite.notInRunAll": "(not in \u201crun all\u201d)",
  "suite.measuringBench": "Measuring {bench}…",
  "suite.startingRun": "Starting the {label} run…",
  "suite.minRepeats": "{min} or more — a single reading has no noise floor",
  "suite.notCompared": "Not compared",
  "suite.metric": "Metric",
  "suite.change": "Change",
  "suite.verdict": "Verdict",
  "suite.withinNoise": "within noise (±{noise}{unit})",
  "suite.deltaBarLabel":
    "{metric}: {pct}% change relative to the largest in this group",
  "suite.otherMeasurements": "Other measurements",
  "suiteCat.latency": "Latency",
  "suiteCat.fps": "Frame rate",
  "suiteCat.thermal": "Heat & wear",
  "suiteCat.network": "Network",
  "suiteCat.resources": "Memory & CPU",
  "suiteCat.storage": "Storage",

  // Verify panel
  "verify.title": "Verify a claim",
  "verify.selectFirst":
    "Select the settings you are about to change, on the Settings tab. A round is only meaningful about settings it knows changed — so this asks which ones rather than guessing from what is applied.",
  "verify.selectedSummary":
    "{count} selected. Measure, apply them, measure again, and this judges what the settings claimed against what the machine did.",
  "verify.couldShow": "What this could show",
  "verify.readingClaims": "Reading the claims…",
  "verify.youWouldNeed": "You would need: ",
  "verify.gapsTitle": "nothing here can check yet, and why",
  "verify.unmeasurableTitle": "no measurement settles — real claims, not gaps",
  "verify.readings": "Readings",
  "verify.noMeasurements":
    "No measurements yet. Take a baseline on the Measure tab, apply these settings, and measure again — this judges the claims against that same pair rather than asking for a second one.",
  "verify.fromSuite":
    "From the measurement suite: {before} readings before, {after} after, across {metrics} metrics.",
  "verify.fromSuiteOne":
    "From the measurement suite: 1 reading before, {after} after, across {metrics} metrics.",
  "verify.fewReadings":
    "Fewer than {wanted} readings a side. Two runs of the same measurement on an idle machine differ, and without knowing by how much, a small change cannot be told from nothing happening — raise the repeat count on the Measure tab.",
  "verify.enoughReadings":
    "Enough readings on both sides for the noise floor to mean something.",
  "verify.judge": "Judge",
  "verify.judgeClaims": "Judge these claims",
  "verify.needsBothSides":
    "Needs a reading on each side, and a setting selected. One side of a pair is not a small result, it is no result.",
  "verify.claimedLine": "claimed {claimed} for {metric} — ",
  "verify.changeBarLabel": "Measured change: {value} {unit}",
  "verify.noiseBarLabel":
    "This machine's own variation (noise floor): {value} {unit}",
  "verify.statusVerified": "Verified",
  "verify.statusContradicted": "Contradicted",
  "verify.statusNoise": "Lost in the noise",
  "verify.statusUnmeasured": "Not measured",
  "verify.statusUnattributable": "Not attributable",

  // Activity log
  "activity.title": "Activity Log",
  "activity.open": "Open activity log",
  "activity.close": "Close activity log",

  // Software Tweaks tab

  // Game Tweaks tab
  "games.searchPlaceholder": "Search game settings...",
  "games.searchLabel": "Search game settings",
  "games.filterGame": "Filter by game",
  "games.allGames": "All games",
  "games.reading": "Reading your game configs…",
  "games.noMatch": "No game setting matches that search.",
  "games.noneFound":
    "No supported game config was found on this machine. fpstune reads a game's config only where the game is installed.",

  // Setting tooltip
  "tooltip.current": "Current:",
  "tooltip.recommended": "Recommended:",
  "tooltip.effect": "Effect:",
  "tooltip.howToChange": "How to change:",
  "tooltip.proven": "Proven",
  "tooltip.experimental": "Experimental",
  "tooltip.likely": "Likely",
  "tooltip.ariaInfo": "Information about {name}",
  "tooltip.provenDetail": "Proven: 3+ independent sources",
  "tooltip.experimentalDetail":
    "Experimental: safe but unproven on modern systems",
  "tooltip.monitorOnly":
    "FPSTune cannot apply this automatically — monitor only.",
  "tooltip.sources": "Sources:",
  "tooltip.requiresRestart": "Requires system restart",

  // What fpstune changed, measured (the benchmark ledger)
  "ledger.homeTitle": "What fpstune changed, measured",
  "ledger.homeHint": "One area, one instrument. Never a sum of the two.",
  "ledger.panelTitle": "Measured on this machine",
  "ledger.panelHint": "Kept on disk, so a reload does not lose the baseline.",
  "ledger.area": "Area",
  "ledger.instrument": "Instrument",
  "ledger.before": "Before",
  "ledger.after": "After",
  "ledger.change": "Change",
  "ledger.verdict": "Verdict",
  "ledger.improved": "Improved",
  "ledger.worse": "Worse",
  "ledger.changed": "Changed",
  "ledger.withinNoise": "Within this machine's own variation of {noise}{unit}, so nothing can be concluded either way",
  "ledger.withinNoiseShort": "Within the machine's own variation",
  "ledger.noise": "noise {noise}{unit}",
  "ledger.noiseUnknown": "noise floor unknown",
  "ledger.samples": "{before} and {after} readings",
  "ledger.loading": "Reading what this machine has measured…",
  "ledger.unreachable": "The measurement ledger could not be read.",
  "ledger.noAreas": "No area has been reported yet.",
  "ledger.triggerBaseline": "Baseline",
  "ledger.triggerAfter": "After your changes",
  "ledger.triggerManual": "Measurement",
  "ledger.jobRunning": "{what} running: step {step}/{total} — {bench}",
  "ledger.jobQueued": "{what} queued — waiting for the machine to be idle",
  "ledger.jobFailed": "{what} could not finish; fpstune will try it again.",
  "ledger.jobIdle": "Nothing is being measured right now.",
  "ledger.bulkPending": "Tweaks were applied since the last measurement — fpstune will measure again once the machine is idle.",
  "ledger.baselineRun": "Baseline: {summary} ({age})",
  "ledger.afterRun": "After: {summary} ({age})",
  "ledger.noRunYet": "Nothing has been measured on this machine yet.",
  "ledger.measureNow": "Measure now",
  "ledger.measureNowHint": "Queues a run; fpstune measures it once the machine is idle and no game is running.",
  "ledger.queued": "Queued.",
  "ledger.alreadyRunning": "A measurement is already in flight.",
  "ledger.queueFailed": "The measurement could not be queued.",

  // Notifications
  "toast.errorsRegion": "Errors and warnings",
  "toast.region": "Notifications",
  "toast.error": "Error",
  "toast.warning": "Warning",
  "toast.success": "Success",
  "toast.info": "Information",
  // Scope actions: one button group for a row's group, a device, a page or a selection
  "actions.apply": "Apply ({count})",
  "actions.undo": "Undo ({count})",
  "actions.reset": "Windows default ({count})",
  "actions.applyShort": "Apply",
  "actions.undoShort": "Undo",
  "actions.resetShort": "Windows default",
  "actions.aria.apply": "Apply {count} tweaks: {name}",
  "actions.aria.undo": "Undo {count} tweaks: {name}",
  "actions.aria.reset": "Return {count} settings to the Windows default: {name}",
  "actions.confirm.apply": "Apply {count} tweaks on {name}?",
  "actions.confirm.undo": "{count} settings will return to what this machine held before fpstune.",
  "actions.confirm.reset": "{count} settings will return to Windows defaults.",
  "actions.confirmBody.apply": "Each row shows its own result, and every change can be undone from the same row.",
  "actions.confirmBody.undo": "Each setting gets back the value fpstune recorded the first time it read this machine.",
  "actions.confirmBody.reset": "Every setting that differs from what Windows ships is put back to it. Each row shows its own result.",
  "settings.search": "Search settings",
  "settings.searchPlaceholder": "Search settings...",
  "settings.filterByCategory": "Filter by category",
  "settings.allCategories": "All",
  "settings.groupCount": "{toFix} to fix / {total} total",
  // Needs / ideal bands
  "bands.needs": "Needs action",
  "bands.ideal": "Ideal",
  "bands.nothingToDo": "Nothing to do here.",
  "bands.showIdeal": "Show {count} already ideal",
  "bands.hideIdeal": "Hide {count} already ideal",
} as const;

export type MessageKey = keyof typeof en;

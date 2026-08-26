"""System setting definitions.

Contains settings for memory, services, cleanup, and maintenance.
These are typically one-time actions or service toggles.
"""

from __future__ import annotations

from fpstune.settings.base import (
    MASK,
    UNMAPPED,
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)

# =============================================================================
# Memory Settings
# =============================================================================

MEMORY_PURGE_STANDBY = SettingExecutor(
    id="memory:purge_standby",
    category=SettingCategory.MAINTENANCE,
    display_name="Purge Standby List",
    description="Clear cached memory. Recommended for systems with <16GB RAM.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,  # Only purge when needed
    requires_reboot=False,
    is_action=True,  # One-time action
    current_impact="Current: Standby memory cached for faster app access",
    recommended_impact="Purge: Clears cached memory → frees RAM for games",
    scope=SettingScope.COMPLETE,  # Optional action
    category_order=20,  # Memory action
    effect="Clears cached memory to free RAM for games on low-memory systems",
    impact_scores={"ram_freed": "1-4GB", "stability": "high"},
    # Action-type settings return boolean for readiness
    detect_type=DetectType.POWERSHELL,
    detect_command="memory_status",
    detect_args={},
    value_map={"True": True, "False": False},  # PowerShell bool -> Python bool
    apply_type=DetectType.POWERSHELL,
    apply_command="purge_standby",
    apply_args={},
    apply_value_map={},
)

# =============================================================================
# Services Settings
# =============================================================================

SERVICE_SYSMAIN = SettingExecutor(
    id="services:SysMain",
    category=SettingCategory.SYSTEM,
    display_name="SysMain (Superfetch)",
    description="Prefetches apps into memory + manages Memory Compression. Disable on SSD systems.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=["https://www.xda-developers.com/i-make-this-one-change-to-make-windows-faster/"],
    current_impact="Enabled: Prefetches apps into memory → extra disk I/O",
    recommended_impact="Disabled: No prefetching → reduced disk I/O on SSD systems",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for SSD systems
    category_order=1,  # Primary service for SSD
    effect="Disables app prefetching to reduce disk I/O on SSD systems",
    impact_scores={"ram_saved": "50-150MB", "latency_ms": 0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'SysMain' -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "SysMain"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "SysMain"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_DIAGTRACK = SettingExecutor(
    id="services:DiagTrack",
    category=SettingCategory.SYSTEM,
    display_name="Connected User Experiences and Telemetry",
    description="Collects and sends diagnostic data to Microsoft.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://www.xda-developers.com/i-disabled-these-5-windows-11-background-services-and-saw-zero-downsides/"
    ],
    current_impact="Enabled: Collects and sends diagnostic data → background activity",
    recommended_impact="Disabled: No telemetry collection → less background activity",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=5,  # Telemetry service
    effect="Stops diagnostic data collection and transmission to Microsoft",
    impact_scores={"privacy": "improved", "cpu_usage": -0.3, "latency_ms": 0},
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'DiagTrack' -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "DiagTrack"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "DiagTrack"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_WSEARCH = SettingExecutor(
    id="services:WSearch",
    category=SettingCategory.SYSTEM,
    display_name="Windows Search",
    description="Indexes files for faster search. Disable to reduce disk I/O.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Indexes files for faster search → continuous disk I/O",
    recommended_impact="Disabled: No indexing → less disk I/O during gaming",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for disk I/O
    category_order=2,  # Disk I/O service
    effect="Stops file indexing to eliminate continuous disk I/O during gaming",
    impact_scores={"cpu_usage": -0.5, "fps": "0%", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'WSearch' -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "WSearch"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "WSearch"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_NVIDIA_TELEMETRY = SettingExecutor(
    id="services:NvTelemetryContainer",
    category=SettingCategory.SYSTEM,
    display_name="NVIDIA Telemetry",
    description="NVIDIA usage data collection. Disabling saves CPU/RAM.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://www.xda-developers.com/i-disabled-these-5-windows-11-background-services-and-saw-zero-downsides/"
    ],
    current_impact="Enabled: Collects and sends NVIDIA usage data → ~50MB RAM usage",
    recommended_impact="Disabled: No telemetry → ~50MB RAM saved",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=6,  # NVIDIA telemetry
    effect="Stops NVIDIA telemetry data collection to save RAM and CPU",
    impact_scores={
        "ram_saved": "10-30MB",
        "cpu_usage": -0.5,
        "privacy": "improved",
        "stability": "high",
    },
    applicable_conditions={"gpu_vendor": "nvidia"},  # Only show for NVIDIA GPUs
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'NvTelemetryContainer'"
    " -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "NvTelemetryContainer"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "NvTelemetryContainer"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_NAHIMIC = SettingExecutor(
    id="services:NahimicService",
    category=SettingCategory.SYSTEM,
    display_name="Nahimic Audio Service",
    description="Audio enhancement that can cause stutter. Safe to disable.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Audio enhancement active → may cause micro-stutters",
    recommended_impact="Disabled: No audio enhancement → no processing overhead",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=7,  # Audio enhancement service
    effect="Disables audio enhancement that can cause micro-stutters in games",
    impact_scores={"fps": "+0-5%", "latency_ms": -2, "cpu_usage": -2, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'NahimicService'"
    " -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "NahimicService"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "NahimicService"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_FAX = SettingExecutor(
    id="services:Fax",
    category=SettingCategory.SYSTEM,
    display_name="Fax Service",
    description="Manages fax transmission. Not needed on modern systems.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Fax service running in background → ~5MB RAM usage",
    recommended_impact="Disabled: Service stopped → ~5MB RAM saved",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=8,  # Legacy service
    effect="Stops unused legacy fax service to save RAM",
    impact_scores={"ram_saved": "5-10MB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'Fax' -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "Fax"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "Fax"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_ERROR_REPORTING = SettingExecutor(
    id="services:WerSvc",
    category=SettingCategory.SYSTEM,
    display_name="Windows Error Reporting",
    description="Sends crash reports to Microsoft. Safe to disable.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Sends crash data to Microsoft → ~10MB RAM usage",
    recommended_impact="Disabled: No crash reporting → ~10MB RAM saved",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=9,  # Error reporting
    effect="Stops Windows error reporting to save RAM and improve privacy",
    impact_scores={
        "ram_saved": "5-15MB",
        "cpu_usage": 0,
        "privacy": "improved",
        "stability": "high",
    },
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'WerSvc' -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "WerSvc"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "WerSvc"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_RETAIL_DEMO = SettingExecutor(
    id="services:RetailDemo",
    category=SettingCategory.SYSTEM,
    display_name="Retail Demo Service",
    description="Demo mode for retail stores. Not needed on personal computers.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Retail demo service running → unnecessary background activity",
    recommended_impact="Disabled: Service stopped → no demo overhead",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=10,  # Retail demo service
    effect="Stops unused retail demo service to reduce background activity",
    impact_scores={"ram_saved": "2-5MB", "cpu_usage": 0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'RetailDemo'"
    " -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "RetailDemo"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "RetailDemo"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_WAP_PUSH = SettingExecutor(
    id="services:dmwappushservice",
    category=SettingCategory.SYSTEM,
    display_name="WAP Push Message Routing",
    description="MDM/Intune device management push. ⚠️ Keep enabled if work/school managed!",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Receives MDM push commands → minor network/CPU usage",
    recommended_impact="Disabled: No MDM push → less background activity (safe for personal PCs)",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=10,  # WAP Push service
    effect="Stops MDM push service to reduce background network and CPU activity",
    impact_scores={
        "ram_saved": "2-5MB",
        "cpu_usage": 0,
        "privacy": "improved",
        "stability": "high",
    },
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'dmwappushservice'"
    " -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "dmwappushservice"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "dmwappushservice"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

# =============================================================================
# Xbox Services (with warning for Xbox Game Pass users)
# =============================================================================

SERVICE_XBOX_AUTH = SettingExecutor(
    id="services:XblAuthManager",
    category=SettingCategory.SYSTEM,
    display_name="Xbox Live Auth Manager",
    description="Xbox Live authentication. Required by Xbox Game Save. Keep enabled for Game Pass!",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",  # Keep enabled by default due to Xbox Game Pass popularity
    requires_reboot=False,
    current_impact="Enabled: Required for Xbox Live sign-in and Game Pass",
    recommended_impact="Disabled: Service stopped → ~10MB RAM saved (only if not using Xbox)",
    scope=SettingScope.COMPLETE,  # Optional for non-Xbox users
    category_order=11,  # Xbox service
    effect="Controls Xbox Live authentication service (required for Game Pass)",
    impact_scores={"ram_saved": "10-20MB", "cpu_usage": 0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'XblAuthManager'"
    " -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "XblAuthManager"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "XblAuthManager"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_XBOX_GAME_SAVE = SettingExecutor(
    id="services:XblGameSave",
    category=SettingCategory.SYSTEM,
    display_name="Xbox Live Game Save",
    description="Xbox cloud saves. ⚠️ Keep enabled if using Xbox Game Pass or Play Anywhere!",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Enabled: Syncs game saves to Xbox Live cloud",
    recommended_impact="Disabled: Service stopped → ~10MB RAM saved (only if not using Xbox)",
    scope=SettingScope.COMPLETE,  # Optional for non-Xbox users
    category_order=12,  # Xbox cloud saves
    effect="Controls Xbox cloud save sync (required for Game Pass saves)",
    impact_scores={"ram_saved": "5-15MB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'XblGameSave'"
    " -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "XblGameSave"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "XblGameSave"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_XBOX_NETWORKING = SettingExecutor(
    id="services:XboxNetApiSvc",
    category=SettingCategory.SYSTEM,
    display_name="Xbox Live Networking",
    description="Xbox multiplayer networking. Keep enabled if using "
    "Xbox Game Pass or Play Anywhere!",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Enabled: Handles Xbox Live multiplayer connections",
    recommended_impact="Disabled: Service stopped → ~10MB RAM saved (only if not using Xbox)",
    scope=SettingScope.COMPLETE,  # Optional for non-Xbox users
    category_order=13,  # Xbox networking
    effect="Controls Xbox multiplayer networking (required for Xbox online)",
    impact_scores={"ram_saved": "5-15MB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'XboxNetApiSvc'"
    " -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "XboxNetApiSvc"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "XboxNetApiSvc"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_XBOX_ACCESSORY = SettingExecutor(
    id="services:XboxGipSvc",
    category=SettingCategory.SYSTEM,
    display_name="Xbox Accessory Management",
    description="Xbox controller management. ⚠️ Keep enabled if using Xbox controllers!",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=False,
    current_impact="Enabled: Manages Xbox controllers and accessories",
    recommended_impact="Disabled: Service stopped → ~5MB RAM saved "
    "(only if not using Xbox controllers)",
    scope=SettingScope.COMPLETE,  # Optional for non-Xbox controller users
    category_order=14,  # Xbox controller
    effect="Controls Xbox controller management (required for Xbox controllers)",
    impact_scores={"ram_saved": "3-8MB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    # Use StartType (2=Automatic, 4=Disabled) instead of Status for reliable verification
    detect_command="$s = Get-Service -Name 'XboxGipSvc'"
    " -ErrorAction SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "XboxGipSvc"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "XboxGipSvc"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

# =============================================================================
# Background Apps Settings
# =============================================================================

BACKGROUND_APPS = SettingExecutor(
    id="services:background_apps",
    category=SettingCategory.SYSTEM,
    display_name="Background Apps",
    description="Allow apps to run in background. Disabling saves significant RAM.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Apps run and update in background → RAM/CPU usage",
    recommended_impact="Disabled: No background apps → ~500MB-1.2GB RAM saved",
    scope=SettingScope.RECOMMENDED,  # Noticeable benefit for RAM/CPU
    category_order=3,  # Background apps impact
    effect="Disables background app activity to save significant RAM and CPU",
    impact_scores={"ram_saved": "100-500MB", "cpu_usage": -1, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications",
        "name": "GlobalUserDisabled",
        "hive": "HKCU",
    },
    # 0 or None = background apps enabled, 1 = disabled
    value_map={1: "disabled", "1": "disabled", 0: "enabled", "0": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications",
        "name": "GlobalUserDisabled",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 1, "enabled": 0},
)

SERVICE_UCPD = SettingExecutor(
    id="services:UCPD",
    category=SettingCategory.SYSTEM,
    display_name="User Choice Protection Driver (UCPD)",
    description="Hidden Microsoft driver that blocks third-party changes to "
    "default app associations. Can interfere with some system tweaks.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=True,  # Kernel driver - change requires reboot to take effect
    current_impact="Enabled: Blocks registry changes to default browser/app settings",
    recommended_impact="Disabled: Full control over default app associations "
    "(takes effect after reboot)",
    scope=SettingScope.COMPLETE,
    category_order=16,
    effect="Disables UCPD kernel driver startup to allow full control "
    "over default app settings after reboot",
    impact_scores={"cpu_usage": 0, "system_control": "improved"},
    applicable_conditions={"is_windows_11": True},
    # Kernel drivers can't be stopped via service_toggle - use registry StartType directly
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Services\UCPD",
        "name": "Start",
        "hive": "HKLM",
    },
    # Service Start values: 0=Boot, 1=System, 2=Automatic, 3=Manual, 4=Disabled
    value_map={
        0: "enabled",
        "0": "enabled",
        1: "enabled",
        "1": "enabled",  # System (UCPD default - kernel driver)
        2: "enabled",
        "2": "enabled",
        3: "enabled",
        "3": "enabled",
        4: "disabled",
        "4": "disabled",
        None: "not_available",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SYSTEM\CurrentControlSet\Services\UCPD",
        "name": "Start",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 4, "enabled": 1},
)

# =============================================================================
# Telemetry Scheduled Tasks (Registry-based disable)
# =============================================================================

TELEMETRY_TASKS = SettingExecutor(
    id="services:telemetry_tasks",
    category=SettingCategory.SYSTEM,
    display_name="Telemetry Scheduled Tasks",
    description="Disables Windows telemetry scheduled tasks as a named compound. Bundles DiagTrack/CEIP/Customer Experience tasks that share one privacy concept.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://www.xda-developers.com/i-disabled-these-5-windows-11-background-services-and-saw-zero-downsides/"
    ],
    current_impact="Enabled: Telemetry tasks collect/send data → heavy CPU/disk usage",
    recommended_impact="Disabled: No telemetry collection → significantly less background activity",
    scope=SettingScope.COMPLETE,  # Minor improvement
    category_order=15,  # Telemetry tasks
    effect="Disables scheduled telemetry tasks to reduce CPU and disk usage",
    impact_scores={"cpu_usage": -0.5, "disk_io": "reduced", "privacy": "improved"},
    # Detection - check BOTH registry and at least one scheduled task state
    # This ensures we report actual state, not partial apply
    detect_type=DetectType.POWERSHELL,
    # ScheduledTask.State enum: 1=Disabled, 2=Queued, 3=Ready, 4=Running
    detect_command=(
        "$regVal = (Get-ItemProperty -Path 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Privacy' "
        "-Name 'TailoredExperiencesWithDiagnosticDataEnabled' -ErrorAction SilentlyContinue).TailoredExperiencesWithDiagnosticDataEnabled; "
        "$task = Get-ScheduledTask -TaskPath '\\Microsoft\\Windows\\Customer Experience Improvement Program\\' "
        "-TaskName 'Consolidator' -ErrorAction SilentlyContinue; "
        "$taskState = if ($task) { [int]$task.State } else { 3 }; "
        "if ($regVal -eq 0 -and $taskState -eq 1) { 'disabled' } "
        "elseif ($regVal -eq 1 -or $taskState -ge 2) { 'enabled' } "
        "else { 'enabled' }"
    ),
    detect_args={},
    value_map={},  # Direct pass-through
    apply_type=DetectType.POWERSHELL,
    apply_command="telemetry_tasks_toggle",
    apply_args={},
    apply_value_map={"disabled": "disable", "enabled": "enable"},
)

# =============================================================================
# Privacy Settings (Registry-based)
# =============================================================================

PRIVACY_ADVERTISING_ID = SettingExecutor(
    id="privacy:advertising_id",
    category=SettingCategory.SYSTEM,
    display_name="Advertising ID",
    description="Unique ID for targeted ads across apps. Disabling improves privacy.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Apps can track you with unique advertising ID",
    recommended_impact="Disabled: No cross-app ad tracking → better privacy",
    scope=SettingScope.COMPLETE,  # Privacy improvement
    category_order=16,  # After telemetry tasks
    effect="Disables unique advertising ID to prevent cross-app ad tracking",
    impact_scores={"privacy": "improved", "cpu_usage": -0.1},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\AdvertisingInfo",
        "name": "Enabled",
        "hive": "HKLM",
    },
    # 1 or None = enabled, 0 = disabled
    value_map={0: "disabled", "0": "disabled", 1: "enabled", "1": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\AdvertisingInfo",
        "name": "Enabled",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0, "enabled": 1},
)

PRIVACY_ACTIVITY_HISTORY = SettingExecutor(
    id="privacy:activity_history",
    category=SettingCategory.SYSTEM,
    display_name="Activity History (Timeline)",
    description="Tracks app usage for Timeline feature. Disabling improves privacy and reduces sync.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Windows tracks and syncs your activity history",
    recommended_impact="Disabled: No activity tracking/sync → less background activity",
    scope=SettingScope.COMPLETE,  # Privacy + minor performance
    category_order=17,  # After advertising ID
    effect="Disables activity history tracking and cloud sync",
    impact_scores={"privacy": "improved", "cpu_usage": -0.1},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\System",
        "name": "EnableActivityFeed",
        "hive": "HKLM",
    },
    # 1 or None = enabled, 0 = disabled
    value_map={0: "disabled", "0": "disabled", 1: "enabled", "1": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\System",
        "name": "EnableActivityFeed",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0, "enabled": 1},
)

PRIVACY_CONSUMER_FEATURES = SettingExecutor(
    id="privacy:consumer_features",
    category=SettingCategory.SYSTEM,
    display_name="Windows Consumer Features",
    description="Suggestions, tips, and promoted apps in Start menu. Disabling reduces clutter.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Windows shows suggestions and promoted apps",
    recommended_impact="Disabled: No suggestions/promoted apps → cleaner experience",
    scope=SettingScope.COMPLETE,  # UX improvement
    category_order=18,  # After activity history
    effect="Disables Start menu suggestions and promoted app installations",
    impact_scores={"privacy": "improved", "ux": "cleaner", "cpu_usage": -0.1},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\CloudContent",
        "name": "DisableWindowsConsumerFeatures",
        "hive": "HKLM",
    },
    # 0 or None = consumer features enabled, 1 = disabled
    value_map={1: "disabled", "1": "disabled", 0: "enabled", "0": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\CloudContent",
        "name": "DisableWindowsConsumerFeatures",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 1, "enabled": 0},
)

PRIVACY_EDGE_TELEMETRY = SettingExecutor(
    id="privacy:edge_telemetry",
    category=SettingCategory.SYSTEM,
    display_name="Microsoft Edge Telemetry",
    description="Edge browser diagnostic data collection. Disabling improves privacy.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Edge sends browsing diagnostics to Microsoft",
    recommended_impact="Disabled: No Edge telemetry → better privacy",
    scope=SettingScope.COMPLETE,  # Privacy improvement
    category_order=19,  # After consumer features
    effect="Disables Microsoft Edge diagnostic data collection",
    impact_scores={"privacy": "improved", "ram_saved": "10-50MB", "cpu_usage": -0.2},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Edge",
        "name": "DiagnosticData",
        "hive": "HKLM",
    },
    # 0 = disabled, 1-3 or None = enabled (DiagnosticData can be 0-3)
    value_map={
        0: "disabled",
        "0": "disabled",
        1: "enabled",
        "1": "enabled",
        2: "enabled",
        "2": "enabled",
        3: "enabled",
        "3": "enabled",
        None: "enabled",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Edge",
        "name": "DiagnosticData",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0, "enabled": 2},
)

PRIVACY_CORTANA = SettingExecutor(
    id="privacy:cortana",
    category=SettingCategory.SYSTEM,
    display_name="Cortana",
    description="Microsoft's voice assistant. Deprecated in Win11 but still collects data if enabled.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Cortana may run in background → collects voice/search data",
    recommended_impact="Disabled: No Cortana background activity → better privacy",
    scope=SettingScope.COMPLETE,  # Privacy improvement
    category_order=20,  # After Edge telemetry
    effect="Disables Cortana to prevent background voice and search data collection",
    impact_scores={"privacy": "improved", "ram_saved": "20-50MB", "cpu_usage": -0.1},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\Windows Search",
        "name": "AllowCortana",
        "hive": "HKLM",
    },
    # 0 = disabled, 1 or None = enabled
    value_map={0: "disabled", "0": "disabled", 1: "enabled", "1": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\Windows Search",
        "name": "AllowCortana",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0, "enabled": 1},
)

PRIVACY_BING_SEARCH = SettingExecutor(
    id="privacy:bing_search",
    category=SettingCategory.SYSTEM,
    display_name="Bing Search in Start Menu",
    description="Web search results in Start menu. Disabling keeps searches local-only.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Search queries sent to Bing for web results",
    recommended_impact="Disabled: Local search only → faster and private",
    scope=SettingScope.COMPLETE,  # Privacy + minor performance
    category_order=21,  # After Cortana
    effect="Disables Bing web search in Start menu for local-only, faster search",
    # Bing in the Start menu affects Start-menu search, not game latency. The -12.0
    # was the impact_scores sweep's clipping cap, and the frontend sums latency_ms
    # into the figure shown on Home, so it credited a privacy tweak with input-lag
    # savings. The real gain is stated in recommended_impact.
    impact_scores={"privacy": "improved", "latency_ms": 0.0, "cpu_usage": -0.1},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Search",
        "name": "BingSearchEnabled",
        "hive": "HKCU",
    },
    # 0 = disabled, 1 or None = enabled
    value_map={0: "disabled", "0": "disabled", 1: "enabled", "1": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Search",
        "name": "BingSearchEnabled",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0, "enabled": 1},
)

PRIVACY_INPUT_PERSONALIZATION = SettingExecutor(
    id="privacy:input_personalization",
    category=SettingCategory.SYSTEM,
    display_name="Typing & Inking Personalization",
    description=(
        "Collects typing and handwriting data to train personalization models. "
        "Disabling blocks both text and ink collection for improved privacy."
    ),
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Windows collects typing and inking patterns for personalization",
    recommended_impact="Disabled: No typing/inking data collection → better privacy",
    scope=SettingScope.COMPLETE,  # Privacy improvement
    category_order=22,  # After Bing search
    effect="Disables typing and inking data collection for improved privacy",
    impact_scores={"privacy": "improved", "cpu_usage": -0.1},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$path = 'HKCU:\\SOFTWARE\\Microsoft\\InputPersonalization';"
        " $t = (Get-ItemProperty -Path $path -Name 'RestrictImplicitTextCollection'"
        " -EA SilentlyContinue).RestrictImplicitTextCollection;"
        " $i = (Get-ItemProperty -Path $path -Name 'RestrictImplicitInkCollection'"
        " -EA SilentlyContinue).RestrictImplicitInkCollection;"
        " if ($t -eq 1 -and $i -eq 1) { Write-Output 'disabled' }"
        " else { Write-Output 'enabled' }"
    ),
    value_map={"disabled": "disabled", "enabled": "enabled"},
    apply_type=DetectType.POWERSHELL,
    apply_command="input_personalization_toggle",
    apply_value_map={"disabled": "disable", "enabled": "enable"},
)

PRIVACY_ACCEPTED_POLICY = SettingExecutor(
    id="privacy:accepted_policy",
    category=SettingCategory.SYSTEM,
    display_name="Personalization Privacy Policy",
    description="Tracks acceptance of personalization privacy policy for speech/typing.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Personalization data collection accepted",
    recommended_impact="Disabled: Personalization policy not accepted → better privacy",
    scope=SettingScope.COMPLETE,  # Privacy improvement
    category_order=23,
    effect="Revokes personalization privacy policy acceptance",
    impact_scores={"privacy": "improved", "cpu_usage": 0},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Personalization\Settings",
        "name": "AcceptedPrivacyPolicy",
        "hive": "HKCU",
    },
    # 1 or None = accepted (enabled), 0 = not accepted (disabled)
    value_map={0: "disabled", "0": "disabled", 1: "enabled", "1": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Personalization\Settings",
        "name": "AcceptedPrivacyPolicy",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0, "enabled": 1},
)

PRIVACY_TILE_NOTIFICATIONS = SettingExecutor(
    id="privacy:tile_notifications",
    category=SettingCategory.SYSTEM,
    display_name="Live Tile Notifications (Win10)",
    description="Live Tiles in Start menu. Only affects Windows 10 (removed in Win11).",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Live Tiles fetch and display content → network activity",
    recommended_impact="Disabled: No tile updates → less network activity",
    scope=SettingScope.COMPLETE,  # Win10 only
    category_order=24,
    effect="Disables Live Tile content fetching to reduce network activity (Win10)",
    impact_scores={"privacy": "improved", "network_overhead": "reduced", "cpu_usage": -0.1},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\CurrentVersion\PushNotifications",
        "name": "NoTileApplicationNotification",
        "hive": "HKCU",
    },
    # 1 = disabled, 0 or None = enabled
    value_map={1: "disabled", "1": "disabled", 0: "enabled", "0": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\CurrentVersion\PushNotifications",
        "name": "NoTileApplicationNotification",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 1, "enabled": 0},
)

PRIVACY_ALLOW_TELEMETRY = SettingExecutor(
    id="privacy:allow_telemetry",
    category=SettingCategory.SYSTEM,
    display_name="Diagnostic Data Level (Policy)",
    description="System-wide telemetry policy. Enterprise=Off, Home/Pro=Basic minimum.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Full diagnostic data collection active",
    recommended_impact="Disabled: Minimum telemetry → Off on Enterprise, Basic on Home/Pro",
    scope=SettingScope.COMPLETE,  # Privacy improvement
    category_order=25,
    effect="Sets Windows telemetry to minimum allowed level for your edition",
    impact_scores={"privacy": "improved", "cpu_usage": -0.2},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\DataCollection",
        "name": "AllowTelemetry",
        "hive": "HKLM",
    },
    # 0 = disabled (minimum), 1-3 or None = various levels enabled
    value_map={
        0: "disabled",
        "0": "disabled",
        1: "enabled",
        "1": "enabled",
        2: "enabled",
        "2": "enabled",
        3: "enabled",
        "3": "enabled",
        None: "enabled",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\DataCollection",
        "name": "AllowTelemetry",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0, "enabled": 3},
)

PRIVACY_COPILOT = SettingExecutor(
    id="privacy:copilot",
    category=SettingCategory.SYSTEM,
    display_name="Windows Copilot",
    description="AI assistant in Windows 11. Disabling removes Copilot completely.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Copilot runs in background → may collect data",
    recommended_impact="Disabled: No Copilot → better privacy and less resource usage",
    scope=SettingScope.COMPLETE,  # Privacy + performance
    category_order=26,
    effect="Disables Windows Copilot AI assistant to save resources and improve privacy",
    impact_scores={"privacy": "improved", "ram_saved": "100-200MB", "cpu_usage": -0.3},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot",
        "name": "TurnOffWindowsCopilot",
        "hive": "HKCU",
    },
    # 1 = Copilot off (disabled setting), 0 or None = Copilot on (enabled setting)
    value_map={1: "disabled", "1": "disabled", 0: "enabled", "0": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot",
        "name": "TurnOffWindowsCopilot",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 1, "enabled": 0},
)

PRIVACY_WINDOWS_ADS = SettingExecutor(
    id="privacy:windows_ads",
    category=SettingCategory.SYSTEM,
    display_name="Windows Ads & Suggestions",
    description="Ads in File Explorer, Start menu, lock screen, and auto-installed apps.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Windows shows ads, suggestions, and auto-installs apps",
    recommended_impact="Disabled: No ads, no suggestions → no auto-installed apps",
    scope=SettingScope.RECOMMENDED,  # UX + privacy improvement
    category_order=27,
    effect="Disables Windows ads, suggestions, and automatic app installations",
    impact_scores={"privacy": "improved", "ux": "cleaner", "cpu_usage": -0.1},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$v = (Get-ItemProperty -Path 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\ContentDeliveryManager' "
        "-Name 'SilentInstalledAppsEnabled' -ErrorAction SilentlyContinue).SilentInstalledAppsEnabled; "
        "if ($null -eq $v) { 'enabled' } elseif ($v -eq 0) { 'disabled' } else { 'enabled' }"
    ),
    detect_args={},
    value_map={},  # Direct pass-through
    apply_type=DetectType.POWERSHELL,
    apply_command="windows_ads_toggle",
    apply_args={},
    apply_value_map={"disabled": "disable", "enabled": "enable"},
)

PRIVACY_WEB_SEARCH_POLICY = SettingExecutor(
    id="privacy:web_search_policy",
    category=SettingCategory.SYSTEM,
    display_name="Web Search in Start (Policy)",
    description="Policy-level block for web search in Start menu. Stronger than BingSearchEnabled.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Start menu searches the web via Bing",
    recommended_impact="Disabled: Local search only → no web queries",
    scope=SettingScope.COMPLETE,
    category_order=28,
    effect="Policy-level block for web search in Start menu (stronger than BingSearchEnabled)",
    impact_scores={"privacy": "improved", "latency_ms": 0, "fps": "0%"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\Windows Search",
        "name": "DisableWebSearch",
        "hive": "HKLM",
    },
    value_map={1: "disabled", "1": "disabled", 0: "enabled", "0": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\Windows Search",
        "name": "DisableWebSearch",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 1, "enabled": 0},
)

# =============================================================================
# Performance Settings
# =============================================================================

PERF_ACCESSIBILITY_POPUPS = SettingExecutor(
    id="perf:accessibility_popups",
    category=SettingCategory.SYSTEM,
    display_name="Accessibility Key Popups",
    description="Sticky Keys (Shift x5), Filter Keys, Toggle Keys popups. Annoying for gamers.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Pressing Shift 5 times shows Sticky Keys popup",
    recommended_impact="Disabled: No accessibility popups → uninterrupted gaming",
    scope=SettingScope.RECOMMENDED,
    category_order=32,
    effect="Disables Sticky Keys, Filter Keys, and Toggle Keys popups",
    impact_scores={"latency_ms": 0, "ux": "improved", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$v = (Get-ItemProperty -Path 'HKCU:\\Control Panel\\Accessibility\\StickyKeys' "
        "-Name 'Flags' -ErrorAction SilentlyContinue).Flags; "
        "if ($null -eq $v) { 'enabled' } elseif ($v -eq '506') { 'disabled' } else { 'enabled' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="accessibility_popups_toggle",
    apply_args={},
    apply_value_map={"disabled": "disable", "enabled": "enable"},
)

PERF_MOUSE_ACCELERATION = SettingExecutor(
    id="perf:mouse_acceleration",
    category=SettingCategory.SYSTEM,
    display_name="Mouse Acceleration (Enhance Pointer Precision)",
    description="Windows pointer acceleration. Disabling gives 1:1 mouse input for gaming.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Mouse movement is accelerated based on speed",
    recommended_impact="Disabled: Raw 1:1 mouse input → better for FPS games",
    scope=SettingScope.RECOMMENDED,
    category_order=33,
    effect="Disables pointer acceleration for raw 1:1 mouse input in FPS games",
    impact_scores={"latency_ms": 0, "input_precision": "improved"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$v = (Get-ItemProperty -Path 'HKCU:\\Control Panel\\Mouse' "
        "-Name 'MouseSpeed' -ErrorAction SilentlyContinue).MouseSpeed; "
        "if ($null -eq $v) { 'enabled' } elseif ($v -eq '0') { 'disabled' } else { 'enabled' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="mouse_acceleration_toggle",
    apply_args={},
    apply_value_map={"disabled": "disable", "enabled": "enable"},
)

PERF_FAST_STARTUP = SettingExecutor(
    id="perf:fast_startup",
    category=SettingCategory.SYSTEM,
    display_name="Fast Startup (Hybrid Boot)",
    description="Hybrid shutdown that saves kernel state. Can cause driver issues.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Windows uses hybrid shutdown → not a true restart",
    recommended_impact="Disabled: Full shutdown → cleaner restarts, fewer driver issues",
    scope=SettingScope.COMPLETE,
    category_order=34,
    effect="Disables hybrid boot for true shutdown and cleaner restarts",
    impact_scores={
        "latency_ms": 0,
        "driver_stability": "improved",
        "startup_speed": "slower",
        "stability": "high",
    },
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Control\Session Manager\Power",
        "name": "HiberbootEnabled",
        "hive": "HKLM",
    },
    value_map={0: "disabled", "0": "disabled", 1: "enabled", "1": "enabled", None: "enabled"},
    apply_type=DetectType.POWERSHELL,
    apply_command="fast_startup_toggle",
    apply_args={},
    apply_value_map={"disabled": "disable", "enabled": "enable"},
)

PERF_MENU_DELAY = SettingExecutor(
    id="perf:menu_delay",
    category=SettingCategory.SYSTEM,
    display_name="Menu Show Delay",
    description="Delay before menus appear. Lower = snappier UI.",
    value_type=SettingValueType.CHOICE,
    choices=("400ms", "50ms"),
    default_value="400ms",
    recommended_value="50ms",
    requires_reboot=False,
    current_impact="Default: 400ms delay before menus appear",
    recommended_impact="Fast: 50ms delay → snappier menus",
    scope=SettingScope.COMPLETE,
    category_order=35,
    effect="Reduces menu show delay from 400ms to 50ms for snappier UI",
    impact_scores={"ux": "improved", "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"Control Panel\Desktop",
        "name": "MenuShowDelay",
        "hive": "HKCU",
    },
    # Registry returns string values - handle all common cases
    value_map={"0": "50ms", "50": "50ms", "100": "50ms", "400": "400ms", None: "400ms"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"Control Panel\Desktop",
        "name": "MenuShowDelay",
        "hive": "HKCU",
        "type": "REG_SZ",
    },
    apply_value_map={"50ms": "50", "400ms": "400"},
)

# === SvcHost Split Threshold ===
# Windows splits services into separate svchost.exe processes when RAM < threshold.
# Setting to max (0xFFFFFFFF) combines all services into fewer processes.
# Benefit: ~100-300MB RAM saved, fewer context switches.
# Microsoft-supported setting, risk-free.
PERF_SVCHOST_SPLIT = SettingExecutor(
    id="perf:svchost_split_threshold",
    category=SettingCategory.SYSTEM,
    display_name="SvcHost Split Threshold",
    description="Combines Windows services into fewer processes. Saves ~100-300MB RAM.",
    value_type=SettingValueType.CHOICE,
    choices=("split", "combined"),
    default_value="split",
    recommended_value="combined",
    requires_reboot=True,
    current_impact="Split: Services in many svchost.exe processes",
    recommended_impact="Combined: Services merged → ~100-300MB RAM saved, fewer context switches",
    scope=SettingScope.RECOMMENDED,
    category_order=36,
    effect="Combines Windows services into fewer processes to save RAM and reduce overhead",
    impact_scores={"ram_saved": "50-150MB", "cpu_usage": -0.5, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Control",
        "name": "SvcHostSplitThresholdInKB",
        "hive": "HKLM",
    },
    # SvcHostSplitThresholdInKB is a threshold in KB, not an enum. 0xFFFFFFFF
    # means "no service ever gets its own process"; every other number is
    # whatever Windows sized to this machine's RAM at install, which is the
    # split state whatever the number happens to be. Listing only 0xFFFFFFFF
    # left a real 3774873 KB reading — a 3.6 GB machine's default — outside
    # `choices`, so the setting could never verify on any machine that had not
    # already been optimized.
    value_map={
        4294967295: "combined",
        "4294967295": "combined",
        None: "split",
        UNMAPPED: "split",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SYSTEM\CurrentControlSet\Control",
        "name": "SvcHostSplitThresholdInKB",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    # 0xFFFFFFFF = max threshold (combine all services)
    apply_value_map={"combined": 0xFFFFFFFF, "split": 380000},
)

# === Network Throttling Index ===
# Windows throttles network during multimedia playback to reduce jitter.
# Setting to 0xFFFFFFFF disables throttling completely.
# Benefit: No network throttling during gaming → more consistent ping.
PERF_NETWORK_THROTTLING = SettingExecutor(
    id="perf:network_throttling",
    category=SettingCategory.SYSTEM,
    display_name="Network Throttling (Multimedia)",
    description="Disables network throttling during multimedia/gaming. More consistent ping.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Removes the reserve Windows keeps for multimedia playback, so heavy network "
    "load and audio streaming now compete freely. On systems that also record or stream audio "
    "this can introduce crackling under load — the exact problem the throttle exists to prevent.",
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/procthread/multimedia-class-scheduler-service"
    ],
    current_impact="Enabled: Network limited to 10 packets/ms during multimedia",
    recommended_impact="Disabled: No network throttling → consistent ping during gaming",
    scope=SettingScope.RECOMMENDED,
    category_order=37,
    effect="Disables network packet throttling during gaming for consistent latency",
    impact_scores={"latency_ms": -2.0, "network_consistency": "improved", "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
        "name": "NetworkThrottlingIndex",
        "hive": "HKLM",
    },
    # 0xFFFFFFFF = disabled, 10 (default) or anything else = enabled
    value_map={
        4294967295: "disabled",
        "4294967295": "disabled",
        10: "enabled",
        "10": "enabled",
        None: "enabled",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile",
        "name": "NetworkThrottlingIndex",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0xFFFFFFFF, "enabled": 10},
)

# =============================================================================
# System Configuration Settings
# =============================================================================

SYSTEM_DRIVER_UPDATES_PROTECTION = SettingExecutor(
    id="system:driver_updates_protection",
    category=SettingCategory.SYSTEM,
    display_name="Driver Updates via Windows Update",
    description="Prevents Windows Update from silently replacing your manually installed GPU or device drivers with outdated generic versions.",
    value_type=SettingValueType.CHOICE,
    choices=("allowed", "blocked"),
    default_value="allowed",
    recommended_value="blocked",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows/deployment/update/exclude-drivers-windows-update"
    ],
    current_impact="Allowed: Windows Update can override your tuned GPU driver at any time",
    recommended_impact="Blocked: Windows Update skips driver updates → your chosen driver stays installed",
    scope=SettingScope.RECOMMENDED,
    category_order=30,
    effect="Prevents Windows Update from overriding manually installed GPU and device drivers",
    impact_scores={"fps": "+0-6%", "driver_stability": "high", "gpu_performance": "preserved"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate",
        "name": "ExcludeWUDriversInQualityUpdate",
        "hive": "HKLM",
    },
    value_map={1: "blocked", "1": "blocked", 0: "allowed", "0": "allowed", None: "allowed"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate",
        "name": "ExcludeWUDriversInQualityUpdate",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"blocked": 1, "allowed": 0},
)

SYSTEM_DELIVERY_OPTIMIZATION = SettingExecutor(
    id="system:delivery_optimization",
    category=SettingCategory.SYSTEM,
    display_name="Delivery Optimization (P2P Updates)",
    description="Windows Update P2P sharing uploads updates to other PCs over the internet, consuming upload bandwidth during gaming.",
    value_type=SettingValueType.CHOICE,
    choices=("internet", "lan_only", "off"),
    default_value="internet",
    recommended_value="off",
    requires_reboot=False,
    evidence_level="likely",
    sources=[
        "https://learn.microsoft.com/en-us/windows/deployment/do/waas-delivery-optimization-reference"
    ],
    current_impact="Internet: Shares Windows updates to strangers over internet → background upload",
    recommended_impact="Off: HTTP download only, no P2P → full bandwidth for gaming",
    scope=SettingScope.RECOMMENDED,
    category_order=31,
    effect="Disables P2P update sharing to preserve upload bandwidth during gaming",
    impact_scores={"latency_ms": -1.5, "bandwidth": "preserved", "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization",
        "name": "DODownloadMode",
        "hive": "HKLM",
    },
    value_map={
        0: "off",
        "0": "off",
        1: "lan_only",
        "1": "lan_only",
        2: "internet",
        "2": "internet",
        3: "internet",
        "3": "internet",
        None: "internet",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization",
        "name": "DODownloadMode",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"off": 0, "lan_only": 1, "internet": 3},
)

SYSTEM_DO_BACKGROUND_BANDWIDTH = SettingExecutor(
    id="system:delivery_optimization_bandwidth",
    category=SettingCategory.SYSTEM,
    display_name="Windows Update Background Bandwidth Cap",
    description="Caps what Windows Update may consume for background downloads to 20% of the "
    "link. On an asymmetric connection an uncapped update download fills the queue and every "
    "other packet, including game traffic, waits behind it.",
    value_type=SettingValueType.CHOICE,
    choices=("unlimited", "capped"),
    default_value="unlimited",
    recommended_value="capped",
    requires_reboot=False,
    evidence_level="likely",
    sources=[
        "https://learn.microsoft.com/en-us/windows/deployment/do/waas-delivery-optimization-reference"
    ],
    current_impact="Unlimited: Update downloads fill the link → queue builds, latency spikes",
    recommended_impact="Capped (20%): Updates leave headroom → game packets are not queued behind them",
    scope=SettingScope.RECOMMENDED,
    category_order=32,
    effect="Caps Windows Update background downloads at 20% of available bandwidth",
    impact_scores={"latency_ms": -20, "jitter_ms": "reduced"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization",
        "name": "DOPercentageMaxBackgroundBandwidth",
        "hive": "HKLM",
    },
    value_map={20: "capped", "20": "capped", 0: "unlimited", "0": "unlimited", None: "unlimited"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization",
        "name": "DOPercentageMaxBackgroundBandwidth",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"capped": 20, "unlimited": 0},
)

SYSTEM_ONEDRIVE_UPLOAD_LIMIT = SettingExecutor(
    id="system:onedrive_upload_limit",
    category=SettingCategory.SYSTEM,
    display_name="OneDrive Upload Rate Cap",
    description="Caps the OneDrive sync client to 30% of upload throughput. Home fibre is "
    "asymmetric, so a sync burst saturates the much smaller uplink and adds queueing delay to "
    "every packet leaving the machine, including game traffic.",
    value_type=SettingValueType.CHOICE,
    choices=("unlimited", "capped"),
    default_value="unlimited",
    recommended_value="capped",
    requires_reboot=False,
    evidence_level="likely",
    sources=[
        "https://learn.microsoft.com/en-us/sharepoint/use-group-policy",
    ],
    current_impact="Unlimited: A sync burst saturates the uplink → latency spikes for all traffic",
    recommended_impact="Capped (30%): Sync leaves uplink headroom → stable ping during transfers",
    scope=SettingScope.RECOMMENDED,
    category_order=33,
    effect="Caps the OneDrive sync client at 30% of upload throughput",
    impact_scores={"latency_ms": -30, "jitter_ms": "reduced"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\OneDrive",
        "name": "AutomaticUploadBandwidthPercentage",
        "hive": "HKLM",
    },
    value_map={30: "capped", "30": "capped", 0: "unlimited", "0": "unlimited", None: "unlimited"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\OneDrive",
        "name": "AutomaticUploadBandwidthPercentage",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"capped": 30, "unlimited": 0},
)

SYSTEM_WINDOWS_UPDATE_MODE = SettingExecutor(
    id="system:windows_update_mode",
    category=SettingCategory.SYSTEM,
    display_name="Windows Update Mode",
    description="Automatic updates trigger background downloads and CPU/disk usage during gaming. Notify-only mode lets you choose when to install.",
    value_type=SettingValueType.CHOICE,
    choices=("automatic", "notify_only"),
    default_value="automatic",
    recommended_value="notify_only",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Automatic: Windows downloads and installs updates silently → CPU/disk usage mid-game",
    recommended_impact="Notify only: No auto-download → full resources for gaming, you install when ready",
    scope=SettingScope.RECOMMENDED,
    category_order=32,
    effect="Prevents automatic update downloads to eliminate mid-game performance drops",
    impact_scores={"fps": "0%", "cpu_usage": -3, "stability": "improved"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU",
        "name": "AUOptions",
        "hive": "HKLM",
    },
    value_map={
        2: "notify_only",
        "2": "notify_only",
        3: "automatic",
        "3": "automatic",
        4: "automatic",
        "4": "automatic",
        5: "automatic",
        "5": "automatic",
        None: "automatic",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU",
        "name": "AUOptions",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"notify_only": 2, "automatic": 4},
)

SYSTEM_COINSTALLERS = SettingExecutor(
    id="system:coinstallers",
    category=SettingCategory.SYSTEM,
    display_name="Hardware Co-Installers",
    description="When plugging in a new device (mouse, headset, keyboard), co-installers auto-install vendor software like Razer Synapse or Logitech G Hub in the background.",
    value_type=SettingValueType.CHOICE,
    choices=("allowed", "blocked"),
    default_value="allowed",
    recommended_value="blocked",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://bogdan-patraucean.github.io/about/wintoys/"],
    current_impact="Allowed: Plugging in new device can trigger background software installation",
    recommended_impact="Blocked: New devices install driver only → no unwanted background software",
    scope=SettingScope.RECOMMENDED,
    category_order=33,
    effect="Blocks peripheral co-installers to prevent unwanted background software installations",
    impact_scores={"fps": "0%", "latency_ms": 0, "stability": "improved"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Device Installer",
        "name": "DisableCoInstallers",
        "hive": "HKLM",
    },
    value_map={1: "blocked", "1": "blocked", 0: "allowed", "0": "allowed", None: "allowed"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Device Installer",
        "name": "DisableCoInstallers",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"blocked": 1, "allowed": 0},
)

SYSTEM_WIDGETS = SettingExecutor(
    id="system:widgets",
    category=SettingCategory.SYSTEM,
    display_name="Windows Widgets",
    description="News and Interests panel on the taskbar. Runs a background WebView2/Edge process consuming RAM and CPU even when not visible.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Enabled: Background WebView2 process always running → ~50-150MB RAM",
    recommended_impact="Disabled: No widgets process → ~100MB RAM freed",
    scope=SettingScope.RECOMMENDED,
    category_order=34,
    applicable_conditions={"is_windows_11": True},
    effect="Disables Windows Widgets panel to free RAM and CPU used by background Edge/WebView2 process",
    impact_scores={
        "ram_saved": "50-150MB",
        "cpu_usage": -1,
        "latency_ms": 0,
        "stability": "improved",
    },
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Dsh",
        "name": "AllowNewsAndInterests",
        "hive": "HKLM",
    },
    # None = policy not set = widgets enabled by default
    value_map={1: "enabled", "1": "enabled", 0: "disabled", "0": "disabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Dsh",
        "name": "AllowNewsAndInterests",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

SYSTEM_FILE_EXPLORER_LAUNCH = SettingExecutor(
    id="system:file_explorer_launch",
    category=SettingCategory.SYSTEM,
    display_name="File Explorer Default View",
    description="Where File Explorer opens by default. 'This PC' shows drives immediately instead of cloud-connected Home/Quick Access.",
    value_type=SettingValueType.CHOICE,
    choices=("home", "this_pc"),
    default_value="home",
    recommended_value="this_pc",
    requires_reboot=False,
    current_impact="Home: Opens to Recent Files / Quick Access with synced cloud items",
    recommended_impact="This PC: Opens directly to drives → faster access, no cloud sync delay",
    scope=SettingScope.COMPLETE,
    category_order=35,
    effect="Sets File Explorer to open to 'This PC' instead of Home/Quick Access",
    impact_scores={"fps": "0%", "latency_ms": 0, "ux": "improved"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "name": "LaunchTo",
        "hive": "HKCU",
    },
    value_map={1: "this_pc", "1": "this_pc", 2: "home", "2": "home", None: "home"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "name": "LaunchTo",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"this_pc": 1, "home": 2},
)

# =============================================================================
# Hyper-V / Virtual Machine Platform
# =============================================================================

SYSTEM_HYPER_V = SettingExecutor(
    id="system:hyper_v",
    category=SettingCategory.SYSTEM,
    display_name="Hyper-V Hypervisor",
    description="Runs Windows as a virtual machine guest under the Hyper-V hypervisor. "
    "Causes 5-15% FPS loss from second-level address translation (SLAT) overhead.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="disabled",
    requires_reboot=True,
    evidence_level="proven",
    sources=[
        "https://www.howtogeek.com/these-windows-settings-are-hurting-your-game-fps/",
    ],
    current_impact="Enabled: Windows runs under hypervisor with 5-15% FPS overhead from SLAT",
    recommended_impact="Disabled: Native hardware access, no hypervisor overhead",
    scope=SettingScope.RECOMMENDED,
    category_order=51,
    effect="Disables Hyper-V hypervisor to remove SLAT overhead from gaming workloads",
    impact_scores={"fps_cpu_bound": "+3-8%", "fps_1_percent_low": "+2-5%", "latency_ms": -1},
    applicable_conditions={"requires_admin": True, "feature_absent": "docker"},
    detect_type=DetectType.POWERSHELL,
    # `Get-WindowsOptionalFeature -Online` needs elevation, and unelevated it
    # raises rather than answering. The old form swallowed that with
    # -ErrorAction SilentlyContinue, left $f null, and fell through to
    # 'disabled' — so a machine actually running Hyper-V reported it as off and
    # fpstune called the setting already optimal. "Could not read" is not
    # "not enabled"; it answers not_available, which detection turns into
    # is_applicable=False rather than a value.
    #
    # The try/catch is also what lets this share a batched session: a raise
    # inside the group's scriptblock costs the setting its batched result and
    # sends it back to its own process.
    detect_command=(
        "try { "
        "$f = Get-WindowsOptionalFeature -Online "
        "-FeatureName Microsoft-Hyper-V -ErrorAction Stop; "
        "if ($f.State -eq 'Enabled') { 'enabled' } else { 'disabled' } "
        "} catch { 'not_available' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="hyper_v_only_toggle",
    apply_args={},
    apply_value_map={"enabled": "enable", "disabled": "disable"},
)

SYSTEM_VM_PLATFORM = SettingExecutor(
    id="system:vm_platform",
    category=SettingCategory.SYSTEM,
    display_name="Virtual Machine Platform",
    description="Windows subsystem for Android apps and WSL2 virtualization. "
    "Disabling removes virtualization overhead when these features are not used.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="disabled",
    requires_reboot=True,
    evidence_level="proven",
    current_impact="Enabled: VirtualMachinePlatform active → small virtualization overhead",
    recommended_impact="Disabled: No VMP overhead → cleaner system when WSL2/Android not needed",
    scope=SettingScope.RECOMMENDED,
    category_order=51,
    effect="Disables VirtualMachinePlatform when WSL2 and Android apps are not in use",
    impact_scores={"fps_cpu_bound": "+0-2%", "latency_ms": -0.3},
    applicable_conditions={"requires_admin": True, "feature_absent": "docker"},
    detect_type=DetectType.POWERSHELL,
    # Same as Hyper-V above: unelevated this raises, and reporting 'disabled'
    # for "could not read" told the user a platform that was on was off.
    detect_command=(
        "try { "
        "$f = Get-WindowsOptionalFeature -Online "
        "-FeatureName VirtualMachinePlatform -ErrorAction Stop; "
        "if ($f.State -eq 'Enabled') { 'enabled' } else { 'disabled' } "
        "} catch { 'not_available' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="vm_platform_toggle",
    apply_args={},
    apply_value_map={"enabled": "enable", "disabled": "disable"},
)

# =============================================================================
# XMP / EXPO Profile (Detect-Only BIOS Advisory)
# =============================================================================

SYSTEM_XMP_EXPO = SettingExecutor(
    id="system:xmp_expo",
    category=SettingCategory.SYSTEM,
    display_name="XMP / EXPO Profile (RAM Speed)",
    description="Detects if RAM runs at rated XMP/EXPO speed or "
    "slower JEDEC default. Enable XMP (Intel) or EXPO (AMD) "
    "in BIOS to fix. BIOS updates silently reset this.",
    value_type=SettingValueType.CHOICE,
    choices=("xmp_active", "xmp_inactive"),
    default_value="xmp_inactive",
    recommended_value="xmp_active",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://www.xda-developers.com/same-mistake-ram-right-speed/",
    ],
    current_impact="XMP inactive: RAM running at JEDEC default "
    "(2133-4800 MHz) instead of rated speed",
    recommended_impact="XMP active: RAM at full rated speed for 10-20 FPS gain in CPU-bound titles",
    scope=SettingScope.RECOMMENDED,
    category_order=52,
    effect="Detects RAM speed mismatch. In BIOS, go to Advanced > DRAM Configuration "
    "and set XMP/EXPO Profile to Profile 1 (or the highest available profile).",
    impact_scores={
        "fps_cpu_bound": "+5-15%",
        "fps_1_percent_low": "+5-12%",
        "memory_bandwidth": "up to 2x on DDR4 / up to 1.5x on DDR5",
    },
    is_readonly=True,
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$m = Get-CimInstance Win32_PhysicalMemory -EA SilentlyContinue "
        "| Select-Object -First 1; "
        "if (-not $m) { "
        "  Write-Host 'FPSTUNE_WARN: WMI Win32_PhysicalMemory returned no results. "
        "XMP detection unavailable — may be soldered/LPDDR RAM or WMI restriction.'; "
        "  'not_available' "
        "} elseif (-not $m.Speed) { "
        "  Write-Host 'FPSTUNE_WARN: RAM rated speed (SPD) unreadable via WMI (Speed=0). "
        "Common on soldered LPDDR RAM or OEM BIOS with restricted WMI access.'; "
        "  'not_available' "
        "} elseif ($m.ConfiguredClockSpeed -ge [int]($m.Speed * 0.95)) { 'xmp_active' } "
        "else { 'xmp_inactive' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="",
    apply_args={},
    apply_value_map={},
)

# =============================================================================
# Thermal Condition Advisory (Detect-Only)
# =============================================================================

SYSTEM_THERMAL_CONDITION = SettingExecutor(
    id="system:thermal_condition",
    category=SettingCategory.SYSTEM,
    display_name="Thermal Condition",
    description="Reads system thermal zone temperature. "
    "High temps (>80C) indicate thermal throttling risk. "
    "Consider reapplying thermal paste (3-5 year lifespan).",
    value_type=SettingValueType.CHOICE,
    choices=("ok", "warning", "critical"),
    default_value="ok",
    recommended_value="ok",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://smoothfps.com/guides/thermal-throttling",
    ],
    current_impact="Unknown: Thermal data not yet read",
    recommended_impact="OK: Temperatures within safe range, no thermal throttling",
    scope=SettingScope.COMPLETE,
    category_order=53,
    effect="Advisory: detects thermal zone temperature. "
    "Target CPU below 80°C and GPU below 85°C under full load. "
    "Clean dust from heatsinks and replace thermal paste if temperatures are high.",
    impact_scores={
        "fps_sustained": "-25 to -50% if throttling",
        "latency_ms": 5,
        "stability": "degraded if overheating",
    },
    is_readonly=True,
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$tz = Get-CimInstance -Namespace root/wmi "
        "-ClassName MSAcpi_ThermalZoneTemperature -EA SilentlyContinue "
        "| Sort-Object CurrentTemperature -Descending | Select-Object -First 1; "
        "if (-not $tz) { "
        "  Write-Host 'FPSTUNE_WARN: MSAcpi_ThermalZoneTemperature WMI class not found. "
        "Normal on many desktop systems — ACPI firmware does not expose thermal zones. "
        "Install HWiNFO64 sensor driver for hardware temperature monitoring.'; "
        "  'not_available' "
        "} else { "
        "  $c = [math]::Round(($tz.CurrentTemperature / 10) - 273.15, 0); "
        "  if ($c -gt 90) { 'critical' } elseif ($c -gt 80) { 'warning' } else { 'ok' } "
        "}"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="",
    apply_args={},
    apply_value_map={},
)

_AFD_SOURCES = [
    "https://learn.microsoft.com/en-us/windows-server/networking/technologies/network-subsystem/net-sub-performance-tuning-nics"
]
_AFD_PATH = r"SYSTEM\CurrentControlSet\Services\AFD\Parameters"

NETWORK_AFD_RECEIVE_WINDOW = SettingExecutor(
    id="system:network_afd_receive_window",
    category=SettingCategory.SYSTEM,
    display_name="Winsock AFD Receive Buffer",
    description="Sets the Winsock AFD default receive socket buffer to 128 KB. Larger buffers prevent UDP packet drops when a burst of packets arrives faster than the app can read them.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "optimized"),
    default_value="default",
    recommended_value="optimized",
    requires_reboot=True,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Changes the Winsock default for every socket on the system, not just games. "
    "Each socket reserves more non-paged pool, so a machine with many concurrent connections "
    "(servers, heavy browser use, VMs) pays memory for a benefit that only shows up under bursty "
    "UDP receive load. Requires a reboot, and a reboot again to undo.",
    sources=_AFD_SOURCES,
    current_impact="Default: OS-chosen receive buffer → drops under burst traffic",
    recommended_impact="Optimized: 128 KB receive buffer → fewer drops in fast-paced online games",
    scope=SettingScope.COMPLETE,  # experimental risk is offered, never assumed (C2/#30)
    category_order=55,
    effect="Sets AFD DefaultReceiveWindow=131072 to reduce UDP receive packet loss",
    impact_scores={"latency_ms": 0, "stability": "marginal"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": _AFD_PATH, "name": "DefaultReceiveWindow", "hive": "HKLM"},
    value_map={131072: "optimized", "131072": "optimized", None: "default"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": _AFD_PATH,
        "name": "DefaultReceiveWindow",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"optimized": 131072, "default": None},
    value_hints={"default": "not set", "optimized": "131072"},
)

NETWORK_AFD_SEND_WINDOW = SettingExecutor(
    id="system:network_afd_send_window",
    category=SettingCategory.SYSTEM,
    display_name="Winsock AFD Send Buffer",
    description="Sets the Winsock AFD default send socket buffer to 128 KB. Larger buffers prevent UDP packet drops when the app writes data faster than the network can drain.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "optimized"),
    default_value="default",
    recommended_value="optimized",
    requires_reboot=True,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="Changes the Winsock default for every socket on the system, not just games. "
    "Each socket reserves more non-paged pool, so a machine with many concurrent connections "
    "pays memory for a benefit that only appears when an application writes faster than the link "
    "drains. Requires a reboot, and a reboot again to undo.",
    sources=_AFD_SOURCES,
    current_impact="Default: OS-chosen send buffer → drops under burst traffic",
    recommended_impact="Optimized: 128 KB send buffer → fewer drops in fast-paced online games",
    scope=SettingScope.COMPLETE,  # experimental risk is offered, never assumed (C2/#30)
    category_order=56,
    effect="Sets AFD DefaultSendWindow=131072 to reduce UDP send packet loss",
    impact_scores={"latency_ms": 0, "stability": "marginal"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": _AFD_PATH, "name": "DefaultSendWindow", "hive": "HKLM"},
    value_map={131072: "optimized", "131072": "optimized", None: "default"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": _AFD_PATH,
        "name": "DefaultSendWindow",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"optimized": 131072, "default": None},
    value_hints={"default": "not set", "optimized": "131072"},
)

NETWORK_DSCP_QOS = SettingExecutor(
    id="system:network_dscp_qos",
    category=SettingCategory.SYSTEM,
    display_name="Game Traffic QoS Marking (DSCP 46)",
    description="Tags UDP packets from CS2, MW3, and Warzone with DSCP Expedited Forwarding (46). "
    "Routers that honor DSCP will prioritize game traffic over bulk downloads.",
    value_type=SettingValueType.CHOICE,
    choices=("disabled", "enabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="experimental",
    risk_level="advanced",
    risk_warning="DSCP marks are only honoured if your router is configured to act on them; most "
    "consumer routers ignore them, and many ISPs strip or rewrite the field at the network edge, "
    "in which case this changes nothing. It writes NetQosPolicy entries and flips the NLA flag, "
    "so on a managed or corporate network it can conflict with existing QoS policy.",
    sources=[
        "https://learn.microsoft.com/en-us/windows-server/networking/technologies/qos/qos-policy-top",
        "https://datatracker.ietf.org/doc/html/rfc3246",
    ],
    current_impact="Disabled: Game UDP packets have no priority marking → compete equally with downloads",
    recommended_impact="Enabled: DSCP=46 (Expedited Forwarding) → router prioritizes game packets",
    scope=SettingScope.COMPLETE,
    category_order=56,
    effect="Marks CS2/MW3/Warzone UDP traffic for hardware QoS prioritization",
    impact_scores={"latency_ms": -1.5, "stability": "conditional"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$policy = Get-NetQosPolicy -Name 'fpstune-cs2.exe' -ErrorAction SilentlyContinue; "
        "if ($policy) { 'enabled' } else { 'disabled' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="dscp_qos_toggle",
    apply_args={},
    apply_value_map={"enabled": "enabled", "disabled": "disabled"},
)

# === Memory: favour applications, not the file cache ===
# LargeSystemCache decides whether the memory manager's working-set trimming
# favours the system file cache or running processes. 1 is the server answer and
# 0 is the workstation default; Microsoft documents it that way, and Windows
# client ships 0. On a gaming machine the file cache winning that argument means
# a game's pages get trimmed to make room for cached file data it will never
# read again.
#
# Not invented from a guide: found set to 1 on the dev machine, where TCP
# Optimizer had left it, and the value is not something any gaming guidance
# calls for. This is the drift-guard shape — recommended equals default, so the
# setting exists to notice and undo a change some other tool made.
SYSTEM_LARGE_SYSTEM_CACHE = SettingExecutor(
    id="system:large_system_cache",
    category=SettingCategory.SYSTEM,
    display_name="Memory Priority (Applications vs File Cache)",
    description="Whether Windows trims running programs to grow the file cache. The server "
    "answer starves games of memory; the workstation default is what a gaming PC wants.",
    value_type=SettingValueType.CHOICE,
    choices=("applications", "file_cache"),
    default_value="applications",
    recommended_value="applications",
    requires_reboot=True,
    evidence_level="proven",
    risk_level="low",
    sources=[
        "https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2003/cc784562(v=ws.10)"
    ],
    current_impact="File cache: the memory manager trims running programs to cache file data",
    recommended_impact="Applications: running programs keep their working set, which is the "
    "Windows client default",
    scope=SettingScope.COMPLETE,
    category_order=40,
    effect="Keeps the memory manager favouring running programs over cached file data",
    impact_scores={"ram_saved": "0-500MB kept resident", "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management",
        "name": "LargeSystemCache",
        "hive": "HKLM",
    },
    # Absent means the default, which is the workstation answer.
    value_map={
        0: "applications",
        "0": "applications",
        1: "file_cache",
        "1": "file_cache",
        None: "applications",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management",
        "name": "LargeSystemCache",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"applications": 0, "file_cache": 1},
)

SYSTEM_CONFIG_SETTINGS: list[SettingExecutor] = [
    SYSTEM_LARGE_SYSTEM_CACHE,
    SYSTEM_DRIVER_UPDATES_PROTECTION,
    SYSTEM_DELIVERY_OPTIMIZATION,
    SYSTEM_DO_BACKGROUND_BANDWIDTH,
    SYSTEM_ONEDRIVE_UPLOAD_LIMIT,
    SYSTEM_WINDOWS_UPDATE_MODE,
    SYSTEM_COINSTALLERS,
    SYSTEM_WIDGETS,
    SYSTEM_FILE_EXPLORER_LAUNCH,
    SYSTEM_HYPER_V,
    SYSTEM_VM_PLATFORM,
    SYSTEM_XMP_EXPO,
    SYSTEM_THERMAL_CONDITION,
    NETWORK_AFD_RECEIVE_WINDOW,
    NETWORK_AFD_SEND_WINDOW,
    NETWORK_DSCP_QOS,
]

# =============================================================================
# Cleanup Settings (Actions)
# =============================================================================

CLEANUP_DISM = SettingExecutor(
    id="cleanup:dism_cleanup",
    category=SettingCategory.MAINTENANCE,
    display_name="DISM Cleanup",
    description="Cleans Windows component store. Can free 1-10 GB. Takes 5-15 minutes. Full disk reclaim may require reboot.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/clean-up-the-winsxs-folder"
    ],
    current_impact="Current: WinSxS folder grows over time with old updates",
    recommended_impact="Clean: Frees WinSxS reclaimable space (visible after reboot) → disk space recovered",
    scope=SettingScope.COMPLETE,  # Optional maintenance action
    category_order=21,  # DISM cleanup
    effect="Cleans Windows component store to free several GB of disk space",
    impact_scores={"disk_freed": "1-10GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "dism"},
    value_map={},  # Raw string passthrough: "ready|1234 MB (WinSxS)"
    apply_type=DetectType.POWERSHELL,
    apply_command="dism_cleanup",
    apply_args={},
    apply_value_map={},
    apply_timeout=900,
)

CLEANUP_TEMP = SettingExecutor(
    id="cleanup:temp_files",
    category=SettingCategory.MAINTENANCE,
    display_name="Temp Files",
    description="Cleans temporary files from Windows and user folders.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/clean-up-the-winsxs-folder"
    ],
    current_impact="Current: Temp files taking disk space",
    recommended_impact="Clean: Remove temporary files → free disk space",
    scope=SettingScope.COMPLETE,  # Optional maintenance action
    category_order=22,  # Temp cleanup
    effect="Cleans temporary files from Windows and user folders",
    impact_scores={"disk_freed": "100MB-2GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "temp"},
    value_map={},  # Raw string passthrough: "ready|456 MB"
    apply_type=DetectType.POWERSHELL,
    apply_command="temp_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_EVENT_LOGS = SettingExecutor(
    id="cleanup:event_logs",
    category=SettingCategory.MAINTENANCE,
    display_name="Event Logs",
    description="Clears all Windows event logs (Application, System, Security, etc.). Frees disk space and speeds up Event Viewer.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://learn.microsoft.com/en-us/windows/win32/wes/windows-event-log"],
    current_impact="Current: Event logs accumulating disk space",
    recommended_impact="Clean: All event logs cleared → disk space freed",
    scope=SettingScope.COMPLETE,
    category_order=51,
    effect="Clears all Windows event logs to free disk space",
    impact_scores={"disk_freed": "10-200MB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "event_logs"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="event_logs_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_WER_REPORTS = SettingExecutor(
    id="cleanup:wer_reports",
    category=SettingCategory.MAINTENANCE,
    display_name="Error Reports (WER)",
    description="Clears Windows Error Reporting crash dumps and report archives. These accumulate silently and can occupy several GB.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://learn.microsoft.com/en-us/windows/win32/wer/windows-error-reporting"],
    current_impact="Current: WER crash dumps and reports taking disk space",
    recommended_impact="Clean: WER archives cleared → disk space freed",
    scope=SettingScope.COMPLETE,
    category_order=52,
    effect="Removes accumulated crash dumps and error report archives",
    impact_scores={"disk_freed": "100MB-2GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "wer"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="wer_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_DEFENDER_CACHE = SettingExecutor(
    id="cleanup:defender_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Defender Cache",
    description="Clears Windows Defender scan history and cache files. Safe to remove — Defender rebuilds cache on next scan.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/microsoft-365/security/defender-endpoint/microsoft-defender-antivirus-on-windows-server"
    ],
    current_impact="Current: Defender scan history and cache occupying disk space",
    recommended_impact="Clean: Defender cache cleared → disk space freed, rebuilt on next scan",
    scope=SettingScope.COMPLETE,
    category_order=53,
    effect="Removes Defender scan cache and history files (rebuilt automatically on next scan)",
    impact_scores={"disk_freed": "100MB-1GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "defender"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="defender_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_PREFETCH = SettingExecutor(
    id="cleanup:prefetch",
    category=SettingCategory.MAINTENANCE,
    display_name="Prefetch Files",
    description="Clears Windows prefetch files (C:\\Windows\\Prefetch). Windows rebuilds them automatically. Useful after uninstalling software.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-server/administration/performance-tuning/role/file-server/storage-spaces-direct"
    ],
    current_impact="Current: Prefetch files from uninstalled apps still occupying disk space",
    recommended_impact="Clean: Prefetch cleared → minor disk freed, apps launch slightly slower first run",
    scope=SettingScope.COMPLETE,
    category_order=54,
    effect="Clears prefetch files to free disk space (Windows rebuilds automatically)",
    impact_scores={"disk_freed": "50-200MB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "prefetch"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="prefetch_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_BROWSER_CACHE = SettingExecutor(
    id="cleanup:browser_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Browser Cache",
    description="Clears cache for Edge, Chrome, Brave, and Firefox. Browsers rebuild cache as you browse. Frees significant disk space.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://support.microsoft.com/en-us/topic/how-to-delete-the-contents-of-the-temporary-internet-files-folder"
    ],
    current_impact="Current: Browser cache files occupying significant disk space",
    recommended_impact="Clean: Browser caches cleared → disk space freed (pages load slightly slower first visit)",
    scope=SettingScope.COMPLETE,
    category_order=55,
    effect="Clears Edge, Chrome, Brave, and Firefox cache to free disk space",
    impact_scores={"disk_freed": "200MB-5GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "browser"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="browser_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_WINDOWS_UPDATE_CACHE = SettingExecutor(
    id="cleanup:windows_update_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Windows Update Cache",
    description="Clears downloaded Windows Update packages from SoftwareDistribution\\Download. Windows re-downloads updates as needed.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows/deployment/update/windows-update-troubleshooting"
    ],
    current_impact="Current: Downloaded update packages occupying disk space",
    recommended_impact="Clean: Update cache cleared → disk space freed (updates re-download when needed)",
    scope=SettingScope.COMPLETE,
    category_order=56,
    effect="Removes downloaded Windows Update packages to free disk space",
    impact_scores={"disk_freed": "1-15GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "windows_update_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="windows_update_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_DELIVERY_OPTIMIZATION = SettingExecutor(
    id="cleanup:delivery_optimization",
    category=SettingCategory.MAINTENANCE,
    display_name="Delivery Optimization Cache",
    description="Clears the P2P Windows Update delivery cache. These files are no longer needed once updates are applied.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://learn.microsoft.com/en-us/windows/deployment/do/waas-delivery-optimization"],
    current_impact="Current: P2P update delivery cache occupying disk space",
    recommended_impact="Clean: Delivery Optimization cache cleared → disk space freed",
    scope=SettingScope.COMPLETE,
    category_order=57,
    effect="Removes Delivery Optimization P2P cache to free disk space",
    impact_scores={"disk_freed": "1-10GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "delivery_optimization"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="delivery_optimization_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_THUMBNAIL_CACHE = SettingExecutor(
    id="cleanup:thumbnail_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Thumbnail Cache",
    description="Clears Explorer thumbnail and icon cache files. Windows rebuilds them automatically when you browse folders.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/troubleshoot/windows-client/shell-experience/thumbnail-cache"
    ],
    current_impact="Current: Thumbnail cache files occupying disk space",
    recommended_impact="Clean: Thumbnail cache cleared → disk space freed (rebuilt on next browse)",
    scope=SettingScope.COMPLETE,
    category_order=58,
    effect="Clears Explorer thumbnail and icon cache (rebuilt automatically)",
    impact_scores={"disk_freed": "100-500MB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "thumbnail_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="thumbnail_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_MEMORY_DUMPS = SettingExecutor(
    id="cleanup:memory_dumps",
    category=SettingCategory.MAINTENANCE,
    display_name="Memory Dump Files",
    description="Removes crash dump files (Minidump, MEMORY.DMP, LiveKernelReports). Safe to delete after crashes have been investigated.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/varieties-of-kernel-mode-dump-files"
    ],
    current_impact="Current: Crash dump files occupying disk space",
    recommended_impact="Clean: Memory dumps deleted → disk space freed",
    scope=SettingScope.COMPLETE,
    category_order=59,
    effect="Removes crash dump files (Minidump, MEMORY.DMP, LiveKernelReports)",
    impact_scores={"disk_freed": "100MB-4GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "memory_dumps"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="memory_dumps_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_SHADOW_COPY = SettingExecutor(
    id="cleanup:shadow_copy_reclaim",
    category=SettingCategory.MAINTENANCE,
    display_name="System Restore Storage (Secondary Drives)",
    description="Caps Volume Shadow Copy storage to 10% of capacity on non-system drives. Windows deletes the oldest restore points to fit, freeing disk space.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="likely",
    sources=[
        "https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/vssadmin-resize-shadowstorage",
        "https://learn.microsoft.com/en-us/previous-versions/windows/desktop/vsswmi/win32-shadowstorage",
    ],
    current_impact="Current: Shadow copy storage may exceed 10% of drive capacity on secondary drives",
    recommended_impact="Capped: Shadow storage capped at 10% → oldest restore points removed, space freed",
    scope=SettingScope.COMPLETE,
    category_order=60,
    effect="Caps shadow copy storage on non-system drives to reclaim disk space",
    impact_scores={"disk_freed": "0-10GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "shadow_copy"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="shadow_copy_cleanup",
    apply_args={},
    apply_value_map={},
)

GAME_CLEANUP_DISCORD_CACHE = SettingExecutor(
    id="game_cleanup:discord_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Discord Cache",
    description="Clears Discord app cache, code cache, and GPU cache. Discord rebuilds cache on next launch.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://support.discord.com/hc/en-us/articles/360004332611"],
    current_impact="Current: Discord cache accumulating disk space",
    recommended_impact="Clean: Discord cache cleared → disk space freed",
    scope=SettingScope.COMPLETE,
    category_order=60,
    effect="Clears Discord app cache to free disk space (rebuilt on next launch)",
    impact_scores={"disk_freed": "500MB-2GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "discord_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="discord_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

GAME_CLEANUP_EPIC_CACHE = SettingExecutor(
    id="game_cleanup:epic_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Epic Games Launcher Cache",
    description="Clears Epic Games Launcher web cache and logs. The launcher rebuilds cache on next launch.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://www.epicgames.com/help/en-US/epic-games-store-c73/launcher-support-c82/how-to-clear-the-epic-games-launcher-cache-a1234"
    ],
    current_impact="Current: Epic launcher cache occupying disk space",
    recommended_impact="Clean: Epic cache cleared → disk space freed",
    scope=SettingScope.COMPLETE,
    category_order=61,
    effect="Clears Epic Games Launcher web cache and logs",
    impact_scores={"disk_freed": "100-500MB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "epic_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="epic_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

GAME_CLEANUP_STEAM_WEBCACHE = SettingExecutor(
    id="game_cleanup:steam_webcache",
    category=SettingCategory.MAINTENANCE,
    display_name="Steam Web Cache",
    description="Clears Steam browser and HTML cache. Steam rebuilds cache on next launch. Does not affect game files.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=True,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://help.steampowered.com/en/faqs/view/1F39-DCB4-FF28-5748"],
    current_impact="Current: Steam web cache occupying disk space",
    recommended_impact="Clean: Steam cache cleared → disk space freed",
    scope=SettingScope.COMPLETE,
    category_order=62,
    effect="Clears Steam browser cache (does not affect game files)",
    impact_scores={"disk_freed": "100-500MB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "steam_webcache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="steam_webcache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_PIP_CACHE = SettingExecutor(
    id="cleanup:pip_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="pip Cache (Python)",
    description="Clears pip package download cache. pip re-downloads packages from PyPI on next install. Only present if Python is installed.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://pip.pypa.io/en/stable/topics/caching/"],
    current_impact="Current: pip download cache occupying disk space",
    recommended_impact="Clean: pip cache cleared → disk space freed (slower next install)",
    scope=SettingScope.COMPLETE,
    category_order=70,
    effect="Clears pip package download cache",
    impact_scores={"disk_freed": "500MB-5GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "pip_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="pip_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_NPM_CACHE = SettingExecutor(
    id="cleanup:npm_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="npm Cache (Node.js)",
    description="Clears npm package download cache. npm re-downloads packages on next install. Only present if Node.js is installed.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://docs.npmjs.com/cli/v10/commands/npm-cache"],
    current_impact="Current: npm download cache occupying disk space",
    recommended_impact="Clean: npm cache cleared → disk space freed (slower next install)",
    scope=SettingScope.COMPLETE,
    category_order=71,
    effect="Clears npm package download cache",
    impact_scores={"disk_freed": "1-10GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "npm_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="npm_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_YARN_CACHE = SettingExecutor(
    id="cleanup:yarn_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Yarn Cache (Node.js)",
    description="Clears Yarn package manager cache. Yarn re-downloads packages on next install. Only present if Yarn is installed.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://yarnpkg.com/cli/cache/clean"],
    current_impact="Current: Yarn download cache occupying disk space",
    recommended_impact="Clean: Yarn cache cleared → disk space freed (slower next install)",
    scope=SettingScope.COMPLETE,
    category_order=72,
    effect="Clears Yarn package download cache",
    impact_scores={"disk_freed": "1-8GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "yarn_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="yarn_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_PNPM_CACHE = SettingExecutor(
    id="cleanup:pnpm_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="pnpm Store (Node.js)",
    description="Clears pnpm content-addressable store. pnpm re-downloads all packages on next install. Only present if pnpm is installed.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://pnpm.io/cli/store"],
    current_impact="Current: pnpm store occupying disk space",
    recommended_impact="Clean: pnpm store cleared → disk space freed (re-downloads on next install)",
    scope=SettingScope.COMPLETE,
    category_order=73,
    effect="Clears pnpm global package store",
    impact_scores={"disk_freed": "1-8GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "pnpm_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="pnpm_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_NUGET_CACHE = SettingExecutor(
    id="cleanup:nuget_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="NuGet Packages (.NET)",
    description="Clears NuGet local package cache. Packages re-download on next build. Only present if .NET/Visual Studio is installed.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/nuget/consume-packages/managing-the-global-packages-and-cache-folders"
    ],
    current_impact="Current: NuGet package cache occupying disk space",
    recommended_impact="Clean: NuGet cache cleared → disk space freed (re-downloads on next build)",
    scope=SettingScope.COMPLETE,
    category_order=74,
    effect="Clears NuGet local package cache",
    impact_scores={"disk_freed": "500MB-5GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "nuget_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="nuget_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_MAVEN_CACHE = SettingExecutor(
    id="cleanup:maven_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Maven Repository (Java)",
    description="Clears Maven local repository. Dependencies re-download on next Maven build. Only present if Maven/Java is installed.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://maven.apache.org/guides/introduction/introduction-to-repositories.html"],
    current_impact="Current: Maven local repository occupying disk space",
    recommended_impact="Clean: Maven cache cleared → disk space freed (re-downloads on next build)",
    scope=SettingScope.COMPLETE,
    category_order=75,
    effect="Clears Maven local repository cache",
    impact_scores={"disk_freed": "1-10GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "maven_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="maven_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_GRADLE_CACHE = SettingExecutor(
    id="cleanup:gradle_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Gradle Cache (Java/Kotlin)",
    description="Clears Gradle build cache and downloaded dependencies. Gradle re-downloads on next build. Only present if Gradle is installed.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://docs.gradle.org/current/userguide/dependency_resolution.html"],
    current_impact="Current: Gradle cache and dependencies occupying disk space",
    recommended_impact="Clean: Gradle cache cleared → disk space freed (slower next build)",
    scope=SettingScope.COMPLETE,
    category_order=76,
    effect="Clears Gradle build cache and downloaded dependencies",
    impact_scores={"disk_freed": "1-10GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "gradle_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="gradle_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

CLEANUP_CARGO_CACHE = SettingExecutor(
    id="cleanup:cargo_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Cargo Registry (Rust)",
    description="Clears Cargo package registry cache. Rust crates re-download on next cargo build. Only present if Rust is installed.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://doc.rust-lang.org/cargo/guide/cargo-home.html"],
    current_impact="Current: Cargo registry cache occupying disk space",
    recommended_impact="Clean: Cargo cache cleared → disk space freed (re-downloads on next build)",
    scope=SettingScope.COMPLETE,
    category_order=77,
    effect="Clears Cargo package registry cache",
    impact_scores={"disk_freed": "500MB-3GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "cargo_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="cargo_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

GAME_CLEANUP_BATTLENET = SettingExecutor(
    id="game_cleanup:battlenet_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Battle.net Cache",
    description="Clears the Battle.net launcher HTTP/asset cache. "
    "Fixes launcher crashes, missing game icons, and failed update downloads. Cache rebuilds automatically on next launch.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://us.battle.net/support/en/article/76459"],
    current_impact="Current: Stale launcher cache may cause update failures or missing content",
    recommended_impact="Clean: Cache cleared → launcher re-downloads fresh assets → fixes update/launch errors",
    scope=SettingScope.COMPLETE,
    category_order=78,
    effect="Clears Battle.net launcher cache to fix update and launch errors",
    impact_scores={"disk_freed": "100MB-2GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "battlenet_cache"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="battlenet_cache_cleanup",
    apply_args={},
    apply_value_map={},
)

# =============================================================================
# Maintenance Settings (Actions)
# =============================================================================

MAINTENANCE_SFC = SettingExecutor(
    id="maintenance:sfc_scan",
    category=SettingCategory.MAINTENANCE,
    display_name="System File Checker",
    description="Scan and repair Windows system files.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/repair-a-windows-image"
    ],
    current_impact="Current: System files may be corrupted",
    recommended_impact="Scan: Repairs corrupted Windows files → improved stability",
    scope=SettingScope.COMPLETE,  # Optional maintenance action
    category_order=24,  # System file check
    effect="Scans and repairs corrupted Windows system files",
    impact_scores={"system_integrity": "verified", "stability": "improved"},
    detect_type=DetectType.POWERSHELL,
    detect_command="maintenance_status",
    detect_args={"type": "sfc"},
    value_map={"True": True, "False": False},  # PowerShell bool -> Python bool
    apply_type=DetectType.POWERSHELL,
    apply_command="sfc_scan",
    apply_args={},
    apply_value_map={},
)

MAINTENANCE_DISM_HEALTH = SettingExecutor(
    id="maintenance:dism_health",
    category=SettingCategory.MAINTENANCE,
    display_name="DISM Health Check",
    description="Check Windows image health.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/repair-a-windows-image"
    ],
    current_impact="Current: Windows image health unknown",
    recommended_impact="Scan: Check and repair Windows image → improved stability",
    scope=SettingScope.COMPLETE,  # Optional maintenance action
    category_order=25,  # DISM health check
    effect="Checks and repairs Windows image health using DISM",
    impact_scores={"system_integrity": "verified", "stability": "improved"},
    detect_type=DetectType.POWERSHELL,
    detect_command="maintenance_status",
    detect_args={"type": "dism_health"},
    value_map={"True": True, "False": False},  # PowerShell bool -> Python bool
    apply_type=DetectType.POWERSHELL,
    apply_command="dism_health",
    apply_args={},
    apply_value_map={},
)

# All system settings
MEMORY_SETTINGS: list[SettingExecutor] = [
    MEMORY_PURGE_STANDBY,
]

# =============================================================================
# MMCSS Service (Multimedia Class Scheduler - foundational for priority tweaks)
# =============================================================================

SERVICE_MMCSS = SettingExecutor(
    id="services:MMCSS",
    category=SettingCategory.SYSTEM,
    display_name="Multimedia Class Scheduler (MMCSS)",
    description="Thread priority service for games and multimedia. "
    "Disabling breaks all MMCSS priority registry settings.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/"
        "procthread/multimedia-class-scheduler-service",
    ],
    current_impact="Enabled: Games get elevated thread priority via MMCSS API",
    recommended_impact="Enabled: Keep enabled - required for gaming priority settings to function",
    scope=SettingScope.ESSENTIAL,
    category_order=0,
    effect="MMCSS elevates game thread priority. Disabling causes "
    "stutter from background process competition",
    impact_scores={"fps_cpu_bound": "+1-3%", "stability": "critical"},
    detect_type=DetectType.POWERSHELL,
    detect_command="$s = Get-Service -Name 'MMCSS' -ErrorAction "
    "SilentlyContinue; "
    "if ($s) { [int]$s.StartType } else { 'not_found' }",
    detect_args={"batch_service": "MMCSS"},
    value_map={
        2: "enabled",
        "2": "enabled",
        4: "disabled",
        "4": "disabled",
        3: "enabled",
        "3": "enabled",
        "not_found": "not_available",
    },
    apply_type=DetectType.POWERSHELL,
    apply_command="service_toggle",
    apply_args={"service": "MMCSS"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICES_SETTINGS: list[SettingExecutor] = [
    SERVICE_MMCSS,
    SERVICE_SYSMAIN,
    SERVICE_DIAGTRACK,
    SERVICE_WSEARCH,
    SERVICE_NVIDIA_TELEMETRY,
    SERVICE_NAHIMIC,
    SERVICE_FAX,
    SERVICE_ERROR_REPORTING,
    SERVICE_RETAIL_DEMO,
    SERVICE_WAP_PUSH,
    SERVICE_XBOX_AUTH,
    SERVICE_XBOX_GAME_SAVE,
    SERVICE_XBOX_NETWORKING,
    SERVICE_XBOX_ACCESSORY,
    BACKGROUND_APPS,
    TELEMETRY_TASKS,
    SERVICE_UCPD,
]

PRIVACY_RECALL = SettingExecutor(
    id="privacy:recall",
    category=SettingCategory.SYSTEM,
    display_name="Windows Recall (AI Screenshot)",
    description="Captures periodic screenshots for AI search. Disabling saves disk space and CPU.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=["https://learn.microsoft.com/en-us/windows/client-management/manage-recall"],
    current_impact="Enabled: Periodic screenshots captured → disk usage + CPU overhead",
    recommended_impact="Disabled: No screenshot capture → saves disk space and CPU cycles",
    scope=SettingScope.COMPLETE,
    category_order=16,
    effect="Disables Windows Recall AI screenshot feature for privacy and resource savings",
    impact_scores={
        "disk_freed": "25-150GB",
        "privacy": "improved",
        "cpu_usage": -2,
        "ram_saved": "200-400MB",
    },
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\WindowsAI",
        "name": "AllowRecallEnablement",
        "hive": "HKLM",
    },
    value_map={0: "disabled", 1: "enabled", "0": "disabled", "1": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\WindowsAI",
        "name": "AllowRecallEnablement",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0, "enabled": 1},
)

PRIVACY_CAMERA_INDICATOR = SettingExecutor(
    id="privacy:camera_indicator",
    category=SettingCategory.SYSTEM,
    display_name="Camera On/Off Indicator",
    description="Shows an on-screen notification above the taskbar when any app turns the camera on or off. Useful on devices without a physical camera LED.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="likely",
    sources=["https://www.askvg.com/enable-camera-on-off-indicator-notification-in-windows-11/"],
    current_impact="Disabled: No on-screen notification when camera starts or stops",
    recommended_impact="Enabled: Pop-up notification shows whenever camera turns on/off → privacy awareness",
    scope=SettingScope.COMPLETE,
    category_order=36,
    effect="Enables on-screen indicator notification when apps turn the camera on or off",
    impact_scores={"privacy": "improved", "fps": "0%"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\OEM\Device\Capture",
        "name": "NoPhysicalCameraLED",
        "hive": "HKLM",
    },
    # NoPhysicalCameraLED=1 → no physical LED → show OSD indicator (enabled)
    # NoPhysicalCameraLED=0 or None → assumes hardware LED → hide OSD (disabled)
    value_map={1: "enabled", "1": "enabled", 0: "disabled", "0": "disabled", None: "disabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\OEM\Device\Capture",
        "name": "NoPhysicalCameraLED",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

PRIVACY_APP_LAUNCH_TRACKING = SettingExecutor(
    id="privacy:app_launch_tracking",
    category=SettingCategory.SYSTEM,
    display_name="App Launch Tracking",
    description="Windows tracks which apps you launch to personalize Start menu suggestions. Disabling improves privacy.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=["https://learn.microsoft.com/en-us/windows/privacy/manage-windows-11-endpoints"],
    current_impact="Enabled: App launch history tracked → used for Start menu suggestions",
    recommended_impact="Disabled: No launch tracking → improved privacy, no telemetry overhead",
    scope=SettingScope.RECOMMENDED,
    category_order=56,
    effect="Stops Windows from tracking app launch history used for Start menu personalization",
    impact_scores={"privacy": "improved", "fps": "0%"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "name": "Start_TrackProgs",
        "hive": "HKCU",
    },
    value_map={1: "enabled", "1": "enabled", 0: "disabled", "0": "disabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Advanced",
        "name": "Start_TrackProgs",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

PRIVACY_ONLINE_SPEECH = SettingExecutor(
    id="privacy:online_speech",
    category=SettingCategory.SYSTEM,
    display_name="Online Speech Recognition",
    description="Sends voice data to Microsoft cloud for speech processing. Disabling keeps voice input local only.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="disabled",  # Windows default: HasAccepted absent/0 = not accepted
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=["https://learn.microsoft.com/en-us/windows/privacy/manage-windows-11-endpoints"],
    current_impact="Enabled: Voice input sent to Microsoft servers for processing",
    recommended_impact="Disabled: Voice processing stays local → improved privacy, no cloud dependency",
    scope=SettingScope.RECOMMENDED,
    category_order=57,
    effect="Disables online speech recognition to prevent voice data from being sent to Microsoft",
    impact_scores={"privacy": "improved", "fps": "0%"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy",
        "name": "HasAccepted",
        "hive": "HKCU",
    },
    value_map={1: "enabled", "1": "enabled", 0: "disabled", "0": "disabled", None: "disabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy",
        "name": "HasAccepted",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

PRIVACY_FEEDBACK_REMINDERS = SettingExecutor(
    id="privacy:feedback_reminders",
    category=SettingCategory.SYSTEM,
    display_name="Feedback Reminders",
    description=(
        "Controls Windows feedback reminder popups (SIUF). "
        "Disabling prevents interruptions during gaming sessions."
    ),
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Windows periodically shows feedback reminder popups",
    recommended_impact="Disabled: No feedback popups → uninterrupted gaming sessions",
    scope=SettingScope.RECOMMENDED,  # Popup interruptions affect gaming
    category_order=58,
    effect="Disables Windows feedback reminder popups",
    impact_scores={"privacy": "improved", "fps": "0%", "interruptions": "eliminated"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$siufPath = 'HKCU:\\SOFTWARE\\Microsoft\\Siuf\\Rules';"
        " $gpPath = 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\DataCollection';"
        " $siufOff = $false; $gpOff = $false;"
        " if (Test-Path $siufPath) {"
        " $v = (Get-ItemProperty -Path $siufPath -Name 'NumberOfSIUFInPeriod'"
        " -EA SilentlyContinue).NumberOfSIUFInPeriod;"
        " if ($v -eq 0) { $siufOff = $true } };"
        " if (Test-Path $gpPath) {"
        " $g = (Get-ItemProperty -Path $gpPath -Name 'DoNotShowFeedbackNotifications'"
        " -EA SilentlyContinue).DoNotShowFeedbackNotifications;"
        " if ($g -eq 1) { $gpOff = $true } };"
        " if ($siufOff -or $gpOff) { Write-Output 'disabled' }"
        " else { Write-Output 'enabled' }"
    ),
    value_map={"disabled": "disabled", "enabled": "enabled"},
    apply_type=DetectType.POWERSHELL,
    apply_command="feedback_reminders_toggle",
    apply_value_map={"disabled": "disable", "enabled": "enable"},
)

PRIVACY_CEIP = SettingExecutor(
    id="privacy:ceip",
    category=SettingCategory.SYSTEM,
    display_name="Customer Experience Improvement Program",
    description=(
        "Sends usage and reliability data to Microsoft as part of CEIP. "
        "Disabling reduces background telemetry and CPU overhead."
    ),
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Usage and reliability data sent to Microsoft",
    recommended_impact="Disabled: No CEIP data collection → reduced CPU overhead",
    scope=SettingScope.COMPLETE,
    category_order=59,
    effect="Disables Customer Experience Improvement Program telemetry",
    impact_scores={"privacy": "improved", "cpu_usage": -1, "fps_1_percent_low": "+0-1%"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\SQMClient\Windows",
        "name": "CEIPEnable",
        "hive": "HKLM",
    },
    # 1 or None = enabled, 0 = disabled
    value_map={1: "enabled", "1": "enabled", 0: "disabled", "0": "disabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\SQMClient\Windows",
        "name": "CEIPEnable",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

PRIVACY_APP_TELEMETRY = SettingExecutor(
    id="privacy:app_telemetry",
    category=SettingCategory.SYSTEM,
    display_name="Application Telemetry (AITEnable)",
    description=(
        "Controls the Application Impact Telemetry engine that monitors app usage. "
        "Disabling reduces background data collection and CPU overhead."
    ),
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    current_impact="Enabled: Application usage data collected in background",
    recommended_impact="Disabled: No app telemetry → reduced CPU overhead",
    scope=SettingScope.COMPLETE,
    category_order=60,
    effect="Disables Application Impact Telemetry engine",
    impact_scores={"privacy": "improved", "cpu_usage": -0.5, "fps_1_percent_low": "+0-1%"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$p = 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\AppCompat';"
        " if (-not (Test-Path $p)) { Write-Output 'enabled'; return };"
        " $ait = (Get-ItemProperty -Path $p -Name 'AITEnable' -EA SilentlyContinue).AITEnable;"
        " $uar = (Get-ItemProperty -Path $p -Name 'DisableUAR' -EA SilentlyContinue).DisableUAR;"
        " $inv = (Get-ItemProperty -Path $p -Name 'DisableInventory' -EA SilentlyContinue).DisableInventory;"
        " if ($ait -eq 0 -or ($uar -eq 1 -and $inv -eq 1)) { Write-Output 'disabled' }"
        " else { Write-Output 'enabled' }"
    ),
    value_map={"disabled": "disabled", "enabled": "enabled"},
    apply_type=DetectType.POWERSHELL,
    apply_command="app_telemetry_toggle",
    apply_value_map={"disabled": "disable", "enabled": "enable"},
)

PRIVACY_SETTINGS: list[SettingExecutor] = [
    PRIVACY_ADVERTISING_ID,
    PRIVACY_ACTIVITY_HISTORY,
    PRIVACY_CONSUMER_FEATURES,
    PRIVACY_EDGE_TELEMETRY,
    PRIVACY_CORTANA,
    PRIVACY_BING_SEARCH,
    PRIVACY_INPUT_PERSONALIZATION,
    PRIVACY_ACCEPTED_POLICY,
    PRIVACY_TILE_NOTIFICATIONS,
    PRIVACY_ALLOW_TELEMETRY,
    PRIVACY_COPILOT,
    PRIVACY_WINDOWS_ADS,
    PRIVACY_WEB_SEARCH_POLICY,
    PRIVACY_RECALL,
    PRIVACY_CAMERA_INDICATOR,
    PRIVACY_APP_LAUNCH_TRACKING,
    PRIVACY_ONLINE_SPEECH,
    PRIVACY_FEEDBACK_REMINDERS,
    PRIVACY_CEIP,
    PRIVACY_APP_TELEMETRY,
]

PERF_STARTUP_DELAY = SettingExecutor(
    id="perf:startup_delay",
    category=SettingCategory.SYSTEM,
    display_name="Startup App Delay",
    description="Windows delays startup apps ~10s after login to improve initial desktop responsiveness. Removing the delay makes startup apps launch and finish earlier.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "disabled"),
    default_value="default",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Default: Startup apps delayed ~10s → still running when game launches",
    recommended_impact="Disabled: Startup apps run immediately → finish before you start gaming",
    scope=SettingScope.RECOMMENDED,
    category_order=46,
    effect="Removes startup app delay so background apps finish loading before gaming sessions",
    impact_scores={"fps": "0%", "latency_ms": 0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$val = (Get-ItemProperty -Path "
        "'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Serialize' "
        "-Name 'StartupDelayInMSec' -ErrorAction SilentlyContinue).StartupDelayInMSec; "
        "if ($null -ne $val -and $val -eq 0) { 'disabled' } else { 'default' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "if ('%value%' -eq 'disabled') { "
        "$p = 'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Serialize'; "
        "if (-not (Test-Path $p)) { New-Item -Path $p -Force | Out-Null }; "
        "Set-ItemProperty -Path $p -Name 'StartupDelayInMSec' -Value 0 -Type DWord "
        "} else { "
        "Remove-ItemProperty -Path "
        "'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Serialize' "
        "-Name 'StartupDelayInMSec' -ErrorAction SilentlyContinue }"
    ),
    apply_args={},
    apply_value_map={},
    value_hints={"default": "~10s delay", "disabled": "0ms"},
)

PERF_NUMLOCK_DEFAULT = SettingExecutor(
    id="perf:numlock_default",
    category=SettingCategory.SYSTEM,
    display_name="Num Lock Default State",
    description="Sets Num Lock state at every Windows login. Useful for numpad keybinds in games.",
    value_type=SettingValueType.CHOICE,
    choices=("off", "on"),
    default_value="off",
    recommended_value="on",
    requires_reboot=False,
    current_impact="Off: Num Lock disabled after login → manual toggle needed each time",
    recommended_impact="On: Num Lock enabled at login → numpad ready for game keybinds",
    scope=SettingScope.COMPLETE,
    category_order=47,
    effect="Enables Num Lock by default on every Windows login",
    impact_scores={"fps": "0%", "latency_ms": 0, "ux": "improved"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"Control Panel\Keyboard",
        "name": "InitialKeyboardIndicators",
        "hive": "HKCU",
    },
    # InitialKeyboardIndicators is a bitmask, not an enum: 0x1 Caps Lock,
    # 0x2 Num Lock, 0x4 Scroll Lock, 0x80000000 "restore the previous state".
    # Only 0x2 is this setting's business. The table used to list 2 and
    # 2147483650, which covered two of the combinations Windows writes and
    # missed 2147483648 — the high bit with Num Lock off, a perfectly ordinary
    # state — so it reached the UI as a bare number outside `choices` and could
    # never verify. Masking answers for every combination, including the ones no
    # Windows version writes yet.
    value_map={MASK: 0x2, 2: "on", 0: "off", None: "off"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"Control Panel\Keyboard",
        "name": "InitialKeyboardIndicators",
        "hive": "HKCU",
        "type": "REG_SZ",
    },
    apply_value_map={"on": "2", "off": "0"},
)

PERF_FOCUS_ASSIST = SettingExecutor(
    id="perf:focus_assist",
    category=SettingCategory.SYSTEM,
    display_name="Focus Assist (Game Notifications)",
    description="Suppresses notifications during fullscreen games. Prevents notification-caused stutter.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Enabled: Notifications can cause frame drops during gaming",
    recommended_impact="Disabled: No notification popups → uninterrupted gaming",
    scope=SettingScope.RECOMMENDED,
    category_order=45,
    effect="Suppresses Windows notifications during gaming to prevent frame drops",
    impact_scores={"fps": "0%", "fps_1_percent_low": "+0-1%", "latency_ms": 0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Notifications\Settings",
        "name": "NOC_GLOBAL_SETTING_TOASTS_ENABLED",
        "hive": "HKCU",
    },
    value_map={0: "disabled", 1: "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Notifications\Settings",
        "name": "NOC_GLOBAL_SETTING_TOASTS_ENABLED",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0, "enabled": 1},
)

PERF_VBS_CORE_ISOLATION = SettingExecutor(
    id="system:vbs_core_isolation",
    category=SettingCategory.SYSTEM,
    display_name="VBS / Core Isolation",
    description="Virtualization-Based Security (Memory Integrity). Keep enabled for security. Disabling gives ~5% FPS but triggers Windows Security warning.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=True,
    evidence_level="proven",
    sources=[
        "https://www.windowscentral.com/microsoft/windows-11/my-top-21-ways-to-improve-windows-11-to-increase-gaming-performance-without-hardware-upgrade"
    ],
    current_impact="Enabled: Hypervisor-enforced code integrity active (~5% FPS cost, strong security)",
    recommended_impact="Enabled: Keep enabled → security outweighs ~5% FPS gain for most users",
    scope=SettingScope.COMPLETE,  # Informational -- user can disable manually if they choose
    category_order=50,
    effect="Removes ~5% CPU overhead from virtualization-based security",
    impact_scores={
        "fps": "+2-5%",
        "fps_cpu_bound": "+4-8%",
        "latency_ms": -0.5,
        "security": "reduced",
    },
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity",
        "name": "Enabled",
        "hive": "HKLM",
    },
    value_map={1: "enabled", 0: "disabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity",
        "name": "Enabled",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 1, "disabled": 0},
)

# =============================================================================
# Shutdown / Startup Speed Settings (individual, replaces PERF_SHUTDOWN_SPEED)
# =============================================================================
DESKTOP_KEY = r"Control Panel\Desktop"
CONTROL_KEY = r"SYSTEM\CurrentControlSet\Control"

SHUTDOWN_SERVICE_TIMEOUT = SettingExecutor(
    id="perf:shutdown_service_timeout",
    category=SettingCategory.SYSTEM,
    display_name="Service Shutdown Timeout",
    description="Maximum milliseconds Windows waits for a service to stop during shutdown. "
    "Reducing from 5000ms to 2000ms shortens shutdown by up to 3 seconds.",
    value_type=SettingValueType.CHOICE,
    choices=("5000ms", "2000ms"),
    default_value="5000ms",
    recommended_value="2000ms",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="5000ms: Windows waits up to 5 seconds per service during shutdown",
    recommended_impact="2000ms: Services killed after 2 seconds → faster shutdown",
    scope=SettingScope.RECOMMENDED,
    category_order=30,
    effect="Reduces service shutdown timeout from 5s to 2s for faster system shutdown",
    impact_scores={"latency_ms": 0, "shutdown_speed": "faster"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": CONTROL_KEY, "name": "WaitToKillServiceTimeout", "hive": "HKLM"},
    value_map={"2000": "2000ms", "5000": "5000ms", None: "5000ms"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": CONTROL_KEY,
        "name": "WaitToKillServiceTimeout",
        "hive": "HKLM",
        "type": "REG_SZ",
    },
    apply_value_map={"2000ms": "2000", "5000ms": "5000"},
)

SHUTDOWN_APP_TIMEOUT = SettingExecutor(
    id="perf:shutdown_app_timeout",
    category=SettingCategory.SYSTEM,
    display_name="App Shutdown Timeout",
    description="Maximum milliseconds Windows waits for a hung application to close during shutdown. "
    "Applies to both hung-app detection and forced kill timeouts.",
    value_type=SettingValueType.CHOICE,
    choices=("5000ms", "2000ms"),
    default_value="5000ms",
    recommended_value="2000ms",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="5000ms: Windows waits up to 5 seconds before killing hung apps on shutdown",
    recommended_impact="2000ms: Hung apps killed after 2 seconds → faster shutdown",
    scope=SettingScope.RECOMMENDED,
    category_order=31,
    effect="Reduces application shutdown timeout from 5s to 2s for faster system shutdown",
    impact_scores={"latency_ms": 0, "shutdown_speed": "faster"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": DESKTOP_KEY, "name": "WaitToKillAppTimeout", "hive": "HKCU"},
    value_map={"2000": "2000ms", "5000": "5000ms", None: "5000ms"},
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "$v = if ('%value%' -eq '2000ms') { '2000' } else { '5000' }; "
        "Set-ItemProperty -Path 'HKCU:\\Control Panel\\Desktop' -Name 'WaitToKillAppTimeout' -Value $v -Type String -Force; "
        "Set-ItemProperty -Path 'HKCU:\\Control Panel\\Desktop' -Name 'HungAppTimeout' -Value $v -Type String -Force; "
        "'ok'"
    ),
    apply_args={},
    apply_value_map={},
)

SHUTDOWN_AUTO_END_TASKS = SettingExecutor(
    id="perf:shutdown_auto_end_tasks",
    category=SettingCategory.SYSTEM,
    display_name="Auto-End Tasks on Shutdown",
    description="Automatically terminates tasks that do not respond to the shutdown signal. "
    "Prevents stuck programs from blocking system shutdown.",
    value_type=SettingValueType.CHOICE,
    choices=("disabled", "enabled"),
    default_value="disabled",
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Disabled: Windows shows dialog for hung apps during shutdown → manual intervention needed",
    recommended_impact="Enabled: Hung apps are terminated automatically → unattended shutdown",
    scope=SettingScope.RECOMMENDED,
    category_order=32,
    effect="Enables automatic termination of non-responsive apps during shutdown",
    impact_scores={"latency_ms": 0, "shutdown_speed": "faster", "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": DESKTOP_KEY, "name": "AutoEndTasks", "hive": "HKCU"},
    value_map={"1": "enabled", "0": "disabled", None: "disabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={"path": DESKTOP_KEY, "name": "AutoEndTasks", "hive": "HKCU", "type": "REG_SZ"},
    apply_value_map={"enabled": "1", "disabled": "0"},
)

GPU_TDR_DELAY = SettingExecutor(
    id="perf:gpu_tdr_delay",
    category=SettingCategory.SYSTEM,
    display_name="GPU TDR Delay",
    description="Extends the GPU driver Timeout Detection and Recovery (TDR) window from the "
    "Windows default of 2 seconds to 10 seconds. DX12 workloads in MW3 frequently stall the GPU "
    "longer than 2 s, triggering a forced driver reset that surfaces as a Dev Error or black-screen crash.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "extended"),
    default_value="default",
    recommended_value="extended",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://www.tomshardware.com/how-to/how-to-fix-video_tdr_failure-bsods-and-video_tdr_timeout_detected-errors",
        "https://www.intel.com/content/www/us/en/docs/oneapi/installation-guide-windows/2024-1/gpu-adjust-timeout-detection-and-recovery-setting.html",
    ],
    current_impact="default (2s): GPU stall > 2s triggers driver reset → Dev Error crash in DX12 titles",
    recommended_impact="extended (10s): GPU stall up to 10s recovers silently → prevents Dev Error crashes",
    scope=SettingScope.RECOMMENDED,
    category_order=33,
    effect="Extends GPU driver TDR timeout to 10s to prevent Dev Error crashes in DX12 games",
    impact_scores={"latency_ms": 0, "stability": "high", "crash_rate": "reduced"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
        "name": "TdrDelay",
        "hive": "HKLM",
    },
    value_map={None: "default", 2: "default", "2": "default", 10: "extended", "10": "extended"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
        "name": "TdrDelay",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"default": 2, "extended": 10},
    value_hints={"default": "2s", "extended": "10s"},
)

PERFORMANCE_SETTINGS: list[SettingExecutor] = [
    SHUTDOWN_SERVICE_TIMEOUT,
    SHUTDOWN_APP_TIMEOUT,
    SHUTDOWN_AUTO_END_TASKS,
    GPU_TDR_DELAY,
    # PERF_GAMING_PRIORITY removed: was a bundle that conflicted with individual settings
    # (priority:system_responsiveness, priority:gpu_priority, priority:game_priority,
    #  priority:scheduling_category, network:network_throttling_index)
    PERF_ACCESSIBILITY_POPUPS,
    PERF_MOUSE_ACCELERATION,
    PERF_FAST_STARTUP,
    # PERF_MENU_DELAY removed: conflicts with visual:animations (both use HKCU\Control Panel\Desktop\MenuShowDelay)
    # visual:animations sets it to "0" (disabled) which is already more aggressive than 50ms
    PERF_SVCHOST_SPLIT,
    # PERF_NETWORK_THROTTLING removed: conflicts with network:network_throttling_index
    # (same registry key: NetworkThrottlingIndex)
    # PERF_MEMORY_COMPRESSION removed: controlled by SysMain service.
    # Disabling SysMain automatically disables Memory Compression.
    # Enabling MC requires SysMain to be running -- circular dependency.
    PERF_STARTUP_DELAY,
    PERF_NUMLOCK_DEFAULT,
    PERF_FOCUS_ASSIST,
    PERF_VBS_CORE_ISOLATION,
]

# =============================================================================
# Game Maintenance — GPU/DX shader caches (module: game_cleanup)
# =============================================================================

GAME_CLEANUP_NVIDIA_SHADER = SettingExecutor(
    id="game_cleanup:nvidia_shader_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="NVIDIA Shader Cache",
    description="Clears NVIDIA DirectX (DXCache) and OpenGL (GLCache) shader caches, including per-driver-version folders. The driver and games recompile shaders on next launch.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://nvidia.custhelp.com/app/answers/detail/a_id/5121"],
    current_impact="Current: NVIDIA shader caches grow after every driver update and game session",
    recommended_impact="Clean: NVIDIA DX/GL caches cleared → disk space freed, stale-shader crashes fixed",
    scope=SettingScope.COMPLETE,
    category_order=80,
    effect="Clears NVIDIA DX and GL shader caches",
    impact_scores={"disk_freed": "100MB-3GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "nvidia_shader"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="nvidia_shader_cleanup",
    apply_args={},
    apply_value_map={},
)

GAME_CLEANUP_AMD_SHADER = SettingExecutor(
    id="game_cleanup:amd_shader_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="AMD Shader Cache",
    description="Clears AMD DirectX (DxCache), Vulkan (VkCache), and OpenGL (GLCache) shader caches. The driver recompiles shaders on next launch.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://www.amd.com/en/support"],
    current_impact="Current: AMD shader caches accumulate across driver updates and game sessions",
    recommended_impact="Clean: AMD DX/Vulkan/GL caches cleared → disk space freed, stale-shader glitches fixed",
    scope=SettingScope.COMPLETE,
    category_order=81,
    effect="Clears AMD DX, Vulkan, and GL shader caches",
    impact_scores={"disk_freed": "100MB-3GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "amd_shader"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="amd_shader_cleanup",
    apply_args={},
    apply_value_map={},
)

GAME_CLEANUP_DIRECTX_SHADER = SettingExecutor(
    id="game_cleanup:directx_shader_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="DirectX Shader Cache",
    description="Clears the Windows DirectX shader cache (D3DSCache) shared by all DirectX games. Windows rebuilds it automatically as games run.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/direct3d12/managing-graphics-pipeline-state-in-direct3d-12"
    ],
    current_impact="Current: DirectX shader cache grows as you play DX11/DX12 games",
    recommended_impact="Clean: DirectX shader cache cleared → disk space freed, shader-corruption stutters fixed",
    scope=SettingScope.COMPLETE,
    category_order=82,
    effect="Clears the Windows DirectX shader cache",
    impact_scores={"disk_freed": "100MB-2GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "directx_shader"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="directx_shader_cleanup",
    apply_args={},
    apply_value_map={},
)

GAME_CLEANUP_INTEL_SHADER = SettingExecutor(
    id="game_cleanup:intel_shader_cache",
    category=SettingCategory.MAINTENANCE,
    display_name="Intel Shader Cache",
    description="Clears Intel GPU shader cache folders. The driver recompiles shaders on next launch.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=["https://www.intel.com/content/www/us/en/support/articles/000090440/graphics.html"],
    current_impact="Current: Intel shader cache accumulates across game sessions",
    recommended_impact="Clean: Intel shader cache cleared → disk space freed, stale-shader issues fixed",
    scope=SettingScope.COMPLETE,
    category_order=83,
    effect="Clears Intel GPU shader caches",
    impact_scores={"disk_freed": "50MB-1GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "intel_shader"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="intel_shader_cleanup",
    apply_args={},
    apply_value_map={},
)

# =============================================================================
# Developer / Container Cleanup (module: cleanup)
# =============================================================================

CLEANUP_DOCKER_PRUNE = SettingExecutor(
    id="cleanup:docker_prune",
    category=SettingCategory.MAINTENANCE,
    display_name="Docker Unused Data (Prune)",
    description="Runs 'docker system prune' to remove dangling images, stopped containers, unused networks, and build cache. Active containers, tagged images in use, and named volumes are preserved.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    # Hide everywhere when Docker is not installed; the "docker" feature is
    # detected from Docker Desktop's presence at startup.
    applicable_conditions={"feature": "docker"},
    risk_level="safe",
    evidence_level="proven",
    sources=["https://docs.docker.com/reference/cli/docker/system/prune/"],
    current_impact="Current: Docker build cache and dangling images accumulate unused disk space",
    recommended_impact="Clean: Unused Docker data removed → disk space freed without touching volumes or active images",
    scope=SettingScope.COMPLETE,
    category_order=68,
    effect="Removes dangling Docker images, stopped containers, and build cache",
    impact_scores={"disk_freed": "500MB-20GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "docker_prune"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="docker_prune",
    apply_args={},
    apply_value_map={},
    apply_timeout=300,
)

CLEANUP_DOCKER_PRUNE_ALL = SettingExecutor(
    id="cleanup:docker_prune_all",
    category=SettingCategory.MAINTENANCE,
    display_name="Docker All Unused Images (Prune -a)",
    description="Runs 'docker system prune -a' to additionally remove ALL images not used by any container, not just dangling ones. Frees the most space. Named volumes and running containers are preserved; removed images are re-pulled or rebuilt on next use.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    # Hide everywhere when Docker is not installed (see docker feature detection).
    applicable_conditions={"feature": "docker"},
    risk_level="moderate",
    evidence_level="proven",
    sources=["https://docs.docker.com/reference/cli/docker/system/prune/"],
    current_impact="Current: Unused (but tagged) Docker images occupy disk space even when no container uses them",
    recommended_impact="Clean: All unused images + cache removed → largest disk reclaim, no data loss (images re-pull/rebuild on demand)",
    scope=SettingScope.COMPLETE,
    category_order=68,
    effect="Removes all unused Docker images, stopped containers, and build cache",
    impact_scores={"disk_freed": "1-50GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "docker_prune_all"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="docker_prune_all",
    apply_args={},
    apply_value_map={},
    apply_timeout=300,
)

CLEANUP_WSL_COMPACT = SettingExecutor(
    id="cleanup:wsl_compact",
    category=SettingCategory.MAINTENANCE,
    display_name="WSL / Docker Disk Compact",
    description="Shuts down WSL and compacts all WSL2 virtual disks (ext4.vhdx), including the Docker Desktop data disk, to return freed space to Windows. WSL disks grow over time and never shrink on their own.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    risk_level="advanced",
    risk_warning="Runs 'wsl --shutdown' first, which immediately closes all running WSL distributions and Docker Desktop (WSL backend). Save your work before running.",
    evidence_level="proven",
    sources=["https://learn.microsoft.com/en-us/windows/wsl/disk-space"],
    current_impact="Current: WSL2 virtual disks stay bloated and never return freed space to Windows",
    recommended_impact="Clean: WSL2 vhdx files compacted → reclaimed disk space returned to Windows (often several GB)",
    scope=SettingScope.COMPLETE,
    category_order=69,
    effect="Compacts WSL2 and Docker virtual disks to reclaim host disk space",
    impact_scores={"disk_freed": "1-30GB", "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command="cleanup_status",
    detect_args={"type": "wsl_compact"},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="wsl_compact",
    apply_args={},
    apply_value_map={},
    apply_timeout=600,
)

CLEANUP_SETTINGS: list[SettingExecutor] = [
    CLEANUP_DISM,
    CLEANUP_TEMP,
    CLEANUP_EVENT_LOGS,
    CLEANUP_WER_REPORTS,
    CLEANUP_DEFENDER_CACHE,
    CLEANUP_PREFETCH,
    CLEANUP_BROWSER_CACHE,
    CLEANUP_WINDOWS_UPDATE_CACHE,
    CLEANUP_DELIVERY_OPTIMIZATION,
    CLEANUP_THUMBNAIL_CACHE,
    CLEANUP_MEMORY_DUMPS,
    CLEANUP_SHADOW_COPY,
    CLEANUP_PIP_CACHE,
    CLEANUP_NPM_CACHE,
    CLEANUP_YARN_CACHE,
    CLEANUP_PNPM_CACHE,
    CLEANUP_NUGET_CACHE,
    CLEANUP_MAVEN_CACHE,
    CLEANUP_GRADLE_CACHE,
    CLEANUP_CARGO_CACHE,
    CLEANUP_DOCKER_PRUNE,
    CLEANUP_DOCKER_PRUNE_ALL,
    CLEANUP_WSL_COMPACT,
]

# Game Maintenance panel settings (module: game_cleanup). MW3-specific game
# cleanups live in game_configs.py and are aggregated via GAME_CONFIG_SETTINGS.
GAME_CLEANUP_SETTINGS: list[SettingExecutor] = [
    GAME_CLEANUP_NVIDIA_SHADER,
    GAME_CLEANUP_AMD_SHADER,
    GAME_CLEANUP_DIRECTX_SHADER,
    GAME_CLEANUP_INTEL_SHADER,
    GAME_CLEANUP_STEAM_WEBCACHE,
    GAME_CLEANUP_EPIC_CACHE,
    GAME_CLEANUP_DISCORD_CACHE,
    GAME_CLEANUP_BATTLENET,
]

MAINTENANCE_SETTINGS: list[SettingExecutor] = [
    MAINTENANCE_SFC,
    MAINTENANCE_DISM_HEALTH,
]

SYSTEM_SETTINGS: list[SettingExecutor] = [
    *MEMORY_SETTINGS,
    *SERVICES_SETTINGS,
    *SYSTEM_CONFIG_SETTINGS,
    *PRIVACY_SETTINGS,
    *PERFORMANCE_SETTINGS,
    *CLEANUP_SETTINGS,
    *GAME_CLEANUP_SETTINGS,
    *MAINTENANCE_SETTINGS,
]

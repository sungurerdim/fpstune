"""System setting definitions.

Contains settings for memory, services, cleanup, and maintenance.
These are typically one-time actions or service toggles.
"""

from __future__ import annotations

from fpstune.settings.base import (
    MASK,
    PERCENT_PROGRESS,
    UNMAPPED,
    DetectType,
    SettingCategory,
    SettingExecutor,
    SettingScope,
    SettingValueType,
)
from fpstune.settings.virtualization import VIRTUALIZATION_IN_USE

# =============================================================================
# Memory Settings
# =============================================================================

MEMORY_PURGE_STANDBY = SettingExecutor(
    id="memory:purge_standby",
    category=SettingCategory.MAINTENANCE,
    display_name="Purge Standby List",
    short_name="Clear standby memory",
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
    short_name="Superfetch preloading",
    description="The service that preloads apps and runs the memory manager agent, memory compression "
    "included. Stopping it switches compression off, so memory pressure goes to the disk instead.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    # A guard since 0.2.0 (consequence 6). Disabling SysMain disables every
    # MMAgent feature with it — memory compression included — and enabling any
    # of them starts SysMain again (Winhance #261, tested with Get-MMAgent
    # before and after). The "less disk I/O on an SSD" it bought is small next
    # to pages leaving RAM for the disk under pressure, which is a hitch in a
    # game; and system:memory_compression would fight a disabled SysMain on
    # every bulk apply. The disabled state is what this row now undoes.
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://github.com/memstechtips/Winhance/issues/261",
        "https://blogs.windows.com/windowsexperience/2015/08/18/announcing-windows-10-insider-preview-build-10525/",
    ],
    current_impact="Disabled: Memory compression is off too → memory pressure is paged to disk",
    recommended_impact="Enabled: Windows' own state → memory compression can run",
    scope=SettingScope.RECOMMENDED,
    category_order=1,
    effect="Restores the service that runs memory compression if another tool disabled it",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
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
    apply_args={"service": "SysMain", "start_mode": "auto"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_DIAGTRACK = SettingExecutor(
    id="services:DiagTrack",
    category=SettingCategory.SYSTEM,
    display_name="Connected User Experiences and Telemetry",
    short_name="Windows telemetry service",
    description="Collects usage and diagnostic data and uploads it to Microsoft on its own schedule, "
    "including during a match. Off, that collection and its upload stop.",
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
    apply_args={"service": "DiagTrack", "start_mode": "auto"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_WSEARCH = SettingExecutor(
    id="services:WSearch",
    category=SettingCategory.SYSTEM,
    display_name="Windows Search",
    short_name="Windows Search indexing",
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
    apply_args={"service": "WSearch", "start_mode": "delayed-auto"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_NVIDIA_TELEMETRY = SettingExecutor(
    id="services:NvTelemetryContainer",
    category=SettingCategory.SYSTEM,
    display_name="NVIDIA Telemetry",
    short_name="NVIDIA telemetry",
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
    apply_args={"service": "NvTelemetryContainer", "start_mode": "auto"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_NAHIMIC = SettingExecutor(
    id="services:NahimicService",
    category=SettingCategory.SYSTEM,
    display_name="Nahimic Audio Service",
    short_name="Nahimic audio service",
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
    apply_args={"service": "NahimicService", "start_mode": "auto"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_FAX = SettingExecutor(
    id="services:Fax",
    category=SettingCategory.SYSTEM,
    display_name="Fax Service",
    short_name="Fax service",
    description="Runs a fax service on a machine with no fax hardware. Off, it stops occupying a service slot "
    "and starting with Windows for nothing.",
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
    apply_args={"service": "Fax", "start_mode": "demand"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_ERROR_REPORTING = SettingExecutor(
    id="services:WerSvc",
    category=SettingCategory.SYSTEM,
    display_name="Windows Error Reporting",
    short_name="Error reporting service",
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
    apply_args={"service": "WerSvc", "start_mode": "demand"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_RETAIL_DEMO = SettingExecutor(
    id="services:RetailDemo",
    category=SettingCategory.SYSTEM,
    display_name="Retail Demo Service",
    short_name="Store demo service",
    description="Exists to run the demo loop on a shop display machine. It has no purpose on a personal "
    "computer and starting it is pure waste.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",  # Windows ships it Manual (trigger-started)
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
    apply_args={"service": "RetailDemo", "start_mode": "demand"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_WAP_PUSH = SettingExecutor(
    id="services:dmwappushservice",
    category=SettingCategory.SYSTEM,
    display_name="WAP Push Message Routing",
    short_name="WAP push service",
    description="Device-management push for MDM and Intune. Keep it enabled on a work or school managed "
    "machine.",
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
    apply_args={"service": "dmwappushservice", "start_mode": "demand"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

# =============================================================================
# Xbox Services (with warning for Xbox Game Pass users)
# =============================================================================

SERVICE_XBOX_AUTH = SettingExecutor(
    id="services:XblAuthManager",
    category=SettingCategory.SYSTEM,
    display_name="Xbox Live Auth Manager",
    short_name="Xbox sign-in service",
    description="Xbox Live sign-in, which Xbox Game Save depends on. Keep it enabled for Game Pass.",
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
    apply_args={"service": "XblAuthManager", "start_mode": "demand"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_XBOX_GAME_SAVE = SettingExecutor(
    id="services:XblGameSave",
    category=SettingCategory.SYSTEM,
    display_name="Xbox Live Game Save",
    short_name="Xbox cloud saves",
    description="Xbox cloud saves. Keep it enabled if you use Xbox Game Pass or Play Anywhere.",
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
    apply_args={"service": "XblGameSave", "start_mode": "demand"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_XBOX_NETWORKING = SettingExecutor(
    id="services:XboxNetApiSvc",
    category=SettingCategory.SYSTEM,
    display_name="Xbox Live Networking",
    short_name="Xbox networking service",
    description="Xbox multiplayer networking. Keep it enabled if you use Xbox Game Pass or Play Anywhere.",
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
    apply_args={"service": "XboxNetApiSvc", "start_mode": "demand"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

SERVICE_XBOX_ACCESSORY = SettingExecutor(
    id="services:XboxGipSvc",
    category=SettingCategory.SYSTEM,
    display_name="Xbox Accessory Management",
    short_name="Xbox accessory service",
    description="Xbox controller management. Keep it enabled if you use an Xbox controller.",
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
    apply_args={"service": "XboxGipSvc", "start_mode": "demand"},
    apply_value_map={"enabled": "start", "disabled": "stop"},
)

# =============================================================================
# Background Apps Settings
# =============================================================================

# Windows 11 has no global "background apps" switch any more; the HKCU
# GlobalUserDisabled value behind the Windows 10 toggle is not the documented
# control. The documented one is the AppPrivacy policy, where 2 = Force Deny
# (Microsoft Learn, "Manage connections from Windows operating system components
# to Microsoft services", section 18.21). Reset deletes it: no policy is stock.
BACKGROUND_APPS = SettingExecutor(
    id="services:background_apps",
    category=SettingCategory.SYSTEM,
    display_name="Background Apps",
    short_name="Background apps",
    description="Whether Store apps may keep running after they are closed. Off, they stop running "
    "behind a game, and they also stop sending notifications until they are opened.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows/privacy/manage-connections-from-windows-operating-system-components-to-microsoft-services",
    ],
    current_impact="Enabled: Store apps keep running in the background after they are closed",
    recommended_impact="Disabled: Store apps run only while open → less background RAM and CPU",
    scope=SettingScope.COMPLETE,
    category_order=3,
    effect="Stops Store apps from running in the background through the documented policy",
    impact_scores={"ram_saved": "50-200MB", "cpu_usage": -0.5, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy",
        "name": "LetAppsRunInBackground",
        "hive": "HKLM",
    },
    # 0 = user in control, 1 = force allow, 2 = force deny, absent = no policy.
    value_map={
        2: "disabled",
        "2": "disabled",
        1: "enabled",
        "1": "enabled",
        0: "enabled",
        "0": "enabled",
        None: "enabled",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy",
        "name": "LetAppsRunInBackground",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 2, "enabled": None},
)

SERVICE_UCPD = SettingExecutor(
    id="services:UCPD",
    category=SettingCategory.SYSTEM,
    display_name="User Choice Protection Driver (UCPD)",
    short_name="Browser-choice protection driver",
    description="A hidden driver that silently blocks changes to default app associations, so a change "
    "appears to apply and is quietly reverted. Off, the settings a user makes actually hold.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    # A Microsoft protection driver with no performance cost: a guard.
    recommended_value="enabled",
    requires_reboot=True,  # Kernel driver - change requires reboot to take effect
    current_impact="Enabled: Blocks registry changes to default browser/app settings",
    recommended_impact="Disabled: Full control over default app associations "
    "(takes effect after reboot)",
    scope=SettingScope.COMPLETE,
    category_order=16,
    effect="Disables UCPD kernel driver startup to allow full control "
    "over default app settings after reboot",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
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
    short_name="Telemetry scheduled tasks",
    description="Scheduled tasks that gather and upload usage data, all serving one purpose and so switched "
    "off together. Off, they stop waking the machine to report on it.",
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

# The documented control is the "Turn off the advertising ID" policy; the
# AdvertisingInfo\Enabled value under HKLM\...\CurrentVersion is not read per
# user and was never what the Settings toggle writes.
PRIVACY_ADVERTISING_ID = SettingExecutor(
    id="privacy:advertising_id",
    category=SettingCategory.SYSTEM,
    display_name="Advertising ID",
    short_name="Advertising ID",
    description="A unique ID apps can read to follow one person across apps for ads. Off by policy, no "
    "app on this machine can read it.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows/privacy/manage-connections-from-windows-operating-system-components-to-microsoft-services",
    ],
    current_impact="Enabled: Apps can track you with unique advertising ID",
    recommended_impact="Disabled: No cross-app ad tracking → better privacy",
    scope=SettingScope.COMPLETE,
    category_order=16,
    effect="Turns off the advertising ID for every account through the documented policy",
    impact_scores={"privacy": "improved", "cpu_usage": -0.1},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\AdvertisingInfo",
        "name": "DisabledByGroupPolicy",
        "hive": "HKLM",
    },
    value_map={1: "disabled", "1": "disabled", 0: "enabled", "0": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\AdvertisingInfo",
        "name": "DisabledByGroupPolicy",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 1, "enabled": None},
)

PRIVACY_ACTIVITY_HISTORY = SettingExecutor(
    id="privacy:activity_history",
    category=SettingCategory.SYSTEM,
    display_name="Activity History (Timeline)",
    short_name="Activity history",
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
    apply_value_map={"disabled": 0, "enabled": None},
)

PRIVACY_CONSUMER_FEATURES = SettingExecutor(
    id="privacy:consumer_features",
    category=SettingCategory.SYSTEM,
    display_name="Windows Consumer Features",
    short_name="Suggested apps and offers",
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
    apply_value_map={"disabled": 1, "enabled": None},
)

PRIVACY_EDGE_TELEMETRY = SettingExecutor(
    id="privacy:edge_telemetry",
    category=SettingCategory.SYSTEM,
    display_name="Microsoft Edge Telemetry",
    short_name="Edge telemetry",
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
    apply_value_map={"disabled": 0, "enabled": None},
)


PRIVACY_INPUT_PERSONALIZATION = SettingExecutor(
    id="privacy:input_personalization",
    category=SettingCategory.SYSTEM,
    display_name="Typing & Inking Personalization",
    short_name="Typing personalization",
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


# 0 ("Security") is honoured on Enterprise and Education only; Home and Pro read
# it as 1. Writing 1 states what every edition will actually do, so the
# recommendation reads back the same everywhere. 0 and 1 both display as the
# minimum, because on the editions most players run they are the same level.
PRIVACY_ALLOW_TELEMETRY = SettingExecutor(
    id="privacy:allow_telemetry",
    category=SettingCategory.SYSTEM,
    display_name="Diagnostic Data Level (Policy)",
    short_name="Diagnostic data level",
    description="How much diagnostic data Windows sends. Required is the lowest level Home and Pro honour, "
    "and the policy keeps it there whatever Settings says.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows/privacy/manage-connections-from-windows-operating-system-components-to-microsoft-services",
    ],
    current_impact="Enabled: Optional diagnostic data may be collected",
    recommended_impact="Disabled: Required diagnostic data only, the minimum Home and Pro allow",
    scope=SettingScope.COMPLETE,
    category_order=25,
    effect="Limits Windows diagnostic data to the required level by policy",
    impact_scores={"privacy": "improved", "cpu_usage": -0.2},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\DataCollection",
        "name": "AllowTelemetry",
        "hive": "HKLM",
    },
    value_map={
        0: "disabled",
        "0": "disabled",
        1: "disabled",
        "1": "disabled",
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
    apply_value_map={"disabled": 1, "enabled": None},
)

PRIVACY_COPILOT = SettingExecutor(
    id="privacy:copilot",
    category=SettingCategory.SYSTEM,
    display_name="Windows Copilot",
    short_name="Windows Copilot",
    description="The assistant keeps a background process and a taskbar entry running whether or not it is "
    "used. Off, that process stops taking memory and CPU from the game.",
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
    apply_value_map={"disabled": 1, "enabled": None},
)

PRIVACY_WINDOWS_ADS = SettingExecutor(
    id="privacy:windows_ads",
    category=SettingCategory.SYSTEM,
    display_name="Windows Ads & Suggestions",
    short_name="Windows ads and tips",
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

# Windows 11 search ignores the older DisableWebSearch and BingSearchEnabled
# values; the policy it honours is "Turn off display of recent search entries
# in the File Explorer search box" (WindowsExplorer.admx), which also removes
# web suggestions from the taskbar and Start search. Per user, read at sign-in.
PRIVACY_WEB_SEARCH_POLICY = SettingExecutor(
    id="privacy:web_search_policy",
    category=SettingCategory.SYSTEM,
    display_name="Web Results in Windows Search",
    short_name="Web results in search",
    description="Whether typing in Start or taskbar search also sends the text to Bing for web results. Off, "
    "search stays on this machine; it takes effect at the next sign-in.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=True,
    current_impact="Enabled: Start and taskbar searches query Bing as you type",
    recommended_impact="Disabled: Local results only → nothing typed leaves the machine",
    scope=SettingScope.COMPLETE,
    category_order=28,
    effect="Removes web suggestions from Start and taskbar search",
    impact_scores={"privacy": "improved", "cpu_usage": -0.1},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\Explorer",
        "name": "DisableSearchBoxSuggestions",
        "hive": "HKCU",
    },
    value_map={1: "disabled", "1": "disabled", 0: "enabled", "0": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\Explorer",
        "name": "DisableSearchBoxSuggestions",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 1, "enabled": None},
)

# =============================================================================
# Performance Settings
# =============================================================================

PERF_ACCESSIBILITY_POPUPS = SettingExecutor(
    id="perf:accessibility_popups",
    category=SettingCategory.SYSTEM,
    display_name="Accessibility Key Popups",
    short_name="Sticky-keys pop-ups",
    description="Tapping Shift five times in a match opens a Sticky Keys dialog, which takes focus away from "
    "the game. Off, the shortcut stops interrupting.",
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
    short_name="Mouse acceleration",
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
    short_name="Fast startup",
    description="Shutdown keeps the old kernel state and restores it next boot, so a driver update never "
    "fully takes effect and hardware faults survive a restart. Off, a shutdown is a real one.",
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


# === SvcHost Split Threshold ===
# Windows splits services into separate svchost.exe processes when RAM < threshold.
# Setting to max (0xFFFFFFFF) combines all services into fewer processes.
# Benefit: ~100-300MB RAM saved, fewer context switches.
# Microsoft-supported setting, risk-free.
PERF_SVCHOST_SPLIT = SettingExecutor(
    id="perf:svchost_split_threshold",
    category=SettingCategory.SYSTEM,
    display_name="SvcHost Split Threshold",
    short_name="Service process grouping",
    description="Combines Windows services into fewer processes. Saves ~100-300MB RAM.",
    value_type=SettingValueType.CHOICE,
    choices=("split", "combined"),
    default_value="split",
    # Microsoft documents service separation as a reliability gain: with
    # services combined one crash takes many down. A guard; stock is Windows
    # sizing it to this machine's RAM, restored by deleting the value.
    recommended_value="split",
    requires_reboot=True,
    current_impact="Split: Services in many svchost.exe processes",
    recommended_impact="Combined: Services merged → ~100-300MB RAM saved, fewer context switches",
    scope=SettingScope.RECOMMENDED,
    category_order=36,
    effect="Combines Windows services into fewer processes to save RAM and reduce overhead",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
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
    apply_value_map={"combined": 0xFFFFFFFF, "split": None},
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
    short_name="Drivers from Windows Update",
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
    apply_value_map={"blocked": 1, "allowed": None},
)

SYSTEM_DELIVERY_OPTIMIZATION = SettingExecutor(
    id="system:delivery_optimization",
    category=SettingCategory.SYSTEM,
    display_name="Delivery Optimization (P2P Updates)",
    short_name="Update sharing (P2P)",
    description="Windows Update P2P sharing uploads updates to other PCs over the internet, consuming upload bandwidth during gaming.",
    value_type=SettingValueType.CHOICE,
    choices=("internet", "lan_only", "off"),
    default_value="lan_only",
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
        None: "lan_only",
    },
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization",
        "name": "DODownloadMode",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"off": 0, "lan_only": None, "internet": 3},
)

SYSTEM_DO_BACKGROUND_BANDWIDTH = SettingExecutor(
    id="system:delivery_optimization_bandwidth",
    category=SettingCategory.SYSTEM,
    display_name="Windows Update Background Bandwidth Cap",
    short_name="Update download cap",
    description="Caps Windows Update background downloads at 20% of the link. Uncapped, an update fills the "
    "queue and every other packet, game traffic included, waits behind it.",
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
    apply_value_map={"capped": 20, "unlimited": None},
)

SYSTEM_ONEDRIVE_UPLOAD_LIMIT = SettingExecutor(
    id="system:onedrive_upload_limit",
    category=SettingCategory.SYSTEM,
    display_name="OneDrive Upload Rate Cap",
    short_name="OneDrive upload cap",
    description="Caps the OneDrive sync client at 30% of upload throughput. A sync burst saturates the small "
    "uplink of home fibre and delays every packet leaving the machine, game traffic included.",
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
    apply_value_map={"capped": 30, "unlimited": None},
)

SYSTEM_WINDOWS_UPDATE_MODE = SettingExecutor(
    id="system:windows_update_mode",
    category=SettingCategory.SYSTEM,
    display_name="Windows Update Mode",
    short_name="Windows Update behaviour",
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
    apply_value_map={"notify_only": 2, "automatic": None},
)

SYSTEM_COINSTALLERS = SettingExecutor(
    id="system:coinstallers",
    category=SettingCategory.SYSTEM,
    display_name="Hardware Co-Installers",
    short_name="Driver extra-software installs",
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
    short_name="Windows widgets",
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
    apply_value_map={"enabled": None, "disabled": 0},
)

SYSTEM_FILE_EXPLORER_LAUNCH = SettingExecutor(
    id="system:file_explorer_launch",
    category=SettingCategory.SYSTEM,
    display_name="File Explorer Default View",
    short_name="File Explorer opens to",
    description="Home queries cloud and recent-file providers every time a window opens, which is the pause "
    "before anything appears. This PC shows the drives immediately.",
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
    short_name="Hyper-V virtualization",
    description="Runs Windows as a guest under the Hyper-V hypervisor, which costs CPU-bound frames. With "
    "Memory Integrity on, the hypervisor stays for security and part of that cost remains.",
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
    # Gated on *anything* using virtualization, not on Docker alone. Docker was
    # the only consumer this ever checked, and it checked it by hardcoded path —
    # so a per-user Docker install, and every WSL distribution ever, went unseen
    # and this setting recommended pulling the floor out from under them.
    applicable_conditions={"requires_admin": True, "feature_absent": VIRTUALIZATION_IN_USE},
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
    #
    # The feature can be installed while no hypervisor runs (hypervisorlaunchtype
    # off), and then there is no overhead to remove. Win32_ComputerSystem's
    # HypervisorPresent answers that without elevation, so a machine with no
    # hypervisor reads as already optimal before the feature query is spent.
    detect_command=(
        "try { "
        "if (-not (Get-CimInstance Win32_ComputerSystem -ErrorAction Stop).HypervisorPresent) "
        "{ 'disabled'; return }; "
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
    short_name="Virtual machine platform",
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
    # See Hyper-V above. VirtualMachinePlatform is the feature WSL2 and Docker
    # Desktop both sit directly on top of, so this one is the more damaging of
    # the two to recommend blind.
    applicable_conditions={"requires_admin": True, "feature_absent": VIRTUALIZATION_IN_USE},
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
    component="memory",
    category=SettingCategory.SYSTEM,
    display_name="XMP / EXPO Profile (RAM Speed)",
    short_name="RAM rated-speed profile (XMP)",
    description="Whether RAM runs at its rated XMP or EXPO speed or at the slower JEDEC default. A BIOS "
    "update silently resets it.",
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
    effect="In BIOS, under Advanced > DRAM Configuration, set the XMP/EXPO profile to Profile 1 or the "
    "highest offered",
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
    component="cpu",
    category=SettingCategory.SYSTEM,
    display_name="Thermal Condition",
    short_name="CPU thermal headroom",
    description="Whether the machine is currently giving up clock speed to stay cool. Throttling is how a "
    "frame rate decays in minute forty of a match, long after any setting was changed.",
    value_type=SettingValueType.CHOICE,
    choices=("not_throttling", "throttling"),
    default_value="not_throttling",
    recommended_value="not_throttling",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-perfformatteddata",
        "https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/design-guide-thermal",
    ],
    current_impact="Throttling: the machine is holding clocks down to stay cool, and frames go with them",
    recommended_impact="Not throttling: the machine is free to hold its clocks through a whole match",
    scope=SettingScope.COMPLETE,
    category_order=53,
    effect="Clear dust from the heatsinks and fans, and replace thermal paste older than three years",
    impact_scores={
        "fps_sustained": "-25 to -50% if throttling",
        "latency_ms": 5,
        "stability": "degraded if overheating",
    },
    is_readonly=True,
    detect_type=DetectType.POWERSHELL,
    # Two sources, and a verdict that is a fact rather than an inference.
    #
    # MSAcpi_ThermalZoneTemperature answers only to an elevated caller. Measured
    # on the same machine within minutes: zero zones unelevated, two zones
    # elevated. fpstune runs elevated, so this is the reading it normally gets —
    # and the earlier note here, that the class was simply absent on this
    # hardware, was drawn from an unelevated probe and was wrong about why.
    #
    # The performance counter stays as the fallback, because it needs no
    # elevation and reads the same ACPI zones through another provider
    # (`\_TZ.TZ00` and `\_SB.ECTZ`, both live: three samples four seconds apart
    # moved 354.2 K, 355.2 K, 354.2 K). It is what keeps the advisory answering
    # when the app is started without administrator rights, instead of the whole
    # check going quiet for a reason nobody could see.
    #
    # The verdict comes from ThrottleReasons and PercentPassiveLimit, not from a
    # temperature threshold, because those two *state* whether the firmware is
    # holding the machine back. A threshold over a zone temperature would be an
    # inference about a sensor whose meaning varies by board: the zone above idles
    # at 81 °C on hardware that is not throttling at all, and a rule that called
    # that a warning would be wrong on exactly the machine it was read from. The
    # temperature still travels, as the finding's context, labelled as the zone
    # reading it is.
    detect_command=(
        "$acpi = Get-CimInstance -Namespace root/wmi "
        "-ClassName MSAcpi_ThermalZoneTemperature -EA SilentlyContinue "
        "| Sort-Object CurrentTemperature -Descending | Select-Object -First 1; "
        "$perf = Get-CimInstance "
        "-ClassName Win32_PerfFormattedData_Counters_ThermalZoneInformation -EA SilentlyContinue "
        "| Sort-Object HighPrecisionTemperature -Descending | Select-Object -First 1; "
        "$celsius = $null; $zone = ''; "
        # The zone label names whichever source supplied the temperature. It used
        # to prefer the counter's name whenever the counter existed, so an
        # elevated run reading the ACPI class still reported the counter's zone —
        # a label describing a different sensor from the number beside it.
        "if ($acpi) { $celsius = [math]::Round(($acpi.CurrentTemperature / 10) - 273.15, 0); "
        "  $zone = $acpi.InstanceName } "
        "elseif ($perf -and $perf.HighPrecisionTemperature) { "
        "  $celsius = [math]::Round(($perf.HighPrecisionTemperature / 10) - 273.15, 0); "
        "  $zone = $perf.Name } "
        "$throttling = $null; "
        "if ($perf) { $throttling = ($perf.ThrottleReasons -ne 0) -or ($perf.PercentPassiveLimit -lt 100) } "
        "if ($null -eq $celsius -and $null -eq $throttling) { 'not_available' } else { "
        "  Write-Output ('FPSTUNE_FINDING: ' + (@{kind='thermal'; celsius=$celsius; "
        "throttling=$throttling; zone=$zone} | ConvertTo-Json -Compress)); "
        "  if ($throttling -eq $true) { 'throttling' } else { 'not_throttling' } "
        "}"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="",
    apply_args={},
    apply_value_map={},
)

# =============================================================================
# Startup Apps Advisory (Detect-Only)
# =============================================================================

# Detect-only on purpose. Which apps start with Windows is a per-machine list
# of names, not one value a setting can own, and the right answer for each
# entry (a chat client, a mouse driver's helper, a VPN) is the user's call.
# What fpstune can do without guessing is count what runs and name it, so the
# choice is made in Task Manager > Startup apps, which writes the same
# StartupApproved flags read here and keeps every entry reversible.
#
# Sources read: the Run keys Microsoft documents (HKCU, HKLM and the 32-bit
# HKLM view) and both Startup folders. An entry Task Manager turned off stays
# where it is, flagged in Explorer\StartupApproved: byte 0 with bit 0 set is
# "disabled" (0x02 / 0x06 enabled, 0x03 disabled; no value at all is enabled).
# That layout is undocumented; it is the one Task Manager writes, read the
# same way by every startup manager that preserves entries.
#
# Security software is never listed as a candidate: Windows Security's own
# tray entry, and any entry that launches from the folder of an antivirus
# product Windows Security Center reports (its root/SecurityCenter2 WMI
# namespace — not on Microsoft Learn, which documents only the wscapi health
# calls, but the registry every antivirus product registers itself in). An
# unreadable namespace leaves the list unfiltered, never empty. Derived on the
# machine, not from a vendor list (C10).
SYSTEM_STARTUP_APPS = SettingExecutor(
    id="system:startup_apps",
    category=SettingCategory.SYSTEM,
    display_name="Startup Apps",
    short_name="Apps starting with Windows",
    description="The third-party apps that start every time you sign in. Each one takes memory and "
    "processor time in the background for the whole session, a match included.",
    value_type=SettingValueType.CHOICE,
    choices=("none_at_startup", "apps_at_startup"),
    default_value="none_at_startup",
    recommended_value="none_at_startup",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows/win32/setupapi/run-and-runonce-registry-keys",
        "https://learn.microsoft.com/en-us/windows/win32/api/wscapi/",
    ],
    current_impact="Apps at startup: each keeps memory and background processor time for the session",
    recommended_impact="None at startup: the session's memory and processor time stay with the game",
    scope=SettingScope.COMPLETE,
    category_order=54,
    effect="Turn off the startup apps you do not need in Task Manager > Startup apps",
    impact_scores={"ram_saved": "20-200MB", "stability": "high"},
    is_readonly=True,
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$ErrorActionPreference = 'SilentlyContinue'; "
        "$cv = 'Software\\Microsoft\\Windows\\CurrentVersion'; "
        "$approvedRoot = $cv + '\\Explorer\\StartupApproved'; "
        "$guard = @(); "
        "foreach ($av in @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct)) { "
        "  foreach ($p in @($av.pathToSignedProductExe, $av.pathToSignedReportingExe)) { "
        "    if ($p) { $d = Split-Path -Parent ([Environment]::ExpandEnvironmentVariables([string]$p)); "
        "      if ($d) { $guard += $d.ToLowerInvariant() } } } }; "
        "function Test-Kept($name, $command) { "
        "  if ($name -eq 'SecurityHealth') { return $true }; "
        "  $c = ([string]$command).ToLowerInvariant(); "
        "  foreach ($d in $guard) { if ($c.Contains($d)) { return $true } }; return $false }; "
        "function Test-Off($approved, $name) { "
        "  $v = (Get-ItemProperty -LiteralPath $approved -Name $name).$name; "
        "  return (($v -is [byte[]]) -and $v.Length -gt 0 -and (($v[0] -band 1) -eq 1)) }; "
        "$apps = New-Object System.Collections.Generic.List[string]; "
        "$runs = @("
        "  @(('HKCU:\\' + $cv + '\\Run'), ('HKCU:\\' + $approvedRoot + '\\Run')), "
        "  @(('HKLM:\\' + $cv + '\\Run'), ('HKLM:\\' + $approvedRoot + '\\Run')), "
        "  @('HKLM:\\Software\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Run', "
        "    ('HKLM:\\' + $approvedRoot + '\\Run32'))); "
        "foreach ($r in $runs) { "
        "  $key = Get-Item -LiteralPath $r[0]; if (-not $key) { continue }; "
        "  foreach ($n in $key.GetValueNames()) { "
        "    if (-not $n) { continue }; "
        "    if (Test-Kept $n $key.GetValue($n)) { continue }; "
        "    if (Test-Off $r[1] $n) { continue }; $apps.Add($n) } }; "
        # The console user's Startup folder, through the redirected HKCU drive:
        # [Environment]::GetFolderPath would name the elevated account's.
        "$userStartup = (Get-ItemProperty -LiteralPath ('HKCU:\\' + $cv + '\\Explorer\\Shell Folders')).Startup; "
        "$folders = @("
        "  @($userStartup, ('HKCU:\\' + $approvedRoot + '\\StartupFolder')), "
        "  @([Environment]::GetFolderPath('CommonStartup'), ('HKLM:\\' + $approvedRoot + '\\StartupFolder'))); "
        "foreach ($f in $folders) { "
        "  if (-not $f[0]) { continue }; "
        "  foreach ($file in @(Get-ChildItem -LiteralPath $f[0] -File)) { "
        "    if ($file.Name -ieq 'desktop.ini') { continue }; "
        "    if (Test-Off $f[1] $file.Name) { continue }; "
        "    $apps.Add([IO.Path]::GetFileNameWithoutExtension($file.Name)) } }; "
        "$names = @($apps | Sort-Object -Unique); "
        "Write-Output ('FPSTUNE_FINDING: ' + (@{kind='startup_apps'; count=$names.Count; "
        "  names=@($names | Select-Object -First 12)} | ConvertTo-Json -Compress)); "
        "if ($names.Count -gt 0) { 'apps_at_startup' } else { 'none_at_startup' }"
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
    short_name="Network receive buffer",
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
    short_name="Network send buffer",
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
    short_name="Game traffic priority tag",
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
    short_name="Apps vs file-cache memory",
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
    SYSTEM_STARTUP_APPS,
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
    short_name="Windows component cleanup",
    description="Cleans the Windows component store, freeing 1-10 GB in 5-15 minutes. A reboot may be needed "
    "to reclaim all of it.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    # /ResetBase makes installed updates permanent (none can be uninstalled
    # afterwards): offered, never recommended.
    recommended_value=False,
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
    duration_estimate="5-15 min",
    progress_pattern=PERCENT_PROGRESS,
)

CLEANUP_TEMP = SettingExecutor(
    id="cleanup:temp_files",
    category=SettingCategory.MAINTENANCE,
    display_name="Temp Files",
    short_name="Temp files",
    description="Installers, updaters and games leave working files behind in the temp folders and never come "
    "back for them. Clearing them costs nothing and returns the space to the disk.",
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
    short_name="Event logs",
    description="Clears all Windows event logs (Application, System, Security, etc.). Frees disk space and speeds up Event Viewer.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    # Erases the evidence a crash or a failed boot leaves: never recommended.
    recommended_value=False,
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
    short_name="Error reports",
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
    short_name="Defender cache",
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
    short_name="Prefetch files",
    description="Clears the Windows prefetch files, which Windows rebuilds on its own. Useful after "
    "uninstalling software.",
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
    short_name="Browser caches",
    description="Clears the cache of Edge, Chrome, Brave and Firefox, which they rebuild as you browse. Frees "
    "significant disk space.",
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
    short_name="Update download cache",
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
    short_name="Update sharing cache",
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
    short_name="Thumbnail cache",
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
    short_name="Crash memory dumps",
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
    short_name="Restore-point space on data drives",
    description="Caps Volume Shadow Copy storage to 10% of capacity on non-system drives. Windows deletes the oldest restore points to fit, freeing disk space.",
    value_type=SettingValueType.BOOL,
    choices=(),
    default_value=False,
    # Deletes restore points on data drives: offered, never recommended.
    recommended_value=False,
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
    short_name="Discord cache",
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
    short_name="Epic launcher cache",
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
    short_name="Steam web cache",
    description="Clears Steam's browser and HTML cache, which rebuilds on next launch. Game files are "
    "untouched.",
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
    short_name="Python pip cache",
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
    short_name="npm cache",
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
    short_name="Yarn cache",
    description="Clears the Yarn package cache; packages re-download on the next install. Only present when "
    "Yarn is installed.",
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
    short_name="pnpm store",
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
    short_name="NuGet packages",
    description="Clears the NuGet package cache; packages re-download on the next build. Only present when "
    ".NET or Visual Studio is installed.",
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
    short_name="Maven repository",
    description="Clears the Maven local repository; dependencies re-download on the next build. Only present "
    "when Maven is installed.",
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
    short_name="Gradle cache",
    description="Clears the Gradle build cache and downloaded dependencies, which re-download on the next "
    "build. Only present when Gradle is installed.",
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
    short_name="Cargo registry",
    description="Clears the Cargo package registry cache; crates re-download on the next build. Only present "
    "when Rust is installed.",
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
    short_name="Battle.net cache",
    description="Clears the Battle.net launcher's HTTP and asset cache, which rebuilds on next launch. Fixes "
    "launcher crashes, missing icons and failed updates.",
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
    short_name="System file repair",
    description="Finds Windows system files that no longer match what Windows shipped and puts the originals "
    "back. A corrupted one shows up as a crash or a feature that stopped working.",
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
    duration_estimate="5-15 min",
    progress_pattern=PERCENT_PROGRESS,
)

MAINTENANCE_DISM_HEALTH = SettingExecutor(
    id="maintenance:dism_health",
    category=SettingCategory.MAINTENANCE,
    display_name="DISM Health Check",
    short_name="Windows image repair",
    description="A damaged Windows component store is what turns a routine update into a failed one, and it "
    "stays hidden until then. This reports the damage; nothing is changed.",
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
    duration_estimate="10-30 min",
    progress_pattern=PERCENT_PROGRESS,
)

# The threshold is 14 days, and it is derived from Windows' own schedule rather
# than from anything about an SSD: the `ScheduledDefrag` task runs weekly, so one
# missed week is a machine that was switched off for a holiday and two is a
# schedule that has stopped running. That is what this row detects — not a drive
# in trouble, but maintenance that is no longer happening. `executors/
# powershell_actions.py` carries the reading, the registry key it comes from and
# the three measurements that chose that key over the Defrag event log.
MAINTENANCE_SSD_RETRIM = SettingExecutor(
    id="maintenance:ssd_retrim",
    category=SettingCategory.MAINTENANCE,
    display_name="SSD TRIM Overdue",
    short_name="SSD retrim",
    description="Tells every SSD which blocks are free again, which Windows normally does weekly. "
    "A drive left without it slows down on writes as its spare blocks fill.",
    value_type=SettingValueType.STRING,
    choices=(),
    default_value=False,
    recommended_value=False,
    requires_reboot=False,
    is_action=True,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/powershell/module/storage/optimize-volume",
        "https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/defrag",
    ],
    current_impact="Overdue: The optimization schedule has not run, so free blocks stay unreported",
    recommended_impact="Run: Every SSD volume retrimmed → sustained write speed kept at the drive's own level",
    scope=SettingScope.RECOMMENDED,
    category_order=26,  # after the two Windows-image repairs
    effect="Runs Windows' own retrim on every SSD volume",
    # The same claim `storage:trim_enabled` makes, because it is the same
    # mechanism: that row keeps TRIM switched on, this one runs the pass that
    # switch enables. No number, because nothing here has measured one — C11
    # rule 1 forbids inventing the range that would look better in the tooltip.
    impact_scores={
        "storage_performance": "maintained",
        "ssd_longevity": "high",
        "stability": "high",
    },
    detect_type=DetectType.POWERSHELL,
    detect_command="maintenance_status",
    detect_args={"type": "ssd_trim"},
    # Empty on purpose: the reading is `overdue|<n> days`, `overdue|never`,
    # `ok|<n> days` or the `not_available` sentinel, and every one of them is
    # rendered as it stands. A map here would have to enumerate every day count.
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="ssd_retrim",
    apply_args={},
    apply_value_map={},
    duration_estimate="10-60 sec",
)


# A drift guard (consequence 2): memory compression is on by default on every
# Windows 11 client, at any RAM size, and turning it off is a staple of
# "optimizer" presets. Off, the memory manager answers pressure by writing
# pages to the page file instead of compressing them in RAM, and a game waits
# on the disk to get them back — the hitch this guard removes.
#
# Read and written through the MMAgent cmdlets, Microsoft's own interface for
# it. The setting is applied at the next start of the memory manager agent, so
# a reboot is asked for. It shares its fate with SysMain (disabling SysMain turns
# every MMAgent feature off, Enable-MMAgent starts SysMain again), which is why
# services:SysMain is a guard on the same side.
MEMORY_COMPRESSION = SettingExecutor(
    id="memory:compression",
    category=SettingCategory.SYSTEM,
    display_name="Memory Compression",
    short_name="RAM compression",
    description="Whether Windows compresses idle memory pages instead of writing them to the page file. "
    "Turned off, memory pressure goes to the disk, and a game waits on it to get those pages back.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=True,
    evidence_level="proven",
    sources=[
        "https://blogs.windows.com/windowsexperience/2015/08/18/announcing-windows-10-insider-preview-build-10525/",
        "https://learn.microsoft.com/en-us/powershell/module/mmagent/enable-mmagent",
        "https://learn.microsoft.com/en-us/powershell/module/mmagent/get-mmagent",
        "https://github.com/memstechtips/Winhance/issues/261",
    ],
    current_impact="Disabled: Memory pressure is paged to disk → hitches while pages come back",
    recommended_impact="Enabled: Windows' own state → idle pages are compressed in RAM",
    scope=SettingScope.RECOMMENDED,
    category_order=2,
    effect="Restores Windows memory compression if another tool turned it off",
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    # Microsoft's Get-MMAgent page lists the older features only; the
    # MemoryCompression property is what the cmdlet returns on Windows 10 and
    # 11. A build that returns no such property is not read as "disabled" —
    # that would have the guard write over a state it cannot see.
    detect_command=(
        "try { $m = Get-MMAgent -ErrorAction Stop; "
        "if ($null -eq $m.MemoryCompression) { 'not_available' } "
        "elseif ($m.MemoryCompression) { 'enabled' } else { 'disabled' } } "
        "catch { 'not_available' }"
    ),
    detect_args={},
    value_map={"enabled": "enabled", "disabled": "disabled"},
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "try { if ('%value%' -eq 'enabled') { Enable-MMAgent -MemoryCompression -ErrorAction Stop } "
        "else { Disable-MMAgent -MemoryCompression -ErrorAction Stop }; 'ok' } "
        "catch { 'error:' + $_.Exception.Message }"
    ),
    apply_args={},
    apply_value_map={"enabled": "enabled", "disabled": "disabled"},
)

# All system settings
MEMORY_SETTINGS: list[SettingExecutor] = [
    MEMORY_PURGE_STANDBY,
    MEMORY_COMPRESSION,
]

# =============================================================================
# MMCSS Service (Multimedia Class Scheduler - foundational for priority tweaks)
# =============================================================================

SERVICE_MMCSS = SettingExecutor(
    id="services:MMCSS",
    category=SettingCategory.SYSTEM,
    display_name="Multimedia Class Scheduler (MMCSS)",
    short_name="Multimedia scheduler service",
    description="Thread priority service for games and multimedia. "
    "Disabling breaks all MMCSS priority registry settings.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=True,
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
    # On Windows 11 MMCSS is a kernel driver (mmcss.sys), not a service:
    # Get-Service never lists it, so a service query read "not found" on every
    # machine and this guard never showed. Its Start value is the one switch.
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SYSTEM\CurrentControlSet\Services\MMCSS",
        "name": "Start",
        "hive": "HKLM",
    },
    value_map={2: "enabled", 3: "enabled", 4: "disabled", None: "not_available"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SYSTEM\CurrentControlSet\Services\MMCSS",
        "name": "Start",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"enabled": 2, "disabled": 4},
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

# Recall exists only where Windows installed its optional feature (Copilot+
# PCs). Everywhere else the policy is a value nothing reads, so the setting
# reports not_available instead of offering a no-op. Microsoft: with
# AllowRecallEnablement = 0 Recall is disabled and removed, after a restart.
PRIVACY_RECALL = SettingExecutor(
    id="privacy:recall",
    category=SettingCategory.SYSTEM,
    display_name="Windows Recall (AI Screenshot)",
    short_name="Windows Recall screenshots",
    description="On Copilot+ PCs, Recall can save periodic screenshots for AI search. The policy removes the "
    "feature, so it can neither be switched on nor spend disk and CPU on snapshots.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=True,
    evidence_level="proven",
    sources=["https://learn.microsoft.com/en-us/windows/client-management/manage-recall"],
    current_impact="Enabled: Recall can be switched on → snapshots spend disk space and CPU",
    recommended_impact="Disabled: Recall is removed after a restart → no snapshots, no index",
    scope=SettingScope.COMPLETE,
    category_order=16,
    effect="Removes Windows Recall through its documented policy",
    impact_scores={"privacy": "improved", "cpu_usage": -0.5},
    applicable_conditions={"requires_admin": True},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "try { $f = Get-WindowsOptionalFeature -Online -FeatureName 'Recall' -ErrorAction Stop } "
        "catch { $f = $null }; "
        "if (-not $f) { 'not_available' } else { "
        "$v = (Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsAI' "
        "-Name 'AllowRecallEnablement' -ErrorAction SilentlyContinue).AllowRecallEnablement; "
        "if ($null -ne $v -and $v -eq 0) { 'disabled' } else { 'enabled' } }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Policies\Microsoft\Windows\WindowsAI",
        "name": "AllowRecallEnablement",
        "hive": "HKLM",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0, "enabled": None},
)

PRIVACY_CAMERA_INDICATOR = SettingExecutor(
    id="privacy:camera_indicator",
    category=SettingCategory.SYSTEM,
    display_name="Camera On/Off Indicator",
    short_name="Camera use indicator",
    description="Puts a notification on screen whenever an app starts or stops using the camera. On a machine "
    "with no camera light, this is the only way to know it happened.",
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
    short_name="App launch tracking",
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
    short_name="Online speech recognition",
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
    short_name="Feedback pop-ups",
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


PRIVACY_APP_TELEMETRY = SettingExecutor(
    id="privacy:app_telemetry",
    category=SettingCategory.SYSTEM,
    display_name="Application Telemetry (AITEnable)",
    short_name="App compatibility telemetry",
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
    PRIVACY_INPUT_PERSONALIZATION,
    PRIVACY_ALLOW_TELEMETRY,
    PRIVACY_COPILOT,
    PRIVACY_WINDOWS_ADS,
    PRIVACY_WEB_SEARCH_POLICY,
    PRIVACY_RECALL,
    PRIVACY_CAMERA_INDICATOR,
    PRIVACY_APP_LAUNCH_TRACKING,
    PRIVACY_ONLINE_SPEECH,
    PRIVACY_FEEDBACK_REMINDERS,
    PRIVACY_APP_TELEMETRY,
]

PERF_STARTUP_DELAY = SettingExecutor(
    id="perf:startup_delay",
    category=SettingCategory.SYSTEM,
    display_name="Startup App Delay",
    short_name="Startup app delay",
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
    short_name="Num Lock at startup",
    description="Whether the numpad is active as soon as Windows starts. Off, a keybind on the numpad does "
    "nothing until the key is pressed once, which is found out mid-match.",
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

# NOC_GLOBAL_SETTING_TOASTS_ENABLED is the Settings > Notifications master
# switch: it silences every toast all day, not only during games. Windows'
# own Do Not Disturb already turns on by itself while a game runs fullscreen,
# so the honest offer is the master switch, named as what it is, for players
# who game windowed. Offered, never assumed: it also hides security alerts.
PERF_FOCUS_ASSIST = SettingExecutor(
    id="perf:focus_assist",
    category=SettingCategory.SYSTEM,
    display_name="All Notifications",
    short_name="All notifications",
    description="Turns every notification banner off, all the time, not only during games. Windows already "
    "mutes them in fullscreen games, so this matters for borderless and windowed play.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="likely",
    current_impact="Enabled: Notification banners can appear over a borderless or windowed game",
    recommended_impact="Disabled: No banners at all → nothing draws over the game",
    scope=SettingScope.COMPLETE,
    category_order=45,
    effect="Turns off all notification banners, including outside games",
    impact_scores={"fps_1_percent_low": "+0-1%", "latency_ms": 0.0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Notifications\Settings",
        "name": "NOC_GLOBAL_SETTING_TOASTS_ENABLED",
        "hive": "HKCU",
    },
    value_map={0: "disabled", "0": "disabled", 1: "enabled", "1": "enabled", None: "enabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": r"SOFTWARE\Microsoft\Windows\CurrentVersion\Notifications\Settings",
        "name": "NOC_GLOBAL_SETTING_TOASTS_ENABLED",
        "hive": "HKCU",
        "type": "REG_DWORD",
    },
    apply_value_map={"disabled": 0, "enabled": None},
)

PERF_VBS_CORE_ISOLATION = SettingExecutor(
    id="system:vbs_core_isolation",
    category=SettingCategory.SYSTEM,
    display_name="VBS / Core Isolation",
    short_name="Core isolation (VBS)",
    description="Whether Memory Integrity (hypervisor-enforced code integrity) is running. It is a "
    "security boundary, so fpstune reports it and never changes it.",
    value_type=SettingValueType.CHOICE,
    choices=("enabled", "disabled"),
    default_value="enabled",
    recommended_value="enabled",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/windows/security/hardware-security/enable-virtualization-based-protection-of-code-integrity",
    ],
    current_impact="Disabled: Kernel code integrity is not enforced by the hypervisor",
    recommended_impact="Enabled: Kernel code integrity stays enforced; turn it on in Windows Security if it is off",
    scope=SettingScope.COMPLETE,
    category_order=50,
    effect="In Windows Security, under Device security > Core isolation, turn Memory integrity on",
    # A red line in this project: never offered as a tweak, measured or not.
    impact_scores={"fps": "0%", "security": "kept"},
    is_readonly=True,
    # The running state, not the registry switch: the "Enabled" value can be
    # absent on a machine where HVCI runs, and present on one where the
    # hypervisor refused to start it. Win32_DeviceGuard lists 2 (HVCI) among
    # SecurityServicesRunning only when it is actually enforced.
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$g = Get-CimInstance -Namespace root\\Microsoft\\Windows\\DeviceGuard "
        "-ClassName Win32_DeviceGuard -ErrorAction SilentlyContinue; "
        "if (-not $g) { 'not_available' } "
        "elseif ($g.SecurityServicesRunning -contains 2) { 'enabled' } else { 'disabled' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command="",
    apply_args={},
    apply_value_map={},
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
    short_name="Shutdown wait for services",
    description="How long shutdown lets each service finish. Shorter waits kill services mid-write, which "
    "can leave a volume dirty and force a disk check at boot.",
    value_type=SettingValueType.CHOICE,
    choices=("stock", "changed"),
    default_value="stock",
    recommended_value="stock",
    requires_reboot=False,
    evidence_level="proven",
    sources=[
        "https://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/shutdown-takes-long-time"
    ],
    current_impact="Changed: services can be killed before they finish writing at shutdown",
    recommended_impact="5000 ms (Windows default): every service gets the time Windows gives it",
    scope=SettingScope.ESSENTIAL,
    category_order=30,
    effect="Restores Windows' own 5-second service shutdown wait",
    # A guard. Fpstune 0.1.0 recommended 2000 ms here; this puts that back.
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": CONTROL_KEY, "name": "WaitToKillServiceTimeout", "hive": "HKLM"},
    value_map={"5000": "stock", 5000: "stock", None: "stock", UNMAPPED: "changed"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={
        "path": CONTROL_KEY,
        "name": "WaitToKillServiceTimeout",
        "hive": "HKLM",
        "type": "REG_SZ",
    },
    apply_value_map={"stock": "5000"},
)

SHUTDOWN_APP_TIMEOUT = SettingExecutor(
    id="perf:shutdown_app_timeout",
    category=SettingCategory.SYSTEM,
    display_name="App Shutdown Timeout",
    short_name="Shutdown wait for apps",
    description="How long Windows waits for programs to close, and to answer, before ending them. Shorter "
    "waits end programs that are still saving, so the values are removed and Windows' own apply again.",
    value_type=SettingValueType.CHOICE,
    choices=("stock", "changed"),
    default_value="stock",
    recommended_value="stock",
    requires_reboot=False,
    evidence_level="proven",
    current_impact="Changed: programs can be ended while they are still saving",
    recommended_impact="Windows default: programs get the time Windows gives them to save and close",
    scope=SettingScope.ESSENTIAL,
    category_order=31,
    effect="Restores Windows' own wait for programs at shutdown",
    # A guard; 0.1.0 recommended 2000 ms for both values. One concept, two
    # values Windows reads together (WaitToKillAppTimeout, HungAppTimeout).
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    detect_type=DetectType.POWERSHELL,
    detect_command=(
        "$d = Get-ItemProperty -Path 'HKCU:\\Control Panel\\Desktop' -ErrorAction SilentlyContinue; "
        "if ($null -eq $d.WaitToKillAppTimeout -and $null -eq $d.HungAppTimeout) { 'stock' } else { 'changed' }"
    ),
    detect_args={},
    value_map={},
    apply_type=DetectType.POWERSHELL,
    apply_command=(
        "foreach ($n in 'WaitToKillAppTimeout', 'HungAppTimeout') { "
        "Remove-ItemProperty -Path 'HKCU:\\Control Panel\\Desktop' -Name $n -ErrorAction SilentlyContinue }; "
        "'ok'"
    ),
    apply_args={},
    apply_value_map={},
    # The script removes both values whatever it is asked for, so "changed" is
    # something to detect, never something to restore.
    unwritable_values=("changed",),
)

SHUTDOWN_AUTO_END_TASKS = SettingExecutor(
    id="perf:shutdown_auto_end_tasks",
    category=SettingCategory.SYSTEM,
    display_name="Auto-End Tasks on Shutdown",
    short_name="Force-close on shutdown",
    description="Whether shutdown ends programs that have not closed without asking. Ending them loses "
    "unsaved work and interrupts their writes, so Windows' own behaviour, which asks, is restored.",
    value_type=SettingValueType.CHOICE,
    choices=("disabled", "enabled"),
    default_value="disabled",
    recommended_value="disabled",
    requires_reboot=False,
    evidence_level="proven",
    current_impact="Enabled: programs are ended at shutdown, unsaved work and all",
    recommended_impact="Disabled (Windows default): Windows asks before ending a program",
    scope=SettingScope.ESSENTIAL,
    category_order=32,
    effect="Restores Windows' own prompt before ending programs at shutdown",
    # A guard; 0.1.0 recommended "enabled".
    impact_scores={"latency_ms": 0.0, "stability": "high"},
    detect_type=DetectType.REGISTRY,
    detect_command="",
    detect_args={"path": DESKTOP_KEY, "name": "AutoEndTasks", "hive": "HKCU"},
    value_map={"1": "enabled", "0": "disabled", None: "disabled"},
    apply_type=DetectType.REGISTRY,
    apply_command="",
    apply_args={"path": DESKTOP_KEY, "name": "AutoEndTasks", "hive": "HKCU", "type": "REG_SZ"},
    apply_value_map={"enabled": "1", "disabled": None},
)

GPU_TDR_DELAY = SettingExecutor(
    id="perf:gpu_tdr_delay",
    component="gpu",
    category=SettingCategory.SYSTEM,
    display_name="GPU TDR Delay",
    short_name="GPU hang tolerance",
    description="Extends the GPU driver timeout (TDR) from Windows' 2 seconds to 10. DX12 games can stall the "
    "GPU longer than 2 s, and the forced driver reset surfaces as a Dev Error or black screen.",
    value_type=SettingValueType.CHOICE,
    choices=("default", "extended"),
    default_value="default",
    # Microsoft: end users should not change TDR keys. A guard: a longer
    # delay only lengthens a hang, and the stock value is restored by deleting.
    recommended_value="default",
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
    impact_scores={"latency_ms": 0.0, "stability": "high"},
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
    apply_value_map={"default": None, "extended": 10},
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
    short_name="NVIDIA shader cache",
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
    short_name="AMD shader cache",
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
    short_name="DirectX shader cache",
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
    short_name="Intel shader cache",
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
    short_name="Docker unused data",
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
)

CLEANUP_DOCKER_PRUNE_ALL = SettingExecutor(
    id="cleanup:docker_prune_all",
    category=SettingCategory.MAINTENANCE,
    display_name="Docker All Unused Images (Prune -a)",
    short_name="Docker all unused images",
    description="Runs docker system prune -a, removing every image no container uses, not only dangling ones. "
    "Named volumes and running containers survive; removed images re-pull or rebuild on next use.",
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
)

CLEANUP_WSL_COMPACT = SettingExecutor(
    id="cleanup:wsl_compact",
    category=SettingCategory.MAINTENANCE,
    display_name="WSL / Docker Disk Compact",
    short_name="WSL disk compact",
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
    MAINTENANCE_SSD_RETRIM,
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

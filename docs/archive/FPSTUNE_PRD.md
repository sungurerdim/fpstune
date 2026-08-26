# fpstune - Proje Dokümanı

## Proje Özeti
**fpstune** - **Windows 11 (21H2+)** odaklı oyun performans optimizasyon aracı. Windows 10 (1903+) temel uyumluluk ile desteklenir. Sisteme zarar vermeyen, geri alınabilir ve UX'e negatif etki etmeyen tweaklerden oluşur.

## Araştırma Sonuçları ve Doğrulama

### Tier 1: Doğrulanmış Faydası Olan Optimizasyonlar

| Tweak | Kaynak | Doğrulanmış Fayda |
|-------|--------|-------------------|
| HPET Devre Dışı | [XbitLabs](https://www.xbitlabs.com/how-to-get-better-latency-in-windows/) | %10-20 FPS artışı (Fortnite benchmark) |
| Timer Resolution 0.5ms | [TimerResolution.com](https://timerresolution.com/) | Input lag azalması, frame consistency |
| SysMain Devre Dışı | [HP Tech Takes](https://www.hp.com/gb-en/shop/tech-takes/how-to-optimize-gaming-pc-disable-background-services) | RAM/CPU overhead azalması (SSD'li sistemlerde) |
| GPU Priority Registry | [GeekFlare](https://geekflare.com/gaming/windows-registry-hacks-to-improve-gaming/) | Stutter azalması, task switching iyileşmesi |

### Tier 2: Koşullu Fayda Sağlayan (Test Gerektiren)

| Tweak | Kaynak | Not |
|-------|--------|-----|
| `disabledynamictick yes` | [Blur Busters](https://forums.blurbusters.com/viewtopic.php?t=8643) | Hardware-dependent, bazı sistemlerde faydalı |
| `useplatformtick yes` | [Overclock.net](https://www.overclock.net/threads/win-10-1909-bcdedit-set-useplatformtick-yes-causes-input-lag.1742922/) | Win10 1909+ input lag riski - **VARSAYILAN OLARAK KAPALI** |
| HAGS | [PCWorld](https://www.pcworld.com/article/2339130/should-you-enable-hardware-accelerated-gpu-scheduling-in-windows-11.html) | RTX 30+ ve RX 6000+ için faydalı olabilir |

### Tier 3: Maintenance/Cleanup (Dolaylı Fayda)

| Tweak | Kaynak | Not |
|-------|--------|-----|
| DISM Cleanup | [Microsoft Learn](https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/clean-up-the-winsxs-folder) | Disk space recovery (~1-2GB), dolaylı performans |
| Telemetry Devre Dışı | [XDA](https://www.xda-developers.com/services-disabled-improve-windows-performance/) | CPU/network overhead azalması |

### RED FLAG: Kaçınılması Gereken Tweakler

| Tweak | Neden Kaçınılmalı |
|-------|------------------|
| `useplatformclock` | Eski, gereksiz, potansiyel sorun |
| Ultimate Performance Power Plan | High Performance'dan farkı yok ([Windows Forum](https://windowsforum.com/threads/ultimate-guide-to-boost-windows-11-performance-with-registry-service-tweaks.366250/)) |
| Nagle Algorithm (TcpNoDelay) | Sadece eski TCP oyunlarında faydalı |

---

## Teknik Spesifikasyon

### Desteklenen Platformlar
- Windows 10 (1903+)
- Windows 11 (21H2+)

### Gereksinimler
- Administrator privileges
- PowerShell 5.1+
- NVIDIA GPU (GTX 900+) veya AMD GPU (RX 400+) (opsiyonel)

---

## Modül Yapısı

### 1. Core System Tweaks

```powershell
# ===============================================
# TIMER / CLOCK OPTIMIZATIONS
# ===============================================

# HPET Devre Dışı (varsayılan olarak zaten off olabilir)
bcdedit /deletevalue useplatformclock

# Dynamic Tick Devre Dışı (opsiyonel, test gerektiren)
# bcdedit /set disabledynamictick yes

# Timer Resolution (0.5ms) - Windows 11 için GlobalTimerRes
# Registry: HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\kernel
# DWORD: GlobalTimerResolutionRequests = 1
```

### 2. GPU Priority & Scheduling

```powershell
# ===============================================
# GPU/CPU PRIORITY
# ===============================================

# Game Priority Boost
# Registry: HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games
# DWORD: GPU Priority = 8
# DWORD: Priority = 6
# STRING: Scheduling Category = "High"

# MMCSS System Profile
# Registry: HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile
# DWORD: SystemResponsiveness = 0  (0 = prioritize foreground apps)
```

### 3. Service Optimizations

```powershell
# ===============================================
# SERVICES TO DISABLE
# ===============================================

# SysMain (Superfetch) - SSD sistemlerde gereksiz
Set-Service -Name "SysMain" -StartupType Disabled
Stop-Service -Name "SysMain" -Force

# Telemetry
Set-Service -Name "DiagTrack" -StartupType Disabled
Stop-Service -Name "DiagTrack" -Force

# Connected User Experiences
Set-Service -Name "CDPUserSvc" -StartupType Disabled

# ===============================================
# SERVICES TO KEEP ENABLED
# ===============================================
# - Windows Defender (güvenlik)
# - Windows Audio (ses)
# - NVIDIA/AMD Display Driver services (GPU)
# - Plug and Play (donanım)
```

### 4. NVIDIA GPU Optimizations

```powershell
# ===============================================
# NVIDIA CONTROL PANEL EQUIVALENT SETTINGS
# ===============================================

# Registry Path: HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000

# Power Management Mode = Prefer Maximum Performance
# Low Latency Mode = Ultra (DX9/11 only)
# Threaded Optimization = On
# Shader Cache = On

# NVIDIA Profile Inspector Settings (nvidiaProfileInspector.exe ile)
# - Maximum Pre-Rendered Frames = 1
# - Power Management Mode = Prefer Maximum Performance
# - Shader Cache = On
# - Texture Filtering Quality = High Performance
# - Threaded Optimization = Auto
```

### 5. AMD GPU Optimizations

```powershell
# ===============================================
# AMD RADEON SETTINGS
# ===============================================

# Shader Cache Force ON
# Registry: HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0000\UMD
# Prevents aggressive shader cache deletion

# Anti-Lag: AMD Adrenalin üzerinden (GUI)
# - Enable Radeon Anti-Lag (veya Anti-Lag 2 desteklenen oyunlarda)
# - Disable Radeon Boost (input latency için)
# - Disable Radeon Chill (input latency için)
# - Disable Enhanced Sync (tearing tercih ediliyorsa)
```

### 6. Cleanup & Maintenance

```powershell
# ===============================================
# SYSTEM CLEANUP
# ===============================================

# Windows Component Cleanup
dism /online /cleanup-image /startcomponentcleanup

# Windows Update Cleanup (eski versiyonlara dönüşü engeller)
# dism /online /cleanup-image /startcomponentcleanup /resetbase

# Temp Files
Remove-Item -Path "$env:TEMP\*" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "C:\Windows\Temp\*" -Recurse -Force -ErrorAction SilentlyContinue
```

---

## CLI Tasarımı

### Komut Yapısı

```bash
# Tam optimizasyon (interaktif)
fpstune apply

# Belirli modüller
fpstune apply --module timer
fpstune apply --module game
fpstune apply --module gpu-nvidia
fpstune apply --module gpu-amd
fpstune apply --module services
fpstune apply --module cleanup

# GPU-specific
fpstune gpu --vendor nvidia --low-latency ultra --vsync off
fpstune gpu --vendor amd --anti-lag on --vsync off

# Durum kontrolü
fpstune status

# Geri alma
fpstune revert --module timer
fpstune revert --all

# Benchmark modu
fpstune benchmark --before
# ... oyun oyna ...
fpstune benchmark --after --compare
```

### Config Dosyası

```yaml
# ~/.fpstune/config.yaml

profile: gaming

modules:
  timer:
    enabled: true
    hpet: disabled
    dynamic_tick: default  # veya "disabled"
    resolution_ms: 0.5

  game:
    enabled: true
    game_mode: enabled
    game_bar: disabled
    hags: enabled

  gpu:
    vendor: auto  # nvidia, amd, auto
    nvidia:
      low_latency: ultra
      power_mode: maximum
      threaded_opt: on
      shader_cache: on
      vsync: off  # veya on, adaptive
      reflex: game  # game (oyun içi) veya driver (NV Control Panel)
    amd:
      anti_lag: on
      anti_lag_2: auto  # desteklenen oyunlarda
      shader_cache: on
      vsync: off

  services:
    disable:
      - SysMain
      - DiagTrack
    keep_enabled:
      - WinDefend
      - AudioSrv

  priority:
    gpu_priority: 8
    game_priority: 6
    system_responsiveness: 0

  cleanup:
    on_apply: true
    dism_cleanup: true
    temp_files: true

safety:
  create_restore_point: true
  backup_registry: true
```

---

## Güvenlik Önlemleri

### Uygulama Öncesi
1. **System Restore Point** oluştur
2. **Registry backup** al
3. **Current settings** kaydet (revert için)

### Revert Mekanizması
```powershell
# Her değişiklik için orijinal değer saklanır
# ~/.fpstune/backups/
#   ├── 2025-01-15_143022/
#   │   ├── registry.reg
#   │   ├── services.json
#   │   ├── bcdedit.txt
#   │   └── manifest.json
```

### Uyarı Gerektiren Durumlar
- HAGS etkinleştirilirken 8GB VRAM uyarısı
- useplatformtick için Windows version uyarısı
- Game Mode'un bazı oyunlarda (Warzone) stuttering yapabileceği uyarısı

---

## Test Stratejisi

### Benchmark Tools (Entegre Edilecek)
1. **CapFrameX** - Frame time analysis
2. **PresentMon** - Latency measurement
3. **LatencyMon** - DPC latency
4. **TimerBench** - Timer resolution

### Test Prosedürü
```bash
# 1. Baseline al
fpstune benchmark --baseline

# 2. Tek bir tweak uygula
fpstune apply --module timer

# 3. Test et (3 run minimum)
fpstune benchmark --run

# 4. Karşılaştır
fpstune benchmark --compare

# 5. Fayda varsa devam, yoksa revert
fpstune revert --module timer
```

---

## Dosya Yapısı (Önerilen)

```
fpstune/
├── src/
│   └── fpstune/
│       ├── __init__.py
│       ├── cli.py              # Click CLI
│       ├── core/
│       │   ├── __init__.py
│       │   ├── registry.py     # Registry operations
│       │   ├── services.py     # Service management
│       │   ├── bcdedit.py      # Boot config
│       │   └── dism.py         # System cleanup
│       ├── modules/
│       │   ├── __init__.py
│       │   ├── timer.py        # HPET, dynamic tick, resolution
│       │   ├── gpu_nvidia.py   # NVIDIA tweaks
│       │   ├── gpu_amd.py      # AMD tweaks
│       │   ├── services.py     # Service optimizations
│       │   ├── priority.py     # GPU/CPU priority
│       │   └── cleanup.py      # DISM, temp files
│       ├── safety/
│       │   ├── __init__.py
│       │   ├── backup.py       # Registry/settings backup
│       │   ├── restore.py      # Restore point creation
│       │   └── revert.py       # Revert mechanism
│       ├── benchmark/
│       │   ├── __init__.py
│       │   ├── runner.py       # Benchmark execution
│       │   └── compare.py      # Before/after comparison
│       └── utils/
│           ├── __init__.py
│           ├── admin.py        # Admin privilege check
│           ├── detect.py       # GPU/Windows detection
│           └── config.py       # YAML config handling
├── profiles/
│   ├── safe.yaml           # Minimal, safe tweaks only
│   ├── balanced.yaml       # Moderate optimization
│   └── aggressive.yaml     # All tweaks (advanced users)
├── tests/
├── pyproject.toml
└── README.md
```

---

## Kaynaklar ve Referanslar

### Timer/Clock
- [BCDEdit Tweaks](https://github.com/dubbyOW/BCDEditTweaks) - GitHub
- [Timer Resolution](https://timerresolution.com/)
- [HPET Analysis](https://www.xbitlabs.com/how-to-get-better-latency-in-windows/)

### GPU
- [NVIDIA Latency Guide](https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/)
- [NVIDIA Profile Inspector](https://github.com/Orbmu2k/nvidiaProfileInspector)
- [AMD Anti-Lag Config](https://www.amd.com/en/resources/support-articles/faqs/DH3-033.html)

### Services
- [HP Gaming Services Guide](https://www.hp.com/gb-en/shop/tech-takes/how-to-optimize-gaming-pc-disable-background-services)
- [XDA Services Guide](https://www.xda-developers.com/services-disabled-improve-windows-performance/)

### HAGS
- [PCWorld HAGS Analysis](https://www.pcworld.com/article/2339130/should-you-enable-hardware-accelerated-gpu-scheduling-in-windows-11.html)
- [BabelTech HAGS Benchmark](https://babeltechreviews.com/hardware-accelerated-gpu-scheduling-performance/)

---

## Web UI Spesifikasyonu

### Tek Sayfa Dashboard

```
┌─────────────────────────────────────────────────────────────────────┐
│  🎮 fpstune                                     [System: Win11 24H2]│
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │ 🖥️ SYSTEM       │  │ 🎯 GPU          │  │ 📊 STATUS       │     │
│  │ Intel i7-12700K │  │ NVIDIA RTX 4080 │  │ ✅ 5/7 Applied  │     │
│  │ 32GB DDR5       │  │ Driver: 555.42  │  │ ⏱️ Last: 2h ago │     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  OPTIMIZATION MODULES                                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─ ⏱️ Timer & Clock ─────────────────────────────────────────────┐ │
│  │                                                                 │ │
│  │  HPET                    [██████████] Disabled  ✅              │ │
│  │  Dynamic Tick            [──────────] Default   ⚪ [Toggle]     │ │
│  │  Timer Resolution        [0.5ms ▼]              ✅              │ │
│  │                                                                 │ │
│  │  ℹ️ Timer tweaks reduce input latency by up to 10-20%          │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ 🎮 Game Mode ───────────────────────────────────────────────────┐ │
│  │                                                                 │ │
│  │  Game Mode               [██████████] Enabled   ✅              │ │
│  │  Game Bar                [██████████] Disabled  ✅              │ │
│  │  HAGS                    [██████████] Enabled   ✅              │ │
│  │                                                                 │ │
│  │  ℹ️ HAGS requires WDDM 2.7+ GPU driver                         │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ 🎮 GPU Settings (NVIDIA) ─────────────────────────────────────┐ │
│  │                                                                 │ │
│  │  Low Latency Mode        [Ultra ▼]              ✅              │ │
│  │  Power Mode              [Maximum Performance ▼] ✅              │ │
│  │  VSync                   [Off ▼]                ✅              │ │
│  │  NVIDIA Reflex           [Game-controlled ▼]    ⚪              │ │
│  │  Shader Cache            [On ▼]                 ✅              │ │
│  │  HAGS                    [──────────] Off       ⚪ [Toggle]     │ │
│  │                                                                 │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ ⚙️ Services ──────────────────────────────────────────────────┐ │
│  │                                                                 │ │
│  │  SysMain (Superfetch)    [██████████] Disabled  ✅              │ │
│  │  Telemetry (DiagTrack)   [██████████] Disabled  ✅              │ │
│  │  Windows Search          [──────────] Enabled   ⚪ [Toggle]     │ │
│  │                                                                 │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌─ 🚀 CPU Priority ──────────────────────────────────────────────┐ │
│  │                                                                 │ │
│  │  GPU Priority            [8 (High) ▼]           ✅              │ │
│  │  Game Priority           [6 ▼]                  ✅              │ │
│  │  System Responsiveness   [0 (Gaming) ▼]         ✅              │ │
│  │                                                                 │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  QUICK ACTIONS                                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [🎯 Apply All]  [↩️ Revert All]  [🧹 System Cleanup]  [📊 Benchmark]│
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  PROFILES                                                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ( ) 🟢 Safe       - Minimal risk, proven tweaks only              │
│  (●) 🟡 Balanced   - Recommended for most users                    │
│  ( ) 🔴 Aggressive - Maximum performance, test required            │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  ACTIVITY LOG                                                       │
├─────────────────────────────────────────────────────────────────────┤
│  14:32:15  ✅ HPET disabled successfully                           │
│  14:32:14  ✅ Timer resolution set to 0.5ms                        │
│  14:32:12  📦 System restore point created                         │
│  14:32:10  🔍 Detecting system configuration...                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Tech Stack

```yaml
frontend:
  framework: React + TypeScript  # veya Svelte (daha lightweight)
  ui: Tailwind CSS + shadcn/ui
  state: Zustand (minimal)
  bundler: Vite

backend:
  runtime: Python (FastAPI) veya Rust (Tauri)

  # Opsiyon 1: Web UI (localhost)
  # FastAPI backend + React frontend
  # Browser üzerinden erişim

  # Opsiyon 2: Native App (Tauri)
  # Rust backend + React frontend
  # Tek executable, native performance
```

### API Endpoints

```yaml
# System Info
GET  /api/system          # OS, CPU, GPU, RAM info
GET  /api/status          # Current optimization status

# Modules
GET  /api/modules         # List all modules and states
POST /api/modules/apply   # Apply specific module
POST /api/modules/revert  # Revert specific module

# GPU
GET  /api/gpu/detect      # Detect GPU vendor
GET  /api/gpu/settings    # Current GPU settings
POST /api/gpu/apply       # Apply GPU settings
  body: {
    vendor: "nvidia" | "amd",
    low_latency: "off" | "on" | "ultra",
    vsync: "off" | "on" | "adaptive",
    power_mode: "optimal" | "maximum",
    reflex: "off" | "on" | "boost"
  }

# Safety
POST /api/backup          # Create backup
POST /api/restore         # Restore from backup
GET  /api/backups         # List backups

# Benchmark
POST /api/benchmark/start # Start benchmark
GET  /api/benchmark/status # Benchmark progress
GET  /api/benchmark/results # Comparison results

# Cleanup
POST /api/cleanup/dism    # Run DISM cleanup
POST /api/cleanup/temp    # Clean temp files
```

### UI/UX Prensipleri

1. **Single Page** - Tüm ayarlar tek sayfada görünür
2. **Real-time Feedback** - Her işlem sonucu anında gösterilir
3. **Toggle-based** - Her ayar için basit on/off toggle
4. **Status Indicators** - ✅ Applied, ⚪ Default, ⚠️ Warning
5. **Undo Always Available** - Her ayar geri alınabilir
6. **Dark Mode Default** - Oyuncu-dostu koyu tema
7. **No Restart Required Indicator** - Hangi ayarlar restart gerektiriyor

### Responsive Layout

```
Desktop (>1024px): Tam dashboard
Tablet (768-1024px): Stacked cards
Mobile (<768px): Full-width cards, collapsible sections
```

---

## Sürüm Planı

### v0.1.0 - MVP
- [ ] Core registry/bcdedit operations
- [ ] Timer module
- [ ] Basic CLI
- [ ] Backup/restore

### v0.2.0
- [ ] NVIDIA GPU module
- [ ] AMD GPU module
- [ ] Service module
- [ ] Config file support

### v0.3.0
- [ ] Web UI (single page dashboard)
- [ ] FastAPI backend
- [ ] React frontend
- [ ] Real-time status updates

### v0.4.0
- [ ] Benchmark integration
- [ ] Profile system (safe/balanced/aggressive)
- [ ] Native app (Tauri) - optional

---

## Önemli Notlar

1. **Her tweak bireysel test gerektirir** - Bir sistemde çalışan başka sistemde çalışmayabilir
2. **Benchmark yapmadan karar vermeyin** - Placebo etkisi çok yaygın
3. **Geri alma her zaman mümkün olmalı** - Tüm değişiklikler için backup
4. **Anti-cheat uyumluluğu** - Bazı oyunlar TPM 2.0 ve Secure Boot gerektirir (Ricochet)
5. **Windows Update sonrası kontrol** - Bazı ayarlar sıfırlanabilir

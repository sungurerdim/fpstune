import type { en } from "./en";

/**
 * The Turkish catalogue (F3). Typed against the English one: a key missing
 * here — or invented here — is a compile error, so the two locales cannot
 * drift apart silently.
 */
export const tr: Record<keyof typeof en, string> = {
  // First run
  "firstRun.title": "fpstune'a hoş geldiniz",
  "firstRun.nothingChanged": "Henüz hiçbir şey değiştirilmedi.",
  "firstRun.nothingChangedBody": "Uygulamayı açmak yalnızca mevcut ayarlarınızı okur. Her değişiklik sizin tıklamanızı bekler, her satır varsayılanına döndürülebilir ve toplu düğmeler önce bir Sistem Geri Yükleme noktası önerir.",
  "firstRun.admin":
    "Üst köşedeki kalkan, fpstune'un Yönetici olarak çalışıp çalışmadığını gösterir. Windows çoğu ince ayar için bunu şart koşar — onsuz her şeye bakabilirsiniz, ama çoğu Uygula düğmesi çalışmaz.",
  "firstRun.dismiss": "Anladım — makineyi göster",

  // The two buttons
  "scope.whatYouGiveUp": "Vazgeçtikleriniz:",
  "scope.restoreFirst": "Önce Sistem Geri Yükleme noktası oluştur (önerilir)",

  // Tabs
  // Single apply / reset outcomes
  "apply.applied": "{name} uygulandı",
  "apply.appliedWarnings": "{name} uyarılarla uygulandı: {reason}",
  "apply.applyFailed": "{name} uygulanamadı: {reason}",
  "apply.reset": "{name} varsayılanına döndürüldü",
  "apply.resetFailed": "{name} sıfırlanamadı: {reason}",
  "apply.unknownError": "neden bildirilmedi",
  "bulk.summary": "{applied} uygulandı, {failed} başarısız.",
  "bulk.requestFailed": "Hiçbir şey uygulanmadı: {reason}",
  "hw.notControllable": "Denetlenemiyor",
  "hw.displaysFailed": "Ekranların hepsi değiştirilemedi: {reason}",
  "hw.displayModeFailed": "Ekran modu değiştirilemedi: {reason}",
  "hw.adapterToggleFailed": "Ağ bağdaştırıcısı açılıp kapatılamadı: {reason}",
  "hw.adapterRestartNote": "Bu ayarları değiştirmek, son değişiklikten birkaç saniye sonra bağdaştırıcıyı bir kez yeniden bağlar.",
  "hw.connectFailed": "Bağlanılamadı: {reason}",
  "hw.disconnectFailed": "Bağlantı kesilemedi: {reason}",
  "hw.audioDeviceFailed": "Ses aygıtı açılıp kapatılamadı: {reason}",
  "hw.loudnessFailed": "Ses normalleştirme değiştirilemedi: {reason}",
  // Version and update (header)
  "update.version": "v{version}",
  "update.check": "Güncellemeleri denetle",
  "update.checking": "Denetleniyor…",
  "update.upToDate": "fpstune {version} en son sürüm.",
  "update.available": "fpstune {latest} yayında (sizdeki {current}).",
  "update.install": "{latest} sürümüne güncelle",
  "update.installing": "İndiriliyor ve doğrulanıyor…",
  "update.unreachable": "Güncellemeler denetlenemedi: {reason}",
  "header.admin": "Yönetici",
  "header.notAdmin": "Yönetici değil",
  "tab.optimize": "Optimize Et",
  "tab.cleanup": "Temizlik ve Onarım",
  "tab.measure": "Ölçüm",

  // Ekran modu onayı
  "displayConfirm.title": "Yeni ekran modu korunsun mu?",
  "displayConfirm.body":
    "{count} monitör doğal moduna geçti. Görüntü düzgünse koruyun; değilse {seconds} sn içinde kendiliğinden geri döner.",
  "displayConfirm.keep": "Koru",
  "displayConfirm.dontKeep": "Koruma",

  // Değişiklik geçmişi

  // Detection notice
  "detection.failedOne": "1 ayar bu makinede okunamadı",
  "detection.failedMany": "{count} ayar bu makinede okunamadı",
  "detection.absentOne": "1 ayar bu donanıma uygulanmıyor",
  "detection.absentMany": "{count} ayar bu donanıma uygulanmıyor",
  "detection.absentFallback": "Bu sisteme uygulanamaz",

  // Self-check notice
  "selfCheck.disagreementsOne":
    "Algılama öz denetimi 1 uyuşmazlık buldu — aşağıdaki değerler bu makinede yanlış olabilir.",
  "selfCheck.disagreementsMany":
    "Algılama öz denetimi {count} uyuşmazlık buldu — aşağıdaki değerler bu makinede yanlış olabilir.",
  "selfCheck.recheck": "Yeniden denetle",
  "selfCheck.checking": "Denetleniyor…",
  "osUpdate.body":
    "fpstune son çalıştığından beri Windows güncellendi (derleme {previous} → {current}). Güncellemeler ayarları Windows'un kendi değerlerine döndürebilir; aşağıdaki tarama yeni derlemede yapıldı.",
  "osUpdate.dismiss": "Kapat",

  // Locale switch
  "locale.switch": "Türkçeye geç",
  "theme.toDark": "Koyu temaya geç",
  "theme.toLight": "Açık temaya geç",

  // Common actions
  "action.apply": "Uygula",
  "action.cancel": "Vazgeç",
  "action.keep": "Koru",
  "action.reset": "Varsayılana dön",
  // Row surface
  "row.notRead": "Okunamadı",
  "row.unreadReason": "Hiçbir değer okunamadı: {reason}",
  "row.unreadNeedsAdmin": "Hiçbir değer okunamadı. fpstune yönetici olarak çalışmıyor; birkaç denetim bunu gerektiriyor.",
  "row.unreadNoReason": "Hiçbir değer okunamadı, dolayısıyla burada eyleme geçilecek bir bulgu yok.",
  "reset.kind.software": "Windows varsayılanı",
  "reset.kind.hardware": "Sürücü varsayılanı",
  "reset.kind.game": "Oyun varsayılanı",
  "reset.kind.application": "Uygulama varsayılanı",
  "reset.kind.firmware": "Donanım yazılımı varsayılanı",
  "row.resetKindValue": "Varsayılana dön: {kind} ({value})",
  "row.resetNamedValue": "{name} ayarını varsayılana döndür: {kind} ({value})",
  "row.applyNamed": "Uygula: {name}",
  "row.selectNamed": "Seç: {name}",
  "row.skipped": "atlandı",
  "row.statusRunning": "Uygulanıyor",
  "row.statusVerified": "Uygulandı ve doğrulandı",
  "row.statusFailed": "Başarısız",
  "row.statusFailedBecause": "Başarısız: {reason}",
  "toolbar.streamFailed": "Toplu işlem durdu: {reason}",
  "toolbar.doneSummary": "{done} tamamlandı, {failed} başarısız.",
  "toolbar.doneWarnings": "{count} ayar uyarılarla uygulandı.",
  "toolbar.stopped": "Durduruldu. Henüz başlamamış ayarlara dokunulmadı.",
  "toolbar.restoreFailed": "Geri yükleme noktası oluşturulamadı — hiçbir şey uygulanmadı. {reason}",
  "row.queued": "sırada",
  "row.notApplicable": "N/A",
  "row.detecting": "Okunuyor…",
  "row.chooseNamed": "{name} için bir değer seç",
  "sr.optimal": "Zaten önerilen değerde: ",
  "sr.currently": "Şu an ",
  "sr.recommendedIs": ", önerilen değer ",
  "finding.linkSpeed.below":
    "Bağlantı {linked} hızında; bağdaştırıcı {ceiling} destekliyor.",
  "finding.linkSpeed.atCeiling":
    "Bağlantı {linked} hızında, bağdaştırıcının en yükseği.",
  "finding.linkSpeed.adviceCable":
    "{cable} veya üstü kablo kullanın; modem ya da switch portunun da {ceiling} desteklediğini kontrol edin.",
  "finding.linkSpeed.adviceFarEnd":
    "Kabloyu ve modem ya da switch portunun {ceiling} desteklediğini kontrol edin.",
  "finding.wifi.onBand": "Sinyal %{signal}, {band} GHz bandında{radio}.",
  "finding.wifi.bandUnknown": "Sinyal %{signal}; bant bildirilmedi{radio}.",
  "finding.wifi.adviceSignal":
    "Modeme yaklaşın ya da aradaki engeli kaldırın; kablo her radyodan iyidir.",
  "finding.wifi.adviceBand":
    "Modemin 5 GHz veya 6 GHz ağına bağlanın; 2,4 GHz daha yavaş ve daha kalabalıktır.",
  "finding.wifiSecurity.legacyCipher":
    "{auth}, {cipher} şifresiyle: radyo 802.11g hızlarına kilitli.",
  "finding.wifiSecurity.wpa3Available":
    "{auth}, {cipher} ile; bu bağdaştırıcı da modem de WPA3 destekliyor.",
  "finding.wifiSecurity.good": "{auth}, {cipher} ile.",
  "finding.wifiSecurity.adviceCipher":
    "Modemde Wi-Fi güvenliğini AES ile WPA2 veya WPA3 yapın; sonra Windows'ta bu ağı unutup yeniden bağlanın.",
  "finding.wifiSecurity.adviceWpa3":
    "Windows'ta bu ağı unutup yeniden bağlanın; profil WPA3 olarak oluşturulur. Hız aynı kalır, parola çok daha zor kırılır.",
  "finding.thermal.zoneReads": "termal bölge {celsius}°C gösteriyor",
  "finding.thermal.noReading": "sıcaklık bildirilmedi",
  "finding.thermal.notThrottling": "Şu an ısı nedeniyle kısılmıyor; {reading}.",
  "finding.thermal.throttling":
    "Ürün yazılımı serin kalmak için hızları düşürüyor; {reading}.",
  "finding.thermal.advice":
    "Soğutucu ve fanlardaki tozu temizleyin, üç yıldan eski termal macunu yenileyin.",
  "finding.powerDcRail.drift": "Pilde bu değer {dc}; Windows'un kendi pil değeri {stock}.",
  "finding.powerDcRail.advice":
    "fpstune yalnız fişteki değeri ayarlar; uygulamak pil değerini Windows'un kendisine geri döndürür.",
  "finding.startupApps.none": "Windows ile hiçbir üçüncü taraf uygulama başlamıyor.",
  "finding.startupApps.one": "Windows ile 1 uygulama başlıyor: {names}.",
  "finding.startupApps.many": "Windows ile {count} uygulama başlıyor: {names}.",
  "finding.startupApps.more": "{names} ve {rest} tane daha",
  "finding.startupApps.advice":
    "Gerekmeyenleri Görev Yöneticisi > Başlangıç uygulamaları'ndan kapatın; güvenlik yazılımı listelenmez.",
  "finding.displayMode.native": "Doğal {width}×{height} @ {hz} Hz değerinde çalışıyor.",
  "finding.displayMode.lowRefresh":
    "{hz} Hz'de çalışıyor; bu panel {max} Hz gösterebiliyor. {max} Hz'de her kare ekranda {oldMs} ms yerine {newMs} ms kalır: daha akıcı hareket ve daha az giriş gecikmesi.",
  "finding.displayMode.lowResolution":
    "{width}×{height} çözünürlükte çalışıyor; panelin doğal çözünürlüğü {nativeWidth}×{nativeHeight}. Doğalın altında Windows görüntüyü ölçekler ve görüntü yumuşar.",
  "finding.displayMode.secondary":
    "İkincil monitör, bu yüzden isteğe bağlı: oyunun kare hızı buna bağlı değil.",
  "finding.displayMode.advice":
    "Uygulamak doğal modu ayarlar; siz korumazsanız 15 saniye sonra kendiliğinden geri döner.",
  "choice.native": "Doğal",
  "choice.not_native": "Doğalın altında",
  "choice.fps_balanced": "FPS Balanced planı",
  "choice.windows_balanced": "Windows Balanced planı",
  "choice.other_plan": "Başka bir güç planı",
  "choice.at_capability": "Azami hızda",
  "choice.below_capability": "Azami hızın altında",
  "choice.good": "İyi",
  "choice.weak_signal": "Zayıf sinyal",
  "choice.on_2_4ghz": "2,4 GHz'de",
  "choice.legacy_cipher": "Eski şifre",
  "choice.wpa3_available": "WPA3 mümkün",
  "choice.not_throttling": "Kısılmıyor",
  "choice.throttling": "Kısılıyor",
  "choice.none_at_startup": "Başlangıçta yok",
  "choice.apps_at_startup": "Başlangıçta uygulama var",
  "tier.off": "Kapalı",
  "tier.on": "Açık",
  "tier.ultra": "Ultra",
  "badge.risk": "RİSK",
  "badge.note": "NOT",

  // Impact categories
  "impact.latency": "Gecikme",
  "impact.fps": "FPS",
  "impact.thermal": "Isı ve aşınma",
  "impact.network": "Ağ",
  "impact.resources": "Kaynaklar",
  "impact.storage": "Depolama",
  "impact.privacy": "Gizlilik",
  "impact.visual": "Görsel",
  // Cleanup & maintenance surfaces
  "run.percent": "%{value}",
  "run.elapsed": "{seconds} sn geçti",
  "cleanup.calculating": "Hesaplanıyor…",
  "cleanup.freed": "{amount} boşaltıldı",
  "cleanup.done": "Tamamlandı",
  "cleanup.serviceDown":
    "Hizmet çalışmıyor ve başlatılamadı. Hizmeti başlatıp bu sekmeyi yeniden açın.",
  "cleanup.unavailable": "Kullanılamıyor",
  "cleanup.trimOverdueNever": "TRIM gecikti: hiç çalışmamış",
  "cleanup.trimOverdueDays": "TRIM gecikti: {days} gün önce",
  "cleanup.trimLastDays": "Son TRIM: {days} gün önce",
  "cleanup.trimLastUnderDay": "Son TRIM: bir günden az önce",
  "cleanup.dismWarning":
    "5-15 dakika sürer. ResetBase ile kaldırılan güncellemeler geri alınamaz. Bildirilen boyut, bileşen deposunun geri kazanılabilir kısmıdır — gerçek boş alan ancak yeniden başlatmadan sonra görünebilir.",
  "cleanup.dockerShutdownWarning":
    "Sanal diski küçültüp gerçek disk alanını geri vermek için Docker Desktop'ı ve tüm WSL dağıtımlarını kapatır. Birkaç dakika sürebilir; önce çalışmalarınızı kaydedin.",
  "cleanup.wslWarning":
    'Önce "wsl --shutdown" çalıştırır; tüm çalışan WSL dağıtımları ve Docker Desktop (WSL arka ucu) anında kapanır. Çalıştırmadan önce işinizi kaydedin. Bildirilen boyut mevcut disk ayak izidir, tam geri kazanılabilir miktar değildir.',
  "cleanup.measuringMore": "{count} öge daha ölçülüyor…",
  "cleanup.measuringFootnote":
    "Bu bittiğinde yukarıda listelenmeyenlerin geri kazanılacak bir şeyi yoktur ya da yazılımı kurulu değildir.",
  "cleanup.runCleanup": "Temizliği Çalıştır",
  "cleanup.runCleanupCount": "Temizliği Çalıştır ({count})",
  "cleanup.groupOther": "Diğer",
  "cleanup.selectGroup": "{group} grubunun tümünü seç",
  "maintenance.title": "Sistem Bakımı",
  "maintenance.running": "Çalışıyor...",
  "maintenance.dismHealthWarning":
    "Onarım dosyalarını indirmek için internet bağlantısı gerekebilir.",
  "docker.title": "Docker ve WSL yeniden başlatılsın mı?",
  "docker.confirm": "Buda ve sıkıştır",
  "docker.body":
    "Docker Desktop ve tüm WSL dağıtımları kapatılıp yeniden başlatılacak; böylece sanal diskleri sıkıştırılır ve alan gerçekten geri kazanılır. Bu birkaç dakika sürebilir. Önce çalışmanızı kaydedin.",

  // Selection toolbar
  "toolbar.advancedTitle": "Gelişmiş ince ayarlar seçili",
  "toolbar.applyAnyway": "Yine de uygula",
  "toolbar.advancedBody":
    "Seçiminizde Gelişmiş olarak işaretli ayarlar var. Bunlar deneyseldir ve donanımınıza göre farklı davranabilir. Devam edilsin mi?",
  "toolbar.selected": "{count} seçili",
  "toolbar.clear": "Temizle",
  "toolbar.stop": "Durdur",
  "toolbar.applySelected": "Seçilenleri uygula ({count})",
  "toolbar.resetSelected": "Seçilenleri varsayılana döndür ({count})",
  "toolbar.apply.essential": "Temel olanları uygula ({count})",
  "toolbar.apply.recommended": "Önerilenleri uygula ({count})",
  "toolbar.apply.complete": "Tümünü uygula ({count})",
  "toolbar.none.apply": "{name} içinde uygulanacak bir şey yok",
  "toolbar.none.reset": "{name} içindeki her şey zaten varsayılanında",
  // Hardware surfaces
  "hw.cpu": "İşlemci",
  "hw.memory": "Bellek",
  "hw.gpu": "Ekran Kartı",
  "hw.displays": "Ekranlar",
  "hw.buses": "USB ve PCIe",
  "hw.storage": "Depolama",
  "hw.network": "Ağ",
  "hw.audio": "Ses",
  "hw.audioOutput": "Ses Çıkışı",
  "hw.audioInput": "Ses Girişi",
  "hw.loudnessEq": "Ses Dengeleme",
  "hw.loudnessNotSupported": "Windows ses dengeleme yok: bu aygıtın sürücüsü Microsoft efektlerini yüklemiyor",
  "hw.loudnessNextStream": "Ses dengeleme değişti. Çalmakta olan ses, uygulaması yeniden başlayınca değişir.",
  "hw.audioDefault": "Varsayılan",
  "hw.notDetected": "Algılanamadı",
  "hw.copy": "Panoya kopyala",
  "device.toApply": "Uygulanacak {count}",
  "device.notOptimized": "{count} iyileştirilmemiş",
  "devices.listLabel": "Cihazlar",
  "device.nothingToDo": "Bu cihazda yapılacak bir şey yok.",
  "device.primary": "birincil",
  "device.secondary": "ikincil",
  "device.monitor": "Monitör {n}",
  "device.allDisplays": "Tüm ekranlar",
  "device.allDrives": "Tüm sürücüler",
  "device.allAdapters": "Tüm ağ bağdaştırıcıları",
  "device.wifi": "Wi-Fi",
  "device.ethernet": "Ethernet",
  "device.adapter": "Ağ bağdaştırıcısı",
  "device.drive": "Sürücü",
  "devices.toFix": "Düzeltilecek {count}",
  "devices.allIdeal": "{count} ayarın hepsi ideal",
  "devices.needYou": "{count} senden işlem bekliyor",
  "devices.reading": "İnce ayarlar okunuyor…",

  // Monitor card
  "monitor.applying": "Uygulanıyor…",
  "monitor.useNative": "Doğal modu kullan",
  "monitor.useNativeAll": "{count} ekranın tümünde doğal modu kullan",
  "monitor.keepTitle": "Bu ekran modu korunsun mu?",
  "monitor.keepAllTitle": "Bu ekran modları korunsun mu?",
  "monitor.revertBody":
    "Korumazsanız bu ekran {seconds} saniye içinde önceki moduna döner — böylece ekranınızın gösteremediği bir mod kendini düzeltir.",
  "monitor.revertAllBody":
    "Korumazsanız değişen her ekran {seconds} saniye içinde önceki moduna döner — böylece ekranınızın gösteremediği bir mod kendini düzeltir.",
  "monitor.resolution": "Çözünürlük:",
  "monitor.refresh": "Yenileme:",
  "monitor.primary": "Birincil",
  "monitor.disconnected": "Bağlı değil",

  // Network adapter card
  "adapter.connect": "Bağlan",
  "adapter.disconnect": "Bağlantıyı kes",
  "adapter.connectTitle": "Ağa bağlan",
  "adapter.disconnectTitle": "Ağ bağlantısını kes",
  "adapter.on": "Aç",
  "adapter.off": "Kapat",
  "adapter.connected": "Bağlı",
  "adapter.disconnected": "Bağlı değil",
  "adapter.notConnected": "Bağlantı Yok",


  // Storage card
  "storage.retrim": "Retrim",
  "storage.defrag": "Birleştir",
  "storage.trimUnknown": "TRIM durumu okunamadı",
  "storage.running": "{action} çalışıyor…",
  // Time distance (formatAge)
  "age.justNow": "az önce",
  "age.minutes": "{count} dk önce",
  "age.hours": "{count} sa önce",
  "age.days": "{count} gün önce",

  // Headroom panel
  "headroom.title": "Bu makinenin ulaştığı",
  "headroom.subtitle":
    "Bu ekranın kendi çözünürlüğünde çizilen sabit bir test sahnesi, ekranın gösterebildiğine karşı ölçülür. Görüntü kalitesine harcanacak kare olup olmadığına bu karar verir.",
  "headroom.measureNow": "Şimdi ölç",
  "headroom.measuring": "Ölçülüyor…",
  "headroom.startFailed": "Ölçüm başlatılamadı.",
  "headroom.readingLast": "Son sonuç okunuyor…",
  "headroom.needsScene":
    "Henüz bir ölçüm yok. fpstune makine boştayken sabit bir test sahnesi çizer, yani bir oyunun açık olması gerekmez — ya da yaklaşık bir dakika süren Şimdi ölç'e basın.",
  "headroom.needsDownload":
    "Test sahnesi Unigine Superposition Basic'tir; tek seferlik 1,3 GB'lık bir indirme. fpstune bunu kendiliğinden başlatmaz.",
  "headroom.installScene": "Sahneyi kur (1,3 GB indirme)",
  "headroom.installing": "Sahne kuruluyor — bu yaklaşık bir dakika sürebilir…",
  "headroom.installStartFailed": "Sahne kurulamadı.",
  "headroom.installFailed": "Sahne kurulamadı: {reason}",
  "headroom.onePercentLow": "(%1 düşüklerde {value})",
  "headroom.againstTarget": "bu panelin {target} fps hedefine karşı",
  "headroom.measuredAgo": "Ölçüm: {age}",
  "headroom.renderedAt": "{width}×{height} ile çizildi, bu ekranın kendi çözünürlüğü",
  "headroom.gaugeLabel":
    "Ekranın {target} fps hedefine karşı ölçülen kare hızı",
  "headroom.tierMet": "Tavanında",
  "headroom.tierMetMeaning":
    "Bu makine ekranın gösterebildiğine ulaşıyor; görüntü kalitesine harcanacak kare fazlası var.",
  "headroom.tierNear": "Yakın",
  "headroom.tierNearMeaning":
    "Neredeyse tamam. Küçük tasarruflar işi bitirir; kare hızına mal olan hiçbir şey bitirmez.",
  "headroom.tierShort": "Eksik",
  "headroom.tierShortMeaning":
    "Ekranın gösterebildiğinin belirgin altında. Süsleme harcanmaya değer; oyuncunun görmesi gerekenler değil.",
  "headroom.tierCritical": "Çok eksik",
  "headroom.tierCriticalMeaning":
    "Ekranın gösterebildiğinin yarısından az. Bilgi olmayan her şey harcanmaya değer; daha keskin bir görüntü zaten masada yok.",
  "headroom.tierUnknown": "Ölçülmedi",
  "headroom.tierUnknownMeaning":
    "Bu makinede henüz bir ölçüm yok ve sessizlik kanıt değildir — bu yüzden kare hızına mal olan hiçbir şey önerilmeyecek.",
  "headroom.gpuBound": "GPU'ya bağlı — kareler grafik ayarlarında saklı",
  "headroom.cpuBound": "CPU'ya bağlı — grafik ayarları bunu pek değiştirmez",
  "headroom.bothBound":
    "İki taraf da doymuş — tek başına grafik ayarları farkı kapatmaz",
  "headroom.presentMode": "Sunum modu: {mode}",

  // Benchmarks tab
  "bench.measure": "Ölç",
  "bench.verifyClaims": "İddiaları doğrula",
  // Measure (suite) panel
  "suite.repeats": "Tekrar",
  "suite.loading": "Araç listesi yükleniyor…",
  "suite.title": "Neyin değiştiğini ölç",
  "suite.baselineTaken":
    "Taban ölçüm alındı. İstediğiniz ince ayarları uygulayın, sonra tekrar basın — iki koşu sizin için karşılaştırılır.",
  "suite.takesBaseline":
    "Bu makinenin taban ölçümünü alır. Hiçbir şey değiştirilmez, hiçbir şey yazılmaz.",
  "suite.measureAgain": "Tekrar ölç ve karşılaştır",
  "suite.measureThis": "Bu makineyi ölç",
  "suite.startOver": "Baştan başla",
  "suite.selectionSummary":
    "{total} araçtan {selected} seçili · {repeats} tekrar",
  "suite.before": "Önce",
  "suite.after": "Sonra",
  "suite.notMeasuredYet": "Henüz ölçülmedi",
  "suite.whichInstruments": "Hangi araçlar ve kaç tekrar",
  "suite.notInRunAll": "(\u201ctümünü çalıştır\u201d kapsamında değil)",
  "suite.measuringBench": "{bench} ölçülüyor…",
  "suite.startingRun": "{label} koşusu başlatılıyor…",
  "suite.minRepeats":
    "{min} veya daha fazla — tek okumanın gürültü tabanı olmaz",
  "suite.notCompared": "Karşılaştırılmadı",
  "suite.metric": "Metrik",
  "suite.change": "Değişim",
  "suite.verdict": "Karar",
  "suite.withinNoise": "gürültü içinde (±{noise}{unit})",
  "suite.deltaBarLabel": "{metric}: bu gruptaki en büyüğe göre %{pct} değişim",
  "suite.otherMeasurements": "Diğer ölçümler",
  "suiteCat.latency": "Gecikme",
  "suiteCat.fps": "Kare hızı",
  "suiteCat.thermal": "Isı ve aşınma",
  "suiteCat.network": "Ağ",
  "suiteCat.resources": "Bellek ve CPU",
  "suiteCat.storage": "Depolama",

  // Verify panel
  "verify.title": "Bir iddiayı doğrula",
  "verify.selectFirst":
    "Değiştirmek üzere olduğunuz ayarları Optimize Et sekmesinden seçin. Bir tur ancak değiştiğini bildiği ayarlar hakkında anlamlıdır — bu yüzden uygulananlardan tahmin etmek yerine hangileri olduğunu sorar.",
  "verify.selectedSummary":
    "{count} ayar seçili. Ölçün, uygulayın, tekrar ölçün; bu, ayarların iddia ettiğini makinenin yaptığıyla yargılar.",
  "verify.couldShow": "Bunun gösterebilecekleri",
  "verify.readingClaims": "İddialar okunuyor…",
  "verify.youWouldNeed": "Gerekenler: ",
  "verify.gapsTitle": "burada henüz denetlenemeyenler ve nedenleri",
  "verify.unmeasurableTitle":
    "hiçbir ölçümün karara bağlamadığı — gerçek iddialar, eksik değil",
  "verify.readings": "Okumalar",
  "verify.noMeasurements":
    "Henüz ölçüm yok. Ölç sekmesinden bir taban alın, bu ayarları uygulayın ve tekrar ölçün — iddialar ikinci bir çift istemek yerine aynı çifte karşı yargılanır.",
  "verify.fromSuite":
    "Ölçüm takımından: önce {before}, sonra {after} okuma, {metrics} metrik boyunca.",
  "verify.fromSuiteOne":
    "Ölçüm takımından: önce 1, sonra {after} okuma, {metrics} metrik boyunca.",
  "verify.fewReadings":
    "Taraf başına {wanted} okumadan az. Boştaki bir makinede aynı ölçümün iki koşusu bile farklı çıkar; ne kadar farklı çıktığı bilinmeden küçük bir değişim hiçbir şey olmamasından ayırt edilemez — Ölç sekmesinde tekrar sayısını artırın.",
  "verify.enoughReadings":
    "Gürültü tabanının anlam taşıması için iki tarafta da yeterli okuma var.",
  "verify.judge": "Yargıla",
  "verify.judgeClaims": "Bu iddiaları yargıla",
  "verify.needsBothSides":
    "Her iki tarafta bir okuma ve seçili bir ayar gerekir. Çiftin tek tarafı küçük bir sonuç değil, sonuçsuzluktur.",
  "verify.claimedLine": "{metric} için {claimed} iddia etti — ",
  "verify.changeBarLabel": "Ölçülen değişim: {value} {unit}",
  "verify.noiseBarLabel":
    "Bu makinenin kendi oynaması (gürültü tabanı): {value} {unit}",
  "verify.statusVerified": "Doğrulandı",
  "verify.statusContradicted": "Yalanlandı",
  "verify.statusNoise": "Gürültüde kayboldu",
  "verify.statusUnmeasured": "Ölçülmedi",
  "verify.statusUnattributable": "Atfedilemez",
  // Activity log
  "activity.empty": "Yakın zamanda etkinlik yok",
  "activity.button": "Etkinlik",
  "activity.title": "Etkinlik Günlüğü",
  "activity.open": "Etkinlik günlüğünü aç",
  "activity.close": "Etkinlik günlüğünü kapat",

  // Optimize tab
  "games.reading": "Oyun yapılandırmalarınız okunuyor…",
  "games.noneFound":
    "Bu makinede desteklenen bir oyun yapılandırması bulunamadı. fpstune bir oyunun yapılandırmasını yalnızca oyun kuruluysa okur.",

  // Setting tooltip
  "tooltip.current": "Mevcut:",
  "tooltip.recommended": "Önerilen:",
  "tooltip.effect": "Etkisi:",
  "tooltip.howToChange": "Nasıl değiştirilir:",
  "tooltip.ariaInfo": "{name} hakkında bilgi",
  "tooltip.monitorOnly":
    "FPSTune bunu kendiliğinden uygulayamaz — yalnızca izler.",
  "tooltip.sources": "Kaynaklar:",
  "tooltip.requiresRestart": "Sistemin yeniden başlatılması gerekir",

  // Satır ayrıntısı ((i) arkasında) ve kategori bölümleri
  "detail.cost": "Bedeli:",
  "detail.defaultIs": "{kind}: {value}",
  "category.notOptimized": "{count} / {total} optimize edilmedi",
  "category.allOptimized": "{total} ayarın tamamı optimize",
  "category.detecting": "Okunuyor…",
  "category.manualSteps": "Elle yapılacaklar ({count})",

  // fpstune neyi değiştirdi, ölçüldü (ölçüm defteri)
  "ledger.panelTitle": "Bu makinede ölçülenler",
  "ledger.panelHint": "Diskte tutulur; sayfa yenilenince temel ölçüm kaybolmaz.",
  "ledger.area": "Alan",
  "ledger.instrument": "Ölçüm aracı",
  "ledger.before": "Önce",
  "ledger.after": "Sonra",
  "ledger.change": "Değişim",
  "ledger.verdict": "Sonuç",
  "ledger.improved": "İyileşti",
  "ledger.worse": "Kötüleşti",
  "ledger.changed": "Değişti",
  "ledger.withinNoise": "Makinenin kendi değişkenliği olan {noise}{unit} içinde kaldı, bu yüzden hiçbir yönde sonuç çıkarmak mümkün değil",
  "ledger.withinNoiseShort": "Makinenin kendi değişkenliği içinde",
  "ledger.noise": "gürültü {noise}{unit}",
  "ledger.noiseUnknown": "gürültü tabanı bilinmiyor",
  "ledger.samples": "{before} ve {after} okuma",
  "ledger.loading": "Bu makinede nelerin ölçüldüğü okunuyor…",
  "ledger.unreachable": "Ölçüm defteri okunamadı.",
  "ledger.triggerBaseline": "Temel ölçüm",
  "ledger.triggerAfter": "Değişikliklerinizden sonra",
  "ledger.triggerManual": "Ölçüm",
  "ledger.jobRunning": "{what} sürüyor: adım {step}/{total} — {bench}",
  "ledger.jobQueued": "{what} sırada — makinenin boşa çıkması bekleniyor",
  "ledger.jobFailed": "{what} tamamlanamadı; fpstune yeniden deneyecek.",
  "ledger.jobIdle": "Şu anda hiçbir ölçüm yapılmıyor.",
  "ledger.bulkPending": "Son ölçümden sonra tweak uygulandı — makine boşa çıkınca fpstune yeniden ölçecek.",
  "ledger.baselineRun": "Temel ölçüm: {summary} ({age})",
  "ledger.afterRun": "Sonra: {summary} ({age})",
  "ledger.noRunYet": "Bu makinede henüz hiçbir ölçüm yapılmadı.",
  "ledger.measureNow": "Şimdi ölç",
  "ledger.measureNowHint": "Ölçümü sıraya alır; fpstune makine boşa çıkıp oyun kapalı olduğunda ölçer.",
  "ledger.queued": "Sıraya alındı.",
  "ledger.alreadyRunning": "Zaten devam eden bir ölçüm var.",
  "ledger.queueFailed": "Ölçüm sıraya alınamadı.",

  // Notifications
  "toast.errorsRegion": "Hatalar ve uyarılar",
  "toast.region": "Bildirimler",
  "toast.error": "Hata",
  "toast.warning": "Uyarı",
  "toast.success": "Başarılı",
  "toast.info": "Bilgi",
  // Scope actions
  "actions.apply": "Uygula ({count})",
  "actions.reset": "Varsayılana dön ({count})",
  "actions.applyShort": "Uygula",
  "actions.aria.reset.software": "{count} ayarı Windows varsayılanına döndür: {name}",
  "actions.aria.reset.hardware": "{count} ayarı sürücü varsayılanına döndür: {name}",
  "actions.aria.reset.game": "{count} ayarı oyun varsayılanına döndür: {name}",
  "actions.aria.reset.mixed": "{count} ayarı kendi varsayılanına (Windows, sürücü ya da oyun) döndür: {name}",
  "actions.resetShort": "Varsayılana dön",
  "actions.aria.apply": "{count} ayarı uygula: {name}",
  "actions.none.apply": "Uygula: {name} içinde uygulanacak bir şey yok",
  "actions.none.reset": "Varsayılana dön: {name} içindeki her şey zaten varsayılanında",
  // Header metrics: a count set apart in bold, then what it counts
  "actions.confirm.apply": "{name} için {count} ayar uygulansın mı?",
  "actions.confirm.reset": "{count} ayar varsayılanına dönecek.",
  "actions.confirmBody.reset.software": "Windows'un sunduğundan farklı olan her ayar ona geri döner. Her satır kendi sonucunu gösterir.",
  "actions.confirmBody.reset.hardware": "Sürücünün sunduğundan farklı olan her ayar ona geri döner. Her satır kendi sonucunu gösterir.",
  "actions.confirmBody.reset.game": "Oyunun sunduğundan farklı olan her ayar ona geri döner. Her satır kendi sonucunu gösterir.",
  "actions.confirmBody.reset.mixed": "Kendi varsayılanından (Windows, sürücü ya da oyunun sunduğu değer) farklı olan her ayar ona geri döner. Her satır kendi sonucunu gösterir.",
  "actions.confirmBody.apply": "Her satır kendi sonucunu gösterir; her satır varsayılanına döndürülebilir.",
  "settings.search": "Ayarlarda ara",
  "settings.searchPlaceholder": "Ayarlarda ara...",
  "optimize.software": "Yazılım",
  "optimize.hardware": "Donanım",
  "optimize.games": "Oyun ayarları",
  "optimize.otherHardware": "Diğer donanım",
  "optimize.results": "Arama sonuçları",
  "optimize.noMatch": "Bu aramayla eşleşen ayar yok.",
  // Gerekenler / ideal bantları
  "bands.needs": "İşlem gerekiyor",
  "bands.ideal": "İdeal",
  "bands.nothingToDo": "Burada yapılacak bir şey yok.",
};

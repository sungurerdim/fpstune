import type { en } from "./en";

/**
 * The Turkish catalogue (F3). Typed against the English one: a key missing
 * here — or invented here — is a compile error, so the two locales cannot
 * drift apart silently.
 */
export const tr: Record<keyof typeof en, string> = {
  // First run
  "firstRun.title": "fpstune'a hoş geldiniz",
  "firstRun.what":
    "fpstune bu makineyi, donanımının izin verdiği en iyi oyun deneyimi için ayarlar — önce kare hızı, her değer kendi donanımınızdan türetilir, asla genel bir ön ayardan değil.",
  "firstRun.nothingChanged": "Henüz hiçbir şey değiştirilmedi.",
  "firstRun.nothingChangedBody":
    "Uygulamayı açmak yalnızca mevcut ayarlarınızı okur. Her değişiklik sizin tıklamanızı bekler, her değişiklik aynı satırdan geri alınabilir ve toplu düğmeler önce bir Sistem Geri Yükleme noktası önerir.",
  "firstRun.admin":
    "Üst köşedeki kalkan, fpstune'un Yönetici olarak çalışıp çalışmadığını gösterir. Windows çoğu ince ayar için bunu şart koşar — onsuz her şeye bakabilirsiniz, ama çoğu Uygula düğmesi çalışmaz.",
  "firstRun.dismiss": "Anladım — makineyi göster",

  // The two buttons
  "scope.competitive": "Rekabetçi Maksimum",
  "scope.competitiveHint":
    "Gördüğünüze ve duyduğunuza dokunmadan alınabilecek en yüksek kare hızı.",
  "scope.absolute": "Mutlak Maksimum",
  "scope.absoluteHint":
    "Her ayar kare hızı ucuna çekilir — kalite harcanır ve bedeli, hiçbir şey çalışmadan önce listelenir.",
  "scope.competitiveConfirmTitle":
    "Rekabetçi Maksimum uygulansın mı? ({count} ayar)",
  "scope.competitiveConfirmBody":
    "Temel ve önerilen tüm ince ayarları uygular — oyun içinde görebildiğiniz veya duyabildiğiniz hiçbir şeyi değiştirmeden bu makinenin ulaşabileceği en yüksek kare hızı. Görüntü veya ses kalitesi harcayan ayarlara dokunulmaz.",
  "scope.absoluteConfirmTitle": "Mutlak Maksimum uygulansın mı? ({count} ayar)",
  "scope.absoluteConfirmBody":
    "Resim ve ses kalitesini harcayanlar dahil, her ayarı kare hızı ucuna iter.",
  "scope.whatYouGiveUp": "Vazgeçtikleriniz:",
  "scope.apply": "Uygula",
  "scope.spendIt": "Harca",
  "scope.restoreFirst": "Önce Sistem Geri Yükleme noktası oluştur (önerilir)",

  // Tabs
  // Single apply / reset / undo outcomes
  "apply.applied": "{name} uygulandı",
  "apply.applyFailed": "{name} uygulanamadı: {reason}",
  "apply.reset": "{name} Windows varsayılanına döndürüldü",
  "apply.resetFailed": "{name} sıfırlanamadı: {reason}",
  "apply.undone": "{name} geri alındı",
  "apply.undoFailed": "{name} geri alınamadı: {reason}",
  "apply.unknownError": "neden bildirilmedi",
  "bulk.summary": "{applied} uygulandı, {failed} başarısız.",
  "bulk.requestFailed": "Hiçbir şey uygulanmadı: {reason}",
  "hw.notControllable": "Denetlenemiyor",
  "hw.displaysFailed": "Ekranların hepsi değiştirilemedi: {reason}",
  "hw.gsyncApplyFailed": "G-Sync ayarları uygulanamadı: {reason}",
  "hw.gsyncResetFailed": "G-Sync ayarları sıfırlanamadı: {reason}",
  "hw.displayModeFailed": "Ekran modu değiştirilemedi: {reason}",
  "hw.adapterToggleFailed": "Ağ bağdaştırıcısı açılıp kapatılamadı: {reason}",
  "hw.adapterRestartNote": "Bu ayarları değiştirmek, son değişiklikten birkaç saniye sonra bağdaştırıcıyı bir kez yeniden bağlar.",
  "hw.connectFailed": "Bağlanılamadı: {reason}",
  "hw.disconnectFailed": "Bağlantı kesilemedi: {reason}",
  "hw.audioDeviceFailed": "Ses aygıtı açılıp kapatılamadı: {reason}",
  "hw.loudnessFailed": "Ses normalleştirme değiştirilemedi: {reason}",
  "hw.powerPlanActivateFailed": "Güç planı etkinleştirilemedi: {reason}",
  "hw.powerPlanRevertFailed": "Güç planı geri alınamadı: {reason}",
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
  "tab.home": "Ana Sayfa",
  "tab.software": "Yazılım İnce Ayarları",
  "tab.hardware": "Donanım İnce Ayarları",
  "tab.games": "Oyun İnce Ayarları",
  "tab.cleanup": "Temizlik ve Onarım",
  "tab.benchmarks": "Ölçümler",
  "tab.history": "Geçmiş",

  // Ekran modu onayı
  "displayConfirm.title": "Yeni ekran modu korunsun mu?",
  "displayConfirm.body":
    "{count} monitör doğal moduna geçti. Görüntü düzgünse koruyun; değilse {seconds} sn içinde kendiliğinden geri döner.",
  "displayConfirm.keep": "Koru",
  "displayConfirm.dontKeep": "Koruma",

  // Değişiklik geçmişi
  "history.title": "fpstune'un değiştirdikleri",
  "history.intro":
    "fpstune'un bu makinede değiştirdiği her ayar; bu oturumda ve öncekilerde. Geri al, fpstune dokunmadan önce makinede olan değeri geri yazar; Windows varsayılanı ise Windows'un fabrika değerini yazar.",
  "history.loading": "Geçmiş okunuyor…",
  "history.error": "Geçmiş okunamadı: {reason}",
  "history.empty": "fpstune bu makinede henüz hiçbir şeyi değiştirmedi.",
  "history.active": "Hâlâ fpstune'un değiştirdiği haliyle ({count})",
  "history.reverted": "Zaten geri alınmış ({count})",
  "history.action.apply": "Uygulandı",
  "history.action.reset": "Windows varsayılanına döndürüldü",
  "history.action.undo": "Geri alındı",
  "history.value": "{value} yapıldı",
  "history.was": "önceden {value} idi",
  "history.noOriginal":
    "Bu ayarın önceki değeri kayıtlı değil; yalnızca Windows varsayılanı geri yüklenebilir.",
  "history.undo": "Geri al",
  "history.reset": "Windows varsayılanı",
  "history.undoNamed": "{name} için fpstune değişikliğini geri al",
  "history.resetNamed": "{name} için Windows varsayılanını geri yükle",
  "history.selectNamed": "{name} seç",
  "history.selectAll": "Tümünü seç",
  "history.undoSelected": "Seçilenleri geri al ({count})",
  "history.resetSelected": "Seçilenler için Windows varsayılanı ({count})",

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

  // Common actions
  "action.apply": "Uygula",
  "action.cancel": "Vazgeç",
  "action.run": "Çalıştır",
  "action.runAll": "Tümünü Çalıştır",
  "action.undo": "Geri Al",
  "action.keep": "Koru",
  // Row surface
  "row.ok": "Tamam",
  "row.advisory": "Bilgilendirme",
  "row.notRead": "Okunamadı",
  "row.verify": "Mevcut değeri doğrula",
  "row.undo": "fpstune'un değişikliğini geri al, {value} değerine dön",
  "row.undoNamed":
    "{name} için fpstune'un değişikliğini geri al, {value} değerine dön",
  "row.undoTooltip":
    "fpstune'un değişikliğini geri al — bu makinenin önceki değeri olan {value} geri gelir",
  "row.resetDefault": "Windows varsayılanına döndür",
  "row.target": "Hedef",
  "row.applyNamed": "Uygula: {name}",
  "row.selectNamed": "Seç: {name}",
  "row.default": "Varsayılan",
  "row.current": "Mevcut",
  "row.skipped": "atlandı",
  "row.statusRunning": "Uygulanıyor",
  "row.statusVerified": "Uygulandı ve doğrulandı",
  "row.statusFailed": "Başarısız",
  "row.statusFailedBecause": "Başarısız: {reason}",
  "toolbar.streamFailed": "Toplu işlem durdu: {reason}",
  "toolbar.doneSummary": "{done} tamamlandı, {failed} başarısız.",
  "toolbar.stopped": "Durduruldu. Henüz başlamamış ayarlara dokunulmadı.",
  "row.queued": "sırada",
  "row.notApplicable": "N/A",
  "row.setTo": "{value} yap",
  "row.resetTo": "{value} değerine sıfırla",
  "row.resetChoice": "{value} (sıfırla)",
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
  "choice.at_capability": "Bağdaştırıcının en yükseğinde",
  "choice.below_capability": "Bağdaştırıcının en yükseğinin altında",
  "choice.good": "İyi",
  "choice.weak_signal": "Zayıf sinyal",
  "choice.on_2_4ghz": "2,4 GHz'de",
  "choice.legacy_cipher": "Eski şifre",
  "choice.wpa3_available": "WPA3 mümkün",
  "choice.not_throttling": "Kısılmıyor",
  "choice.throttling": "Kısılıyor",
  "choice.none_at_startup": "Başlangıçta yok",
  "choice.apps_at_startup": "Başlangıçta uygulama var",
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
  // Home
  "home.hardwareTweaks": "Donanım ince ayarları",
  "home.hardwareSubtitle": "GPU, ekran, ağ bağdaştırıcıları, depolama, ses",
  "home.softwareTweaks": "Yazılım ince ayarları",
  "home.softwareSubtitle": "Windows, hizmetler, oyun başlatıcıları",
  "home.gameTweaks": "Oyun ince ayarları",
  "home.gameSubtitle": "Oyunun kendi yapılandırma dosyasındaki ayarlar",
  "home.readingSettings": "Mevcut ayarlarınız okunuyor…",
  "home.allOptimized": "Uygulanabilir her şey zaten en iyi durumda.",
  "home.cleanupTitle": "Kullanılabilir disk temizliği eylemleri",
  "home.cleanupUpkeepTitle": "Disk temizliği ve bakım",
  "home.measuringReclaim": "Geri kazanılabilecek alan ölçülüyor…",
  "home.nothingToReclaim": "Şu an geri kazanılacak bir şey yok.",
  "home.rowMeasuring": "— geri kazanılabilecek alan ölçülüyor…",
  "home.advisories": "Sizin müdahalenizi bekliyor",
  "home.advisoriesHint":
    "fpstune'un algılayabildiği ama yalnızca sizin değiştirebileceğiniz bulgular",
  "home.advisoriesClear": "Denetlendi, değişiklik gerekmiyor",
  "home.advisoriesClearHint":
    "fpstune'un denetleyip zaten doğru bulduğu donanım ayarları",
  "home.whatToDo": "Ne yapabilirsiniz:",
  "home.advisoriesUnread": "Denetlenemedi",
  "home.advisoriesUnreadHint":
    "bunlar bu makine hakkında hiçbir şey söylemiyor",
  "home.advisoryUnreadReason": "Hiçbir değer okunamadı: {reason}",
  "home.advisoryUnreadNeedsAdmin":
    "Hiçbir değer okunamadı. fpstune yönetici olarak çalışmıyor; birkaç denetim bunu gerektiriyor.",
  "home.advisoryUnreadNoReason":
    "Hiçbir değer okunamadı, dolayısıyla burada eyleme geçilecek bir bulgu yok.",
  "home.alreadyOptimized": "Zaten en iyi durumda",
  "home.detecting":
    "Ayarlarınız algılanıyor — {done}/{total} kategori okundu; listeler ve toplamlar sonuçlar geldikçe dolar…",
  "home.detectingProgress": "Ayar kategorilerinde algılama ilerlemesi",
  "home.statIdeal": "ayar ideal değerinde",
  "home.statIdealHint":
    "{changed} tanesini fpstune değiştirdi · {stock} tanesi zaten doğruydu",
  "home.statGuards": " · {count} sapma bekçisi nöbette",
  "home.measured": "Ölçüldü",
  "home.noMeasurement":
    "henüz kare hızı ölçülmedi — test sahnesini çalıştırmak için Ölçümler'i açın",
  "home.sceneLabel": "Test sahnesi, bu ekranın çözünürlüğünde",
  "home.ofTarget": "bu ekranın gösterebildiği {target} fps'in %{pct}'i",
  "home.noTarget": "ekran hedefi yok — panel yenileme hızı bilinmiyor",
  "home.claimed": "Henüz uygulanmamış ayarların vaadi",
  "home.latencyTweaks": "gecikme ayarı",
  "home.memoryTweaks": "bellek ayarı",
  "home.diskToReclaim": "geri kazanılabilir disk",
  // Cleanup & maintenance surfaces
  "cleanup.systemTitle": "Sistem Temizliği",
  "cleanup.systemDescription":
    "Temizlenecek öğeleri seçin. Silinen dosyalar geri getirilemez.",
  "cleanup.gameTitle": "Oyun Bakımı",
  "cleanup.gameDescription":
    "Oyun, GPU shader ve başlatıcı önbelleklerini temizler. Silinen dosyalar geri getirilemez; oyunlar ve sürücüler önbellekleri bir sonraki açılışta yeniden oluşturur.",
  "run.percent": "%{value}",
  "run.queued": "sırada",
  "run.skipped": "Uygulanmıyor",
  "run.elapsed": "{seconds} sn geçti",
  "run.showOutput": "çıktıyı göster",
  "run.hideOutput": "çıktıyı gizle",
  "run.commandLabel": "Çalıştırılan komut",
  "run.stepProgress": "{name} ilerlemesi",
  "run.noOutputYet": "Henüz çıktı yok.",
  "cleanup.calculating": "Hesaplanıyor…",
  "cleanup.freed": "{amount} boşaltıldı",
  "cleanup.failed": "Başarısız",
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
  "maintenance.title": "Sistem Bakımı",
  "maintenance.description": "Windows sistem sorunlarını onarır ve giderir.",
  "maintenance.running": "Çalışıyor...",
  "maintenance.dismHealthWarning":
    "Onarım dosyalarını indirmek için internet bağlantısı gerekebilir.",
  "maintenance.run": "Çalıştır",
  "maintenance.runCount": "Çalıştır ({count})",
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
  // Hardware surfaces
  "hw.ramSummary": "{total} GB RAM • {available} GB boş",
  "hw.title": "Donanım",
  "hw.admin": "Yönetici",
  "hw.notAdmin": "Yönetici Değil",
  "hw.cpu": "İşlemci",
  "hw.memory": "Bellek",
  "hw.gpu": "Ekran Kartı",
  "hw.displays": "Ekranlar",
  "hw.buses": "USB ve PCIe",
  "hw.storage": "Depolama",
  "hw.network": "Ağ",
  "hw.powerPlan": "Güç planı",
  "hw.audioOutput": "Ses Çıkışı",
  "hw.audioInput": "Ses Girişi",
  "hw.loudnessEq": "Ses Dengeleme",
  "hw.loudnessNotSupported": "Windows ses dengeleme yok: bu aygıtın sürücüsü Microsoft efektlerini yüklemiyor",
  "hw.loudnessNextStream": "Ses dengeleme değişti. Çalmakta olan ses, uygulaması yeniden başlayınca değişir.",
  "hw.audioDefault": "Varsayılan",
  "hw.notDetected": "Algılanamadı",
  "hw.copy": "Panoya kopyala",
  "device.toApply": "Uygulanacak {count}",
  "device.ideal": "İdeal",
  "device.noTweaks": "Bu cihazda ayarlanacak bir şey yok",
  "device.nothingToDo": "Bu cihazda yapılacak bir şey yok.",
  "device.open": "{name} cihazını Donanım sayfasında aç",
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
  "devices.advisoryHint":
    "fpstune bunları değiştiremez — her satır nereden değişeceğini söyler.",

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
  "monitor.noCap": "sınır yok",
  "monitor.fpsCap": "{count} fps sınırı",
  "monitor.recommendedPrefix": "önerilen:",
  "monitor.unknown": "bilinmiyor",
  "monitor.notApplicable": "uygulanamaz",
  "monitor.optimizeGsync": "G-Sync'i Optimize Et",
  "monitor.resetDriver": "Sürücü varsayılanlarına döndür",
  "monitor.resetting": "Sıfırlanıyor…",

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

  // Power plan card
  "power.activeHint":
    "FPS Balanced etkin — oyun istediğinde tam güç, boştaki çekirdekler yavaşlayabilir.",
  "power.inactiveHint":
    "FPS Balanced yük altında tam güç verir, boştaki çekirdeklerin yavaşlamasına izin verir — aynı kare hızına daha az ısı.",
  "power.activate": "FPS Balanced'ı Etkinleştir",
  "power.revert": "Windows Balanced'a Dön",
  "power.reverting": "Geri dönülüyor…",

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
    "Değiştirmek üzere olduğunuz ayarları Ayarlar sekmesinden seçin. Bir tur ancak değiştiğini bildiği ayarlar hakkında anlamlıdır — bu yüzden uygulananlardan tahmin etmek yerine hangileri olduğunu sorar.",
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

  // Software Tweaks tab

  // Game Tweaks tab
  "games.searchPlaceholder": "Oyun ayarlarında ara...",
  "games.searchLabel": "Oyun ayarlarında ara",
  "games.filterGame": "Oyuna göre süz",
  "games.allGames": "Tüm oyunlar",
  "games.reading": "Oyun yapılandırmalarınız okunuyor…",
  "games.noMatch": "Bu aramayla eşleşen oyun ayarı yok.",
  "games.noneFound":
    "Bu makinede desteklenen bir oyun yapılandırması bulunamadı. fpstune bir oyunun yapılandırmasını yalnızca oyun kuruluysa okur.",

  // Setting tooltip
  "tooltip.current": "Mevcut:",
  "tooltip.recommended": "Önerilen:",
  "tooltip.effect": "Etkisi:",
  "tooltip.howToChange": "Nasıl değiştirilir:",
  "tooltip.proven": "Kanıtlı",
  "tooltip.experimental": "Deneysel",
  "tooltip.likely": "Olası",
  "tooltip.ariaInfo": "{name} hakkında bilgi",
  "tooltip.provenDetail": "Kanıtlı: 3+ bağımsız kaynak",
  "tooltip.experimentalDetail":
    "Deneysel: güvenli ama modern sistemlerde kanıtlanmamış",
  "tooltip.monitorOnly":
    "FPSTune bunu kendiliğinden uygulayamaz — yalnızca izler.",
  "tooltip.sources": "Kaynaklar:",
  "tooltip.requiresRestart": "Sistemin yeniden başlatılması gerekir",

  // fpstune neyi değiştirdi, ölçüldü (ölçüm defteri)
  "ledger.homeTitle": "fpstune neyi değiştirdi, ölçüldü",
  "ledger.homeHint": "Her alan için tek araç. İkisi asla toplanmaz.",
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
  "ledger.noAreas": "Henüz hiçbir alan bildirilmedi.",
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
  "actions.undo": "Geri al ({count})",
  "actions.reset": "Windows varsayılanı ({count})",
  "actions.applyShort": "Uygula",
  "actions.undoShort": "Geri al",
  "actions.resetShort": "Windows varsayılanı",
  "actions.aria.apply": "{count} ayarı uygula: {name}",
  "actions.aria.undo": "{count} ayarı geri al: {name}",
  "actions.aria.reset": "{count} ayarı Windows varsayılanına döndür: {name}",
  "actions.confirm.apply": "{name} için {count} ayar uygulansın mı?",
  "actions.confirm.undo": "{count} ayar, fpstune'dan önce bu makinede olan değere dönecek.",
  "actions.confirm.reset": "{count} ayar Windows varsayılanına dönecek.",
  "actions.confirmBody.apply": "Her satır kendi sonucunu gösterir; her değişiklik aynı satırdan geri alınabilir.",
  "actions.confirmBody.undo": "Her ayar, fpstune'un bu makineyi ilk okuduğunda kaydettiği değeri geri alır.",
  "actions.confirmBody.reset": "Windows'un sunduğundan farklı olan her ayar ona geri döner. Her satır kendi sonucunu gösterir.",
  "settings.search": "Ayarlarda ara",
  "settings.searchPlaceholder": "Ayarlarda ara...",
  "settings.filterByCategory": "Kategoriye göre süz",
  "settings.allCategories": "Tümü",
  "settings.groupCount": "{toFix} düzeltilecek / {total} toplam",
  // Gerekenler / ideal bantları
  "bands.needs": "İşlem gerekiyor",
  "bands.ideal": "İdeal",
  "bands.nothingToDo": "Burada yapılacak bir şey yok.",
  "bands.showIdeal": "Zaten ideal olan {count} ayarı göster",
  "bands.hideIdeal": "Zaten ideal olan {count} ayarı gizle",
};

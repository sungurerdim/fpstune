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
  "tab.home": "Ana Sayfa",
  "tab.software": "Yazılım İnce Ayarları",
  "tab.hardware": "Donanım İnce Ayarları",
  "tab.games": "Oyun İnce Ayarları",
  "tab.cleanup": "Temizlik ve Onarım",
  "tab.benchmarks": "Ölçümler",

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

  // Locale switch
  "locale.switch": "Türkçeye geç",

  // Common actions
  "action.apply": "Uygula",
  "action.cancel": "Vazgeç",
  "action.run": "Çalıştır",
  "action.runAll": "Tümünü Çalıştır",
  "action.undo": "Geri Al",
  "action.reset": "Sıfırla",
  "action.verify": "Doğrula",
  "action.keep": "Koru",
  // Row surface
  "row.ok": "Tamam",
  "row.advisory": "Bilgilendirme",
  "row.verify": "Mevcut değeri doğrula",
  "row.undo": "fpstune'un değişikliğini geri al, {value} değerine dön",
  "row.undoNamed":
    "{name} için fpstune'un değişikliğini geri al, {value} değerine dön",
  "row.undoTooltip":
    "fpstune'un değişikliğini geri al — bu makinenin önceki değeri olan {value} geri gelir",
  "row.resetDefault": "Windows varsayılanına döndür",
  "row.target": "Hedef",
  "row.applyNamed": "Uygula: {name}",
  "sr.optimal": "Zaten önerilen değerde: ",
  "sr.currently": "Şu an ",
  "sr.recommendedIs": ", önerilen değer ",
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
  "home.applyAll": "Tümünü uygula ({count})",
  "home.readingSettings": "Mevcut ayarlarınız okunuyor…",
  "home.allOptimized": "Uygulanabilir her şey zaten en iyi durumda.",
  "home.cleanupTitle": "Kullanılabilir disk temizliği eylemleri",
  "home.measuringReclaim": "Geri kazanılabilecek alan ölçülüyor…",
  "home.nothingToReclaim": "Şu an geri kazanılacak bir şey yok.",
  "home.rowMeasuring": "— geri kazanılabilecek alan ölçülüyor…",
  "home.advisories": "Bilgilendirmeler",
  "home.advisoriesHint":
    "fpstune'un algılayabildiği ama yalnızca sizin değiştirebileceğiniz bulgular",
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
    "henüz kare hızı ölçülmedi — bir oyun başlatın ya da Ölçümler'i açın",
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
  "cleanup.results": "Temizlik Sonuçları",
  "cleanup.resultsEmpty":
    "Aşağıdan öğeleri seçip temizliği çalıştırın; boşalan alan burada görünür.",
  "cleanup.calculating": "Hesaplanıyor…",
  "cleanup.freed": "{amount} boşaltıldı",
  "cleanup.failedCount": "{count} başarısız",
  "cleanup.failed": "Başarısız",
  "cleanup.done": "Tamamlandı",
  "cleanup.serviceDown":
    "Hizmet çalışmıyor ve başlatılamadı. Hizmeti başlatıp bu sekmeyi yeniden açın.",
  "cleanup.runCleanup": "Temizliği Çalıştır",
  "cleanup.runCleanupCount": "Temizliği Çalıştır ({count})",
  "maintenance.title": "Sistem Bakımı",
  "maintenance.description": "Windows sistem sorunlarını onarır ve giderir.",
  "maintenance.running": "Çalışıyor...",
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
  "toolbar.processing": "İşleniyor…",
  "toolbar.stop": "Durdur",
  "toolbar.resetSelected": "Seçilenleri Sıfırla",
  "toolbar.applySelected": "Seçilenleri Uygula",
  "toolbar.resetToDefaults": "Varsayılanlara Sıfırla ({count})",
  // Hardware surfaces
  "hw.title": "Donanım",
  "hw.admin": "Yönetici",
  "hw.notAdmin": "Yönetici Değil",
  "hw.cpu": "İşlemci",
  "hw.memory": "Bellek",
  "hw.gpu": "Ekran Kartı",
  "hw.displays": "Ekranlar",
  "hw.storage": "Depolama",
  "hw.network": "Ağ",
  "hw.powerPlan": "Güç planı",
  "hw.audioOutput": "Ses Çıkışı",
  "hw.audioInput": "Ses Girişi",
  "hw.loudnessEq": "Ses Dengeleme",
  "hw.loudnessNotSupported": "Bu cihaz ses dengelemeyi desteklemiyor",
  "hw.notDetected": "Algılanamadı",
  "hw.copy": "Panoya kopyala",
  "devices.reading": "İnce ayarlar okunuyor…",
  "devices.showIdeal": "Zaten ideal olan ayarları göster",
  "devices.hideIdeal": "Zaten ideal olan ayarları gizle",
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
  "storage.running": "{action} çalışıyor…",
};

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
  "choice.at_capability": "Bağdaştırıcının en yükseğinde",
  "choice.below_capability": "Bağdaştırıcının en yükseğinin altında",
  "choice.good": "İyi",
  "choice.weak_signal": "Zayıf sinyal",
  "choice.on_2_4ghz": "2,4 GHz'de",
  "choice.legacy_cipher": "Eski şifre",
  "choice.wpa3_available": "WPA3 mümkün",
  "choice.not_throttling": "Kısılmıyor",
  "choice.throttling": "Kısılıyor",
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
  "cleanup.unavailable": "Kullanılamıyor",
  "cleanup.dockerWarning":
    "Sanal diski küçültmek için Docker Desktop'ı ve tüm WSL dağıtımlarını yeniden başlatır; birkaç dakika sürebilir.",
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
  "devices.fix": "Düzelt",
  "devices.advancedBadge": "İLERİ",

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
    "Ekranın gösterebildiğine karşı ölçülür. Görüntü kalitesine harcanacak kare olup olmadığına bu karar verir.",
  "headroom.measureNow": "Şimdi ölç",
  "headroom.measuring": "Ölçülüyor…",
  "headroom.startFailed": "Ölçüm başlatılamadı.",
  "headroom.readingLast": "Son sonuç okunuyor…",
  "headroom.needsGame":
    "Kare hızı ölçmek için ekranda bir şeyin çizilmesi gerekir. Bir oyun başlatın; fpstune ölçümü kendiliğinden alır — ya da oyun açıkken Şimdi ölç'e basın.",
  "headroom.runningNow": "şu an çalışıyor",
  "headroom.onePercentLow": "(%1 düşüklerde {value})",
  "headroom.againstTarget": "bu panelin {target} fps hedefine karşı",
  "headroom.measuredAgo": "Ölçüm: {age}",
  "headroom.gaugeLabel":
    "{game}: ekranın {target} fps hedefine karşı ölçülen kare hızı",
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
    "Bu oyun için henüz bir ölçüm yok ve sessizlik kanıt değildir — bu yüzden kare hızına mal olan hiçbir şey önerilmeyecek.",
  "headroom.gpuBound": "GPU'ya bağlı — kareler grafik ayarlarında saklı",
  "headroom.cpuBound": "CPU'ya bağlı — grafik ayarları bunu pek değiştirmez",
  "headroom.bothBound":
    "İki taraf da doymuş — tek başına grafik ayarları farkı kapatmaz",
  "headroom.presentMode": "Sunum modu: {mode}",

  // Benchmarks tab
  "bench.measure": "Ölç",
  "bench.verifyClaims": "İddiaları doğrula",
  // Measure (suite) panel
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
  "activity.short": "Etkinlik",
  "activity.title": "Etkinlik Günlüğü",
  "activity.open": "Etkinlik günlüğünü aç",
  "activity.close": "Etkinlik günlüğünü kapat",

  // Software Tweaks tab
  "settings.searchPlaceholder": "Ayarlarda ara...",
  "settings.searchLabel": "Ayarlarda ara",
  "settings.filterCategory": "Kategoriye göre süz",
  "settings.filterImpact": "Etkiye göre süz",
  "settings.allCategories": "Tüm kategoriler",
  "settings.allImpacts": "Tüm etkiler",
  "settings.optimized": "En iyi durumda",
  "settings.noOptimizedYet": "Henüz en iyi duruma getirilen ayar yok.",
  "settings.needsOptimization": "İyileştirme bekleyenler",
  "settings.nothingNeeds": "İyileştirme bekleyen bir şey yok.",
  "settings.fixAll": "Tümünü düzelt ({count})",
  "settings.appliedCount": "{count} uygulandı",
  "settings.failedCount": " · {count} başarısız",

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

  // Notifications
  "toast.errorsRegion": "Hatalar ve uyarılar",
  "toast.region": "Bildirimler",
  "toast.error": "Hata",
  "toast.warning": "Uyarı",
  "toast.success": "Başarılı",
  "toast.info": "Bilgi",
};

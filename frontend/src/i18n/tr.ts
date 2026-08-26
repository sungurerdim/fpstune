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
};

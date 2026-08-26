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
};

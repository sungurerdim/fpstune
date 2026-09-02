/**
 * Turkish forms of the setting copy, keyed by setting id (F3).
 *
 * The English source of truth stays in the backend registry per C4; these
 * are the edge translations `i18n/settings.ts` resolves when the locale is
 * Turkish. Per-adapter settings are keyed on the stable pattern
 * `network:*:<name>` — the machine-specific interface index never appears
 * in source (C9). An id missing here falls back to English, visibly.
 */
export const settingsTr: Record<
  string,
  { name: string; description: string; effect?: string }
> = {
  "power:cpu_min_parking": {
    name: "Uyanık tutulan çekirdekler",
    description:
      "Etkin kalacak asgari CPU çekirdeği yüzdesi. %100, çekirdek park etmeyi kapatır ve park edilmiş çekirdeklerin uyanma gecikmesini ortadan kaldırır.",
  },
  "power:power_throttling": {
    name: "CPU güç kısması",
    description:
      "Windows, arka plan saydığı işlemleri güç tasarrufu için kısar; dizüstünde buna oyunun ses, shader derleme ve hile koruması gibi yan işlemleri de girebilir. Kapatmak bu iş parçacıklarını tam hızda tutar.",
  },
  "power:cpu_boost": {
    name: "CPU hızlanma davranışı",
    description:
      "CPU'nun yük altında yüksek frekanslara ne kadar agresif çıkacağını belirler. Efficient Aggressive, daha az güç taşmasıyla neredeyse en yüksek performansı verir.",
  },
  "power:cpu_increase_threshold": {
    name: "Hızlanma tetik noktası",
    description:
      "Frekans artışını tetikleyen CPU kullanım yüzdesi. Düşük değerler frekansın daha hızlı yükselmesini sağlar ve CPU kaynaklı kare süresi sıçramalarını azaltır.",
  },
  "power:cpu_decrease_threshold": {
    name: "Yavaşlama tetik noktası",
    description:
      "Frekansın düşürüldüğü CPU kullanım eşiği. Yüksek değerler CPU'yu daha uzun süre hızda tutar ve oyun sırasında frekansın inip çıkmasını azaltır.",
  },
  "power:cpu_increase_policy": {
    name: "CPU'nun hızlanma biçimi",
    description:
      "Frekans yükseltilirken kullanılan algoritma. Rocket doğrudan gereken en yüksek frekansa sıçrar; Ideal kademeli adımlar kullanır.",
  },
  "power:cpu_decrease_policy": {
    name: "CPU'nun yavaşlama biçimi",
    description:
      "Frekans düşürülürken kullanılan algoritma. Rocket anında düşer; Ideal kademeli iner. Rocket, gerektiğinde daha hızlı geri yükselmeye izin verir.",
  },
  "power:cpu_epp": {
    name: "Performans-pil dengesi",
    description:
      "CPU donanım zamanlayıcısına verilen performans-verimlilik dengesi ipucu. Düşük değerler performansa yaslanır; 0 = en yüksek performans, 100 = en yüksek verimlilik.",
  },
  "power:cpu_min_state": {
    name: "Asgari CPU hızı",
    description:
      "İş yokken CPU'nun inebileceği en düşük hız. 100'e çekmek her çekirdeği gün boyu en yüksek çarpanda sabitler: sürekli ısı üretir ve tek bir kare kazandırmaz.",
  },
  "power:cpu_max_state": {
    name: "Azami CPU hızı",
    description:
      "CPU'nun çıkabileceği en yüksek hız. Daha serin çalışsın diye 99'a çekme tavsiyesi turboyu tamamen kapatarak çalışır; kazandırdığı ısıdan çok daha fazla performansa mal olur.",
  },
  "power:cpu_idle_states": {
    name: "CPU boşta uyku",
    description:
      "Çekirdeklerin iş yokken düşük güç C-durumlarına girip giremeyeceği. Kapatmak, tek kare kazandırmadan sürekli ısı üreten ve parçanın ömrünü kısaltan, çok tekrarlanan bir oyun 'tweak'idir.",
  },
  "power:cpu_perf_check_interval": {
    name: "CPU yük kontrol aralığı",
    description:
      "Windows'un saat hızını değiştirip değiştirmeme kararı için işlemci yüküne ne sıklıkla baktığı. Aralık, yük değiştikten sonra bir çekirdeğin yanlış hızda ne kadar kalabileceğini iki yönde de sınırlar.",
  },
  "power:cpu_decrease_time": {
    name: "Yavaşlama gecikmesi",
    description:
      "CPU'nun düşük saat hızına inmesi için üst üste kaç boş yük kontrolü gerektiği. Varsayılan 1'de, iki kare arasındaki tek sessiz aralık bile bir sonraki karenin geri ödemek zorunda kalacağı bir yavaşlamayı başlatır.",
  },
  "power:cpu_increase_time": {
    name: "Hızlanma gecikmesi",
    description:
      "CPU'nun hız yükseltmesi için üst üste kaç yüklü kontrol gerektiği. Windows zaten mümkün olan en hızlı değerle gelir; bu ayar, başka bir şeyin onu yükselttiğini fark etmek için var.",
  },
  "power:cpu_latency_hint_unpark": {
    name: "Ani yük için ek çekirdek",
    description:
      "Windows tepki süresine duyarlı bir iş yükü algıladığı anda geri açtığı çekirdek payı. Boştaki çekirdek park etmeyi güvenli kılan budur: çekirdekler dinlenebilir, ama oyun hepsini teker teker değil bir anda geri alır.",
  },
  "power:cpu_latency_hint_perf": {
    name: "Ani yük için ek hız",
    description:
      "Windows gecikmeye duyarlı bir iş yükü algıladığında sıçradığı saat hızı. 100'ün altındaki her değer, anında tepki isteyen oyunun makinenin verebileceğinden azını alması demektir.",
  },
  "power:cpu_parking_increase_policy": {
    name: "Çekirdeklerin uyanma biçimi",
    description:
      "Yük arttığında Windows'un park edilmiş çekirdeklerden kaçını geri getirdiği. Hepsini birden uyandırmak gerektikleri anda hiçbir şeye mal olmaz ve maç yüklenirken teker teker uyanmanın basamak etkisini önler.",
  },
  "power:cpu_parking_increase_time": {
    name: "Çekirdek uyanma gecikmesi",
    description:
      "Park edilmiş bir çekirdeğin geri gelmesi için kaç yük kontrolü geçmesi gerektiği. Varsayılan 3, bir iş parçacığının zaten var olan bir çekirdeği beklediği üç aralıktır.",
  },
  "power:usb_selective_suspend": {
    name: "USB uykusu",
    description:
      "Boştaki USB aygıtlarını uyutur. Fare/klavye gecikmesine yol açabilir.",
  },
  "power:pcie_link_state": {
    name: "PCI-E güç tasarrufu",
    description:
      "Boşta PCIe bağlantı hızını düşürerek güç tasarrufu yapar. GPU mikro takılmalarına ve kare süresi sıçramalarına yol açabilir.",
  },
  "power:disk_timeout": {
    name: "Disk uyku sayacı",
    description:
      "Boştaki sabit diskin durdurulmasından önceki saniye. 0 durdurmayı kapatır ve oyun sırasında dosyaya erişirken yeniden dönme gecikmesini ortadan kaldırır.",
  },
  "power:thermal_cooling": {
    name: "Önce fan mı, önce yavaşlama mı",
    description:
      "Sıcaklık yükselince sistemin önce fanı mı (aktif) yoksa CPU kısmayı mı (pasif) kullanacağını belirler. Aktif soğutma termal kısmayı önler.",
  },
  "power:wlan_power_saving": {
    name: "Wi-Fi güç tasarrufu",
    description:
      "Wi-Fi bağdaştırıcısını paketler arasında uyutur. Oyun sırasında 20-100 ms ping sıçramalarına yol açar.",
  },
  "power:hibernation": {
    name: "Hazırda beklet",
    description:
      "Tüm RAM içeriğini kapalıyken hızlı uyanmak için diske (hiberfil.sys) yazar. Kapatmak 4-16 GB SSD alanı boşaltır.",
  },
  "power:ryzen_balanced_plan": {
    name: "AMD Ryzen güç planı",
    description:
      "AMD'nin kendi güç planının etkin olup olmadığı. Ryzen 1000-3000 CPU'larda Precision Boost 2'nin AMD'nin amaçladığı gibi davranması için gerekir.",
  },
  "timer:global_timer_resolution": {
    name: "Windows zamanlayıcı hassasiyeti",
    description:
      "Zamanlayıcı çözünürlüğü isteklerini işlem başına değil sistem genelinde uygular.",
  },
  "priority:gpu_priority": {
    name: "Oyuna GPU önceliği",
    description: "Oyun süreçleri için GPU zamanlama önceliği (0-31).",
  },
  "priority:game_priority": {
    name: "Oyuna CPU önceliği",
    description: "Oyun görev önceliği (1-6; 6 en yüksek).",
  },
  "priority:system_responsiveness": {
    name: "Arka plana ayrılan CPU",
    description: "Ön plan uygulama önceliği (0 = azami ön plan önceliği).",
  },
  "priority:scheduling_category": {
    name: "Oyun zamanlama sınıfı",
    description:
      "Multimedya sınıf zamanlayıcısının oyunlara atadığı MMCSS zamanlama kategorisi. Yüksek kategoriler öncelikli CPU erişimi ve daha düşük zamanlama gecikmesi alır.",
  },
  "priority:win32_priority_separation": {
    name: "Ön plan CPU payı",
    description:
      "CPU zaman dilimi dağıtımını belirler. Sabit kısa kuantumlar daha düşük giriş gecikmesi demektir.",
  },
  "priority:sfio_priority": {
    name: "Oyun depolama önceliği",
    description:
      "Oyun süreçleri için zamanlanmış dosya G/Ç önceliği. Yüksek değer, oyun varlıklarının daha hızlı yüklenmesi demektir.",
  },
  "visual:animations": {
    name: "Pencere animasyonları",
    description:
      "Windows arayüz animasyonlarını ve menü gecikmelerini denetler. Kapatmak görsel gecikmeyi kaldırır ve GPU/CPU döngülerini oyunlara bırakır.",
  },
  "visual:transparency": {
    name: "Saydamlık efektleri",
    description: "Pencere saydamlık efektleri (GPU kullanır).",
  },
  "visual:smooth_scrolling": {
    name: "Akıcı kaydırma",
    description:
      "Gezgin'de ve uygulamalarda animasyonlu kaydırmayı denetler. Kapatmak animasyon yükü olmadan anında kaydırma tepkisi verir.",
  },
  "storage:trim_enabled": {
    name: "SSD TRIM",
    description:
      "Kullanılmayan blokları SSD'ye bildirir. Yazma hızını korur ve sürücü ömrünü uzatır.",
  },
  "storage:disable_8dot3": {
    name: "Eski tip kısa dosya adları",
    description:
      "Her dosya için eski 8.3 DOS adları üretir. Kapatmak gereksiz G/Ç yükünü kaldırır.",
  },
  "storage:disable_last_access": {
    name: "Dosya erişim zamanı kaydı",
    description:
      "Her dosya okumasında son erişim zamanını günceller. Kapatmak gereksiz SSD yazmalarını azaltır.",
  },
  "network:wifi_radio_when_wired": {
    name: "Kabloda Wi-Fi kapalı",
    description:
      "Etkin bir Wi-Fi bağdaştırıcısı hiçbir şeye bağlı değilken bile ağ taramaya devam eder ve her tarama oyunla yarışan çekirdek işidir.",
  },
  "network:tcp_auto_tuning": {
    name: "Ağ penceresi otomatik ayarı",
    description:
      "TCP alma penceresi boyutunu dinamik ayarlar. Normal mod çoğu bağlantı için en iyi aktarım hızını verir.",
  },
  "network:nagle_algorithm": {
    name: "Nagle paket biriktirme",
    description:
      "TcpNoDelay ile kapatılan TCP küçük paket biriktirmesi. Nagle UDP'ye hiç dokunmaz ve modern rekabetçi oyunların neredeyse tamamı UDP'dir; onlar için hiçbir şeyi değiştirmez.",
  },
  "network:tcp_ack_frequency": {
    name: "TCP onay sıklığı",
    description:
      "Onaydan önce beklenecek segment sayısı (TcpAckFrequency); Windows varsayılanı 2, 1 her segmenti onaylar. Yalnız TCP'yi etkiler; UDP oyun trafiğine dokunmaz.",
  },
  "network:tcp_del_ack_ticks": {
    name: "TCP gecikmeli onay sayacı",
    description:
      "100 ms adımlarla gecikmeli onay sayacı (TcpDelAckTicks); Windows varsayılanı 2, 0 kapatır. Windows 2000 dönemi bir anahtar; yalnız TCP'yi etkiler, UDP oyun trafiğini etkilemez.",
  },
  "network:scaling_heuristics": {
    name: "Otomatik ayarın Windows engeli",
    description:
      "Eski bir ayar (Windows 8.1 sonrasında etkisiz). Sezgisel kısıtlama varsayılan olarak kapalıdır.",
  },
  "network:congestion_provider": {
    name: "Tıkanıklık kontrol algoritması",
    description:
      "TCP'nin ağ tıkanıklığına nasıl tepki vereceğini belirler. CUBIC, modern ağlar için en iyi durumdaki algoritmadır.",
  },
  "network:receive_side_scaling": {
    name: "Ağ yükünü çekirdeklere dağıt",
    description:
      "Ağ paketi işlemesini tek çekirdek yerine birden çok CPU çekirdeğine dağıtır. Daha yüksek aktarım sağlar ve tek çekirdeğin ağ darboğazı olmasını önler.",
  },
  "network:receive_segment_coalescing": {
    name: "Gelen paketleri biriktirme",
    description:
      "Gelen TCP segmentlerini işletim sistemine vermeden önce büyük öbeklerde birleştirir. Kapatmak bu biriktirmenin yapay gecikmesini önler.",
  },
  "network:throttling_index": {
    name: "Medya için ağ kısması",
    description:
      "Windows multimedya çalışırken ağ bant genişliğini sınırlar. Tam hız için kapatın.",
  },
  "network:dns_security": {
    name: "Güvenli DNS",
    description:
      "Alan adı sorgularını hangi çözümleyicinin yanıtladığını ve zararlı ile oltalama alanlarının daha çözümlenmeden engellenip engellenmediğini belirler. Quad9 bu alanları süzer; burada sunulan çözümleyicilerin hiçbiri oyun CDN'inin daha yakın indirme sunucusu seçmesini sağlayan istemci-alt-ağ ipucunu göndermez.",
  },
  "network:dns_over_https": {
    name: "HTTPS üzerinden DNS",
    description:
      "DNS sorgularını düz metin UDP 53 yerine HTTPS üzerinden gönderir. Onsuz seçilen çözümleyici ağda görünür ve zararlı süzmesi yolda soyulabilir.",
  },
  "network:dns_local_priority": {
    name: "Yerel DNS önbellek önceliği",
    description:
      "Yerel çözümleyici önbelleğinin arama önceliği. Düşük değer daha önce bakılması demektir. İyileştirilmiş: 4 (varsayılan: 499).",
  },
  "network:dns_hosts_priority": {
    name: "Hosts dosyası önceliği",
    description:
      "Hosts dosyasının arama önceliği. Düşük değer daha önce bakılması demektir. İyileştirilmiş: 5 (varsayılan: 500).",
  },
  "network:dns_query_priority": {
    name: "DNS sorgu önceliği",
    description:
      "DNS sunucusu sorgu önceliği. Düşük değer daha önce sorulması demektir. İyileştirilmiş: 6 (varsayılan: 2000).",
  },
  "network:dns_netbt_priority": {
    name: "NetBIOS çözümleme önceliği",
    description:
      "NetBIOS çözümleme önceliği. Düşük değer daha önce sorulması demektir. İyileştirilmiş: 7 (varsayılan: 2001).",
  },
  "network:qos_bandwidth": {
    name: "QoS bant genişliği payı",
    description:
      "Windows'un QoS için ayırdığı bant genişliği yüzdesi (NonBestEffortLimit). 0 = ayırma yok.",
  },
  "network:qos_nla": {
    name: "QoS ev-dışı ağ istisnası",
    description:
      "QoS'un ev dışı ağlarda kısmasını önler. 'Do not use NLA'=1 yazar.",
  },
  "network:tcp_fast_open": {
    name: "TCP hızlı açılış",
    description:
      "TCP el sıkışması sırasında veri göndererek yeni bağlantılarda 1 gidiş-dönüş kazandırır. Eşleştirmeyi hızlandırır.",
  },
  "network:max_user_port": {
    name: "Azami bağlantı portu",
    description:
      "Geçici port aralığının üst sınırı. Yüksek değer, eşzamanlı bağlantılar için daha fazla giden port demektir.",
  },
  "network:tcp_num_connections": {
    name: "Azami TCP bağlantısı",
    description:
      "Eşzamanlı azami TCP bağlantısı. 65534 bağlantı tablosunun taşmasını önler.",
  },
  "network:tcp_timed_wait_delay": {
    name: "Kapanan port bekleme süresi",
    description:
      "Kapanan soketlerin port yeniden kullanılmadan önce beklediği süre. Düşük değer portların daha hızlı dönmesi demektir.",
  },
  "network:ipv6_privacy": {
    name: "IPv6 gizlilik adresleri",
    description:
      "Gizlilik için geçici IPv6 adresleri üretir. Kapatmak ek yükü azaltır.",
  },
  "network:ipv6_random_identifiers": {
    name: "IPv6 rastgele kimlikler",
    description:
      "IPv6 arayüz kimliklerini rastgeleleştirir. Kapatmak kararlı bağlantılar sağlar.",
  },
  "network:teredo": {
    name: "Teredo tüneli",
    description:
      "IPv4 NAT üzerinden IPv6 tünelleme. Oyun için gerekmez; etkinken gecikme ekler.",
  },
  "network:tcp_timestamps": {
    name: "TCP zaman damgaları",
    description:
      "Her TCP paketine zaman damgası ekler. Kapatmak oyun için başlık yükünü azaltır.",
  },
  "network:tcp_ecn": {
    name: "Tıkanıklık erken uyarısı (ECN)",
    description:
      "Ağ tıkanıklığı sinyali. Bazı yönlendiricilerle gecikme sıçramalarına yol açabilir.",
  },
  "network:default_ttl": {
    name: "Paket yaşam süresi (TTL)",
    description:
      "Paketlerin başlangıç Time-To-Live değeri. 64 idealdir (Linux/macOS varsayılanı).",
  },
  "gpu-nvidia:low_latency": {
    name: "Düşük gecikme modu",
    description:
      "NVIDIA Reflex / Ultra Low Latency modu. Önceden hazırlanan kare sayısını denetler.",
  },
  "gpu-nvidia:vsync": {
    name: "V-Sync",
    description:
      "Sürücüde kare eşitleme. VRR panel ve yenileme hızının altındaki bir kare sınırıyla V-Sync oyun sırasında hiç devreye girmez; yalnızca sınır kısa süre aşılırsa yırtılmayı önleyen emniyet ağı olur.",
  },
  "gpu-nvidia:power_mode": {
    name: "GPU güç modu",
    description:
      "GPU'nun en yüksek saat durumundan ne zaman inebileceğini belirler. Optimal, oyun çalışırken zaten tam saat hızındadır; azamiye zorlamak yalnızca boş masaüstünde yaptığını değiştirir.",
  },
  "gpu-nvidia:threaded_opt": {
    name: "Sürücü çoklu iş parçacığı",
    description:
      "GPU sürücüsünün çoklu iş parçacığı kullanımı. Auto kararı sürücüye bırakır (en güvenlisi). On, OpenGL'de takılmaya yol açabilir.",
  },
  "gpu-nvidia:shader_cache": {
    name: "Shader önbelleği",
    description:
      "Derlenmiş shader'ları diske kaydeder. Oyun yüklemeyi hızlandırır.",
  },
  "gpu-nvidia:texture_quality": {
    name: "Doku filtreleme kalitesi",
    description:
      "Doku filtreleme kalitesi. Quality, çoğu oyunda High Quality ile görsel olarak aynıdır.",
  },
  "gpu-nvidia:vrr_mode": {
    name: "G-Sync",
    description:
      "NVIDIA Denetim Masası'nın G-SYNC kapsamını yansıtan değişken yenileme hızı modu. 'on' pencereli ve kenarlıksızın yanında tam ekranı da kapsar. G-Sync/FreeSync uyumlu monitör gerektirir.",
  },
  "gpu-nvidia:fps_limit": {
    name: "Kare hızı sınırı",
    description:
      "Sürücü düzeyinde kare sınırı. Panelin yenileme hızının hemen altında tutulur ki kare hızı G-Sync penceresinde kalsın: sunumu ekran yönetir, V-Sync hiç devreye girmez.",
  },
  "gpu-nvidia:bg_app_fps": {
    name: "Arka plan kare sınırı",
    description:
      "NVIDIA'nın odak dışı pencereler için kare sınırı; sürücü bunu, katmanları ön plan algısını şaşırtan odaktaki oyunlara da uygulayabiliyor. Kapalı tutun.",
  },
  "gpu-nvidia:aniso_sample_opt": {
    name: "Anizotropik kısayol",
    description:
      "Anizotropik filtreleme örneklerini küçük bir performans kazancı için azaltır.",
  },
  "gpu-nvidia:texture_lod_bias": {
    name: "Doku keskinlik eğilimi",
    description:
      "Doku filtrelemede negatif LOD eğilimini denetler. Clamp bulanık dokuları önler.",
  },
  "gpu-nvidia:ogl_thread_opt": {
    name: "OpenGL iş parçacığı",
    description:
      "Çok iş parçacıklı OpenGL. Auto kararı sürücüye bırakır (en güvenlisi). Çoğu oyun OpenGL değil DirectX kullanır.",
  },
  "gpu-nvidia:cuda_force_p2": {
    name: "CUDA bellek saati sınırı",
    description:
      "CUDA uygulamaları için daha yüksek GPU güç durumu zorlar. GPU hesaplama işleri için yararlıdır.",
  },
  "gpu-nvidia:max_prerendered": {
    name: "Önceden kuyruklanan kareler",
    description:
      "CPU'nun önceden hazırladığı kare kuyruğunun derinliği. Düşük değerler giriş gecikmesini azaltır ama aktarımı düşürebilir. İnce ayar için Düşük Gecikme Modu ile birlikte çalışır.",
  },
  "gpu-nvidia:triple_buffer": {
    name: "Üçlü arabellek",
    description:
      "V-Sync için üçüncü bir kare arabelleği ekler. V-Sync açıkken akıcılığı artırabilir ama gecikme ekler. Rekabetçi oyunda kapalı tutun.",
  },
  "gpu-nvidia:vrr_app_override": {
    name: "Uygulama bazlı G-Sync",
    description:
      "Uygulama başına G-Sync/VRR geçersiz kılma. Sürücü varsayılanı genel ayarı uygular. Force on, kenarlıksız pencereli oyunlarda G-Sync'i garantiler.",
  },
  "gpu-nvidia:fan_curve": {
    name: "GPU fan eğrisi",
    description:
      "GPU çekirdek ile bellek sıcak nokta sıcaklığını karşılaştırır. Sıcak nokta çekirdeği 20°C'den fazla aşıyorsa fan eğrisi fazla pasif olabilir. MSI Afterburner'dan ayarlayın.",
  },
  "gpu-nvidia:battery_boost": {
    name: "Pilde kare sınırı",
    description:
      "NVIDIA App'in dizüstü pildeyken oyunları 30 FPS civarında tutup tutamayacağı. Sınır bir hata değil bir özellik; ama maçın ortasında kimsenin istemediği bir tavandır.",
  },
  "gpu-amd:anti_lag": {
    name: "Anti-Lag",
    description:
      "AMD Anti-Lag, CPU ve GPU iş yüklerini eşitleyerek giriş gecikmesini azaltır.",
  },
  "gpu-amd:shader_cache": {
    name: "Shader önbelleği",
    description:
      "Derlenmiş shader'ları daha hızlı oyun yükleme için diske kaydeder.",
  },
  "gpu-amd:vsync": {
    name: "V-Sync",
    description:
      "Kareleri monitör yenileme hızına eşitler. Yırtılmayı önler ama giriş gecikmesi ekler.",
  },
  "gpu-amd:radeon_boost": {
    name: "Radeon Boost",
    description:
      "Kamera hızlı hareket ederken render çözünürlüğünü düşürür ve görüntü durulunca geri yükler, böylece %5-15 daha fazla kare verir. Bedeli tam hedef takibi anında ödenir: fazladan kareler, en çok gerektiği anda netlik karşılığında alınır.",
  },
  "gpu-amd:enhanced_sync": {
    name: "Enhanced Sync",
    description:
      "Giriş gecikmesi eklemeden yırtılmayı azaltan V-Sync alternatifi. FPS yenileme hızının üstündeyken en iyisidir.",
  },
  "gpu-amd:chill": {
    name: "Radeon Chill",
    description:
      "Ekrandaki hareket azaldığında kare hızını düşürür — maçın ortasında bile. Sınır siz kımıldayınca kalkar, ama tam da o kareye ihtiyacınız olduktan sonra kalkar.",
  },
  "gpu-amd:frtc": {
    name: "Kare hızı sınırı (FRTC)",
    description:
      "AMD GPU'lar için genel FPS sınırı. Etkinken oyun ayarlarından bağımsız azami FPS'i sınırlar. Sınırsız performans için kapatın.",
  },
  "gpu-hardware:resizable_bar": {
    name: "Resizable BAR",
    description:
      "CPU'nun GPU belleğinin tamamına erişmesini sağlayan PCIe özelliği. BIOS'tan açılır (Resizable BAR + Above 4G Decoding). NVIDIA sürücü düzeyinde sessizce kapatabilir.",
  },
  "gpu-hardware:gpu_assignment": {
    name: "Oyunu çalıştıran GPU",
    description:
      "Makinede hem tümleşik hem ayrık GPU varken oyunlarınızın hangisinde çalıştığı. Tümleşik çipe düşmek, makinenin kare hızının çoğuna mal olur.",
  },
  "gpu-hardware:msi_mode": {
    name: "GPU kesme modu",
    description:
      "GPU kesmelerini paylaşımlı eski IRQ hattı yerine aygıt başına MSI ile iletir. RTX 40 serisi MSI açık gelir; 30 serisi ve daha eski kartlar sıkça hat tabanlı kesmede kalır.",
  },
  "display:windowed_flip_model": {
    name: "Pencereli oyun hızlı yolu",
    description:
      "DX10-DX11 pencereli/kenarlıksız oyunlar için flip-model sunumu açar. Daha düşük gecikme sağlar, Auto HDR ve VRR'yi mümkün kılar.",
  },
  "display:mpo_disable": {
    name: "Çoklu düzlem katmanı",
    description:
      "GPU görüntü motorunun pencereleri donanımda birleştirip birleştirmediği. Özellikle karışık yenileme hızlı çok monitörlü kurulumlarda titremeye ve kare aralığı sorunlarına yol açabilir.",
  },
  "memory:purge_standby": {
    name: "Bekleme belleğini temizle",
    description:
      "Önbelleğe alınmış belleği temizler. 16 GB altı RAM'li sistemler için önerilir.",
  },
  "services:MMCSS": {
    name: "Multimedya zamanlayıcı hizmeti",
    description:
      "Oyun ve multimedya için iş parçacığı öncelik hizmeti. Kapatmak tüm MMCSS öncelik ayarlarını bozar.",
  },
  "services:SysMain": {
    name: "Superfetch ön yükleme",
    description:
      "Uygulamaları belleğe önceden getirir ve bellek sıkıştırmayı yönetir. SSD'li sistemlerde kapatın.",
  },
  "services:DiagTrack": {
    name: "Windows telemetri hizmeti",
    description: "Tanılama verilerini toplar ve Microsoft'a gönderir.",
  },
  "services:WSearch": {
    name: "Windows arama dizini",
    description:
      "Daha hızlı arama için dosyaları dizinler. Disk G/Ç'sini azaltmak için kapatın.",
  },
  "services:NvTelemetryContainer": {
    name: "NVIDIA telemetrisi",
    description: "NVIDIA kullanım verisi toplama. Kapatmak CPU/RAM kazandırır.",
  },
  "services:NahimicService": {
    name: "Nahimic ses hizmeti",
    description:
      "Takılmaya yol açabilen ses geliştirme hizmeti. Kapatması güvenlidir.",
  },
  "services:Fax": {
    name: "Faks hizmeti",
    description: "Faks iletimini yönetir. Modern sistemlerde gerekmez.",
  },
  "services:WerSvc": {
    name: "Hata raporlama hizmeti",
    description:
      "Çökme raporlarını Microsoft'a gönderir. Kapatması güvenlidir.",
  },
  "services:RetailDemo": {
    name: "Mağaza demo hizmeti",
    description:
      "Mağazalar için tanıtım modu. Kişisel bilgisayarlarda gerekmez.",
  },
  "services:dmwappushservice": {
    name: "WAP anında ileti hizmeti",
    description:
      "MDM/Intune cihaz yönetimi iletileri. İş/okul yönetimli cihazlarda açık kalmalı!",
  },
  "services:XblAuthManager": {
    name: "Xbox oturum hizmeti",
    description:
      "Xbox Live kimlik doğrulaması. Xbox Game Save buna bağlıdır. Game Pass kullanıyorsanız açık bırakın!",
  },
  "services:XblGameSave": {
    name: "Xbox bulut kayıtları",
    description:
      "Xbox bulut kayıtları. Xbox Game Pass veya Play Anywhere kullanıyorsanız açık bırakın!",
  },
  "services:XboxNetApiSvc": {
    name: "Xbox ağ hizmeti",
    description:
      "Xbox çok oyunculu ağ hizmeti. Xbox Game Pass veya Play Anywhere kullanıyorsanız açık bırakın!",
  },
  "services:XboxGipSvc": {
    name: "Xbox aksesuar hizmeti",
    description:
      "Xbox kumanda yönetimi. Xbox kumandası kullanıyorsanız açık bırakın!",
  },
  "services:background_apps": {
    name: "Arka plan uygulamaları",
    description:
      "Uygulamaların arka planda çalışmasına izin verir. Kapatmak ciddi RAM kazandırır.",
  },
  "services:telemetry_tasks": {
    name: "Telemetri zamanlanmış görevleri",
    description:
      "Windows telemetri zamanlanmış görevlerini tek kavram olarak kapatır. Aynı gizlilik kavramını paylaşan DiagTrack/CEIP/Customer Experience görevlerini bir arada ele alır.",
  },
  "services:UCPD": {
    name: "Tarayıcı seçimi koruma sürücüsü",
    description:
      "Varsayılan uygulama ilişkilendirmelerinin üçüncü taraflarca değiştirilmesini engelleyen gizli Microsoft sürücüsü. Bazı sistem ayarlarına karışabilir.",
  },
  "system:large_system_cache": {
    name: "Uygulama-önbellek bellek dengesi",
    description:
      "Windows'un dosya önbelleğini büyütmek için çalışan programları kırpıp kırpmadığı. Sunucu cevabı oyunları bellekten mahrum bırakır; iş istasyonu varsayılanı oyun bilgisayarının istediğidir.",
  },
  "system:driver_updates_protection": {
    name: "Windows Update sürücü koruması",
    description:
      "Windows Update'in elle kurduğunuz GPU veya aygıt sürücülerini eski genel sürümlerle sessizce değiştirmesini önler.",
  },
  "system:delivery_optimization": {
    name: "Güncelleme paylaşımı (P2P)",
    description:
      "Windows Update P2P paylaşımı, güncellemeleri internet üzerinden başka bilgisayarlara yükler ve oyun sırasında yükleme bant genişliğini tüketir.",
  },
  "system:delivery_optimization_bandwidth": {
    name: "Güncelleme indirme sınırı",
    description:
      "Windows Update'in arka plan indirmelerini hattın %20'siyle sınırlar. Asimetrik bir bağlantıda sınırsız bir güncelleme indirmesi kuyruğu doldurur ve oyun paketleri dahil her paketi bekletir.",
  },
  "system:onedrive_upload_limit": {
    name: "OneDrive yükleme sınırı",
    description:
      "OneDrive eşitlemesini yükleme hızının %30'uyla sınırlar. Ev fiberi asimetriktir; bir eşitleme patlaması çok daha küçük olan yukarı hattı doldurur ve makineden çıkan her pakete kuyruğa girme gecikmesi ekler.",
  },
  "system:windows_update_mode": {
    name: "Windows Update davranışı",
    description:
      "Otomatik güncellemeler oyun sırasında arka plan indirmeleri ve CPU/disk kullanımı tetikler. Yalnızca bildir modu kurulum zamanını size bırakır.",
  },
  "system:coinstallers": {
    name: "Sürücü yan yazılım kurulumları",
    description:
      "Yeni bir aygıt takıldığında (fare, kulaklık, klavye) yardımcı kurucular Razer Synapse veya Logitech G Hub gibi üretici yazılımlarını arka planda kendiliğinden kurar.",
  },
  "system:widgets": {
    name: "Windows widget'ları",
    description:
      "Görev çubuğundaki haberler ve ilgi alanları paneli. Görünmezken bile RAM ve CPU tüketen bir arka plan WebView2/Edge işlemi çalıştırır.",
  },
  "system:file_explorer_launch": {
    name: "Dosya Gezgini açılış görünümü",
    description:
      "Dosya Gezgini'nin varsayılan olarak nerede açıldığı. 'Bu bilgisayar' buluta bağlı Giriş/Hızlı Erişim yerine sürücüleri anında gösterir.",
  },
  "system:hyper_v": {
    name: "Hyper-V sanallaştırma",
    description:
      "Windows'u Hyper-V hipervizörü altında sanal makine konuğu olarak çalıştırır. İkinci düzey adres çevirisi (SLAT) yükünden %5-15 FPS kaybına yol açar.",
  },
  "system:vm_platform": {
    name: "Sanal makine platformu",
    description:
      "Android uygulamaları ve WSL2 için Windows sanallaştırması. Bu özellikler kullanılmıyorsa kapatmak sanallaştırma yükünü kaldırır.",
  },
  "system:xmp_expo": {
    name: "RAM anma hızı profili (XMP)",
    description:
      "RAM'in anma XMP/EXPO hızında mı yoksa daha yavaş JEDEC varsayılanında mı çalıştığını algılar. Düzeltmek için BIOS'tan XMP (Intel) veya EXPO (AMD) açın. BIOS güncellemeleri bunu sessizce sıfırlar.",
  },
  "system:thermal_condition": {
    name: "CPU ısı payı",
    description:
      "Sistem termal bölge sıcaklığını okur. Yüksek sıcaklık (>80°C) termal kısma riskine işaret eder. Termal macunu yenilemeyi düşünün (3-5 yıl ömür).",
  },
  "system:network_afd_receive_window": {
    name: "Ağ alma arabelleği",
    description:
      "Winsock AFD varsayılan alma arabelleğini 128 KB yapar. Büyük arabellek, paketler uygulamanın okuyabildiğinden hızlı geldiğinde UDP paket kayıplarını önler.",
  },
  "system:network_afd_send_window": {
    name: "Ağ gönderme arabelleği",
    description:
      "Winsock AFD varsayılan gönderme arabelleğini 128 KB yapar. Büyük arabellek, uygulama ağın boşaltabildiğinden hızlı yazdığında UDP paket kayıplarını önler.",
  },
  "system:network_dscp_qos": {
    name: "Oyun trafiği öncelik etiketi",
    description:
      "CS2, MW3 ve Warzone'un UDP paketlerini DSCP Expedited Forwarding (46) ile etiketler. DSCP'ye saygılı yönlendiriciler oyun trafiğini toplu indirmelerin önüne alır.",
  },
  "privacy:advertising_id": {
    name: "Reklam kimliği",
    description:
      "Uygulamalar arası hedefli reklam için benzersiz kimlik. Kapatmak gizliliği artırır.",
  },
  "privacy:activity_history": {
    name: "Etkinlik geçmişi",
    description:
      "Zaman çizelgesi için uygulama kullanımını izler. Kapatmak gizliliği artırır ve eşitlemeyi azaltır.",
  },
  "privacy:consumer_features": {
    name: "Önerilen uygulamalar ve teklifler",
    description:
      "Başlat menüsündeki öneriler, ipuçları ve tanıtılan uygulamalar. Kapatmak karmaşayı azaltır.",
  },
  "privacy:edge_telemetry": {
    name: "Edge telemetrisi",
    description:
      "Edge tarayıcısının tanılama verisi toplaması. Kapatmak gizliliği artırır.",
  },
  "privacy:cortana": {
    name: "Cortana",
    description:
      "Microsoft'un sesli asistanı. Windows 11'de emekli edildi ama açıksa hâlâ veri toplar.",
  },
  "privacy:bing_search": {
    name: "Başlat menüsünde web sonuçları",
    description:
      "Başlat menüsündeki web arama sonuçları. Kapatmak aramaları yalnızca yerelde tutar.",
  },
  "privacy:input_personalization": {
    name: "Yazma kişiselleştirmesi",
    description:
      "Kişiselleştirme modellerini eğitmek için yazma ve el yazısı verisi toplar. Kapatmak hem metin hem mürekkep toplamayı engeller.",
  },
  "privacy:accepted_policy": {
    name: "Kişiselleştirme onay bayrağı",
    description:
      "Konuşma/yazma kişiselleştirme gizlilik ilkesinin kabulünü izler.",
  },
  "privacy:tile_notifications": {
    name: "Canlı kutucuk bildirimleri",
    description:
      "Başlat menüsündeki canlı kutucuklar. Yalnızca Windows 10'u etkiler (Windows 11'de kaldırıldı).",
  },
  "privacy:allow_telemetry": {
    name: "Tanılama verisi düzeyi",
    description:
      "Sistem geneli telemetri ilkesi. Enterprise=Kapalı; Home/Pro'da asgari Temel.",
  },
  "privacy:copilot": {
    name: "Windows Copilot",
    description:
      "Windows 11'deki yapay zekâ asistanı. Kapatmak Copilot'u tamamen kaldırır.",
  },
  "privacy:windows_ads": {
    name: "Windows reklamları ve ipuçları",
    description:
      "Dosya Gezgini, Başlat menüsü ve kilit ekranındaki reklamlar ile kendiliğinden kurulan uygulamalar.",
  },
  "privacy:web_search_policy": {
    name: "Başlat'ta web araması (ilke)",
    description:
      "Başlat menüsünde web aramasını ilke düzeyinde engeller. BingSearchEnabled'dan daha güçlüdür.",
  },
  "privacy:recall": {
    name: "Windows Recall ekran kayıtları",
    description:
      "Yapay zekâ araması için düzenli ekran görüntüleri alır. Kapatmak disk alanı ve CPU kazandırır.",
  },
  "privacy:camera_indicator": {
    name: "Kamera kullanım göstergesi",
    description:
      "Bir uygulama kamerayı açtığında veya kapattığında görev çubuğunun üstünde bildirim gösterir. Fiziksel kamera ışığı olmayan cihazlarda yararlıdır.",
  },
  "privacy:app_launch_tracking": {
    name: "Uygulama başlatma izleme",
    description:
      "Windows, Başlat önerilerini kişiselleştirmek için hangi uygulamaları açtığınızı izler. Kapatmak gizliliği artırır.",
  },
  "privacy:online_speech": {
    name: "Çevrimiçi konuşma tanıma",
    description:
      "Ses verisini işlenmek üzere Microsoft bulutuna gönderir. Kapatmak ses girişini yalnızca yerelde tutar.",
  },
  "privacy:feedback_reminders": {
    name: "Geri bildirim istekleri",
    description:
      "Windows geri bildirim hatırlatmalarını (SIUF) denetler. Kapatmak oyun sırasında bölünmeyi önler.",
  },
  "privacy:ceip": {
    name: "Deneyim geliştirme programı",
    description:
      "CEIP kapsamında kullanım ve güvenilirlik verilerini Microsoft'a gönderir. Kapatmak arka plan telemetrisini ve CPU yükünü azaltır.",
  },
  "privacy:app_telemetry": {
    name: "Uygulama uyumluluk telemetrisi",
    description:
      "Uygulama kullanımını izleyen Application Impact Telemetry motorunu denetler. Kapatmak arka plan veri toplamayı ve CPU yükünü azaltır.",
  },
  "perf:shutdown_service_timeout": {
    name: "Kapanışta hizmet bekleme",
    description:
      "Kapanış sırasında bir hizmetin durması için beklenen azami milisaniye. 5000'den 2000'e indirmek kapanışı 3 saniyeye kadar kısaltır.",
  },
  "perf:shutdown_app_timeout": {
    name: "Kapanışta uygulama bekleme",
    description:
      "Kapanışta yanıt vermeyen bir uygulamanın kapanması için beklenen azami milisaniye. Hem asılı kalma algısına hem zorla kapatma sayaçlarına uygulanır.",
  },
  "perf:shutdown_auto_end_tasks": {
    name: "Kapanışta zorla kapat",
    description:
      "Kapanış sinyaline yanıt vermeyen görevleri kendiliğinden sonlandırır. Takılan programların kapanışı engellemesini önler.",
  },
  "perf:gpu_tdr_delay": {
    name: "GPU takılma toleransı",
    description:
      "GPU sürücüsünün zaman aşımı algılama penceresini (TDR) Windows varsayılanı 2 saniyeden 10 saniyeye çıkarır. MW3'ün DX12 yükleri GPU'yu sıkça 2 saniyeden uzun oyalayıp sahte sürücü sıfırlamaları tetikler.",
  },
  "perf:accessibility_popups": {
    name: "Yapışkan tuş uyarıları",
    description:
      "Yapışkan Tuşlar (5×Shift), Filtre Tuşları ve Geçiş Tuşları pencereleri. Oyun sırasında rahatsız eder.",
  },
  "perf:mouse_acceleration": {
    name: "Fare ivmesi",
    description:
      "Windows işaretçi ivmesi. Kapatmak oyun için 1:1 fare girişi verir.",
  },
  "perf:fast_startup": {
    name: "Hızlı başlangıç",
    description:
      "Çekirdek durumunu kaydeden melez kapanış. Sürücü sorunlarına yol açabilir.",
  },
  "perf:svchost_split_threshold": {
    name: "Hizmet süreci gruplama",
    description:
      "Windows hizmetlerini daha az sürece toplar. Yaklaşık 100-300 MB RAM kazandırır.",
  },
  "perf:startup_delay": {
    name: "Başlangıç uygulaması gecikmesi",
    description:
      "Windows, masaüstü ilk açılışta akıcı kalsın diye başlangıç uygulamalarını ~10 sn geciktirir. Gecikmeyi kaldırmak bu uygulamaların daha erken açılıp bitmesini sağlar.",
  },
  "perf:numlock_default": {
    name: "Açılışta Num Lock",
    description:
      "Her Windows oturumunda Num Lock durumunu ayarlar. Sayısal tuş ataması kullanan oyunlar için yararlıdır.",
  },
  "perf:focus_assist": {
    name: "Oyunda bildirimler",
    description:
      "Tam ekran oyun sırasında bildirimleri bastırır. Bildirim kaynaklı takılmayı önler.",
  },
  "system:vbs_core_isolation": {
    name: "Çekirdek yalıtımı (VBS)",
    description:
      "Sanallaştırma tabanlı güvenlik (Bellek Bütünlüğü). Güvenlik için açık tutun. Kapatmak ~%5 FPS verir ama Windows Güvenliği uyarısı tetikler.",
  },
  "cleanup:dism_cleanup": {
    name: "Windows bileşen temizliği",
    description:
      "Windows bileşen deposunu temizler. 1-10 GB boşaltabilir. 5-15 dakika sürer. Tam alan kazanımı için yeniden başlatma gerekebilir.",
  },
  "cleanup:temp_files": {
    name: "Geçici dosyalar",
    description:
      "Windows ve kullanıcı klasörlerindeki geçici dosyaları temizler.",
  },
  "cleanup:event_logs": {
    name: "Olay günlükleri",
    description:
      "Tüm Windows olay günlüklerini (Uygulama, Sistem, Güvenlik vb.) temizler. Disk alanı boşaltır ve Olay Görüntüleyicisi'ni hızlandırır.",
  },
  "cleanup:wer_reports": {
    name: "Hata raporları",
    description:
      "Windows Hata Raporlama çökme dökümlerini ve rapor arşivlerini temizler. Sessizce birikir ve birkaç GB tutabilir.",
  },
  "cleanup:defender_cache": {
    name: "Defender önbelleği",
    description:
      "Windows Defender tarama geçmişini ve önbelleğini temizler. Silmesi güvenlidir — Defender bir sonraki taramada yeniden oluşturur.",
  },
  "cleanup:prefetch": {
    name: "Prefetch dosyaları",
    description:
      "Windows prefetch dosyalarını temizler. Windows bunları kendiliğinden yeniden oluşturur. Yazılım kaldırdıktan sonra yararlıdır.",
  },
  "cleanup:browser_cache": {
    name: "Tarayıcı önbellekleri",
    description:
      "Edge, Chrome, Brave ve Firefox önbelleklerini temizler. Tarayıcılar gezindikçe yeniden oluşturur. Ciddi disk alanı boşaltır.",
  },
  "cleanup:windows_update_cache": {
    name: "Güncelleme indirme önbelleği",
    description:
      "İndirilen Windows Update paketlerini temizler. Windows gerektiğinde yeniden indirir.",
  },
  "cleanup:delivery_optimization": {
    name: "Güncelleme paylaşım önbelleği",
    description:
      "P2P Windows Update dağıtım önbelleğini temizler. Güncellemeler kurulduktan sonra bu dosyalara gerek kalmaz.",
  },
  "cleanup:thumbnail_cache": {
    name: "Küçük resim önbelleği",
    description:
      "Gezgin'in küçük resim ve simge önbelleklerini temizler. Klasörlerde gezindikçe Windows yeniden oluşturur.",
  },
  "cleanup:memory_dumps": {
    name: "Çökme bellek dökümleri",
    description:
      "Çökme dökümü dosyalarını (Minidump, MEMORY.DMP, LiveKernelReports) siler. Çökmeler incelendikten sonra silmek güvenlidir.",
  },
  "cleanup:shadow_copy_reclaim": {
    name: "Veri disklerinde geri yükleme alanı",
    description:
      "Sistem dışı sürücülerde Birim Gölge Kopyası alanını kapasitenin %10'uyla sınırlar. Windows sığdırmak için en eski geri yükleme noktalarını siler ve alan boşalır.",
  },
  "cleanup:pip_cache": {
    name: "Python pip önbelleği",
    description:
      "pip paket indirme önbelleğini temizler. pip bir sonraki kurulumda PyPI'den yeniden indirir. Yalnızca Python kuruluysa görünür.",
  },
  "cleanup:npm_cache": {
    name: "npm önbelleği",
    description:
      "npm paket indirme önbelleğini temizler. npm bir sonraki kurulumda yeniden indirir. Yalnızca Node.js kuruluysa görünür.",
  },
  "cleanup:yarn_cache": {
    name: "Yarn önbelleği",
    description:
      "Yarn paket yöneticisi önbelleğini temizler. Yarn bir sonraki kurulumda yeniden indirir. Yalnızca Yarn kuruluysa görünür.",
  },
  "cleanup:pnpm_cache": {
    name: "pnpm deposu",
    description:
      "pnpm içerik-adresli deposunu temizler. pnpm bir sonraki kurulumda tüm paketleri yeniden indirir. Yalnızca pnpm kuruluysa görünür.",
  },
  "cleanup:nuget_cache": {
    name: "NuGet paketleri",
    description:
      "NuGet yerel paket önbelleğini temizler. Paketler bir sonraki derlemede yeniden iner. Yalnızca .NET/Visual Studio kuruluysa görünür.",
  },
  "cleanup:maven_cache": {
    name: "Maven deposu",
    description:
      "Maven yerel deposunu temizler. Bağımlılıklar bir sonraki Maven derlemesinde yeniden iner. Yalnızca Maven/Java kuruluysa görünür.",
  },
  "cleanup:gradle_cache": {
    name: "Gradle önbelleği",
    description:
      "Gradle derleme önbelleğini ve indirilen bağımlılıkları temizler. Gradle bir sonraki derlemede yeniden indirir. Yalnızca Gradle kuruluysa görünür.",
  },
  "cleanup:cargo_cache": {
    name: "Cargo kayıt önbelleği",
    description:
      "Cargo paket kayıt önbelleğini temizler. Rust crate'leri bir sonraki cargo derlemesinde yeniden iner. Yalnızca Rust kuruluysa görünür.",
  },
  "cleanup:docker_prune": {
    name: "Docker kullanılmayan veriler",
    description:
      "'docker system prune' çalıştırarak sahipsiz imajları, durmuş kapsayıcıları, kullanılmayan ağları ve derleme önbelleğini siler. Etkin kapsayıcılar, kullanılan etiketli imajlar ve adlandırılmış birimler korunur.",
  },
  "cleanup:docker_prune_all": {
    name: "Docker tüm kullanılmayan imajlar",
    description:
      "'docker system prune -a' ile ayrıca hiçbir kapsayıcının kullanmadığı TÜM imajları siler; en çok alanı bu boşaltır. Adlandırılmış birimler ve çalışan kapsayıcılar korunur.",
  },
  "cleanup:wsl_compact": {
    name: "WSL disk sıkıştırma",
    description:
      "WSL'i kapatır ve Docker Desktop veri diski dahil tüm WSL2 sanal disklerini (ext4.vhdx) sıkıştırarak boşalan alanı Windows'a geri verir. WSL diskleri zamanla büyür ve kendiliğinden küçülmez.",
  },
  "game_cleanup:nvidia_shader_cache": {
    name: "NVIDIA shader önbelleği",
    description:
      "NVIDIA DirectX (DXCache) ve OpenGL (GLCache) shader önbelleklerini, sürücü sürümü klasörleri dahil temizler. Sürücü ve oyunlar bir sonraki açılışta yeniden derler.",
  },
  "game_cleanup:amd_shader_cache": {
    name: "AMD shader önbelleği",
    description:
      "AMD DirectX (DxCache), Vulkan (VkCache) ve OpenGL (GLCache) shader önbelleklerini temizler. Sürücü bir sonraki açılışta yeniden derler.",
  },
  "game_cleanup:directx_shader_cache": {
    name: "DirectX shader önbelleği",
    description:
      "Tüm DirectX oyunlarının paylaştığı Windows DirectX shader önbelleğini (D3DSCache) temizler. Windows, oyunlar çalıştıkça yeniden oluşturur.",
  },
  "game_cleanup:intel_shader_cache": {
    name: "Intel shader önbelleği",
    description:
      "Intel GPU shader önbellek klasörlerini temizler. Sürücü bir sonraki açılışta yeniden derler.",
  },
  "game_cleanup:steam_webcache": {
    name: "Steam web önbelleği",
    description:
      "Steam tarayıcı ve HTML önbelleğini temizler. Steam bir sonraki açılışta yeniden oluşturur. Oyun dosyalarına dokunmaz.",
  },
  "game_cleanup:epic_cache": {
    name: "Epic başlatıcı önbelleği",
    description:
      "Epic Games Launcher web önbelleğini ve günlüklerini temizler. Başlatıcı bir sonraki açılışta yeniden oluşturur.",
  },
  "game_cleanup:discord_cache": {
    name: "Discord önbelleği",
    description:
      "Discord uygulama, kod ve GPU önbelleklerini temizler. Discord bir sonraki açılışta yeniden oluşturur.",
  },
  "game_cleanup:battlenet_cache": {
    name: "Battle.net önbelleği",
    description:
      "Battle.net başlatıcısının HTTP/varlık önbelleğini temizler. Başlatıcı çökmelerini, kayıp oyun simgelerini ve başarısız güncelleme indirmelerini düzeltir. Bir sonraki açılışta yeniden oluşur.",
  },
  "maintenance:sfc_scan": {
    name: "Sistem dosyası onarımı",
    description: "Windows sistem dosyalarını tarar ve onarır.",
  },
  "maintenance:dism_health": {
    name: "Windows imaj onarımı",
    description: "Windows imajının sağlığını denetler.",
  },
  "game:game_mode": {
    name: "Oyun Modu",
    description:
      "Windows oyun iyileştirmesi. GPU'ya öncelik verir, oyun sırasında güncellemeleri engeller.",
  },
  "game:game_bar": {
    name: "Xbox Game Bar",
    description:
      "Ekran görüntüsü, kayıt ve performans bileşenleri için Xbox katmanı.",
  },
  "game:background_recording": {
    name: "Arka plan kaydı",
    description:
      "Anında tekrar için oyunu arka planda kaydeder. GPU ve disk kullanır.",
  },
  "game:hags": {
    name: "GPU donanım zamanlaması",
    description:
      "GPU zamanlamasını GPU'ya devreder. DLSS 3 Kare Üretimi için gereklidir. En iyi gecikme için kare sınırıyla birlikte kullanın.",
  },
  "game:vrr": {
    name: "Pencereli VRR",
    description:
      "DX11 oyunları için sistem geneli VRR. FreeSync, G-Sync Compatible ve Adaptive-Sync ile çalışır.",
  },
  "audio:enhancements": {
    name: "Ses geliştirmeleri",
    description:
      "Windows ses DSP efektleri (ekolayzır, yankı, ses dengeleme). İşleme oyunla hoparlör arasına girer ve keskinleştirmesi gereken yön ipuçlarını bulanıklaştırır.",
  },
  "audio:endpoint_enhancements": {
    name: "Çıkış bazlı ses efektleri",
    description:
      "Herhangi bir etkin çıkışta o aygıta özgü Windows geliştirmelerinin hâlâ açık olup olmadığı. Genel anahtar bunları kapsamaz.",
  },
  "audio:device_format": {
    name: "Ses örnekleme hızı",
    description:
      "Her giriş ve çıkışın çalıştığı hız. Eşleşmeyen her şey Windows karıştırıcısında her tamponda yeniden örneklenir; bu boşuna CPU harcar.",
  },
  "audio:exclusive_mode": {
    name: "Özel ses modu",
    description:
      "Uygulamalara özel ses erişimi verir. Gecikme düşer ama diğer sesleri engeller.",
  },
  "audio:communications_ducking": {
    name: "Sesli sohbette kısma",
    description:
      "Sesli sohbet etkinken Windows'un oyun sesini kısıp kısmadığı. Varsayılan diğer tüm sesleri %80 kısar; bir takım arkadaşı konuştuğunda ayak sesleri beşte bire düşer.",
  },
  "launcher:steam:downloads_during_gameplay": {
    name: "Oyundayken Steam indirmeleri",
    description:
      "Oyundayken Steam'in güncelleme indirmesine izin verir. Kapatmak bant genişliği çekişmesini ve CPU sıçramalarını önler.",
  },
  "launcher:steam:overlay": {
    name: "Steam katmanı",
    description:
      "Oyun içi katman (Shift+Tab). Kapatmak GPU belleği boşaltır ve mikro takılmaları azaltır.",
  },
  "launcher:steam:cef_gpu": {
    name: "Steam tarayıcısında GPU",
    description:
      "Steam arayüzü GPU'lu Chromium kullanır. Kapatmak Steam açıkken boştaki GPU kullanımını azaltır.",
  },
  "launcher:steam:shader_precache": {
    name: "Steam shader ön yüklemesi",
    description:
      "Shader önbelleklerini önceden indirir. Açık olması ilk açılış takılmalarını azaltır.",
  },
  "launcher:steam:broadcast": {
    name: "Steam yayını",
    description:
      "Steam canlı yayın özelliği. Kapatmak arka plan kodlama yükünü kaldırır.",
  },
  "launcher:steam:download_throttle": {
    name: "Steam indirme hız sınırı",
    description:
      "Steam indirme hızını sınırlar (KB/sn). Sınırı tamamen kaldırmak için -1 yapın.",
  },
  "launcher:steam:streaming_throttle": {
    name: "Steam Remote Play sınırı",
    description:
      "Steam Remote Play akış bant genişliğini kısar. Kapatmak akış kalitesini en üste çıkarır.",
  },
  "launcher:bnet:hardware_accel": {
    name: "Battle.net donanım hızlandırma",
    description:
      "Battle.net arayüzü GPU ile çizilir. Kapatmak başlatıcı açıkken boştaki GPU kullanımını azaltır.",
  },
  "launcher:bnet:p2p": {
    name: "Battle.net P2P indirmeleri",
    description:
      "Eşten eşe güncelleme dağıtımı. Kapatmak yükleme bant genişliği kullanımını durdurur.",
  },
  "launcher:bnet:background_download": {
    name: "Battle.net arka plan indirmeleri",
    description:
      "Oyundayken güncelleme indirir. Kapatmak bant genişliği çekişmesini önler.",
  },
  "launcher:bnet:download_limit": {
    name: "Battle.net indirme sınırı",
    description:
      "Battle.net indirme hızını sınırlar. Sınırı kaldırmak için en yükseğe ayarlayın.",
  },
  "launcher:bnet:background_download_limit": {
    name: "Battle.net arka plan sınırı",
    description:
      "Battle.net arka plan indirme hızını sınırlar. Arkada daha hızlı güncelleme için sınırı kaldırın.",
  },
  "game_config:cs2:sdr": {
    name: "CS2 Steam Datagram Relay",
    description:
      "CS2 autoexec.cfg'ye 'net_client_steamdatagram_enable_override 1' yazar. Trafiği açık internet yerine Valve'ın özel SDR omurgasından geçirir.",
  },
  "game_config:cs2:maxping": {
    name: "CS2 azami eşleştirme pingi",
    description:
      "CS2 autoexec.cfg'ye 'mm_dedicated_search_maxping 50' yazar. Eşleştirmenin sizi 50 ms üzeri pingli sunuculara koymasını önler.",
  },
  "game_config:cs2:qos_timeout": {
    name: "CS2 QoS arama süresi",
    description:
      "CS2 autoexec.cfg'ye 'mm_session_search_qos_timeout 20' yazar. Sunucu seçilmeden önce QoS verisi bekleme süresini kısaltır.",
  },
  "game_config:cs2:fps_max": {
    name: "CS2 FPS sınırı",
    description:
      "CS2 autoexec.cfg'ye 'fps_max 0' ekleyerek motorun FPS sınırını kaldırır. En düşük giriş gecikmesi için GPU'nun mümkün olan her kareyi çizmesine izin verir.",
  },
  "game_config:cs2:disable_ragdolls": {
    name: "CS2 ragdoll kapatma",
    description:
      "'cl_disable_ragdolls 1' yazar — cesetlerdeki istemci tarafı ragdoll fiziğini kapatır. Çoklu ölümlü çatışmalarda CPU kazandırır ve bilinen bir takılma kaynağını kaldırır.",
  },
  "game_config:cs2:tracers_firstperson": {
    name: "CS2 kendi izli mermilerini gizle",
    description:
      "'r_drawtracers_firstperson 0' yazar — yalnızca kendi silahınızın izli mermilerini gizler (üçüncü şahıs izleri çizilmeye devam eder, düşman ateşi görünür kalır). Sprey sırasında daha temiz nişan görüntüsü.",
  },
  "game_config:cs2:low_latency_sleep": {
    name: "CS2 düşük gecikme uykusu",
    description:
      "'engine_low_latency_sleep_after_client_tick true' yazar — motorun düşük gecikme uykusunu istemci tick'inden öncesi yerine sonrasına alır ve çizim gecikmesini sıkılaştırır.",
  },
  "game_config:cs2:autohelp": {
    name: "CS2 otomatik yardım kapatma",
    description:
      "'cl_autohelp 0' yazar — oyun içi yardım/ipucu pencerelerini kapatır. Arayüz çizim maliyetini kaldırır ve görsel kalabalığı azaltır.",
  },
  "game_config:cs2:game_instructor": {
    name: "CS2 eğitmen katmanı kapatma",
    description:
      "'gameinstructor_enable 0' yazar — öğretici katman sistemini kapatır. Az miktarda CPU kazandırır ve HUD'dan araya giren mesajları kaldırır.",
  },
  "game_config:cs2:violence_hblood": {
    name: "CS2 kan izleri",
    description:
      "CS2 autoexec.cfg'ye 'violence_hblood 0' yazar; yüzeylerdeki ve karakterlerdeki kan izlerini kapatır. Kan, başka türlü göremeyeceğiniz bir isabeti doğrular ve duvarı işaretler — bilgidir.",
  },
  "game_config:cs2:violence_agibs": {
    name: "CS2 vücut parçaları",
    description:
      "CS2 autoexec.cfg'ye 'violence_agibs 0' yazar; ölümde vücut parçalanmasını kapatır. Raunt sonu parça fiziği hesaplarını kaldırır.",
  },
  "game_config:cs2:draw_particles": {
    name: "CS2 kozmetik parçacıklar",
    description:
      "CS2 autoexec.cfg'ye 'r_drawparticles 0' yazar; parçacık çizimini kapatır. İsabet kıvılcımları ateşin nereden geldiğini söyler ve alev kaynakları molotofun alanını gösterir — bunlar bilgidir.",
  },
  "game_config:mw3:preferred_display_mode": {
    name: "MW3 tercih edilen ekran modu",
    description:
      "MW3'ün tam ekrana dönerken kullandığı, etkin Ekran Modu'ndan ayrı saklanan mod. İkisi uyuşmazsa oyun tercih edilene geri kayar; bu yüzden Ekran Modu ile eşleşmelidir.",
  },
  "game_config:mw3:hw_change_detection": {
    name: "MW3 donanım değişikliği algısı",
    description:
      "Donanım veya GPU sürücüsü değişince MW3'ün otomatik ayar algısını yeniden çalıştırıp tüm grafik seçeneklerini kendi tahminleriyle ezmesi. Kapatmak, uygulanan ayarları yerinde tutan şeydir.",
  },
  "game_config:mw3:vrs": {
    name: "MW3 değişken oranlı gölgeleme",
    description:
      "Sürücünün daha az fark edilir saydığı ekran bölgelerini düşük oranda gölgeler. Bildirilen kazanım GPU'ya göre ~%10'dan önemsize kadar iner; bazı sistemlerde kararsızlık görülür.",
  },
  "game_config:mw3:texture_streaming": {
    name: "MW3 doku akışı sınırı",
    description:
      "MW3'ün maç sırasında HTTP üzerinden doku indirmeye harcadığı bandı sınırlar. Bu indirme hattı maçın kendi trafiğiyle paylaşır ve motor oluşan gecikmeyi ping olarak raporlar.",
  },
  "game_config:mw3:nat_firewall": {
    name: "MW3 açık NAT güvenlik duvarı kuralları",
    description:
      "MW3/Warzone'un gerektirdiği tüm portları açan Windows Güvenlik Duvarı kuralları oluşturur. Daha hızlı eşleştirme için Açık NAT sağlar.",
  },
  "game_config:mw3:world_streaming_quality": {
    name: "MW3 isteğe bağlı doku akışı",
    description:
      "MW3'ün maç sırasında isteğe bağlı ne kadar indirdiği. Season 5 Reloaded eski Kapalı seçeneğini kaldırdı; bu derlemenin indirebileceği en az düzey Düşük'tür.",
  },
  "game_config:mw3:local_texture_quality": {
    name: "MW3 yerel doku akış kalitesi",
    description:
      "Sanal doku bellek yuvası sayısı. Yerel akış önbelleğine kaç dokunun sığdığını belirler. Düşük değer daha az VRAM baskısı demektir.",
  },
  "game_config:mw3:nvidia_reflex": {
    name: "MW3 NVIDIA Reflex",
    description:
      "NVIDIA Reflex Düşük Gecikme. 'Enabled + boost' GPU'yu yükten bağımsız azami saate zorlar ve çizim kuyruğu gecikmesini azaltır. RTX kartlarda bedava giriş gecikmesi kazancı.",
  },
  "game_config:mw3:dlss_frame_generation": {
    name: "MW3 DLSS kare üretimi",
    description:
      "DLSS 3+ Kare Üretimi yapay zekâyla ara kareler üretir. FPS sayacını yükseltir ama giriş gecikmesi ekler — rekabetçi çok oyunculuda istenmez. MP için KAPALI tutun.",
  },
  "game_config:mw3:dlss_perf_mode": {
    name: "MW3 DLSS performans modu",
    description:
      "DLSS iç çizim ölçeği. Quality doğalın %67'sinde, Balanced %58'inde, Performance %50'sinde çizer. Yükseltici kare almak için var; en üst kademesi kapatıldığı şeyin çoğunu geri verir.",
  },
  "game_config:mw3:depth_of_field": {
    name: "MW3 alan derinliği",
    description:
      "Odak dışı bölgelerde kamera lens bulanıklığı, özellikle nişandayken. Uzak düşmanları bulanıklaştırır — görüş için istenmez. Rekabetçi oyunda daima KAPALI.",
  },
  "game_config:mw3:shadow_quality": {
    name: "MW3 gölge kalitesi",
    description:
      "Dünya gölgesi ayrıntı düzeyi. Düşük, gölgeleri görünür tutar — düşman siluetini okumaya devam edersiniz — ve GPU maliyeti düşer.",
  },
  "game_config:mw3:screen_space_shadows": {
    name: "MW3 ekran alanı gölgeleri",
    description:
      "Karakter ve silahlarda kendi kendine gölgeleme. Kanalın taşıdığı bilgi, bir bedenin gölgeli olduğu ve ortamdan ayrıştığıdır; gölgenin ne kadar keskin çözüldüğü bilgi değildir.",
  },
  "game_config:mw3:volumetric_quality": {
    name: "MW3 hacimsel kalite",
    description:
      "Tanrı ışınları, hacimsel sis ve atmosfer saçılımı kalitesi. Rekabetçi getirisi olmayan çok pahalı bir GPU efekti. Düşük önerilir.",
  },
  "game_config:mw3:particle_quality": {
    name: "MW3 parçacık çözünürlüğü",
    description:
      "Duman, ateş, patlama ve mermi izi parçacık çözünürlüğü/yoğunluğu. Düşük, maliyeti azaltırken efektleri okunur tutar.",
  },
  "game_config:mw3:ssao": {
    name: "MW3 ortam kapatması (SSAO)",
    description:
      "Ekran alanı ortam kapatması yumuşak temas gölgeleri ekler. Kapalı önerilir — köşeleri (düşmanın saklandığı yerleri) karartır, rekabetçi getirisi yoktur, GPU harcar.",
  },
  "game_config:mw3:ssr": {
    name: "MW3 ekran alanı yansımaları",
    description:
      "Metalik ve ıslak yüzeylerde gerçek zamanlı yansımalar. Kalite menüsünün en ağır iki seçeneğinden biri; yansıma çatışmada görünür bilgi değildir.",
  },
  "game_config:mw3:shader_quality": {
    name: "MW3 shader kalitesi",
    description:
      "Malzeme shader karmaşıklığı. Düşük, geometriye ve görünürlüğe dokunmadan yüzey gölgelemesini sadeleştirir. Sürücü güncellemesi sonrası shader derleme süresini kısaltır.",
  },
  "game_config:mw3:dxr_mode": {
    name: "MW3 ışın izleme (DXR)",
    description:
      "Gölge ve yansımalar için DirectX ışın izleme. Devasa GPU maliyeti (%20-40 FPS kaybı), sıfır rekabetçi getiri. Çok oyunculuda azami FPS için kapalı olmalı.",
  },
  "game_config:mw3:audio_mix": {
    name: "MW3 ses karışımı",
    description:
      "Ses son işleme ön ayarı. Treble Boost (5) ve Headphones (1) tiz sesleri (ayak sesleri, silah tıkırtıları) bas müzik ve patlamaların önüne çıkarır.",
  },
  "game_config:mw3:detail_quality": {
    name: "MW3 ayrıntı kalitesi",
    description:
      "Geometri ayrıntısı / model LOD'u. Nesnelerin, bitki örtüsünün, kayaların ve çıkartmaların poligon yoğunluğunu belirler. Düşük, görünürlüğü etkilemeden küçük dağınıklığı sadeleştirir.",
  },
  "game_config:mw3:persistent_effects": {
    name: "MW3 kalıcı efektler",
    description:
      "Yüzeylerde kalan mermi izleri ve patlama lekeleri. Yetkin rekabetçi rehberler kapatılmasını önerir.",
  },
  "game_config:mw3:static_reflection_quality": {
    name: "MW3 statik yansıma kalitesi",
    description:
      "Küp harita yansıma sondalarının yeniden aydınlatma sıklığı/kalitesi. 1=Düşük, 4=Yüksek. 1'e inmek yalnızca %0-1 FPS ölçüyor; oyunun varsayılanı bu yüzden korunur.",
  },
  "game_config:mw3:deferred_physics": {
    name: "MW3 ertelenmiş fizik kalitesi",
    description:
      "GPU hızlandırmalı çevre fiziği benzetimi (enkaz, duman şekillenmesi). Maliyet, oyun menüsünün söylediğinin aksine GPU'ya değil CPU'ya biner.",
  },
  "game_config:mw3:render_resolution": {
    name: "MW3 çizim çözünürlüğü çarpanı",
    description:
      "Yükselticiden ÖNCE uygulanan dış çizim ölçeği (ekranın yüzdesi). Kalite-performans dengesi: 50, doğala göre +%89 FPS ama çok bulanık; 75 dengelidir.",
  },
  "game_config:mw3:weather_grid": {
    name: "MW3 hava durumu ızgaraları",
    description:
      "Hacimsel hava efektleri (yağmur, kar, sis yoğunluk ızgaraları). Seçenek bazlı ölçümler neredeyse hiç FPS farkı göstermiyor; bu yüzden kare hızı için değil hedef görünürlüğü için kapalı tutulur.",
  },
  "game_config:mw3:tessellation": {
    name: "MW3 mozaikleme",
    description:
      "Arazi ve model yüzey ayrıntısı için GPU mozaiklemesi. Rekabetçi standart Kapalı'dır — yalnızca yakın yüzeylerde görünür, GPU'da pahalıdır.",
  },
  "game_config:mw3:menu_render_resolution": {
    name: "MW3 menü çizim çözünürlüğü",
    description:
      "MW3'ün menü ve lobi gibi oyun dışı sahnelerde güç tasarrufu için çizim çözünürlüğünü ne kadar düşürdüğü. Değer, düşüşün büyüklüğünü adlandırır.",
  },
  "game_config:mw3:display_mode": {
    name: "MW3 ekran modu",
    description:
      "Pencere modu. Kenarlıksız, MW3'ü flip-model sunum yolunda tutar; Windows 11'de bu, tam ekrana göre ölçülebilir gecikme maliyeti olmadan gelir.",
  },
  "game_config:mw3:anisotropic": {
    name: "MW3 anizotropik doku filtresi",
    description:
      "Eğik açıyla görülen dokular için anizotropik filtreleme düzeyi. Normal (4x), asgari GPU maliyetiyle keskin zemin ve duvar dokusu verir.",
  },
  "game_config:mw3:bullet_impacts": {
    name: "MW3 mermi izi işaretleri",
    description:
      "Yüzeylerdeki mermi izleri. Açık tutmak düşmanın nereden ateş ettiğini gösterir — atış yönü hakkında taktik bilgidir.",
  },
  "game_config:mw3:pause_rendering": {
    name: "MW3 odak dışı çizimi durdurma",
    description:
      "Oyun penceresi yalnızca küçültüldüğünde değil, odağı her kaybettiğinde GPU çizimini durdurur. Çok monitörlü kurulumda görünür kalan MW3 penceresi bayat bir karede donar.",
  },
  "game_config:mw3:fps_cap_out_of_focus": {
    name: "MW3 odak dışı kare sınırı",
    description:
      "Pencere odakta değilken azami kare hızı. Oyun penceresini dondurmadan GPU'yu alt-tab yaptığınız şeye geri verir.",
  },
  "game_config:mw3:dlss_sharpness": {
    name: "MW3 DLSS keskinliği",
    description:
      "DLSS çıktısının üstüne uygulanan keskinleştirme. 0.25, hale izi üretmeden uzak düşman siluet netliğini artıran hafif bir keskinlik ekler.",
  },
  "game_config:mw3:path_tracing": {
    name: "MW3 yol izleme",
    description:
      "Tam donanımsal yol izleme — deneysel anahtar; yalnızca Silah Ustası, Atış Poligonu ve lobide etkindir, maçlarda değil. Maç dışı alanlarda ciddi GPU harcar.",
  },
  "game_config:mw3:dlss_ray_reconstruction": {
    name: "MW3 DLSS ışın yeniden kurma",
    description:
      "Işın izlemeli kareler için DLSS 3.5 yapay zekâ gürültü giderici — deneysel anahtar; Path Tracing ile birlikte yalnızca maç dışı alanlarda etkindir.",
  },
  "game_config:mw3:texture_resolution": {
    name: "MW3 doku çözünürlüğü",
    description:
      "Dünya yüzeyleri ve nesneler için doku ayrıntı düzeyi. VRAM'e bağlıdır; High'dan Normal'e inmek 1-2 GB VRAM kazandırır ve 8 GB kartlarda doygunluk takılmalarını bitirir.",
  },
  "game_config:mw3:water_quality": {
    name: "MW3 su kalitesi",
    description:
      "Su yüzeylerinin benzetim ayrıntısı (yansıma, dalga, ışık kırılması). Seçenek bazlı ölçüm düşürmenin performansa etkisini ölçemedi; oyun varsayılanı bu yüzden korunur.",
  },
  "game_config:mw3:weapon_motion_blur": {
    name: "MW3 silah hareket bulanıklığı",
    description:
      "Hızlı hareket ve kamera dönüşünde tutulan silah modeline uygulanan bulanıklık. Kapalı, nişangâhı her an keskin tutar — hızlı hedef alma için kritiktir.",
  },
  "game_config:mw3:dlss_rr_perf_mode": {
    name: "MW3 DLSS RR modu",
    description:
      "DLSS Işın Yeniden Kurma gürültü gidericisinin iç çizim ölçeği. En yüksek kalite en iyi sonucu verir; yalnızca DLSS RR açıkken anlamlıdır.",
  },
  "game_config:mw3:water_caustics": {
    name: "MW3 su ışık desenleri",
    description:
      "Su kenarındaki yüzeylere yansıyan ışık desenleri. Rekabetçi getirisi olmayan tamamen kozmetik bir GPU efekti — Kapalı önerilir.",
  },
  "game_config:mw3:reflection_probe_half_res": {
    name: "MW3 yarım çözünürlük yansıma sondaları",
    description:
      "Yansıma sonda küp haritalarını yarım çözünürlükte çizer. Çok oyunculuda gözle görülür fark olmadan yansıma VRAM'ini azaltır.",
  },
  "game_config:mw3:fsr_frame_interpolation": {
    name: "MW3 FSR 3 kare arası üretim",
    description:
      "AMD FSR 3 kare ara değerlemesi (FSR-FI). DLSS Kare Üretimi gibi ara kare ve giriş gecikmesi ekler — rekabetçi çok oyunculuda KAPALI olmalı.",
  },
  "game_config:mw3:dlss_mode": {
    name: "MW3 DLSS modu",
    description:
      "DLSS etkin yükselticiyken alt modu. DLSS, yükseltme + kenar yumuşatmayla en iyi FPS kazancını verir. DLAA yalnızca tam çözünürlük kenar yumuşatması sağlar (FPS kazancı yok).",
  },
  "game_config:mw3:sun_shadow_cascade": {
    name: "MW3 güneş gölgesi katmanları",
    description:
      "Güneş gölgelerinin ne kadar uzağa kadar çizildiği. Katmanlar mesafe bantlarıdır; bire inmek yakın gölgeleri korur ama uzaktakileri — köşede duran birinin gölgesi dahil — çizmeyi bırakır.",
  },
  "game_config:mw3:water_wave_wetness": {
    name: "MW3 su kenarı ıslaklığı",
    description:
      "Su kenarındaki sabit geometrinin kalıcı ıslaklık görünümü. Kapalı, rekabetçi etkisi olmadan ıslak yüzey shader geçişini kaldırır.",
  },
  "game_config:mw3:velocity_blur": {
    name: "MW3 hız bulanıklığı",
    description:
      "Sahnedeki hareketli nesnelere hız tabanlı bulanıklık uygular. Kapatmak hızlı hedeflerdeki bulanıklığı kaldırır ve çatışma netliğini artırır.",
  },
  "game_config:mw3:vsync": {
    name: "MW3 V-Sync (oyun içi)",
    description:
      "Oyun motorunun kendi dikey eşitlemesi — sürücününkinden ayrı bir anahtar. MW3'ün eşitleme döngüsü VRR'den habersizdir: kare kuyruklar ve bunun bedelini gecikmeyle ödetir.",
  },
  "game_config:mw3:vsync_menu": {
    name: "MW3 V-Sync (menü)",
    description:
      "Menü ve lobi ekranlarında uygulanan dikey eşitleme. %100, menü kare hızını monitör yenileme hızıyla sınırlar ve menüde boşuna GPU yükünü önler.",
  },
  "game_config:mw3:cloud_savegame": {
    name: "MW3 bulut yapılandırma kaydı",
    description:
      "Oyun açılışında oyuncu yapılandırma dosyalarını Activision bulutuyla eşitler. Açıkken oyun buluttaki ayarları indirip yerel değişiklikleri ezer — iyileştirilmiş ayarlar kaybolur.",
  },
  "game_config:mw3:cloud_storage": {
    name: "MW3 bulut yapılandırma deposu",
    description:
      "Yapılandırma verisini Activision bulut deposuna yükler ve oradan indirir. Kapatmak, buluttaki kopyanın yerel iyileştirmeleri ezmesini önler.",
  },
  "game_cleanup:mw3:shader_cache_cleanup": {
    name: "MW3 shader önbelleği",
    description:
      "Oyun klasöründeki MW3 PSO shader, teleskop ve xpak önbelleklerini siler. Sürücü güncellemesi sonrası bayat shader'ların yol açtığı açılış çökmelerini ve siyah ekranları düzeltir.",
  },
  "game_cleanup:mw3:crash_cleanup": {
    name: "MW3 çökme dökümleri",
    description:
      "Belgeler klasöründe biriken MW3 çökme dökümlerini siler. Çökmeler çözüldükten sonra işe yaramaz ve yüzlerce MB tutabilir.",
  },
  "game_config:hots:vsync": {
    name: "HotS dikey eşitleme",
    description:
      "Oyun içi kare eşitleme. Değişken yenilemeli panelde sürücü kare hızını zaten G-Sync penceresinde tutar; oyunun içindeki ikinci V-Sync yalnızca bekleme ekler.",
  },
  "game_config:hots:movies": {
    name: "HotS sinematikler",
    description:
      "Menülerde ve maç başında oynatılan önceden kaydedilmiş videolar. Maç sırasında çizilen bir şey değil, maç öncesi çözülen video dosyalarıdır.",
  },
  "game_config:hots:portraits_3d": {
    name: "HotS 3B portreler",
    description:
      "Kahraman portrelerini düz resim yerine canlı 3B model olarak çizer. Modeller, çatışma sırasında bakmadığınız bir köşede her kare yeniden çizilir.",
  },
  "game_config:hots:shadow_quality": {
    name: "HotS gölge kalitesi",
    description:
      "Gölgelerin çözünürlüğü ve filtrelenmesi. Gölgeler bu motorda kare başına en pahalı efekt ve takım savaşını okumakta en az işe yarayanıdır.",
  },
  "game_config:hots:post_processing": {
    name: "HotS son işleme",
    description:
      "Sahne çizildikten sonra uygulanan tam ekran efektler (bloom, alan derinliği gibi). Her biri tüm pikseller üzerinde ek bir geçiştir ve birkaçı tahtayı fiilen örter.",
  },
  "game_config:hots:ssao": {
    name: "HotS ortam kapatması",
    description:
      "Nesnelerin zeminle buluştuğu yerdeki yumuşak temas gölgesi (SSAO). Tüm çıktısı hafif gölgeleme olan piksel başına bir geçiştir.",
  },
  "game_config:hots:reflections": {
    name: "HotS yansımalar",
    description:
      "Su gibi yansıtıcı yüzeyler; yansıma görüntüsü için sahnenin bir kısmını ikinci kez çizer.",
  },
  "game_config:hots:physics_quality": {
    name: "HotS fizik kalitesi",
    description:
      "Kahraman modellerinde kumaş, ragdoll ve enkaz benzetimi. Hiçbiri maçta olan biteni etkilemez — çatışma sırasında CPU harcayan süslemedir.",
  },
  "game_config:hots:effects_detail": {
    name: "HotS efekt ayrıntısı",
    description:
      "Yetenek ve büyü efektlerinin ayrıntısı. Bu oyunda bir yetenek kendini efektiyle duyurur; bu, oyuncunun ne okuyabildiğine karar veren tek grafik ayarıdır.",
  },
  "game_config:mw4:recommended_set": {
    name: "MW4 özel ayarları koru",
    description:
      "Yapılandırmayı kullanıcı ayarlı olarak işaretler. Dosyanın kendi notuna göre 0 değeri oyunun her ayarı önerilen varsayılanlara sıfırlamasına yol açar — bütün işi çöpe atar.",
  },
  "game_config:mw4:cloud_storage": {
    name: "MW4 bulut yapılandırma deposu",
    description:
      "Yerel yapılandırmayı Activision'ın bulut kopyasıyla eşitler. Açıkken başka makineden veya önceki oturumdan yazılmış bulut kopyası buradaki ayarları habersizce ezebilir.",
  },
  "game_config:mw4:hw_change_detection": {
    name: "MW4 donanım değişikliği algısı",
    description:
      "Donanım veya sürücü değişikliği görünce oyunun otomatik kalite algısını yeniden çalıştırır. Bir sürücü güncellemesi bile tetikler ve yeniden algı ayarlanmış değerleri ezer.",
  },
  "game_config:mw4:nvidia_reflex": {
    name: "MW4 NVIDIA Reflex",
    description:
      "NVIDIA'nın düşük gecikme modu; karelerin GPU önünde birikmesine izin vermek yerine çizim kuyruğunu kısa tutar. 'Enabled + boost' ayrıca GPU saatini yüksek tutar.",
  },
  "game_config:mw4:fps_cap_out_of_focus": {
    name: "MW4 odak dışı kare sınırı",
    description:
      "Pencere odakta değilkenki kare sınırı. Tarayıcıya alt-tab yapılmış bir oyunun tam hızda çizmesi için sebep yoktur; çizdiği her kare ön plandaki işin ısı ve gücüne mal olur.",
  },
  "game_config:mw4:render_resolution": {
    name: "MW4 çizim çözünürlüğü çarpanı",
    description:
      "3B sahnenin pencere çözünürlüğünün yüzde kaçında çizildiği; her yükselticiden önce uygulanır. 100'ün altında oyun daha az piksel çizip gerer.",
  },
  "game_config:mw4:dlss_perf_mode": {
    name: "MW4 DLSS kalite modu",
    description:
      "DLSS'in çıkışa yükseltmeden önce çizdiği iç çözünürlük. Yükseltici kare almak için var; en pahalı kademesi, açılma nedeninin çoğunu geri verir.",
  },
  "game_config:mw4:dlss_model": {
    name: "MW4 DLSS modeli",
    description:
      "Yükseltmeyi hangi DLSS sinir modelinin yaptığı. Transformer model ince ayrıntıyı harekette eski evrişimsel modelden daha iyi tutar ve kare hızının %3'üne kadarına mal olur.",
  },
  "game_config:mw4:texture_quality": {
    name: "MW4 doku kalitesi",
    description:
      "Oyunun yüklediği dokuların çözünürlüğü; ters ölçekte 0 en yüksek, 3 en düşüktür. Oyuncu modellerindeki doku ayrıntısı, rakibi sahneden ayırt ettiren şeydir.",
  },
  "game_config:mw4:anisotropic": {
    name: "MW4 doku filtrelemesi",
    description:
      "Açıyla görülen yüzeylere uygulanan anizotropik filtreleme. Uzaktaki zemin ve duvar dokusunu keskinleştirir — bu manzaradır; rakip, modeliyle çözülür.",
  },
  "game_config:mw4:volumetric_quality": {
    name: "MW4 hacimsel kalite",
    description:
      "Hacimsel sis, tanrı ışınları ve ışık huzmelerinin kalitesi. Düşürmek hem kare kazandırır hem oyuncuyla içinde hareket eden her şey arasındaki havayı temizler.",
  },
  "game_config:mw4:reflection_probe_half_res": {
    name: "MW4 yarım çözünürlük yansıma sondaları",
    description:
      "Cam, metal ve sudaki küp harita yansımalarını yarım çözünürlükte çizer. Yansımalar oyuncunun eyleme döktüğü bir şey taşımaz; bu onları dosyanın en ucuz harcamalarından yapar.",
  },
  "game_config:mw4:motion_blur": {
    name: "MW4 hareket bulanıklığı",
    description:
      "Sahneyi hareket yönünde bulandırır. Kare harcayıp hareketli hedefi çözmeyi zorlaştıran efektin dosyadaki en açık örneğidir.",
  },
  "game_config:mw4:weapon_motion_blur": {
    name: "MW4 silah hareket bulanıklığı",
    description:
      "Hareket hâlindeki silah modeline bulanıklık uygular. Ekranın nişan aldığınız kısmını bulandırır ve karşılığında hiçbir şey vermez.",
  },
  "game_config:mw4:velocity_blur": {
    name: "MW4 hız bulanıklığı",
    description:
      "Oyuncu hızıyla büyüyen dairesel bir bulanıklık ekler. Koşu, oyuncunun ekran kenarlarını okumaya en çok ihtiyaç duyduğu andır; bunu yumuşatan da tam bu efekttir.",
  },
  "game_config:mw4:depth_of_field": {
    name: "MW4 alan derinliği",
    description:
      "Kameranın odaklanmadığı her şeyi bulandırır. Birinci şahıs nişancıda odak dışı olan genellikle uzaktır — hedeflerin olduğu yer.",
  },
  "game_config:mw4:dof_weapon": {
    name: "MW4 silah alan derinliği",
    description:
      "Görüş odağı kayınca silah modelini bulandırır. Dünya alan derinliğinden ayrıdır; açık bırakılırsa dünya efekti kapandıktan sonra da bulandırmaya devam eder.",
  },
  "game_config:mw4:dof_world": {
    name: "MW4 dünya alan derinliği",
    description:
      "Odak düzlemi dışındaki dünyayı bulandırır. Ana alan derinliği denetimi Kapalı yerine Script'e alındığında ayakta kalan anahtar budur.",
  },
  "game_config:mw4:dof_quality": {
    name: "MW4 alan derinliği kalitesi",
    description:
      "Alan derinliği filtresinin örnek sayısı. Yalnız alan derinliği açıkken maliyeti vardır; bu da High'ı dosyada geride bırakılması en pahalı ayar yapar.",
  },
  "game_config:mw4:weather_grid": {
    name: "MW4 hava durumu ızgaraları",
    description:
      "Hacimsel yağmur, kar ve sis yoğunluk ızgaraları. Hava hacimleri oyuncuyla diğer her şeyin arasında durur; kapatmak hem kare hem görüş hattı geri verir.",
  },
  "game_config:mw4:subdivision": {
    name: "MW4 geometri alt bölme",
    description:
      "Model siluetlerini geometri ekleyerek yumuşatan Catmull-Clark alt bölme düzeyi. Oyuncunun asla incelemediği kenarları yuvarlar ve bunun için geometri gücü harcar.",
  },
  "game_config:mw4:shadow_filtering": {
    name: "MW4 gölge filtrelemesi",
    description:
      "Gölge kenarlarının ne kadar yumuşak harmanlandığı. Gölgenin kendisi bilgidir — köşeden düşen gölge birini haber verir — ama kenarının yumuşaklığı bilgi değildir.",
  },
  "game_config:mw4:shader_quality": {
    name: "MW4 shader kalitesi",
    description:
      "Oyunun derlediği malzeme shader'larının karmaşıklığı. Düşürmek yüzeylerin ışığa tepkisini sadeleştirir; hareket eden hiçbir şeyi gizlemeden görünümü değiştirir.",
  },
  "game_config:mw4:cinematic_emissive": {
    name: "MW4 oyun içi sinematikler",
    description:
      "Oynanışı bölen kurgulu sinematikleri oynatır. Tanımı gereği gösteridir ve içindeki hiçbir şey eyleme dökülmez.",
  },
  "game_config:mw4:show_brass": {
    name: "MW4 boş kovanlar",
    description:
      "Ateş ederken silahın attığı boş kovanları çizer. Tam oyuncunun hedef takip ettiği anda belirirler ve kimsenin yeri hakkında bir şey taşımazlar.",
  },
  "game_config:mw4:blood_limit": {
    name: "MW4 kan efekti sınırı",
    description:
      "Kan efektlerinin ne hızda üst üste binebileceğini oyunun kendi aralığıyla sınırlar. Kan bir isabeti doğrular, bu bilgidir — ama biriken kan doğruladığı hedefi örter.",
  },
  "game_config:mw4:corpse_limit": {
    name: "MW4 ceset sınırı",
    description:
      "Aynı anda dünyada kaç bedenin kaldığı. Her biri hâlâ çizilen tam bir modeldir ve çekişmeli hedefte tam görüş hatlarının üstünde birikirler.",
  },
  "game_config:mw4:corpses_culling": {
    name: "MW4 ceset temizleme eşiği",
    description:
      "Sınıra ulaşılmadan bedenlerin ne kadar erken kaldırıldığı. Düşük değer onları daha erken temizler — üstteki sınırın sürekli uygulanmış hâli.",
  },
  "game_config:mw4:skip_season_intro": {
    name: "MW4 sezon tanıtım videosu",
    description:
      "Açılışta sezon fragmanını oynatır. Her oturumda yükleme süresine mal olur ve içindeki hiçbir şey maçı etkilemez.",
  },
  "game_config:mw4:marks_player_only": {
    name: "MW4 karakterlerde mermi izleri",
    description:
      "Karakterlerdeki mermi izlerini yalnızca kendi atışlarınızla sınırlar. Çıkartmaları azaltır ama başkalarının bıraktığı izleri de kaldırır — kimin vurulduğuna dair bir sinyaldir.",
  },
  "game_config:mw4:ssr": {
    name: "MW4 ekran alanı yansımaları",
    description:
      "Islak zemin, cam ve metalde ekrandakinden hesaplanan yansımalar. Pahalıdır ve oyuncunun eyleme döktüğü hiçbir şey taşımaz.",
  },
  "game_config:mw4:dxr_mode": {
    name: "MW4 ışın izleme",
    description:
      "DirectX ışın izlemenin ana anahtarı. Işın izlemeli aydınlatma oyunun sunduğu en pahalı seçenektir ve oyuncunun neyi gelirken görebildiğini değiştirmez.",
  },
  "game_config:mw4:dxr_quality": {
    name: "MW4 ışın izleme kalitesi",
    description:
      "Işın izleme açıkken kullanılan kalite kademesi. MW4 bunu kendi değer listesiyle ikinci bir kapsamda saklar; ana anahtar Kapalı okunurken yüksek kademede durabilir.",
  },
  "game_config:mw4:tessellation": {
    name: "MW4 mozaikleme",
    description:
      "Düz dokulara kabartı görünümü vermek için yüzey geometrisi ekler. Duvarların şeklini değiştirmek için geometri gücü harcar; oyuncunun tepki verdiği hiçbir şey duvarda değildir.",
  },
  "game_config:mw4:water_caustics": {
    name: "MW4 su ışık desenleri",
    description:
      "Suyun yakın yüzeylere düşürdüğü dalgalı ışık desenlerini benzetir. Dosyadaki en saf süslemelerden biridir — oynanışa hiçbir etkisi olmayan bir efekt.",
  },
  "game_config:mw4:water_wave_wetness": {
    name: "MW4 kalıcı dalga ıslaklığı",
    description:
      "Dalgalar çekildikten sonra sabit geometriyi görünür biçimde ıslak tutar. Etki dalgadan çok sonra da sürer; hiçbir şey olmazken bile hesaplanmaya devam eder.",
  },
  "game_config:mw4:persistent_damage": {
    name: "MW4 kalıcı hasar katmanı",
    description:
      "Mermi deliklerini ve yanık izlerini soldurmak yerine yüzeyde tutar. İzler ateşin nereden geldiğini söyler; bu da onu süsleme değil bilgi yapar.",
  },
  "game_config:mw4:model_quality": {
    name: "MW4 model kalitesi",
    description:
      "Karakter ve silah modellerindeki geometrik ayrıntı. Uzaktaki rakibin ne kadarının gerçekten çizildiğine bu karar verir — cila değil bilgidir.",
  },
  "game_config:mw4:particle_quality": {
    name: "MW4 parçacık kalitesi",
    description:
      "Duman, izli mermi, namlu alevi ve el bombası efektlerinin ayrıntısı. Atılan bomba da sıkılan silah da kendini parçacıklarıyla duyurur; bu, oyuncunun okuduğu bir kanaldır.",
  },
  "game_config:mw4:world_streaming": {
    name: "MW4 dünya akış kalitesi",
    description:
      "Oyunun dünya geometrisini ve dokularını oyuncunun önünden ne kadar agresif yüklediği. Geç yüklemenin bedeli, bakış dönerken bir anlık bulanık manzaradır.",
  },
  "game_config:mw4:shadow_quality": {
    name: "MW4 gölge kalitesi",
    description:
      "Gölge haritalarının çözünürlüğü ve çizim mesafesi. Köşeden düşen gölge, görülmeyen biri hakkında oyuncunun öğrenebildiği az şeyden biridir; gölgenin var olması bilgidir.",
  },
  "game_config:mw4:screen_space_shadows": {
    name: "MW4 ekran alanı gölgeleri",
    description:
      "Modelin yüzeyle buluştuğu yerdeki ince temas gölgeleri; ekran tamponundan hesaplanır. Bedenin dünyaya oturuşunu keskinleştirir; pozisyon veren köşe gölgesi değildir.",
  },
  "game_config:mw4:ambient_lighting": {
    name: "MW4 ortam aydınlatma kalitesi",
    description:
      "Gölgeli alanları dolduran dolaylı, seken ışığın kalitesi. Kapatmak sahneyi düzleştirir — düz sahnede yerdeki beden zeminden ayrışmaz olur.",
  },
  "game_config:mw4:bullet_impacts": {
    name: "MW4 mermi izleri",
    description:
      "Mermilerin yüzeye çarptığı yerde etki efektlerini çizer. Siperin yanındaki izler, daha kimseyi görmeden ateşin yönünü çıkarmanın yoludur.",
  },
  "game_config:mw4:show_blood": {
    name: "MW4 kan efektleri",
    description:
      "İsabet anında kan çizer — oyunun atışın oturduğuna dair onayı. Hedefi örten birikme ayrı bir sınırla kısıtlanır; onay, örtme olmadan korunabilir.",
  },
  "game_config:mw4:st_lod_skip": {
    name: "MW4 LOD atlama",
    description:
      "Çizicinin uzak geometride kaç ayrıntı düzeyi atlayabileceği. Atlanan her düzey daha uzaktaki bir şeyi sadeleştirir; nişancıda daha uzakta olan hedeftir.",
  },
  "game_config:mw4:shader_preload": {
    name: "MW4 çevrimdışı shader ön derleme",
    description:
      "Shader'ları oyun sırasında değil önceden derler. Onsuz bir efektle ilk karşılaşma shader'ını kare ortasında derler — yolda yürürken gelen o takılma budur.",
  },
  "game_config:mw4:gpu_upload_heaps": {
    name: "MW4 GPU yükleme yığınları",
    description:
      "Donanım destekliyorsa Resizable BAR hızlı yolunu kullanarak veriyi doğrudan VRAM'e basar. Özelliği olan makinede bedava kazanç, olmayanda etkisizdir.",
  },
  "game_config:mw4:vrs": {
    name: "MW4 değişken oranlı gölgeleme",
    description:
      "Düşük kontrastlı alanları kaba oranda gölgeler, gözün baktığı yerde ayrıntıyı korur. Oyuncunun zaten okumadığı bölgelerden kare geri kazandırır.",
  },
  "game_config:mw4:dynamic_scene_resolution": {
    name: "MW4 dinamik çözünürlük",
    description:
      "Kare süresi hedefini tutturmak için çözünürlüğü anlık düşürür. Sabit görüntüyü sabit sayıyla takas eder — ve çözünürlük en çok sahne kalabalıklaştığında düşer.",
  },
  "game_config:mw4:absolute_target_resolution": {
    name: "MW4 mutlak hedef çözünürlüğü",
    description:
      "Çizim hedefini ekrandan bağımsız sabit bir çözünürlükle ezer. None bırakıldığında oyun bulunduğu panel için çizer; diğer ekran ayarlarının varsaydığı budur.",
  },
  "game_config:mw4:weapon_cycle_delay": {
    name: "MW4 silah geçiş gecikmesi",
    description:
      "Fare tekeriyle silah değiştirmeler arasına zorlanan asgari bekleme. Sıfırın üstündeki her değer girişle geçiş arasına bilerek konmuş bir bekleyiştir — kasıtlı giriş gecikmesi.",
  },
  "game_config:mw4:music_volume": {
    name: "MW4 müzik sesi",
    description:
      "Oyun müziğinin sesi. Müzik, ayak sesleri ve şarjörlerle aynı çıkışı paylaşır ve konumunu bilmeniz gerekmeyen tek rakip sestir.",
  },
  "game_config:mw4:wartracks_volume": {
    name: "MW4 savaş müziği sesi",
    description:
      "Araçlardan çalan müzik parçalarının sesi. Satın alınan kozmetik bir özelliktir ve müziğin örttüğü aynı ipuçlarını örter.",
  },
  "game_config:mw4:telescope_volume": {
    name: "MW4 menü akışı sesi",
    description:
      "Menülerde oynayan duyuru akışının sesi. Tanıtım sesidir ve maç sırasında asla çalmaz.",
  },
  "game_config:mw4:cinematic_volume": {
    name: "MW4 sinematik sesi",
    description:
      "Kurgulu sinematiklerin sesi. Sinematiklerin çizimini durduran ayarla eşleşir — görüntüsüz ses kalmasın diye.",
  },
  "game_config:mw4:alt_shell_shock": {
    name: "MW4 boğuk sersemleme sesi",
    description:
      "Flaş ya da patlama sonrası çınlama efektini boğuk bir versiyonla değiştirir. Varsayılan çınlama, saniyeler boyunca tam ayak sesi frekanslarının üstüne oturur.",
  },
  "game_config:mw4:mute_licensed_music": {
    name: "MW4 lisanslı müzik",
    description:
      "Oyunun kendi müziğinden ayrı çaldığı lisanslı parçaları susturur. Müzik ses düzeyinden etkilenmeyen ikinci bir müzik kanalıdır.",
  },
  "game_config:mw4:effects_volume": {
    name: "MW4 efekt sesi",
    description:
      "Ayak seslerinin, şarjörlerin ve silah ateşinin yaşadığı efekt kanalının sesi. Diğer tüm ses ayarları bu kanalı temiz tutmak için vardır.",
  },
  "game_config:mw4:hitmarkers_volume": {
    name: "MW4 isabet sesi",
    description:
      "İsabet onay tonunun sesi. Atışın oturduğuna dair oyunun verdiği en hızlı geri bildirimdir — bir karaltıya ateşe devam edilip edilmeyeceğini bu söyler.",
  },
  "game_config:mw4:voice_volume": {
    name: "MW4 konuşma sesi",
    description:
      "Karakter diyaloglarının ve anonsçunun sesi. Anons bildirimleri eyleme dökülen bilgi taşır — tepede düşman UAV'si, alınan hedef — bu yüzden bir kanaldır.",
  },
  "game_config:mw4:mono_sound": {
    name: "MW4 tek kanal ses",
    description:
      "Stereo çıkışı tek kanala indirir. Erişilebilirlik içindir; açmak, yönün okunduğu sağ-sol farkını — ses sisteminin en değerli bilgisini — ortadan kaldırır.",
  },
  "game_config:mw4:mouse_acceleration": {
    name: "MW4 fare ivmesi",
    description:
      "Nişanı farenin hızına göre ölçekler; aynı mesafe hıza göre farklı dönüş üretir. Bir kez tutan fliğin bir daha tutmamasının nedenidir.",
  },
  "game_config:mw4:mouse_filter": {
    name: "MW4 fare filtrelemesi",
    description:
      "Fare girişini birkaç örnek üzerinden ortalar. Ortalama, nişanın elden geride kalması demektir ve gecikme filtre gücüyle büyür.",
  },
  "game_config:mw4:mouse_smoothing": {
    name: "MW4 fare yumuşatması",
    description:
      "Hareket pürüzsüz görünsün diye fare örnekleri arasında ara değer üretir. Yumuşattığı şey fliğin sonundaki küçük hızlı düzeltmedir — atışı oturtan kısım.",
  },
  "game_config:mw4:sprint_assist_delay": {
    name: "MW4 koşu yardımı gecikmesi",
    description:
      "Koşunun kendiliğinden devreye girmesi için yönün ne kadar basılı tutulması gerektiği. Her gecikme, koşmak isterken yürüyerek geçirilen zamandır — her rotasyonun başında.",
  },
  "game_config:mw4:ads_fov_scaling": {
    name: "MW4 nişanda görüş alanı ölçekleme",
    description:
      "Nişan alırken görüş alanını oyuncunun ayarıyla ölçekli tutar. Kapalıyken nişan görüşü sabit varsayılana daraltır ve kenarlarda olanı gizler.",
  },
  "game_config:mw4:free_look": {
    name: "MW4 serbest bakış",
    description:
      "Bakışın hareket yönünden bağımsız dönmesine izin verir. Onsuz oyuncu geri çekilirken arkasını kontrol edemez — arkaya bakmanın önemli olduğu an tam da odur.",
  },
  "game_config:mw4:gamepad_aim": {
    name: "MW4 kumandayla nişan",
    description:
      "Nişanı fare yerine kumanda çubuğuyla sınırlar. Klavye-fare makinesinde açık kalırsa fare nişan almayı tamamen bırakır — oyun bozulmuş gibi görünür.",
  },
  "game_config:mw4:fov": {
    name: "MW4 görüş alanı",
    description:
      "Dünyanın aynı anda ne kadarının göründüğü; 60 ile 120 derece arası. Geniş görüş oyuncunun yanındakini daha çok gösterir ama içindeki her şeyi küçültür ve uzaklaştırır.",
  },
  "game_config:mw4:aspect_ratio": {
    name: "MW4 en-boy oranı",
    description:
      "Pencereden bağımsız belirli bir en-boy oranı zorlar. Auto dışındaki her şey görüntüyü ya gerer ya kenarları kırpar — hareket kenarlarda olur.",
  },
  "game_config:mw4:display_mode": {
    name: "MW4 ekran modu",
    description:
      "Oyunun ekranı nasıl kapladığı. Kenarlıksız, masaüstü birleştiriciyi devrede tutar ama anında alt-tab yapar ve masaüstünün çözünürlük ile yenileme hızını izler.",
  },
  "game_config:mw4:preferred_display_mode": {
    name: "MW4 tercih edilen ekran modu",
    description:
      "Ekran değişikliği veya sürücü sıfırlamasından sonra oyunun döndüğü mod. Etkin moddan ayrı okunur; geride bırakılırsa üstteki modu bir sonraki fırsatta geri alır.",
  },
  "game_config:mw4:vsync": {
    name: "MW4 V-Sync",
    description:
      "Her kareyi ekran hazır olana dek tutar. Değişken yenilemeli panelde ekran zaten kareyi bekler; V-Sync yalnızca kuyruğa — tam bir kareye kadar — bekleme ekler.",
  },
  "game_config:mw4:vsync_menu": {
    name: "MW4 menü V-Sync",
    description:
      "Yalnızca menülerde uygulanan V-Sync. Menüde giriş gecikmesi önemsizdir; orada sınırlamak, GPU'nun maç başlamadan kasayı ısıtmasını durdurmanın en ucuz yollarından biridir.",
  },
  "game_config:mw4:cap_fps": {
    name: "MW4 özel kare sınırı",
    description:
      "Bu oyundaki tüm kare sınırlarının ana anahtarı. Kapalıyken oyun içi, menü ve odak dışı sınırların hepsi etkisizdir — makine lobide 900 kare çizmeye böyle varır.",
  },
  "game_config:mw4:display_gamma": {
    name: "MW4 renk uzayı",
    description:
      "Oyunun çıktı verdiği renk uzayı. sRGB, sıradan bir SDR panelin beklediğidir; alternatifi farklı bir aktarım eğrisini hedefler ve gölgeli alanları yanlış okutur.",
  },
  "game_config:mw4:hdr": {
    name: "MW4 HDR",
    description:
      "Oyunun yüksek dinamik aralık çıkışı verip vermediği. Automatic ekrana sorar ve yanıta göre davranır — panelin HDR yeteneği fpstune'un elindeki veride yoktur.",
  },
  "game_config:mw4:menu_scene_resolution": {
    name: "MW4 menü sahne çözünürlüğü",
    description:
      "Etkileşimsiz menülerin arkasındaki 3B sahnenin çizim çözünürlüğünü düşürür. Menüde nişan alınan bir şey yoktur; oraya harcanan pikseller maça taşınan ısıdır.",
  },
  "game_config:mw4:reduce_quality_idle": {
    name: "MW4 boşta kalite düşürme",
    description:
      "Oyuncu hareketsiz kaldığında çizim kalitesini düşürür. Hareketsiz oyuncu tanımı gereği kimseyi aramıyordur; kalitenin ona gösterecek bir şeyi yoktur.",
  },
  "game_config:mw4:reduce_quality_idle_delay": {
    name: "MW4 boşta kalite gecikmesi",
    description:
      "Kalitenin düşmesi için oyuncunun ne kadar hareketsiz kalması gerektiği. MW4 bunu üstteki anahtarla aynı adlı ikinci bir kapsamda, kendi süre listesiyle tutar.",
  },
  "game_config:mw4:pause_rendering": {
    name: "MW4 çizimi durdurma",
    description:
      "Duraklatma menüsünde veya pencere odağı kaybettiğinde çizimi tamamen durdurur. Odak dışı kare sınırı aynı işi 30 fps'te zaten görür; tam durdurma her şeyi yeniden kurmak zorunda kalır.",
  },
  "game_config:mw4:eco_low_battery": {
    name: "MW4 düşük pil modu",
    description:
      "Pil azalınca oturumu uzatmak için ağır ayarları düşürür. Dizüstünde, maçın ortasında, kendini duyurmadan devreye giren bir kare hızı tavanıdır.",
  },
  "game_config:mw4:eco_battery_threshold": {
    name: "MW4 düşük pil eşiği",
    description:
      "Üstteki tasarrufun devreye girdiği pil düzeyi. MW4 bunu aynı aralıklı iki kapsam indeksinde tutar; ikisi uyuşmazsa bağlayan eşik beklediğiniz olmaz.",
  },
  "game_config:mw4:skip_intro": {
    name: "MW4 açılış logoları",
    description:
      "Açılıştaki yayıncı ve motor logolarını atlar. Her oturumda aynı saniyelere mal olur ve iki kez izlenecek bir şey içermezler.",
  },
  "game_config:mw4:skip_season_video": {
    name: "MW4 tekrarlanan sezon videosu",
    description:
      "İlk izlemeden sonraki her girişte sezon videosunu atlar. İlk atlatan anahtardan ayrıdır; geride bırakılırsa video sonraki oturumlarda geri gelir.",
  },
  "game_config:mw4:enable_hud": {
    name: "MW4 arayüz (HUD)",
    description:
      "HUD'u çizer — can, mermi, mini harita, seri durumu. Her ögesi oyuncunun eyleme döktüğü bilgidir; kare için kapatmak mümkün olan en net yanlış tasarruftur.",
  },
  "game_config:mw4:amd_antilag": {
    name: "MW4 AMD Anti-Lag 2",
    description:
      "AMD'nin düşük gecikme modu; kareleri GPU önünde biriktirmek yerine çizim kuyruğunu kısa tutar. NVIDIA Reflex'in karşılığıdır; kapalı bırakmak aynı gecikmeyi masada bırakır.",
  },
  "game_config:mw4:amd_fsr_quality": {
    name: "MW4 FSR kalite modu",
    description:
      "FSR 2/3'ün yükseltmeden önce çizdiği iç çözünürlük. Yükseltici kare almak için var; en pahalı kademesi açılma nedeninin çoğunu geri verir.",
  },
  "game_config:mw4:amd_fsr1_quality": {
    name: "MW4 FSR 1 kalite modu",
    description:
      "FSR 2/3'ten ayrı tutulan eski uzamsal FSR 1 yolunun kalite kademesi. Yalnız FidelityFX FSR 1'e ayarlıyken geçerlidir; burada düşük kademe zamansal onarımı olmayan yumuşak bir görüntüdür.",
  },
  "game_config:mw4:amd_fidelityfx": {
    name: "MW4 AMD FidelityFX",
    description:
      "Hangi FidelityFX yolunun etkin olduğu: yalnız keskinleştirme, uzamsal FSR 1 veya zamansal FSR 3. MW4 seçimi aynı değer listesiyle iki kapsam indeksinde tutar; ikisi uyuşmalıdır.",
  },
  "game_config:mw4:amd_cas_strength": {
    name: "MW4 kontrast uyarlamalı keskinleştirme",
    description:
      "AMD keskinleştirme filtresinin gücü. Keskinleştirme, yükselticinin yumuşattığının bir kısmını geri alır; ama bir noktadan sonra kenarlarda hale çizer — nesne olmayan yerde kontrast üretir.",
  },
  "game_config:mw4:fsr_frame_interpolation": {
    name: "MW4 FSR kare üretimi",
    description:
      "Çizilen karelerin arasına üretilmiş kareler ekler. Sayaç yükselir, giriş gecikmesi de yükselir; üretilmiş bir kare oyuncunun yaptığı hiçbir şeyi gösteremez.",
  },
  "game_config:mw4:intel_xell": {
    name: "MW4 Intel XeLL",
    description:
      "Intel'in düşük gecikme modu; kareleri biriktirmek yerine çizim kuyruğunu kısa tutar. Reflex ve Anti-Lag'in karşılığıdır; Arc sahibi kapalı bırakınca aynı kazancı kaybeder.",
  },
  "game_config:mw4:xess_quality": {
    name: "MW4 XeSS kalite modu",
    description:
      "XeSS'in yükseltmeden önce çizdiği iç çözünürlük. Yükseltici kare almak için var; en pahalı kademesi açılma nedeninin çoğunu geri verir.",
  },
  "game_config:mw4:intel_xefg": {
    name: "MW4 Intel XeSS kare üretimi",
    description:
      "Çizilen karelerin arasına üretilmiş kareler ekler. Sayaç yükselir, giriş gecikmesi de; üretilmiş kare oyuncunun yaptığı hiçbir şeyi gösteremez.",
  },
  "game_config:mw4:intel_xefg_multi": {
    name: "MW4 XeSS kare üretim çarpanı",
    description:
      "XeSS'in çizilen kare başına kaç kare ürettiği. Kare üretimi kapalıyken etkisizdir; 1 üstündeki her adım üretimin kendisinin üstüne gecikme ekler.",
  },
  "game_config:mw4:dlss_mode": {
    name: "MW4 DLSS modu",
    description:
      "Hangi DLSS yolunun çalıştığı: yükseltme, doğal çözünürlükte kenar yumuşatma veya ışın yeniden kurma gürültü gidericisi. Kare geri getirirken görüntüyü ayakta tutan, yükseltmedir.",
  },
  "game_config:mw4:dlss_frame_generation": {
    name: "MW4 DLSS kare üretimi",
    description:
      "Çizilen karelerin arasına üretilmiş kareler ekler. Sayaç yükselir, giriş gecikmesi de yükselir; üretilmiş kare oyuncunun yaptığı hiçbir şeyi gösteremez.",
  },
  "game_config:mw4:dlss_sharpness": {
    name: "MW4 DLSS keskinliği",
    description:
      "DLSS yükseltmesinden sonra uygulanan keskinleştirme. Bir miktarı yükselticinin yumuşattığını geri alır; fazlası kenarlarda hale çizer ve nesne olmayan yerde kontrast üretir.",
  },
  "game_config:mw4:nvidia_image_scaling": {
    name: "MW4 NVIDIA görüntü ölçekleme",
    description:
      "DLSS öncesinden kalma, zamansal bilgisi olmayan uzamsal bir yükseltici. DLSS ile birlikte çalıştırmak iki yükselticiyi üst üste bindirir — yükseltici altında düşük çizim çözünürlüğüyle aynı hatadır.",
  },
  "game_config:mw4:dxr_denoiser": {
    name: "MW4 ışın izleme gürültü gidericisi",
    description:
      "Işın izlemeli aydınlatmayı hangi gürültü gidericinin temizlediği. Işın izleme kapalıyken etkisizdir; buradaki üreticiye özgü seçenekler yan etki olarak kendi yükseltici yollarını da getirir.",
  },
  "game_cleanup:mw4:shader_cache_cleanup": {
    name: "MW4 shader önbelleği",
    description:
      "MW4'ün derlenmiş shader önbelleğini ve oyun klasöründeki xpak ile telescope içerik önbelleklerini siler. Oyun üçünü de bir sonraki açılışta yeniden kurar.",
  },
  "game_cleanup:cod_crash_reports": {
    name: "Call of Duty çökme raporları",
    description:
      "Call of Duty başlatıcısının oyuncu profili yanına yazdığı çökme dökümlerini ve GPU hata raporlarını siler. Çoktan olup bitmiş çökmelerin tanılama dosyalarıdır.",
  },
  "network:*:interrupt_moderation": {
    name: "Kesme biriktirme",
    description:
      "Ağ bağdaştırıcısının birden çok paket için CPU kesme isteklerini biriktirip biriktirmediği. Kapatmak her paketi anında işler; biraz CPU karşılığında gecikme düşer.",
  },
  "network:*:flow_control": {
    name: "Akış denetimi",
    description:
      "Donanım akış denetimi, alma arabellekleri dolunca duraklatma çerçeveleriyle iletimi durdurur. Kapatmak bu duraklamaların yol açtığı gecikme sıçramalarını bitirir.",
  },
  "network:*:eee": {
    name: "Enerji tasarruflu Ethernet",
    description:
      "IEEE 802.3az güç tasarrufu. Kapatmak boştan etkine geçişteki gecikme sıçramalarını önler.",
  },
  "network:*:advanced_eee": {
    name: "Derin Ethernet güç tasarrufu",
    description:
      "Intel genişletilmiş güç tasarrufu (daha derin EEE). Kapatmak gecikme sıçramalarını önler.",
  },
  "network:*:power_management": {
    name: "Bağdaştırıcı güç tasarrufu",
    description:
      "Windows'un güç tasarrufu için bağdaştırıcıyı kapatmasına izin verir. Kapatmak kopmaları önler.",
  },
  "network:*:lso": {
    name: "Büyük paket devretme",
    description:
      "Büyük paketleri ağ kartı böler. Kapatmak küçük paketlerde gecikmeyi azaltır.",
  },
  "network:*:checksum_offload": {
    name: "Sağlama devretme",
    description:
      "Paket sağlamalarını ağ kartı hesaplar. Güvenli bir iyileştirmedir; gecikme etkisi yoktur.",
  },
  "network:*:wake_on_lan": {
    name: "Ağdan uyandırma",
    description:
      "Bilgisayarı ağ paketiyle uyandırır. Kapatmak beklenmedik uyanmaları önler.",
  },
  "network:*:receive_buffers": {
    name: "Alma arabellekleri",
    description:
      "Ağ kartının paket alma arabelleği boyutu. Yüksek değer, patlamalarda daha az paket kaybı demektir.",
  },
  "network:*:transmit_buffers": {
    name: "Gönderme arabellekleri",
    description:
      "Ağ kartının paket gönderme arabelleği boyutu. Yüksek değer, ani yüklemelerde daha az takılma demektir.",
  },
  "network:*:packet_coalescing": {
    name: "Uyanıkken paket biriktirme",
    description:
      "Etkin güç durumunda gelen paketleri CPU bildirimlerini azaltmak için biriktirir. Kapatmak DPC gecikme sıçramalarını kaldırmak için paket başına işlemeye zorlar.",
  },
  "network:*:msi_mode": {
    name: "Kesme modu (MSI)",
    description:
      "Ağ kartı kesmelerini paylaşımlı eski IRQ hatları yerine aygıt başına MSI/MSI-X ile iletir. Açmak paylaşımlı kesme gecikmesini kaldırır.",
  },
  "network:*:green_ethernet": {
    name: "Green Ethernet",
    description:
      "Tahmini kablo uzunluğuna göre verici gücünü düşüren Realtek tasarrufu. Sınırdaki bir kabloda azalan sinyal payı, bağlantı yenileme ve kısa kopmalar olarak görünür.",
  },
  "network:*:gigalite": {
    name: "GigaLite yarı hız modu",
    description:
      "Bağdaştırıcının düşük güçlü bağlantı modu pazarlığına izin veren Realtek tasarrufu. Kablo ve anahtarın desteklediğinden düşük bir hızda karar kılabilir.",
  },
  "network:*:nic_power_saving": {
    name: "Ağ kartı güç tasarrufu",
    description:
      "Bağdaştırıcının toplu boşta güç yönetimi (Realtek). Düşük güç durumuna girip çıkmak, boşluk sonrası ilk pakette uyanma süresine mal olur.",
  },
  "network:*:rss_base_processor": {
    name: "Ağ için CPU çekirdeği seçimi",
    description:
      "Ağ kartı kesmelerini RSS üzerinden karşılayan ilk CPU çekirdeği. Tabanı yoğun Çekirdek 0'dan taşımak DPC gecikmesini düşürür.",
  },
  "network:*:speed_duplex": {
    name: "Bağlantı hızı ve dupleks",
    description:
      "Bağdaştırıcının anahtarla bağlantı hızını nasıl kararlaştırdığı. Otomatik pazarlık standarttır ve tek güvenli seçimdir; zorlanmış hız onu bozar.",
  },
  "network:*:link_capability": {
    name: "Hat hızı denetimi",
    description:
      "Bu bağlantının pazarlıkla vardığı hızı bağdaştırıcının desteklediği en yüksek hızla karşılaştırır. Fark; kablo, anahtar portu veya karşı uç sınırıdır — Windows ayarı değildir.",
    effect:
      "Kabloyu kontrol edin (1 Gbps için Cat 5e ve üstü, 2,5 Gbps ve üzeri için Cat 6), başka bir anahtar portu deneyin ve karşı ucun yüksek hızı desteklediğini doğrulayın.",
  },
  "network:*:wifi_link_quality": {
    name: "Wi-Fi sinyal denetimi",
    description:
      "Wi-Fi bağlantısının ne kadar güçlü olduğu ve hangi bantta çalıştığı. Zayıf sinyal ya da 2,4 GHz bandı, hiçbir bağdaştırıcı ayarının kaldıramayacağı gecikme sıçramaları ekler ve hızı sınırlar.",
    effect:
      "Erişim noktasına yaklaşın ya da aradaki engeli kaldırın; yönlendirici sunuyorsa 5 GHz veya 6 GHz ağına bağlanın; kablo ikisini de geçer.",
  },
  "network:*:wifi_security": {
    name: "Wi-Fi güvenlik denetimi",
    description:
      "Wi-Fi bağlantısının hangi güvenlik standardını ve şifreyi kullandığı. TKIP veya WEP şifresi bağlantıyı 802.11g hızına kilitler; iki uç da WPA3 yapabiliyorken WPA2, aynı hızda daha zayıf korumadır.",
    effect:
      "Modemi AES ile WPA2/WPA3 yapın; sonra Windows'ta bu ağı unutup yeniden bağlanın ki profil güçlü standartla oluşsun.",
  },
  "network:*:roaming_aggressiveness": {
    name: "Wi-Fi gezinme hevesi",
    description:
      "Wi-Fi erişim noktası tarama sıklığı. Düşük değer, oyun sırasında daha az ping sıçraması demektir.",
  },
  "network:*:uapsd": {
    name: "Wi-Fi güç tasarruflu teslim",
    description:
      "Wi-Fi güç tasarrufu paket teslim zamanlaması (U-APSD/WMM-PS). Kapatmak inen paketleri anında teslim eder; gecikme ve seğirme düşer.",
  },
  "network:*:throughput_booster": {
    name: "Wi-Fi aktarım güçlendirici",
    description:
      "Aktarımı seğirme pahasına yükselten Wi-Fi paket biriktirme özelliği. Kapatmak oyun için tutarlı, düşük seğirmeli teslimi öne alır.",
  },
  "network:*:mtu": {
    name: "Paket boyutu (MTU)",
    description:
      "Bu bağdaştırıcının bölmeden gönderdiği en büyük çerçeve. Hattın gerçekten taşıdığıyla eşleşmelidir — fpstune bunu varsaymak yerine ölçer.",
  },
  "game_config:mw3:vram_scale": { name: "MW3 VRAM hedefi", description: "" },
  "game_config:mw3:aa_technique": {
    name: "MW3 kenar yumuşatma tekniği",
    description: "",
  },
  "game_config:mw3:refresh_rate": {
    name: "MW3 yenileme hızı",
    description: "",
  },
  "game_config:mw3:fps_cap_ingame": {
    name: "MW3 oyun içi kare sınırı",
    description: "",
  },
  "game_config:mw3:fps_cap_menu": {
    name: "MW3 menü kare sınırı",
    description: "",
  },
  "game_config:mw3:resolution": {
    name: "MW3 tam ekran çözünürlüğü",
    description: "",
  },
  "game_config:mw4:vram_scale": { name: "MW4 VRAM bütçesi", description: "" },
  "game_config:mw4:aa_technique": {
    name: "MW4 kenar yumuşatma tekniği",
    description: "",
  },
  "game_config:mw4:fps_cap_ingame": {
    name: "MW4 oyun içi kare sınırı",
    description: "",
  },
  "game_config:mw4:fps_cap_menu": {
    name: "MW4 menü kare sınırı",
    description: "",
  },
  "game_config:mw4:refresh_rate": {
    name: "MW4 yenileme hızı",
    description: "",
  },
  "game_config:mw4:resolution": {
    name: "MW4 tam ekran çözünürlüğü",
    description: "",
  },
  "game_config:hots:refresh_rate": {
    name: "HotS yenileme hızı",
    description: "",
  },
  "game_config:hots:sound_sample_rate": {
    name: "HotS ses örnekleme hızı",
    description: "",
  },
};

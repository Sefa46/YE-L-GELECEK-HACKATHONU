# SİPER AI — Codex Ana Proje Planı

> **Proje adı:** SİPER AI
> **Açılımı:** Sel İçin Proaktif Erken Risk Yönetimi
> **Alt başlık:** Yapay Zekâ Destekli Drenaj Ağı, Afet Öncesi Risk ve Müdahale Optimizasyonu Platformu
> **İngilizce çalışma adı:** *SIPER AI — Predictive Stormwater Infrastructure & Flood-Risk Operations Platform*
> **Proje türü:** Açık veri + görüntü analizi + hidrolik dijital ikiz + karar optimizasyonu + operasyon yönetimi
> **Etkinlik:** KTÜ Yeşil Gelecek Hackathonu, 30–31 Ekim 2026; 2 kişilik ekip, 24 saat.
> **Durum:** Mühendislik tasarımı. Burada belirtilen algoritmaların sonuç verdiği **henüz deneysel olarak gösterilmemiştir**.

---

## 0. CODEX'E GÖREV — ÖNCE BURAYI OKU

Bu belge **yürütülebilir geliştirme talimatıdır**, fikir özeti değildir. Amaç 24 saatte sıfırdan üretim seviyesinde belediye yazılımı yapmak değil, **küçük ama uçtan uca çalışan ve karşılaştırmalı ölçümü olan bir MVP** üretmektir.

**Ana kural:** Sadece fotoğrafta tıkanıklık işaretleyen ya da “ekibi buraya gönderin” diyen bir demo yapma. Sistem şu zinciri gerçekten çalıştırmalı:

`Meteorolojik uyarı / yağış senaryosu → Altyapı gözlemi → Görsel ve sensör verisinin yorumlanması → Bağlantılı drenaj ağında risk hesabı → Müdahale senaryolarının dijital ikizde değerlendirilmesi → Kısıtlı ekip/araç/zaman optimizasyonu → İş emri ve uygulama akışı → Yeni gözlem → Riskin tekrar hesaplanması ve yeniden planlama.`

**Codex çalışma ilkeleri:**

1. Önce mevcut depo dosyalarını incele, hazır kod varsa bozma; yoksa bu belgedeki mimariyle başla.
2. Her aşamadan sonra çalışan bir ara sürüm bırak; testleri çalıştır ve sonucu belirt.
3. Bir bağımlılık, API veya veri seti erişilemezse **deterministik, kaynağı etiketlenmiş demo verisiyle** devam et; sahte canlı veri veya sahte deney başarısı üretme.
4. Risk modeli, derin öğrenme ve hidrolik model arasındaki bağları modüler tut; bir modül başarısız olduğunda demo bütünü çökmesin.
5. **P0 görevleri tamamlanmadan P1 özelliklerine geçme.**
6. Tüm arayüz dili Türkçe olsun; Python modül, fonksiyon ve veri alanları İngilizce olabilir.
7. Her iddia için kaynağı belirt: `real_observation`, `forecast`, `open_dataset`, `synthetic_scenario`, `hydraulic_simulation`, `heuristic_estimate`, `operator_input`.
8. Kritik operasyon kararlarını **öneri / simülasyon / yetkilendirilmiş onay** olarak ayır. Gerçek belediye pompası, vanası, şebekesi veya kamu alarmına izinsiz komut gönderme.
9. Her yeni kod parçası için kısa test yaz; yanıtı yalnızca güzel ekran görüntüsüyle sınırlama.
10. Son teslimde gerçek durum tablosu oluştur: `Çalışıyor / Kısmi / Simülasyon / Yapılmadı`.

## 1. Vizyon ve temel problem

Şiddetli yağış uyarısı verildiğinde bir şehirde **mazgallar, yağmur suyu girişleri, menfezler, kolektörler, açık kanallar, dere geçişleri, depolama havuzları, terfi pompaları ve deşarj noktaları** birbirine bağlı olarak çalışır. Birinde tıkanıklık veya kapasite kaybı olduğunda diğerlerinin de davranışı değişebilir.

Belediyenin sınırlı sayıda ekibi, aracı, pompası, müdahale süresi ve erişilebilirliği bulunur. **En fazla tıkalı altyapı elemanını önce temizlemek, mutlaka en fazla taşkın riskini azaltan karar değildir.** Bir menfezin açılması veya kritik pompanın kullanılabilir hale gelmesi, aynı sürede birçok küçük mazgal temizliğinden daha etkili olabilir. Tersine, aşağı akım doluyken üst taraftaki su girişini açmak bazı koşullarda istenmeyen sonuçlar doğurabilir.

### Ana soru

> **Yaklaşan yağış öncesindeki sınırlı zamanda, hangi altyapı unsurlarına hangi sırayla ve hangi kaynaklarla müdahale edilirse şehir genelindeki modellenen taşkın etkisi en fazla azaltılır?**

### Sistem ne DEĞİLDİR?

- Yalnızca mazgal tıkanıklığı sınıflandırıcısı değildir.
- Genel bir “sel tahmin ettik, uyarı veriyoruz” uygulaması değildir.
- Tek başına GPS rota çizimi veya yapılacaklar listesi değildir.
- Kamera fotoğrafından yer altındaki bütün sorunları bildiğini iddia etmez.
- Gerçek şehirde taşkını tamamen engellediğini iddia etmez.
- Bir noktada görülen yüzey kapanma yüzdesini doğrudan hidrolik kapasite kaybı diye kabul etmez.

### Başarı tanımı

**Aynı yağış ve aynı kaynak koşullarında**, sırayla bakım, yalnız tıkanıklığa göre bakım ve yalnız risk puanına göre bakıma kıyasla, SİPER AI'nın seçtiği **müdahale kombinasyonu** daha düşük modellenen taşkın etkisi üretmelidir; aynı zamanda ekip, süre ve güvenlik kısıtlarına uymalıdır. Daha iyi sonuç elde edilmezse bunu açıkça raporla.

---

## 2. Yarışma kapsamı ve değerlendirme

Organizatörün kullanıcıya bildirdiği açıklamaya göre **afet önleme kapsamı kabul ediliyor**; bu bilgi kullanıcı beyanıdır, yüklenen Word belgesinin açık alt teması değildir.

Word şartnamesi dört tema tanımlar: (2.1) yapay zekâ ve bilgisayarlı görüyle sıfır atık; (2.2) IoT tabanlı çevre ve kaynak izleme; (2.3) dijital karbon ve sürdürülebilirlik; (2.4) akıllı tarım ve verimlilik. SİPER AI özellikle **2.2 ile ilişkilendirilecek**, afet önleme izniyle kapsam genişletilecektir.

**Jüri kriterleri:** çevresel etki ve sürdürülebilirlik **%30**, teknik altyapı ve çalışan demo **%30**, inovasyon ve özgünlük **%20**, sunum ve sahada uygulanabilirlik **%20**.

**Teslim:** Çalışan MVP/demo, açık kaynak kodlu GitHub deposu ve varsa donanım mimarisi. Hazır kütüphane/API kullanmak serbesttir; asıl entegrasyon ve yenilik yarışmada geliştirilmelidir.

---

## 3. Altyapı veri modeli: bütün drenaj ağı

Başlangıçta 8–12 bağlı unsurdan oluşan **küçük, sentetik ve açıkça işaretlenmiş** bir drenaj ağı oluştur. Her unsurun bağlantıları, konumu, türü, kapasitesi/kapasite göstergesi ve durum gözlemi olsun.

| Tür | Örnek gözlem | Potansiyel müdahale | MVP kapsamı |
|---|---|---|---|
| `inlet` / `grate` | Görsel atık, yüzey kapanması, giriş su seviyesi | Çöp temizliği | **P0** |
| `culvert` | Görsel tıkanma, giriş/çıkış su seviyesi | Engel kaldırma | **P0** |
| `pipe` / `collector` | CCTV muayenesi, basınç/seviye, kapasite düşüşü | Doğrulanmış bakım / uygun temizleme | P0 ağda temsil, P1 görüntü |
| `open_channel` | Tortu, bitki, su seviyesi | Kanal bakımı | P0 ağda temsil |
| `pump_station` | Çalışma durumu, hazır kapasite | Yetkili pompa operasyonu | **P0 simülasyon** |
| `storage` | Doluluk, kullanılabilir hacim | Güvenli depolama/tahliye senaryosu | P0 ağda temsil |
| `outfall` | Çıkış koşulları, aşağı akım su seviyesi | Çıkış kontrolü / senaryo | P0 ağda temsil |
| `critical_area` | Alt geçit, yol, hastane erişimi vb. | Doğrudan bakım değil; maruziyet katsayısı | **P0** |

**İlişkiler:** `upstream_ids`, `downstream_ids` veya `NetworkX` yönlü grafı ile **ağ bağlantıları** tutulsun. Hidrolik etkiyi yalnız geometriye indirgeme; graf, gerçek SWMM modelinin yerine geçmez.

### Varlık şeması (önerilen alanlar)

```text
Asset:
  id: str
  name: str
  type: enum[inlet, grate, culvert, pipe, collector, open_channel,
             pump_station, storage, outfall]
  lat: float | null
  lon: float | null
  upstream_ids: list[str]
  downstream_ids: list[str]
  drainage_zone_id: str
  image_path: str | null
  blockage_visual_fraction: float | null  # 0..1: sadece görünür alan oranı
  hydraulic_capacity_factor: float | null # 0..1: ayrı kalibre/senaryo değişkeni
  water_level_m: float | null
  observation_time: ISO8601 | null
  observation_source: enum[real_observation, open_dataset, synthetic_scenario,
                           operator_input, simulated_sensor]
  confidence: float | null
  inspection_accessible: bool
  criticality_tags: list[str]
  condition_notes: str
```

**Önemli:** `blockage_visual_fraction` ile `hydraulic_capacity_factor` farklı alanlar; aralarındaki dönüşüm kalibre edilmemişse uyarı göster.

---

## 4. Yedi katmanlı işleyiş

### Katman 1 — Meteorolojik erken uyarı ve olay tetikleme

**Girdi:** Kullanıcının eklediği doğrulanabilir MGM MeteoUYARI kaydı veya demo uyarısı; Open-Meteo saatlik yağış tahmini, yağış olasılığı, zaman damgası ve veri kaynağı.

**İş:** `WeatherEvent` oluştur. Yağış başlamadan kalan zamanı ve senaryoları (düşük/orta/yüksek yoğunluk) hesapla. **MGM uyarısını tahmin API'sinden türetip “resmî uyarı” diye gösterme.** MGM'nin herkese açık sayfasından doğrulanabilir giriş veya manuel operatör kaydı kullanılabilir; teyitsiz API/scraper varsayma.

**Çıktı:** `event_id`, zaman aralığı, saatlik yağış dizisi, senaryo kimliği, veri güvenilirliği.

### Katman 2 — Görsel analiz, sensörler ve gözlem güveni

**Girdi:** Mazgal/menfez fotoğrafı, varsa seviye/debi/operasyon telemetrisi, önceki bakım tarihi, çekim saati.

**P0:** Önce görüntü işleme için gerçekten çalışır ve ölçülebilir basit bir yöntem oluştur: manuel doğrulanabilen tıkanıklık etiketi + opsiyonel CV model tahmini + güven skoru. **Hazır bir modeli kullanıp doğru çalıştığını test etmeden “AI detection” gösterme.** Görsellerde `unblocked`, `partial`, `severe`, `unknown` etiketlerini destekle. Zor sahnede model `unknown` dönebilir.

**P1:** Zenodo menfez veri setinden **izin/lisans koşulları doğrulanmış küçük bir alt küme** ile eğitim/değerlendirme. Veri seti menfez ağırlıklıdır; doğrudan Türkiye yol mazgalı modeli diye iddia etme. Manuel kamera örnekleriyle domain-shift testi yap.

**Çıktı:** Gözlemin tarihi, kaynağı, sınıfı, belirsizliği; varlığın durumundaki değişiklik.

### Katman 3 — Hidrolik dijital ikiz ve bütün-ağ etki modeli

**Tercih edilen motor:** EPA SWMM 5.2; Python entegrasyonu uygunsa PySWMM. Bir örnek `.inp` şebekesi ve **aynı yağış altında** başlangıç durumunu çalıştır.

**P0 teknik yaklaşımı:** Önce küçük ağ üzerinde güvenilir, tekrar üretilebilir baz koşul oluştur. İlgili SWMM varlıkları ve giriş tipleri destekliyorsa tıkanıklık/kapasite senaryosu uygula. SWMM 5.2'nin inlet usage tanımı `Clogged` alanını içerir; ancak bu alan yalnız **uygun giriş/bağlantı konfigürasyonları** için kullanılmalıdır. Menfez, pompa, kollektör müdahalelerini ayrı doğru hidrolik değişkenler üzerinden modelle. SWMM ile her tür varlığı aynı `Clogged` parametresiyle temsil etme.

**Fallback:** SWMM ikili çalıştırma veya `.inp` entegrasyonu kurulamazsa **ayrı isimli, basitleştirilmiş `proxy_model`** kullan. Bu mod **fiziksel taşkın tahmini değil**; grafik üzerinden karar algoritması demosudur ve arayüzde açıkça `HEURISTIC / NOT HYDRAULICALLY VALIDATED` yazsın.

**Çıktı metrikleri:** Simüle edilen yüzey taşma hacmi (m³, simülatör sağlıyorsa), kritik düğüm taşma göstergeleri, su seviyeleri, kapasite göstergeleri, toplu senaryo özeti. Simülatör vermiyorsa sayısal m³ uydurma.

### Katman 4 — Risk değerlendirmesi, hiyerarşik sıralama

Dört kademeli karar yapısı kur:

1. **Olay riski:** Yaklaşan yağış senaryosunun gücü / belirsizliği.
2. **Bölge riski:** Drenaj havzası ve maruz kalan kritik altyapı için modellenen etki.
3. **Varlık riski:** Konum, gözlem güveni, hidrolik bağlam ve kapasite sorunu.
4. **Müdahale faydası:** Bu müdahale uygulanırsa **tüm ağda** ne kadar etki azalır?

**İki puanı karıştırma:** `risk_score` ≠ `intervention_benefit`. En riskli öğe her zaman ilk görev değildir.

Risk puanı ilk MVP'de açıklanabilir, ağırlıkları yapılandırılabilir bir indeks olabilir. Gerçek sel olasılığı veya gerçek beklenen ekonomik zarar diye pazarlama. Sahada doğrulanmış maruziyet verisi yoksa `simulated_risk_index` olarak etiketle.

### Katman 5 — Müdahale adayları ve bileşik etki

`Action` kayıtları: `clean_inlet`, `clear_culvert`, `clear_channel`, `inspect_collector`, `prepare_pump`, `operate_pump_simulated`, `evaluate_storage_drawdown`.

Her eylem:

- `asset_id`, tahmini süre, gerekli ekipman, uygun ekip/ehliyet, saha erişimi
- zaman penceresi, maliyet puanı, güvenlik kısıtı
- *önce/sonra* durum dönüşümü
- tek başına `simulated_benefit` ve **başka eylemlerle etkileşimi**

**Çok önemli inovasyon:** Eylemler arası faydayı doğrudan toplama. `Benefit(A+B)` her zaman `Benefit(A)+Benefit(B)` değildir. Küçük bir ağda tekli ve ikili müdahale kombinasyonlarını dijital ikizde dene ve sonucu önbellekle (`scenario_hash + action_set`).

### Katman 6 — Kısıtlı ekip, araç, zaman ve rota optimizasyonu

**Girdi:** 2–3 ekip; ekip başlangıç noktaları; araç/ekipman; erişim ve trafik için test amaçlı süre matrisi; tahmini bakım süreleri; yağışa kalan süre; `intervention_benefit`.

**P0:** Önce uygulanabilirliği sağlayan bir çözüm üret; başlangıçta deterministik greedy/beam search olabilir. Birden fazla ekiple, bazı işlerin seçilememesi ve zaman pencereleri için Google OR-Tools kullanılabilir.

**Hedef:** Belirlenmiş süre ve kaynaklar içinde en fazla **senaryo bazlı sistem-geneli risk/taşkın etkisi azalımı**. Rota optimizasyonunun amaç fonksiyonu yalnız mesafe minimizasyonu olmasın. İlk sürümde görev portföyü seçimi (`action set`) + ekip/rota ataması iki aşamalı yapılabilir; portföy faydasını eylemlerin toplamıymış gibi hesaplama.

**P0 senaryo:** 8–12 varlık, 6–8 aday müdahale, 2 ekip, 1–3 araç/ekipman türü ve 120 dakika (temsili) son zaman.

**Çıktı:** `Plan` → her ekip için sırayla atanmış görevler; toplam süre; elenen görevlerin nedeni; karşılanamayan kısıtlar; baz senaryoya göre risk farkı.

### Katman 7 — İş emri, uygulama doğrulama ve yeniden planlama

**İş emri durumları:** `candidate → assigned → en_route → in_progress → completed_pending_verification → verified` veya `failed / inaccessible / cancelled`.

- Operatör veya demo simülatörü `completed` bildirir.
- Yeni gözlem / fotoğraf / sensör değeri gerekir; yoksa `verified` deme.
- Müdahale sonrası ağ senaryosunu **yeniden** hesapla.
- Fayda ölçülmedi veya ekip geciktiyse kalan işleri yeniden planla.
- Tüm kararları `event_log` içinde zaman, veri kaynağı, kim/ne, karar gerekçesi olarak kaydet.

**Gerçek dünya ayrımı:** Belediye çalışanının temizleme işi fiziksel eylemdir. MVP'deki `apply_action()` dijital ikizde durum dönüşümüdür; gerçek sahaya komut gönderildiği iddia edilmez. Uzaktan kontrol edilebilir pompa varsa yalnız yetkili endüstriyel entegrasyonla çalıştırılabilir; yarışma demosunda *simüle* edilir.

---

## 5. Teknik mimari ve teknoloji seçimi

**Hızlı MVP için önerilen yığın:**

- **Python 3.11**; `streamlit` (tek ekran/çok sekmeli panel), `pydantic`, `pandas`, `numpy`.
- **Görsel analiz:** `opencv-python-headless`, `Pillow`; isteğe bağlı Ultralytics/öğrenilmiş model, ama şart değil.
- **Ağ:** `networkx`; coğrafi görünüm için Streamlit `pydeck` veya basit SVG/Plotly; hassas konumlar için sentetik veri.
- **Hidrolik:** EPA SWMM + mümkünse `pyswmm`; bağımsız çalıştırılabilir adapter ve `proxy_model` yedeği.
- **Planlama:** İlk aşamada sınırlı aday arama; ardından `ortools` (rota + zaman/ekipman kısıtları).
- **Veri saklama:** `sqlite3` + JSON fixture dosyaları. Karmaşık mikroservis kullanma.
- **Hava:** Open-Meteo HTTP GET (opsiyonel canlı); her zaman çevrimdışı JSON fixture çalışmalı.
- **Test:** `pytest`; ağ ve matematik testleri, uçtan uca demo testi.

### Önerilen dosya ağacı

```text
siper-ai/
├── README.md
├── AGENTS.md                       # Bu ana plana kısa atıf
├── pyproject.toml
├── .gitignore
├── app.py                          # Streamlit giriş ekranı
├── src/siper/
│   ├── schemas.py                  # Tipler, veri doğrulama
│   ├── weather.py                  # Uyarı + tahmin + fixture
│   ├── network.py                  # Bağlantılı drenaj grafı
│   ├── vision.py                   # Görsel sınıf + güven + manuel düzeltme
│   ├── observations.py             # IoT / simüle telemetri ve kaynak bilgisi
│   ├── hydraulics.py               # SWMM adapter / proxy fallback
│   ├── risk.py                     # Bölge/varlık/eylem riskleri
│   ├── actions.py                  # Müdahale ve durum dönüşümü
│   ├── optimizer.py                # Kombinasyon seçimi + ekip/rota
│   ├── workflow.py                 # İş emirleri ve yeniden planlama
│   ├── evaluation.py               # Baseline karşılaştırmaları
│   └── storage.py                  # SQLite / JSON
├── data/
│   ├── fixtures/
│   │   ├── demo_network.json       # 8-12 unsur + bağlantı
│   │   ├── demo_weather.json       # ETİKET: sentetik yağış
│   │   ├── teams.json              # 2 veya 3 ekip
│   │   ├── actions.json
│   │   └── demo_images/            # Yalnız kullanılmasına izin verilen örnekler
│   ├── external/                   # .gitignore; büyük veri indirme
│   └── swmm/                       # Lisansı uygun örnek .inp
├── tests/
│   ├── test_network.py
│   ├── test_risk.py
│   ├── test_hydraulics.py
│   ├── test_optimizer.py
│   └── test_workflow.py
└── docs/
    ├── evaluation_results.md
    ├── limitations.md
    └── demo_script.md
```

**Donanım varsa (P1):** ESP32 + düşük voltajlı seviye/akış sensörü; MQTT veya seri porttan olay akışı. Bağlanmamışsa sadece `simulated_sensor` etiketi kullanılmalı. Donanım olmadan da tam P0 simülasyon demosu çalışmalıdır.

---

## 6. Veri setleri ve doğrulanmış başlangıç kaynakları

| Kaynak | Kullanım | Sınır / not |
|---|---|---|
| [MGM MeteoUYARI](https://www.mgm.gov.tr/meteouyari/turkiye.aspx) | Türkiye için resmî uyarı durumunu gözle doğrulama / operatör kaydı | Doğrulanmış resmî API olmadan otomatik çekildiği iddia edilmesin |
| [Open-Meteo Forecast API](https://open-meteo.com/en/docs) | Saatlik yağış ve olasılık dizisi | Uyarının resmî statüsünün yerine geçmez; atıf ve kullanım koşulları kontrol edilir |
| [Zenodo — Computer Vision Datasets for Visual Blockage Assessment at Culverts](https://zenodo.org/records/7623641) | Menfez tıkanıklığı için görüntü örnekleri / sınıflandırma | Yaklaşık 3,3 GB; tamamı yerine uygun alt küme; mazgal görüntüsü değildir |
| [US EPA SWMM](https://www.epa.gov/water-research/storm-water-management-model-swmm) | Hidrolojik/hidrolik senaryo ve müdahale karşılaştırması | İndirilebilir/yürütülebilir model gerek; kalibrasyonsuz gerçek şehir tahmini değildir |
| [SWMM 5.2 Inlet Clogging](https://usepa.github.io/Stormwater-Management-Model/d4/d4b/md__s_w_m_m__5_82_80.html) | Doğru tipte inlet için `Clogged` parametresi | Tüm boru/menfez/pompaya doğrudan uygulanmaz |
| [PySWMM](https://pyswmm.github.io/pyswmm/) | Python–SWMM entegrasyonu | Kurulum ve motor uyumluluğu ilk aşamada doğrulanmalı |
| [OR-Tools VRPTW](https://developers.google.com/optimization/routing/vrptw) | Ekip/araç rota ve zaman pencereleri | Rota optimizasyonu taşkın etkisini kendi başına hesaplamaz |

**Veri lisansları:** Her açık verinin lisansını ayrı kontrol et; kullanılmayan/yeniden dağıtılamayan görüntüleri GitHub deposuna yükleme. Büyük veri setini commit etme.

---

## 7. P0 — 24 saat sonunda MUTLAKA çalışan çekirdek

1. **Demo olay:** Şiddetli yağış senaryosu ve başlangıç zamanı; source etiketi görünür.
2. **Bağlı ağ:** Mazgal, menfez, kolektör, kanal, pompa, depolama ve çıkış içeren 8–12 düğümlü örnek drenaj grafı.
3. **Gözlem:** En az 2 fotoğrafa dayalı *görünür tıkanıklık* verisi; kalan varlıklar için açık etiketli senaryo/telemetri girdileri.
4. **Baz risk:** Müdahalesiz ağ senaryosu; bölgelerin ve varlıkların sıralanması.
5. **Eylemler:** En az 3 farklı müdahale türü; tüm ağdaki öncesi/sonrası etki hesabı.
6. **Ekip planı:** En az 2 ekip, sınırlı süre ve ekipman; uygulanabilir görev ve sıralama.
7. **İş emri akışı:** Bir görev tamamlandıktan ve yeni gözlem girildikten sonra riskin yeniden hesaplanması, yeni plan.
8. **Karşılaştırma:** En çok tıkalıyı önce, en yüksek yerel riskliyi önce ve SİPER AI planı aynı koşullarda kıyaslanır.
9. **Rapor:** Baseline ve önerilen planın modellenen etkisi; belirsizlik/sınırlar; `simulated` etiketi.
10. **Teslim:** GitHub'a hazır kod, kurulum komutları, 3 dakikalık canlı demo senaryosu ve test çıktısı.

**P1 — Ancak P0 bittiyse:** Canlı Open-Meteo entegrasyonu, SAM/YOLO, gerçek ESP32 sensörü, kapsamlı SWMM kalibrasyonu, çoklu yağış senaryosu, belirsizliğe duyarlı optimizasyon, ayrıntılı interaktif harita.

## 8. Uçtan uca demo akışı (hakem/jüri)

1. Operatör **“Şiddetli Yağış Uyarısı — Demo Senaryosu”** olayını açar. Kalan süre: örnek 120 dakika.
2. Ekranda bağlantılı drenaj ağı, varlık türleri, gözlem kaynakları ve sorunlar gösterilir.
3. Bir mazgal/menfez görüntüsü yüklenir; sistem sınıflandırma ve güven seviyesini gösterir; gerektiğinde kullanıcı sonucu düzeltir.
4. **“Müdahalesiz senaryo”** çalıştırılır: bölgesel risk/taşma göstergeleri kaydedilir.
5. **“Müdahale adaylarını simüle et”**: Örneğin mazgal temizliği, menfez açılması, pompa hazırlığı ayrı ayrı ve seçili kombinasyonlarda denenir.
6. **“Ekipleri planla”**: İki ekibe zaman ve ekipman kısıtlarını ihlal etmeyen görev dağılımı çıkar.
7. Bir iş emri tamamlanır ve yeni fotoğraf/durum girilir; sistem değişimin doğrulanmasını ve **yeniden planlamayı** yapar.
8. Son ekranda üç kontrol yaklaşımı karşılaştırılır; **gerçekçi bir iyileşme yoksa bunun nedeni de görünür**.

### UI sekmeleri

- `Durum Merkezi`: olay, kaynak, zaman, yağış şiddeti ve veri güveni.
- `Drenaj Ağı`: harita/graf, varlık türleri, bağlantılar.
- `Gözlem & AI`: fotoğraf, sınıf, güven, manuel doğrulama.
- `Risk & Senaryolar`: müdahalesiz ve müdahaleli ağ sonuçları.
- `Ekip Planlama`: ekipler, müdahale sırası, kaynak gereksinimleri.
- `Operasyon Takibi`: iş emirleri, tamamlanma, yeni gözlem, yeniden planlama.
- `Performans`: baseline karşılaştırması ve sınırlamalar.

---

## 9. Baseline deneyleri ve gerçekten ölçülecek başarı

### Aynı koşulda en az dört politika

- **B0:** Müdahale yok.
- **B1:** En yüksek görünür tıkanıklığı olanı önce seç.
- **B2:** En yüksek yerel/bölgesel risk puanını önce seç.
- **P:** SİPER AI; *bütün-ağ müdahale faydası + ekip/rota/zaman kısıtları*.

### Ölçümler

| Ölçüt | Birim veya yorum |
|---|---|
| Modellenen taşma hacmi | m³ (SWMM gerçekten üretiyorsa) |
| Kritik alanlarda taşkın göstergesi | sayısal değer ve kaynak |
| Planla önlenen modellenen etki | B0 - P; sadece aynı koşullarda |
| Tamamlanabilen müdahale sayısı | adet, süre limitine göre |
| Toplam yol ve çalışma süresi | dakika |
| Kaynak kısıtı ihlali | adet, hedef 0 |
| İş emri yeniden planlama süresi | saniye |
| Görsel model değerlendirme | precision/recall/F1; etiketli test varsa |
| Güvenilirlik / veri eskiliği | eksik veri ve şüpheli gözlem sayısı |

**Kabul edilmez değerlendirme:** Önceki farklı bir yağış ile sonraki farklı yağışı karşılaştırıp “%X seli önledik” demek; gerçek fotoğraf olmadan “kamerayla tespit ettik” demek; proxy indeksini m³ diye göstermek; simüle ekip görevinin gerçek sahada yapıldığını söylemek.

### Kritik deney: müdahale sinerjisi

İki altyapı unsurunun tek tek onarımı ile **birlikte** müdahalesini ayrı çalıştır. Ağ etkisinde fark varsa göster. İki müdahalenin faydası basitçe toplanmıyorsa SİPER AI'nın neden sadece tıkanıklık sıralaması yapmaması gerektiği görünür.

---

## 10. Kabul testleri (Codex, bunları kodla)

- `test_network_is_connected`: Demo drenaj ağı bağlı ve çıkış yoluna ulaşabilir; kopuk noktalar etiketlenir.
- `test_unknown_blockage_not_automatically_zero`: Görüntü okunamazsa “temiz” kabul edilmez, `unknown` olur.
- `test_visual_obstruction_not_equal_hydraulic_capacity`: Görüntü alan oranı hidrolik katsayıya otomatik kopyalanmaz.
- `test_risk_distinct_from_benefit`: En yüksek riskli varlığın otomatik en faydalı müdahale sayılması engellenir.
- `test_intervention_synergy`: Senaryo portföyü hesaplaması eylem faydalarını körlemesine toplamaz.
- `test_team_skills_and_equipment`: Yetkinliği olmayan ekip uygun olmayan göreve atanmaz.
- `test_deadline_respected`: Yağış başlangıç sınırını aşacak görev planı kabul edilmez veya açıkça “tamamlanamaz” denir.
- `test_assignment_no_duplicate_tasks`: Bir görev aynı anda iki ekipte bulunmaz.
- `test_completed_requires_verification`: Tamamlandı işaretlemek, doğrulanmış anlamına gelmez.
- `test_replanning_updates_remaining_jobs`: Yeni gözlem/eski görevin kapanması planı günceller.
- `test_simulation_labels`: Sentetik veriler, tahminler, ölçümler ve simülasyon sonuçları karıştırılmaz.
- `test_baselines_equal_conditions`: B0, B1, B2 ve P aynı yağış/ağ/ekip kısıtlarıyla karşılaştırılır.
- `test_no_hydraulics_no_fake_cubic_meters`: Proxy modu taşma hacmi (m³) üretmiş gibi sunulamaz.
- `test_weather_offline`: İnternet yokken fixture verisiyle demo açılır.
- `test_full_demo`: Uyarı → risk → müdahale seçimi → ekip planı → tamamlanma → doğrulama → yeniden planlama tek test akışı çalışır.

---

## 11. 24 saatlik geliştirme sıralaması ve durdurma kuralları

| Süre | Amaç | Bitmiş sayılma şartı |
|---|---|---|
| **0–2 saat** | Repo, bağımlılıklar, veri sözleşmeleri, sentetik ağ | Streamlit ekranı ve fixture yükleniyor |
| **2–5 saat** | Yağış olayı, ağ görüntüsü, varlık/sensör durumları | 8–12 unsur bağlanıyor, veri kaynağı etiketli |
| **5–9 saat** | İlk hidrolik baz ve müdahale adapteri | Aynı koşulda en az 2 farklı sonuç tekrar üretilebiliyor |
| **9–13 saat** | Risk kademeleri, eylem faydası, kombinasyon testi | En riskli ile en faydalı arasındaki fark görünür |
| **13–17 saat** | Ekip/ekipman/rota optimizasyonu | 2 ekip için süre kısıtlarına uyan plan |
| **17–20 saat** | İş emri + doğrulama + yeniden planlama | Tek tık/geri bildirim sonrası yeni plan oluşuyor |
| **20–22 saat** | Görsel model / manuel destekli gerçek görüntü akışı | Fotoğraf ve belirsizlikle çalışan analiz |
| **22–24 saat** | Baselines, testler, demo, README ve GitHub | Demo baştan sona kesintisiz; test raporu hazır |

**Durdurma kuralları:**

- 5. saate kadar ağ+olay akışı yoksa görüntü modeliyle uğraşma.
- 9. saate kadar SWMM entegrasyonu çalışmıyorsa proxy'yi devreye al ve **simülatör yetersizliğini açıkça işaretle**; SWMM'yi sonradan geri ekleyebilirsin.
- 13. saate kadar ağ etkisi hesaplanamıyorsa rota optimizasyonunu süs olarak ekleme; önce risk/eylem mantığını düzelt.
- 20. saate kadar otomatik CV yoksa manuel doğrulamalı görüntü işleme yaklaşımını kullan; doğruluk iddiası üretme.
- 22. saatten sonra yeni modül açma; sadece test, hata düzeltme ve sunum.

### 2 kişilik iş bölümü

**Geliştirici A:** `weather`, `vision`, `observations`, UI durum/gözlem ekranı, veri belgeleri ve CV testleri.
**Geliştirici B:** `network`, `hydraulics`, `risk`, `actions`, `optimizer`, `workflow`, teknik deneyler.
**Birlikte:** `app.py` entegrasyonu, karşılaştırmalı sonuçlar, demo, README ve GitHub.

---

## 12. Ürün ve etik sınırlar

- SİPER AI, başlangıçta bir **afet öncesi karar destek ve operasyon simülasyon prototipidir**; sertifikalı sel uyarı veya gerçek altyapı kontrol sistemi değildir.
- Gerçek belediye/altyapı konumları, personel hareketleri ve erişim bilgileri izin alınmadan işlenmez/yayımlanmaz. Demo için sentetik şehir ağı kullanılır.
- Gerçek sahada bakım gerektiren görevlerde yetkili ekip, ekipman ve iş güvenliği prosedürleri zorunludur.
- Su baskınlarının tamamı drenaj tıkanıklığından kaynaklanmaz; dere taşması, kıyı koşulları ve kapasite üzeri yağışlar için kapasite sınırını açıkla.
- API verisi yoksa kullanıcıya haber verilmeden sentetik veriye geçme; etiketle.
- Resmî MGM uyarıları ve üçüncü taraf yağış tahminleri farklı kaynak ve anlamlara sahiptir.
- Mümkün olmayan müdahaleyi “otomatik tamamlandı” yapma. Fiziksel operasyon başka, simüle durum geçişi başkadır.

---

## 13. Codex'ten beklenen son teslim listesi

- [ ] Python projesi ve `pyproject.toml`/kurulum talimatları.
- [ ] `python -m streamlit run app.py` ile çalışan Türkçe demo.
- [ ] Olay, ağ, gözlem, risk, plan, operasyon ve değerlendirme sekmeleri.
- [ ] En az 8 bağlı drenaj varlığı ve 3 farklı müdahale türü.
- [ ] Gerçek veya açıkça etiketli simüle görüntü/sensör girişi.
- [ ] Kaynağı belirtilmiş yağış olayları ve çevrimdışı demo.
- [ ] Müdahalesiz baz ve karşılaştırmalı müdahale senaryoları.
- [ ] En az iki ekibe uygun, zaman kısıtlı plan.
- [ ] İş emri kapatıldığında/doğrulandığında yeniden risk ve rota hesabı.
- [ ] Aynı senaryoda B0 / B1 / B2 / SİPER AI karşılaştırma tablosu.
- [ ] `pytest` testleri ve yürütülen testlerin gerçek çıktısı.
- [ ] Lisans/atıf ve gerçek/simüle veri sınırlarını açıklayan README.
- [ ] `docs/demo_script.md`: 3 dakikalık jüri gösterim akışı.
- [ ] `docs/evaluation_results.md`: Başarılar, başarısızlıklar, hesaplama süreleri, ölçülen değerler; veri yoksa boş/`not_measured`.

## 14. Codex'in ilk uygulama komutu

**Aşağıdaki komut gibi çalış (metin, terminal komutu değil):**

> Bu depodaki `SIPER_AI_CODEX_PROJE_PLANI.md` belgesini oku ve SİPER AI MVP'sini uygulamaya başla. Önce dosya ağacını ve fixture veri şemalarını kur. P0 özelliklerini dikey dilimler halinde geliştir; her dilimde çalışan arayüz ve test bırak. Meteorolojik olay, ağ, hidrolik adapter, risk, müdahale kombinasyonu, iki ekipli optimizasyon ve iş emri yeniden planlama zincirini kesintisiz çalıştır. Önceden yapılmamış test sonucu, yağış ölçümü, bilgisayarlı görü doğruluğu veya gerçek sel azaltımı uydurma. Bağımlılıklar çalışmazsa alternatif modülü açıkça etiketle ve geliştirmeye devam et. En sonunda çalıştırma adımlarını, test sonuçlarını ve hangi modüllerin gerçek/simülasyon olduğunu bildir.

---

## 15. Kaynak notları ve bilinen boşluklar

- **Şartname kaynağı:** Kullanıcının ilettiği `Ysil_Gelecek_Hackathonu_Bilgilendirme(3).docx`; dört resmî alt tema, jüri yüzdeleri, MVP/GitHub şartı. **Afet önlemeye izin verildiği** ayrıca kullanıcı tarafından aktarılmıştır.
- **MGM uyarıları:** `https://www.mgm.gov.tr/meteouyari/meteouyari-nedir.aspx`
- **Open-Meteo:** `https://open-meteo.com/en/docs`
- **Menfez görsel veri seti:** `https://zenodo.org/records/7623641` — yol mazgalı veri setiyle eşdeğer değildir.
- **EPA SWMM:** `https://www.epa.gov/water-research/storm-water-management-model-swmm`
- **PySWMM:** `https://pyswmm.github.io/pyswmm/`
- **OR-Tools:** `https://developers.google.com/optimization/routing/vrptw`

**Henüz kanıtlanmamış konular:** Yerel kentsel drenaj haritasının tamamına erişim; yeraltı hatları için gerçek kamera/sensör verisi; görüntüdeki görünür atığın hidrolik kapasiteye nicel etkisi; risk indeksinin saha validasyonu; gerçek belediye operasyonunda müdahale sonuçları; sistemi başka şehre genelleyebilme. Bunları gelecekteki çalışma alanı olarak koru; jüriye tamamlanmış gibi sunma.

---

**Tek cümlelik ürün özeti:** **SİPER AI, şiddetli yağış öncesinde bütün drenaj ağını birlikte değerlendirip hangi müdahale kombinasyonunun en fazla beklenen su baskını etkisini azaltacağını hesaplayan, belediye ekiplerini zaman ve kaynak kısıtlarına göre yönlendiren ve operasyonu yeniden ölçerek dinamik biçimde güncelleyen yapay zekâ destekli afet önleme platformudur.**

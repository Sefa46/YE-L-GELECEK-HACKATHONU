# SİPER AI

**Sel İçin Proaktif Erken Risk Yönetimi**, yaklaşan yağış öncesinde küçük bir drenaj ağındaki müdahale kombinasyonlarını karşılaştıran, ekip ve süre kısıtları altında iş planı oluşturan karar destek MVP'sidir.

> Bu depo bir afet öncesi operasyon **simülasyon prototipidir**. Küçük SWMM modeli fiziksel simülasyon çıktısı üretir; sentetik geometrisi saha kalibrasyonlu bir Trabzon sel tahmini değildir.

## Hızlı başlangıç

Python 3.11 kullanın:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,hydraulic]'
python -m streamlit run app.py
```

Testler:

```bash
source .venv/bin/activate
pytest
```

SWMM doğrulama sonuçlarını yeniden üretmek için:

```bash
source .venv/bin/activate
python scripts/run_swmm_validation.py
```

## Çalışan P0 zinciri

`Sentetik yağış → Kaynak etiketli gözlem → Bağlı drenaj ağı → SWMM doğrulaması + proxy karar modeli → Müdahale kombinasyonu → İki ekipli plan → İş emri → Yeni gözlemle doğrulama → Yeniden planlama`

- 10 bağlı varlık: mazgal, menfez, kolektör, açık kanal, depolama, pompa, boru ve çıkış.
- CC BY 4.0 lisanslı VHBD kaynağından 6 laboratuvar görüntüsü, galeri, yeni görüntü yükleme ve tıkanıklık bölgesi işaretleme ekranı.
- Görünür kapanma ile hidrolik kapasiteyi ayrı tutan veri sözleşmesi.
- Tekli faydaları körlemesine toplamayan kombinasyon simülasyonu.
- Yetkinlik, ekipman, yol ve 120 dakika sınırına uyan iki ekipli plan.
- `completed_pending_verification` ile `verified` durumlarını ayıran iş akışı.
- Aynı fixture ve kaynak koşullarında B0/B1/B2/SİPER AI karşılaştırması.
- EPA SWMM 5.2.4 ile aynı yağışta baz, tekli ve üçlü fiziksel múhale senaryosu.

## Veri ve model sınırları

| Bileşen | Gerçek durum | Kaynak etiketi |
|---|---|---|
| Yağış olayı | Çevrimdışı deterministik fixture | `synthetic_scenario` |
| Ağ ve sensörler | Sentetik şehir ağı | `synthetic_scenario` / `simulated_sensor` |
| Görseller | AI ile üretilmiş demo fixture; manuel etiket | `synthetic_scenario` |
| Görsel analiz | Renk-bölge tabanlı otomatik işaretleme + operatör doğrulaması | `heuristic_estimate` / `operator_input` |
| Ağ etkisi | Deterministik proxy indeks | `heuristic_estimate` |
| Saha eylemleri | Yalnız dijital durum dönüşümü | `synthetic_scenario` |
| SWMM / fiziksel m³ | Küçük sentetik model; saha kalibrasyonsuz | `hydraulic_simulation` |

Proxy sonuçlarının sabit etiketi **`HEURISTIC / NOT HYDRAULICALLY VALIDATED`** şeklindedir ve `overflow_volume_m3` alanı `None` kalır. Yalnız SWMM adapterinin sonucu fiziksel `m³` alanını doldurur.

## Proje yapısı

- `app.py`: Türkçe, yedi sekmeli Streamlit demo.
- `src/siper/`: veri sözleşmeleri, ağ, hava, proxy model, risk, eylem, optimizasyon ve iş akışı.
- `data/fixtures/`: çevrimdışı sentetik ağ, olay, ekip, eylem ve görseller.
- `data/fixtures/open_dataset/`: VHBD açık veri alt kümesi, sınıf kataloğu ve lisans atfı.
- `data/swmm/`: küçük SWMM ağı ve tekrar üretilebilir doğrulama sonuçları.
- `scripts/run_swmm_validation.py`: baz ve múhale koşullarını yeniden çalıştırır.
- `tests/`: plandaki P0 kabul testleri.
- `docs/demo_script.md`: üç dakikalık jüri akışı.
- `docs/evaluation_results.md`: ölçülen demo sonuçları ve gerçek durum tablosu.
- `docs/development_roadmap.md`: P0–P4 geliştirme sırası ve kabul durumu.
- `docs/limitations.md`: teknik ve etik sınırlar.

## Kaynaklar ve atıf

Gelecek doğrulama/entegrasyon çalışmaları için ana kaynaklar:

- [MGM MeteoUYARI](https://www.mgm.gov.tr/meteouyari/turkiye.aspx)
- [Open-Meteo Forecast API](https://open-meteo.com/en/docs)
- [US EPA SWMM](https://www.epa.gov/water-research/storm-water-management-model-swmm)
- [SWMM 5.2 dokümantasyonu](https://usepa.github.io/Stormwater-Management-Model/)
- [PySWMM](https://pyswmm.github.io/pyswmm/)
- [OR-Tools VRPTW](https://developers.google.com/optimization/routing/vrptw)
- [VHBD/SIC menfez tıkanıklığı veri seti](https://doi.org/10.5281/zenodo.7623641) — CC BY 4.0 lisanslı altı görüntülük alt küme kullanılır.

VHBD görüntüleri kontrollü hidrolik laboratuvarında kaydedilmiştir; Trabzon saha gözlemi veya model doğruluk kanıtı değildir. Büyük/harici veri `data/external/` altında Git dışında tutulur.

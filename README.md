# SİPER AI

**Sel İçin Proaktif Erken Risk Yönetimi**, yaklaşan yağış öncesinde küçük bir drenaj ağındaki müdahale kombinasyonlarını karşılaştıran, ekip ve süre kısıtları altında iş planı oluşturan karar destek MVP'sidir.

> Bu depo bir afet öncesi operasyon **simülasyon prototipidir**. Sertifikalı sel tahmini, gerçek belediye kontrol sistemi veya fiziksel taşma hacmi modeli değildir.

## Hızlı başlangıç

Python 3.11 kullanın:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m streamlit run app.py
```

Testler:

```bash
source .venv/bin/activate
pytest
```

## Çalışan P0 zinciri

`Sentetik yağış → Kaynak etiketli gözlem → Bağlı drenaj ağı → Heuristik etki hesabı → Müdahale kombinasyonu → İki ekipli plan → İş emri → Yeni gözlemle doğrulama → Yeniden planlama`

- 10 bağlı varlık: mazgal, menfez, kolektör, açık kanal, depolama, pompa, boru ve çıkış.
- İki yapay üretilmiş, açıkça `synthetic_scenario` etiketli görsel fixture.
- Görünür kapanma ile hidrolik kapasiteyi ayrı tutan veri sözleşmesi.
- Tekli faydaları körlemesine toplamayan kombinasyon simülasyonu.
- Yetkinlik, ekipman, yol ve 120 dakika sınırına uyan iki ekipli plan.
- `completed_pending_verification` ile `verified` durumlarını ayıran iş akışı.
- Aynı fixture ve kaynak koşullarında B0/B1/B2/SİPER AI karşılaştırması.

## Veri ve model sınırları

| Bileşen | Gerçek durum | Kaynak etiketi |
|---|---|---|
| Yağış olayı | Çevrimdışı deterministik fixture | `synthetic_scenario` |
| Ağ ve sensörler | Sentetik şehir ağı | `synthetic_scenario` / `simulated_sensor` |
| Görseller | AI ile üretilmiş demo fixture; manuel etiket | `synthetic_scenario` |
| Görsel analiz | Manuel operatör doğrulaması; otomatik CV yok | `operator_input` |
| Ağ etkisi | Deterministik proxy indeks | `heuristic_estimate` |
| Saha eylemleri | Yalnız dijital durum dönüşümü | `synthetic_scenario` |
| SWMM / fiziksel m³ | Yapılmadı | Sonuç üretilmez |

Proxy sonuçlarının sabit etiketi **`HEURISTIC / NOT HYDRAULICALLY VALIDATED`** şeklindedir. `overflow_volume_m3` alanı bilerek `None` kalır.

## Proje yapısı

- `app.py`: Türkçe, yedi sekmeli Streamlit demo.
- `src/siper/`: veri sözleşmeleri, ağ, hava, proxy model, risk, eylem, optimizasyon ve iş akışı.
- `data/fixtures/`: çevrimdışı sentetik ağ, olay, ekip, eylem ve görseller.
- `tests/`: plandaki P0 kabul testleri.
- `docs/demo_script.md`: üç dakikalık jüri akışı.
- `docs/evaluation_results.md`: ölçülen demo sonuçları ve gerçek durum tablosu.
- `docs/limitations.md`: teknik ve etik sınırlar.

## Kaynaklar ve atıf

Gelecek doğrulama/entegrasyon çalışmaları için ana kaynaklar:

- [MGM MeteoUYARI](https://www.mgm.gov.tr/meteouyari/turkiye.aspx)
- [Open-Meteo Forecast API](https://open-meteo.com/en/docs)
- [US EPA SWMM](https://www.epa.gov/water-research/storm-water-management-model-swmm)
- [SWMM 5.2 dokümantasyonu](https://usepa.github.io/Stormwater-Management-Model/)
- [PySWMM](https://pyswmm.github.io/pyswmm/)
- [OR-Tools VRPTW](https://developers.google.com/optimization/routing/vrptw)
- [Zenodo menfez tıkanıklığı veri seti](https://zenodo.org/records/7623641) — bu depoya indirilmemiştir.

Görsel fixture'lar yalnız demo içindir; gerçek saha gözlemi veya CV doğruluk kanıtı değildir. Büyük/harici veri `data/external/` altında Git dışında tutulur.

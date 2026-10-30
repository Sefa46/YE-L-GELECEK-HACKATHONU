# Değerlendirme sonuçları

## Deney koşulu

- Senaryo: `synthetic_high_rain_v1`
- Ağ: 10 düğüm, 9 bağlantı, tek çıkışa erişen çevrimsiz sentetik ağ
- Kaynak: `synthetic_scenario`
- Etki modeli: `heuristic_estimate`
- Model etiketi: `HEURISTIC / NOT HYDRAULICALLY VALIDATED`
- Ekip: 2
- Son zaman: 120 dakika
- Portföy sınırı: en fazla 3 müdahale
- Fiziksel taşma hacmi: `not_measured`

## Aynı koşullarda karşılaştırma

| Politika | Seçilen eylemler | Etki indeksi | Fayda indeksi | Kısıt ihlali |
|---|---|---:|---:|---:|
| B0 — Müdahale yok | — | 354.8095 | 0.0000 | 0 |
| B1 — Görünür tıkanıklık | A4, A2, A5 | 338.5432 | 16.2663 | 0 |
| B2 — Yerel risk | A6, A3, A1 | 232.9362 | 121.8733 | 0 |
| P — SİPER AI portföyü | A1, A2, A3 | 226.4531 | 128.3564 | 0 |

Bu ölçüm yalnız deterministik proxy indeksini karşılaştırır. Gerçek taşkın, ekonomik zarar veya önlenen m³ olarak yorumlanamaz. Bu fixture'da SİPER AI en düşük etki indeksini üretmiştir; saha genellemesi gösterilmemiştir.

## SWMM hidrolik doğrulaması

- Motor: EPA SWMM `5.2.4`, PySWMM `1.5.0`
- Birimler: `LPS`; raporlanan yüzey taşması `m³`
- Model: 8 hidrolik düğüm, 7 bağlantı, 3 alt havza
- Geometri ve yağış: sentetik, saha kalibrasyonu yok
- Koşul: her senaryoda aynı yağış ve aynı başlangıç modeli

| SWMM senaryosu | Eylemler | Yüzey taşması | Baza göre azalma | Süreklilik hatası |
|---|---|---:|---:|---:|
| Baz | — | 26.392 m³ | — | -1.695% |
| Menfez kesiti geri kazanımı | A3 | 5.309 m³ | 79.88% | -1.106% |
| Üç üst-hat kesiti geri kazanımı | A1, A2, A3 | 3.660 m³ | 86.13% | -1.013% |

Bu sayılar gerçek SWMM motorunun bu küçük model için ürettiği fiziksel simülasyon sonuçlarıdır. Sentetik geometri ve yağış nedeniyle Trabzon'da beklenen veya önlenen taşma hacmi olarak kullanılamaz. Ayrıntılı düğüm sonuçları `data/swmm/validation_results.json` dosyasındadır.

## Kombinasyon etkisi

`A1 + A3` birleşik müdahalesinin faydası ile iki tekli faydanın toplamı arasındaki fark `+21.5705` indeks puanıdır. Bu, proxy modelde portföy faydasının tekli faydaların düz toplamı olarak ele alınmadığını doğrular; fiziksel sinerji kanıtı değildir.

## Test sonucu

```text
22 passed
```

Test paketi yerel Python 3.11 ortamında çalıştırılmıştır.

## Gerçek durum tablosu

| Modül | Durum | Not |
|---|---|---|
| Veri sözleşmeleri ve fixture yükleme | Çalışıyor | Pydantic doğrulaması |
| Bağlı ağ ve çıkış erişimi | Çalışıyor | NetworkX, sentetik DAG |
| Çevrimdışı yağış olayı | Çalışıyor | Sentetik fixture |
| Görsel gözlem | Kısmi | Yüklenen görüntüde renk-bölge işaretleme + manuel doğrulama; öğrenilmiş model yok |
| Hidrolik etki | Çalışıyor | SWMM 5.2.4 küçük sentetik model + ayrı proxy fallback |
| Risk ve müdahale faydası | Simülasyon | Ayrı indeksler |
| Kombinasyon/sinerji hesabı | Çalışıyor | Senaryo karması + eylem kümesine göre bellek içi önbellek aktif |
| İki ekipli planlama | Çalışıyor | Deterministik sınırlı arama |
| İş emri ve yeniden planlama | Çalışıyor | Yeni operatör gözlemi zorunlu |
| Baseline karşılaştırması | Çalışıyor | Aynı fixture koşulları |
| Canlı Open-Meteo/MGM | Yapılmadı | P1 |
| SWMM/PySWMM | Çalışıyor | Fiziksel m³, düğüm taşması, derinlik ve süreklilik hatası üretiliyor |
| Öğrenilmiş CV modeli | Yapılmadı | Doğruluk metriği üretilmedi |
| Gerçek belediye/donanım bağlantısı | MVP kapsamı dışı | Sentetik görüntü, ağ ve operasyon akışı bilinçli demo tercihidir; dış sisteme komut gönderilmez |

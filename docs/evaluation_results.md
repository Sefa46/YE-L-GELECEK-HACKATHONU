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

## Kombinasyon etkisi

`A1 + A3` birleşik müdahalesinin faydası ile iki tekli faydanın toplamı arasındaki fark `+21.5705` indeks puanıdır. Bu, proxy modelde portföy faydasının tekli faydaların düz toplamı olarak ele alınmadığını doğrular; fiziksel sinerji kanıtı değildir.

## Test sonucu

```text
16 passed in 0.18s
```

Test süresi yerel Apple Silicon makinedeki tek çalıştırmadan alınmıştır; performans garantisi değildir.

## Gerçek durum tablosu

| Modül | Durum | Not |
|---|---|---|
| Veri sözleşmeleri ve fixture yükleme | Çalışıyor | Pydantic doğrulaması |
| Bağlı ağ ve çıkış erişimi | Çalışıyor | NetworkX, sentetik DAG |
| Çevrimdışı yağış olayı | Çalışıyor | Sentetik fixture |
| Görsel gözlem | Kısmi | Görsel + manuel etiket; otomatik CV yok |
| Hidrolik etki | Simülasyon | Heuristik proxy; SWMM değil |
| Risk ve müdahale faydası | Simülasyon | Ayrı indeksler |
| Kombinasyon/sinerji hesabı | Çalışıyor | Proxy senaryo önbelleği henüz yok |
| İki ekipli planlama | Çalışıyor | Deterministik sınırlı arama |
| İş emri ve yeniden planlama | Çalışıyor | Yeni operatör gözlemi zorunlu |
| Baseline karşılaştırması | Çalışıyor | Aynı fixture koşulları |
| Canlı Open-Meteo/MGM | Yapılmadı | P1 |
| SWMM/PySWMM | Yapılmadı | Proxy fallback aktif |
| Öğrenilmiş CV modeli | Yapılmadı | Doğruluk metriği üretilmedi |
| Gerçek belediye/donanım bağlantısı | Yapılmadı | Yetkisiz komut yok |

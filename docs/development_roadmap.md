# Öncelikli geliştirme planı

Bu sıra, sonraki geliştirme kararları için ana öncelik listesidir. Bir aşamanın kabul koşulları tamamlanmadan sonraki aşama ana geliştirme konusu yapılmaz.

## P0 — SWMM hidrolik doğrulaması

**Durum:** Tamamlandı

- EPA SWMM 5.2.4 ile küçük sentetik fiziksel drenaj modeli çalışıyor.
- Baz, tekli múhale ve üçlü múhale aynı yağış altında karşılaştırılıyor.
- Taşma hacmi, düğüm taşması, maksimum derinlik ve süreklilik hatası kaydediliyor.
- Proxy model ayrı fallback olarak korunuyor.
- Desteklenmeyen múhale, etkiliymiş gibi sessizce uygulanmıyor.

## P1 — Yağış öncesi / aktif olay modları

**Durum:** Sıradaki

- Hazırlık, aktif yağış ve olay sonrası modlarını ayır.
- Kalan süre bir bakım görevine yetmediğinde sistemi boş bırakma.
- Güvenli kısa işler, gözlem, bariyer/erişim kontrolü ve ekip konumlandırma gibi uygulanabilir kararlar üret.
- Mod geçişlerini ve zaman kısıtlarını test et.

## P2 — Görüntü analizi

**Durum:** Bekliyor

- Lisansı doğrulanmış gerçek görüntü kümesi kullan.
- Otomatik tıkanıklık tahmini, `unknown` sonucu ve operatör düzeltmesini destekle.
- Ayrı test kümesinde hata matrisi, precision, recall ve F1 raporla.
- Görünür kapanmayı hidrolik kapasiteye doğrudan kopyalama.

## P3 — Çok senaryolu karşılaştırma

**Durum:** Bekliyor

- Düşük, orta ve yüksek yağış senaryolarını aynı ağda çalıştır.
- SİPER AI, görünür tıkanıklık ve yerel risk politikalarını SWMM taşma hacmiyle karşılaştır.
- Sonuçları senaryo bazında ve toplu olarak raporla.

## P4 — Meteorolojik veri entegrasyonu

**Durum:** Bekliyor

- Gerçek zamanlı tahmin ile sentetik senaryoyu veri kaynağına göre ayır.
- Open-Meteo verisini zaman damgası ve erişim hatası yönetimiyle al.
- Resmî MGM uyarısını yalnız doğrulanmış kayıt veya operatör girdisiyle göster.
- Ağ erişilemezse çevrimdış fixture ile uygulamayı çalışır tut.

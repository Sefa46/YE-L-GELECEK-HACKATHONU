# Sınırlar ve güvenli kullanım

- Ağ, yağış, sensör, kapasite ve ekip süreleri sentetiktir.
- Proxy model fiziksel hidrolik denklemler içermez ve karar akışında ayrı fallback olarak kullanılır.
- SWMM modeli fiziksel denklemler ve sentetik boru geometrisi kullanır; arazi/saha verisiyle kalibre edilmemiştir ve gerçek Trabzon taşkın tahmini değildir.
- Etki ve fayda değerleri göreli demo indeksleridir; m³, olasılık, ekonomik zarar veya gerçek sel azaltımı değildir.
- Görsel ekrandaki otomatik maske, renk-bölge tabanlı başlangıç işaretlemesidir. Öğrenilmiş bilgisayarlı görü modeli ve bağımsız doğruluk değerlendirmesi henüz yoktur.
- Görünür kapanma oranı hidrolik kapasiteye otomatik dönüştürülmez.
- MGM uyarısı otomatik çekilmez ve sentetik olay resmî uyarı olarak gösterilmez.
- `apply`/doğrulama akışı dijital ikiz durumunu değiştirir; fiziksel pompa, vana, alarm veya ekibe komut göndermez.
- Gerçek belediye veya donanım entegrasyonu bu hackathon MVP'sinin hedefi değildir; uçtan uca akış sentetik görüntü, ağ ve operasyon verisiyle gösterilir.
- Gerçek kullanım için mevcut SWMM modelinin saha geometrisi ve gözlemleriyle kalibrasyonu, yetkili veri erişimi, güvenlik prosedürleri ve insan onayı gerekir.

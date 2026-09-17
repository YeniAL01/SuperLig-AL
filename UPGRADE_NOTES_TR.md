# Yapılan geliştirmeler — 17 Eylül 2026

## Teslim edilen sürüm
adaptive-v2: çevrimiçi model ağırlıklandırma, gerçek sonuç hafızası ve kronolojik değerlendirme.

## Düzeltilen sorunlar
- PredictionEngine içindeki çalışmayı engelleyen girinti hataları kaldırıldı.
- Eski yardımcı motorlardaki eksik veri sınıfı parametreleri tamamlandı.
- Ev/deplasman toplam gollerini ikiye bölerek takım formu hesaplama kaldırıldı.
- Varsayılan xG/Elo değerleriyle bağımsız güçlü sinyal varmış izlenimi giderildi.
- Veri yeterlilik puanının maç olasılığı gibi gösterilmesi kaldırıldı.
- Öğrenme artık yalnızca başarı sayacı değil: gerçekleşen sonuç, her alt modelin
  olasılık hatasına göre sonraki model ağırlıklarını etkiliyor.
- Yayınlanmayan tahminler de kaydediliyor; seçilim yanlılığı izlenebiliyor.
- Başarılı çalışmada maç sayısının CLI hata koduna dönüşmesi düzeltildi.
- Eksik environment.yml kullanan eski CI, Python 3.12 test işine dönüştürüldü.
- Canlı FotMob scoreStr alanı desteklendi; iki farklı lig yanıt şeması test edildi.
- Bozuk JSON'un boş hafıza olarak yorumlanması kaldırıldı.
- Aynı maçı yeniden öğrenmeye karşı kimlik bazlı koruma ve kayıt tutarlılığı eklendi.
- Tahmin/öğrenme/rapor işlerinde ortak GitHub concurrency grubu eklendi.
- Test komutu salt okunur önizlemeye dönüştürüldü; sahte başarı yüzdesi üretmiyor.

## Kontroller
- 20 test geçti.
- Tüm Python dosyaları compileall ile derlendi.
- Canlı FotMob uçtan 306 fikstür ve 45 tamamlanmış sonuç okundu.
- 9 yaklaşan maçta salt okunur önizleme çalıştı; Telegram'a mesaj gönderilmedi.
- Zaman sızıntısı, aynı anda başlayan maçlar, tekrar öğrenme, eksik xG,
  olasılık toplamı, kayıt bozulması ve CLI çıkış kodu test edildi.
- Windows çalışma ortamında geçici klasörlere 0700 izni uygulayan test aracı
  erişim hatası verdiğinden yerel test başlatıcısı klasör oluşturmayı 0777 ile
  çalıştırdı. Bu ortam uyarlaması teslim edilen uygulama koduna eklenmedi.
- GitHub Actions işleri burada uzakta çalıştırılmadı.
- Gerçek tahmin doğruluğu veya eski sürüme göre doğruluk artışı kanıtlanmadı.

## Başlangıç verisi
data/results.json içindeki 45 sonuç sağlayıcıdan alınmıştır; doğru oldukları ikinci
bir kaynaktan karşılaştırılmamıştır. İlk görülme zamanları saklanmıştır.
Bu sonuçlar takım özelliklerini başlatır. Henüz maç öncesi tahmin/sonuç eşleşmesi
olmadığından öğrenilmiş model ağırlıkları başlangıçta eşittir.

## Sınırlar ve sonraki geliştirme
- Elo, son 10 maç formu ve Poisson temel modellerdir; gelişmiş oyuncu/sakatlık,
  transfer, kadro kalitesi, gerçek xG veya piyasa oranı özellikleri bağlı değildir.
- Olasılık kalibrasyonu güvenilirlik gruplarında ölçülür; ayrı bir eğitilmiş
  kalibrasyon modeli bu ilk sürümde yoktur.
- Maç tarihi, takım adı ve kimlik tutarlılığı veri kaynağına bağlıdır.
- İlk 5 maçlık düşük kapsamla başlayan model, %58 eşiğini geçmeyebilir.
  Daha çok mesaj için eşiği düşürmek doğruluk artışı anlamına gelmez.
- Sonraki önemli adım birkaç sezonluk temiz geçmiş veri ile ayrı geliştirme/test
  dönemleri üzerinde karşılaştırmalı değerlendirmedir.


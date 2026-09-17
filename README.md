# SuperLig-AL — adaptive-v2

Süper Lig maçları için maç öncesi olasılık tahmini ve sonuçlardan öğrenme.
Bu sürüm yüksek doğruluk garantisi vermez. Gerçek tahmin başarısı henüz ölçülmedi.
Paketin başlangıç verisi, 17 Eylül 2026'da FotMob'dan alınan 45 tamamlanmış maçtır.
Bu maçlar takım formunu/Elo'yu başlatır; tahmin başarısı olarak sayılmaz.

## Kurulum

Python 3.12 önerilir (en az 3.11).

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q
python main.py test
```

`test` salt okunur önizlemedir. Telegram'a göndermez, rastgele sonuç üretmez ve
üretim tahminlerini/öğrenme kayıtlarını değiştirmez.

## Çalıştırma

```bash
python main.py predict
python main.py learn
python main.py metrics
```

- predict: T-15 ile başlama zamanı arasında bir kez tahmin kilitler.
  %58 model olasılığı ve her iki takım için en az 5 geçmiş maç şartını sağlayanları yayınlar.
  Eşik Settings.minimum_probability içinde değiştirilebilir; doğruluk garantisi değildir.
- learn: bitmiş sonuçları eşleştirir, performans ve model ağırlıklarını günceller.
- metrics: tüm tahminlerin ve yayınlananların başarısını, kapsama oranını, log loss,
  Brier skoru, güvenilirlik gruplarını ve yaklaşık %95 isabet aralığını gösterir.
- report.py: mevcut PNG raporunu üretip Telegram rapor botuna gönderebilir.

Telegram için TELEGRAM_PREDICTION_BOT_TOKEN / TELEGRAM_PREDICTION_CHAT_ID,
rapor için TELEGRAM_REPORT_BOT_TOKEN / TELEGRAM_REPORT_CHAT_ID ortam değişkenlerini
veya GitHub Secrets değerlerini kullanın. Sırlar dosyaya yazılmaz.
Bu paketin hazırlanması sırasında Telegram mesajı gönderilmedi.

## Nasıl öğrenir?

1. Tamamlanmış maçlardan son 10 maçın atılan/yenen gol ortalamaları ve Elo hesaplanır.
   Hiç gol atılmamışsa 0 korunur; ev/deplasman perspektifi karıştırılmaz.
2. Poisson, Elo ve sabit lig önseli HOME/DRAW/AWAY dağılımları üretir.
   Eksik xG uydurulmaz. Gerçek xG verisi bağlanana kadar üretimde xG kullanılmaz.
3. Maç öncesi tüm model olasılıkları, ağırlıklar, zamanlar ve sürüm saklanır.
   Yayın eşiğine takılan tahminler de forecasts.json içinde gölge kayıt olarak tutulur.
4. Gerçek sonuç geldiğinde her modelin log loss hatası ölçülür. Daha düşük hatalı
   modellerin etkisi artar. Son 300 uygun tahmin, zaman ağırlığı ve 20 gözlemlik
   önsel kullanılır; küçük örneklemlerde sert değişiklikler sınırlandırılır.
5. Her maç bir kez değerlendirilir. Gelecekte bilinen sonuçlar geçmiş tahmine giremez.
   Eski sürüm kayıtları yeni model ağırlıklarını eğitmez.

Bu bir çevrimiçi model ağırlıklandırma sistemidir; kendi kaynak kodunu değiştirmez.
Gösterilen yüzde modelin sonuç olasılığıdır; henüz saha verisinde kalibre edilmiş
başarı oranı değildir. İlk 11 bilgisi sadece doğrulama bayrağıdır; oyuncu etkileri
modellenmediğinden olasılığa keyfî bonus verilmez. Tahmini skor, seçilen sonuçla
uyumlu en olası skordur; toplamda en olası kesin skor farklı olabilir.
score_probability bu koşulla seçilen skorun koşulsuz model olasılığını saklar.

## Geçmiş veri ve dürüst test

CSV sütunları (UTF-8):

```text
fixture_id,home_team,away_team,kickoff,home_goals,away_goals,available_at
```

kickoff/available_at saat dilimli ISO-8601 olmalıdır.
available_at sonucun bilinir olduğu zamandır. Yoksa başlama +3 saat varsayılır;
gecikme/yarıda kalma bulunan maçlarda gerçek zaman girilmelidir. Yalnızca tarih
biliniyorsa kickoff için o gün 00:00, available_at için ertesi gün 00:00 kullanın;
bu aynı gün içindeki maçlar arasında sonuç sızıntısını önler.
Takım adları kaynaklar arasında tutarlı olmalıdır. FotMob ile birleştirilecek
satırlarda FotMob maç kimliğini kullanın; kimlik çatışmaları otomatik ezilmez.

```bash
python main.py backtest --csv historical.csv --output reports/backtest.json
python main.py import-history --csv historical.csv
```

Backtest maçları tarih sırasıyla, T-15'te elde bulunan bilgilerle tahmin eder;
sonradan gelen sonuçlar sadece sonraki tahminleri etkiler. Canlı kayıtları değiştirmez.
Rapor sabit ev sahibi önseliyle aynı maçlar üzerinde karşılaştırma yapar.
Başlangıçtaki az verili maçlar da tüm-maç metriğinde tutulur; yayınlanan alt küme
ayrıca raporlanır. Test verisine bakıp eşik/parametre seçmek ölçümü iyimser yapar;
parametre geliştirme için ayrı geçmiş dönem, son değerlendirme için dokunulmamış
sezon ayırın. Güven aralıkları maçların bağımsızlığı varsayımıyla yaklaşık hesaplanır.

Paketteki results.json verileri ilk görüldükleri zamanla işaretlidir. Bunları
geçmişte biliniyormuş gibi geriye taşıyıp başarı iddiasında bulunmayın.
Gerçek geçmiş değerlendirmesi için yukarıdaki zaman bilgileri olan CSV gerekir.

## Kayıtlar ve işletim sınırları

- results.json: doğrulanmış sonuçlar ve bilgiye erişim zamanı.
- forecasts.json: tüm değiştirilemez maç öncesi tahminler.
- predictions.json: yayın koşullarını karşılayan tahminler.
- performance.json: tahminlerle eşleşen gerçek sonuçlar.
- model_state.json / metrics.json / memory.json: yeniden üretilebilir özetler.
- delivery.json: başarılı Telegram gönderimleri.

Bozuk JSON'da sistem sessizce sıfırlanmaz; hata vererek durur.
GitHub tahmin/öğrenme/rapor işlerinde ortak concurrency grubu yazmaları sıraya koyar.
Başarılı CLI komutları maç sayısından bağımsız 0 çıkış kodu döndürür.
Yerelde aynı data klasörüne aynı anda birden fazla süreç çalıştırmayın.
GitHub zamanlayıcısı T-15 çalışmasını garanti etmez; dakikalık sunucu zamanlayıcısı
daha uygundur. FotMob API resmî SLA sunmaz; şema değişiklikleri izlenmelidir.
45 sonuç ve 306 sezon fikstürü bu sürüm hazırlanırken canlı uçtan okunmuştur.

Gönderim hatasında kayıtlı tahmin başlama zamanına kadar yeniden denenir.
Telegram başarılı gönderimden hemen sonra süreç çökerse tekrar mesaj mümkün olabilir;
Bot API üzerinden tam olarak bir kez teslim garantisi yoktur.
T-18 yedek penceresi kaldırıldı; T-15 sırasında maç ayrıntısı alınamazsa kayıtlı
sonuç geçmişiyle tahmin yapılır. Eski xG/Form/ensemble modülleri uyumluluk için
korunmuştur; üretim hattı yeni PredictionEngine kullanır.


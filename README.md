# SuperLig-AL

Trendyol Süper Lig için yalnızca yüksek güvenli maç tahminleri üreten, GitHub Actions uyumlu Python uygulaması.

## Kurulum

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
python main.py predict
python main.py learn
python report.py
```

Telegram gönderimi için GitHub Secrets içinde `TELEGRAM_PREDICTION_BOT_TOKEN`, `TELEGRAM_PREDICTION_CHAT_ID`, `TELEGRAM_REPORT_BOT_TOKEN` ve `TELEGRAM_REPORT_CHAT_ID` tanımlayın. Uygulama bu değerler yoksa mesajı güvenle atlar.

`data/` çalışma sırasında oluşur ve GitHub Actions tarafından depoya geri yazılır; böylece tahmin kilidi, performans geçmişi ve hafıza sonraki çalışmalar arasında korunur. Actions için `contents: write` izni bu nedenle gereklidir.

## İlkeler

Uygulama resmî ilk 11'i doğrulayamıyorsa T-18'de güven cezası uygular. T-15'ten sonra aynı maç için yayınlanmış tahmin değiştirilmez. Yetersiz veri, tahmin üretmek yerine açıkça kayda alınır.

GitHub'ın zamanlanmış iş başlatma gecikmesi kesin zaman garantisi vermez. Daha dar bir T-15 operasyonel garantisi gerekirse aynı komutu dakikalık çalışan bir sunucu zamanlayıcısında da yürütün.

## Komutlar

- `python main.py predict`: yaklaşan karşılaşmaları kontrol eder ve kilit zamanındaki tahminleri yayınlar.
- `python main.py learn`: bitmiş karşılaşmaları sonuçlarla eşleştirip performans ve hafızayı günceller.
- `python report.py`: son tamamlanan haftanın PNG raporunu üretir ve rapor botuyla yollar.

Veri sağlayıcıları: FotMob'un herkese açık skor/maç uçları ve Open-Meteo. Sağlayıcı sözleşmeleri değişebileceğinden hata yönetimi veri eksikliği halinde muhafazakâr davranır.

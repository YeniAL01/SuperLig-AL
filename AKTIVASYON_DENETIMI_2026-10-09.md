# SuperLig-AL | Uçtan uca aktivasyon denetimi

**Tarih:** 9 Ekim 2026 (Türkiye saati)  
**Kapsam:** Kullanıcının yüklediği `SuperLig-AL-main.zip` içeriği; 90 ZIP girdisi, Python uygulaması, JSON durum kayıtları, 4 GitHub Actions iş akışı, tahmin/öğrenme/raporlama zinciri.  
**Durum:** Çevrimdışı kod ve veri denetimi tamamlandı. Canlı GitHub Actions, repo secrets/variables, Telegram ve FotMob API erişimi doğrulanmadı. **Otomasyon etkinleştirilmedi.**

## Karar

**Doğruluk iddiasıyla koşulsuz üretim aktivasyonunu önermiyorum.** Sistem kod olarak çalışabiliyor, fakat tarihsel örneklem ve karşılaştırmalı ölçümler modelin üstünlüğünü kanıtlamıyor. Hatalar giderilmiş ZIP, güvenli bir dağıtım adayıdır; canlı erişim ve yayın politikası kontrolü olmadan üretim onayı değildir.

## 1. Mevcut kanıtlar: başarı ve referans karşılaştırması

| Ölçüm | Sonuç | Yorum |
|---|---:|---|
| Saklanan tamamlanmış lig maçı | 54 | İlk 45 maçın ilk gözlenme tarihi 17 Eylül; tahmin başarısı sayılmaz. |
| Gerçek maç öncesi tahmin | 9 | 18–20 Eylül 2026. |
| Telegram'a başarılı teslim | 8/9 | 1 maç gölge kayıt. |
| 1X2 isabeti, tüm tahminler | 6/9 = %66,7 | **9/9 seçim HOME.** |
| 1X2 isabeti, teslim edilenler | 6/8 = %75,0 | Seçilmiş küçük örneklem; başarı garantisi değil. |
| Daima HOME referansı | 6/9 = %66,7 | Model, bu referansı isabette geçmiyor. |
| Model 1X2 log loss | 0,99384 | Daha düşük iyidir. |
| Sabit lig önseli log loss | 0,96474 | Modelden daha düşük (daha iyi). |
| Model 1X2 Brier | 0,59290 | Daha düşük iyidir. |
| Sabit lig önseli Brier | 0,57158 | Modelden daha düşük (daha iyi). |
| 2,5 Alt/Üst isabeti | 7/9 = %77,8 | 8/9 OVER seçimi; çok küçük örneklem. |
| KG Var/Yok isabeti | 3/9 = %33,3 | 9/9 YES seçimi; ortalama güven %59,78. |
| Kaydedilen 1X2 güvenleri | %40,41–%47,47 | 9/9 tahmin %58 eşiğinin altında. |
| Kaydedilen tam skor isabeti | 0/9 | Kesin skor tahmininde kanıt yok. |
| Son öğrenme durumu | 23 Eylül 2026 | Yüklenen arşiv bu tarihte kalmış. |

**Önemli:** `backtest` komutu mevcut 54 maç üzerinde 54/54 HOME tahmini ve %48,15 1X2 isabeti üretiyor; daima HOME referansı da %48,15. Ancak ilk 45 maçın `available_at` alanı 17 Eylül olduğundan geçmişte bunların bilinmediği varsayılıyor. Bu geriye dönük koşu **güncel üretim kalitesini ölçen geçerli bağımsız test olarak yorumlanamaz**. Modelin yön seçimi ve veri kapsamı sorunlarını teşhis etmek için kullanılabilir.

## 2. Üretim zinciri

1. **FotMob:** `collectors/fotmob.py` lig fikstürlerini ve bitmiş maçları topluyor. Şema uyumsuzluğunda hata veriyor; JSON bozuksa sessiz sıfırlama yok.
2. **Sonuç geçmişi:** `learning/history.py` maçları kimlikle birleştiriyor; sağlayıcı skor düzeltmelerini `result_conflicts.json` içine ayırıyor. `available_at` filtrelemesi maç sonrası veri sızıntısını sınırlandırıyor.
3. **Takım özellikleri:** Son 10 maçın gol/form ortalaması ve Elo. xG, sakatlık, gerçek kadro oyuncu etkisi, piyasa oranları **bağlı değil**.
4. **Tahmin:** Poisson + Elo + sabit lig önseli; 1X2, Alt/Üst 2,5 ve KG. Öğrenme öncesi ağırlıklar eşit. İlk 11 bilgisi oyuncu bazlı modele girmiyor.
5. **Yayın:** Tahmin ve gönderim rezervasyonu JSON'a yazılıyor; ayrı `deliver` adımı Telegram PNG gönderiyor. Başarısız gönderim sonraki tahmin işinde tekrar denenebiliyor. Telegram tarafında mutlak exactly-once garantisi yok.
6. **Öğrenme:** Sonuç geldikçe performans ve adaptif faktörler güncelleniyor. 28 gün gözlem, en az 20 değerlendirme ve 30 uyarlama örneği gerekiyor. 9 örnekle adaptasyon henüz devrede değil.
7. **Rapor:** Son tamamlanan haftanın görsel raporu üretiliyor ve rapor botuna gönderiliyor. Görsel üretimi çevrimdışı başarıyla denendi.

## 3. Bulunan kritik riskler ve durum

| Önem | Bulgu | Dosya/yer | Durum |
|---|---|---|---|
| Kritik | Aynı sonuç kümesiyle her `learn` çağrısında ağırlıklar yeniden kayabiliyordu. Deney: 1,00 → 0,95 → 0,9025 → 0,8574. | `learning/adaptive.py` | **Düzeltildi; örnek kümesi anahtarı ile idempotent.** |
| Yüksek | `learning.yml` farklı concurrency grubu kullandığı için `predict`/`report` ile aynı `data/` klasörüne eşzamanlı commit/push riski vardı. | `.github/workflows/learning.yml` | **Düzeltildi.** |
| Yüksek | 11 tahmini oyuncu, resmî ilk 11 olarak doğrulanabiliyordu. | `app/service.py::_lineup_verified` | **Düzeltildi: lineupType doğrulaması.** |
| Yüksek | GitHub cron gecikince üç kadro sorgusu tamamlanmadan maç başlayabilir, hiç tahmin çıkmayabilirdi. | `app/service.py::run` | **Son 15 dakika fallback eklendi.** Cron hiç çalışmazsa hâlâ garanti yok. |
| Orta | Test önizlemesi kayıtlı `learning_state.json` kullanmadığından üretimle farklı sonuç gösterebilirdi. | `app/test_run.py` | **Düzeltildi.** |
| Yüksek | Görselde tahmin güveni “Başarı Oranı” olarak sunuluyordu; gerçek ölçülmüş başarı değil. | `reporting/prediction_table.py` | **“Tahmin Güveni” olarak düzeltildi.** |
| Kritik / politika | Canlı servis **tüm** oluşturulan tahminleri yayınlıyor; %58 ve en az 5 maç filtresi uygulanmıyor. Eski README ve backtest aksi yöndeydi. | `app/service.py:342–360`, `learning/backtest.py:30`, `config/settings.py` | **Davranış korunarak açıkça belgelendi; karar bekliyor.** |
| Yüksek / model | KG tahmini 9/9 YES; isabet 3/9. Oyuncu, sakatlık, gerçek xG ve odds bilgisi yok. | `prediction/engine.py`, `learning/history.py` | **Çözülmedi; model geliştirme + bağımsız test gerekli.** |
| Yüksek / altyapı | Gerçek repo `AUTOMATION_ENABLED` değişkeni, Telegram secrets, GitHub Actions geçmişi ve canlı FotMob şeması görülemedi. | GitHub ve dış servisler | **Canlı kontrol bekliyor.** |
| Orta / uyumluluk | Repo kökündeki `prediction.yml` GitHub Actions tarafından kullanılmayan eski taslak; aktif iş `.github/workflows/prediction.yml`. | `prediction.yml` | **Silinmedi; yanlış dosyanın düzenlenmemesi için not edildi.** |
| Orta / entegrasyon | FotMob gayriresmî uç noktalarının servis ve kullanım koşulları dış bağımlılık riski taşıyor. | `collectors/fotmob.py` | **İzin/erişim doğrulaması gerekli.** |

## 4. Uygulanan düzeltmeler

- `learning/adaptive.py`: aynı veriyle ikinci kez faktör veya kalibrasyon güncellemesi yapılmaz; yeni sonuç geldiğinde bir kez uyarlanır. Tekrarlanan review/audit kayıtları da engellendi.
- `.github/workflows/learning.yml`: `superlig-state` ortak concurrency grubu.
- `app/service.py`: `lineupType` `standard` veya `confirmed` değilse 11 oyuncu tek başına resmî ilk 11 sayılmaz; GitHub gecikmesinde T-15 emniyet fallback'i.
- `app/test_run.py`: önizleme, üretimdeki kayıtlı öğrenme durumunu kullanır.
- `reporting/prediction_table.py`: kanıtlanmamış başarı iddiaları kaldırıldı.
- `README.md`: gerçek canlı yayın politikası, kayıtlı 9 maçlık performans ve operasyon sınırları güncellendi.
- `tests/test_readiness.py`: yeni regresyon testleri eklendi.

**Değiştirilmedi:** 1X2/Alt-Üst/KG model formülleri, %58 yayın eşiğinin canlıya uygulanması, eski tahmin/performance JSON'ları, Telegram erişimi, GitHub repository ayarları. Geçmiş tahminleri yeniden yazmadım.

## 5. Gerçekleştirilen kontroller

- İlk ZIP: `pytest`: **51/51** geçti.
- Düzeltilmiş kopya: `pytest`: **56/56** geçti.
- `compileall`: başarılı.
- Resmî/tahmini ilk 11 ayrımı, son 15 dakika fallback'i, ortak concurrency, test/üretim öğrenme durumu ve tekrarlı öğrenme için regresyon testleri eklendi.
- 8 kaydedilmiş Telegram tahmininden 4'üyle gerçek PNG üretildi; 9 kayıtla haftalık rapor PNG'si üretildi. Her iki PNG okunabildi. **Hiçbir Telegram API isteği yapılmadı.**
- 54 maçlık tarihsel backtest ve 9 gerçek tahminin basit referansla karşılaştırması yapıldı. Başarı garantisi çıkarılmadı.
- Canlı FotMob bağlantısı, Telegram teslimi, GitHub cron gecikmesi, GitHub Secrets/Variables ve repo üzerindeki son sürüm doğrulanamadı. Bunlar test edilmiş gibi gösterilmemelidir.

## 6. Aktivasyon öncesi zorunlu kararlar

1. **Yayın politikası:** Mevcut davranış tüm maçları düşük güvenle de Telegram'a gönderir. Alternatif: yalnızca minimum güven ve minimum örnek sayısını geçenleri yayınlamak, diğerlerini `forecasts.json` içinde gölge tahmin olarak saklamak. Ancak geçmişteki 9 tahminin hiçbiri %58'i geçmiyor; eşik, doğruluk artışı kanıtı değildir.
2. **Model geçerliliği:** Birkaç sezonluk zaman damgalı maç verisiyle dönemsel walk-forward değerlendirme; her pazar için 1X2, KG, Alt/Üst baz çizgileri, log loss/Brier/kalibrasyon ve tahmin yönü dağılımı. 9 maç üzerinden optimizasyon yapılmamalı.
3. **GitHub canlı kontrolü:** Doğru repository/default branch, `AUTOMATION_ENABLED=true`, Prediction/Learning/Weekly Report workflow etkinliği, doğru Telegram secrets, write permission, GitHub Actions cron ve push logları doğrulanmalı.
4. **Canlı sağlayıcı:** Bugünkü fikstür ve matchDetails `lineupType` gerçek yanıtla doğrulanmalı; FotMob erişim ve kullanım koşulları kontrol edilmeli.
5. **Güvenli devreye alma:** Önce ZIP'i yeni commit ile yükle; testleri çalıştır; `python main.py test` salt okunur önizleme; manuel `learn` ile sonuçları güncelle; canlı yayına geçmeden önce Telegram testini **açık onayla** çalıştır. Bu denetimde gönderim yapılmadı.

## 7. Bugün için işletim uyarısı

9 Ekim 2026 Cuma günü Galatasaray–Kasımpaşa maçı 17:00 UTC / 20:00 Türkiye saatinde planlı. İş akışı cron'u bu saatten önce en az bir kez çalışmalıdır. **GitHub cron dakikası garanti edilmez**; yalnızca GitHub Actions üzerinde T-15 kesin zamanlı teslim vaadi verilemez. `AUTOMATION_ENABLED` kapalıysa zamanlanmış işler hiç başlamaz; manuel `workflow_dispatch` bundan bağımsız çalışabilir.

**Sonuç:** Teknik hazırlık düzeltmeleri uygulanmış ZIP teslim edilebilir. Fakat canlı entegrasyon kanıtı ve modelin basit referanstan üstün olduğuna dair ölçüm olmadan “doğru tahmin sistemi hazır” demek bilimsel olarak savunulamaz.

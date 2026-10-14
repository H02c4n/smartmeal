# 05 — Güvenlik ve İş Kuralları

## 1. Kimlik ve yetkilendirme

- Django'nun güvenli parola saklama mekanizmaları kullanılır.
- Yönetici hesaplarında çok faktörlü doğrulama ihtiyacı değerlendirilir.
- Rol kontrolüne ek olarak nesne ve tesis kapsamı kontrol edilir.
- Müşteri yalnızca kendi sipariş, adres ve destek taleplerine erişir.
- Kurye yalnızca kendisine atanmış teslimatları ve gerekli minimum bilgileri görür.
- Stok düzeltme, lot serbest bırakma, iade, rol değişikliği ve audit erişimi özel izin gerektirir.
- Yetki kontrolleri varsayılan olarak kapalı değil, açıkça izin verilen yaklaşımda tasarlanır.

## 2. Stok bütünlüğü

- Stok değişimleri `StockMovement` hareket defterine kaydedilir.
- Normal işlem akışında geçmiş hareketler düzenlenmez; ters hareketle düzeltilir.
- Kullanılabilir stok: fiziksel stok eksi aktif rezervasyonlar ve bloke miktarlar; hesaplama tanımı tüm modüllerde aynı olmalıdır.
- Aynı stok üzerinde eşzamanlı işlemler transaction ve uygun kilitleme/kısıtlarla korunur.
- Rezervasyon oluşturma, serbest bırakma ve tüketme idempotent olmalıdır.
- Negatif kullanılabilir stok engellenir; izin verilen istisna varsa ayrı ve denetlenebilir bir iş kuralı olur.
- Lot tahsisi için FEFO önerilir, ancak gerçek raf ömrü ve kalite politikasıyla doğrulanmalıdır.

## 3. Sipariş kuralları

- Fiyat ve toplam tutar sunucuda hesaplanır.
- Sipariş satırı ürün adı/fiyatı ve reçete sürümünü snapshot olarak saklar.
- Sipariş iptalinde ödeme ve rezervasyon etkileri ayrı ayrı işlenir.
- İptal için izin verilen durumlar ve zaman sınırları açıkça belirlenir.
- Durum değişikliği aktör, zaman ve gerekçe ile denetlenebilir olmalıdır.
- Aynı idempotency anahtarıyla tekrar gönderim ikinci bir iş etkisi oluşturmamalıdır.

## 4. Gıda güvenliği ve lot izlenebilirliği

- Mal kabulde lot kodu ve son kullanma tarihi kaydedilir.
- Kalite kontrolü bekleyen malzeme kullanılabilir stok sayılmaz.
- Bloke lot üretim planlaması ve rezervasyonda kullanılamaz.
- Uygunsuzlukta lot/parti/paket/sipariş bağlantıları üzerinden etki alanı bulunabilir.
- Kalite blokajını kaldırmak yetkili rol, gerekçe ve audit kaydı gerektirir.
- Sıcaklık ve diğer kritik kontrollerde ölçüm birimi, zaman ve kontrol eden kişi kaydedilir.
- Gıda güvenliği mevzuatı, saklama süreleri, etiket ve alerjen gereksinimleri faaliyet gösterilen ülke ve ürünlere göre ayrıca doğrulanmalıdır.

## 5. Mobil idempotency ve offline

- Her kuyruklanan mobil komut benzersiz bir işlem kimliği taşır.
- Sunucu tekrar gelen komutları güvenli biçimde tanır.
- Çevrimdışı komutların geçerliliği sunucuda yeniden doğrulanır.
- Eski veriyle kritik durum geçişi istenirse çatışma döndürülür; istemci sessizce başarı göstermez.
- Yerel cihazda hassas veri minimumda tutulur; oturum ve cihaz güvenliği platformun güvenli saklama araçlarıyla tasarlanır.

## 6. Kişisel veri ve gizlilik

- Yalnızca iş için gereken kişisel veri tutulur.
- Loglara token, parola, ödeme verisi veya gereksiz kişisel veri yazılmaz.
- Fotoğraf/konum gibi teslimat kanıtları için amaç, erişim ve saklama süresi tanımlanır.
- Veri dışa aktarma ve silme talepleri için iş akışı tasarlanır.
- Faaliyet gösterilen ülkeye uygulanabilir veri koruma ve tüketici mevzuatı hukuk/uyum uzmanıyla doğrulanır.

## 7. Ödeme

- Ödeme sağlayıcısı henüz seçilmemiştir.
- Kart numarası ve CVV SmartMeal veritabanına/loglarına yazılmaz.
- Sağlayıcı webhook'ları imza doğrulaması, tekrar koruması ve audit ile işlenir.
- Ödeme durumu ile sipariş durumu ayrı tutulur.
- İade ve mutabakat kayıtları denetlenebilir olmalıdır.

## 8. Yedekleme ve kurtarma

- PostgreSQL yedekleme sıklığı ve saklama süresi belirlenir.
- Geri yükleme düzenli olarak test edilir.
- RPO (kabul edilebilir veri kaybı) ve RTO (kabul edilebilir kurtarma süresi) ürün sahibi tarafından belirlenir.
- Migration ve deploy prosedürleri yedekleme planıyla uyumlu olmalıdır.
- Üretim gizli bilgileri geliştirme ortamından ayrıdır.

## 9. Kritik testler

- Eşzamanlı stok rezervasyonu
- Aynı idempotency anahtarıyla yinelenen istek
- Başka müşterinin siparişine erişim
- Kurye kapsamı dışındaki teslimatı değiştirme
- Bloke lotu kullanmaya çalışma
- İzin verilmeyen durum geçişi
- Mal kabul ve ters stok hareketi
- Sipariş iptali ve rezervasyon serbest bırakma
- Ödeme webhook tekrarları
- Yedekten geri yükleme provası

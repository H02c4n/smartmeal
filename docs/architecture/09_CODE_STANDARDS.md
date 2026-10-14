# 09 — Kod Standartları

## 1. Genel
- TypeScript strict mode hedeflenir.
- Python kodu PEP 8 ve seçilmiş formatter/linter kurallarına uyar.
- Bağımlılık sürümleri lockfile ile sabitlenir.
- Her iş parçası küçük, gözden geçirilebilir ve test edilebilir olur.
- Gizli bilgiler kaynak kodda tutulmaz.
- İsimler iş alanını açık anlatır; genel amaçlı `utils` klasörleri kontrolsüz büyütülmez.

## 2. Django
- Custom user modeli ilk migration'dan önce oluşturulur.
- İş işlemleri view/serializer içine yığılmaz; uygun service fonksiyonları kullanılır.
- Okuma sorguları karmaşıksa `selectors.py` gibi açık bir yere alınabilir.
- `transaction.atomic()` yalnızca transaction sınırının açık olması gereken işlemlerde kullanılır.
- Eşzamanlı stok değişiklikleri için test edilmiş kilitleme/kısıt stratejisi uygulanır.
- Serializer doğrulaması veritabanı kısıtlarının yerine geçmez; ikisi tamamlayıcıdır.
- Kritik durum geçişleri merkezi servislerde doğrulanır.
- İlişkili modül verileri sahibinin servisinden değiştirilir.
- Migration'lar küçük ve gözden geçirilebilir tutulur; büyük veri migration'ları ayrı planlanır.

## 3. API
- `/api/v1/` sürümlemesi korunur.
- Request/response şemaları OpenAPI ile belgelenir.
- Hata kodları tutarlı olur.
- Liste endpoint'leri sayfalama ve izin filtrelemesi içerir.
- Kritik POST işlemleri idempotency gereksinimi açısından değerlendirilir.
- Durum değiştiren endpoint'ler eylem odaklıdır; istemcinin serbest status yazmasına izin verilmez.

## 4. Next.js
- API erişimi tek bir tanımlı istemci katmanından yapılır.
- Server/client bileşen sınırı bilinçli seçilir.
- Yetki kontrolü yalnızca UI'da yapılmaz; backend de her isteği doğrular.
- Form doğrulaması kullanıcı deneyimi içindir; sunucu doğrulaması zorunludur.
- API tipleri elle kopyalanmak yerine mümkün olduğunda OpenAPI şemasından üretilir.

## 5. React Native
- API ve hata işleme ortaklaştırılabilir.
- Hassas token'lar platformun güvenli saklama yaklaşımıyla korunur.
- Kritik eylemler için loading, success, failure ve retry durumları açıkça gösterilir.
- Offline kuyruk yalnızca onaylanmış eylemleri kapsar ve idempotency anahtarı kullanır.
- İstemci, sunucu onayı gelmeden kritik eylemi kesinleşmiş gibi göstermez.

## 6. Test
- İş kuralları için birim testleri
- PostgreSQL davranışına ihtiyaç duyan akışlar için entegrasyon testleri
- Yetki ve nesne kapsamı testleri
- Eşzamanlılık/idempotency testleri
- Kritik kullanıcı akışları için uçtan uca testler
- Testlerin sonucu gerçekten çalıştırılmadan “geçti” olarak raporlanmaz.

## 7. Git ve değişiklikler
- Küçük ve açıklayıcı commit'ler
- Özellik başına anlaşılır branch/PR
- Büyük refactor ile işlev değişikliği mümkün olduğunca ayrılır
- Mimari karar değişiklikleri `07_DECISION_LOG.md` içine kaydedilir
- Her oturum sonunda `08_CURRENT_STATE.md` güncellenir

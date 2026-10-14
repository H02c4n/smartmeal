# SmartMeal Project Master

**Belge sürümü:** 1.0  
**Durum:** Başlangıç blueprint'i — henüz uygulama koduyla doğrulanmadı  
**Ürün:** SmartMeal yemek siparişi, malzeme tedariki, üretim, kalite, paketleme ve teslimat yönetim sistemi

## 1. Ürün hedefi

SmartMeal, müşteri siparişlerinden malzeme planlamasına, üretime, kalite kontrolüne, paketlemeye ve teslimata kadar operasyon zincirini uçtan uca yönetir. İlk operasyon hedefi haftada yaklaşık 600 siparişi güvenilir biçimde yönetebilmektir. Bu hedef performans testiyle doğrulanmalıdır; sipariş hacmi tek başına mimari kapasite garantisi değildir.

## 2. Onaylanmış teknoloji kararları

- Backend: Python, Django, Django REST Framework (DRF)
- Veritabanı: PostgreSQL
- Web: Next.js + TypeScript
- Admin: tamamen özelleştirilmiş Next.js Admin
- Mobil: React Native + TypeScript
- Mobil uygulamalar: müşteri ve operasyon için iki ayrı uygulama
- Yerel geliştirme: Docker Compose + PostgreSQL; başlangıç geliştirmesi yerel ve ücretsiz araçlarla
- Arka plan işleri: ihtiyaç olduğunda Celery + Redis
- API tanımı: OpenAPI
- Testler: Django/pytest tabanlı testler; istemci testleri uygulama kapsamına göre
- Mimari yaklaşım: modüler monolit; başlangıçta mikroservis yok

Sürümler, paket yöneticileri ve kesin bağımlılık sürümleri repository oluşturulurken seçilip lockfile'lara sabitlenmelidir. Bu belgede sürüm numarası belirtilmemesi kasıtlıdır.

## 3. Uygulamalar

1. Müşteri web sitesi — Next.js
2. SmartMeal Admin — Next.js, özel yönetim ve üretim ekranları
3. Müşteri mobil uygulaması — React Native
4. Operasyon/teslimat mobil uygulaması — React Native
5. Ortak backend API — Django REST Framework

Tüm istemciler backend API üzerinden iletişim kurar. İstemciler veritabanına doğrudan erişmez.

## 4. Bağlayıcı mimari ilkeler

1. **Tek doğruluk kaynağı:** iş kuralları backend'de uygulanır; UI doğrulaması yalnızca kullanıcı deneyimi içindir.
2. **Veri bütünlüğü:** stok, rezervasyon, sipariş, üretim ve teslimat işlemleri veritabanı transaction'ları ve kısıtlarla korunur.
3. **Açık durum geçişleri:** kritik nesnelerin durumları izin verilen geçişlerle değişir; genel amaçlı serbest `status` güncellemesi yapılmaz.
4. **İzlenebilirlik:** stok hareketleri, lotlar, üretim partileri ve audit olayları ilişkilendirilebilir olmalıdır.
5. **Güvenli tekrar:** mobil bağlantı kopması ve ağ tekrarları çift sipariş/çift teslimat gibi sonuçlar oluşturmamalıdır.
6. **En az ayrıcalık:** kullanıcı yalnızca yetkili olduğu işlemi ve nesneleri görür.
7. **Belgeler ve kod senkronize:** API/model değişikliği ilgili belgelerde ve testlerde yansıtılır.
8. **Migration disiplini:** Django migration'ları sürüm kontrolünde tutulur; üretim verisi üzerinde kontrolsüz şema değişikliği yapılmaz.
9. **Geriye dönük geçmiş:** onaylanmış reçete sürümü ve sipariş anındaki fiyat gibi geçmişe ait bilgiler sonradan sessizce değişmez.
10. **Modüler monolit:** Django uygulamaları iş alanlarına göre ayrılır; modüller birbirlerinin tablolarını gelişigüzel güncellemez.

## 5. Modüller

- `accounts`
- `catalog`
- `recipes`
- `inventory`
- `purchasing`
- `orders`
- `planning`
- `production`
- `quality`
- `packing`
- `delivery`
- `notifications`
- `support`
- `billing`
- `reporting`
- `audit`

Modül sorumlulukları `01_ARCHITECTURE.md` içindedir.

## 6. Çalışma kuralları

- Görev başlamadan önce `08_CURRENT_STATE.md` okunur.
- Kod varsa belgelerle karşılaştırılır; var olmayan dosya, endpoint veya model mevcutmuş gibi varsayılmaz.
- Her görev mümkün olduğunca küçük ve test edilebilir tutulur.
- İlgisiz modüller refactor edilmez.
- Mimari çelişki bulunursa değişiklik yapmadan önce çelişki, seçenekler ve etkiler açıklanır.
- Tamamlanma iddiası yalnızca gerçekten çalıştırılmış test ve doğrulamalara dayanır.
- Her oturum sonunda değişen dosyalar, migration'lar, testler, açık riskler ve sıradaki görev `08_CURRENT_STATE.md` içinde güncellenir.
- Mimari kararda değişiklik yapılırsa `07_DECISION_LOG.md` kaydı eklenir.

## 7. İlk dikey dilim

İlk işlevsel akış şu sırayla geliştirilir:

**Malzeme → Reçete → Lot/Stok → Sipariş → Rezervasyon**

Bu akışın veri bütünlüğü ve testleri kanıtlanmadan kapsamlı üretim planlama veya mobil çevrimdışı özelliklerine geçilmez.

## 8. Henüz karara bağlanmamış ürün kararları

Bunlar sessizce varsayılmamalıdır; ilgili geliştirmeden önce netleştirilmelidir:

- Sipariş onayı ve stok rezervasyonu için kesin politika ve rezervasyon süresi
- Ödeme sağlayıcısı, ödeme yakalama/iade akışı
- Vergi, para birimi ve satış yapılacak ülkelerin gereklilikleri
- Üretim tesisi/şube sayısı ve tesis bazlı stok
- Reçete birimleri, dönüşüm ve fire hesaplama politikası
- Gıda güvenliği kayıtları ve saklama süreleri
- Müşteri bildirim kanalları
- Teslimat kanıtı, konum verisi ve fotoğraf saklama politikası
- Mobil uygulamanın çevrimdışı destekleyeceği kesin işlemler
- Veri saklama, silme, yedekleme ve kurtarma hedefleri (RPO/RTO)
- Operasyonel eşzamanlı kullanıcı ve performans hedefleri

## 9. Başarı ölçütü

Bir özellik yalnızca UI ekranı tamamlandığı için bitmiş sayılmaz. İlgili iş kuralı, API, izin, veri bütünlüğü, hata davranışı, testler ve belge güncellemesi tamamlanmalıdır.

# 04 — Web ve Mobil Uygulamalar

## 1. Müşteri web sitesi — Next.js + TypeScript

Ekran kapsamı:
- Menü/kategori ve ürün listeleme
- Ürün detayları, içerikler ve alerjen bilgileri
- Teslimat tarihi/adresi seçimi
- Sepet ve checkout
- Ödeme sağlayıcısına yönlendirme veya sağlayıcıya uygun güvenli ödeme akışı
- Sipariş geçmişi ve durum takibi
- Profil, adresler, destek talepleri

Kurallar:
- Fiyat ve stok kararı API'den gelir.
- Müşteri yalnızca kendi verilerine erişir.
- SEO ve sayfa performansı gereken ekranlarda Next.js rendering stratejisi bilinçli seçilir.
- Ödeme kartı verisi SmartMeal uygulama sunucusunda saklanmaz.

## 2. SmartMeal Admin — Next.js + TypeScript

Bu, genel amaçlı Django Admin değil, özel operasyon arayüzüdür.

Ana ekranlar:
- Operasyon dashboard'u
- Sipariş listesi ve detay
- Menü ve reçete sürümleri
- Tedarikçi, satın alma, mal kabul
- Stok lotları, son kullanma tarihleri ve düzeltmeler
- Talep ve üretim planlama
- Üretim partileri, görevler ve fire
- Kalite kontrolleri, blokajlar ve uygunsuzluklar
- Paketleme ve teslimat yönetimi
- Kullanıcı/rol yönetimi
- Audit ve raporlar

UX ilkeleri:
- Tehlikeli işlemler gerekçe/onay isteyebilir.
- Durum geçişleri yalnızca izinliyse gösterilir.
- Liste ekranları filtre, arama, sayfalama ve toplu işlem sınırlarına sahip olur.
- Kritik işlemlerden sonra sunucunun döndürdüğü güncel durum gösterilir.
- Form doğrulaması backend doğrulamasının yerine geçmez.

## 3. Müşteri mobil — React Native + TypeScript

Kapsam:
- Giriş ve hesap
- Menü ve ürünler
- Sepet/sipariş
- Adresler
- Sipariş durumu ve bildirimler
- Sipariş geçmişi
- Destek

Müşteri uygulaması operasyon rolü/ekranlarını içermez. Web ile aynı API iş kurallarını kullanır.

## 4. Operasyon mobil — React Native + TypeScript

Kapsam, rol ve iş gereksinimine göre açılır:
- Atanmış görev listesi
- Üretim ve paketleme adımları
- Lot/paket barkod veya QR doğrulama
- Teslimat listesi ve duraklar
- Teslim edildi/edilemedi sonucu
- Gerekiyorsa teslimat kanıtı
- Bağlantı durumu ve senkronizasyon göstergesi

Çevrimdışı mod sınırsız yazma anlamına gelmez. Yalnızca önceden belirlenmiş işlemler yerel kuyruğa alınır; her işlem benzersiz kimlikle sunucuya gönderilir. Çakışma halinde sunucunun sonucu otoritedir.

## 5. Paylaşılan istemci kodu

Monorepo kullanılırsa `packages/api-types` içinde OpenAPI'den üretilen tipler tutulabilir. Genel yardımcılar paylaşılabilir; ancak uygulamaların izin ve navigasyon akışları ayrı kalır.

İstemcilerde stok, fiyat veya rol kurallarının ikinci bir kopyası otorite olarak uygulanmaz. UI yalnızca API sonucunu gösterir.

## 6. Erişilebilirlik ve yerelleştirme

- Form alanlarında erişilebilir etiketler
- Hata mesajlarında anlaşılır metin
- Tarih, saat ve para gösterimi yerel ayarlara göre
- Backend'de para birimi ve zaman değerlerinin açık saklanması
- Alerjen ve gıda bilgileri için net, erişilebilir gösterim

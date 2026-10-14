# 01 — Sistem Mimarisi

## 1. Genel görünüm

```text
Müşteri Web (Next.js) ───────┐
SmartMeal Admin (Next.js) ───┤
Müşteri Mobil (React Native) ├── HTTPS/JSON ── Django REST API
Operasyon Mobil (React Native)┘                       │
                                      ┌────────────────┼───────────────┐
                                      │                │               │
                                  PostgreSQL       Celery/Redis    Dosya depolama
                                  ana veriler      arka plan       ileride S3 uyumlu
```

Celery/Redis başlangıçta yalnızca ihtiyaç duyulan asenkron görevler için eklenir. Kritik stok/sipariş tutarlılığı arka plan görevinin başarılı olmasına bağımlı bırakılmaz.

## 2. Mimari stil

Django modüler monolit. Tek deploy edilebilir backend ve tek ana PostgreSQL veritabanı bulunur. İş alanları ayrı Django apps olarak düzenlenir; modüller servis arayüzleri ve açık bağımlılıklarla iletişim kurar.

Mikroservis, Kubernetes, Kafka ve dağıtık sistem karmaşıklığı ilk sürüm için varsayılan değildir. Gerçek ölçek, ekip veya bağımsız dağıtım ihtiyacı ortaya çıkarsa ayrı ADR ile değerlendirilir.

## 3. Modül sınırları

| Django app | Sahip olduğu iş alanı |
|---|---|
| `accounts` | Kullanıcı, rol, tesis kapsamı, oturum ve izinler |
| `catalog` | Ürün, kategori, SKU, satışa açıklık; malzeme tanımı (`Ingredient`) ve birim/dönüşüm sözlüğü (ADR-011, önerildi) |
| `recipes` | Reçete sürümleri, satırlar, verim, malzeme ihtiyacı |
| `inventory` | Malzeme stoğu (malzeme tanımı `catalog`'da): lot, stok hareketi, bakiye, rezervasyon, blokaj |
| `purchasing` | Tedarikçi, satın alma siparişi, mal kabul |
| `orders` | Müşteri siparişi, satırlar, fiyat snapshot'ı, iptal |
| `planning` | Talep özeti, malzeme ihtiyacı, üretim planı |
| `production` | Üretim emri/partisi, iş adımları, gerçekleşen miktar ve fire |
| `quality` | Kontrol listeleri, ölçümler, uygunsuzluk, hold/release |
| `packing` | Paket ve etiket; sipariş/paket/parti bağlantıları |
| `delivery` | Rota, durak, atama, teslimat sonucu ve kanıt |
| `notifications` | Bildirim tercihleri ve gönderim kayıtları |
| `support` | Müşteri destek talepleri ve çözüm |
| `billing` | Ödeme sağlayıcısı referansları, iadeler ve mutabakat |
| `reporting` | Operasyon raporları ve KPI sorguları |
| `audit` | Kritik eylemlerin değiştirilemez denetim izi |

## 4. Bağımlılık ilkeleri

- `orders` ürün ve reçete sürümü bilgilerini okur; stok rezervasyonu için `inventory` servis işlemini çağırır.
- `production` malzeme tüketimini `inventory` servis işlemleriyle kaydeder.
- `quality` ilgili parti veya lot üzerinde blokaj/release kararını tanımlı servis üzerinden uygular.
- `packing` paketlerin sipariş ve üretim partileriyle ilişkisini tutar.
- `delivery` siparişin teslimat durumunu izinli geçiş üzerinden günceller.
- `reporting` esas olarak salt okunur sorgular kullanır; iş verisini doğrudan değiştirmez.
- `audit` kritik modüllerden olay alır; denetim kaydı uygulama loglarından ayrı düşünülür.
- Modüller başka modülün modellerini kullanabilir, ancak başka modülün tablolarını doğrudan yazan iş mantığı oluşturmamalıdır. Gerekli çapraz modül işlemi sahibi modülün servis API'si üzerinden yapılır.

## 5. Transaction ve yan etkiler

Bir veritabanı transaction'ı içinde:
1. Gerekli kayıtlar kilitlenir/ doğrulanır.
2. İş kuralı uygulanır.
3. Ana kayıtlar ve hareket defteri yazılır.
4. Transaction commit edilir.

E-posta, push bildirimi veya uzun süren rapor gibi yan etkiler commit sonrasında yapılır. Commit ile kuyruklama arasında kayıp riskini azaltmak için gerekirse transactional outbox deseni uygulanır. Bildirim başarısızlığı sipariş transaction'ını geriye almamalıdır.

## 6. Altyapı ortamları

- `local`: Docker Compose, yerel PostgreSQL ve örnek/test verileri
- `test`: izole test veritabanı, otomatik testler
- `staging`: üretime benzer ama ayrı ve hassas olmayan test verileri
- `production`: ayrı gizli bilgiler, erişim kısıtları, izleme, yedek ve kurtarma prosedürleri

Yerel geliştirme için ücretsiz araçlar hedeflenir. Üretim barındırma ve ödeme sağlayıcısı bu pakette seçilmiş değildir.

## 7. Gözlemlenebilirlik

- Yapılandırılmış uygulama logları
- Her HTTP isteğine `request_id`
- Hata oranı ve API yanıt süresi metrikleri
- Kuyruk görevlerinin başarısızlık ve tekrar deneme takibi
- Veritabanı yedeklerinin durumu
- Kritik iş metrikleri: sipariş sayısı, stok uyuşmazlığı, bloke lotlar, başarısız teslimat, kalite uygunsuzluğu

Loglara parola, token, ödeme kartı bilgisi veya gereksiz kişisel veri yazılmaz.

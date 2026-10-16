# 03 — API Sözleşmeleri

## 1. Genel standart

- Base path: `/api/v1/`
- Transport: HTTPS, JSON
- Kimlik: uygun token/session stratejisi; müşteri ve personel istemcileri için tehdit modeline göre seçilir.
- API schema: OpenAPI; istemci tipleri mümkünse şemadan üretilir.
- Liste endpoint'leri: sayfalama ve belgelenmiş filtreler.
- Tarih/saat: ISO 8601, timezone açık.
- Para: ondalık string ve para birimi; istemciden gelen toplam fiyat otorite değildir.
- Her hata cevabında `error.code`, güvenli `message`, gerektiğinde `details` ve `request_id`.
- Kritik create/complete işlemleri için idempotency desteği.
- API değişiklikleri geriye uyumluluk dikkate alınarak yapılır; kırıcı değişiklik için sürümleme ve geçiş planı gerekir.

## 2. Önerilen hata kodları

- `VALIDATION_ERROR` — alan doğrulaması başarısız
- `AUTHENTICATION_REQUIRED` — oturum/token yok veya geçersiz
- `PERMISSION_DENIED` — işlem için yetki yok
- `RESOURCE_NOT_FOUND` — kaynak bulunamadı veya erişim politikası gereği gizlendi
- `INVALID_STATE_TRANSITION` — izin verilmeyen durum geçişi
- `INSUFFICIENT_STOCK` — kullanılabilir stok yetersiz
- `LOT_BLOCKED` — kalite nedeniyle lot kullanılamaz
- `IDEMPOTENCY_CONFLICT` — aynı anahtar farklı içerikle kullanıldı
- `CONFLICT` — güncel veriyle işlem çakışıyor
- `RATE_LIMITED` — hız sınırı aşıldı

## 3. İlk endpoint envanteri

### Kimlik
- `POST /auth/login/`
- `POST /auth/refresh/`
- `POST /auth/logout/`
- `GET /me/`

**Uygulandı (ADR-013):** web istemcileri sunucu tarafı oturum çerezi + CSRF kullanır; `refresh` yalnızca mobil token akışı içindir (Faz 6, henüz yok).

| Endpoint | Davranış |
|---|---|
| `GET /auth/csrf/` | Herkese açık; `{"csrf_token": "..."}` döner ve `csrftoken` çerezini kurar. İstemci, `POST`'lardan önce bunu çağırır ve token'ı `X-CSRFToken` başlığında gönderir. |
| `POST /auth/login/` | Gövde `{email, password}`. Başarıda `200` + `/me/` yükü ve `HttpOnly` oturum çerezi (oturum anahtarı her girişte yenilenir). Hatalı parola, bilinmeyen e-posta ve pasif hesap **aynı** yanıtı verir: `401 AUTHENTICATION_REQUIRED` "Invalid email or password." CSRF anonim istekte de zorunludur. Hız sınırı: adres başına `20/dk`, e-posta başına `5/dk` (`429 RATE_LIMITED`). |
| `POST /auth/register/` | ADR-015. Gövde `{email, password, phone?}`. Hesap yalnızca `CUSTOMER` rolüyle oluşur (gövde rol/bayrak seçemez), oturum açılır, `201` + `/me/` yükü. CSRF zorunlu. Geçersiz e-posta/telefon veya Django parola doğrulayıcılarını geçemeyen parola `400 VALIDATION_ERROR` (`details.password` mesaj listesi). Kayıtlı e-posta `400` (`details.email`, küçük/büyük harf fark etmez). Zaten oturum açıksa `409`. Hız sınırı: adres başına `5/saat` (`429 RATE_LIMITED`). E-posta doğrulaması henüz yok. |
| `POST /auth/logout/` | Oturumu kapatır, `204`. Oturumsuzsa `401`. |
| `GET /me/` | `{id, email, phone, roles[], permissions[]}`. `permissions`, rollerin verdiği izin kodlarıdır; istemci eylemleri göstermek/gizlemek için kullanabilir ama güvenlik sunucudadır. |

Kimliksiz istek her yerde **401** `AUTHENTICATION_REQUIRED` döner (`WWW-Authenticate: Session`); kimlikli ama yetkisiz istek **403** `PERMISSION_DENIED`. Hız sınırı sayaçları Django önbelleğindedir: birden çok backend süreci için paylaşımlı önbellek (Redis) gerekir. CORS henüz açık değildir (aşağıya bakın).

### Katalog ve reçete
- `GET /products/`
- `GET /products/{id}/`
- `POST /admin/products/`
- `POST /admin/recipe-versions/`
- `POST /admin/recipe-versions/{id}/approve/`

**Faz 1 genişletmesi (uygulandı; ADR-011 ile önerildi).** Yukarıdaki listeye ek olarak şu endpoint'ler eklendi. Yeni alanlar ve endpoint'ler mevcut sözleşmeyi bozmaz.
- `GET /admin/products/`, `GET|PATCH /admin/products/{id}/`, `POST /admin/products/{id}/activate/`, `POST /admin/products/{id}/deactivate/`
- `GET|POST /admin/ingredients/`, `GET|PATCH /admin/ingredients/{id}/`, `POST /admin/ingredients/{id}/activate/`, `POST /admin/ingredients/{id}/deactivate/`
- `GET /admin/units/`, `GET /admin/units/{id}/` (salt okunur birim sözlüğü)

Ortak kurallar (aşağıdaki §7 maddeleri için):
- **Kimlik:** hepsi kimlik doğrulama ister. `/products/*`: giriş yapmış herhangi bir kullanıcı (müşteri listesi kimlik zorunlu kabul edildi; herkese açma ayrı karar). `/admin/*`: rol tabanlı `IsCatalogAdmin` (ADR-013; okuma `catalog:read`, yazma `catalog:manage`, tablo 05 §1). Kimliksiz: 401 `AUTHENTICATION_REQUIRED`; yetkisiz: 403 `PERMISSION_DENIED`.
- **Nesne kapsamı:** `/products/` yalnızca `is_active=true` ürünleri döndürür; pasif ürün detayı `RESOURCE_NOT_FOUND`. Admin tüm kayıtları görür.
- **Alanlar:** `is_active` düz gövdeyle yazılamaz (`VALIDATION_ERROR`); yalnızca `activate`/`deactivate` eylemleriyle değişir (idempotent, 200). `sku` ve ingredient `base_unit` oluşturulduktan sonra değişmez: PATCH'te farklı değer `VALIDATION_ERROR`, aynı değerin tekrarı kabul edilir. `PUT` ve `DELETE` yoktur (405).
- **Filtreler (liste):** `q` (SKU/ad, büyük-küçük harf duyarsız), `is_active` (yalnızca admin listeleri, `true|false`, geçersiz değer `VALIDATION_ERROR`). Sayfalama: DRF `PageNumberPagination` (50): `count`, `next`, `previous`, `results`.
- **Para:** `price` ondalık string (`"129.00"`) + `currency` (3 harf, büyük harfe normalize).
- **Hatalar:** `VALIDATION_ERROR` (alan hataları `details` altında; yinelenen SKU `details.sku`), `RESOURCE_NOT_FOUND`, `AUTHENTICATION_REQUIRED`, `PERMISSION_DENIED`.
- **Transaction/idempotency:** her yazma tek kayıt ve tek transaction'dır. Create, SKU benzersizliği ile doğal olarak tekrar-güvenlidir (ikinci istek `VALIDATION_ERROR`); eşzamanlı yinelenen create DB benzersiz indeksiyle yakalanıp aynı hataya çevrilir. Ayrı `Idempotency-Key` mekanizması bu fazda yoktur.
- **İstek/yanıt şemaları:** OpenAPI şemasında (`/api/v1/schema/`); `ProductCreate`, `PatchedProductUpdate`, `IngredientCreate`, `PatchedIngredientUpdate`, `Product` (müşteri), `ProductAdmin`, `Ingredient`, `Unit`.
- **Ingredient request:** `POST` gövdesi `{sku, name, base_unit}`; `base_unit` birim `code`'udur (`g`, `ml`, `pcs`), taban birim olmalıdır. `PATCH` yalnızca `name` değiştirir.
- **Henüz API'si yok:** `IngredientUnitConversion` yönetimi (şimdilik Django admin ve `catalog.services.create_unit_conversion`).

**Faz 1 tamamlayıcıları (uygulandı; ADR-012).** Hepsi `IsCatalogAdmin` ister (rol tabanlı, ADR-013).
- Alerjen: `GET|POST /admin/allergens/`, `GET|PATCH /admin/allergens/{id}/`, `POST …/activate/`, `POST …/deactivate/` (`code` değişmez); `GET|PUT /admin/ingredients/{id}/allergens/` (PUT gövdesi `{"allergens":[{"allergen":"gluten","presence":"contains"}]}` beyanı bütün olarak değiştirir, boş liste temizler; pasif alerjen yeni eklenemez).
- Reçete: `GET|POST /admin/recipe-versions/` (filtre `product` SKU, `status`), `GET|PATCH /admin/recipe-versions/{id}/` (yalnızca taslak; `lines` verilirse satırların tamamı değişir), `POST …/approve/`, `POST …/retire/`, `GET …/requirements/?quantity=&unit=` (taban birimde net/brüt ihtiyaç). `status` düz gövdeyle yazılamaz. `GET` ayrıntısı `lines` ve türetilmiş `allergens` içerir.
- Hatalar: onaylı/emekli sürümü düzenleme veya yanlış durumdan geçiş `409 INVALID_STATE_TRANSITION`; satırsız onay, pasif malzeme, dönüştürülemeyen birim `400 VALIDATION_ERROR`.

### Sipariş (ADR-014 — uygulandı; geçici ürün varsayımlarıyla)
| Endpoint | Davranış |
|---|---|
| `POST /orders/` | `CUSTOMER`. `Idempotency-Key` **zorunlu** (yoksa 400). Gövde 4. bölümdeki gibi. Tek işlemde: doğrulama → fiyat/reçete snapshot'ı → malzeme bazında toplu FEFO rezervasyonu → sipariş `confirmed`. İlk istek `201`, aynı anahtar+gövde tekrarı `200` (güncel durumla), aynı anahtar farklı gövde `409 IDEMPOTENCY_CONFLICT`. Yetersiz stok `409 INSUFFICIENT_STOCK`, `details: {"products": [id…]}` — **malzeme adı/miktarı müşteriye sızmaz**; hiçbir kayıt/rezervasyon kalmaz. Doğrulama hataları `400 VALIDATION_ERROR` (`details.items[i].product_id/quantity`, `delivery_date`, `delivery_address_id`). Pasif ürün, onaylı reçetesi olmayan ürün ve adet-bazlı olmayan reçete aynı mesajla "sipariş edilemez" döner. |
| `GET /orders/`, `GET /orders/{id}/` | `CUSTOMER`: yalnızca kendi siparişleri. `ADMIN`, `PLANNER`, `PRODUCTION`, `PACKING`, `SUPPORT`, `FINANCE`: tümü; yanıtta ek olarak `customer_id`, `customer_email`, `status_history`. Başkasının siparişi **404** `RESOURCE_NOT_FOUND`. Filtreler: `status`, `delivery_date`, `customer` (e-posta; yalnızca arka ofis, müşteri için yok sayılır). |
| `POST /orders/{id}/cancel/` | Gövde `{reason?}`. `CUSTOMER` kendi siparişini, teslimata en az `ORDER_CUSTOMER_CANCEL_MIN_DAYS` (varsayılan 1) gün varken iptal eder; geçmişse `409 CONFLICT` (`details.latest_cancellation_date`). `ADMIN`/`SUPPORT` (`orders:cancel_any`) süre sınırı olmadan iptal eder ama `reason` zorunlu. Rezervasyonlar aynı işlemde serbest bırakılır. İdempotent (iptal edilmişse `200`). |
| `GET|POST /me/addresses/`, `GET|PATCH|DELETE /me/addresses/{id}/` | `CUSTOMER`; yalnızca kendi adres defteri (başkasınınki 404). `country_code` ISO-2 (büyük harfe çevrilir). |

Durum değerleri **küçük harfle** (`confirmed`, `cancelled`; kodun geri kalanıyla tutarlı), 4. bölümdeki örnekteki `CONFIRMED` yalnızca örnektir.

### Stok ve satın alma
- `GET /inventory/balances/`
- `GET /inventory/lots/`
- `POST /purchase-orders/`
- `POST /purchase-orders/{id}/submit/`
- `POST /goods-receipts/`
- `POST /inventory/adjustments/`

**Faz 2 uygulaması (ADR-012, onaylandı).** Yukarıdaki altı endpoint ve aşağıdakiler uygulandı. Yetki rol tabanlıdır (ADR-013; tablo 05 §1): okuma `*:read`, tedarik yazma `purchasing:manage`, rezervasyon/tüketim `inventory:reserve`, lot release/block `QUALITY`, düzeltme/ters hareket ve mal kabul ters kaydı `ADMIN`.

| Endpoint | Not |
|---|---|
| `GET|POST /suppliers/`, `GET|PATCH /suppliers/{id}/`, `POST …/activate/`, `…/deactivate/` | `is_active` yalnızca eylemlerle; DELETE yok |
| `GET|POST /purchase-orders/`, `GET|PATCH /purchase-orders/{id}/` | PATCH yalnızca `draft`; `lines` bütün olarak değişir; filtre `status` |
| `POST /purchase-orders/{id}/submit/`, `…/cancel/` | İdempotent; alınmış sipariş iptal edilemez (409) |
| `GET|POST /goods-receipts/`, `GET /goods-receipts/{id}/` | **`Idempotency-Key` zorunlu**; ilk istek 201, tekrar 200 (aynı gövde), farklı gövde 409 `IDEMPOTENCY_CONFLICT` |
| `POST /goods-receipts/{id}/reverse/` | İzin `purchasing.reverse_goodsreceipt`; gövde `{"reason"}`; stoğa dokunulmuşsa 409 `CONFLICT`; idempotent |
| `GET /inventory/balances/` | Malzeme başına `physical/reserved/available/unavailable` (02 §4 tanımı), taban birimde |
| `GET /inventory/lots/`, `GET …/{id}/` | Filtre `ingredient`, `quality_status`, `has_stock`; SKT'ye göre sıralı |
| `POST /inventory/lots/{id}/release/`, `…/block/` | İzin `inventory.release_lot` / `inventory.block_lot`; gerekçe zorunlu; idempotent; kalite olay günlüğüne yazar |
| `GET /inventory/movements/` | Salt okunur defter; filtre `lot`, `movement_type` |
| `POST /inventory/movements/{id}/reverse/` | İzin `inventory.adjust_stock`; bir hareket bir kez ters çevrilir |
| `POST /inventory/adjustments/` | İzin `inventory.adjust_stock`; **`Idempotency-Key` zorunlu**; `quantity` işaretli, `reason` zorunlu, `movement_type` `adjustment` (varsayılan) veya `waste` |
| `GET|POST /inventory/reservations/` | POST: tümü-ya-hiç FEFO rezervasyon; (referans, malzeme) başına idempotent — tekrar 200 aynı kayıtlar, farklı miktar 409 `IDEMPOTENCY_CONFLICT`; yetersiz stok 409 `INSUFFICIENT_STOCK` (`details`: istenen/mevcut) |
| `POST /inventory/reservations/{id}/release/`, `…/consume/` | Release idempotent; consume `{quantity?}` kısmi tüketimde kalanı serbest bırakır; bloke/süresi dolmuş lot 409 `LOT_BLOCKED`; tüketilmiş kayıt serbest bırakılamaz |

Miktarlar ondalık string (`"2000.0000"`), stok miktarları malzemenin taban biriminde; girişte herhangi uyumlu birim kabul edilir. Fazla teslimat (sipariş + %10 üstü) `409 CONFLICT`. Kimliksiz `AUTHENTICATION_REQUIRED`, yetkisiz `PERMISSION_DENIED`.

### Planlama ve üretim
- `POST /production-plans/`
- `POST /production-plans/{id}/release/`
- `GET /production-plans/{id}/`
- `POST /batches/{id}/start/`
- `POST /batches/{id}/record-consumption/`
- `POST /batches/{id}/complete/`

### Kalite ve paketleme
- `POST /batches/{id}/quality-checks/`
- `POST /quality-incidents/{id}/hold/`
- `POST /quality-incidents/{id}/release/`
- `POST /packages/{id}/pack/`

### Teslimat
- `POST /delivery-runs/`
- `POST /delivery-runs/{id}/assign/`
- `POST /delivery-stops/{id}/complete/`
- `POST /delivery-stops/{id}/fail/`

### Raporlama ve destek
- `GET /reports/daily-operations/`
- `GET /reports/inventory-expiry/`
- `POST /support/tickets/`
- `GET /support/tickets/`

Bu liste taslaktır; endpoint'ler kodlanmış kabul edilmez. Kesin OpenAPI şeması uygulama sırasında üretilmeli ve testlerle doğrulanmalıdır.

## 4. Örnek: sipariş oluşturma

Request:
```http
POST /api/v1/orders/
Idempotency-Key: <unique-key>
Content-Type: application/json
```

```json
{
  "delivery_date": "2026-10-19",
  "delivery_address_id": "uuid",
  "items": [
    {"product_id": "uuid", "quantity": 3},
    {"product_id": "uuid", "quantity": 2}
  ]
}
```

Response `201 Created`:
```json
{
  "id": "uuid",
  "order_number": "SM-20261019-0001",
  "status": "CONFIRMED",
  "currency": "SEK",
  "total_amount": "645.00",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 3,
      "unit_price": "129.00",
      "line_total": "387.00"
    }
  ]
}
```

Tutarlar sadece örnektir. Fiyat, indirim, vergi ve teslimat ücreti sunucuda hesaplanır. Uygulanan akış (ADR-014): ödeme sağlayıcısı henüz yok ve stok kontrolü eşzamanlı olduğundan sipariş, rezervasyon başarılıysa doğrudan `confirmed` olur; `PLACED`/ödeme bekleme durumu ödeme kararıyla eklenecektir.

## 5. Örnek hata

```json
{
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Yeterli kullanılabilir stok yok.",
    "details": {
      "ingredient_id": "uuid",
      "requested_quantity": "1200",
      "available_quantity": "800"
    },
    "request_id": "uuid"
  }
}
```

## 6. İşlem güvenliği

- Kritik işlemler `transaction.atomic()` içinde uygulanır.
- Eşzamanlı stok değişikliklerinde uygun satır kilidi/constraint kullanılır.
- Aynı idempotency anahtarı aynı isteğin tekrarında aynı sonucu döndürür; farklı payload ile yeniden kullanılması reddedilir.
- Liste endpoint'lerinde kullanıcının erişebileceği kayıtlar QuerySet düzeyinde filtrelenir.
- Yetkilendirme hem endpoint hem nesne/tesis kapsamı düzeyinde yapılır.
- Bildirimler transaction commit olduktan sonra gönderilir; gerekiyorsa transactional outbox kullanılır.
- API sözleşmesi değişince OpenAPI ve ilgili istemci tipleri/testleri güncellenir.

## 7. Endpoint başına zorunlu dokümantasyon

Her endpoint için:
1. Amaç
2. HTTP metodu ve path
3. Kimlik doğrulama gereksinimi
4. Rol/nesne kapsamı
5. Request şeması
6. Success response şeması
7. Olası hata kodları
8. Transaction ve yan etkiler
9. Idempotency/tekrar davranışı
10. Test senaryoları

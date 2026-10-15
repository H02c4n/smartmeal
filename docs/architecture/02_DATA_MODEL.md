# 02 — Veri Modeli

Bu doküman ilk mantıksal modeldir. Alan türleri, null kuralları, indeksler ve kesin foreign key davranışları model geliştirilirken migration ve testlerle kesinleştirilir.

## 1. Ortak standartlar

- Birincil anahtar: tercihen UUID; karar tüm projede tutarlı uygulanır.
- Tarih/saat: veritabanında timezone-aware zamanlar; API'de ISO 8601.
- Para: `Decimal` / PostgreSQL `NUMERIC`, ayrıca ISO para birimi kodu.
- Miktarlar: kesin decimal veya alanın doğasına uygun integer; ölçü birimi açıkça saklanır.
- Genel alanlar: `created_at`, `updated_at`; kritik işlemlerde aktör.
- Geçmişi koruma: sipariş fiyatı ve kullanılan reçete sürümü snapshot olarak saklanır.
- İşlem defterleri: stok hareketleri gibi kayıtlar olağan akışta silinmez; ters kayıtla düzeltilir.

## 2. Kimlik ve erişim

### `User`
Önerilen alanlar: `id`, `email`, `phone`, `password_hash` (Django yönetir), `is_active`, `created_at`, `updated_at`.

Django custom user modeli ilk migration'dan önce oluşturulmalıdır.

### `RoleAssignment`
Alanlar: `id`, `user_id`, `role_code`, `site_id` (tesis kapsamı gerekiyorsa), `created_at`.

Roller örnek: `CUSTOMER`, `ADMIN`, `PLANNER`, `PURCHASING`, `PRODUCTION`, `QUALITY`, `PACKING`, `DRIVER`, `SUPPORT`, `FINANCE`. Gerçek yetkiler role adıyla sınırlı kalmamalı; işlem ve nesne kapsamı da kontrol edilmelidir.

## 3. Katalog ve reçete

### `Unit` (birim sözlüğü — ADR-011)
`id`, `code` (benzersiz, `[a-z]{1,16}`), `name`, `dimension` (`mass` / `volume` / `count`), `factor_to_base` (`NUMERIC(20,9)`, `> 0`).
`factor_to_base`, birimin boyutunun taban birimine (g, ml, pcs) çarpanıdır; boyut başına tam bir taban birim (çarpan 1) DB kısmi benzersiz indeksiyle zorlanır. Tohum (migration `catalog.0002`): `g`, `kg`, `ml`, `l`, `pcs`. Mutfak ölçüleri (çay/yemek kaşığı, bardak) kapsam dışıdır. Salt okunur referans veridir; değişiklik migration ile yapılır.

### `IngredientUnitConversion`
`id`, `ingredient_id`, `unit_id`, `base_unit_quantity` (`NUMERIC(20,9)`, `> 0`). Anlam: `1 <unit> = base_unit_quantity × ingredient.base_unit`. Yalnızca **boyutlar arası** (hacim↔ağırlık, adet↔ağırlık) ve malzemeye özeldir; (`ingredient`, `unit`) benzersiz, malzeme başına boyut başına en fazla bir kayıt (model `clean()`/servis ile; DB kısıtı değil). Aynı boyut içi dönüşüm `Unit.factor_to_base` ile yapılır.

### `Ingredient`
`id`, `sku`, `name`, `base_unit` (FK → `Unit`, `PROTECT`; taban birim olmalı, oluşturulduktan sonra **değişmez**), `is_active`. `sku`: büyük harfe normalize, `^[A-Z0-9_-]{2,40}$` (DB CHECK), benzersiz, değişmez. Fiziksel silme yok; `is_active=false` ile pasife alınır. `waste_factor` malzemede **yoktur** (yalnızca `RecipeLine`'da, bkz. ADR-011).

### `Product`
`id`, `sku`, `name`, `description`, `price` (`NUMERIC(12,2)`, `>= 0`), `currency` (3 harf `^[A-Z]{3}$`, varsayılan yok, ISO 4217 listesiyle eşleştirilmez), `is_active`. SKU kuralları Ingredient ile aynıdır. Vergi modellenmez (açık karar, 00 §8). `allergen_information` veya ilişkili alerjen kayıtları ayrı görevde gelir; bu modelde şimdilik alan yoktur.

### `Allergen` ve `IngredientAllergen` (ADR-012)
`Allergen`: `id`, `code` (`^[a-z][a-z0-9_]{1,31}$`, benzersiz, değişmez), `name`, `is_active`. **Migration ile tohumlanmaz**: hangi alerjenlerin beyan edileceği ülkeye/ürüne göre değişir (05 §4); liste işletme tarafından yönetilir. `IngredientAllergen`: `ingredient`, `allergen`, `presence` (`contains` | `may_contain`); (`ingredient`, `allergen`) benzersiz. Malzeme beyanı API'de PUT ile bütün olarak değiştirilir. Reçete alerjen özeti, malzeme beyanlarından türetilir (`contains` > `may_contain`); pasifleştirilen alerjen mevcut reçetelerde **görünmeye devam eder**. Bu özet yasal etiket değildir.

### `RecipeVersion` (ADR-012)
`id`, `product`, `version_number` (ürün başına 1, 2, 3…; yeniden kullanılmaz), `yield_quantity` (`> 0`), `yield_unit`, `status` (`draft` → `approved` → `retired`), `effective_from`, `effective_to`, `approved_at`, `approved_by`, `retired_at`, `retired_by`. Ürün başına **aynı anda en çok bir `approved`** sürüm (kısmi benzersiz indeks). Yeni sürümü onaylamak eskisini aynı transaction'da `retired` yapar. `draft` dışında verim alanları ve satırlar değişmez (model `save()`/`delete()` korumaları + servis; `QuerySet.update()` bunları aşar, bu yüzden yazma yalnızca `recipes.services` üzerinden).

### `RecipeLine`
`id`, `recipe_version`, `ingredient`, `quantity` (`> 0`, net), `unit`, `waste_factor` (`0 ≤ w < 1`, varsayılan 0), `net_base_quantity`, `gross_base_quantity`. Son ikisi taslakta `NULL`; **onayda bir kez** malzemenin taban birimine hesaplanıp dondurulur (`gross = net ÷ (1 − waste)`, ham net'ten tek yuvarlama). Böylece `IngredientUnitConversion` sonradan değişse de onaylı reçetenin anlamı değişmez (ADR-011 riski kapatıldı).

Reçete sürümleri yayımlandıktan sonra geçmiş sipariş/üretim kayıtları için değiştirilmemelidir; değişiklik yeni sürüm oluşturur.

**Miktar hesabı politikası (ADR-011):** miktar alanları `NUMERIC(14,4)`; hesaplamada float yok, ara adımlarda yuvarlama yok, sonuç bir kez `ROUND_HALF_UP` ile 4 ondalığa yuvarlanır (`catalog.services.convert_quantity`). Fire formülü (yalnızca `RecipeLine`'da): `brüt = net ÷ (1 − fire)`, `0 ≤ fire < 1`; bu görevde uygulanmadı, RecipeLine görevinde uygulanacak.

## 4. Tedarik ve stok

> **Faz 2 uygulandı (ADR-012, onaylandı).** Aşağıdaki alanlar koddaki gerçek modellerdir. Tüm stok miktarları malzemenin **taban biriminde** tutulur; girişler servis sınırında `convert_quantity` ile dönüştürülür. Tesis (`site_id`) **yoktur**: tesis sayısı açık karardır (00 §8), tek tesis varsayıldı; çoklu tesis gerekirse migration ile eklenir.

### `Supplier`
`id`, `name` (büyük/küçük harf duyarsız benzersiz), `contact_details`, `is_active`. Silinmez; pasife alınır.

### `PurchaseOrder`
`id`, `po_number` (benzersiz, üretilir), `supplier`, `status` (`draft` → `submitted` → `partially_received` → `received`; `draft`/`submitted` → `cancelled`), `currency`, `ordered_at`, `expected_at`, `created_by`, `cancelled_at`. Yalnızca `draft` düzenlenir. Kısmen/tamamen alınmış sipariş iptal edilemez.

### `PurchaseOrderLine`
`id`, `purchase_order`, `ingredient`, `ordered_quantity`, `unit`, `ordered_base_quantity`, `received_base_quantity`, `unit_cost`. (sipariş, malzeme) benzersiz.

### `GoodsReceipt`
`id`, `purchase_order`, `status` (`posted` | `reversed`), `received_at`, `received_by`, `reversed_at/by`, `reversal_reason`. Atomik: satırlar, lotlar, `RECEIPT` hareketleri ve sipariş miktarları birlikte yazılır. Satır başına fazla teslimat toleransı %10 (`PO_OVER_RECEIPT_TOLERANCE`, **geçici varsayım**).

### `GoodsReceiptLine`
`id`, `goods_receipt`, `po_line`, `ingredient`, `received_quantity`, `unit`, `received_base_quantity`, `supplier_lot_code` (zorunlu), `expiry_date` (zorunlu, geçmiş olamaz).

### `InventoryLot`
`id`, `ingredient`, `supplier`, `receipt_line` (1-1), `supplier_lot_code`, `internal_lot_code` (benzersiz), `received_at`, `expiry_date`, `quality_status` (`pending` → `released` ⇄ `blocked`), `initial_quantity`, `on_hand`, `reserved`. `on_hand`/`reserved` projeksiyondur ve DB kısıtlarıyla korunur: `on_hand ≥ 0`, `reserved ≥ 0`, **`reserved ≤ on_hand`**. Tedarikçi lot kodu tedarikçiler arasında tekrar edebilir (benzersiz olan dahili koddur). Kabul edilen lot `pending` başlar (05 §4).

### `LotQualityEvent`
Kalite durum değişikliklerinin yalnızca-ekleme günlüğü (`lot`, `from_status`, `to_status`, `reason` zorunlu, `actor`). `audit` modülü gelene kadar yerini tutar.

### `StockMovement`
`id`, `lot`, `movement_type` (`receipt`, `consumption`, `adjustment`, `waste`, `return`, `reversal`), `quantity_delta`, `unit`, `balance_after`, `reference_type`, `reference_id`, `occurred_at`, `actor`, `reason`, `reverses` (1-1, kendisine). **Yalnızca ekleme** (`save`/`delete` engelli). DB kısıtları: delta ≠ 0; işaret türe uygun (receipt/return +, consumption/waste −); `adjustment`/`waste`/`reversal` için gerekçe zorunlu; `reversal` ⇔ `reverses` dolu. Bir hareket yalnızca bir kez ters çevrilir; `reversal` ters çevrilemez.

### `StockReservation`
`id`, `lot`, `quantity`, `status` (`active` | `released` | `consumed`), `reference_type`, `reference_id` (tüketici: sipariş/üretim; FK yok çünkü tablolar henüz yok), `expires_at`, `released_at`, `consumed_at`, `consumed_quantity`. **Lot bazlı** (FEFO ve izlenebilirlik için). (lot, referans) için tek aktif kayıt (kısmi benzersiz indeks) — aynı isteği tekrarlamak yeni kayıt açmaz. Bir tüketici bir malzeme için birden fazla lottan satır alabilir.

### `IdempotencyRecord` (`core`)
`scope`, `key`, `actor`, `request_hash`, `resource_id`, `expires_at` (7 gün). (scope, key, actor) benzersiz. Aynı anahtar + aynı gövde → ilk sonuç (200); aynı anahtar + farklı gövde → `IDEMPOTENCY_CONFLICT`. Kayıt, işlemle **aynı transaction'da** yazılır: başarısız istek kayıt bırakmaz, yeniden denenebilir.

### Stok hesapları (uygulanan tanım — tüm modüllerde `inventory.selectors.stock_levels`)
Malzeme başına, taban birimde:
- `physical = Σ on_hand` (pending/blocked/süresi dolmuş lotlar dahil)
- `reserved = Σ reserved`
- `available = Σ (on_hand − reserved)` yalnızca **released ve SKT'si geçmemiş** lotlarda (SKT günü hâlâ kullanılabilir)
- `unavailable = Σ (on_hand − reserved)` pending, blocked veya süresi dolmuş lotlarda
- Değişmez: `physical = reserved + available + unavailable`.
- `on_hand` ve `reserved` projeksiyondur; `selectors.reconcile()` / `manage.py reconcile_inventory` bunları hareket defteri ve aktif rezervasyonlarla karşılaştırır (tutarsızlıkta hata kodu ile çıkar).
- **FEFO:** rezervasyon yalnızca released, süresi dolmamış ve boş miktarı olan lotlardan, en erken SKT → kabul zamanı → id sırasıyla tahsis edilir. `use_by_on_or_after` ile asgari raf ömrü payı istenebilir. İş/kalite politikasıyla (gerçek raf ömrü kuralları) hâlâ doğrulanmalıdır.
- **Kilitleme:** değiştirilen her lot `SELECT … FOR UPDATE` ile kilitlenir; birden çok lot birincil anahtar sırasıyla kilitlenir (kilitlenme olmaz). Rezervasyon ayrıca (tüketici, malzeme) başına `pg_advisory_xact_lock` alır; aynı isteğin paralel tekrarları tek rezervasyon üretir.

## 5. Sipariş

### `Order`
`id`, `order_number`, `customer_id`, `status`, `delivery_date`, `delivery_address_snapshot`, `currency`, `subtotal`, `tax_amount`, `delivery_fee`, `total_amount`, `created_at`, `confirmed_at`, `cancelled_at`.

Adres snapshot'ı, müşteri adresini sonradan değiştirse bile geçmiş siparişin teslimat adresini korur.

### `OrderLine`
`id`, `order_id`, `product_id`, `product_name_snapshot`, `quantity`, `unit_price`, `line_total`, `recipe_version_id`.

### `Payment`
`id`, `order_id`, `provider`, `provider_reference`, `status`, `amount`, `currency`, `created_at`.

Kart numarası/CVV gibi ödeme kartı verileri SmartMeal veritabanında saklanmaz. Sağlayıcı ve PCI kapsamı ayrıca belirlenir.

## 6. Planlama ve üretim

### `ProductionPlan`
`id`, `production_date`, `site_id`, `status`, `created_by`, `released_at`.

### `ProductionBatch`
`id`, `plan_id`, `product_id`, `recipe_version_id`, `planned_quantity`, `actual_quantity`, `waste_quantity`, `status`, `started_at`, `completed_at`.

### `BatchIngredient`
`id`, `batch_id`, `lot_id`, `planned_quantity`, `actual_quantity`, `unit`.

Bu ilişki, üretim partisinin hangi lotlardan ne kadar kullandığını izler.

### `ProductionTask`
`id`, `batch_id`, `task_type`, `assigned_to`, `status`, `started_at`, `completed_at`.

## 7. Kalite, paketleme ve teslimat

### `QualityCheck`
`id`, `batch_id` veya `lot_id`, `check_type`, `result`, `measurement_value`, `unit`, `checked_by`, `checked_at`, `notes`.

### `QualityIncident`
`id`, `object_type`, `object_id`, `severity`, `status`, `reason`, `reported_by`, `resolved_by`, `resolved_at`.

### `Package`
`id`, `order_id`, `package_code`, `status`, `packed_by`, `packed_at`.

Bir sipariş birden fazla pakete ayrılabilir. Paket/üretim partisi ilişkisi gerekiyorsa `PackageLine` veya `PackageBatch` ilişkisi eklenir.

### `DeliveryRun`
`id`, `delivery_date`, `driver_id`, `status`, `started_at`, `completed_at`.

### `DeliveryStop`
`id`, `run_id`, `order_id`, `sequence_number`, `status`, `delivered_at`, `failure_reason`, `proof_reference`.

Fotoğraf ve konum kanıtlarının saklama ve erişim politikası belirlenmelidir.

## 8. Denetim ve idempotency

### `AuditEvent`
`id`, `actor_id`, `action`, `object_type`, `object_id`, `reason`, `request_id`, `created_at`, güvenli ve sınırlı metadata.

### `IdempotencyRecord`
`id`, `key`, `actor_id`/istemci kapsamı, `request_hash`, `response_status`, `response_body` veya sonuç referansı, `created_at`, `expires_at`.

Idempotency anahtarı kapsamı ve saklama süresi tanımlanmalı; aynı anahtar farklı gövdeyle kullanılırsa istek reddedilmelidir.

## 9. İlişki özeti

- `Product 1—N RecipeVersion`
- `RecipeVersion 1—N RecipeLine`
- `Ingredient 1—N InventoryLot`
- `InventoryLot 1—N StockMovement`
- `Order 1—N OrderLine`
- `Order 1—N StockReservation`
- `ProductionPlan 1—N ProductionBatch`
- `ProductionBatch 1—N BatchIngredient`
- `ProductionBatch 1—N QualityCheck`
- `Order 1—N Package`
- `DeliveryRun 1—N DeliveryStop`

## 10. Durum makinesi ilkeleri

Sipariş, satın alma siparişi, üretim partisi, kalite kontrolü, paket ve teslimat için ayrı durum makinesi tanımlanır. Geçişler merkezi servislerde doğrulanır. Geçersiz geçişler `409 Conflict` veya uygun doğrulama hatasıyla reddedilir. Durum adları API'de sabit enum/string sözleşmesi olarak belgelenir.

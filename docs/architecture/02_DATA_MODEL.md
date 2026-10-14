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

### `RecipeVersion`
`id`, `product_id`, `version_number`, `yield_quantity`, `yield_unit`, `status`, `effective_from`, `effective_to`, `approved_by`.

### `RecipeLine`
`id`, `recipe_version_id`, `ingredient_id`, `quantity`, `unit`, `waste_factor` (iş kuralı kesinleşirse).

Reçete sürümleri yayımlandıktan sonra geçmiş sipariş/üretim kayıtları için değiştirilmemelidir; değişiklik yeni sürüm oluşturur.

**Miktar hesabı politikası (ADR-011):** miktar alanları `NUMERIC(14,4)`; hesaplamada float yok, ara adımlarda yuvarlama yok, sonuç bir kez `ROUND_HALF_UP` ile 4 ondalığa yuvarlanır (`catalog.services.convert_quantity`). Fire formülü (yalnızca `RecipeLine`'da): `brüt = net ÷ (1 − fire)`, `0 ≤ fire < 1`; bu görevde uygulanmadı, RecipeLine görevinde uygulanacak.

## 4. Tedarik ve stok

### `Supplier`
`id`, `name`, `contact_details`, `status`.

### `PurchaseOrder`
`id`, `supplier_id`, `status`, `ordered_at`, `expected_at`, `created_by`.

### `PurchaseOrderLine`
`id`, `purchase_order_id`, `ingredient_id`, `ordered_quantity`, `unit`, `unit_cost`.

### `GoodsReceipt`
`id`, `purchase_order_id`, `received_at`, `received_by`, `status`.

### `GoodsReceiptLine`
`id`, `goods_receipt_id`, `ingredient_id`, `received_quantity`, `unit`, `supplier_lot_code`, `expiry_date`, `quality_status`.

### `InventoryLot`
`id`, `ingredient_id`, `supplier_id`, `supplier_lot_code`, `internal_lot_code`, `received_at`, `expiry_date`, `quality_status`, `site_id`.

Lot kodunun benzersizliği tedarikçi/tesis kapsamına göre tanımlanmalıdır; her tedarikçi aynı lot kodunu kullanabilir.

### `StockMovement`
`id`, `lot_id`, `movement_type`, `quantity_delta`, `unit`, `reference_type`, `reference_id`, `occurred_at`, `actor_id`, `reason`.

Hareket türleri örnek: `RECEIPT`, `CONSUMPTION`, `ADJUSTMENT`, `WASTE`, `RETURN`, `REVERSAL`. Hareketin işareti ve yönü standartlaştırılır.

### `StockReservation`
`id`, `order_id`, `ingredient_id` veya `lot_id`, `quantity`, `unit`, `status`, `expires_at`, `created_at`, `released_at`.

Rezervasyon malzeme bazında veya lot bazında tutulabilir. Lot bazlı rezervasyon FIFO/FEFO ve izlenebilirliği kolaylaştırır; seçilen yaklaşımın tüm kodda tutarlı olması gerekir.

### Stok hesapları
- Fiziksel miktar, stok hareketlerinden veya güvenilir bir bakiye projeksiyonundan hesaplanır.
- Rezerve miktar aktif rezervasyonlardan hesaplanır.
- Bloke lotlar kullanılabilir miktara dahil edilmez.
- Performans için bakiye tablosu/projeksiyonu kullanılacaksa hareket defteriyle uzlaştırma testi bulunur.
- Son kullanma tarihine göre tahsis için FEFO (ilk önce tarihi en yakın lot) varsayılan adaydır; iş/kalite kurallarıyla doğrulanmalıdır.

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

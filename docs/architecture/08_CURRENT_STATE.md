# 08 — Güncel Proje Durumu

> Bu dosya her çalışma oturumunun sonunda güncellenmelidir. Gerçek kod ve test durumu doğrulanmadan tamamlanmış gibi işaretlenmemelidir.

## Son güncelleme
- Tarih: 2026-10-14
- Güncelleyen: Faz 1 tamamlayıcıları (alerjen, reçete) + Faz 2 oturumu (tedarik ve stok), backend

## Genel durum
- [x] Faz 0 altyapısı (değişmedi)
- [x] `catalog`: Unit, IngredientUnitConversion, Ingredient, Product (Faz 1/ilk kısım) + **Allergen, IngredientAllergen** (bu oturum)
- [x] `recipes`: RecipeVersion, RecipeLine, onay/emekli, taban birim snapshot'ı, fire, ihtiyaç hesabı (bu oturum)
- [x] `purchasing`: Supplier, PurchaseOrder(+Line), GoodsReceipt(+Line) (bu oturum)
- [x] `inventory`: InventoryLot, StockMovement, StockReservation, LotQualityEvent, FEFO, kalite blokajı, uzlaştırma (bu oturum)
- [x] `core`: ortak 409 hata sınıfları, `Idempotency-Key` altyapısı, izin yardımcıları (bu oturum)
- [ ] **Hiçbir Faz 1/Faz 2 değişikliği kullanıcının Docker ortamında veya GitHub Actions'ta çalıştırılmadı.** Aşağıdaki sonuçlar sandbox'tandır.
- [ ] ADR-007…011 ve yeni **ADR-012 "Önerildi"**; onay bekliyor

## Faz durumu
- Faz 0: **Tamamlandı**
- Faz 1: **Backend tamamlandı**; kalan tek madde **Next.js Admin temel ekranları** (henüz başlanmadı)
- Faz 2: **Backend tamamlandı** (sandbox'ta doğrulandı); Docker/CI doğrulaması ve ADR-012 onayı bekliyor
- Faz 3–7: Bekliyor

## Son tamamlanan görev
1. **Alerjen:** `Allergen` (tohumsuz, kod değişmez, pasife alınır), `IngredientAllergen` (`contains`/`may_contain`), malzeme beyanını bütün olarak değiştiren `PUT`, reçete bazında türetilmiş alerjen özeti.
2. **Reçete:** sürüm numaralandırma (ürün kilidiyle), taslak düzenleme, `approve` (satırsız/pasif malzeme/dönüştürülemeyen birim reddi; miktarları taban birime dondurma; önceki onaylıyı emekli etme), `retire`, `requirements` (net/brüt ihtiyaç, ölçeklenmiş).
3. **Tedarik:** tedarikçi, sipariş durum makinesi, atomik mal kabul (lot + `RECEIPT` hareketi + sipariş miktarları), %10 fazla-teslimat toleransı, mal kabul ters kaydı.
4. **Stok:** lot (`pending` başlar), yalnızca-ekleme defter, rezervasyon (lot bazlı, FEFO, tümü-ya-hiç, idempotent, süre sonu), tüketim (`LOT_BLOCKED` kuralı), serbest bırakma/bloke (gerekçe + olay günlüğü), düzeltme ve ters hareket, bakiye tanımı (`physical = reserved + available + unavailable`), `reconcile_inventory`.
5. **Idempotency:** `core.IdempotencyRecord` + `run_idempotent`; mal kabul ve stok düzeltmede `Idempotency-Key` zorunlu.

## Aktif görev
Yok. Sıradaki: bkz. "Sonraki görev".

## Değişen dosyalar (bu oturum)
- Yeni app'ler: `backend/apps/recipes/`, `backend/apps/purchasing/`, `backend/apps/inventory/` (models, services, selectors, serializers, views, urls, admin, migrations, tests; inventory'de ayrıca `management/commands/{reconcile_inventory,release_expired_reservations}.py`)
- `backend/apps/catalog/`: `models.py` (+Allergen, IngredientAllergen), `services.py`, `selectors.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, `migrations/0003_allergens.py`, `tests/test_allergens.py`; `tests/test_django_admin.py` (yeni inline form alanları)
- `backend/apps/core/`: yeni `api_errors.py`, `idempotency.py`, `permissions.py`, `serializers.py`, `migrations/0001_idempotency.py`, `models.py` (+IdempotencyRecord), `exceptions.py` (`error.details` için `extra` desteği), `tests/test_api_errors.py`, `tests/test_idempotency.py`; `tests/test_project_setup.py` ("core tablosuzdur" testi "yalnızca IdempotencyRecord" olarak bilinçli değiştirildi)
- `backend/config/settings/base.py` (INSTALLED_APPS, `SPECTACULAR_SETTINGS.ENUM_NAME_OVERRIDES`), `backend/config/urls.py`
- `backend/pyproject.toml`: testler için ruff `F811` yok sayıldı (başka app'in fixture'larını içe aktarma)
- Belgeler: `docs/architecture/{01,02,03,06,07,08}`, `README.md`
- Değişmeyen: `uv.lock`/bağımlılıklar (yeni paket yok), Docker/CI dosyaları

## Migration durumu
- Faz 0/1: `accounts.0001`, `catalog.0001`, `catalog.0002_seed_units`
- Yeni: `catalog.0003_allergens`, `core.0001_idempotency`, `recipes.0001_initial`, `purchasing.0001_initial`, `inventory.0001_initial`, `inventory.0002_initial` (purchasing ↔ inventory FK'leri bu yüzden iki parça)
- Sandbox'ta doğrulandı: boş DB'ye `migrate`, `inventory/purchasing/recipes/core zero` ve `catalog 0002`'ye geri alma, yeniden `migrate`; `makemigrations --check --dry-run` temiz. **Kullanıcının Docker ortamında uygulanmadı.**

## Test durumu
**Sandbox** (Python 3.12.3, PostgreSQL 16, Django 5.2; bu oturumda çalıştırıldı):
- `pytest`: **414 geçti, 0 başarısız** (192 önceki + yeni catalog/core/recipes/purchasing/inventory testleri)
- `ruff check` ve `ruff format --check`: temiz
- `makemigrations --check --dry-run`: değişiklik yok
- `spectacular --validate --fail-on-warn`: geçti
- Gerçek eşzamanlılık testleri (`transaction=True`, ayrı bağlantılar/thread'ler): 20 paralel rezervasyon/1000 g stok → tam 10 başarılı; çok lotlu paralel rezervasyon; aynı tüketicinin paralel tekrarı tek rezervasyon; paralel tüketim/serbest bırakma tek etki; düzeltme ↔ rezervasyon yarışı; paralel mal kabulde fazla teslimat reddi; paralel reçete onayı sonunda tek `approved`.

**Docker (kullanıcı makinesi) ve GitHub Actions:** henüz çalıştırılmadı. Komutlar: `docker compose run --rm backend python manage.py migrate`, `… pytest`, `… ruff check .`, `… ruff format --check .`, `… python manage.py makemigrations --check --dry-run`, `… python manage.py spectacular --validate --fail-on-warn --file /dev/null`.

**Test edilmeyenler:** yük/performans (özellikle `reserve_stock`'un aday kilitleme maliyeti ~600 sipariş/hafta profilinde); gerçek oturum/CSRF akışı (testler `force_authenticate`); süre sonu rezervasyon zamanlayıcısı (yalnızca komut test edildi); yedekten geri yükleme.

## Ortamla ilgili notlar
- Windows'ta `127.0.0.1:5432` kullanılamazsa `.env` içinde `POSTGRES_HOST_PORT=55432`.
- Windows/Git Bash'te `make` yok; `docker compose run --rm backend ...` kullanılır.
- Yeni migration'lar için: `docker compose run --rm backend python manage.py migrate`.
- Yeni izinler (`inventory.adjust_stock/release_lot/block_lot`, `purchasing.reverse_goodsreceipt`) migration ile oluşur; süper kullanıcı hepsine sahiptir, diğer personel için Django admin'den atanır.

## Açık sorunlar ve ürün kararları
- **ADR-012 onayı** (özellikle: lot bazlı rezervasyon, tesis yok, %10 fazla-teslimat toleransı, `IdempotencyRecord`'un `core`'da olması). ADR-007…011 hâlâ onay bekliyor.
- **Kimlik doğrulama (ADR-010) ve roller:** tüm yeni endpoint'ler geçici `is_staff` + Django model izinleri kullanıyor; `RoleAssignment` gelince değişmeli. Oturum kimlik doğrulamasında yazma istekleri CSRF ister.
- **Rezervasyon süresi** (00 §8): ürün kararı yok; `expires_at` isteğe bağlı, zamanlayıcı yok. Faz 3'te sipariş onayı ile birlikte netleşmeli (Celery/cron gerekebilir).
- **Tesis sayısı** (00 §8): tek tesis varsayıldı.
- **Fazla teslimat toleransı %10** geçici varsayım.
- **Audit:** `audit` modülü yok; kalite değişiklikleri `LotQualityEvent`'te, stok değişiklikleri defterde. Fiyat/SKU/aktiflik ve reçete onayı için genel denetim izi yok.
- **Reçete ↔ stok bağı:** `recipes.requirements` malzeme ihtiyacını hesaplar ama stokla karşılaştırmaz/rezerve etmez; bu Faz 3/4 işi (sipariş → reçete sürümü snapshot'ı → rezervasyon).
- **Alerjen listesi** boş başlar; hangi alerjenlerin beyan edileceği ve etiket yükümlülükleri ülke/hukuk doğrulaması ister (05 §4). Türetilmiş reçete alerjen özeti yasal etiket değildir.
- Para birimi kümesi, vergi, `LANGUAGE_CODE`, üretim ayarları, ödeme sağlayıcısı, gıda güvenliği saklama süreleri, offline kapsamı, RPO/RTO, yük testi profili (değişmedi).
- Katalog/PO/lot kayıtları silinmez (PROTECT); düzeltme için pasife alma / ters kayıt kullanılır.
- Django admin: stok, reçete, PO ve mal kabul **salt okunur** (ledger/durum makinesini aşmasın diye); yalnızca tedarikçi ve alerjen/katalog kayıtları düzenlenebilir.

## Sonraki görev
1. Kullanıcı ortamında doğrulama: `migrate`, `pytest`, lint, şema (yukarıdaki komutlar) ve GitHub Actions; ADR-007…012 kararı.
2. Faz 1'in kalanı: **Next.js Admin temel ekranları** (katalog/reçete/alerjen/tedarik/stok). Ayrı bir görev olarak önce kimlik doğrulama stratejisi (ADR-010) ve `RoleAssignment` kararı gerekir.
3. Faz 3: Order/OrderLine, fiyat snapshot'ı, durum makinesi, sipariş → `reserve_stock` entegrasyonu. Önce 00 §8'deki sipariş onayı/rezervasyon süresi kararı alınmalı.

## Oturum sonu özeti
- Tamamlanan: alerjen, reçete (recipes), tedarik (purchasing), stok (inventory), ortak idempotency/hata altyapısı, belgeler
- Eklenen migration'lar: `catalog.0003_allergens`, `core.0001_idempotency`, `recipes.0001_initial`, `purchasing.0001_initial`, `inventory.0001_initial`, `inventory.0002_initial`
- Açık hatalar: bilinen yok; Docker/CI doğrulaması bekliyor
- Bu oturumda yakalanıp düzeltilen gerçek hatalar: reçete satırı CHECK kısıtının NULL durumunu kaçırması; satır değiştirirken eski satırlarla benzersizlik çakışması
- Sıradaki tek görev: Docker/CI doğrulaması + ADR-012 onayı, ardından Next.js Admin (Faz 1 kalanı)

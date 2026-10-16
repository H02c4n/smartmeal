# 08 — Güncel Proje Durumu

> Bu dosya her çalışma oturumunun sonunda güncellenmelidir. Gerçek kod ve test durumu doğrulanmadan tamamlanmış gibi işaretlenmemelidir.

## Son güncelleme
- Tarih: 2026-10-15
- Güncelleyen: ADR-013 (kimlik/roller) + Faz 3 backend (sipariş) + müşteri kaydı (ADR-015) + Next.js araç ADR'si (ADR-016), sandbox'ta test edilerek
- Önceki oturumlar: karar oturumu (ADR-007…013 onayı, 2026-10-15); Faz 1 tamamlayıcıları + Faz 2 backend (2026-10-14)

## Genel durum
- [x] Faz 0 altyapısı (değişmedi)
- [x] `catalog`: Unit, IngredientUnitConversion, Ingredient, Product (Faz 1/ilk kısım) + **Allergen, IngredientAllergen** (bu oturum)
- [x] `recipes`: RecipeVersion, RecipeLine, onay/emekli, taban birim snapshot'ı, fire, ihtiyaç hesabı (bu oturum)
- [x] `purchasing`: Supplier, PurchaseOrder(+Line), GoodsReceipt(+Line) (bu oturum)
- [x] `inventory`: InventoryLot, StockMovement, StockReservation, LotQualityEvent, FEFO, kalite blokajı, uzlaştırma (bu oturum)
- [x] `core`: ortak 409 hata sınıfları, `Idempotency-Key` altyapısı, izin yardımcıları (bu oturum)
- [x] Faz 1/Faz 2 kodu kullanıcının Docker ortamında, testlerde ve GitHub Actions'ta çalıştırıldı; **kullanıcı sonucu başarılı olarak bildirdi** (2026-10-15). Ayrıntılı çıktılar bu oturumda görülmedi; aşağıdaki sayılar sandbox'tandır.
- [x] ADR-007…012 **Onaylandı** (2026-10-15)
- [x] ADR-013 (kimlik doğrulama ve roller) **uygulandı (backend)**: `RoleAssignment`, oturum çerezi + CSRF, `/auth/csrf|login|logout/`, `/me/`, 401, giriş hız sınırı, koda sabit rol→izin tablosu
- [x] `orders` (Faz 3 backend): Order, OrderLine, OrderStatusEvent, CustomerAddress, sipariş/iptal servisleri, `/orders/*`, `/me/addresses/*`
- [x] **ADR-014 (sipariş akışı) Onaylandı** (2026-10-16, ürün sahibi); varsayımlar gerçek veriyle gözden geçirilecek
- [x] **ADR-015 (müşteri kaydı)** Onaylandı ve uygulandı (backend): `POST /auth/register/`, yalnızca `CUSTOMER` rolü, oturum açar, hız sınırlı; e-posta doğrulaması ve parola sıfırlaması yok
- [x] **ADR-016 (Next.js araçları)** Onaylandı, **uygulanmadı**: `web/` + `admin/`, pnpm workspace, aynı origin `/api` proxy (CORS yok), OpenAPI'den tip üretimi
- [x] Bu oturumun kodu kullanıcının Docker ortamında ve GitHub Actions'ta çalıştı (kullanıcı bildirimi)


## Faz durumu
- Faz 0: **Tamamlandı**
- Faz 1: **Backend tamamlandı** (kimlik ve roller dahil); kalan: **Next.js Admin temel ekranları**
- Faz 2: **Backend tamamlandı** ve doğrulandı
- Faz 3: **Backend uygulandı (sandbox, Docker ve GitHub Actions'ta doğrulandı), ADR-014 onaylandı**; kalan: **Next.js müşteri web akışı** (ADR-016 ile araçlar belli)
- Faz 4–7: Bekliyor

## Son tamamlanan görev
1. **ADR-013 backend:** `accounts.RoleAssignment`; `apps/accounts/roles.py` (roller, izin kodları, sabit ve değişmez rol→izin tablosu); `GET /auth/csrf/`, `POST /auth/login/` (CSRF zorunlu, oturum anahtarı yenilenir, tek tip hata, hız sınırı), `POST /auth/logout/`, `GET /me/`; kimliksiz istek 401 (`SessionAuthentication401`); `core.permissions.has_permission / has_permission_by_method`; purchasing ve inventory view'ları ile `IsCatalogAdmin` rol tabanlıya geçti; `IsBackOfficeStaff` ve `staff_with_permission` silindi; Django admin'de kullanıcıya rol inline'ı.
2. **Faz 3 backend (ADR-014, onaylandı):** `place_order` (doğrulama → fiyat/reçete/adres snapshot'ı → malzeme bazında toplu FEFO rezervasyonu → `confirmed`, hepsi tek işlemde), `cancel_order` (rezervasyon serbest bırakma, müşteri süre sınırı, arka ofis gerekçesi, idempotent), gün bazlı sipariş numarası, durum olay günlüğü, adres defteri, müşteri/arka ofis nesne kapsamı, müşteriye stok sızıntısı yok.
3. **Müşteri kaydı (ADR-015):** `register_customer` servisi (yalnızca `CUSTOMER` rolü, yinelenen e-posta büyük/küçük harf fark etmeden reddedilir, paralel kayıtta tek hesap), parola doğrulayıcıları, telefon isteğe bağlı/benzersiz değil, adres başına `5/saat`, kayıt sonrası oturum açma.
4. **Gerçek hata düzeltmesi:** `create_address` gerçek oturum kullanıcısıyla (`request.user` lazy nesne) 500 veriyordu; önceki testler `force_authenticate` kullandığı için kaçırılmıştı. Düzeltildi ve gerçek-oturum regresyon testi eklendi.
5. Önceki oturumlar: alerjen, reçete, tedarik, stok, idempotency (değişmedi).

## Aktif görev
Yok. Sıradaki: bkz. "Sonraki görev".

## Değişen dosyalar (bu oturum)
- Yeni: `backend/apps/orders/` (models, services, selectors, serializers, views, urls, admin, `migrations/0001_initial.py`, tests: `conftest`, `test_services`, `test_api`, `test_concurrency`)
- Yeni (accounts): `roles.py`, `authentication.py`, `throttles.py`, `serializers.py`, `views.py`, `urls.py`, `schema.py`, `services.py` (kayıt), `migrations/0002_roleassignment.py`, `tests/{test_roles,test_auth_api,test_register}.py`; değişen: `models.py` (+RoleAssignment), `admin.py` (rol inline'ı), `apps.py` (OpenAPI uzantısı), `tests/test_admin.py`
- Değişen (core): `permissions.py` (yeniden yazıldı); yeni `tests/test_role_permissions.py` (rol × endpoint erişim matrisi)
- Değişen: `catalog/permissions.py`, `purchasing/views.py`, `inventory/views.py`, `purchasing/tests/{test_api,conftest}.py`, `inventory/tests/{conftest,test_api}.py`, kök `conftest.py` (rol fixture'ları, önbellek temizliği)
- `backend/config/settings/base.py` (kimlik doğrulama sınıfı, hız sınırları: giriş ve kayıt, çerez/CSRF ayarları, `ORDER_*`/`ADDRESS_*` ayarları, `apps.orders`, `OrderStatusEnum`), `settings/local.py` (çerezler Secure değil), `config/urls.py`
- Düzeltme: `orders/services.py` (`create_address` lazy kullanıcı), `orders/tests/test_api.py` (gerçek oturum testi)
- Belgeler: `docs/architecture/{02,03,05,06,07,08}`
- Değişmeyen: bağımlılıklar/`uv.lock` (yeni paket yok), Docker/CI dosyaları

## Migration durumu
- Önceki: `accounts.0001`, `catalog.0001–0003`, `core.0001_idempotency`, `recipes.0001`, `purchasing.0001`, `inventory.0001–0002`
- Yeni: `accounts.0002_roleassignment`, `orders.0001_initial`
- Sandbox'ta: boş DB'ye tüm migration'lar uygulandı (test veritabanı oluşturuldu); `makemigrations --check --dry-run` temiz. Geri alma (zero) bu oturumda **denenmedi**. **Kullanıcının Docker ortamında uygulanmadı.**

## Test durumu
**Sandbox** (Python 3.12.3, PostgreSQL 16, Django 5.2; bu oturumda çalıştırıldı):
- `pytest`: **660 geçti, 0 başarısız** (önceki 414 + roller/kimlik/erişim matrisi + orders + kayıt)
- `ruff check` ve `ruff format --check`: temiz
- `makemigrations --check --dry-run`: değişiklik yok
- `spectacular --validate --fail-on-warn`: geçti
- Yeni test alanları: rol→izin tablosu (onaylı satırlar dahil); giriş/çıkış/`me`, tek tip giriş hatası, CSRF (anonim giriş ve oturumlu yazma), oturum anahtarı yenileme, adres/e-posta hız sınırı; rol × endpoint okuma/yazma matrisi; kimliksiz 401 / yetkisiz 403 / başkasının nesnesi 404; sipariş fiyat/reçete/adres snapshot'ı, toplu rezervasyon, hepsi-ya-hiç geri alma (deterministik malzeme sırasıyla), idempotent tekrar ve çakışma, stok sızıntısı yok, iptal (süre sınırı, arka ofis gerekçesi, rezervasyon iadesi); kayıt (rol sızdırma yok, parola/e-posta/telefon doğrulama, CSRF, hız sınırı, paralel kayıtta tek hesap); gerçek eşzamanlılık: 15 paralel sipariş/1000 g stok → tam 5 başarılı ve tutarlı sipariş numaraları, 6 paralel iptal → tek etki.

**Docker (kullanıcı makinesi) ve GitHub Actions:** `migrate` başarılı; `docker compose run --rm backend pytest -q` → **660 geçti** (kullanıcı çıktısı, sandbox ile aynı sayı); lint/format/migration/şema komutları ve GitHub Actions **başarılı** (kullanıcı bildirimi, 2026-10-16; ayrıntılı çıktılar görülmedi).

**Test edilmeyenler:** tarayıcıdan gerçek oturum/CSRF akışı (testler Django/DRF istemcisiyle; çerez bayrakları yanıtta kontrol edildi); birden çok süreçte hız sınırı (yerel önbellek); yük/performans (`reserve_stock` aday kilitleme maliyeti, ~600 sipariş/hafta); süre sonu rezervasyon zamanlayıcısı; yedekten geri yükleme; `orders` migration geri alma.

## Ortamla ilgili notlar
- Windows'ta `127.0.0.1:5432` kullanılamazsa `.env` içinde `POSTGRES_HOST_PORT=55432`.
- Windows/Git Bash'te `make` yok; `docker compose run --rm backend ...` kullanılır.
- Yeni migration'lar için: `docker compose run --rm backend python manage.py migrate`.
- API yetkisi artık rol tabanlı (ADR-013): ilk `ADMIN` için `docker compose run --rm backend python manage.py createsuperuser`, sonra Django admin'de kullanıcının sayfasından rol (inline) ekleyin. Süper kullanıcı bayrağı API'de yetki vermez. Eski Django model izinleri (`inventory.adjust_stock` vb.) modellerde durur ama API kullanmaz.


## Açık sorunlar ve ürün kararları
- ADR-007…012 onaylandı. Gözden geçirilecek varsayım: %10 fazla-teslimat toleransı (gerçek tedarikçi verisiyle).
- **Kimlik ve roller: uygulandı (ADR-013).** Tablonun ürün sahibinin vermediği satırları onun bıraktığı yetkiyle belirlendi (05 §1). İlk `ADMIN` Django admin'de rol verilerek oluşturulur (süper kullanıcı API'de yetkisizdir). Rol değişikliği denetim izi yok. **CORS yok** ve gerekmeyecek (ADR-016: aynı origin proxy). Hız sınırı için çok süreçte Redis gerekir. Personel MFA Faz 7 öncesi hedef.
- **ADR-014 onaylı; çalışma varsayımları gözden geçirilecek:** onay anında rezervasyon (süre/zamanlayıcı yok); sipariş adedi = 1 `pcs`, adet-bazlı reçete şart; teslimat en erken yarın; müşteri iptali teslimattan ≥1 gün önce, arka ofis gerekçeyle her zaman; vergi ve teslimat ücreti `0`; ödeme yok (`pending_payment` durumu ödeme kararıyla gelecek).
- **E-posta doğrulaması ve parola sıfırlama (ADR-015):** yok; ikisi de e-posta altyapısı ister (Faz 6 bildirimleri). **Parolasını unutan müşteri hesabına dönemez; pilot öncesi zorunlu.** Kayıt, bir e-postanın kayıtlı olduğunu gizleyemez (hız sınırıyla azaltıldı).
- **Teslimat bölgesi/günleri/saat pencereleri** doğrulanmıyor (00 §8).
- **Tesis sayısı** (00 §8): tek tesis varsayıldı.
- **Fazla teslimat toleransı %10** geçici varsayım.
- **Audit:** `audit` modülü yok; kalite değişiklikleri `LotQualityEvent`'te, stok değişiklikleri defterde. Fiyat/SKU/aktiflik ve reçete onayı için genel denetim izi yok.
- **Reçete ↔ stok bağı:** sipariş artık onaylı reçete sürümünü dondurur ve ihtiyacı rezerve eder (ADR-014). Üretim planında gerçekleşen tüketim ve rezervasyon bağlantısı Faz 4.
- **Alerjen listesi** boş başlar; hangi alerjenlerin beyan edileceği ve etiket yükümlülükleri ülke/hukuk doğrulaması ister (05 §4). Türetilmiş reçete alerjen özeti yasal etiket değildir.
- Para birimi kümesi, vergi, `LANGUAGE_CODE`, üretim ayarları, ödeme sağlayıcısı, gıda güvenliği saklama süreleri, offline kapsamı, RPO/RTO, yük testi profili (değişmedi).
- Katalog/PO/lot kayıtları silinmez (PROTECT); düzeltme için pasife alma / ters kayıt kullanılır.
- Django admin: stok, reçete, PO ve mal kabul **salt okunur** (ledger/durum makinesini aşmasın diye); yalnızca tedarikçi ve alerjen/katalog kayıtları düzenlenebilir.


## Sonraki görev
1. ~~Docker/CI doğrulaması~~ **Tamamlandı** (kullanıcı bildirimi, 2026-10-16).
2. **Next.js iskeleti (ADR-016):** pnpm workspace, `web/` ve `admin/`, `packages/api-client` (OpenAPI'den tip üretimi), `/api` rewrite, CI'ya Node job'ı. Önce giriş/kayıt ve `/me/` ile rol bazlı kabuk; sonra Admin katalog ekranları ve müşteri sipariş akışı.
3. Faz 4 hazırlığı: sipariş talep özeti (teslimat tarihine göre `confirmed` siparişlerin toplam ihtiyacı).
4. Pilot öncesi zorunlular: e-posta doğrulama + parola sıfırlama (Faz 6 bildirimleri), personel MFA, ödeme kararı.

## Oturum sonu özeti
- Tamamlanan: ADR-013 backend (roller, oturum, hız sınırı, 401, rol tabanlı izinler), Faz 3 backend (sipariş/iptal/adres, rezervasyon), müşteri kaydı (ADR-015), Next.js araç kararı (ADR-016); belgeler
- Eklenen migration'lar: `accounts.0002_roleassignment`, `orders.0001_initial`
- Açık hatalar: bilinen yok; Docker ve GitHub Actions doğrulandı (kullanıcı bildirimi)
- Bu oturumda yakalanıp düzeltilen gerçek hatalar: `login()` aynı kullanıcının oturumunu yenilemez (oturum sabitleme testi anonim oturumla yeniden yazıldı); Django admin kullanıcı ekleme formu yeni rol inline'ının yönetim alanlarını istiyor
- Sıradaki: Next.js iskeleti (ADR-016), ayrı bir sohbette; başlangıç talimatı `docs/architecture/NEXTJS_CHAT_START_PROMPT.md`

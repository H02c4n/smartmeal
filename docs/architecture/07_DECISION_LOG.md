# 07 — Mimari Karar Kaydı (Decision Log)

Bu dosyaya mimari etkisi olan kararlar eklenir. Bir karar değiştiğinde eski kayıt silinmez; yeni kayıt önceki karara referans verir.

## ADR-001 — Backend Django + DRF
- **Durum:** Onaylandı
- **Karar:** Python Django ve Django REST Framework kullanılır.
- **Gerekçe:** Olgun backend altyapısı, ORM, migration, kimlik ve API ekosistemi.
- **Etkiler:** İş kuralları, API ve veri doğruluğu backend'de uygulanır.

## ADR-002 — PostgreSQL
- **Durum:** Onaylandı
- **Karar:** Ana ilişkisel veritabanı PostgreSQL.
- **Gerekçe:** Transaction, ilişkisel bütünlük, indeksleme ve güvenilir veri modeli.
- **Etkiler:** Stok/sipariş kritik işlemleri transaction ve kısıtlarla tasarlanır.

## ADR-003 — Next.js + TypeScript
- **Durum:** Onaylandı
- **Karar:** Müşteri web sitesi ve özel Admin Next.js + TypeScript kullanır.
- **Etkiler:** İki web uygulaması ortak API'yi kullanır; Admin özel operasyon UX'i sağlar.

## ADR-004 — İki ayrı React Native uygulaması
- **Durum:** Onaylandı
- **Karar:** Müşteri ve operasyon uygulamaları ayrı ürün/dağıtım olarak geliştirilir.
- **Etkiler:** Ortak tip ve yardımcı kod paylaşılabilir; izin/navigasyon akışları ayrıdır.

## ADR-005 — Docker Compose ile yerel geliştirme
- **Durum:** Onaylandı
- **Karar:** Yerel geliştirme Docker Compose ve PostgreSQL ile başlar.
- **Etkiler:** Kurulum tekrarlanabilir olur; üretim dağıtımı ayrı karardır.

## ADR-006 — Modüler monolit
- **Durum:** Onaylandı
- **Karar:** İlk sürüm tek Django backend dağıtımı; iş alanları ayrı Django apps.
- **Gerekçe:** İlk hacimde mikroservis operasyon maliyetinden kaçınmak.
- **Etkiler:** Modül sınırları açık tutulur; bağımsız servis ihtiyacı ölçümle değerlendirilir.

## ADR-007 — UUID birincil anahtar (domain modelleri)
- **Tarih:** 2026-10-13
- **Durum:** Onaylandı (2026-10-15; ürün sahibi, Faz 0 uygulamasıyla birlikte; Docker ve CI doğrulaması kullanıcı tarafından bildirildi)
- **Bağlam:** `02_DATA_MODEL.md` §1 "tercihen UUID, tüm projede tutarlı" diyor; karar verilmesi gerekiyordu.
- **Karar:** Tüm SmartMeal domain modelleri `apps.core.models.UUIDTimestampedModel` (UUIDv4 `id`, `created_at`, `updated_at`) üzerinden türer. Django'nun kendi tabloları (Group, Permission vb.) `BigAutoField` kalır.
- **Alternatifler:** BigAutoField; UUIDv7 (Python 3.12 standart kütüphanesinde yok).
- **Gerekçe:** Tahmin edilemeyen kimlikler (API'de numaralandırma riskini azaltır), mobil/offline istemcilerde kimlik üretimi, modüller arası tutarlılık. ~600 sipariş/hafta ölçeğinde UUIDv4 indeks maliyeti kabul edilebilir; ölçümle doğrulanmalı.
- **Etkilenen modüller/dosyalar:** `apps/core/models.py`, `apps/accounts/models.py`, tüm gelecek modeller.
- **Migration/API etkisi:** `User.id` UUID. Sonradan PK tipini değiştirmek zor olduğundan Faz 0'da karar verildi.
- **Geri dönüş planı:** Henüz veri yok; Faz 1'den önce değiştirmek ucuz, sonrasında maliyetli.

## ADR-008 — Araç ve sürüm seçimleri
- **Tarih:** 2026-10-13
- **Durum:** Onaylandı (2026-10-15; ürün sahibi, Faz 0 uygulamasıyla birlikte; Docker ve CI doğrulaması kullanıcı tarafından bildirildi)
- **Karar:** Python 3.12; Django 5.2 LTS (`>=5.2,<5.3`); DRF; drf-spectacular (OpenAPI); psycopg 3 (binary); django-environ; PostgreSQL 16; paket yönetimi **uv** (`pyproject.toml` + `uv.lock`, CI'da `--frozen`); test **pytest + pytest-django**; lint/format **ruff**.
- **Alternatifler:** Django 6.x (daha yeni, LTS değil); pip-tools/Poetry; black+flake8.
- **Gerekçe:** LTS ile destek penceresi ve kararlılık; tek araçla lint+format; kilit dosyası ile tekrarlanabilir kurulum (00_PROJECT_MASTER §2 sürümlerin lockfile'a sabitlenmesini şart koşar).
- **Etkilenen dosyalar:** `backend/pyproject.toml`, `backend/uv.lock`, `backend/Dockerfile`, `.github/workflows/ci.yml`.
- **Geri dönüş planı:** Araçlar birbirinden bağımsız değiştirilebilir; uygulama kodu araçlara bağımlı değildir.

## ADR-009 — Custom User modeli kapsamı
- **Tarih:** 2026-10-13
- **Durum:** Onaylandı (2026-10-15; ürün sahibi, Faz 0 uygulamasıyla birlikte; Docker ve CI doğrulaması kullanıcı tarafından bildirildi)
- **Karar:** `accounts.User`: UUID PK, `email` (giriş kimliği, benzersiz, **her zaman küçük harf** — manager/`save()` normalize eder, `CHECK (email = lower(email))` veritabanında zorlar), `phone` (opsiyonel, benzersiz değil), `is_active`, `is_staff`, `is_superuser`, `created_at`, `updated_at`. Ad/soyad ve iş rolleri **yoktur**; roller `RoleAssignment` ile ayrı görevde eklenir. `is_staff` yalnızca Django admin erişimidir; Django admin geliştirici aracıdır, ürün Admin'i Next.js'tir (ADR-003).
- **Alternatifler:** Postgres `citext` (ek extension gerektirir); Lower() tabanlı UniqueConstraint (Django, USERNAME_FIELD için `unique=True` ister).
- **Etkilenen dosyalar:** `apps/accounts/*`, `config/settings/base.py` (`AUTH_USER_MODEL`).
- **Migration/API etkisi:** `accounts.0001_initial` — diğer tüm migration'lardan önce, ilk migrate'ten önce üretildi.
- **Açık nokta:** Telefon benzersizliği ve ad/soyad ihtiyacı ürün kararıdır; Faz 3 (müşteri/sipariş) öncesinde netleştirilmeli.

## ADR-010 — Hata zarfı ve request_id temel altyapıda
- **Tarih:** 2026-10-13
- **Durum:** Onaylandı (2026-10-15; ürün sahibi, Faz 0 uygulamasıyla birlikte; Docker ve CI doğrulaması kullanıcı tarafından bildirildi)
- **Karar:** `03_API_CONTRACTS.md` §1/§5 sözleşmesi baştan uygulanır: her hata `{"error": {"code","message","details?","request_id"}}`; `X-Request-ID` middleware'i (istemci değeri yalnızca `[A-Za-z0-9._-]{8,64}` ise kabul, aksi halde UUID üretilir), log kayıtlarına `request_id` eklenir. DRF varsayılan izni `IsAuthenticated` (varsayılan kapalı).
- **Geçici nokta (ADR-013 ile karara bağlandı):** Kimlik doğrulama stratejisi (token/session) açıktı; ADR-013 seçti. `SessionAuthentication` **geçici yer tutucudur**; bu nedenle kimliksiz istek şimdilik 403 (`AUTHENTICATION_REQUIRED` koduyla) döner; token stratejisi seçilince 401 olacaktır. Ayrı ADR gerekir (Faz 3'ten önce, `/auth/*` endpoint'leriyle birlikte).
- **Etkilenen dosyalar:** `apps/core/{middleware,exceptions,logging,request_id}.py`.

## ADR-011 — Katalog modülü: malzeme, ürün, birim sözlüğü ve miktar politikası
- **Tarih:** 2026-10-14
- **Durum:** Onaylandı (2026-10-15; ürün sahibi; Docker ve CI doğrulaması kullanıcı tarafından bildirildi)
- **Bağlam:** 01 §3 malzemeyi `inventory`'ye, 02 §3 `Ingredient`'ı "Katalog ve reçete" altına yerleştiriyordu; birim sözlüğünün sahibi tanımsızdı; 00 §8'de reçete birimi/dönüşüm/fire politikası açık karardı.
- **Karar:**
  1. `Ingredient`, `Product`, `Unit`, `IngredientUnitConversion` `catalog` app'indedir. `inventory` (lot, hareket) ileride `catalog.Ingredient`'a bağlanır; bağımlılık yönü `inventory → catalog`, `recipes → catalog` (döngü yok). Yeni app açılmadı (00 §5 listesi değişmedi). 01 §3 tablosu buna göre not düşüldü.
  2. Birim modeli: boyut (`mass`/`volume`/`count`) + boyutun taban birimine çarpan. Metrik tohum: `g`, `kg`, `ml`, `l`, `pcs`; mutfak ölçüleri ve `mg` kapsam dışı. Birim sözlüğü salt okunur referans veridir (migration ile değişir).
  3. Boyutlar arası dönüşüm (hacim↔ağırlık, adet↔ağırlık) malzemeye özel `IngredientUnitConversion` ile; malzeme başına boyut başına en fazla bir kayıt.
  4. Her malzemenin tek taban birimi vardır (g, ml veya pcs) ve oluşturulduktan sonra değişmez.
  5. Miktar politikası: `NUMERIC(14,4)`; çarpanlar `NUMERIC(20,9)`; float yok; ara yuvarlama yok; sonuç bir kez `ROUND_HALF_UP`.
  6. Fire formülü (RecipeLine görevinde uygulanacak): verim bazlı `brüt = net ÷ (1 − fire)`, `0 ≤ fire < 1`; yalnızca `RecipeLine`'da tutulur, `Ingredient`'ta varsayılan fire yoktur.
  7. SKU: elle girilir, büyük harfe normalize, `^[A-Z0-9_-]{2,40}$`, benzersiz, değişmez; Ingredient ve Product ayrı ad alanları. Silme yok, `is_active` ile pasife alma (eylem endpoint'leriyle).
  8. `Product.price` `NUMERIC(12,2)` ve `currency` 3 harf, varsayılan yok; vergi modellenmez.
  9. Geçici yetki: katalog yazma endpoint'leri `IsCatalogAdmin` (= `is_staff`, placeholder). ADR-009 "`is_staff` yalnızca Django admin" ilkesiyle gerilim bilinçlidir; `RoleAssignment` gelince değişir.
  10. API genişletmesi: 03'teki üç endpoint'e ek olarak admin ürün/malzeme yönetimi ve salt okunur birim listesi (03 güncellendi).
- **Alternatifler:** `Ingredient`'ı `inventory`'de tutmak (01'e birebir uyumlu; birimler `catalog`'da); ayrı `units` app'i; mutfak ölçüleri tohumda; toplamsal fire formülü; malzemede varsayılan fire.
- **Gerekçe:** Ana veri (katalog) ile stok hareketlerini ayırır; bağımlılık yönü tek yönlü kalır; yeni app/ADR maliyeti yok; model sonradan app değiştirmek pahalı olduğu için şimdi karar verildi.
- **Etkilenen modüller/dosyalar:** `apps/catalog/*`, `config/settings/base.py`, `config/urls.py`, `docs/architecture/{01,02,03,06,07,08}`.
- **Migration/API etkisi:** `catalog.0001_initial`, `catalog.0002_seed_units`. Yeni endpoint'ler; mevcut sözleşme değişmedi.
- **Bilinen risk:** Bir `IngredientUnitConversion` değeri değişirse, o dönüşümü kullanan reçetelerin hesaplanan taban miktarı da değişir; onaylı reçete sürümlerinin geçmişi koruma ilkesiyle (00 §4.9) uyum için RecipeVersion onayında dönüşüm değerlerinin snapshot'lanması veya dönüşümlerin sürümlenmesi gerekecektir (RecipeLine görevinde karara bağlanmalı).
- **Geri dönüş planı:** Henüz üretim verisi yok; model/app yerleşimini şimdi değiştirmek ucuz, `Ingredient`'a bağlı tablolar (RecipeLine, Lot) gelince maliyetlidir.

## ADR-012 — Reçete sürümleri, alerjen, tedarik ve stok (Faz 1 tamamlayıcıları + Faz 2)
- **Tarih:** 2026-10-14
- **Durum:** Onaylandı (2026-10-15; ürün sahibi; Docker ve CI doğrulaması kullanıcı tarafından bildirildi). Onay notu: lot bazlı rezervasyon, tek tesis ve %10 fazla teslimat toleransı olduğu gibi kabul edildi; tolerans gerçek tedarikçi verisiyle gözden geçirilecek (ürün varsayımı).
- **Bağlam:** Faz 1'in kalan işleri (RecipeVersion/RecipeLine, alerjen) ve Faz 2 (tedarik, lot, stok defteri, rezervasyon, FEFO, kalite blokajı) için 02 §4'te açık bırakılmış seçimler (rezervasyon granülaritesi, tesis, idempotency, izin modeli) karara bağlanmalıydı. 00 §8'deki ürün kararları (rezervasyon süresi, tesis sayısı) hâlâ açık olduğundan kararlar **geri alınabilir** tutuldu.
- **Karar:**
  1. **Yeni app'ler:** `recipes`, `purchasing`, `inventory` (00 §5 listesindeki adlarla). Bağımlılık: `purchasing → inventory → catalog`, `recipes → catalog`; `inventory` → `purchasing` yalnızca FK referansıyla (içe aktarma yok).
  2. **Reçete yaşam döngüsü:** `draft → approved → retired`; ürün başına en çok bir `approved` (kısmi benzersiz indeks); yeni sürümü onaylamak eskisini emekli eder. **Onayda satır miktarları taban birime dondurulur** (ADR-011 riskinin çözümü): `IngredientUnitConversion` sonradan değişse de onaylı reçete değişmez. Fire formülü ADR-011 §6 ile uygulandı: `brüt = net ÷ (1 − fire)`, ham net'ten tek yuvarlama.
  3. **Alerjen:** `Allergen` + `IngredientAllergen` (`contains`/`may_contain`); **tohumlanmaz** (yasal liste ülkeye göre; 05 §4). Reçete özeti türetilir, yasal etiket değildir; pasif alerjen mevcut reçetelerden gizlenmez.
  4. **Stok miktarı taban birimde.** Siparişler/kabuller her birimde girilebilir, servis sınırında dönüştürülür; stok aritmetiği yalnızca taban birimde.
  5. **Defter + projeksiyon:** `StockMovement` yalnızca-ekleme; `InventoryLot.on_hand/reserved` projeksiyon, DB CHECK ile korunur (`reserved ≤ on_hand`, negatif yok). Uzlaştırma: `selectors.reconcile()` ve `reconcile_inventory` komutu.
  6. **Rezervasyon lot bazlıdır** (02 §4'teki iki seçenekten); FEFO: en erken SKT → kabul zamanı → id. Tümü-ya-hiç. (lot, referans) için tek aktif kayıt + (tüketici, malzeme) advisory kilidi ⇒ tekrar güvenli. Rezervasyon **süresi** ürün kararı olmadığı için isteğe bağlı `expires_at`; süresi dolanları bırakan `release_expired_reservations` komutu var, **zamanlayıcı yok** (Celery henüz eklenmedi).
  7. **Kalite:** kabul edilen lot `pending`; `released`/`blocked` yalnızca gerekçeyle ve olay günlüğüne yazılarak değişir; tüketim yalnızca released + SKT geçmemiş lottan (`LOT_BLOCKED`). Bloke lotun mevcut rezervasyonu kalır ama tüketilemez; serbest bırakılabilir.
  8. **Tesis yok:** tek tesis varsayıldı (`site_id` eklenmedi). Çoklu tesis kararı gelirse lot/rezervasyon/PO'ya migration ile eklenir.
  9. **Idempotency (`core.IdempotencyRecord`):** `Idempotency-Key` başlığı; (scope, key, actor) benzersiz; kayıt işlemle aynı transaction'da, 7 gün saklanır; aynı anahtar + farklı gövde ⇒ 409. Mal kabul ve stok düzeltmede **zorunlu**. `core`'un "tablosuz" kuralı bu tek tablo için bilinçli olarak gevşetildi (test güncellendi).
  10. **Geçici izin modeli:** `IsBackOfficeStaff` (`is_staff`) + 05 §1'in "özel izin" işlemleri için Django model izinleri (`inventory.adjust_stock/release_lot/block_lot`, `purchasing.reverse_goodsreceipt`). ADR-009 ile gerilim bilinçli ve geçici; `RoleAssignment` ile değişecek.
  11. **Mal kabul toleransı:** satır başına sipariş miktarının %10 üstü reddedilir (`PO_OVER_RECEIPT_TOLERANCE`). Bu bir **ürün varsayımıdır**, onay gerekir.
  12. **Hata kodları:** `INVALID_STATE_TRANSITION`, `INSUFFICIENT_STOCK`, `LOT_BLOCKED`, `IDEMPOTENCY_CONFLICT`, `CONFLICT` — hepsi 409, 03 §2 ile uyumlu; `details` ile sayısal bağlam taşıyabilir.
- **Alternatifler:** malzeme bazlı rezervasyon (izlenebilirlik sonraya kalır); stoku bakiye tablosu yerine yalnızca defterden toplamak (okuma maliyeti); tesis modelini baştan eklemek; idempotency için yanıt gövdesi saklamak (kaynak referansı seçildi: yeniden oynatma güncel durumu döner).
- **Etkilenen modüller/dosyalar:** `apps/{recipes,purchasing,inventory}/*`, `apps/catalog` (alerjen), `apps/core` (`api_errors`, `idempotency`, `permissions`, `serializers`, `IdempotencyRecord`), `config/settings/base.py`, `config/urls.py`, `docs/architecture/{01,02,03,06,07,08}`, `README.md`.
- **Migration/API etkisi:** `catalog.0003_allergens`, `core.0001_idempotency`, `recipes.0001_initial`, `purchasing.0001_initial`, `inventory.0001_initial`, `inventory.0002_initial`. Yeni endpoint'ler; mevcut Faz 1 sözleşmesi bozulmadı. Sandbox'ta boş veritabanına ileri-geri doğrulandı.
- **Bilinen riskler:** (a) `reserve_stock` tüm adayları kilitler — ~600 sipariş/hafta için yeterli, yük testiyle doğrulanmadı; (b) rezervasyon süresi için zamanlayıcı yok; (c) `AuditEvent` yok, yalnızca `LotQualityEvent` ve defter; (d) reçete onayı yetkisi hâlâ `is_staff`; (e) `waste_factor` tek değer, adımlı fire yok.
- **Geri dönüş planı:** Henüz üretim verisi yok; tablolar boşken app yerleşimi/tesis kararı ucuz değişir. Tesis modeli sonradan eklenebilir (nullable FK → doldur → zorunlu).

## ADR-013 — Kimlik doğrulama stratejisi ve rol modeli
- **Tarih:** 2026-10-15
- **Durum:** Onaylandı (2026-10-15; ürün sahibi, "uygun olanı seç" yetkisiyle). **Backend uygulandı** (2026-10-15, sandbox'ta test edildi); rol→izin tablosunun ana satırları ürün sahibince onaylandı, kalanı onun bıraktığı yetkiyle belirlendi (bkz. 05 §1, 2026-10-16). Next.js tarafı ve CORS henüz yok.
- **Bağlam:** ADR-010 kimlik doğrulama stratejisini Faz 3'ten önce karara bağlamayı şart koştu; ADR-009 rolleri `RoleAssignment`'a bıraktı. Next.js Admin ekranlarına başlamadan önce ikisi de gerekli. Geçici `is_staff` + Django izinleri (ADR-012 §10) hâlâ yürürlükte.
- **Karar:**
  1. **Web (müşteri sitesi ve Admin, Next.js): sunucu tarafı oturum.** `HttpOnly`, `Secure`, `SameSite=Lax` oturum çerezi + Django CSRF. Tarayıcıda (localStorage vb.) token tutulmaz. Web ve API aynı kayıtlı alan adı altında (ör. `app.` ve `api.` alt alanları) dağıtılır; CORS yalnızca izinli origin'lere, `credentials` ile açılır. Mevcut `SessionAuthentication` doğru seçimdir, yer tutucu olmaktan çıkar.
  2. **Mobil (Faz 6): kısa ömürlü access token + dönen refresh token**, cihaz bazlı iptal edilebilir; platformun güvenli saklaması (Keychain/Keystore). Kütüphane seçimi Faz 6'da, bağımlılık eklenmeden önce yapılır. Web oturumu ile mobil token aynı kullanıcı ve izin modelini kullanır.
  3. **Uç noktalar:** `POST /auth/login/`, `POST /auth/logout/`, `GET /me/` (web, Faz 1 sonu); `POST /auth/refresh/` mobil ile birlikte (Faz 6). Kimliksiz istek **401** `AUTHENTICATION_REQUIRED` döner (şu an geçici olarak 403; ADR-010 notu kapanır). Giriş denemesine hız sınırı (DRF throttle) zorunludur.
  4. **Rol modeli:** `accounts.RoleAssignment` (`user`, `role_code`, `created_at`; tek tesis olduğu için `site` yok, ADR-012 §8). Roller 02 §2'deki liste: `CUSTOMER`, `ADMIN`, `PLANNER`, `PURCHASING`, `PRODUCTION`, `QUALITY`, `PACKING`, `DRIVER`, `SUPPORT`, `FINANCE`. Bir kullanıcının birden çok rolü olabilir. **Rol → izin eşlemesi kodda sabit ve testlidir** (yönetim ekranından düzenlenmez); varsayılan reddet. Rol tek başına yetmez: nesne kapsamı da kontrol edilir (müşteri yalnızca kendi kayıtları, kurye yalnızca atanmış teslimatlar; 05 §1).
  5. **Geçici yetkilerin yerine geçiş:** `IsCatalogAdmin`, `IsBackOfficeStaff` ve `staff_with_permission(...)` tek noktalardır; rol tabanlı izinle **yalnızca bu sınıflar** değiştirilir, view'lara dokunulmaz. `is_staff` yalnızca Django admin erişimi anlamına döner (ADR-009 ilkesi geri kurulur). İlk eşleme önerisi: katalog/reçete → `ADMIN`; tedarik ve mal kabul → `PURCHASING`; lot release/block → `QUALITY`; stok düzeltme ve ters hareket → `ADMIN`; rezervasyon/tüketim → `PLANNER`, `PRODUCTION`; mal kabul ters kaydı → `ADMIN`. Eşleme uygulama sırasında tabloya dökülür ve test edilir.
  6. **Hesap güvenliği:** Django parola doğrulayıcıları kalır; personel/Admin hesapları için çok faktörlü doğrulama **Faz 7 (pilot) öncesinde zorunlu hedef**, ondan önce şart değil. Müşteri kaydı, e-posta doğrulama ve telefon benzersizliği Faz 3 başında ayrıca karara bağlanır (ADR-009 açık noktası burada kapanmaz).
- **Alternatifler:** Web için de JWT (tarayıcıda token saklama/XSS riski, iptal zorluğu); yalnızca Django grupları/izinleri (rol-nesne kapsamı ve eşleme testi zayıf); tüm istemciler için tek token yöntemi.
- **Gerekçe:** Tarayıcıda oturum çerezi, token saklamaktan daha güvenlidir ve mevcut kodla uyumludur; mobil için cihaz bazlı token gerekir. Roller, 05 §1'deki "varsayılan olarak izin yok" ilkesini kodda sabit bir eşlemeyle uygular.
- **Etkilenen modüller/dosyalar (uygulamada):** `apps/accounts` (RoleAssignment, giriş/çıkış/`me` görünümleri, throttle), `apps/core/permissions.py`, `apps/catalog/permissions.py`, `config/settings/base.py` (oturum çerezi, CORS/CSRF ayarları), `docs/architecture/{02,03,05,08}`.
- **Migration/API etkisi:** `accounts.0002_roleassignment`; yeni `/auth/*`, `/me/`. Mevcut endpoint sözleşmeleri değişmez, yalnızca kimliksiz yanıt 403 → 401 olur (istemciler henüz yok).
- **Bilinen riskler:** çerez tabanlı oturum için aynı site (same-site) dağıtım şart; farklı alan adlarına bölünürse strateji yeniden değerlendirilir. Mobil token yöntemi Faz 6'ya kadar denenmemiş kalır.
- **Geri dönüş planı:** Henüz kod yok; kullanıcı/oturum verisi olmadığından strateji değişimi ucuz.

### ADR-013 — Uygulama notları (2026-10-15)
Karardan **bilinçli sapmalar ve eklemeler**:
1. **"Yalnızca bu sınıflar değişir, view'lara dokunulmaz" gevşetildi.** Onaylanan tablo modül içinde ayrım istiyor (örn. `PURCHASING` mal kabul yapar ama stok düzeltemez; `ADMIN` okur ama sipariş vermez). Bunun için `IsBackOfficeStaff` ve `staff_with_permission` silindi; yerlerine `core.permissions.has_permission(kod)` ve `has_permission_by_method(read=, write=)` geldi ve purchasing/inventory view'larındaki `permission_classes` satırları değişti. `IsCatalogAdmin` adı korundu (okuma `catalog:read`, yazma `catalog:manage`).
2. **`ADMIN` süper rol değildir.** Tabloda yazanları ve tüm okumaları taşır; lot serbest bırakma yalnızca `QUALITY`'de. Süper kullanıcı bayrağı API'de yetki vermez; ilk `ADMIN`, Django admin'de bir kullanıcıya rol verilerek oluşturulur. Rol değişiklikleri için denetim izi henüz yok (audit modülü açık sorun).
3. **Ek uç nokta `GET /auth/csrf/`:** SPA'nın `POST`'tan önce CSRF token'ı alabilmesi için (token gövdede de döner; web ve API farklı alt alanlarda olduğunda çerez okunamayabilir).
4. **Giriş CSRF'e tabidir** (anonim istek dahil, login-CSRF'e karşı); hız sınırı adres başına `20/dk` + e-posta başına `5/dk`. Tüm giriş hataları aynı yanıtı verir (kullanıcı sayımı yok).
5. **CORS bu görevde eklenmedi** ve **ADR-016 ile gereksiz kılındı**: Next.js uygulamaları API'yi aynı origin üzerinden proxy'ler. `CSRF_TRUSTED_ORIGINS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` ayarları hazır (üretimde varsayılan güvenli).
6. **Bilinen sınırlar:** hız sınırı sayaçları süreç-yerel önbellektedir; birden çok süreç/sunucu için Redis gerekir. Proxy arkasında `NUM_PROXIES` ayarlanmazsa adres sınırı proxy adresine uygulanır. Django model izinleri (`inventory.adjust_stock` vb.) modellerde durmaya devam eder ama API artık kullanmaz.

## ADR-014 — Sipariş akışı: onay, rezervasyon, iptal ve adres defteri
- **Tarih:** 2026-10-15
- **Durum:** Onaylandı (2026-10-16; ürün sahibi, "uygun olanı yap" yetkisiyle; maddeler olduğu gibi kabul edildi). Backend uygulandı (sandbox testli). "Geçici varsayım" işaretli maddeler 00 §8'deki açık kararların çalışma varsayımlarıdır; gerçek porsiyon/verim, ödeme ve teslimat kararlarıyla yeniden gözden geçirilir (her biri ayar veya küçük değişiklikle geri alınabilir).
- **Bağlam:** Faz 3, siparişi stok rezervasyonuna bağlar. 00 §8'de sipariş onayı/rezervasyon süresi, vergi, teslimat ücreti, ödeme ve müşteri kaydı kararları açıktı; Faz 3'ü bekletmemek için en az riskli varsayımlar seçildi.
- **Karar:**
  1. **Onay anında rezervasyon (geçici varsayım).** Sipariş tek işlemde doğrulanır, malzeme ihtiyacı sipariş genelinde toplanır, her malzeme için bir FEFO rezervasyonu yapılır ve sipariş `confirmed` olur. Biri yetersizse hepsi geri alınır (`INSUFFICIENT_STOCK`). Taahhütsüz "tutma" olmadığından **rezervasyon süresi/zamanlayıcı gerekmez** (`expires_at` boş). Ödeme sağlayıcısı seçilince `pending_payment` durumu ve süreli rezervasyon eklenir.
  2. **Durumlar:** `confirmed`, `cancelled`. `PLACED` yok (stok kontrolü eşzamanlı). Yeni durumlar aynı servis üzerinden eklenir; her değişiklik `OrderStatusEvent`'e (aktör, zaman, gerekçe) yazılır.
  3. **Sipariş birimi (geçici varsayım):** bir sipariş adedi = ürünün **1 adedi (`pcs`)**; ürünün onaylı reçetesinin verimi adet-bazlı olmalı. Malzeme ihtiyacı `calculate_requirements(sürüm, adet, pcs)` ile (fire dahil, brüt) hesaplanır. Verimi gram/litre olan reçeteler sipariş edilemez (porsiyon boyutu tanımsız).
  4. **Raf ömrü:** rezervasyon `use_by_on_or_after = teslimat tarihi` ile yapılır; teslimattan önce tarihi geçecek lotlar ayrılmaz.
  5. **Teslimat tarihi (geçici varsayım):** en erken `bugün + ORDER_MIN_LEAD_DAYS` (varsayılan 1). Teslimat günleri/saat pencereleri/bölge doğrulaması yok.
  6. **İptal (geçici varsayım):** müşteri, teslimata en az `ORDER_CUSTOMER_CANCEL_MIN_DAYS` (varsayılan 1) gün varken kendi siparişini iptal eder; arka ofis (`orders:cancel_any`: ADMIN, SUPPORT) süre sınırı olmadan, **zorunlu gerekçeyle** iptal eder. İptal rezervasyonları aynı işlemde serbest bırakır; tekrar iptal zararsızdır. Ödeme iadesi yok (ödeme yok).
  7. **Fiyat/vergi/ücret:** fiyat sunucuda ürün fiyatından alınır ve satıra dondurulur; bir siparişteki tüm ürünler aynı para birimini paylaşmalı. `tax_amount` ve `delivery_fee` sütunları var, değerleri `0` (kural kararına kadar).
  8. **Müşteriye sızıntı yok:** stok yetersizliğinde yanıt yalnızca etkilenen ürün kimliklerini içerir; malzeme adı, miktar ve stok seviyesi yalnızca günlüğe yazılır.
  9. **Nesne kapsamı:** müşteri yalnızca kendi sipariş ve adreslerini görür; başkasınınki 404. Arka ofis rolleri tüm siparişleri okur.
  10. **Adres defteri:** `CustomerAddress` (`orders` app'inde; ayrı bir müşteri profili modülü gerekçelenene kadar), müşteri başına en çok 10; sipariş adresi kopyalar.
  11. **Sınırlar (kötüye kullanım koruması, iş kuralı değil):** sipariş başına en çok 30 satır, satır başına en çok 100 adet.
  12. **Müşteri kaydı bu ADR'de yok.** Backend siparişi bir `CUSTOMER` rolü olan kullanıcıyla çalışır; kayıt, e-posta doğrulama ve telefon benzersizliği (ADR-009/013 açık noktası) müşteri web akışıyla birlikte karara bağlanır.
- **Alternatifler:** Ödeme/onay sonrası süreli rezervasyon (ödeme kararı olmadan zamanlayıcı ve ek durum getirir); sipariş başına satır bazlı rezervasyon (aynı malzemeyi paylaşan ürünlerde idempotency anahtarı çakışır, malzeme bazlı toplu rezervasyon seçildi); stok yetersizliğinde ayrıntılı miktar döndürmek (envanter bilgisini müşteriye sızdırır).
- **Gerekçe:** Taahhüt anında rezervasyon, zamanlayıcı ve ek durum olmadan fazla satışı engeller ve mevcut `reserve_stock` garantilerinden (tümü-ya-hiç, idempotent, FEFO) yararlanır.
- **Etkilenen modüller/dosyalar:** yeni `apps/orders` (models, services, selectors, serializers, views, urls, admin, migration, testler), `config/settings/base.py` (ayarlar, `OrderStatusEnum`), `config/urls.py`, `docs/architecture/{02,03,05,06,07,08}`.
- **Migration/API etkisi:** `orders.0001_initial`; yeni `/orders/*`, `/me/addresses/*`. Mevcut endpoint'ler değişmez.
- **Bilinen riskler:** (a) sipariş birimi varsayımı gerçek porsiyon/verim modeliyle çelişebilir; (b) onay anında rezervasyon, ödeme eklenince iptal/yarım kalan ödeme akışı ister; (c) onaylı reçete sipariş ile rezervasyon arasında değişirse sipariş, okunduğu sürümü dondurur (kabul edilmiş küçük yarış); (d) `reserve_stock`'un aday kilitleme maliyeti yük testinden geçmedi; (e) müşteri hesabı kaydı olmadığı için sipariş yolunu üretimde kullanmak, hesapların Django admin'den açılmasını gerektirir.
- **Geri dönüş planı:** Ayarlar (`ORDER_*`) davranışı değiştirir; durum/ödeme kararı eklenirse yeni durumlar ve migration gerekir, mevcut siparişler `confirmed`/`cancelled` olarak geçerli kalır.

## ADR-015 — Müşteri kaydı
- **Tarih:** 2026-10-16
- **Durum:** Onaylandı (2026-10-16; ürün sahibi, "uygun olanı" yetkisiyle). Backend uygulandı (sandbox testli).
- **Bağlam:** Faz 3 siparişi `CUSTOMER` rolüyle çalışıyor ama hesaplar yalnızca Django admin'den açılabiliyordu. ADR-009/013'ün açık noktaları: müşteri kaydı, e-posta doğrulama, telefon benzersizliği.
- **Karar:**
  1. `POST /auth/register/` (`{email, password, phone?}`) kullanıcıyı ve **yalnızca** `CUSTOMER` rolünü tek işlemde oluşturur ve oturumu açar. Gövde rol veya bayrak (`is_staff` vb.) seçemez; personel hesapları yalnızca Django admin'den ve rol atamasıyla oluşur.
  2. Parola, Django parola doğrulayıcılarından geçmelidir (uzunluk, yaygın parola, yalnızca rakam, e-postaya benzerlik).
  3. **E-posta doğrulaması bu aşamada yok** (e-posta/bildirim altyapısı yok; Faz 6). Doğrulanmamış hesaplar sipariş verebilir. Doğrulama geldiğinde `email_verified_at` eklenir ve sipariş için zorunlu kılmak bir ayar olur.
  4. **Telefon benzersiz değildir** (ADR-009 ile uyumlu; aynı hanede paylaşılabilir, doğrulama olmadan benzersizliğin anlamı yok) ve isteğe bağlıdır.
  5. **E-posta sayımı kabul edilmiş sınırlamadır:** doğrulama olmadan kayıt, bir adresin kayıtlı olduğunu gizleyemez (`400`, `details.email`). Karşılık: adres başına `5/saat` hız sınırı, yinelenen yolda parola yine de hash'lenir (zaman farkı yok), giriş ucu tek tip hata verir.
  6. **Parola sıfırlama yok** (e-posta gerektirir): parolasını unutan müşteri şimdilik hesabına dönemez. Faz 6 bildirimleriyle birlikte gelir; **canlıya (pilot) çıkmadan önce zorunlu.**
- **Alternatifler:** Doğrulama bağlantısı olmadan kayıt açmamak (siparişleri bekletir, e-posta altyapısı gerekir); davetle kayıt; telefonu benzersiz yapmak (doğrulamasız anlamsız).
- **Gerekçe:** Faz 3 akışını uçtan uca denenebilir kılar; eksik doğrulama ve sıfırlama, pilot öncesi kapatılacak açık risk olarak kayda geçer.
- **Etkilenen dosyalar:** `apps/accounts/{services,serializers,views,urls,throttles}.py`, `config/settings/base.py` (`register_ip` hız sınırı), testler.
- **Migration/API etkisi:** Migration yok; yeni `POST /auth/register/`.
- **Bilinen riskler:** doğrulanmamış hesap spam'i; sahte e-postayla sipariş; hız sınırı süreç-yerel önbellekte (çok süreçte Redis); parola sıfırlama yokluğu.
- **Geri dönüş planı:** Endpoint kapatılabilir (URL kaldırılır); mevcut hesaplar etkilenmez.

## ADR-016 — Web istemcileri: Next.js araçları ve API erişimi
- **Tarih:** 2026-10-16
- **Durum:** Onaylandı (2026-10-16; ürün sahibi, "uygun olanı" yetkisiyle). Henüz uygulanmadı (kod yok); ADR-003'ü tamamlar.
- **Bağlam:** ADR-003 iki Next.js uygulaması öngörüyor (müşteri sitesi ve Admin). Araç seçimi, çerez oturumunun işleyişi ve CORS kararı (ADR-013 uygulama notu 5) açıktı.
- **Karar:**
  1. **İki ayrı uygulama, tek repo:** `web/` (müşteri) ve `admin/` (operasyon), pnpm workspace. Ortak kod `packages/api-client` içinde (OpenAPI'den üretilen tipler ve ince istemci); UI bileşenleri başta paylaşılmaz.
  2. **Next.js (App Router) + TypeScript `strict`**, güncel LTS Node (sürüm `.nvmrc`/`engines` ile iskele aşamasında sabitlenir), **pnpm**.
  3. **API'ye aynı origin üzerinden erişim:** her uygulama kendi `/api/*` yolunu Next.js `rewrites` ile (geliştirmede `http://localhost:8000`, üretimde ters vekil veya aynı rewrite) Django'ya iletir. Sonuç: **CORS eklenmez**, oturum ve CSRF çerezleri her uygulamanın kendi host'unda (host-only) kalır; `web` ve `admin` oturumları birbirinden ayrıdır. Sunucu tarafı render'da çerez isteğe bağlı olarak API'ye iletilir; müşteriye özel sayfalar istemci veya dinamik render ile çalışır, önbelleğe alınmaz.
  4. **Tip üretimi:** `openapi-typescript` + `openapi-fetch`; şema `manage.py spectacular` çıktısından üretilir, üretilen dosya repoda tutulur ve CI'da "yeniden üret ve fark varsa başarısız" kontrolü yapar (sözleşme kayması yakalanır, 09 §4).
  5. **UI ve veri:** Tailwind CSS + shadcn/ui (Radix); veri çekme için TanStack Query; Admin tabloları için TanStack Table; formlar React Hook Form + Zod. Durum geçiş düğmeleri yalnızca `/me/` içindeki `permissions` izin veriyorsa gösterilir (güvenlik yine sunucudadır).
  6. **Test:** Vitest + Testing Library (birim/bileşen), Playwright (giriş, kayıt, sipariş ve iptal akışları, rol bazlı görünürlük).
  7. **Bağımlılık ilkesi:** her yeni paket için lisans, bakım durumu ve güvenlik geçmişi bakılır; `pnpm audit` CI'da çalışır; kilit dosyası commit edilir.
- **Alternatifler:** Tek Next.js uygulaması (route group'lar; güvenlik sınırı ve dağıtım bağımı karışır); tarayıcıdan API'ye doğrudan çağrı + CORS (üçüncü taraf çerez/SameSite karmaşası, ek CORS yüzeyi); SWR veya Redux (TanStack Query sunucu durumuna daha uygun); npm/yarn.
- **Gerekçe:** Aynı origin proxy, oturum çerezi stratejisini (ADR-013) basit ve güvenli tutar ve CORS yüzeyini ortadan kaldırır; üretilmiş tipler kontrat kaymasını erken yakalar.
- **Etkilenen modüller/dosyalar (uygulamada):** yeni `web/`, `admin/`, `packages/api-client/`, kök `pnpm-workspace.yaml`, CI'ya Node job'ı, `docker-compose.yml` (geliştirme servisleri), `docs/architecture/{01,04,08,09}`.
- **Migration/API etkisi:** Yok (backend değişmez).
- **Bilinen riskler:** Next.js proxy ek bir sıçrama ekler; SSR'de çerez iletimi dikkat ister; Admin ve müşteri sitesi için ayrı kök alan adı/alt alan kararı dağıtımda netleşecek; çok sayıda üçüncü taraf paket (tedarik zinciri riski).
- **Geri dönüş planı:** Henüz kod yok; proxy yerine CORS'a geçmek ADR-013 notu 5'in ayarlarını (django-cors-headers, origin listesi) eklemekten ibarettir.

## Yeni karar şablonu

### ADR-XXX — Kısa başlık
- **Tarih:** YYYY-MM-DD
- **Durum:** Önerildi / Onaylandı / Reddedildi / Yerini başka karar aldı
- **Bağlam:** Hangi problem veya gereksinim?
- **Karar:** Ne seçildi?
- **Alternatifler:** Hangi seçenekler değerlendirildi?
- **Gerekçe:** Neden bu seçenek?
- **Etkilenen modüller/dosyalar:** ...
- **Migration/API etkisi:** ...
- **Geri dönüş planı:** ...

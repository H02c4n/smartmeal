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
- **Durum:** Önerildi (Faz 0 uygulaması; onay bekliyor)
- **Bağlam:** `02_DATA_MODEL.md` §1 "tercihen UUID, tüm projede tutarlı" diyor; karar verilmesi gerekiyordu.
- **Karar:** Tüm SmartMeal domain modelleri `apps.core.models.UUIDTimestampedModel` (UUIDv4 `id`, `created_at`, `updated_at`) üzerinden türer. Django'nun kendi tabloları (Group, Permission vb.) `BigAutoField` kalır.
- **Alternatifler:** BigAutoField; UUIDv7 (Python 3.12 standart kütüphanesinde yok).
- **Gerekçe:** Tahmin edilemeyen kimlikler (API'de numaralandırma riskini azaltır), mobil/offline istemcilerde kimlik üretimi, modüller arası tutarlılık. ~600 sipariş/hafta ölçeğinde UUIDv4 indeks maliyeti kabul edilebilir; ölçümle doğrulanmalı.
- **Etkilenen modüller/dosyalar:** `apps/core/models.py`, `apps/accounts/models.py`, tüm gelecek modeller.
- **Migration/API etkisi:** `User.id` UUID. Sonradan PK tipini değiştirmek zor olduğundan Faz 0'da karar verildi.
- **Geri dönüş planı:** Henüz veri yok; Faz 1'den önce değiştirmek ucuz, sonrasında maliyetli.

## ADR-008 — Araç ve sürüm seçimleri
- **Tarih:** 2026-10-13
- **Durum:** Önerildi (Faz 0 uygulaması; onay bekliyor)
- **Karar:** Python 3.12; Django 5.2 LTS (`>=5.2,<5.3`); DRF; drf-spectacular (OpenAPI); psycopg 3 (binary); django-environ; PostgreSQL 16; paket yönetimi **uv** (`pyproject.toml` + `uv.lock`, CI'da `--frozen`); test **pytest + pytest-django**; lint/format **ruff**.
- **Alternatifler:** Django 6.x (daha yeni, LTS değil); pip-tools/Poetry; black+flake8.
- **Gerekçe:** LTS ile destek penceresi ve kararlılık; tek araçla lint+format; kilit dosyası ile tekrarlanabilir kurulum (00_PROJECT_MASTER §2 sürümlerin lockfile'a sabitlenmesini şart koşar).
- **Etkilenen dosyalar:** `backend/pyproject.toml`, `backend/uv.lock`, `backend/Dockerfile`, `.github/workflows/ci.yml`.
- **Geri dönüş planı:** Araçlar birbirinden bağımsız değiştirilebilir; uygulama kodu araçlara bağımlı değildir.

## ADR-009 — Custom User modeli kapsamı
- **Tarih:** 2026-10-13
- **Durum:** Önerildi (Faz 0 uygulaması; onay bekliyor)
- **Karar:** `accounts.User`: UUID PK, `email` (giriş kimliği, benzersiz, **her zaman küçük harf** — manager/`save()` normalize eder, `CHECK (email = lower(email))` veritabanında zorlar), `phone` (opsiyonel, benzersiz değil), `is_active`, `is_staff`, `is_superuser`, `created_at`, `updated_at`. Ad/soyad ve iş rolleri **yoktur**; roller `RoleAssignment` ile ayrı görevde eklenir. `is_staff` yalnızca Django admin erişimidir; Django admin geliştirici aracıdır, ürün Admin'i Next.js'tir (ADR-003).
- **Alternatifler:** Postgres `citext` (ek extension gerektirir); Lower() tabanlı UniqueConstraint (Django, USERNAME_FIELD için `unique=True` ister).
- **Etkilenen dosyalar:** `apps/accounts/*`, `config/settings/base.py` (`AUTH_USER_MODEL`).
- **Migration/API etkisi:** `accounts.0001_initial` — diğer tüm migration'lardan önce, ilk migrate'ten önce üretildi.
- **Açık nokta:** Telefon benzersizliği ve ad/soyad ihtiyacı ürün kararıdır; Faz 3 (müşteri/sipariş) öncesinde netleştirilmeli.

## ADR-010 — Hata zarfı ve request_id temel altyapıda
- **Tarih:** 2026-10-13
- **Durum:** Önerildi (Faz 0 uygulaması; onay bekliyor)
- **Karar:** `03_API_CONTRACTS.md` §1/§5 sözleşmesi baştan uygulanır: her hata `{"error": {"code","message","details?","request_id"}}`; `X-Request-ID` middleware'i (istemci değeri yalnızca `[A-Za-z0-9._-]{8,64}` ise kabul, aksi halde UUID üretilir), log kayıtlarına `request_id` eklenir. DRF varsayılan izni `IsAuthenticated` (varsayılan kapalı).
- **Geçici nokta:** Kimlik doğrulama stratejisi (token/session) hâlâ açık karardır. `SessionAuthentication` **geçici yer tutucudur**; bu nedenle kimliksiz istek şimdilik 403 (`AUTHENTICATION_REQUIRED` koduyla) döner; token stratejisi seçilince 401 olacaktır. Ayrı ADR gerekir (Faz 3'ten önce, `/auth/*` endpoint'leriyle birlikte).
- **Etkilenen dosyalar:** `apps/core/{middleware,exceptions,logging,request_id}.py`.

## ADR-011 — Katalog modülü: malzeme, ürün, birim sözlüğü ve miktar politikası
- **Tarih:** 2026-10-14
- **Durum:** Önerildi (Faz 1 uygulaması; onay bekliyor)
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

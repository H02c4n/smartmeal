# 08 — Güncel Proje Durumu

> Bu dosya her çalışma oturumunun sonunda güncellenmelidir. Gerçek kod ve test durumu doğrulanmadan tamamlanmış gibi işaretlenmemelidir.

## Son güncelleme
- Tarih: 2026-10-14
- Güncelleyen: Faz 1 oturumu (Ingredient, Product, birim ve dönüşüm sözlüğü)

## Genel durum
- [x] Faz 0 altyapısı (Django 5.2 LTS + DRF + PostgreSQL, custom user, hata zarfı, request_id, health, OpenAPI, CI) — Faz 0'da doğrulandı, bu oturumda değişmedi
- [x] `catalog` app'i: `Unit`, `IngredientUnitConversion`, `Ingredient`, `Product` modelleri, servisleri, API'si, Django admin kaydı (sandbox'ta doğrulandı)
- [ ] Faz 1 değişiklikleri kullanıcının Docker ortamında ve GitHub Actions'ta **henüz çalıştırılmadı**
- [ ] ADR-007…010 ve yeni ADR-011 "Önerildi" durumunda; onay bekliyor

## Faz durumu
- Faz 0 — Repo temelini hazırla: **Tamamlandı**
- Faz 1 — Katalog ve reçeteler: **Kısmen** (Ingredient/Product ve birim-dönüşüm sözlüğü tamamlandı; RecipeVersion/RecipeLine, alerjen, Next.js admin ekranları bekliyor)
- Faz 2–7: Bekliyor

## Son tamamlanan görev
Faz 1, ilk kısım: `apps/catalog` — birim sözlüğü (`g`, `kg`, `ml`, `l`, `pcs`; migration ile tohumlandı), malzemeye özel boyutlar arası dönüşüm (`IngredientUnitConversion`), `Ingredient` ve `Product` (SKU normalizasyonu/değişmezliği, DB CHECK kısıtları, pasife alma), `convert_quantity` servisi (Decimal, ara yuvarlama yok, sonda `ROUND_HALF_UP` 4 ondalık), katalog API'si ve Django admin kaydı. Kararlar ADR-011 önerisinde.

## Aktif görev
Yok. Sıradaki: Faz 1, `RecipeVersion` ve `RecipeLine` (ayrı görev).

## Değişen dosyalar (bu oturum)
- Yeni: `backend/apps/catalog/` — `apps.py`, `models.py`, `exceptions.py`, `services.py`, `selectors.py`, `serializers.py`, `permissions.py`, `views.py`, `urls.py`, `admin.py`, `migrations/0001_initial.py`, `migrations/0002_seed_units.py`, `tests/` (`conftest.py`, `test_models.py`, `test_convert_quantity.py`, `test_services.py`, `test_api_products.py`, `test_api_admin_products.py`, `test_api_admin_ingredients.py`, `test_django_admin.py`, `test_openapi.py`)
- Değişen: `backend/config/settings/base.py` (`apps.catalog` INSTALLED_APPS), `backend/config/urls.py` (`apps.catalog.urls` api/v1 altına)
- Belgeler: `docs/architecture/01` (modül tablosu notu), `02` (§3 modeller ve miktar politikası), `03` (Faz 1 endpoint'leri ve ortak kurallar), `06` (Faz 1 maddeleri), `07` (ADR-011 önerisi), `08` (bu dosya)
- Değişmeyen: `pyproject.toml`, `uv.lock` (yeni bağımlılık yok), Docker/CI dosyaları

## Migration durumu
- `accounts.0001_initial` (Faz 0)
- `catalog.0001_initial`: `Unit`, `IngredientUnitConversion`, `Ingredient`, `Product` ve kısıtlar (CHECK: SKU formatı, fiyat ≥ 0, para birimi formatı, çarpan/miktar > 0, birim kodu formatı; kısmi benzersiz indeks: boyut başına tek taban birim; benzersiz: SKU, birim kodu, (malzeme, birim))
- `catalog.0002_seed_units`: `g`, `kg`, `ml`, `l`, `pcs` (idempotent `update_or_create`; geri alma no-op)
- Sandbox'ta doğrulandı: boş DB'ye `migrate`, `catalog 0001`/`0002`/`zero` ileri-geri, yeniden `migrate`; `makemigrations --check --dry-run` temiz. Kullanıcının Docker ortamında henüz uygulanmadı.

## Test durumu
**Sandbox** (Python 3.12.3, PostgreSQL 16.15, Django 5.2.18, bu oturumda çalıştırıldı):
- `pytest`: **192 geçti, 0 başarısız** (52 Faz 0 + 140 yeni `apps/catalog`)
- `ruff check` ve `ruff format --check`: temiz
- `makemigrations --check --dry-run`: değişiklik yok
- `spectacular --validate --fail-on-warn`: geçti

**Docker (kullanıcı makinesi) ve GitHub Actions:** Faz 1 kodu için henüz çalıştırılmadı. Doğrulama komutları:
`docker compose run --rm backend python manage.py migrate`, `docker compose run --rm backend pytest`, `docker compose run --rm backend ruff check .`, `docker compose run --rm backend ruff format --check .`, `docker compose run --rm backend python manage.py makemigrations --check --dry-run`, `docker compose run --rm backend python manage.py spectacular --validate --fail-on-warn --file /dev/null`.

**Test edilmeyenler:** gerçek eşzamanlı (çok iş parçacıklı) yinelenen-SKU create yarışı (yalnızca `IntegrityError` eşlemesi simüle edildi); yük/performans; CSRF'li gerçek oturum akışı (testler `force_authenticate` kullanır).

## Ortamla ilgili notlar
- Windows'ta 127.0.0.1:5432 host portu kullanılamadı; `.env` içinde `POSTGRES_HOST_PORT=55432` ile çözüldü. Uygulama DB'ye Docker ağında `db:5432` ile bağlanır.
- Windows/Git Bash'te `make` yok; doğrudan `docker compose run --rm backend ...` komutları kullanılır.
- Yeni migration'ları uygulamak için: `docker compose run --rm backend python manage.py migrate`.

## Açık sorunlar ve ürün kararları
- ADR-007…010 ve ADR-011 "Önerildi"; onay bekliyor. ADR-007 (UUID PK) reddedilirse tüm Faz 1 modelleri etkilenir.
- Kimlik doğrulama stratejisi hâlâ açık (ADR-010). Katalog yazma endpoint'leri geçici `IsCatalogAdmin` (= `is_staff`) kullanıyor; ADR-009'daki "`is_staff` yalnızca Django admin" ilkesiyle gerilim bilinçli ve geçici. `RoleAssignment` gelince değişmeli. Oturum tabanlı kimlik doğrulamada yazma istekleri CSRF ister (token stratejisi seçilince değişir).
- `GET /products/` şimdilik kimlik zorunlu; müşteri akışı netleşince herkese açma kararı verilmeli.
- Para birimi kümesi, vergi, para birimi başına küçük birim hassasiyeti (`price` şimdilik `NUMERIC(12,2)`), `currency` ISO 4217 listesiyle eşleştirilmiyor (00 §8, açık).
- Birim kümesi: `mg` ve mutfak ölçüleri (çay kaşığı, yemek kaşığı, bardak) kapsam dışı; gerekirse migration + ADR.
- **Risk:** `IngredientUnitConversion` değeri değişirse bu dönüşümü kullanan reçetelerin hesaplanan miktarı değişir; onaylı reçete geçmişini korumak için RecipeVersion onayında snapshot veya dönüşüm sürümlemesi gerekecek (RecipeLine görevinde karar).
- Fire formülü karara bağlandı (verim bazlı `net ÷ (1 − fire)`, yalnızca RecipeLine'da) ama henüz kodlanmadı; geçerli aralık `0 ≤ fire < 1`.
- "Malzeme başına boyut başına en fazla bir dönüşüm" kuralı model/servis seviyesindedir, DB kısıtı değildir; ihlal edilirse `convert_quantity` tahmin etmez, "Ambiguous" hatası verir.
- Audit modülü henüz yok: fiyat/SKU/aktiflik değişiklikleri şimdilik denetim izi bırakmıyor (yalnızca `updated_at`).
- Silme politikası: katalog öğeleri ve birimler `PROTECT` ile korunur, API ve Django admin'den silinemez; pasife alınır.
- `LANGUAGE_CODE` (hata mesajı dili) henüz ürün kararı değil; `en-us` geçici
- Üretim imajı/ayarları (`production.py`, gunicorn, statik dosya) kapsam dışı
- Sipariş onayı/rezervasyon anı, ödeme sağlayıcısı, vergi, tesis kapsamı, gıda güvenliği, offline kapsamı, bildirim sağlayıcısı, RPO/RTO, yük testi profili (değişmedi)

## Sonraki görev
1. Faz 1: `RecipeVersion` ve `RecipeLine` — durum geçişleri (taslak → onaylı), onayda geçmişi koruma (dönüşüm snapshot kararı), fire (`waste_factor`) uygulaması, reçete miktarlarının taban birime hesaplanması (`convert_quantity` kullanılarak). Önce kapsam ve açık kararlar sorulur, onaydan sonra uygulanır.
2. Ardından: alerjen bilgisi; Admin temel ekranları (Next.js); RoleAssignment (katalog yetkisinin `is_staff`'ten çıkarılması).

## Oturum sonu özeti
- Tamamlanan: `catalog` app'i (birim sözlüğü, dönüşüm servisi, Ingredient, Product, API, Django admin, testler, belgeler)
- Eklenen migration'lar: `catalog.0001_initial`, `catalog.0002_seed_units`
- Açık hatalar: bilinen yok; Docker/CI doğrulaması bekliyor
- Belgelerde güncellenen bölümler: 01 (§3 not), 02 (§3), 03 (katalog), 06 (Faz 1), 07 (ADR-011), 08 (bu dosya)
- Sıradaki tek görev: Faz 1, RecipeVersion ve RecipeLine

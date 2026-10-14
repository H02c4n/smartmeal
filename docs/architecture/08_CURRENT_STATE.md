# 08 — Güncel Proje Durumu

> Bu dosya her çalışma oturumunun sonunda güncellenmelidir. Gerçek kod ve test durumu doğrulanmadan tamamlanmış gibi işaretlenmemelidir.

## Son güncelleme
- Tarih: 2026-10-14
- Güncelleyen: Faz 0 oturumu (repo iskeleti + Docker Compose doğrulaması + kapanış)

## Genel durum
- [x] Repository yapısı oluşturuldu (yerel dosyalar; uzak depo ve ilk commit kullanıcı tarafından)
- [x] Docker Compose yerelde çalışıyor — kullanıcının Windows/Git Bash makinesinde `docker compose build` başarılı, `docker compose up -d` ile `db` (healthy) ve `backend` (running) ayakta, `curl http://localhost:8000/api/v1/health/` → `{"status":"ok","database":"ok"}`
- [x] Django API başlatılıyor (hem host üzerinde hem Docker içinde; health 200)
- [x] PostgreSQL migration'ları — sandbox'ta ve kullanıcının Docker ortamında `migrate` başarılı (kullanıcı bildirdi, hata yok)
- [~] CI/test altyapısı — testler sandbox'ta 52/52 geçiyor ve kullanıcının Docker ortamında düzeltme sonrası hatasız çalıştığı bildirildi (kullanıcı bildirdi; çıktı iletilmedi); `.github/workflows/ci.yml` **hiç çalıştırılmadı**
- [x] OpenAPI şeması üretiliyor ve doğrulanıyor (`spectacular --validate --fail-on-warn`, sandbox)

## Faz durumu
- Faz 0 — Repo temelini hazırla: **Büyük ölçüde tamamlandı** (kalan tek madde: CI'nın GitHub'da ilk çalışması)
- Faz 1–7: Bekliyor

## Son tamamlanan görev
Faz 0 backend iskeleti: Django 5.2 LTS + DRF + PostgreSQL, custom user, request_id + hata zarfı, health endpoint, OpenAPI, pytest/ruff, Docker/Compose/Makefile/CI dosyaları, README. Docker Compose akışı (build, up, migrate, test, health) gerçek ortamda doğrulandı.

## Aktif görev
Faz 0'ı kapatmak: depoyu GitHub'a gönderip CI'nın ilk çalışmasını doğrulamak. Ardından Faz 1.

## Değişen dosyalar
`README.md`, `Makefile`, `docker-compose.yml`, `.env.example`, `.gitignore`, `.editorconfig`, `.github/workflows/ci.yml`,
`backend/` (pyproject.toml, uv.lock, Dockerfile, manage.py, conftest.py, config/*, apps/core/*, apps/accounts/*),
`docs/architecture/` (Architecture Pack kopyası; 06, 07, 08 güncellendi).

## Migration durumu
- `accounts.0001_initial` (User; CHECK `accounts_user_email_lowercase`). Django'nun auth/admin/sessions/contenttypes migration'ları ile birlikte sandbox'ta boş veritabanına uygulandı.
- `makemigrations --check` temiz (sandbox).
- Docker ortamında `migrate`: başarılı (kullanıcı bildirdi).

## Test durumu
**Sandbox** (Python 3.12.3, PostgreSQL 16, Django 5.2.18):
- `pytest`: **52 geçti, 0 başarısız**
- `ruff check` ve `ruff format --check`: temiz
- `makemigrations --check --dry-run`: değişiklik yok
- `spectacular --validate --fail-on-warn`: geçti

**Docker (kullanıcı makinesi), ilk çalıştırma:** 50 geçti, 2 başarısız (`test_anonymous_gets_authentication_required_envelope`, `test_non_staff_gets_permission_denied_envelope`).
- Sebep: Compose backend konteynerine `DJANGO_SETTINGS_MODULE=config.settings.local` veriyor; pytest-django'da ortam değişkeni `pyproject.toml` değerinden önceliklidir, testler `test` yerine `local` ayarlarıyla koştu (şema endpoint'i local'de bilerek `AllowAny`).
- Düzeltme: `backend/pyproject.toml` → `addopts = "-ra --strict-markers --ds=config.settings.test"` (komut satırı seçeneği ortam değişkeninden önceliklidir). Sandbox'ta hata yeniden üretildi ve düzeltme sonrası 52/52 geçti.
- Kullanıcı, düzeltme sonrası Docker içinde testlerin hatasız çalıştığını bildirdi (ayrıntılı çıktı iletilmedi).

**Çalıştırılmayanlar:** GitHub Actions workflow'u.

## Ortamla ilgili notlar
- Windows'ta 127.0.0.1:5432 host portu kullanılamadı (izin hatası); `.env` içinde `POSTGRES_HOST_PORT=55432` ile çözüldü. Uygulama veritabanına Docker ağı içinden `db:5432` ile bağlandığı için etkilenmez.
- Windows/Git Bash'te `make` yok; README'deki `make` hedefleri yerine doğrudan `docker compose ...` komutları kullanılıyor (örn. `docker compose run --rm backend pytest`).

## Açık sorunlar ve ürün kararları
- ADR-007…010 "Önerildi" durumunda; onay bekliyor
- Kimlik doğrulama stratejisi (token/session) — şu an `SessionAuthentication` geçici yer tutucu (ADR-010)
- Telefon benzersizliği, kullanıcı ad/soyad ihtiyacı (ADR-009)
- `LANGUAGE_CODE` (hata mesajı dili) henüz ürün kararı değil; `en-us` geçici
- Üretim imajı/ayarları (`production.py`, gunicorn, statik dosya) kapsam dışı bırakıldı
- Sipariş onayı/rezervasyon anı, ödeme sağlayıcısı, vergi/para birimi, tesis kapsamı, reçete birimleri, gıda güvenliği, offline kapsamı, bildirim sağlayıcısı, RPO/RTO, yük testi profili (değişmedi)

## Sonraki görev
1. Kullanıcı: depoyu GitHub'a gönderip Actions'taki ilk CI çalışmasını bildirsin (başarısızsa log'u iletsin).
2. Faz 1: Ingredient ve Product (+ birim sözlüğü). CI'nın ilk çalışması Faz 1'i engellemez.

## Oturum sonu özeti
- Tamamlanan: Faz 0 backend iskeleti; Docker Compose build/up/migrate/test/health gerçek ortamda doğrulandı; README'ye Windows komutları eklendi
- Eklenen migration'lar: `accounts.0001_initial`
- Açık hatalar: bilinen yok (Docker'daki test ayarı önceliği hatası düzeltildi ve doğrulandı)
- Belgelerde güncellenen bölümler: 06 (Faz 0 durumu), 07 (ADR-007…010), 08 (bu dosya)
- Sıradaki tek görev: Faz 1 (Ingredient ve Product); paralelde CI'nın GitHub'da ilk çalışması

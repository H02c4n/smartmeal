# SmartMeal

Yemek siparişi, malzeme tedariki, üretim, kalite, paketleme ve teslimat yönetim sistemi.
Mimari referans: [`docs/architecture/`](docs/architecture/) (başlangıç noktası: `00_PROJECT_MASTER.md`).

**Durum:** Faz 0 (repo temeli). Backend iskeleti hazır; web/admin/mobil uygulamalar henüz yok.

## Gereksinimler

- Docker + Docker Compose v2 (`docker compose version`)
- `make` (isteğe bağlı kısayollar; olmadan komutları Makefile içinden kopyalayabilirsiniz)

## Hızlı başlangıç

```bash
cp .env.example .env          # sonra .env içinde DJANGO_SECRET_KEY ve POSTGRES_PASSWORD değerlerini değiştirin
make build                    # backend imajını derle
make up                       # PostgreSQL + Django API'yi başlat
make migrate                  # veritabanı migration'larını uygula
make superuser                # (isteğe bağlı) Django admin için yönetici oluştur
```

Doğrulama:

| Ne | Adres |
|---|---|
| Sağlık kontrolü (API + DB) | http://localhost:8000/api/v1/health/ → `{"status":"ok","database":"ok"}` |
| OpenAPI şeması (yalnızca local) | http://localhost:8000/api/v1/schema/ |
| Swagger UI (yalnızca local) | http://localhost:8000/api/v1/docs/ |
| Django admin (yalnızca geliştirici aracı) | http://localhost:8000/django-admin/ |

```bash
make test                     # test paketi
make check                    # CI'nin çalıştırdığı tüm kontroller (lint, migration drift, şema, test)
```

Windows'ta `make` yoksa: `docker compose run --rm backend pytest` gibi doğrudan komutlar kullanın.
`DJANGO_SECRET_KEY` üretmek için: `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`

### Windows / `make` olmadan

`make` yoksa (ör. Git Bash) karşılıkları:

| make | docker compose |
|---|---|
| `make build` | `docker compose build` |
| `make up` / `make down` | `docker compose up -d` / `docker compose down` |
| `make ps` / `make logs` | `docker compose ps` / `docker compose logs -f` |
| `make migrate` | `docker compose run --rm backend python manage.py migrate` |
| `make makemigrations` | `docker compose run --rm backend python manage.py makemigrations` |
| `make superuser` | `docker compose run --rm backend python manage.py createsuperuser` |
| `make test` | `docker compose run --rm backend pytest` |
| `make lint` | `docker compose run --rm backend sh -c "ruff check . && ruff format --check ."` |
| `make format` | `docker compose run --rm backend sh -c "ruff check . --fix && ruff format ."` |

Windows'ta `127.0.0.1:5432` "izin yok" hatası verirse `.env` içinde `POSTGRES_HOST_PORT=55432` yapın (uygulama DB'ye Docker ağından bağlandığı için etkilenmez).

## Günlük komutlar

`make help` tüm hedefleri listeler. Sık kullanılanlar: `up`, `down`, `logs`, `migrate`, `makemigrations`,
`shell`, `dbshell`, `test`, `lint`, `format`, `schema`, `reset-db` (yerel veritabanını siler, onay ister).

## Repository yapısı

```text
smartmeal/
├── backend/                  Django + DRF modüler monolit
│   ├── config/               settings (base/local/test), urls, wsgi/asgi
│   ├── apps/                 İş alanı modülleri (Django apps)
│   │   ├── core/             Ortak altyapı: UUID taban model, request_id, hata zarfı, health
│   │   └── accounts/         Custom User modeli (+ ileride RoleAssignment)
│   ├── conftest.py           Ortak pytest fixture'ları
│   ├── pyproject.toml        Bağımlılıklar, pytest ve ruff yapılandırması
│   ├── uv.lock               Sabitlenmiş bağımlılık sürümleri (commit edilir)
│   └── Dockerfile            Geliştirme imajı
├── docs/
│   ├── architecture/         Architecture Pack (00–09 belgeleri)
│   └── adr/                  (ileride ayrı ADR dosyaları gerekirse)
├── .github/workflows/ci.yml  CI: lint, format, migration drift, OpenAPI, test, compose build
├── docker-compose.yml        db (PostgreSQL 16) + backend
├── .env.example              Ortam değişkenleri şablonu
└── Makefile                  Geliştirici kısayolları
```

Planlanan (henüz oluşturulmadı) monorepo dizinleri: `web/` (müşteri sitesi, Next.js), `admin/` (Next.js Admin),
`mobile-customer/` ve `mobile-ops/` (React Native), `packages/api-types/` (OpenAPI'den üretilen tipler).

Yeni bir iş alanı modülü eklerken: `backend/apps/<modül>/` altında oluşturun, `AppConfig.name = "apps.<modül>"`
ve `label` verin, `INSTALLED_APPS`'e ekleyin. Modül sınırları ve bağımlılık kuralları için
`docs/architecture/01_ARCHITECTURE.md` §3–4.

## Ortam değişkenleri

Tümü `.env.example` içinde açıklanmıştır. Önemliler:

| Değişken | Açıklama |
|---|---|
| `DJANGO_SECRET_KEY` | **Zorunlu**, varsayılanı yok; eksikse uygulama başlamaz |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Hem db konteyneri hem Django kullanır |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Docker **dışında** çalışırken (varsayılan `localhost:5432`); Compose içinde `db:5432`'ye ezilir |
| `POSTGRES_HOST_PORT`, `BACKEND_PORT` | Host'a yayınlanan portlar (yalnızca `127.0.0.1`) |
| `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_LOG_LEVEL` | Django davranışı |

### Gizli bilgi politikası

- Gerçek gizli bilgiler (şifre, anahtar, token) **asla** commit edilmez; `.env` git-ignore'dadır, yalnızca `.env.example` takip edilir.
- `.env.example` içinde yalnızca yer tutucu değerler bulunur ve bunlar **sadece yerel geliştirme** içindir.
- Staging/production gizli bilgileri geliştirme ortamından ayrıdır ve bu depoda tutulmaz.
- Loglara parola, token, ödeme verisi veya gereksiz kişisel veri yazılmaz.
- Bir gizli bilgi yanlışlıkla commit edilirse: değeri hemen değiştirin (git geçmişinden silmek yeterli değildir).

## Docker olmadan (host üzerinde) çalıştırma

Bir PostgreSQL erişilebilir olmalı (ör. `docker compose up -d db`). Python 3.12 ve [uv](https://docs.astral.sh/uv/) gerekir.

```bash
cd backend
uv sync                 # uv.lock'a göre kurar
uv run pytest           # ../.env otomatik okunur (POSTGRES_HOST=localhost)
uv run python manage.py runserver
```

## Test, lint ve format

| Amaç | Komut (Docker) |
|---|---|
| Testler | `make test` |
| Lint + format kontrolü | `make lint` |
| Otomatik düzeltme | `make format` |
| CI ile aynı tüm kontroller | `make check` |

Testler gerçek PostgreSQL'e karşı çalışır (pytest-django `test_<db>` veritabanı oluşturur).
Model değişikliği migration olmadan bırakılırsa `test_no_pending_model_changes` ve CI başarısız olur.

## Sorun giderme

- **`Copy .env.example to .env first`** — `.env` yok; `cp .env.example .env`.
- **Port 5432/8000 dolu** — `.env` içinde `POSTGRES_HOST_PORT` / `BACKEND_PORT` değiştirin, `make down && make up`.
- **Şifreyi değiştirdim ama bağlanamıyorum** — PostgreSQL şifreyi yalnızca ilk kurulumda uygular: `make reset-db` (yerel veriyi siler).
- **Linux'ta dosya izin hatası** — `.env` içinde `HOST_UID`/`HOST_GID` değerlerini `id -u`/`id -g` ile eşleyip `make build`.

## Katkı kuralları

Küçük, test edilebilir değişiklikler; her oturum sonunda `docs/architecture/08_CURRENT_STATE.md` güncellenir;
mimari karar değişirse `07_DECISION_LOG.md`'ye kayıt eklenir. Ayrıntı: `docs/architecture/09_CODE_STANDARDS.md`.

# SmartMeal — Next.js İskeleti: Yeni Chat Başlangıç Talimatı

Aşağıdaki metni yeni Chat'e, `nextjs-chat-pack.zip` içindeki dosyaları ekledikten sonra gönder.

---

SmartMeal projesine devam ediyoruz. Backend (Django + DRF) Faz 3'e kadar tamam ve Docker ile GitHub Actions'ta doğrulandı (660 test). Bu sohbetin görevi **yalnızca Next.js iskeleti**. Ekli belgeleri oku; ana referanslar `08_CURRENT_STATE.md`, `07_DECISION_LOG.md` (özellikle **ADR-016**, ayrıca ADR-003, ADR-013, ADR-015), `03_API_CONTRACTS.md`, `04_APPLICATIONS.md`, `09_CODE_STANDARDS.md` ve `openapi.yml` (gerçek API şeması).

## Görev
ADR-016'yı uygula (yalnızca iskelet ve kimlik kabuğu):
1. pnpm workspace: `web/` (müşteri), `admin/` (operasyon), `packages/api-client/`. Next.js App Router + TypeScript `strict`. Sürümleri iskele aşamasında bilinçli sabitle (kilit dosyası commit edilir).
2. `packages/api-client`: `openapi.yml`'den `openapi-typescript` ile tip üretimi + `openapi-fetch` ile ince istemci; üretim betiği ve "yeniden üret, fark varsa başarısız" kontrolü.
3. Her uygulamada `/api/*` → Django `rewrites` (API adresi ortam değişkeninden; geliştirmede `http://localhost:8000`, Docker içinde `http://backend:8000`). CORS yok.
4. Kimlik akışı: giriş ve kayıt sayfaları (`web/`), giriş sayfası (`admin/`), `/me/` ile oturum durumu, çıkış. Rol/izin bazlı bir kabuk: Admin gezinmesi yalnızca `/me/` içindeki `permissions` izin veriyorsa gösterir (güvenlik yine sunucuda); `admin/` yalnızca arka ofis rollerine (`CUSTOMER` dışı) açılır.
5. Tek bir tanımlı istemci katmanı; hata zarfı (`error.code/message/details/request_id`) ve 401/403 ayrımı merkezi işlenir; 401'de giriş sayfasına yönlendirme.
6. Vitest + Testing Library ile istemci katmanı ve kimlik kabuğu için testler.
7. CI'ya Node job'ı ekle (`.github/workflows/ci.yml`): install (frozen lockfile), lint, typecheck, test, build, `pnpm audit`, api-client "fark yok" kontrolü. Mevcut backend ve compose job'larına dokunma.
8. Geliştirme için `docker-compose.yml`'ye servis eklemek istersen önce gerekçesini söyle; backend servislerini bozma.

**Kapsam dışı:** katalog/stok/sipariş ekranları, ödeme, mobil, backend değişiklikleri. Backend'de değişiklik gerekiyorsa değiştirme; neden gerektiğini ve etkisini raporla (karar kaydı öner).

## API kuralları (kanıt: `openapi.yml`, `03_API_CONTRACTS.md`)
- Taban yol `/api/v1/`. Oturum çerezi (`sessionid`, HttpOnly) + CSRF: önce `GET /auth/csrf/` → `{csrf_token}`, `POST/PATCH/DELETE`'te `X-CSRFToken` başlığı. Giriş sonrası token değişebilir; her yazmadan önce güncel token'ı kullan. Anonim `POST /auth/login/` ve `/auth/register/` da CSRF ister.
- Kimliksiz istek **401** `AUTHENTICATION_REQUIRED`; yetkisiz **403** `PERMISSION_DENIED`; başkasının nesnesi **404**. Giriş hataları tek tip: 401 "Invalid email or password."; hız sınırı **429** `RATE_LIMITED`.
- `GET /me/` → `{id, email, phone, roles[], permissions[]}`. Roller: `CUSTOMER`, `ADMIN`, `PLANNER`, `PURCHASING`, `PRODUCTION`, `QUALITY`, `PACKING`, `DRIVER`, `SUPPORT`, `FINANCE`.
- Kayıt (`POST /auth/register/`) yalnızca `CUSTOMER` oluşturur ve oturum açar.

## Bilinen tuzaklar (henüz Next.js ile denenmedi; doğrula)
- **CSRF Origin kontrolü:** proxy üzerinden gelen isteklerde tarayıcının `Origin`'i Next.js origin'idir. Django'da `DJANGO_CSRF_TRUSTED_ORIGINS` (örn. `http://localhost:3000,http://localhost:3001`) ayarlı olmalı; `.env.example`'a eklendi, kullanıcının `.env` dosyasına da eklenmeli ve backend yeniden başlatılmalı. "CSRF Failed: Origin checking failed" görürsen sebep budur.
- **Yerel çerez paylaşımı:** `localhost:3000` ve `localhost:3001` aynı çerezleri paylaşır, `web` ve `admin` oturumları karışabilir. Çözüm adayı: `web.localhost` / `admin.localhost`. Seçimi gerekçesiyle öner.
- Müşteriye özel sayfalar önbelleğe alınmamalı; SSR'de çerezi API'ye ilet.
- Windows/Git Bash: `nul` adında dosya oluşturma (`> nul`, `--file nul`); orada `make` yok, komutlar `pnpm`/`docker compose` ile verilmeli.

## Çalışma kuralları
1. Önce görevi, bağımlılıkları ve kullanıcıdan istediğin bilgileri (Node/pnpm kurulu mu, Docker içinde mi çalışılacak) kısa özetle; belirsizlikte tek soru sor.
2. Yeni her paket için lisans, bakım ve güvenlik durumuna bak; gereksiz bağımlılık ekleme.
3. Çalıştırmadığın komutu/testi çalıştırılmış gibi raporlama. Sandbox'ta çalıştırdıklarını ve kullanıcıdan beklediğin doğrulamaları ayrı yaz.
4. Mevcut API sözleşmesini sessizce kırma; belge ile `openapi.yml` çelişirse `openapi.yml`'yi esas al ve çelişkiyi bildir.
5. Bitince: değişen dosyalar, çalıştırılan komutlar ve sonuçları, açık riskler, sıradaki görev; `08_CURRENT_STATE.md` için güncellenmiş içerik ver; mimari karar değiştiyse `07_DECISION_LOG.md` için kayıt öner.

## Çıkış kriteri
`pnpm install --frozen-lockfile`, `pnpm -r lint`, `pnpm -r typecheck`, `pnpm -r test`, `pnpm -r build` geçer; Docker Compose'taki backend'e karşı tarayıcıda kayıt → çıkış → giriş → `/me/` akışı çalışır (kullanıcı doğrular); `admin/` bir `CUSTOMER` hesabını reddeder; CI'daki Node job'ı yeşildir.

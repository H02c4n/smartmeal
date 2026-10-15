# 06 — Geliştirme Yol Haritası

Süreler tahminidir; ekip boyutu, entegrasyonlar ve operasyonel gereksinimler netleştikçe güncellenmelidir. Her fazın çıkış kriteri geçmeden sonraki faza geçilmemelidir.

## Faz 0 — Kararları ve repo temelini hazırla
- [x] Git deposu ve monorepo yapısı (yapı oluşturuldu; uzak depo/ilk commit kullanıcıda)
- [x] Docker Compose (build, up, db healthy ve /health 200 kullanıcı makinesinde doğrulandı)
- [x] Django custom user modeli
- [x] PostgreSQL bağlantısı ve migration (PostgreSQL 16'ya karşı doğrulandı)
- [x] Lint/test/format komutları
- [~] CI temel akışı (workflow yazıldı; **GitHub Actions'ta henüz çalıştırılmadı**)
- [x] API schema altyapısı (drf-spectacular, `--validate --fail-on-warn` geçiyor)
- [x] `.env.example`, gizli bilgi politikası (README)

**Çıkış:** Yeni geliştirici README ile projeyi yerelde çalıştırabilir; testler otomatik çalışır.

## Faz 1 — Katalog ve reçeteler
- [x] Ingredient ve Product (modeller, servisler, API, Django admin; sandbox'ta test edildi — Docker/CI doğrulaması bekliyor)
- [x] Birim ve dönüşüm sözlüğü (`Unit`, `IngredientUnitConversion`, `convert_quantity`; sandbox'ta test edildi — Docker/CI doğrulaması bekliyor)
- [x] RecipeVersion ve RecipeLine (taslak → onaylı → emekli, onayda taban birim snapshot'ı, fire, ihtiyaç hesabı; sandbox'ta test edildi — Docker/CI doğrulaması bekliyor)
- [x] Alerjen bilgisi (`Allergen`, `IngredientAllergen`, reçete bazında türetilmiş özet; sandbox'ta test edildi)
- [ ] Admin temel ekranları (Next.js — henüz başlanmadı; Faz 1'in tek açık maddesi)
- [x] Model ve API testleri (backend için; sandbox'ta çalıştırıldı)

**Çıkış:** Ürün ve reçete sürümü yönetilir; reçete miktarları standart birimlerle hesaplanabilir. *(Backend karşılandı; Next.js Admin ekranları hariç.)*

## Faz 2 — Tedarik ve stok
- [x] Supplier ve PurchaseOrder (durum makinesi: draft → submitted → partially_received → received / cancelled)
- [x] GoodsReceipt (atomik; fazla teslimat toleransı %10; ters kayıt)
- [x] InventoryLot (kabulde `pending`; lot kodu ve SKT zorunlu)
- [x] StockMovement (yalnızca ekleme; işaret/tür DB kısıtı; `REVERSAL` ile düzeltme)
- [x] StockReservation (lot bazlı, tümü-ya-hiç, referans başına idempotent, süre sonu)
- [x] FEFO aday tahsisi (en erken SKT → kabul zamanı → id)
- [x] Kalite blokajı (pending/released/blocked, gerekçe + olay günlüğü, tüketimde `LOT_BLOCKED`)
- [x] Eşzamanlılık ve uzlaştırma testleri (gerçek paralel PostgreSQL bağlantılarıyla; `reconcile_inventory`)

*Sandbox'ta doğrulandı (PostgreSQL 16); Docker ve GitHub Actions'ta henüz çalıştırılmadı.*

**Çıkış:** Mal kabulden kullanılabilir stok hesabına kadar hareketler izlenebilir; stok fazla rezerve edilemez. *(Backend için karşılandı; kanıt: `inventory/tests/test_concurrency.py`.)*

## Faz 3 — Sipariş ve müşteri web'i
- [ ] Order ve OrderLine
- [ ] Fiyat snapshot'ı
- [ ] Durum makinesi
- [ ] Idempotency
- [ ] Sipariş/iptal ve rezervasyon kuralları
- [ ] Next.js müşteri web akışı
- [ ] Kimlik ve erişim testleri

**Çıkış:** Uçtan uca sipariş oluşturma ve güvenli iptal çalışır.

## Faz 4 — Üretim planlama
- [ ] Sipariş talep özeti
- [ ] Malzeme ihtiyaç hesaplama
- [ ] Üretim planı ve partiler
- [ ] Gerçekleşen miktar/fire
- [ ] Malzeme lotu tüketim bağlantısı

**Çıkış:** Planlanan ihtiyaç, kullanılan lot ve gerçekleşen üretim karşılaştırılabilir.

## Faz 5 — Kalite ve paketleme
- [ ] Kalite kontrol şablonları
- [ ] Ölçüm kayıtları
- [ ] Hold/release ve uygunsuzluk
- [ ] Paket ve etiket
- [ ] Paket/parti/sipariş izlenebilirliği

**Çıkış:** Kalite onayı olmayan ürünün paketleme/teslimat akışına geçmesi engellenir.

## Faz 6 — Teslimat ve mobil uygulamalar
- [ ] DeliveryRun ve DeliveryStop
- [ ] Kurye ataması
- [ ] Operasyon mobil görev akışı
- [ ] Teslimat sonucu ve kanıt
- [ ] Müşteri mobil uygulaması
- [ ] Bildirimler
- [ ] Ağ kesintisi ve idempotency

**Çıkış:** Sipariş üretimden teslimat sonucuna kadar izlenebilir.

## Faz 7 — Pilot ve üretime hazırlık
- [ ] Admin KPI panosu
- [ ] Operasyon raporları
- [ ] Hata/performans izleme
- [ ] Yedek ve restore provası
- [ ] Temsilî yük testi
- [ ] Yetki/güvenlik gözden geçirmesi
- [ ] Pilot kabul senaryoları
- [ ] Operasyon eğitim dokümanı

**Çıkış:** Pilot senaryoları geçer, bilinen riskler ve operasyon prosedürleri belgelenir.

## Öncelik kuralı

İlk dikey dilim: **malzeme → reçete → stok/lot → sipariş → rezervasyon**. Bu temel tutarlı hale gelmeden gelişmiş AI, gelişmiş rota optimizasyonu, mikroservis veya kapsamlı offline senaryolarına öncelik verilmez.

## Definition of Done

Bir görev tamamlanmış sayılır ancak:
- İş kuralı backend'de uygulanmıştır.
- Yetki ve nesne kapsamı doğrulanmıştır.
- Gerekli testler yazılmış ve çalıştırılmıştır.
- API/şema veya migration değişiklikleri belgelenmiştir.
- Hata ve tekrar davranışı ele alınmıştır.
- `08_CURRENT_STATE.md` güncellenmiştir.
- Mimari karar değişmişse ADR/decision log eklenmiştir.

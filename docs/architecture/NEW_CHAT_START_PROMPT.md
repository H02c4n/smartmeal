# SmartMeal — Yeni Chat Başlangıç Talimatı

Aşağıdaki metni yeni bir Chat'e, bu Architecture Pack dosyalarını ekledikten sonra gönder.

---

SmartMeal projesine devam ediyoruz. Ekli Architecture Pack belgelerini oku ve ana referans olarak kullan.

## Öncelik sırası
1. `00_PROJECT_MASTER.md` — bağlayıcı proje kararları
2. `08_CURRENT_STATE.md` — son bilinen çalışma durumu
3. `01_ARCHITECTURE.md`, `02_DATA_MODEL.md`, `03_API_CONTRACTS.md` — ilgili teknik sözleşmeler
4. Mevcut kaynak kodu, migration'lar ve testler — gerçek uygulamanın durumu

Belgelerle gerçek kod çelişirse çelişkiyi açıkça bildir. Kodun veya endpoint'in var olduğunu kanıt olmadan varsayma. Test çalıştırmadıysan testlerin geçtiğini söyleme.

## Sabit kararlar
- Django + Django REST Framework
- PostgreSQL
- Next.js + TypeScript müşteri web sitesi
- Next.js + TypeScript özel Admin
- React Native + TypeScript müşteri mobil uygulaması
- React Native + TypeScript operasyon mobil uygulaması; iki ayrı uygulama
- Docker Compose ile yerel geliştirme
- Modüler monolit; başlangıçta mikroservis yok

## Görev kuralları
1. İstenen görevi ve bağımlılıklarını önce kısa biçimde özetle.
2. İlgili mevcut dosyaları incele; eksik dosyaları açıkça belirt.
3. Görev kapsamı dışında dosya değiştirme.
4. Veri bütünlüğü, yetkilendirme, idempotency ve durum geçişlerini gerektiği yerde ele al.
5. Gerekli migration, test ve dokümantasyon değişikliklerini dahil et.
6. Mevcut API sözleşmelerini sessizce kırma. Değişiklik gerekiyorsa etkileri açıkla ve decision log öner.
7. Gerçekten çalıştırmadığın komut/testleri çalıştırılmış gibi raporlama.
8. Tamamlanınca değişen dosyaları, migration'ları, test sonuçlarını, açık riskleri ve sıradaki görevi listele.
9. `08_CURRENT_STATE.md` için güncellenmiş içeriği ver. Mimari karar değiştiyse `07_DECISION_LOG.md` için yeni kayıt öner.

## Çalışılacak görev
[Buraya tek ve net görevi yaz]

Önce belgeleri ve varsa kodu değerlendir; ardından bu görevi mevcut mimariyle uyumlu şekilde uygula.

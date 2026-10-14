# SmartMeal Architecture Pack

Bu paket SmartMeal projesinin mimari referansını ve yeni Chat oturumlarında tutarlı çalışmak için gerekli çalışma protokolünü içerir.

## Başlangıç

1. Bu klasörü SmartMeal Git deposunda `docs/architecture/` altına kopyalayın.
2. `00_PROJECT_MASTER.md` dosyasını proje için ana referans olarak kullanın.
3. Her yeni Chat'e `00_PROJECT_MASTER.md`, `01_ARCHITECTURE.md`, `08_CURRENT_STATE.md` ve o görevle ilgili belgeleri yükleyin.
4. Kod mevcutsa, ilgili kaynak kodlarını ve migration dosyalarını da ekleyin. Belgeler tek başına gerçek kodun yerini tutmaz.
5. Her oturum sonunda `08_CURRENT_STATE.md` ve gerektiğinde `07_DECISION_LOG.md` güncellensin.
6. Mimari karar değişiklikleri sessizce yapılmasın; önce karar gerekçesi ve etkilenen modüller yazılsın.

## Dosyalar

- `00_PROJECT_MASTER.md` — ana referans ve bağlayıcı proje kararları
- `01_ARCHITECTURE.md` — sistem bileşenleri ve modül sınırları
- `02_DATA_MODEL.md` — önerilen veri modeli
- `03_API_CONTRACTS.md` — API ilkeleri ve başlangıç endpoint envanteri
- `04_APPLICATIONS.md` — web ve mobil uygulama kapsamları
- `05_SECURITY_AND_BUSINESS_RULES.md` — güvenlik, stok, gıda güvenliği ve kritik kurallar
- `06_DEVELOPMENT_ROADMAP.md` — fazlar, görevler ve kabul kriterleri
- `07_DECISION_LOG.md` — karar kayıtları
- `08_CURRENT_STATE.md` — güncel geliştirme durumu şablonu
- `09_CODE_STANDARDS.md` — kod, test ve repository standartları
- `NEW_CHAT_START_PROMPT.md` — yeni Chat için kopyalanabilir başlangıç talimatı

## Belge statüsü

Bu paket başlangıç blueprint'idir. Buradaki veri modeli ve API uç noktaları önerilen taslaktır; henüz kodlandıkları veya test edildikleri anlamına gelmez. Gerçek uygulama geliştikçe belgeler kodla eşitlenmelidir.

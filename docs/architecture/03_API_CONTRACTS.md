# 03 — API Sözleşmeleri

## 1. Genel standart

- Base path: `/api/v1/`
- Transport: HTTPS, JSON
- Kimlik: uygun token/session stratejisi; müşteri ve personel istemcileri için tehdit modeline göre seçilir.
- API schema: OpenAPI; istemci tipleri mümkünse şemadan üretilir.
- Liste endpoint'leri: sayfalama ve belgelenmiş filtreler.
- Tarih/saat: ISO 8601, timezone açık.
- Para: ondalık string ve para birimi; istemciden gelen toplam fiyat otorite değildir.
- Her hata cevabında `error.code`, güvenli `message`, gerektiğinde `details` ve `request_id`.
- Kritik create/complete işlemleri için idempotency desteği.
- API değişiklikleri geriye uyumluluk dikkate alınarak yapılır; kırıcı değişiklik için sürümleme ve geçiş planı gerekir.

## 2. Önerilen hata kodları

- `VALIDATION_ERROR` — alan doğrulaması başarısız
- `AUTHENTICATION_REQUIRED` — oturum/token yok veya geçersiz
- `PERMISSION_DENIED` — işlem için yetki yok
- `RESOURCE_NOT_FOUND` — kaynak bulunamadı veya erişim politikası gereği gizlendi
- `INVALID_STATE_TRANSITION` — izin verilmeyen durum geçişi
- `INSUFFICIENT_STOCK` — kullanılabilir stok yetersiz
- `LOT_BLOCKED` — kalite nedeniyle lot kullanılamaz
- `IDEMPOTENCY_CONFLICT` — aynı anahtar farklı içerikle kullanıldı
- `CONFLICT` — güncel veriyle işlem çakışıyor
- `RATE_LIMITED` — hız sınırı aşıldı

## 3. İlk endpoint envanteri

### Kimlik
- `POST /auth/login/`
- `POST /auth/refresh/`
- `POST /auth/logout/`
- `GET /me/`

### Katalog ve reçete
- `GET /products/`
- `GET /products/{id}/`
- `POST /admin/products/`
- `POST /admin/recipe-versions/`
- `POST /admin/recipe-versions/{id}/approve/`

### Sipariş
- `POST /orders/`
- `GET /orders/`
- `GET /orders/{id}/`
- `POST /orders/{id}/cancel/`

### Stok ve satın alma
- `GET /inventory/balances/`
- `GET /inventory/lots/`
- `POST /purchase-orders/`
- `POST /purchase-orders/{id}/submit/`
- `POST /goods-receipts/`
- `POST /inventory/adjustments/`

### Planlama ve üretim
- `POST /production-plans/`
- `POST /production-plans/{id}/release/`
- `GET /production-plans/{id}/`
- `POST /batches/{id}/start/`
- `POST /batches/{id}/record-consumption/`
- `POST /batches/{id}/complete/`

### Kalite ve paketleme
- `POST /batches/{id}/quality-checks/`
- `POST /quality-incidents/{id}/hold/`
- `POST /quality-incidents/{id}/release/`
- `POST /packages/{id}/pack/`

### Teslimat
- `POST /delivery-runs/`
- `POST /delivery-runs/{id}/assign/`
- `POST /delivery-stops/{id}/complete/`
- `POST /delivery-stops/{id}/fail/`

### Raporlama ve destek
- `GET /reports/daily-operations/`
- `GET /reports/inventory-expiry/`
- `POST /support/tickets/`
- `GET /support/tickets/`

Bu liste taslaktır; endpoint'ler kodlanmış kabul edilmez. Kesin OpenAPI şeması uygulama sırasında üretilmeli ve testlerle doğrulanmalıdır.

## 4. Örnek: sipariş oluşturma

Request:
```http
POST /api/v1/orders/
Idempotency-Key: <unique-key>
Content-Type: application/json
```

```json
{
  "delivery_date": "2026-10-19",
  "delivery_address_id": "uuid",
  "items": [
    {"product_id": "uuid", "quantity": 3},
    {"product_id": "uuid", "quantity": 2}
  ]
}
```

Response `201 Created`:
```json
{
  "id": "uuid",
  "order_number": "SM-20261019-0001",
  "status": "CONFIRMED",
  "currency": "SEK",
  "total_amount": "645.00",
  "items": [
    {
      "product_id": "uuid",
      "quantity": 3,
      "unit_price": "129.00",
      "line_total": "387.00"
    }
  ]
}
```

Tutarlar sadece örnektir. Fiyat, indirim, vergi ve teslimat ücreti sunucuda hesaplanır. Gerçek iş kuralına göre sipariş önce `PLACED` olup stok/ödeme doğrulamasından sonra `CONFIRMED` olabilir; bu durum makinesi ürün kararıyla kesinleştirilmelidir.

## 5. Örnek hata

```json
{
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Yeterli kullanılabilir stok yok.",
    "details": {
      "ingredient_id": "uuid",
      "requested_quantity": "1200",
      "available_quantity": "800"
    },
    "request_id": "uuid"
  }
}
```

## 6. İşlem güvenliği

- Kritik işlemler `transaction.atomic()` içinde uygulanır.
- Eşzamanlı stok değişikliklerinde uygun satır kilidi/constraint kullanılır.
- Aynı idempotency anahtarı aynı isteğin tekrarında aynı sonucu döndürür; farklı payload ile yeniden kullanılması reddedilir.
- Liste endpoint'lerinde kullanıcının erişebileceği kayıtlar QuerySet düzeyinde filtrelenir.
- Yetkilendirme hem endpoint hem nesne/tesis kapsamı düzeyinde yapılır.
- Bildirimler transaction commit olduktan sonra gönderilir; gerekiyorsa transactional outbox kullanılır.
- API sözleşmesi değişince OpenAPI ve ilgili istemci tipleri/testleri güncellenir.

## 7. Endpoint başına zorunlu dokümantasyon

Her endpoint için:
1. Amaç
2. HTTP metodu ve path
3. Kimlik doğrulama gereksinimi
4. Rol/nesne kapsamı
5. Request şeması
6. Success response şeması
7. Olası hata kodları
8. Transaction ve yan etkiler
9. Idempotency/tekrar davranışı
10. Test senaryoları

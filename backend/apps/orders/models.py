"""Customer orders (02_DATA_MODEL §5, ADR-014).

Written only through ``orders.services``. An order is confirmed in one transaction together with
its stock reservation, so the only states today are ``confirmed`` and ``cancelled``; later phases
(production, packing, delivery) add states and transitions through the same central service.

History never changes silently (00 §4.9): product name/SKU/price, the recipe version used and the
delivery address are copied onto the order, and status changes are an append-only event log.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import UUIDTimestampedModel

CURRENCY_PATTERN = r"^[A-Z]{3}$"
COUNTRY_PATTERN = r"^[A-Z]{2}$"


class CustomerAddress(UUIDTimestampedModel):
    """A delivery address in a customer's address book.

    Orders copy the address into ``Order.delivery_address_snapshot``; editing or deleting an
    address therefore never changes a past order. Delivery zones are not validated (open
    decision, 00 §8).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses"
    )
    recipient_name = models.CharField(max_length=120)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    postal_code = models.CharField(max_length=20)
    city = models.CharField(max_length=100)
    country_code = models.CharField(max_length=2)
    phone = models.CharField(max_length=32, blank=True)

    class Meta:
        db_table = "orders_customer_address"
        ordering = ["created_at"]
        verbose_name_plural = "customer addresses"
        constraints = [
            models.CheckConstraint(
                condition=Q(country_code__regex=COUNTRY_PATTERN),
                name="orders_address_country_format",
            ),
            models.CheckConstraint(
                condition=~Q(recipient_name="") & ~Q(line1="") & ~Q(postal_code="") & ~Q(city=""),
                name="orders_address_required_parts",
            ),
        ]

    def snapshot(self) -> dict:
        return {
            "recipient_name": self.recipient_name,
            "line1": self.line1,
            "line2": self.line2,
            "postal_code": self.postal_code,
            "city": self.city,
            "country_code": self.country_code,
            "phone": self.phone,
        }


class OrderNumberCounter(models.Model):
    """Per-day counter behind ``SM-YYYYMMDD-NNNN`` order numbers.

    Incremented inside the order's own transaction, so a rolled-back order leaves no gap.
    """

    day = models.DateField(primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "orders_number_counter"

    def __str__(self) -> str:
        return f"{self.day}: {self.last_number}"


class Order(UUIDTimestampedModel):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    order_number = models.CharField(max_length=24, unique=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders"
    )
    status = models.CharField(max_length=16, choices=Status.choices)
    delivery_date = models.DateField()
    delivery_address_snapshot = models.JSONField()
    currency = models.CharField(max_length=3)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    # Tax and delivery fee are open decisions (00 §8): stored, but 0 until a rule is decided.
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    confirmed_at = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        db_table = "orders_order"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"], name="orders_order_customer_idx"),
            models.Index(fields=["status", "delivery_date"], name="orders_order_status_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["confirmed", "cancelled"]), name="orders_order_status"
            ),
            models.CheckConstraint(
                condition=Q(currency__regex=CURRENCY_PATTERN), name="orders_order_currency_format"
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0)
                & Q(tax_amount__gte=0)
                & Q(delivery_fee__gte=0)
                & Q(total_amount__gte=0),
                name="orders_order_amounts_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(total_amount=F("subtotal") + F("tax_amount") + F("delivery_fee")),
                name="orders_order_total_adds_up",
            ),
            models.CheckConstraint(
                condition=(Q(status="cancelled") & Q(cancelled_at__isnull=False))
                | (Q(status="confirmed") & Q(cancelled_at__isnull=True)),
                name="orders_order_cancelled_at_matches_status",
            ),
        ]

    def __str__(self) -> str:
        return self.order_number


class OrderLine(UUIDTimestampedModel):
    """One product on an order, with the price and recipe version frozen at order time."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="order_lines"
    )
    product_sku_snapshot = models.CharField(max_length=40)
    product_name_snapshot = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    recipe_version = models.ForeignKey(
        "recipes.RecipeVersion", on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "orders_order_line"
        ordering = ["product_sku_snapshot"]
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="orders_line_unique_product"),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="orders_line_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="orders_line_unit_price_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(line_total=F("unit_price") * F("quantity")),
                name="orders_line_total_is_price_times_quantity",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Order lines are immutable; they carry the order-time snapshot.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Order lines are immutable; they carry the order-time snapshot.")


class OrderStatusEvent(UUIDTimestampedModel):
    """Append-only log of status changes: who, when, why (05 §3)."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="events")
    from_status = models.CharField(max_length=16, blank=True)  # empty for the creation event
    to_status = models.CharField(max_length=16)
    reason = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "orders_order_status_event"
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Order status events are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Order status events are append-only.")

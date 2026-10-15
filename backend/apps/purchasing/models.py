"""Suppliers, purchase orders and goods receipts (02_DATA_MODEL §4, ADR-012).

Dependency note: ``purchasing`` owns these tables and calls ``inventory.services`` to turn a
received line into a lot. ``inventory`` only *references* ``Supplier`` and ``GoodsReceiptLine``
by foreign key (string reference, no import), so there is no import cycle.

Quantities that matter for stock are kept twice: as entered (``quantity`` + ``unit``) and as
``*_base_quantity`` in the ingredient's base unit. Stock arithmetic uses the base quantities only.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from apps.core.models import UUIDTimestampedModel

CURRENCY_PATTERN = r"^[A-Z]{3}$"


def generate_po_number() -> str:
    return f"PO-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"


class Supplier(UUIDTimestampedModel):
    name = models.CharField(max_length=200)
    contact_details = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "purchasing_supplier"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="purchasing_supplier_name_unique_ci"),
            models.CheckConstraint(
                condition=~Q(name=""), name="purchasing_supplier_name_not_empty"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class PurchaseOrder(UUIDTimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        PARTIALLY_RECEIVED = "partially_received", "Partially received"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    po_number = models.CharField(max_length=32, unique=True, default=generate_po_number)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    currency = models.CharField(max_length=3)
    ordered_at = models.DateTimeField(null=True, blank=True)
    expected_at = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "purchasing_purchase_order"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=["draft", "submitted", "partially_received", "received", "cancelled"]
                ),
                name="purchasing_po_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(currency__regex=CURRENCY_PATTERN), name="purchasing_po_currency_format"
            ),
            models.CheckConstraint(
                condition=Q(status="draft") | Q(status="cancelled") | Q(ordered_at__isnull=False),
                name="purchasing_po_submitted_has_ordered_at",
            ),
        ]

    def __str__(self) -> str:
        return self.po_number


class PurchaseOrderLine(UUIDTimestampedModel):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="lines"
    )
    ingredient = models.ForeignKey(
        "catalog.Ingredient", on_delete=models.PROTECT, related_name="purchase_order_lines"
    )
    ordered_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit = models.ForeignKey(
        "catalog.Unit", on_delete=models.PROTECT, related_name="purchase_order_lines"
    )
    ordered_base_quantity = models.DecimalField(max_digits=14, decimal_places=4, editable=False)
    received_base_quantity = models.DecimalField(
        max_digits=14, decimal_places=4, default=0, editable=False
    )
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        db_table = "purchasing_purchase_order_line"
        ordering = ["purchase_order", "ingredient__sku"]
        constraints = [
            models.UniqueConstraint(
                fields=["purchase_order", "ingredient"], name="purchasing_po_line_unique_ingredient"
            ),
            models.CheckConstraint(
                condition=Q(ordered_quantity__gt=0), name="purchasing_po_line_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(ordered_base_quantity__gt=0),
                name="purchasing_po_line_base_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(received_base_quantity__gte=0),
                name="purchasing_po_line_received_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(unit_cost__gte=0), name="purchasing_po_line_cost_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.purchase_order_id}: {self.ordered_quantity} {self.unit_id}"


class GoodsReceipt(UUIDTimestampedModel):
    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"

    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="receipts"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.POSTED)
    received_at = models.DateTimeField(default=timezone.now)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reversal_reason = models.TextField(blank=True)

    class Meta:
        db_table = "purchasing_goods_receipt"
        ordering = ["-received_at"]
        permissions = [("reverse_goodsreceipt", "Can reverse a goods receipt")]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["posted", "reversed"]),
                name="purchasing_receipt_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(status="posted")
                | (Q(reversed_at__isnull=False) & ~Q(reversal_reason="")),
                name="purchasing_receipt_reversed_has_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"Receipt {self.pk} for {self.purchase_order_id}"


class GoodsReceiptLine(UUIDTimestampedModel):
    goods_receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, related_name="lines")
    po_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.PROTECT, related_name="receipt_lines"
    )
    ingredient = models.ForeignKey("catalog.Ingredient", on_delete=models.PROTECT, related_name="+")
    received_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit = models.ForeignKey("catalog.Unit", on_delete=models.PROTECT, related_name="+")
    received_base_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    supplier_lot_code = models.CharField(max_length=64)
    expiry_date = models.DateField()

    class Meta:
        db_table = "purchasing_goods_receipt_line"
        ordering = ["goods_receipt", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(received_quantity__gt=0) & Q(received_base_quantity__gt=0),
                name="purchasing_receipt_line_quantity_positive",
            ),
            models.CheckConstraint(
                condition=~Q(supplier_lot_code=""), name="purchasing_receipt_line_lot_not_empty"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.supplier_lot_code}: {self.received_quantity} {self.unit_id}"

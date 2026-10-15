"""Lots, stock movements and reservations (02_DATA_MODEL §4, ADR-012).

Design in short:

* **All stock is held in the ingredient's base unit** (g, ml, pcs); inputs in other units are
  converted at the service boundary with ``catalog.services.convert_quantity``.
* ``StockMovement`` is the append-only ledger. ``InventoryLot.on_hand`` and ``.reserved`` are
  projections kept in step with it under a row lock; database CHECK constraints make
  over-reservation and negative stock impossible even if application code is wrong, and
  ``selectors.reconcile`` proves the projections against ledger and reservations.
* Stock definitions (05 §2), per lot: ``available = on_hand - reserved`` if the lot is released
  and not expired, otherwise it is *unavailable* (pending, blocked or expired).

``QuerySet.update()``/``bulk_*`` bypass the guards in ``save()``/``delete()``; all writes go
through ``inventory.services``.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import UUIDTimestampedModel


def generate_internal_lot_code() -> str:
    return f"L{timezone.now():%y%m%d}-{uuid.uuid4().hex[:6].upper()}"


class InventoryLot(UUIDTimestampedModel):
    class QualityStatus(models.TextChoices):
        PENDING = "pending", "Pending quality check"
        RELEASED = "released", "Released"
        BLOCKED = "blocked", "Blocked"

    ingredient = models.ForeignKey(
        "catalog.Ingredient", on_delete=models.PROTECT, related_name="lots"
    )
    supplier = models.ForeignKey(
        "purchasing.Supplier", on_delete=models.PROTECT, related_name="lots"
    )
    receipt_line = models.OneToOneField(
        "purchasing.GoodsReceiptLine", on_delete=models.PROTECT, related_name="lot"
    )
    supplier_lot_code = models.CharField(max_length=64)
    internal_lot_code = models.CharField(
        max_length=32, unique=True, default=generate_internal_lot_code
    )
    received_at = models.DateTimeField()
    expiry_date = models.DateField()
    quality_status = models.CharField(
        max_length=16, choices=QualityStatus.choices, default=QualityStatus.PENDING
    )
    initial_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    on_hand = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    reserved = models.DecimalField(max_digits=14, decimal_places=4, default=0)

    class Meta:
        db_table = "inventory_lot"
        ordering = ["expiry_date", "received_at", "id"]
        permissions = [
            ("release_lot", "Can release a lot (end quality hold)"),
            ("block_lot", "Can block a lot (quality hold)"),
            ("adjust_stock", "Can adjust stock quantities"),
        ]
        indexes = [
            # FEFO candidate search: released lots of one ingredient by expiry.
            models.Index(
                fields=["ingredient", "expiry_date", "received_at"],
                name="inventory_lot_fefo_idx",
                condition=Q(quality_status="released"),
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(quality_status__in=["pending", "released", "blocked"]),
                name="inventory_lot_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(initial_quantity__gt=0), name="inventory_lot_initial_positive"
            ),
            models.CheckConstraint(
                condition=Q(on_hand__gte=0), name="inventory_lot_on_hand_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(reserved__gte=0), name="inventory_lot_reserved_non_negative"
            ),
            # The invariant behind "stock cannot be over-reserved".
            models.CheckConstraint(
                condition=Q(reserved__lte=F("on_hand")),
                name="inventory_lot_reserved_within_on_hand",
            ),
        ]

    def __str__(self) -> str:
        return self.internal_lot_code

    @property
    def available(self):
        return self.on_hand - self.reserved

    def is_usable(self, today=None) -> bool:
        """Released and not past its expiry date (the last day is still usable)."""
        today = today or timezone.localdate()
        return self.quality_status == self.QualityStatus.RELEASED and self.expiry_date >= today


class LotQualityEvent(UUIDTimestampedModel):
    """Append-only log of quality status changes (stands in for ``audit`` until it exists)."""

    lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT, related_name="quality_events")
    from_status = models.CharField(max_length=16)
    to_status = models.CharField(max_length=16)
    reason = models.TextField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "inventory_lot_quality_event"
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(condition=~Q(reason=""), name="inventory_quality_event_reason"),
        ]


class StockMovement(UUIDTimestampedModel):
    """One signed change of a lot's quantity. Never edited or deleted; corrected by REVERSAL."""

    class Type(models.TextChoices):
        RECEIPT = "receipt", "Receipt"
        CONSUMPTION = "consumption", "Consumption"
        ADJUSTMENT = "adjustment", "Adjustment"
        WASTE = "waste", "Waste"
        RETURN = "return", "Return"
        REVERSAL = "reversal", "Reversal"

    lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=16, choices=Type.choices)
    quantity_delta = models.DecimalField(max_digits=14, decimal_places=4)
    unit = models.ForeignKey("catalog.Unit", on_delete=models.PROTECT, related_name="+")
    balance_after = models.DecimalField(max_digits=14, decimal_places=4)
    reference_type = models.CharField(max_length=32, blank=True)
    reference_id = models.UUIDField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    reason = models.TextField(blank=True)
    reverses = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )

    class Meta:
        db_table = "inventory_stock_movement"
        ordering = ["occurred_at", "created_at", "id"]
        indexes = [models.Index(fields=["lot", "occurred_at"], name="inventory_movement_lot_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    movement_type__in=[
                        "receipt",
                        "consumption",
                        "adjustment",
                        "waste",
                        "return",
                        "reversal",
                    ]
                ),
                name="inventory_movement_type_valid",
            ),
            models.CheckConstraint(
                condition=~Q(quantity_delta=0), name="inventory_movement_delta_non_zero"
            ),
            # Sign convention (05 §2): receipts/returns add, consumption/waste remove,
            # adjustments and reversals go either way.
            models.CheckConstraint(
                condition=(Q(movement_type__in=["receipt", "return"]) & Q(quantity_delta__gt=0))
                | (Q(movement_type__in=["consumption", "waste"]) & Q(quantity_delta__lt=0))
                | Q(movement_type__in=["adjustment", "reversal"]),
                name="inventory_movement_sign_matches_type",
            ),
            models.CheckConstraint(
                condition=Q(balance_after__gte=0), name="inventory_movement_balance_non_negative"
            ),
            models.CheckConstraint(
                condition=(Q(movement_type="reversal") & Q(reverses__isnull=False))
                | (~Q(movement_type="reversal") & Q(reverses__isnull=True)),
                name="inventory_movement_reversal_links_original",
            ),
            models.CheckConstraint(
                condition=~Q(movement_type__in=["adjustment", "waste", "reversal"]) | ~Q(reason=""),
                name="inventory_movement_reason_required",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.movement_type} {self.quantity_delta} on {self.lot_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Stock movements are append-only; post a reversal instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Stock movements are append-only; post a reversal instead.")


class StockReservation(UUIDTimestampedModel):
    """A hold on quantity in one lot for a consumer, e.g. an order (Faz 3) or production batch.

    ``reference_type``/``reference_id`` identify the consumer without a foreign key, because
    those tables do not exist yet. A consumer reserving an ingredient may end up with several
    rows, one per lot, allocated first-expired-first-out.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Released"
        CONSUMED = "consumed", "Consumed"

    lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT, related_name="reservations")
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    reference_type = models.CharField(max_length=32)
    reference_id = models.UUIDField()
    expires_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    consumed_quantity = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    class Meta:
        db_table = "inventory_stock_reservation"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["reference_type", "reference_id"], name="inventory_resv_ref_idx"),
            models.Index(
                fields=["expires_at"],
                name="inventory_resv_expiry_idx",
                condition=Q(status="active", expires_at__isnull=False),
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["active", "released", "consumed"]),
                name="inventory_reservation_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="inventory_reservation_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(
                    status="consumed", consumed_quantity__gt=0, consumed_quantity__lte=F("quantity")
                )
                | (~Q(status="consumed") & Q(consumed_quantity__isnull=True)),
                name="inventory_reservation_consumed_quantity",
            ),
            # One active hold per consumer and lot; this is what makes re-reserving idempotent.
            models.UniqueConstraint(
                fields=["lot", "reference_type", "reference_id"],
                condition=Q(status="active"),
                name="inventory_reservation_one_active_per_reference_lot",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reference_type}:{self.reference_id} {self.quantity} ({self.status})"

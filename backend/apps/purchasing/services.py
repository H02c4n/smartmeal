"""Purchasing write operations (09_CODE_STANDARDS §2, ADR-012).

Purchase order state machine::

    draft --submit--> submitted --(receipts)--> partially_received --> received
      |                  |
      +----cancel--------+  (cancel only while nothing has been received)

A goods receipt is posted atomically: its lines, the lots (via ``inventory.services``), the
RECEIPT movements and the purchase order's received quantities commit together or not at all.
Over-receiving beyond ``PO_OVER_RECEIPT_TOLERANCE`` is rejected. A posted receipt can only be
reversed while none of its stock has been touched (reservation, use, adjustment).
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import as_serializer_error

from apps.catalog.models import Ingredient, Unit
from apps.core.api_errors import Conflict, InvalidStateTransition
from apps.inventory import services as inventory_services

from .models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)

# Suppliers sometimes ship a little more than ordered; beyond this share it is rejected.
PO_OVER_RECEIPT_TOLERANCE = Decimal("0.10")


def _full_clean(instance) -> None:
    try:
        instance.full_clean()
    except DjangoValidationError as exc:
        raise ValidationError(as_serializer_error(exc)) from exc


# --- Suppliers ------------------------------------------------------------------------------
def create_supplier(*, name: str, contact_details: str = "") -> Supplier:
    supplier = Supplier(name=name.strip(), contact_details=contact_details)
    _full_clean(supplier)
    try:
        with transaction.atomic():
            supplier.save(force_insert=True)
    except IntegrityError:
        raise ValidationError({"name": ["A supplier with this name already exists."]}) from None
    return supplier


def update_supplier(supplier: Supplier, **changes) -> Supplier:
    allowed = {"name", "contact_details"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Not updatable: {sorted(unknown)}")
    for field, value in changes.items():
        setattr(supplier, field, value.strip() if field == "name" else value)
    _full_clean(supplier)
    try:
        with transaction.atomic():
            supplier.save(update_fields=[*changes, "updated_at"])
    except IntegrityError:
        raise ValidationError({"name": ["A supplier with this name already exists."]}) from None
    return supplier


def set_supplier_active(supplier: Supplier, is_active: bool) -> Supplier:
    if supplier.is_active != is_active:
        supplier.is_active = is_active
        supplier.save(update_fields=["is_active", "updated_at"])
    return supplier


# --- Purchase orders ------------------------------------------------------------------------
@dataclass(frozen=True)
class POLineInput:
    ingredient: Ingredient
    quantity: Decimal
    unit: Unit
    unit_cost: Decimal


def _build_po_lines(po: PurchaseOrder, lines: list[POLineInput]) -> None:
    PurchaseOrderLine.objects.filter(purchase_order=po).delete()
    seen: set = set()
    for entry in lines:
        if entry.ingredient.pk in seen:
            raise ValidationError(
                {"lines": [f"Ingredient {entry.ingredient.sku} appears more than once."]}
            )
        seen.add(entry.ingredient.pk)
        if not entry.ingredient.is_active:
            raise ValidationError({"lines": [f"Ingredient {entry.ingredient.sku} is inactive."]})
        line = PurchaseOrderLine(
            purchase_order=po,
            ingredient=entry.ingredient,
            ordered_quantity=entry.quantity,
            unit=entry.unit,
            ordered_base_quantity=inventory_services.to_base_quantity(
                entry.ingredient, entry.quantity, entry.unit
            ),
            unit_cost=entry.unit_cost,
        )
        _full_clean(line)
        line.save(force_insert=True)


def create_purchase_order(
    *,
    supplier: Supplier,
    currency: str,
    created_by,
    expected_at: date | None = None,
    lines: list[POLineInput] | None = None,
) -> PurchaseOrder:
    if not supplier.is_active:
        raise ValidationError({"supplier": ["Inactive suppliers cannot receive new orders."]})
    with transaction.atomic():
        po = PurchaseOrder(
            supplier=supplier,
            currency=currency.strip().upper(),
            expected_at=expected_at,
            created_by=created_by,
        )
        _full_clean(po)
        po.save(force_insert=True)
        _build_po_lines(po, lines or [])
    return po


def update_purchase_order(
    po: PurchaseOrder,
    *,
    expected_at: date | None = None,
    set_expected_at: bool = False,
    lines: list[POLineInput] | None = None,
) -> PurchaseOrder:
    """Edit a draft: expected date and/or the whole line set."""
    with transaction.atomic():
        locked = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
        if locked.status != PurchaseOrder.Status.DRAFT:
            raise InvalidStateTransition("Only a draft purchase order can be edited.")
        if set_expected_at:
            locked.expected_at = expected_at
            locked.save(update_fields=["expected_at", "updated_at"])
        if lines is not None:
            _build_po_lines(locked, lines)
    return locked


def submit_purchase_order(po: PurchaseOrder) -> PurchaseOrder:
    """draft -> submitted. Idempotent for an order that is already submitted."""
    with transaction.atomic():
        locked = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
        if locked.status == PurchaseOrder.Status.SUBMITTED:
            return locked
        if locked.status != PurchaseOrder.Status.DRAFT:
            raise InvalidStateTransition(f"A {locked.status} purchase order cannot be submitted.")
        if not locked.lines.exists():
            raise ValidationError({"lines": ["An order needs at least one line."]})
        if not locked.supplier.is_active:
            raise ValidationError({"supplier": ["The supplier is inactive."]})
        locked.status = PurchaseOrder.Status.SUBMITTED
        locked.ordered_at = timezone.now()
        locked.save(update_fields=["status", "ordered_at", "updated_at"])
    return locked


def cancel_purchase_order(po: PurchaseOrder) -> PurchaseOrder:
    """draft/submitted -> cancelled, as long as nothing was received. Idempotent."""
    with transaction.atomic():
        locked = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
        if locked.status == PurchaseOrder.Status.CANCELLED:
            return locked
        if locked.status not in {PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.SUBMITTED}:
            raise InvalidStateTransition(f"A {locked.status} purchase order cannot be cancelled.")
        locked.status = PurchaseOrder.Status.CANCELLED
        locked.cancelled_at = timezone.now()
        locked.save(update_fields=["status", "cancelled_at", "updated_at"])
    return locked


# --- Goods receipt --------------------------------------------------------------------------
@dataclass(frozen=True)
class ReceiptLineInput:
    po_line: PurchaseOrderLine
    quantity: Decimal
    unit: Unit
    supplier_lot_code: str
    expiry_date: date


def _refresh_po_status(po: PurchaseOrder) -> None:
    lines = list(po.lines.all())
    if all(line.received_base_quantity >= line.ordered_base_quantity for line in lines):
        new_status = PurchaseOrder.Status.RECEIVED
    elif any(line.received_base_quantity > 0 for line in lines):
        new_status = PurchaseOrder.Status.PARTIALLY_RECEIVED
    else:
        new_status = PurchaseOrder.Status.SUBMITTED
    if po.status != new_status:
        po.status = new_status
        po.save(update_fields=["status", "updated_at"])


def post_goods_receipt(
    *,
    purchase_order: PurchaseOrder,
    lines: list[ReceiptLineInput],
    actor,
    received_at: datetime | None = None,
) -> GoodsReceipt:
    """Receive goods against a submitted order; creates pending lots and RECEIPT movements."""
    if not lines:
        raise ValidationError({"lines": ["At least one line is required."]})
    received_at = received_at or timezone.now()
    if received_at > timezone.now() + timedelta(minutes=5):
        raise ValidationError({"received_at": ["Cannot be in the future."]})
    today = timezone.localdate()

    with transaction.atomic():
        po = (
            PurchaseOrder.objects.select_for_update()
            .select_related("supplier")
            .get(pk=purchase_order.pk)
        )
        if po.status not in {
            PurchaseOrder.Status.SUBMITTED,
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
        }:
            raise InvalidStateTransition(
                f"Goods can only be received against a submitted order; this one is {po.status}."
            )
        po_lines = {
            line.pk: line
            for line in PurchaseOrderLine.objects.select_for_update()
            .select_related("ingredient__base_unit")
            .filter(purchase_order=po)
            .order_by("pk")
        }

        receipt = GoodsReceipt.objects.create(
            purchase_order=po, received_at=received_at, received_by=actor
        )
        incoming: dict = {}
        for entry in lines:
            po_line = po_lines.get(entry.po_line.pk)
            if po_line is None:
                raise ValidationError({"lines": ["A line does not belong to this purchase order."]})
            lot_code = (entry.supplier_lot_code or "").strip()
            if not lot_code:
                raise ValidationError({"lines": ["A supplier lot code is required (05 §4)."]})
            if entry.expiry_date < today:
                raise ValidationError(
                    {"lines": [f"Lot {lot_code} is already expired ({entry.expiry_date})."]}
                )
            base_quantity = inventory_services.to_base_quantity(
                po_line.ingredient, entry.quantity, entry.unit
            )
            incoming[po_line.pk] = incoming.get(po_line.pk, Decimal("0")) + base_quantity
            receipt_line = GoodsReceiptLine.objects.create(
                goods_receipt=receipt,
                po_line=po_line,
                ingredient=po_line.ingredient,
                received_quantity=entry.quantity,
                unit=entry.unit,
                received_base_quantity=base_quantity,
                supplier_lot_code=lot_code,
                expiry_date=entry.expiry_date,
            )
            inventory_services.receive_lot(
                ingredient=po_line.ingredient,
                supplier=po.supplier,
                receipt_line=receipt_line,
                base_quantity=base_quantity,
                supplier_lot_code=lot_code,
                expiry_date=entry.expiry_date,
                received_at=received_at,
                actor=actor,
            )

        for line_id, quantity in incoming.items():
            po_line = po_lines[line_id]
            limit = po_line.ordered_base_quantity * (1 + PO_OVER_RECEIPT_TOLERANCE)
            if po_line.received_base_quantity + quantity > limit:
                raise Conflict(
                    f"Receiving this would exceed the ordered quantity of "
                    f"{po_line.ingredient.sku} by more than "
                    f"{PO_OVER_RECEIPT_TOLERANCE:.0%}.",
                    extra={
                        "ingredient": po_line.ingredient.sku,
                        "ordered": format(po_line.ordered_base_quantity, "f"),
                        "already_received": format(po_line.received_base_quantity, "f"),
                        "this_receipt": format(quantity, "f"),
                    },
                )
            po_line.received_base_quantity += quantity
            po_line.save(update_fields=["received_base_quantity", "updated_at"])
        _refresh_po_status(po)
    return receipt


def reverse_goods_receipt(receipt: GoodsReceipt, *, reason: str, actor) -> GoodsReceipt:
    """Undo a posted receipt: reverses every lot's receipt movement and the PO quantities.

    Rejected (nothing changes) if any of its stock was reserved, used or adjusted. Idempotent
    for a receipt that is already reversed.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": ["A reason is required."]})
    with transaction.atomic():
        locked = (
            GoodsReceipt.objects.select_for_update()
            .select_related("purchase_order")
            .get(pk=receipt.pk)
        )
        if locked.status == GoodsReceipt.Status.REVERSED:
            return locked
        po = PurchaseOrder.objects.select_for_update().get(pk=locked.purchase_order_id)
        lines = list(locked.lines.select_related("lot").order_by("pk"))
        po_lines = {
            line.pk: line
            for line in PurchaseOrderLine.objects.select_for_update()
            .filter(pk__in=[line.po_line_id for line in lines])
            .order_by("pk")
        }
        for line in lines:
            inventory_services.reverse_receipt(line.lot.pk, reason=reason, actor=actor)
            po_line = po_lines[line.po_line_id]
            po_line.received_base_quantity -= line.received_base_quantity
            po_line.save(update_fields=["received_base_quantity", "updated_at"])
        locked.status = GoodsReceipt.Status.REVERSED
        locked.reversed_at = timezone.now()
        locked.reversed_by = actor
        locked.reversal_reason = reason
        locked.save(
            update_fields=[
                "status",
                "reversed_at",
                "reversed_by",
                "reversal_reason",
                "updated_at",
            ]
        )
        if po.status in {PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.PARTIALLY_RECEIVED}:
            _refresh_po_status(po)
    return locked

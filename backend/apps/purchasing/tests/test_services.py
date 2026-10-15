from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.api_errors import Conflict, InvalidStateTransition
from apps.inventory.models import InventoryLot
from apps.purchasing import services
from apps.purchasing.models import GoodsReceipt, PurchaseOrder
from apps.purchasing.services import POLineInput, ReceiptLineInput

pytestmark = pytest.mark.django_db


# --- Suppliers ------------------------------------------------------------------------------
def test_supplier_names_are_unique_ignoring_case(supplier):
    with pytest.raises(ValidationError):
        services.create_supplier(name="  fresh farms ab ")
    other = services.create_supplier(name="Other AB")
    with pytest.raises(ValidationError):
        services.update_supplier(other, name="FRESH FARMS AB")
    with pytest.raises(ValidationError):
        services.create_supplier(name="   ")


def test_supplier_activation_is_idempotent(supplier):
    assert services.set_supplier_active(supplier, False).is_active is False
    assert services.set_supplier_active(supplier, False).is_active is False
    assert services.set_supplier_active(supplier, True).is_active is True


# --- Purchase orders ------------------------------------------------------------------------
def make_po(supplier, flour, kilogram, staff_user, **kw):
    return services.create_purchase_order(
        supplier=supplier,
        currency="sek",
        created_by=staff_user,
        lines=[POLineInput(flour, Decimal("10"), kilogram, Decimal("12.50"))],
        **kw,
    )


def test_create_po_converts_to_base_units(supplier, flour, kilogram, staff_user):
    po = make_po(supplier, flour, kilogram, staff_user)
    line = po.lines.get()
    assert (po.status, po.currency) == ("draft", "SEK")
    assert po.po_number.startswith("PO-")
    assert (line.ordered_quantity, line.ordered_base_quantity) == (
        Decimal("10.0000"),
        Decimal("10000.0000"),
    )


def test_po_rejects_duplicates_inactive_ingredients_and_suppliers(
    supplier, flour, kilogram, gram, staff_user
):
    with pytest.raises(ValidationError):
        services.create_purchase_order(
            supplier=supplier,
            currency="SEK",
            created_by=staff_user,
            lines=[
                POLineInput(flour, Decimal("1"), kilogram, Decimal("1")),
                POLineInput(flour, Decimal("2"), gram, Decimal("1")),
            ],
        )
    assert PurchaseOrder.objects.count() == 0  # atomic
    flour.is_active = False
    flour.save()
    with pytest.raises(ValidationError):
        make_po(supplier, flour, kilogram, staff_user)
    flour.is_active = True
    flour.save()
    services.set_supplier_active(supplier, False)
    with pytest.raises(ValidationError):
        make_po(supplier, flour, kilogram, staff_user)


def test_po_state_machine(supplier, flour, kilogram, staff_user):
    po = make_po(supplier, flour, kilogram, staff_user)
    empty = services.create_purchase_order(supplier=supplier, currency="SEK", created_by=staff_user)
    with pytest.raises(ValidationError):
        services.submit_purchase_order(empty)
    submitted = services.submit_purchase_order(po)
    assert submitted.status == "submitted" and submitted.ordered_at is not None
    assert services.submit_purchase_order(po).status == "submitted"  # idempotent
    with pytest.raises(InvalidStateTransition):
        services.update_purchase_order(po, lines=[])  # no longer a draft
    assert services.cancel_purchase_order(po).status == "cancelled"
    assert services.cancel_purchase_order(po).status == "cancelled"  # idempotent
    with pytest.raises(InvalidStateTransition):
        services.submit_purchase_order(po)


def test_receipt_requires_a_submitted_order(supplier, flour, kilogram, staff_user, today):
    po = make_po(supplier, flour, kilogram, staff_user)
    line = ReceiptLineInput(
        po.lines.get(), Decimal("1"), kilogram, "X-1", today + timedelta(days=9)
    )
    with pytest.raises(InvalidStateTransition):
        services.post_goods_receipt(purchase_order=po, lines=[line], actor=staff_user)


# --- Goods receipt --------------------------------------------------------------------------
def test_partial_then_full_receipt_updates_order_status(submitted_po, receive):
    receive("40", "A")
    submitted_po.refresh_from_db()
    assert submitted_po.status == "partially_received"
    assert submitted_po.lines.get().received_base_quantity == Decimal("40000.0000")
    receive("60", "B")
    submitted_po.refresh_from_db()
    assert submitted_po.status == "received"
    assert InventoryLot.objects.count() == 2


def test_receipt_in_another_unit_and_multiple_lots_per_line(
    submitted_po, staff_user, gram, kilogram, today
):
    po_line = submitted_po.lines.get()
    receipt = services.post_goods_receipt(
        purchase_order=submitted_po,
        actor=staff_user,
        lines=[
            ReceiptLineInput(po_line, Decimal("20"), kilogram, "L1", today + timedelta(days=20)),
            ReceiptLineInput(po_line, Decimal("5000"), gram, "L2", today + timedelta(days=10)),
        ],
    )
    lots = {line.supplier_lot_code: line.lot for line in receipt.lines.all()}
    assert lots["L1"].on_hand == Decimal("20000.0000")
    assert lots["L2"].on_hand == Decimal("5000.0000")
    assert receipt.status == "posted"


def test_over_receipt_beyond_tolerance_is_rejected_atomically(submitted_po, receive):
    receive("100", "A")  # exactly the ordered quantity
    submitted_po.refresh_from_db()
    assert submitted_po.status == "received"
    with pytest.raises(InvalidStateTransition):
        receive("1", "B")


def test_within_tolerance_is_accepted_beyond_is_not(submitted_po, receive):
    receive("105", "A")  # 5% over: fine
    submitted_po.refresh_from_db()
    assert submitted_po.status == "received"


def test_over_receipt_rolls_everything_back(submitted_po, staff_user, kilogram, today):
    po_line = submitted_po.lines.get()
    with pytest.raises(Conflict):
        services.post_goods_receipt(
            purchase_order=submitted_po,
            actor=staff_user,
            lines=[
                ReceiptLineInput(
                    po_line, Decimal("120"), kilogram, "BIG", today + timedelta(days=9)
                )
            ],
        )
    assert InventoryLot.objects.count() == 0
    assert GoodsReceipt.objects.count() == 0
    submitted_po.refresh_from_db()
    assert submitted_po.status == "submitted"
    assert submitted_po.lines.get().received_base_quantity == 0


def test_receipt_line_validation(submitted_po, staff_user, kilogram, today):
    po_line = submitted_po.lines.get()
    good = ReceiptLineInput(po_line, Decimal("1"), kilogram, "OK-1", today + timedelta(days=5))
    with pytest.raises(ValidationError):
        services.post_goods_receipt(purchase_order=submitted_po, lines=[], actor=staff_user)
    with pytest.raises(ValidationError):  # lot code mandatory (05 §4)
        services.post_goods_receipt(
            purchase_order=submitted_po,
            actor=staff_user,
            lines=[
                ReceiptLineInput(po_line, Decimal("1"), kilogram, "  ", today + timedelta(days=5))
            ],
        )
    with pytest.raises(ValidationError):  # already expired
        services.post_goods_receipt(
            purchase_order=submitted_po,
            actor=staff_user,
            lines=[
                ReceiptLineInput(po_line, Decimal("1"), kilogram, "OLD", today - timedelta(days=1))
            ],
        )
    with pytest.raises(ValidationError):  # received in the future
        services.post_goods_receipt(
            purchase_order=submitted_po,
            actor=staff_user,
            lines=[good],
            received_at=timezone.now() + timedelta(days=2),
        )
    assert InventoryLot.objects.count() == 0


def test_line_of_another_order_is_rejected(
    supplier, flour, kilogram, staff_user, submitted_po, today
):
    other = services.submit_purchase_order(make_po(supplier, flour, kilogram, staff_user))
    foreign = ReceiptLineInput(
        other.lines.get(), Decimal("1"), kilogram, "F-1", today + timedelta(days=5)
    )
    with pytest.raises(ValidationError):
        services.post_goods_receipt(purchase_order=submitted_po, lines=[foreign], actor=staff_user)
    assert InventoryLot.objects.count() == 0

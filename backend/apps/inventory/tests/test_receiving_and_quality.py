from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from apps.core.api_errors import Conflict, InsufficientStock, InvalidStateTransition
from apps.inventory import selectors, services
from apps.inventory.models import InventoryLot, LotQualityEvent, StockMovement
from apps.purchasing import services as purchasing_services

pytestmark = pytest.mark.django_db


# --- Receiving ------------------------------------------------------------------------------
def test_receipt_creates_a_pending_lot_with_a_ledger_entry(receive):
    lot = receive("40", "SUP-A")
    assert lot.quality_status == "pending"
    assert lot.on_hand == Decimal("40000.0000")  # 40 kg in the base unit g
    assert lot.initial_quantity == lot.on_hand
    assert lot.reserved == 0
    [movement] = lot.movements.all()
    assert movement.movement_type == "receipt"
    assert movement.quantity_delta == Decimal("40000.0000")
    assert movement.balance_after == Decimal("40000.0000")
    assert movement.unit.code == "g"
    assert lot.internal_lot_code and lot.supplier_lot_code == "SUP-A"


def test_pending_stock_is_physical_but_not_available(receive, flour):
    receive("10", "SUP-A")
    [level] = selectors.stock_levels()
    assert level["physical"] == Decimal("10000.0000")
    assert level["available"] == 0
    assert level["unavailable"] == Decimal("10000.0000")


def test_release_makes_stock_available_and_is_logged(receive, staff_user):
    lot = receive("10", "SUP-A")
    released = services.release_lot(lot, actor=staff_user, reason="Temperature OK")
    assert released.quality_status == "released"
    [level] = selectors.stock_levels()
    assert (level["available"], level["unavailable"]) == (Decimal("10000.0000"), 0)
    event = LotQualityEvent.objects.get(lot=lot)
    assert (event.from_status, event.to_status, event.actor) == ("pending", "released", staff_user)
    assert event.reason == "Temperature OK"


def test_release_requires_a_reason_and_is_idempotent(receive, staff_user):
    lot = receive("10", "SUP-A")
    with pytest.raises(ValidationError):
        services.release_lot(lot, actor=staff_user, reason="  ")
    services.release_lot(lot, actor=staff_user, reason="ok")
    services.release_lot(lot, actor=staff_user, reason="ok again")
    assert LotQualityEvent.objects.filter(lot=lot).count() == 1


def test_blocked_lot_is_excluded_and_can_be_released_again(make_released_lot, staff_user):
    lot = make_released_lot("10", "SUP-A")
    blocked = services.block_lot(lot, actor=staff_user, reason="Supplier recall")
    assert blocked.quality_status == "blocked"
    assert selectors.stock_levels()[0]["available"] == 0
    services.release_lot(lot, actor=staff_user, reason="Recall cancelled")
    assert selectors.stock_levels()[0]["available"] == Decimal("10000.0000")
    assert LotQualityEvent.objects.filter(lot=lot).count() == 3


def test_expired_lots_are_not_available(make_released_lot, today):
    lot = make_released_lot("10", "SUP-A", days=5)
    assert selectors.stock_levels(today=today)[0]["available"] == Decimal("10000.0000")
    from datetime import timedelta

    later = today + timedelta(days=6)
    assert selectors.stock_levels(today=later)[0]["available"] == 0
    assert selectors.stock_levels(today=later)[0]["unavailable"] == Decimal("10000.0000")
    assert lot.is_usable(today) and not lot.is_usable(later)


def test_physical_equals_reserved_plus_available_plus_unavailable(
    make_released_lot, receive, flour, gram
):
    from uuid import uuid4

    make_released_lot("10", "SUP-A")
    receive("5", "SUP-B")  # stays pending
    services.reserve_stock(
        ingredient=flour,
        quantity=Decimal("3000"),
        unit=gram,
        reference_type="order",
        reference_id=uuid4(),
    )
    [level] = selectors.stock_levels()
    assert level["physical"] == (
        level["reserved_total"] + level["available"] + level["unavailable"]
    )
    assert level["available"] == Decimal("7000.0000")
    assert level["unavailable"] == Decimal("5000.0000")


# --- Database guarantees --------------------------------------------------------------------
def test_database_refuses_negative_or_over_reserved_stock(make_released_lot):
    lot = make_released_lot("1", "SUP-A")
    InventoryLot.objects.filter(pk=lot.pk)  # constraints apply even to raw updates:
    with pytest.raises(IntegrityError), transaction.atomic():
        InventoryLot.objects.filter(pk=lot.pk).update(on_hand=-1)
    with pytest.raises(IntegrityError), transaction.atomic():
        InventoryLot.objects.filter(pk=lot.pk).update(reserved=lot.on_hand + 1)


def test_ledger_is_append_only(receive):
    movement = receive("1", "SUP-A").movements.get()
    movement.reason = "tampered"
    with pytest.raises(ValueError):
        movement.save()
    with pytest.raises(ValueError):
        movement.delete()


def test_movement_sign_must_match_its_type(receive, gram):
    lot = receive("1", "SUP-A")
    for movement_type, delta in [("receipt", -5), ("consumption", 5), ("waste", 5), ("return", -1)]:
        with pytest.raises(IntegrityError), transaction.atomic():
            StockMovement.objects.create(
                lot=lot,
                movement_type=movement_type,
                quantity_delta=Decimal(delta),
                unit=gram,
                balance_after=Decimal("1"),
            )


def test_adjustments_need_a_reason_by_constraint(receive, gram):
    lot = receive("1", "SUP-A")
    with pytest.raises(IntegrityError), transaction.atomic():
        StockMovement.objects.create(
            lot=lot,
            movement_type="adjustment",
            quantity_delta=Decimal("1"),
            unit=gram,
            balance_after=Decimal("1"),
        )


# --- Adjustments and reversals --------------------------------------------------------------
def test_adjustment_changes_stock_through_the_ledger(make_released_lot, staff_user, gram, kilogram):
    lot = make_released_lot("10", "SUP-A")
    services.adjust_stock(
        lot, quantity=Decimal("-2.5"), unit=kilogram, reason="Count", actor=staff_user
    )
    services.adjust_stock(lot, quantity=Decimal("100"), unit=gram, reason="Found", actor=staff_user)
    lot.refresh_from_db()
    assert lot.on_hand == Decimal("7600.0000")
    assert [m.balance_after for m in lot.movements.all()] == [
        Decimal("10000.0000"),
        Decimal("7500.0000"),
        Decimal("7600.0000"),
    ]
    assert selectors.reconcile() == []


def test_adjustment_validation(make_released_lot, staff_user, gram):
    lot = make_released_lot("1", "SUP-A")
    kwargs = {"unit": gram, "actor": staff_user}
    with pytest.raises(ValidationError):
        services.adjust_stock(lot, quantity=Decimal("0"), reason="x", **kwargs)
    with pytest.raises(ValidationError):
        services.adjust_stock(lot, quantity=Decimal("5"), reason="", **kwargs)
    with pytest.raises(ValidationError):
        services.adjust_stock(
            lot, quantity=Decimal("5"), reason="x", movement_type="waste", **kwargs
        )
    with pytest.raises(ValidationError):
        services.adjust_stock(
            lot, quantity=Decimal("5"), reason="x", movement_type="receipt", **kwargs
        )


def test_cannot_remove_more_than_on_hand_or_reserved_stock(
    make_released_lot, staff_user, gram, flour
):
    from uuid import uuid4

    lot = make_released_lot("1", "SUP-A")  # 1000 g
    with pytest.raises(InsufficientStock):
        services.adjust_stock(
            lot, quantity=Decimal("-1001"), unit=gram, reason="x", actor=staff_user
        )
    services.reserve_stock(
        ingredient=flour,
        quantity=Decimal("600"),
        unit=gram,
        reference_type="order",
        reference_id=uuid4(),
    )
    with pytest.raises(InsufficientStock):  # only 400 g is free
        services.adjust_stock(
            lot, quantity=Decimal("-500"), unit=gram, reason="x", actor=staff_user
        )
    services.adjust_stock(lot, quantity=Decimal("-400"), unit=gram, reason="x", actor=staff_user)
    lot.refresh_from_db()
    assert (lot.on_hand, lot.reserved) == (Decimal("600.0000"), Decimal("600.0000"))


def test_reverse_movement_restores_the_balance_once(make_released_lot, staff_user, gram):
    lot = make_released_lot("1", "SUP-A")
    movement = services.adjust_stock(
        lot, quantity=Decimal("-300"), unit=gram, reason="Spill", actor=staff_user
    )
    reversal = services.reverse_movement(movement, reason="Entered by mistake", actor=staff_user)
    lot.refresh_from_db()
    assert lot.on_hand == Decimal("1000.0000")
    assert reversal.reverses == movement and reversal.quantity_delta == Decimal("300.0000")
    with pytest.raises(InvalidStateTransition):
        services.reverse_movement(movement, reason="again", actor=staff_user)
    with pytest.raises(InvalidStateTransition):
        services.reverse_movement(reversal, reason="undo the undo", actor=staff_user)
    assert selectors.reconcile() == []


def test_reversing_a_receipt_movement_that_would_break_a_reservation_fails(
    make_released_lot, staff_user, flour, gram
):
    from uuid import uuid4

    lot = make_released_lot("1", "SUP-A")
    services.reserve_stock(
        ingredient=flour,
        quantity=Decimal("900"),
        unit=gram,
        reference_type="order",
        reference_id=uuid4(),
    )
    receipt_movement = lot.movements.get(movement_type="receipt")
    with pytest.raises(InsufficientStock):
        services.reverse_movement(receipt_movement, reason="Wrong lot", actor=staff_user)
    lot.refresh_from_db()
    assert lot.on_hand == Decimal("1000.0000")


# --- Receipt reversal -----------------------------------------------------------------------
def test_reverse_receipt_removes_stock_and_reopens_the_order(submitted_po, receive, staff_user):
    lot = receive("100", "SUP-A")
    submitted_po.refresh_from_db()
    assert submitted_po.status == "received"
    receipt = lot.receipt_line.goods_receipt
    purchasing_services.reverse_goods_receipt(
        receipt, reason="Delivered to wrong site", actor=staff_user
    )
    lot.refresh_from_db()
    receipt.refresh_from_db()
    submitted_po.refresh_from_db()
    assert lot.on_hand == 0
    assert receipt.status == "reversed" and receipt.reversed_by == staff_user
    assert submitted_po.status == "submitted"
    assert submitted_po.lines.get().received_base_quantity == 0
    assert selectors.reconcile() == []


def test_reverse_receipt_is_idempotent_and_needs_a_reason(receive, staff_user):
    lot = receive("10", "SUP-A")
    receipt = lot.receipt_line.goods_receipt
    with pytest.raises(ValidationError):
        purchasing_services.reverse_goods_receipt(receipt, reason="", actor=staff_user)
    purchasing_services.reverse_goods_receipt(receipt, reason="Mistake", actor=staff_user)
    purchasing_services.reverse_goods_receipt(receipt, reason="Mistake", actor=staff_user)
    assert lot.movements.filter(movement_type="reversal").count() == 1


def test_reverse_receipt_fails_when_stock_was_touched(make_released_lot, staff_user, gram, flour):
    from uuid import uuid4

    lot = make_released_lot("10", "SUP-A")
    services.reserve_stock(
        ingredient=flour,
        quantity=Decimal("100"),
        unit=gram,
        reference_type="order",
        reference_id=uuid4(),
    )
    receipt = lot.receipt_line.goods_receipt
    with pytest.raises(Conflict):
        purchasing_services.reverse_goods_receipt(receipt, reason="Mistake", actor=staff_user)
    receipt.refresh_from_db()
    lot.refresh_from_db()
    assert receipt.status == "posted"
    assert lot.on_hand == Decimal("10000.0000")


# --- Reconciliation -------------------------------------------------------------------------
def test_reconcile_detects_a_drifted_projection(make_released_lot):
    lot = make_released_lot("1", "SUP-A")
    assert selectors.reconcile() == []
    InventoryLot.objects.filter(pk=lot.pk).update(on_hand=Decimal("900"))
    problems = selectors.reconcile()
    assert [p["lot"] for p in problems] == [lot.internal_lot_code]
    assert problems[0]["ledger_total"] == Decimal("1000.0000")
    InventoryLot.objects.filter(pk=lot.pk).update(on_hand=Decimal("1000"), reserved=Decimal("5"))
    assert selectors.reconcile()[0]["active_reservations_total"] == 0


def test_reconcile_command(make_released_lot, capsys):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    lot = make_released_lot("1", "SUP-A")
    call_command("reconcile_inventory")
    InventoryLot.objects.filter(pk=lot.pk).update(on_hand=Decimal("1"))
    with pytest.raises(CommandError):
        call_command("reconcile_inventory")

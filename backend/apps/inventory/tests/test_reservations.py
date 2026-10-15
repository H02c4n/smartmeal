from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.api_errors import (
    IdempotencyConflict,
    InsufficientStock,
    InvalidStateTransition,
    LotBlocked,
)
from apps.inventory import selectors, services
from apps.inventory.models import InventoryLot, StockMovement, StockReservation

pytestmark = pytest.mark.django_db


def reserve(flour, gram, grams, ref=None, **extra):
    return services.reserve_stock(
        ingredient=flour,
        quantity=Decimal(grams),
        unit=gram,
        reference_type="order",
        reference_id=ref or uuid4(),
        **extra,
    )


# --- FEFO -----------------------------------------------------------------------------------
def test_fefo_takes_the_earliest_expiry_first(make_released_lot, flour, gram):
    late = make_released_lot("10", "LATE", days=60)
    soon = make_released_lot("2", "SOON", days=5)
    mid = make_released_lot("5", "MID", days=20)
    reservations = reserve(flour, gram, "6000")
    taken = {r.lot_id: r.quantity for r in reservations}
    assert taken == {soon.pk: Decimal("2000.0000"), mid.pk: Decimal("4000.0000")}
    late.refresh_from_db()
    assert late.reserved == 0


def test_fefo_ties_break_by_receipt_time_then_id(make_released_lot, flour, gram):
    first = make_released_lot("1", "FIRST", days=10)
    second = make_released_lot("1", "SECOND", days=10)
    [reservation] = reserve(flour, gram, "500")
    assert reservation.lot_id == first.pk
    assert second.reserved == 0


def test_pure_allocation_plan_is_deterministic(make_released_lot):
    a = make_released_lot("1", "A", days=3)
    b = make_released_lot("1", "B", days=1)
    allocations, total = services.plan_fefo_allocation([a, b], Decimal("1500"))
    assert [(x.lot.supplier_lot_code, x.quantity) for x in allocations] == [
        ("B", Decimal("1000.0000")),
        ("A", Decimal("500")),
    ]
    assert total == Decimal("2000.0000")


def test_only_released_unexpired_lots_are_used(make_released_lot, receive, flour, gram, staff_user):
    receive("20", "PENDING")  # never released
    blocked = make_released_lot("20", "BLOCKED")
    services.block_lot(blocked, actor=staff_user, reason="Recall")
    good = make_released_lot("1", "GOOD")
    with pytest.raises(InsufficientStock) as info:
        reserve(flour, gram, "2000")
    assert info.value.extra["available"] == "1000.0000"
    [reservation] = reserve(flour, gram, "1000")
    assert reservation.lot_id == good.pk


def test_use_by_margin_excludes_lots_that_expire_too_soon(make_released_lot, flour, gram, today):
    make_released_lot("5", "SHORT", days=2)
    long_lived = make_released_lot("5", "LONG", days=30)
    [reservation] = reserve(flour, gram, "1000", use_by_on_or_after=today + timedelta(days=7))
    assert reservation.lot_id == long_lived.pk


# --- Safety rules ---------------------------------------------------------------------------
def test_insufficient_stock_reserves_nothing(make_released_lot, flour, gram):
    lot = make_released_lot("1", "A")
    with pytest.raises(InsufficientStock) as info:
        reserve(flour, gram, "1000.0001")
    assert info.value.extra == {
        "ingredient": "FLOUR-001",
        "requested": "1000.0001",
        "available": "1000.0000",
    }
    lot.refresh_from_db()
    assert lot.reserved == 0
    assert StockReservation.objects.count() == 0


def test_cannot_over_reserve_across_consumers(make_released_lot, flour, gram):
    make_released_lot("1", "A")
    reserve(flour, gram, "700")
    with pytest.raises(InsufficientStock):
        reserve(flour, gram, "400")
    reserve(flour, gram, "300")  # exactly the remainder fits


def test_reservation_input_validation(make_released_lot, flour, gram, litre):
    make_released_lot("1", "A")
    with pytest.raises(ValidationError):
        reserve(flour, gram, "0")
    with pytest.raises(ValidationError):
        services.reserve_stock(
            ingredient=flour,
            quantity=Decimal("1"),
            unit=gram,
            reference_type="",
            reference_id=uuid4(),
        )
    with pytest.raises(ValidationError):
        reserve(flour, gram, "10", expires_at=timezone.now() - timedelta(minutes=1))
    from apps.catalog.exceptions import UnitConversionError

    with pytest.raises(UnitConversionError):  # flour has no volume conversion
        services.reserve_stock(
            ingredient=flour,
            quantity=Decimal("1"),
            unit=litre,
            reference_type="order",
            reference_id=uuid4(),
        )


# --- Idempotency ----------------------------------------------------------------------------
def test_repeating_a_reservation_returns_the_same_rows(make_released_lot, flour, gram):
    make_released_lot("1", "A")
    ref = uuid4()
    first = reserve(flour, gram, "400", ref=ref)
    again = reserve(flour, gram, "400", ref=ref)
    assert [r.pk for r in first] == [r.pk for r in again]
    assert StockReservation.objects.count() == 1
    assert InventoryLot.objects.get().reserved == Decimal("400.0000")


def test_same_reference_with_another_quantity_is_a_conflict(make_released_lot, flour, gram):
    make_released_lot("1", "A")
    ref = uuid4()
    reserve(flour, gram, "400", ref=ref)
    with pytest.raises(IdempotencyConflict):
        reserve(flour, gram, "500", ref=ref)
    assert InventoryLot.objects.get().reserved == Decimal("400.0000")


# --- Release --------------------------------------------------------------------------------
def test_release_gives_stock_back_and_is_idempotent(make_released_lot, flour, gram):
    lot = make_released_lot("1", "A")
    ref = uuid4()
    reserve(flour, gram, "600", ref=ref)
    assert services.release_reservations_for(reference_type="order", reference_id=ref) == 1
    assert services.release_reservations_for(reference_type="order", reference_id=ref) == 0
    lot.refresh_from_db()
    assert lot.reserved == 0
    assert StockReservation.objects.get().status == "released"
    reserve(flour, gram, "1000")  # all of it is free again
    assert selectors.reconcile() == []


def test_release_spans_all_lots_of_a_consumer(make_released_lot, flour, gram):
    make_released_lot("1", "A", days=5)
    make_released_lot("1", "B", days=9)
    ref = uuid4()
    assert len(reserve(flour, gram, "1500", ref=ref)) == 2
    assert services.release_reservations_for(reference_type="order", reference_id=ref) == 2
    assert InventoryLot.objects.filter(reserved__gt=0).count() == 0


def test_expired_reservations_are_released(make_released_lot, flour, gram):
    make_released_lot("1", "A")
    [reservation] = reserve(flour, gram, "500", expires_at=timezone.now() + timedelta(hours=1))
    assert services.release_expired_reservations(timezone.now()) == 0
    assert services.release_expired_reservations(timezone.now() + timedelta(hours=2)) == 1
    assert services.release_expired_reservations(timezone.now() + timedelta(hours=2)) == 0
    reservation.refresh_from_db()
    assert reservation.status == "released"
    from django.core.management import call_command

    call_command("release_expired_reservations")


# --- Consume --------------------------------------------------------------------------------
def test_consume_posts_a_movement_and_closes_the_hold(make_released_lot, flour, gram, staff_user):
    lot = make_released_lot("1", "A")
    [reservation] = reserve(flour, gram, "400")
    consumed = services.consume_reservation(reservation, actor=staff_user)
    lot.refresh_from_db()
    assert consumed.status == "consumed" and consumed.consumed_quantity == Decimal("400.0000")
    assert (lot.on_hand, lot.reserved) == (Decimal("600.0000"), 0)
    movement = lot.movements.get(movement_type="consumption")
    assert movement.quantity_delta == Decimal("-400.0000")
    assert movement.reference_type == "order"
    assert selectors.reconcile() == []


def test_partial_consumption_frees_the_rest(make_released_lot, flour, gram, staff_user):
    lot = make_released_lot("1", "A")
    [reservation] = reserve(flour, gram, "400")
    services.consume_reservation(reservation, actor=staff_user, quantity=Decimal("350"))
    lot.refresh_from_db()
    assert (lot.on_hand, lot.reserved) == (Decimal("650.0000"), 0)
    with pytest.raises(ValidationError):
        services.consume_reservation(
            reserve(flour, gram, "100")[0], actor=staff_user, quantity=Decimal("101")
        )


def test_consume_is_idempotent_and_final(make_released_lot, flour, gram, staff_user):
    lot = make_released_lot("1", "A")
    [reservation] = reserve(flour, gram, "400")
    services.consume_reservation(reservation, actor=staff_user)
    services.consume_reservation(reservation, actor=staff_user)  # replay: no second movement
    assert lot.movements.filter(movement_type="consumption").count() == 1
    with pytest.raises(IdempotencyConflict):
        services.consume_reservation(reservation, actor=staff_user, quantity=Decimal("300"))
    with pytest.raises(InvalidStateTransition):
        services.release_reservation(reservation)


def test_released_reservation_cannot_be_consumed(make_released_lot, flour, gram, staff_user):
    make_released_lot("1", "A")
    [reservation] = reserve(flour, gram, "400")
    services.release_reservation(reservation)
    with pytest.raises(InvalidStateTransition):
        services.consume_reservation(reservation, actor=staff_user)


def test_blocked_lot_cannot_be_consumed_even_if_reserved_earlier(
    make_released_lot, flour, gram, staff_user
):
    lot = make_released_lot("1", "A")
    [reservation] = reserve(flour, gram, "400")
    services.block_lot(lot, actor=staff_user, reason="Contamination suspected")
    with pytest.raises(LotBlocked) as info:
        services.consume_reservation(reservation, actor=staff_user)
    assert info.value.extra["quality_status"] == "blocked"
    lot.refresh_from_db()
    reservation.refresh_from_db()
    assert (lot.on_hand, lot.reserved) == (Decimal("1000.0000"), Decimal("400.0000"))
    assert reservation.status == "active"
    # ... and the hold can still be released, freeing the quantity bookkeeping.
    services.release_reservation(reservation)
    assert InventoryLot.objects.get().reserved == 0


def test_expired_lot_cannot_be_consumed(make_released_lot, flour, gram, staff_user):
    lot = make_released_lot("1", "A", days=1)
    [reservation] = reserve(flour, gram, "400")
    InventoryLot.objects.filter(pk=lot.pk).update(
        expiry_date=timezone.localdate() - timedelta(days=1)
    )
    with pytest.raises(LotBlocked):
        services.consume_reservation(reservation, actor=staff_user)
    assert StockMovement.objects.filter(movement_type="consumption").count() == 0

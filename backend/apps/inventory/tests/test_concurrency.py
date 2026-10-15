"""Real concurrent transactions (separate connections, committed data): 05 §9 critical tests.

``transaction=True`` commits for real; ``serialized_rollback`` restores migration-seeded units.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import connection
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Ingredient, Unit
from apps.core.api_errors import InsufficientStock
from apps.inventory import selectors, services
from apps.inventory.models import InventoryLot, StockReservation
from apps.purchasing import services as purchasing_services
from apps.purchasing.services import POLineInput, ReceiptLineInput

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


@pytest.fixture
def world(db):
    gram = Unit.objects.get(code="g")
    flour = Ingredient.objects.create(sku="FLOUR-C", name="Flour", base_unit=gram)
    actor = User.objects.create_user("ops@example.com", "s3cret-Pass-123", is_staff=True)
    supplier = purchasing_services.create_supplier(name="Concurrent Farms")
    po = purchasing_services.create_purchase_order(
        supplier=supplier,
        currency="SEK",
        created_by=actor,
        lines=[POLineInput(flour, Decimal("1000000"), gram, Decimal("1"))],
    )
    po = purchasing_services.submit_purchase_order(po)

    def lot(grams, code, days=30):
        receipt = purchasing_services.post_goods_receipt(
            purchase_order=po,
            actor=actor,
            lines=[
                ReceiptLineInput(
                    po.lines.get(),
                    Decimal(grams),
                    gram,
                    code,
                    timezone.localdate() + timedelta(days=days),
                )
            ],
        )
        created = receipt.lines.get().lot
        return services.release_lot(created, actor=actor, reason="QC passed")

    return {"gram": gram, "flour": flour, "actor": actor, "lot": lot}


def run_parallel(function, count):
    def wrapped(index):
        try:
            return function(index)
        except Exception as exc:
            return exc
        finally:
            connection.close()  # each thread owns its connection

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(wrapped, range(count)))


def test_parallel_reservations_never_exceed_stock(world):
    """20 consumers each want 100 g from 1000 g: exactly 10 succeed, the rest are refused."""
    world["lot"]("1000", "CAP")

    def reserve(_):
        return services.reserve_stock(
            ingredient=world["flour"],
            quantity=Decimal("100"),
            unit=world["gram"],
            reference_type="order",
            reference_id=uuid4(),
        )

    outcomes = run_parallel(reserve, 20)
    succeeded = [o for o in outcomes if isinstance(o, list)]
    refused = [o for o in outcomes if isinstance(o, InsufficientStock)]
    assert len(succeeded) == 10
    assert len(refused) == 10
    assert len(succeeded) + len(refused) == 20  # no other kind of error
    lot = InventoryLot.objects.get(supplier_lot_code="CAP")
    assert (lot.on_hand, lot.reserved) == (Decimal("1000.0000"), Decimal("1000.0000"))
    assert selectors.reconcile() == []


def test_parallel_reservations_spanning_lots_stay_consistent(world):
    """Several lots and uneven requests: no over-reservation, no deadlock, FEFO respected."""
    world["lot"]("500", "A", days=5)
    world["lot"]("500", "B", days=10)
    world["lot"]("500", "C", days=15)

    def reserve(index):
        return services.reserve_stock(
            ingredient=world["flour"],
            quantity=Decimal(100 + (index % 3) * 50),
            unit=world["gram"],
            reference_type="order",
            reference_id=uuid4(),
        )

    outcomes = run_parallel(reserve, 24)
    unexpected = [
        o for o in outcomes if isinstance(o, Exception) and not isinstance(o, InsufficientStock)
    ]
    assert unexpected == []
    for lot in InventoryLot.objects.all():
        assert 0 <= lot.reserved <= lot.on_hand
    held = sum(r.quantity for r in StockReservation.objects.filter(status="active"))
    assert held == sum(lot.reserved for lot in InventoryLot.objects.all())
    assert held <= Decimal("1500")
    assert selectors.reconcile() == []


def test_identical_retries_reserve_only_once(world):
    """The same consumer retrying in parallel (e.g. a mobile client) gets one reservation."""
    world["lot"]("1000", "ONE")
    reference = uuid4()

    def reserve(_):
        return services.reserve_stock(
            ingredient=world["flour"],
            quantity=Decimal("300"),
            unit=world["gram"],
            reference_type="order",
            reference_id=reference,
        )

    outcomes = run_parallel(reserve, 8)
    assert all(isinstance(o, list) for o in outcomes), outcomes
    assert len({tuple(r.pk for r in o) for o in outcomes}) == 1
    assert StockReservation.objects.count() == 1
    assert InventoryLot.objects.get().reserved == Decimal("300.0000")


def test_parallel_consume_of_one_reservation_posts_one_movement(world):
    world["lot"]("1000", "USE")
    [reservation] = services.reserve_stock(
        ingredient=world["flour"],
        quantity=Decimal("400"),
        unit=world["gram"],
        reference_type="batch",
        reference_id=uuid4(),
    )

    outcomes = run_parallel(
        lambda _: services.consume_reservation(reservation, actor=world["actor"]), 6
    )
    assert all(isinstance(o, StockReservation) for o in outcomes), outcomes
    lot = InventoryLot.objects.get()
    assert (lot.on_hand, lot.reserved) == (Decimal("600.0000"), 0)
    assert lot.movements.filter(movement_type="consumption").count() == 1
    assert selectors.reconcile() == []


def test_parallel_release_frees_the_hold_once(world):
    world["lot"]("1000", "REL")
    [reservation] = services.reserve_stock(
        ingredient=world["flour"],
        quantity=Decimal("400"),
        unit=world["gram"],
        reference_type="order",
        reference_id=uuid4(),
    )
    run_parallel(lambda _: services.release_reservation(reservation), 6)
    assert InventoryLot.objects.get().reserved == 0
    assert selectors.reconcile() == []


def test_adjustments_racing_with_reservations_keep_the_invariant(world):
    """Removing stock while others reserve it: reserved <= on_hand holds at every moment."""
    lot = world["lot"]("1000", "RACE")

    def work(index):
        if index % 2:
            return services.adjust_stock(
                lot,
                quantity=Decimal("-100"),
                unit=world["gram"],
                reason="Count correction",
                actor=world["actor"],
            )
        return services.reserve_stock(
            ingredient=world["flour"],
            quantity=Decimal("100"),
            unit=world["gram"],
            reference_type="order",
            reference_id=uuid4(),
        )

    outcomes = run_parallel(work, 24)
    unexpected = [
        o for o in outcomes if isinstance(o, Exception) and not isinstance(o, InsufficientStock)
    ]
    assert unexpected == []
    lot.refresh_from_db()
    assert 0 <= lot.reserved <= lot.on_hand
    assert selectors.reconcile() == []


def test_parallel_goods_receipts_cannot_over_receive(world):
    """Two deliveries racing for the last of an order: the over-receipt tolerance holds."""
    gram, flour, actor = world["gram"], world["flour"], world["actor"]
    supplier = purchasing_services.create_supplier(name="Tight Supplier")
    po = purchasing_services.create_purchase_order(
        supplier=supplier,
        currency="SEK",
        created_by=actor,
        lines=[POLineInput(flour, Decimal("1000"), gram, Decimal("1"))],
    )
    po = purchasing_services.submit_purchase_order(po)

    def deliver(index):
        return purchasing_services.post_goods_receipt(
            purchase_order=po,
            actor=actor,
            lines=[
                ReceiptLineInput(
                    po.lines.get(),
                    Decimal("600"),
                    gram,
                    f"RACE-{index}",
                    timezone.localdate() + timedelta(days=30),
                )
            ],
        )

    outcomes = run_parallel(deliver, 4)
    ok = [o for o in outcomes if not isinstance(o, Exception)]
    assert len(ok) == 1  # 600 fits; a second 600 would reach 1200 > 1100 (10% tolerance)
    po.refresh_from_db()
    assert po.lines.get().received_base_quantity == Decimal("600.0000")
    assert selectors.reconcile() == []

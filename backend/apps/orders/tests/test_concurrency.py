"""Real concurrent order placement (separate connections, committed data): 05 §9."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone

from apps.accounts.models import RoleAssignment, User
from apps.accounts.roles import Role
from apps.catalog.models import Ingredient, Product, Unit
from apps.core.api_errors import InsufficientStock
from apps.inventory import services as inventory_services
from apps.inventory.models import InventoryLot, StockReservation
from apps.orders import services
from apps.orders.models import CustomerAddress, Order
from apps.orders.services import OrderItemInput
from apps.purchasing import services as purchasing
from apps.recipes import services as recipes
from apps.recipes.services import LineInput

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


@pytest.fixture
def world(db):
    gram, piece = Unit.objects.get(code="g"), Unit.objects.get(code="pcs")
    flour = Ingredient.objects.create(sku="FLOUR-X", name="Flour", base_unit=gram)
    ops = User.objects.create_user("ops@example.com", "s3cret-Pass-123")
    item = Product.objects.create(sku="MEAL-X", name="Bowl", price=Decimal("10.00"), currency="SEK")
    version = recipes.create_recipe_version(
        product=item,
        yield_quantity=Decimal("1"),
        yield_unit=piece,
        lines=[LineInput(flour, Decimal("100"), gram)],
    )
    recipes.approve_recipe_version(version, actor=ops)
    po = purchasing.submit_purchase_order(
        purchasing.create_purchase_order(
            supplier=purchasing.create_supplier(name="Concurrent Farms"),
            currency="SEK",
            created_by=ops,
            lines=[purchasing.POLineInput(flour, Decimal("1000000"), gram, Decimal("1"))],
        )
    )

    def stock(grams):
        receipt = purchasing.post_goods_receipt(
            purchase_order=po,
            actor=ops,
            lines=[
                purchasing.ReceiptLineInput(
                    po.lines.get(),
                    Decimal(grams),
                    gram,
                    "LOT-X",
                    timezone.localdate() + timedelta(30),
                )
            ],
        )
        inventory_services.release_lot(receipt.lines.get().lot, actor=ops, reason="QC ok")

    def customer(n):
        user = User.objects.create_user(f"c{n}@example.com", "s3cret-Pass-123")
        RoleAssignment.objects.create(user=user, role_code=Role.CUSTOMER)
        address = CustomerAddress.objects.create(
            user=user, recipient_name="X", line1="1", postal_code="1", city="C", country_code="SE"
        )
        return user, address

    return {"product": item, "stock": stock, "customer": customer}


def run_parallel(function, count):
    def wrapped(index):
        try:
            return function(index)
        except Exception as exc:
            return exc
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(wrapped, range(count)))


def test_parallel_orders_never_oversell(world):
    """15 customers each order 2 bowls (200 g) from 1000 g: exactly 5 succeed."""
    world["stock"]("1000")
    people = [world["customer"](n) for n in range(15)]
    when = timezone.localdate() + timedelta(days=5)

    def attempt(index):
        user, address = people[index]
        return services.place_order(
            customer=user,
            items=[OrderItemInput(world["product"], 2)],
            delivery_date=when,
            address=address,
        )

    results = run_parallel(attempt, 15)
    placed = [r for r in results if isinstance(r, Order)]
    refused = [r for r in results if isinstance(r, InsufficientStock)]
    assert len(placed) == 5 and len(refused) == 10, results

    lot = InventoryLot.objects.get()
    assert lot.reserved == Decimal("1000") and lot.available == 0
    held = sum(r.quantity for r in StockReservation.objects.filter(status="active"))
    assert held == lot.reserved
    assert Order.objects.count() == 5
    numbers = sorted(Order.objects.values_list("order_number", flat=True))
    assert len(set(numbers)) == 5 and numbers[0].endswith("-0001") and numbers[-1].endswith("-0005")


def test_parallel_cancel_and_order_keep_the_books_balanced(world):
    world["stock"]("400")  # exactly 2 orders of 2 bowls
    user, address = world["customer"](0)
    when = timezone.localdate() + timedelta(days=5)
    first = services.place_order(
        customer=user,
        items=[OrderItemInput(world["product"], 2)],
        delivery_date=when,
        address=address,
    )

    def work(index):
        if index == 0:
            return services.cancel_order(first, actor=user, customer_rules=True)
        return services.cancel_order(first, actor=user, customer_rules=True)

    results = run_parallel(work, 6)  # six simultaneous cancellations of the same order
    assert all(isinstance(r, Order) and r.status == "cancelled" for r in results), results
    assert InventoryLot.objects.get().reserved == 0
    assert Order.objects.get().events.count() == 2  # created + exactly one cancellation

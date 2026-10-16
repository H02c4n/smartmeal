from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Ingredient, Product
from apps.core.api_errors import Conflict, InsufficientStock
from apps.inventory import selectors as inventory_selectors
from apps.inventory import services as inventory_services
from apps.inventory.models import InventoryLot, StockReservation
from apps.orders import services
from apps.orders.models import Order, OrderLine, OrderStatusEvent
from apps.orders.services import OrderItemInput

pytestmark = pytest.mark.django_db


def place(customer, address, delivery_date, *pairs, **kwargs):
    return services.place_order(
        customer=customer,
        items=[OrderItemInput(product, quantity) for product, quantity in pairs],
        delivery_date=delivery_date,
        address=address,
        **kwargs,
    )


def reserved_grams(flour):
    return inventory_selectors.stock_levels(ingredient_sku=flour.sku)[0]["reserved_total"]


# --- Happy path and snapshots ----------------------------------------
def test_place_order_confirms_prices_and_reserves_stock(
    customer, address, delivery_date, bowl, wrap, stocked, flour
):
    order = place(customer, address, delivery_date, (bowl, 3), (wrap, 2))

    assert order.status == Order.Status.CONFIRMED
    assert order.order_number.startswith(f"SM-{timezone.localdate():%Y%m%d}-")
    assert order.subtotal == Decimal("586.00")  # 3 x 129.00 + 2 x 99.50
    assert (order.tax_amount, order.delivery_fee) == (Decimal("0"), Decimal("0"))
    assert order.total_amount == Decimal("586.00")
    assert order.currency == "SEK"
    assert order.delivery_address_snapshot["city"] == "Stockholm"

    lines = {line.product_sku_snapshot: line for line in order.lines.all()}
    assert lines["MEAL-001"].line_total == Decimal("387.00")
    assert lines["MEAL-002"].line_total == Decimal("199.00")
    assert lines["MEAL-001"].recipe_version.product == bowl

    # 3 x 200 g + 2 x 100 g flour = 800 g, reserved once for the whole order.
    assert reserved_grams(flour) == Decimal("800.0000")
    reservations = StockReservation.objects.filter(reference_type="order", reference_id=order.pk)
    assert sum(r.quantity for r in reservations) == Decimal("800.0000")

    event = order.events.get()
    assert (event.from_status, event.to_status, event.actor) == ("", "confirmed", customer)


def test_order_keeps_its_price_recipe_and_address_when_the_catalog_changes(
    customer, address, delivery_date, bowl, stocked, staff_user, make_recipe, flour, gram
):
    order = place(customer, address, delivery_date, (bowl, 1))
    original_version = order.lines.get().recipe_version_id

    bowl.price = Decimal("150.00")
    bowl.name = "Renamed bowl"
    bowl.save()
    make_recipe(bowl, [(flour, "999", gram)])  # a new approved version retires the old one
    address.city = "Uppsala"
    address.save()

    line = Order.objects.get(pk=order.pk).lines.get()
    assert (line.unit_price, line.product_name_snapshot) == (Decimal("129.00"), "Chicken bowl")
    assert line.recipe_version_id == original_version
    assert Order.objects.get(pk=order.pk).delivery_address_snapshot["city"] == "Stockholm"


def test_order_numbers_count_up_per_day(customer, address, delivery_date, bowl, stocked):
    first = place(customer, address, delivery_date, (bowl, 1))
    second = place(customer, address, delivery_date, (bowl, 1))
    assert first.order_number.endswith("-0001")
    assert second.order_number.endswith("-0002")


def test_lots_that_expire_before_delivery_are_not_reserved(
    customer, address, bowl, make_released_lot, flour
):
    make_released_lot("10", "SHORT", days=3)  # expires before the delivery date below
    far = timezone.localdate() + timedelta(days=10)
    with pytest.raises(InsufficientStock):
        place(customer, address, far, (bowl, 1))
    near = timezone.localdate() + timedelta(days=2)
    assert place(customer, address, near, (bowl, 1)).status == Order.Status.CONFIRMED


# --- Stock is all-or-nothing ----------------------------------------
def test_insufficient_stock_rejects_the_order_without_any_effect(
    customer, address, delivery_date, bowl, make_released_lot, flour
):
    make_released_lot("1", "SMALL")  # 1000 g = 5 bowls
    place(customer, address, delivery_date, (bowl, 3))  # 600 g reserved
    before = reserved_grams(flour)

    with pytest.raises(InsufficientStock) as caught:
        place(customer, address, delivery_date, (bowl, 3))  # needs 600 g, 400 g free

    assert reserved_grams(flour) == before
    assert Order.objects.count() == 1
    assert OrderLine.objects.count() == 1
    assert OrderStatusEvent.objects.count() == 1
    # Customer-safe: names the affected products, never quantities or ingredients.
    assert caught.value.extra == {"products": [str(bowl.pk)]}


def test_shortage_of_a_later_ingredient_rolls_back_earlier_reservations(
    customer, address, delivery_date, make_released_lot, make_recipe, gram, flour
):
    # Fixed ids make "flour is reserved first, then the scarce ingredient fails" deterministic.
    first = Ingredient.objects.create(
        id="00000000-0000-0000-0000-00000000000a", sku="ZZ-FIRST", name="Plenty", base_unit=gram
    )
    scarce = Ingredient.objects.create(
        id="ffffffff-ffff-ffff-ffff-fffffffffffa", sku="AA-SCARCE", name="Scarce", base_unit=gram
    )
    item = Product.objects.create(
        sku="MEAL-009", name="Two-part", price=Decimal("10"), currency="SEK"
    )
    make_recipe(item, [(first, "100", gram), (scarce, "100", gram)])
    from apps.purchasing import services as purchasing

    # Stock only for the first ingredient: build its own PO/lot.
    supplier = purchasing.create_supplier(name="Rollback Farms")
    po = purchasing.submit_purchase_order(
        purchasing.create_purchase_order(
            supplier=supplier,
            currency="SEK",
            created_by=customer,
            lines=[purchasing.POLineInput(first, Decimal("5000"), gram, Decimal("1"))],
        )
    )
    receipt = purchasing.post_goods_receipt(
        purchase_order=po,
        actor=customer,
        lines=[
            purchasing.ReceiptLineInput(
                po.lines.get(), Decimal("5000"), gram, "R-1", timezone.localdate() + timedelta(30)
            )
        ],
    )
    inventory_services.release_lot(receipt.lines.get().lot, actor=customer, reason="QC ok")

    with pytest.raises(InsufficientStock):
        place(customer, address, delivery_date, (item, 2))

    assert StockReservation.objects.count() == 0, "the first ingredient's hold must be undone"
    assert InventoryLot.objects.get().reserved == 0
    assert Order.objects.count() == 0


# --- Validation ----------------------------------------
def test_products_without_an_approved_recipe_or_inactive_are_not_orderable(
    customer, address, delivery_date, bowl, stocked
):
    no_recipe = Product.objects.create(sku="MEAL-100", name="No recipe", price=1, currency="SEK")
    with pytest.raises(ValidationError) as caught:
        place(customer, address, delivery_date, (bowl, 1), (no_recipe, 1))
    assert caught.value.detail["items"][1]["product_id"][0] == services.UNAVAILABLE_MESSAGE
    assert caught.value.detail["items"][0] == {}

    bowl.is_active = False
    bowl.save()
    with pytest.raises(ValidationError):
        place(customer, address, delivery_date, (bowl, 1))
    assert Order.objects.count() == 0


def test_a_recipe_that_is_not_piece_based_is_not_orderable(
    customer, address, delivery_date, stocked, flour, gram, kilogram, staff_user
):
    from apps.recipes import services as recipes
    from apps.recipes.services import LineInput

    item = Product.objects.create(sku="MEAL-200", name="By weight", price=5, currency="SEK")
    version = recipes.create_recipe_version(
        product=item,
        yield_quantity=Decimal("1"),
        yield_unit=kilogram,
        lines=[LineInput(flour, Decimal("1"), kilogram)],
    )
    recipes.approve_recipe_version(version, actor=staff_user)
    with pytest.raises(ValidationError):
        place(customer, address, delivery_date, (item, 1))


@pytest.mark.parametrize("days", [0, -1])
def test_delivery_date_must_respect_the_lead_time(customer, address, bowl, stocked, days):
    too_soon = timezone.localdate() + timedelta(days=days)
    with pytest.raises(ValidationError) as caught:
        place(customer, address, too_soon, (bowl, 1))
    assert "delivery_date" in caught.value.detail


@pytest.mark.parametrize("quantity", [0, -2, 101])
def test_quantity_is_bounded(customer, address, delivery_date, bowl, stocked, quantity):
    with pytest.raises(ValidationError) as caught:
        place(customer, address, delivery_date, (bowl, quantity))
    assert "quantity" in caught.value.detail["items"][0]


def test_duplicate_products_empty_orders_and_mixed_currencies_are_rejected(
    customer, address, delivery_date, bowl, wrap, stocked
):
    with pytest.raises(ValidationError):
        place(customer, address, delivery_date, (bowl, 1), (bowl, 2))
    with pytest.raises(ValidationError):
        place(customer, address, delivery_date)
    wrap.currency = "EUR"
    wrap.save()
    with pytest.raises(ValidationError) as caught:
        place(customer, address, delivery_date, (bowl, 1), (wrap, 1))
    assert "currency" in str(caught.value.detail["items"])
    assert Order.objects.count() == 0


def test_another_customers_address_cannot_be_used(
    customer, other_address, delivery_date, bowl, stocked
):
    with pytest.raises(ValidationError) as caught:
        place(customer, other_address, delivery_date, (bowl, 1))
    assert "delivery_address_id" in caught.value.detail


# --- Cancellation ----------------------------------------
def test_cancel_releases_the_reservation_and_logs_the_change(
    customer, address, delivery_date, bowl, stocked, flour
):
    order = place(customer, address, delivery_date, (bowl, 4))
    assert reserved_grams(flour) == Decimal("800.0000")

    cancelled = services.cancel_order(
        order, actor=customer, reason="Plans changed", customer_rules=True
    )

    assert cancelled.status == Order.Status.CANCELLED
    assert cancelled.cancelled_by == customer and cancelled.cancelled_at is not None
    assert reserved_grams(flour) == Decimal("0.0000")
    assert not StockReservation.objects.filter(status="active").exists()
    last = order.events.order_by("created_at").last()
    assert (last.from_status, last.to_status, last.reason) == (
        "confirmed",
        "cancelled",
        "Plans changed",
    )


def test_cancel_twice_is_harmless(customer, address, delivery_date, bowl, stocked, flour):
    order = place(customer, address, delivery_date, (bowl, 1))
    services.cancel_order(order, actor=customer, customer_rules=True)
    again = services.cancel_order(order, actor=customer, customer_rules=True)
    assert again.status == Order.Status.CANCELLED
    assert order.events.count() == 2  # created + one cancellation, not two
    assert reserved_grams(flour) == Decimal("0.0000")


def test_cancelled_stock_can_be_ordered_by_someone_else(
    customer, other_customer, address, other_address, delivery_date, bowl, make_released_lot
):
    make_released_lot("1", "ONE-KG")  # exactly 5 bowls
    mine = place(customer, address, delivery_date, (bowl, 5))
    with pytest.raises(InsufficientStock):
        place(other_customer, other_address, delivery_date, (bowl, 1))
    services.cancel_order(mine, actor=customer, customer_rules=True)
    assert place(other_customer, other_address, delivery_date, (bowl, 5)).status == "confirmed"


def test_customer_cannot_cancel_after_the_deadline(customer, address, bowl, stocked, flour):
    delivery = timezone.localdate() + timedelta(days=1)  # deadline is delivery - 1 day = today
    order = place(customer, address, delivery, (bowl, 1))
    assert services.cancel_order(order, actor=customer, customer_rules=True).status == "cancelled"

    # An order whose delivery day is today can no longer be cancelled by the customer.
    late = place(customer, address, delivery, (bowl, 1))
    Order.objects.filter(pk=late.pk).update(delivery_date=timezone.localdate())
    with pytest.raises(Conflict) as caught:
        services.cancel_order(late, actor=customer, customer_rules=True)
    assert "latest_cancellation_date" in caught.value.extra
    assert Order.objects.get(pk=late.pk).status == "confirmed"
    assert reserved_grams(flour) == Decimal("200.0000")


def test_staff_may_cancel_after_the_deadline_but_must_give_a_reason(
    customer, staff_user, address, bowl, stocked, flour
):
    order = place(customer, address, timezone.localdate() + timedelta(days=1), (bowl, 1))
    Order.objects.filter(pk=order.pk).update(delivery_date=timezone.localdate())
    with pytest.raises(ValidationError):
        services.cancel_order(order, actor=staff_user, reason="  ", customer_rules=False)
    done = services.cancel_order(
        order, actor=staff_user, reason="Kitchen closed", customer_rules=False
    )
    assert done.status == "cancelled" and done.cancelled_by == staff_user
    assert reserved_grams(flour) == Decimal("0.0000")


def test_a_customer_cannot_cancel_someone_elses_order(
    customer, other_customer, address, delivery_date, bowl, stocked
):
    from django.core.exceptions import PermissionDenied

    order = place(customer, address, delivery_date, (bowl, 1))
    with pytest.raises(PermissionDenied):
        services.cancel_order(order, actor=other_customer, customer_rules=True)
    assert Order.objects.get(pk=order.pk).status == "confirmed"


# --- Immutability ----------------------------------------
def test_order_lines_and_events_cannot_be_edited_or_deleted(
    customer, address, delivery_date, bowl, stocked
):
    order = place(customer, address, delivery_date, (bowl, 1))
    line, event = order.lines.get(), order.events.get()
    line.quantity = 99
    with pytest.raises(ValueError, match="immutable"):
        line.save()
    with pytest.raises(ValueError, match="immutable"):
        line.delete()
    event.reason = "rewritten"
    with pytest.raises(ValueError, match="append-only"):
        event.save()
    with pytest.raises(ValueError, match="append-only"):
        event.delete()

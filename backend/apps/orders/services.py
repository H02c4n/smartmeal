"""Order placement and cancellation (ADR-014). The only writers of orders tables.

Placement is one transaction: validate -> price/recipe snapshot -> reserve ingredient stock
(FEFO, via ``inventory.services``) -> write order, lines and the first status event. Any failure
(including ``INSUFFICIENT_STOCK`` for the last ingredient) rolls back everything, so there is
never an order without its reservation, nor a reservation without its order.

Dependencies follow 01 §4: ``orders`` reads catalog/recipes and calls ``inventory`` services; it
never writes their tables.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Ingredient, Product, Unit
from apps.core.api_errors import Conflict, InsufficientStock, InvalidStateTransition
from apps.inventory import services as inventory_services
from apps.recipes import services as recipe_services
from apps.recipes.models import RecipeVersion

from .models import (
    CustomerAddress,
    Order,
    OrderLine,
    OrderNumberCounter,
    OrderStatusEvent,
)

logger = logging.getLogger(__name__)

RESERVATION_REFERENCE_TYPE = "order"
UNAVAILABLE_MESSAGE = "This product is not available for ordering."
COUNT_UNIT_CODE = "pcs"  # an ordered unit is one piece of the product (ADR-014 §5)
TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class OrderItemInput:
    product: Product
    quantity: int


def _items_error(index: int, count: int, field: str, message: str) -> ValidationError:
    """Validation error aligned with the request's ``items`` list (empty dict = no error)."""
    errors: list[dict] = [{} for _ in range(count)]
    errors[index] = {field: [message]}
    return ValidationError({"items": errors})


def _next_order_number(day: date) -> str:
    """``SM-YYYYMMDD-NNNN``; must run inside the order transaction (row lock on the counter)."""
    OrderNumberCounter.objects.get_or_create(day=day)
    counter = OrderNumberCounter.objects.select_for_update().get(day=day)
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    return f"SM-{day:%Y%m%d}-{counter.last_number:04d}"


def _validate_request(*, customer, items, delivery_date, address, today) -> None:
    if address.user_id != customer.pk:
        raise ValidationError({"delivery_address_id": ["Address not found."]})
    earliest = today + timedelta(days=settings.ORDER_MIN_LEAD_DAYS)
    if delivery_date < earliest:
        raise ValidationError(
            {"delivery_date": [f"The earliest possible delivery date is {earliest.isoformat()}."]}
        )
    if not items:
        raise ValidationError({"items": ["At least one item is required."]})
    if len(items) > settings.ORDER_MAX_LINES:
        raise ValidationError({"items": [f"At most {settings.ORDER_MAX_LINES} items per order."]})
    seen: set = set()
    for index, item in enumerate(items):
        if item.product.pk in seen:
            raise _items_error(index, len(items), "product_id", "Each product may appear once.")
        seen.add(item.product.pk)
        if not 1 <= item.quantity <= settings.ORDER_MAX_LINE_QUANTITY:
            raise _items_error(
                index,
                len(items),
                "quantity",
                f"Must be between 1 and {settings.ORDER_MAX_LINE_QUANTITY}.",
            )
        if not item.product.is_active:
            raise _items_error(index, len(items), "product_id", UNAVAILABLE_MESSAGE)
    currencies = {item.product.currency for item in items}
    if len(currencies) > 1:
        raise ValidationError({"items": ["All products in one order must share a currency."]})


def place_order(
    *,
    customer,
    items: list[OrderItemInput],
    delivery_date: date,
    address: CustomerAddress,
    today: date | None = None,
) -> Order:
    """Create a confirmed order and reserve the stock it needs, or fail without any effect."""
    today = today or timezone.localdate()
    _validate_request(
        customer=customer, items=items, delivery_date=delivery_date, address=address, today=today
    )
    piece = Unit.objects.get(code=COUNT_UNIT_CODE)
    order_id = uuid.uuid4()

    with transaction.atomic():
        # --- Snapshot: approved recipe per product and the ingredient need of the whole order ---
        versions: dict = {}
        needs: dict = {}  # ingredient pk -> [ingredient, total gross base quantity]
        users_of: dict = {}  # ingredient pk -> product ids that need it
        for index, item in enumerate(items):
            version = (
                RecipeVersion.objects.filter(
                    product=item.product, status=RecipeVersion.Status.APPROVED
                )
                .select_related("yield_unit")
                .first()
            )
            if version is None or version.yield_unit.dimension != Unit.Dimension.COUNT:
                # Same message as an inactive product: the customer cannot act on the reason.
                logger.warning(
                    "Product %s cannot be ordered: %s",
                    item.product.sku,
                    "no approved recipe" if version is None else "recipe yield is not count-based",
                )
                raise _items_error(index, len(items), "product_id", UNAVAILABLE_MESSAGE)
            versions[item.product.pk] = version
            for need in recipe_services.calculate_requirements(
                version, quantity=item.quantity, unit=piece
            ):
                entry = needs.setdefault(need.ingredient.pk, [need.ingredient, Decimal("0")])
                entry[1] += need.gross_quantity
                users_of.setdefault(need.ingredient.pk, set()).add(item.product.pk)

        # --- Reserve stock: one reservation per ingredient, in a fixed order (no lock cycles) ---
        for ingredient_pk in sorted(needs, key=str):
            ingredient, quantity = needs[ingredient_pk]
            _reserve(
                ingredient,
                quantity,
                order_id=order_id,
                delivery_date=delivery_date,
                affected_products=users_of[ingredient_pk],
            )

        # --- Order, lines, first event (order number last: shortest hold on the counter row) ---
        subtotal = sum(
            (item.product.price * item.quantity for item in items), Decimal("0")
        ).quantize(TWO_PLACES)
        now = timezone.now()
        order = Order.objects.create(
            id=order_id,
            order_number=_next_order_number(today),
            customer=customer,
            status=Order.Status.CONFIRMED,
            delivery_date=delivery_date,
            delivery_address_snapshot=address.snapshot(),
            currency=items[0].product.currency,
            subtotal=subtotal,
            tax_amount=Decimal("0.00"),
            delivery_fee=Decimal("0.00"),
            total_amount=subtotal,
            confirmed_at=now,
        )
        for item in items:
            OrderLine.objects.create(
                order=order,
                product=item.product,
                product_sku_snapshot=item.product.sku,
                product_name_snapshot=item.product.name,
                quantity=item.quantity,
                unit_price=item.product.price,
                line_total=(item.product.price * item.quantity).quantize(TWO_PLACES),
                recipe_version=versions[item.product.pk],
            )
        OrderStatusEvent.objects.create(
            order=order, from_status="", to_status=Order.Status.CONFIRMED, actor=customer
        )
    return order


def _reserve(
    ingredient: Ingredient, quantity: Decimal, *, order_id, delivery_date, affected_products
) -> None:
    try:
        inventory_services.reserve_stock(
            ingredient=ingredient,
            quantity=quantity,
            unit=ingredient.base_unit,
            reference_type=RESERVATION_REFERENCE_TYPE,
            reference_id=order_id,
            # Stock must still be usable on the delivery day (production happens before it).
            use_by_on_or_after=delivery_date,
        )
    except InsufficientStock as exc:
        # Internal quantities and ingredient names stay in the log, not in the customer response.
        logger.info("Order rejected, insufficient stock: %s", exc.extra)
        raise InsufficientStock(
            "Some items are not available in the requested quantity.",
            extra={"products": sorted(str(pk) for pk in affected_products)},
        ) from None


def cancel_order(order: Order, *, actor, reason: str = "", customer_rules: bool) -> Order:
    """Cancel a confirmed order and release its reservations; idempotent.

    ``customer_rules=True`` (the customer cancelling their own order): only the owner, and only
    while delivery is at least ``ORDER_CUSTOMER_CANCEL_MIN_DAYS`` away. Staff cancellations
    (``customer_rules=False``) are not bound by that deadline but need a reason. Payment effects
    are not handled yet: no payment exists in this phase (00 §8).
    """
    reason = (reason or "").strip()
    if customer_rules and order.customer_id != actor.pk:
        raise DjangoPermissionDenied("Only the customer can cancel their own order here.")
    if not customer_rules and not reason:
        raise ValidationError(
            {"reason": ["A reason is required to cancel on a customer's behalf."]}
        )

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status == Order.Status.CANCELLED:
            return locked
        if locked.status != Order.Status.CONFIRMED:
            raise InvalidStateTransition(f"A {locked.status} order cannot be cancelled.")
        if customer_rules:
            latest = locked.delivery_date - timedelta(days=settings.ORDER_CUSTOMER_CANCEL_MIN_DAYS)
            if timezone.localdate() > latest:
                raise Conflict(
                    "The cancellation deadline for this order has passed.",
                    extra={"latest_cancellation_date": latest.isoformat()},
                )
        inventory_services.release_reservations_for(
            reference_type=RESERVATION_REFERENCE_TYPE, reference_id=locked.pk
        )
        locked.status = Order.Status.CANCELLED
        locked.cancelled_at = timezone.now()
        locked.cancelled_by = actor
        locked.cancellation_reason = reason
        locked.save(
            update_fields=[
                "status",
                "cancelled_at",
                "cancelled_by",
                "cancellation_reason",
                "updated_at",
            ]
        )
        OrderStatusEvent.objects.create(
            order=locked,
            from_status=Order.Status.CONFIRMED,
            to_status=Order.Status.CANCELLED,
            reason=reason,
            actor=actor,
        )
    return locked


# --- Address book ---------------------------------------------------------------------------
def create_address(*, user, **fields) -> CustomerAddress:
    with transaction.atomic():
        # Serialise per user so two parallel requests cannot both slip under the limit.
        # (``request.user`` is a lazy wrapper, so go through the model class, not ``type(user)``.)
        get_user_model().objects.select_for_update().get(pk=user.pk)
        if user.addresses.count() >= settings.ADDRESS_MAX_PER_CUSTOMER:
            raise ValidationError(
                {"non_field_errors": [f"At most {settings.ADDRESS_MAX_PER_CUSTOMER} addresses."]}
            )
        return CustomerAddress.objects.create(user=user, **fields)

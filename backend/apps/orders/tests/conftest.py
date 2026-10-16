from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.roles import Role
from apps.catalog.models import Product
from apps.inventory.tests.conftest import (  # noqa: F401
    egg,
    flour,
    gram,
    kilogram,
    litre,
    make_released_lot,
    milk,
    millilitre,
    piece,
    product,
    receive,
    submitted_po,
    supplier,
    today,
    units,
)
from apps.orders.models import CustomerAddress
from apps.recipes import services as recipe_services
from apps.recipes.services import LineInput


@pytest.fixture
def customer(make_user):
    return make_user("buyer@example.com", Role.CUSTOMER)


@pytest.fixture
def other_customer(make_user):
    return make_user("other@example.com", Role.CUSTOMER)


@pytest.fixture
def address(customer) -> CustomerAddress:
    return CustomerAddress.objects.create(
        user=customer,
        recipient_name="Anna Svensson",
        line1="Storgatan 1",
        postal_code="11122",
        city="Stockholm",
        country_code="SE",
        phone="+46700000000",
    )


@pytest.fixture
def other_address(other_customer) -> CustomerAddress:
    return CustomerAddress.objects.create(
        user=other_customer,
        recipient_name="Olle Persson",
        line1="Lillgatan 2",
        postal_code="22233",
        city="Malmo",
        country_code="SE",
    )


@pytest.fixture
def delivery_date():
    return timezone.localdate() + timedelta(days=5)


@pytest.fixture
def make_recipe(staff_user, piece):
    """``make_recipe(product, [(ingredient, quantity, unit), ...])`` -> approved recipe.

    Yield is 1 piece, so each ordered unit needs exactly the listed quantities.
    """

    def _make(target, lines, yield_quantity="1"):
        version = recipe_services.create_recipe_version(
            product=target,
            yield_quantity=Decimal(yield_quantity),
            yield_unit=piece,
            lines=[LineInput(ing, Decimal(qty), unit) for ing, qty, unit in lines],
        )
        return recipe_services.approve_recipe_version(version, actor=staff_user)

    return _make


@pytest.fixture
def bowl(product, make_recipe, flour, gram):
    """MEAL-001, 129.00 SEK, needs 200 g flour per piece."""
    make_recipe(product, [(flour, "200", gram)])
    return product


@pytest.fixture
def wrap(db, make_recipe, flour, gram) -> Product:
    """MEAL-002, 99.50 SEK, needs 100 g flour per piece (shares flour with ``bowl``)."""
    item = Product.objects.create(
        sku="MEAL-002", name="Veggie wrap", price=Decimal("99.50"), currency="SEK"
    )
    make_recipe(item, [(flour, "100", gram)])
    return item


@pytest.fixture
def stocked(make_released_lot):
    """10 kg of released flour: enough for 50 bowls."""
    return make_released_lot("10", "FLOUR-A", days=30)

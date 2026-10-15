from decimal import Decimal

import pytest

from apps.catalog.models import Ingredient, Product

# Reuse the catalog fixtures (units, ingredients, product) in recipe tests.
from apps.catalog.tests.conftest import (  # noqa: F401
    egg,
    flour,
    gram,
    kilogram,
    litre,
    milk,
    millilitre,
    piece,
    product,
    units,
)
from apps.recipes import services
from apps.recipes.services import LineInput


@pytest.fixture
def salt(gram) -> Ingredient:
    return Ingredient.objects.create(sku="SALT-001", name="Salt", base_unit=gram)


@pytest.fixture
def other_product(db) -> Product:
    return Product.objects.create(
        sku="MEAL-002", name="Veggie wrap", price=Decimal("99.00"), currency="SEK"
    )


@pytest.fixture
def make_version(product, flour, milk, gram, kilogram, litre, piece):
    """Draft: yield 10 pcs; 2 kg flour (10% waste) and 1 l milk."""

    def _make(target=None, lines=None):
        return services.create_recipe_version(
            product=target or product,
            yield_quantity=Decimal("10"),
            yield_unit=piece,
            lines=lines
            if lines is not None
            else [
                LineInput(flour, Decimal("2"), kilogram, Decimal("0.1")),
                LineInput(milk, Decimal("1"), litre),
            ],
        )

    return _make


@pytest.fixture
def draft(make_version):
    return make_version()

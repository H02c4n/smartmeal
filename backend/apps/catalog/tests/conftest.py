from decimal import Decimal

import pytest

from apps.catalog.models import Ingredient, IngredientUnitConversion, Product, Unit


@pytest.fixture
def units(db) -> dict[str, Unit]:
    """The seeded unit dictionary (migration 0002), keyed by code."""
    return {unit.code: unit for unit in Unit.objects.all()}


@pytest.fixture
def gram(units) -> Unit:
    return units["g"]


@pytest.fixture
def kilogram(units) -> Unit:
    return units["kg"]


@pytest.fixture
def millilitre(units) -> Unit:
    return units["ml"]


@pytest.fixture
def litre(units) -> Unit:
    return units["l"]


@pytest.fixture
def piece(units) -> Unit:
    return units["pcs"]


@pytest.fixture
def flour(gram) -> Ingredient:
    return Ingredient.objects.create(sku="FLOUR-001", name="Wheat flour", base_unit=gram)


@pytest.fixture
def milk(gram, litre) -> Ingredient:
    """Base unit g; 1 l = 1030 g."""
    ingredient = Ingredient.objects.create(sku="MILK-001", name="Milk", base_unit=gram)
    IngredientUnitConversion.objects.create(
        ingredient=ingredient, unit=litre, base_unit_quantity=Decimal("1030")
    )
    return ingredient


@pytest.fixture
def egg(gram, piece) -> Ingredient:
    """Base unit g; 1 pcs = 55 g."""
    ingredient = Ingredient.objects.create(sku="EGG-001", name="Egg", base_unit=gram)
    IngredientUnitConversion.objects.create(
        ingredient=ingredient, unit=piece, base_unit_quantity=Decimal("55")
    )
    return ingredient


@pytest.fixture
def product(db) -> Product:
    return Product.objects.create(
        sku="MEAL-001", name="Chicken bowl", price=Decimal("129.00"), currency="SEK"
    )


@pytest.fixture
def inactive_product(db) -> Product:
    return Product.objects.create(
        sku="MEAL-OLD", name="Retired bowl", price=Decimal("99.00"), currency="SEK", is_active=False
    )

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.catalog.exceptions import ImmutableFieldError
from apps.catalog.models import Ingredient, IngredientUnitConversion, Product, Unit

pytestmark = pytest.mark.django_db


# --- Seeded unit dictionary -----------------------------------------------------------------
def test_unit_dictionary_is_seeded(units):
    assert {code: (u.dimension, u.factor_to_base) for code, u in units.items()} == {
        "g": ("mass", Decimal("1")),
        "kg": ("mass", Decimal("1000")),
        "ml": ("volume", Decimal("1")),
        "l": ("volume", Decimal("1000")),
        "pcs": ("count", Decimal("1")),
    }


def test_each_dimension_has_exactly_one_base_unit(units):
    for dimension in Unit.Dimension.values:
        bases = [u for u in units.values() if u.dimension == dimension and u.is_base_unit]
        assert len(bases) == 1, dimension


# --- Unit constraints -----------------------------------------------------------------------
def test_unit_factor_must_be_positive(db):
    with pytest.raises(IntegrityError), transaction.atomic():
        Unit.objects.create(code="bad", name="Bad", dimension="mass", factor_to_base=Decimal("0"))


def test_second_base_unit_in_a_dimension_is_rejected(db):
    with pytest.raises(IntegrityError), transaction.atomic():
        Unit.objects.create(code="gram2", name="G2", dimension="mass", factor_to_base=Decimal("1"))


@pytest.mark.parametrize("code", ["G", "g1", "", "a-b"])
def test_unit_code_format_is_enforced_in_db(db, code):
    with pytest.raises(IntegrityError), transaction.atomic():
        Unit.objects.create(code=code, name="X", dimension="mass", factor_to_base=Decimal("5"))


# --- Ingredient -----------------------------------------------------------------------------
def test_ingredient_sku_is_normalised_on_save(gram):
    ingredient = Ingredient.objects.create(sku="  tom-01 ", name="Tomato", base_unit=gram)
    assert ingredient.sku == "TOM-01"


def test_ingredient_sku_uniqueness_is_case_insensitive_via_normalisation(gram, flour):
    with pytest.raises(IntegrityError), transaction.atomic():
        Ingredient.objects.create(sku="flour-001", name="Dup", base_unit=gram)


@pytest.mark.parametrize("sku", ["a", "has space", "lower_ok?", "ümlaut"])
def test_ingredient_sku_format_is_enforced_in_db_even_when_save_is_bypassed(gram, sku):
    with pytest.raises(IntegrityError), transaction.atomic():
        Ingredient.objects.bulk_create([Ingredient(sku=sku, name="Bad", base_unit=gram)])


def test_ingredient_base_unit_must_be_a_base_unit(kilogram):
    ingredient = Ingredient(sku="BAD-KG", name="Bad", base_unit=kilogram)
    with pytest.raises(ValidationError) as excinfo:
        ingredient.full_clean()
    assert "base_unit" in excinfo.value.message_dict


def test_ingredient_sku_cannot_change_after_creation(flour):
    flour.sku = "OTHER-SKU"
    with pytest.raises(ImmutableFieldError):
        flour.save()
    assert Ingredient.objects.get(pk=flour.pk).sku == "FLOUR-001"


def test_ingredient_base_unit_cannot_change_after_creation(flour, millilitre):
    flour.base_unit = millilitre
    with pytest.raises(ImmutableFieldError):
        flour.save()
    assert Ingredient.objects.get(pk=flour.pk).base_unit.code == "g"


def test_ingredient_name_and_active_flag_can_change(flour):
    flour.name = "Plain flour"
    flour.is_active = False
    flour.save()
    flour.refresh_from_db()
    assert (flour.name, flour.is_active) == ("Plain flour", False)


def test_unit_in_use_cannot_be_deleted(flour, gram):
    with pytest.raises(ProtectedError):
        gram.delete()


# --- IngredientUnitConversion ---------------------------------------------------------------
def test_conversion_must_cross_dimensions(flour, kilogram):
    conversion = IngredientUnitConversion(
        ingredient=flour, unit=kilogram, base_unit_quantity=Decimal("1000")
    )
    with pytest.raises(ValidationError) as excinfo:
        conversion.full_clean()
    assert "unit" in excinfo.value.message_dict


def test_only_one_conversion_per_dimension_per_ingredient(milk, millilitre):
    # milk already has litre (volume); millilitre would be a second volume conversion
    conversion = IngredientUnitConversion(
        ingredient=milk, unit=millilitre, base_unit_quantity=Decimal("1.03")
    )
    with pytest.raises(ValidationError) as excinfo:
        conversion.full_clean()
    assert "unit" in excinfo.value.message_dict


def test_duplicate_ingredient_unit_pair_is_rejected_in_db(milk, litre):
    with pytest.raises(IntegrityError), transaction.atomic():
        IngredientUnitConversion.objects.create(
            ingredient=milk, unit=litre, base_unit_quantity=Decimal("1")
        )


@pytest.mark.parametrize("value", ["0", "-1"])
def test_conversion_quantity_must_be_positive_in_db(flour, piece, value):
    with pytest.raises(IntegrityError), transaction.atomic():
        IngredientUnitConversion.objects.create(
            ingredient=flour, unit=piece, base_unit_quantity=Decimal(value)
        )


# --- Product --------------------------------------------------------------------------------
def test_product_normalises_sku_and_currency(db):
    product = Product.objects.create(
        sku=" meal-9 ", name="Bowl", price=Decimal("10.00"), currency="sek"
    )
    assert (product.sku, product.currency) == ("MEAL-9", "SEK")


def test_product_price_cannot_be_negative_in_db(db):
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.bulk_create(
            [Product(sku="NEG-1", name="Neg", price=Decimal("-0.01"), currency="SEK")]
        )


@pytest.mark.parametrize("currency", ["SE", "S3K", "sek", ""])
def test_product_currency_format_is_enforced_in_db(db, currency):
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.bulk_create(
            [Product(sku="CUR-1", name="Cur", price=Decimal("1.00"), currency=currency)]
        )


def test_product_sku_cannot_change_after_creation(product):
    product.sku = "CHANGED"
    with pytest.raises(ImmutableFieldError):
        product.save()


def test_product_price_has_two_decimal_places(product):
    product.price = Decimal("129.999")
    with pytest.raises(ValidationError):
        product.full_clean()

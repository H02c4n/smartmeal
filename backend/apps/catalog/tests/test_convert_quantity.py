from decimal import Decimal

import pytest

from apps.catalog.exceptions import UnitConversionError
from apps.catalog.models import Ingredient, IngredientUnitConversion
from apps.catalog.services import convert_quantity

pytestmark = pytest.mark.django_db

D = Decimal


# --- Same dimension (no ingredient needed) --------------------------------------------------
@pytest.mark.parametrize(
    ("quantity", "src", "dst", "expected"),
    [
        ("1.5", "kg", "g", "1500.0000"),
        ("250", "g", "kg", "0.2500"),
        ("2", "l", "ml", "2000.0000"),
        ("750", "ml", "l", "0.7500"),
        ("3", "pcs", "pcs", "3.0000"),
        ("0", "kg", "g", "0.0000"),
    ],
)
def test_same_dimension_conversion_is_exact(units, quantity, src, dst, expected):
    assert convert_quantity(D(quantity), units[src], units[dst]) == D(expected)


def test_result_is_decimal_quantised_to_four_places(units):
    result = convert_quantity(D("1"), units["kg"], units["g"])
    assert isinstance(result, Decimal)
    assert result.as_tuple().exponent == -4


def test_rounding_is_half_up_and_only_applied_once(units):
    # 0.05 g = 0.00005 kg; half-up -> 0.0001 (banker's rounding would give 0.0000)
    assert convert_quantity(D("0.05"), units["g"], units["kg"]) == D("0.0001")
    # 0.049 g = 0.000049 kg -> rounds down
    assert convert_quantity(D("0.049"), units["g"], units["kg"]) == D("0.0000")


def test_quantize_false_returns_full_precision(units):
    assert convert_quantity(D("0.05"), units["g"], units["kg"], quantize=False) == D("0.00005")


def test_int_and_str_quantities_are_accepted(units):
    assert convert_quantity(2, units["kg"], units["g"]) == D("2000.0000")
    assert convert_quantity("2", units["kg"], units["g"]) == D("2000.0000")


def test_float_quantities_are_rejected(units):
    with pytest.raises(TypeError):
        convert_quantity(1.5, units["kg"], units["g"])


def test_negative_quantity_is_rejected(units):
    with pytest.raises(UnitConversionError):
        convert_quantity(D("-1"), units["kg"], units["g"])


# --- Cross dimension (ingredient specific) --------------------------------------------------
def test_volume_to_mass_uses_ingredient_conversion(milk, units):
    # 1 l milk = 1030 g -> 250 ml = 257.5 g
    assert convert_quantity(D("250"), units["ml"], units["g"], milk) == D("257.5000")
    assert convert_quantity(D("1"), units["l"], units["kg"], milk) == D("1.0300")


def test_mass_to_volume_is_the_inverse(milk, units):
    assert convert_quantity(D("515"), units["g"], units["ml"], milk) == D("500.0000")
    assert convert_quantity(D("2.06"), units["kg"], units["l"], milk) == D("2.0000")


def test_count_to_mass_and_back(egg, units):
    assert convert_quantity(D("3"), units["pcs"], units["g"], egg) == D("165.0000")
    assert convert_quantity(D("220"), units["g"], units["pcs"], egg) == D("4.0000")
    assert convert_quantity(D("0.11"), units["kg"], units["pcs"], egg) == D("2.0000")


def test_ingredient_counted_in_pieces_with_mass_equivalent(piece, units):
    tortilla = Ingredient.objects.create(sku="TORT-01", name="Tortilla", base_unit=piece)
    # 1 g = 0.02 pcs  (i.e. 50 g per piece)
    IngredientUnitConversion.objects.create(
        ingredient=tortilla, unit=units["g"], base_unit_quantity=D("0.02")
    )
    assert convert_quantity(D("100"), units["g"], units["pcs"], tortilla) == D("2.0000")
    assert convert_quantity(D("3"), units["pcs"], units["kg"], tortilla) == D("0.1500")


def test_same_dimension_ignores_ingredient_conversions(milk, units):
    assert convert_quantity(D("1"), units["kg"], units["g"], milk) == D("1000.0000")


def test_no_intermediate_rounding_in_chains(piece, units):
    third = Ingredient.objects.create(sku="THIRD-1", name="Third", base_unit=piece)
    IngredientUnitConversion.objects.create(
        ingredient=third, unit=units["g"], base_unit_quantity=D("0.333333333")
    )
    # 3 g -> 0.999999999 pcs -> quantised once -> 1.0000
    assert convert_quantity(D("3"), units["g"], units["pcs"], third) == D("1.0000")


# --- Errors ---------------------------------------------------------------------------------
def test_cross_dimension_without_ingredient_is_rejected(units):
    with pytest.raises(UnitConversionError):
        convert_quantity(D("1"), units["l"], units["g"])


def test_missing_conversion_is_rejected(flour, units):
    with pytest.raises(UnitConversionError) as excinfo:
        convert_quantity(D("1"), units["l"], units["g"], flour)
    assert "FLOUR-001" in str(excinfo.value.detail)


def test_missing_conversion_for_target_dimension_is_rejected(milk, units):
    # milk has a volume conversion but no count conversion
    with pytest.raises(UnitConversionError):
        convert_quantity(D("1"), units["l"], units["pcs"], milk)


def test_ambiguous_conversions_are_reported_not_guessed(milk, units):
    # Bypass model validation to simulate inconsistent data (e.g. a concurrent insert).
    IngredientUnitConversion.objects.bulk_create(
        [IngredientUnitConversion(ingredient=milk, unit=units["ml"], base_unit_quantity=D("1.03"))]
    )
    with pytest.raises(UnitConversionError) as excinfo:
        convert_quantity(D("1"), units["l"], units["g"], milk)
    assert "Ambiguous" in str(excinfo.value.detail)


def test_unit_conversion_error_renders_as_validation_error():
    from rest_framework.exceptions import ValidationError

    assert issubclass(UnitConversionError, ValidationError)

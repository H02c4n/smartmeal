from decimal import Decimal

import pytest
from django.db import IntegrityError
from rest_framework.exceptions import ValidationError

from apps.catalog import services
from apps.catalog.exceptions import ImmutableFieldError
from apps.catalog.models import Ingredient, Product

pytestmark = pytest.mark.django_db


def test_create_ingredient_normalises_and_persists(gram):
    ingredient = services.create_ingredient(sku=" rice-1 ", name="Rice", base_unit=gram)
    assert Ingredient.objects.get(pk=ingredient.pk).sku == "RICE-1"
    assert ingredient.is_active is True


def test_create_ingredient_duplicate_sku_is_a_field_error(gram, flour):
    with pytest.raises(ValidationError) as excinfo:
        services.create_ingredient(sku="flour-001", name="Dup", base_unit=gram)
    assert "sku" in excinfo.value.detail


def test_create_ingredient_rejects_non_base_unit(kilogram):
    with pytest.raises(ValidationError) as excinfo:
        services.create_ingredient(sku="KG-1", name="Bad", base_unit=kilogram)
    assert "base_unit" in excinfo.value.detail


def test_concurrent_duplicate_insert_is_mapped_to_a_field_error(monkeypatch, gram, flour):
    """Pre-validation passes (race), the INSERT then hits the unique index."""
    real_full_clean = Ingredient.full_clean
    calls = {"n": 0}

    def racing_full_clean(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # first (pre-insert) validation: "no duplicate yet"
        return real_full_clean(self, *args, **kwargs)

    monkeypatch.setattr(Ingredient, "full_clean", racing_full_clean)
    with pytest.raises(ValidationError) as excinfo:
        services.create_ingredient(sku="FLOUR-001", name="Dup", base_unit=gram)
    assert "sku" in excinfo.value.detail


def test_unrelated_integrity_errors_are_not_swallowed(monkeypatch, gram):
    def boom(self, *args, **kwargs):
        raise IntegrityError("something else")

    monkeypatch.setattr(Ingredient, "save", boom)
    with pytest.raises(IntegrityError):
        services.create_ingredient(sku="OK-1", name="Fine", base_unit=gram)


def test_update_ingredient_changes_name_only(flour):
    updated = services.update_ingredient(flour, name="Plain flour")
    updated.refresh_from_db()
    assert updated.name == "Plain flour"
    assert updated.sku == "FLOUR-001"


@pytest.mark.parametrize("target", [True, False])
def test_set_active_is_idempotent(flour, target):
    first = services.set_ingredient_active(flour, target)
    stamp = first.updated_at
    second = services.set_ingredient_active(first, target)
    assert second.is_active is target
    assert second.updated_at == stamp  # no-op: nothing rewritten


def test_create_unit_conversion_validates(flour, kilogram, litre):
    with pytest.raises(ValidationError):
        services.create_unit_conversion(
            ingredient=flour, unit=kilogram, base_unit_quantity=Decimal("1000")
        )
    conversion = services.create_unit_conversion(
        ingredient=flour, unit=litre, base_unit_quantity=Decimal("530")
    )
    assert conversion.pk
    with pytest.raises(ValidationError):  # second volume conversion for the same ingredient
        services.create_unit_conversion(
            ingredient=flour, unit=litre, base_unit_quantity=Decimal("531")
        )


def test_create_product_and_update(db):
    product = services.create_product(
        sku="bowl-1", name="Bowl", price=Decimal("120.50"), currency="sek"
    )
    assert (product.sku, product.currency, product.description) == ("BOWL-1", "SEK", "")
    updated = services.update_product(product, price=Decimal("125.00"), description="Tasty")
    assert Product.objects.get(pk=product.pk).price == Decimal("125.00")
    assert updated.description == "Tasty"


def test_update_product_rejects_sku_and_unknown_fields(product):
    with pytest.raises(ImmutableFieldError):
        services.update_product(product, sku="NEW")
    with pytest.raises(ValueError, match="is_active"):
        services.update_product(product, is_active=False)


def test_update_product_validates_values(product):
    with pytest.raises(ValidationError):
        services.update_product(product, price=Decimal("-1"))
    product.refresh_from_db()
    assert product.price == Decimal("129.00")

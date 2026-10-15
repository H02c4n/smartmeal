"""Catalog write operations and unit conversion (09_CODE_STANDARDS §2).

Views call these functions; they own validation, transaction boundaries and the mapping of
database races to the API error shape. Other modules must change catalog data only through here.
"""

from decimal import ROUND_HALF_UP, Decimal, localcontext

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import as_serializer_error

from .exceptions import ImmutableFieldError, UnitConversionError
from .models import (
    Allergen,
    Ingredient,
    IngredientAllergen,
    IngredientUnitConversion,
    Product,
    Unit,
)

# --- Quantity policy (ADR-011) --------------------------------------------------------------
# No rounding in intermediate steps; the final result is quantised once, ROUND_HALF_UP,
# to the precision of quantity columns (NUMERIC(14,4)).
QUANTITY_PLACES = Decimal("0.0001")
_WORKING_PRECISION = 50

MUTABLE_PRODUCT_FIELDS = frozenset({"name", "description", "price", "currency"})


# --- Helpers --------------------------------------------------------------------------------
def _full_clean(instance) -> None:
    try:
        instance.full_clean()
    except DjangoValidationError as exc:
        raise ValidationError(as_serializer_error(exc)) from exc


def _insert(instance):
    """Validate and insert; a concurrent duplicate surfaces as a normal validation error."""
    _full_clean(instance)
    try:
        with transaction.atomic():
            instance.save(force_insert=True)
    except IntegrityError:
        # Lost a race against another insert: re-validating now reports the duplicate as a
        # field error. If validation passes the failure is something else; do not hide it.
        _full_clean(instance)
        raise
    return instance


def _update(instance, update_fields: list[str]):
    _full_clean(instance)
    instance.save(update_fields=[*update_fields, "updated_at"])
    return instance


def _set_active(instance, is_active: bool):
    """Idempotent: setting the current value is a no-op success."""
    if instance.is_active != is_active:
        instance.is_active = is_active
        instance.save(update_fields=["is_active", "updated_at"])
    return instance


# --- Ingredient -----------------------------------------------------------------------------
def create_ingredient(*, sku: str, name: str, base_unit: Unit) -> Ingredient:
    return _insert(Ingredient(sku=sku, name=name, base_unit=base_unit))


def update_ingredient(ingredient: Ingredient, *, name: str) -> Ingredient:
    """Only the name is editable; SKU and base unit are immutable (ADR-011)."""
    ingredient.name = name
    return _update(ingredient, ["name"])


def set_ingredient_active(ingredient: Ingredient, is_active: bool) -> Ingredient:
    return _set_active(ingredient, is_active)


def create_unit_conversion(
    *, ingredient: Ingredient, unit: Unit, base_unit_quantity: Decimal
) -> IngredientUnitConversion:
    return _insert(
        IngredientUnitConversion(
            ingredient=ingredient, unit=unit, base_unit_quantity=base_unit_quantity
        )
    )


# --- Product --------------------------------------------------------------------------------
def create_product(
    *, sku: str, name: str, price: Decimal, currency: str, description: str = ""
) -> Product:
    return _insert(
        Product(sku=sku, name=name, description=description, price=price, currency=currency)
    )


def update_product(product: Product, **changes) -> Product:
    if "sku" in changes:
        raise ImmutableFieldError("sku cannot be changed after creation.")
    unknown = set(changes) - MUTABLE_PRODUCT_FIELDS
    if unknown:
        raise ValueError(f"Not updatable: {sorted(unknown)}")
    for field, value in changes.items():
        setattr(product, field, value)
    return _update(product, list(changes))


def set_product_active(product: Product, is_active: bool) -> Product:
    return _set_active(product, is_active)


# --- Allergens ------------------------------------------------------------------------------
def create_allergen(*, code: str, name: str) -> Allergen:
    return _insert(Allergen(code=code, name=name))


def update_allergen(allergen: Allergen, *, name: str) -> Allergen:
    """Only the name is editable; the code is immutable."""
    allergen.name = name
    return _update(allergen, ["name"])


def set_allergen_active(allergen: Allergen, is_active: bool) -> Allergen:
    return _set_active(allergen, is_active)


def set_ingredient_allergens(
    ingredient: Ingredient, entries: list[tuple[Allergen, str]]
) -> list[IngredientAllergen]:
    """Replace the ingredient's allergen declaration with ``entries`` (allergen, presence).

    All-or-nothing in one transaction; the row is locked so concurrent replacements serialise.
    Declaring an inactive allergen is rejected unless the ingredient already carries it, so a
    deactivated allergen cannot silently disappear from existing declarations.
    """
    seen: set = set()
    for allergen, presence in entries:
        if allergen.pk in seen:
            raise ValidationError({"allergens": [f"Duplicate allergen {allergen.code}."]})
        seen.add(allergen.pk)
        if presence not in IngredientAllergen.Presence.values:
            raise ValidationError({"allergens": [f"Invalid presence '{presence}'."]})

    with transaction.atomic():
        Ingredient.objects.select_for_update().get(pk=ingredient.pk)
        existing = {
            link.allergen_id: link
            for link in IngredientAllergen.objects.filter(ingredient=ingredient)
        }
        for allergen, _presence in entries:
            if not allergen.is_active and allergen.pk not in existing:
                raise ValidationError(
                    {"allergens": [f"Allergen {allergen.code} is inactive and cannot be added."]}
                )
        wanted = {allergen.pk: presence for allergen, presence in entries}
        IngredientAllergen.objects.filter(ingredient=ingredient).exclude(
            allergen_id__in=wanted
        ).delete()
        for allergen, presence in entries:
            link = existing.get(allergen.pk)
            if link is None:
                IngredientAllergen.objects.create(
                    ingredient=ingredient, allergen=allergen, presence=presence
                )
            elif link.presence != presence:
                link.presence = presence
                link.save(update_fields=["presence", "updated_at"])
    return list(IngredientAllergen.objects.filter(ingredient=ingredient).select_related("allergen"))


# --- Unit conversion ------------------------------------------------------------------------
def _as_decimal(value) -> Decimal:
    if isinstance(value, float):
        raise TypeError("Quantities must be Decimal, int or str, never float.")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _ingredient_conversion(ingredient: Ingredient, dimension: str) -> IngredientUnitConversion:
    conversions = list(
        IngredientUnitConversion.objects.filter(
            ingredient=ingredient, unit__dimension=dimension
        ).select_related("unit")
    )
    if not conversions:
        raise UnitConversionError(
            f"No {dimension} conversion is defined for ingredient {ingredient.sku}."
        )
    if len(conversions) > 1:
        raise UnitConversionError(
            f"Ambiguous: ingredient {ingredient.sku} has several {dimension} conversions."
        )
    return conversions[0]


def _to_ingredient_base(ingredient: Ingredient, quantity: Decimal, unit: Unit) -> Decimal:
    base_unit = ingredient.base_unit
    if unit.dimension == base_unit.dimension:
        return quantity * unit.factor_to_base / base_unit.factor_to_base
    conversion = _ingredient_conversion(ingredient, unit.dimension)
    in_conversion_unit = quantity * unit.factor_to_base / conversion.unit.factor_to_base
    return in_conversion_unit * conversion.base_unit_quantity


def _from_ingredient_base(ingredient: Ingredient, base_quantity: Decimal, unit: Unit) -> Decimal:
    base_unit = ingredient.base_unit
    if unit.dimension == base_unit.dimension:
        return base_quantity * base_unit.factor_to_base / unit.factor_to_base
    conversion = _ingredient_conversion(ingredient, unit.dimension)
    in_conversion_unit = base_quantity / conversion.base_unit_quantity
    return in_conversion_unit * conversion.unit.factor_to_base / unit.factor_to_base


def convert_quantity(
    quantity,
    from_unit: Unit,
    to_unit: Unit,
    ingredient: Ingredient | None = None,
    *,
    quantize: bool = True,
) -> Decimal:
    """Convert ``quantity`` from ``from_unit`` to ``to_unit``.

    * Same dimension: exact, from the unit dictionary (``ingredient`` not needed).
    * Different dimensions: needs ``ingredient`` and its ``IngredientUnitConversion`` rows.
    * Pure Decimal arithmetic (floats are rejected); no intermediate rounding. With
      ``quantize=True`` the result is rounded once, half-up, to ``QUANTITY_PLACES``.

    Raises ``UnitConversionError`` (API: ``VALIDATION_ERROR``) for negative quantities,
    cross-dimension requests without an ingredient, and missing/ambiguous conversions.
    """
    amount = _as_decimal(quantity)
    if amount < 0:
        raise UnitConversionError("Quantity must not be negative.")

    with localcontext() as context:
        context.prec = _WORKING_PRECISION
        if from_unit.dimension == to_unit.dimension:
            result = amount * from_unit.factor_to_base / to_unit.factor_to_base
        else:
            if ingredient is None:
                raise UnitConversionError(
                    f"Converting {from_unit.dimension} to {to_unit.dimension} requires an "
                    "ingredient."
                )
            base_quantity = _to_ingredient_base(ingredient, amount, from_unit)
            result = _from_ingredient_base(ingredient, base_quantity, to_unit)
        if quantize:
            result = result.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP)
    return result

"""Catalog master data: units, ingredients, products (02_DATA_MODEL §3).

Module placement (ADR-011 proposal): ``Ingredient`` lives here, not in ``inventory``; stock
models in ``inventory`` will reference ``catalog.Ingredient`` (dependency: inventory -> catalog).
"""

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDTimestampedModel

from .exceptions import ImmutableFieldError

SKU_PATTERN = r"^[A-Z0-9_-]{2,40}$"
CURRENCY_PATTERN = r"^[A-Z]{3}$"


def normalize_sku(value):
    return value.strip().upper() if isinstance(value, str) else value


def normalize_currency(value):
    return value.strip().upper() if isinstance(value, str) else value


class Unit(UUIDTimestampedModel):
    """Entry of the unit dictionary (reference data, seeded by migration).

    Units belong to a *dimension* (mass, volume, count). ``factor_to_base`` is the number of
    the dimension's base unit (g, ml, pcs) in one of this unit, so conversions inside a
    dimension are exact and need no per-ingredient data. Conversions *across* dimensions
    depend on the ingredient: see ``IngredientUnitConversion``.
    """

    class Dimension(models.TextChoices):
        MASS = "mass", "Mass"
        VOLUME = "volume", "Volume"
        COUNT = "count", "Count"

    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=64)
    dimension = models.CharField(max_length=16, choices=Dimension.choices)
    factor_to_base = models.DecimalField(max_digits=20, decimal_places=9)

    class Meta:
        db_table = "catalog_unit"
        ordering = ["dimension", "factor_to_base", "code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(factor_to_base__gt=0), name="catalog_unit_factor_positive"
            ),
            models.CheckConstraint(
                condition=Q(code__regex=r"^[a-z]{1,16}$"), name="catalog_unit_code_format"
            ),
            # Exactly one canonical base unit (factor 1) per dimension.
            models.UniqueConstraint(
                fields=["dimension"],
                condition=Q(factor_to_base=1),
                name="catalog_unit_one_base_per_dimension",
            ),
        ]

    def __str__(self) -> str:
        return self.code

    @property
    def is_base_unit(self) -> bool:
        return self.factor_to_base == 1


class CatalogItem(UUIDTimestampedModel):
    """Shared shape of Ingredient and Product: SKU, name, active flag.

    * SKU is normalised (stripped, upper-case) and immutable after creation.
    * Rows are never hard-deleted through the product; use ``is_active`` instead.
    * Immutability is enforced in ``save()``; ``QuerySet.update()``/``bulk_update()`` bypass it
      (same caveat as ``updated_at``), so write paths go through ``catalog.services``.
    """

    immutable_fields: tuple[str, ...] = ("sku",)

    sku = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{self.sku} — {self.name}"

    def clean(self) -> None:
        super().clean()
        self.sku = normalize_sku(self.sku)

    def save(self, *args, **kwargs):
        self.sku = normalize_sku(self.sku)
        self._ensure_immutable_fields_unchanged()
        super().save(*args, **kwargs)

    def _ensure_immutable_fields_unchanged(self) -> None:
        if self._state.adding:
            return
        stored = type(self).objects.filter(pk=self.pk).values(*self.immutable_fields).first()
        if stored is None:
            return
        for field, old_value in stored.items():
            if getattr(self, field) != old_value:
                raise ImmutableFieldError(f"{field} cannot be changed after creation.")


class Ingredient(CatalogItem):
    """Raw material. ``base_unit`` is its canonical unit (g, ml or pcs) and never changes."""

    immutable_fields = ("sku", "base_unit_id")

    base_unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="ingredients")

    class Meta:
        db_table = "catalog_ingredient"
        ordering = ["sku"]
        constraints = [
            models.CheckConstraint(
                condition=Q(sku__regex=SKU_PATTERN), name="catalog_ingredient_sku_format"
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if not self.base_unit_id:
            return
        try:
            base_unit = self.base_unit
        except ObjectDoesNotExist:
            return
        if not base_unit.is_base_unit:
            raise ValidationError(
                {"base_unit": "Must be a base unit of its dimension (g, ml or pcs)."}
            )


class IngredientUnitConversion(UUIDTimestampedModel):
    """Ingredient-specific equivalence across dimensions.

    ``1 <unit> of this ingredient = base_unit_quantity <ingredient.base_unit>``, e.g. for milk
    (base unit g): unit ``l``, quantity 1030; for egg (base unit g): unit ``pcs``, quantity 55.
    At most one conversion per (ingredient, unit dimension); same-dimension conversions come
    from the unit dictionary and are rejected here.

    Risk: changing a value alters computed quantities of recipes that use it (see ADR-011).
    """

    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT, related_name="unit_conversions"
    )
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="ingredient_conversions")
    base_unit_quantity = models.DecimalField(max_digits=20, decimal_places=9)

    class Meta:
        db_table = "catalog_ingredient_unit_conversion"
        ordering = ["ingredient__sku", "unit__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["ingredient", "unit"], name="catalog_conversion_unique_ingredient_unit"
            ),
            models.CheckConstraint(
                condition=Q(base_unit_quantity__gt=0),
                name="catalog_conversion_quantity_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ingredient_id}: 1 {self.unit_id} = {self.base_unit_quantity} base"

    def clean(self) -> None:
        super().clean()
        if not (self.ingredient_id and self.unit_id):
            return
        try:
            ingredient, unit = self.ingredient, self.unit
        except ObjectDoesNotExist:
            return
        if unit.dimension == ingredient.base_unit.dimension:
            raise ValidationError(
                {
                    "unit": "Same-dimension conversions come from the unit dictionary; "
                    "define a conversion only across dimensions."
                }
            )
        clash = IngredientUnitConversion.objects.filter(
            ingredient_id=self.ingredient_id, unit__dimension=unit.dimension
        ).exclude(pk=self.pk)
        if clash.exists():
            raise ValidationError(
                {"unit": f"This ingredient already has a {unit.dimension} conversion."}
            )


class Product(CatalogItem):
    """Sellable product. Price/currency are current values; orders snapshot them later.

    Open decisions (00 §8): currency set, tax handling, minor-unit precision per currency.
    ``currency`` therefore has no default and is only format-checked, not matched to ISO 4217.
    """

    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)

    class Meta:
        db_table = "catalog_product"
        ordering = ["sku"]
        constraints = [
            models.CheckConstraint(
                condition=Q(sku__regex=SKU_PATTERN), name="catalog_product_sku_format"
            ),
            models.CheckConstraint(
                condition=Q(price__gte=0), name="catalog_product_price_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(currency__regex=CURRENCY_PATTERN),
                name="catalog_product_currency_format",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self.currency = normalize_currency(self.currency)

    def save(self, *args, **kwargs):
        self.currency = normalize_currency(self.currency)
        super().save(*args, **kwargs)

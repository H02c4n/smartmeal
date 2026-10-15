"""Recipe versions and lines (02_DATA_MODEL §3, ADR-012).

A recipe version belongs to one product and moves ``draft -> approved -> retired``. Only a
draft is editable. Approving freezes each line's quantity in the ingredient's base unit
(``net_base_quantity`` / ``gross_base_quantity``), so later changes to unit conversions can no
longer change what an approved recipe means (00 §4.9, ADR-011 risk). At most one version per
product is approved at any time (partial unique index).

Immutability is enforced in ``save()``/``delete()``; ``QuerySet.update()``/``bulk_*`` bypass it,
so every write path goes through ``recipes.services``.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDTimestampedModel

from .exceptions import RecipeLockedError


class RecipeVersion(UUIDTimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        RETIRED = "retired", "Retired"

    # Fields frozen once the version leaves draft.
    FROZEN_FIELDS = ("product_id", "version_number", "yield_quantity", "yield_unit_id")

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="recipe_versions"
    )
    version_number = models.PositiveIntegerField()
    yield_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    yield_unit = models.ForeignKey(
        "catalog.Unit", on_delete=models.PROTECT, related_name="recipe_versions"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_recipe_versions",
    )
    retired_at = models.DateTimeField(null=True, blank=True)
    retired_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retired_recipe_versions",
    )

    class Meta:
        db_table = "recipes_recipe_version"
        ordering = ["product__sku", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "version_number"], name="recipes_version_unique_number"
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(status="approved"),
                name="recipes_one_approved_version_per_product",
            ),
            models.CheckConstraint(
                condition=Q(yield_quantity__gt=0), name="recipes_version_yield_positive"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["draft", "approved", "retired"]),
                name="recipes_version_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(status="draft")
                | (Q(approved_at__isnull=False) & Q(effective_from__isnull=False)),
                name="recipes_version_approved_has_dates",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_from__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="recipes_version_effective_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} v{self.version_number} ({self.status})"

    @property
    def is_draft(self) -> bool:
        return self.status == self.Status.DRAFT

    def save(self, *args, **kwargs):
        if not self._state.adding:
            stored = (
                type(self).objects.filter(pk=self.pk).values("status", *self.FROZEN_FIELDS).first()
            )
            if stored is not None and stored["status"] != self.Status.DRAFT:
                for field in self.FROZEN_FIELDS:
                    if getattr(self, field) != stored[field]:
                        raise RecipeLockedError(
                            f"{field.removesuffix('_id')} cannot change after approval."
                        )
        super().save(*args, **kwargs)


class RecipeLine(UUIDTimestampedModel):
    """One ingredient of a recipe version.

    ``quantity``/``unit`` are what the cook sees (net, before waste). ``waste_factor`` is the
    share lost in preparation (``0 <= w < 1``); gross = net / (1 - w) (ADR-011). The two
    ``*_base_quantity`` columns are NULL while the version is a draft and are filled, once, on
    approval.
    """

    recipe_version = models.ForeignKey(
        RecipeVersion, on_delete=models.PROTECT, related_name="lines"
    )
    ingredient = models.ForeignKey(
        "catalog.Ingredient", on_delete=models.PROTECT, related_name="recipe_lines"
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit = models.ForeignKey("catalog.Unit", on_delete=models.PROTECT, related_name="recipe_lines")
    waste_factor = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    net_base_quantity = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, editable=False
    )
    gross_base_quantity = models.DecimalField(
        max_digits=14, decimal_places=4, null=True, blank=True, editable=False
    )

    class Meta:
        db_table = "recipes_recipe_line"
        ordering = ["recipe_version", "ingredient__sku"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipe_version", "ingredient"], name="recipes_line_unique_ingredient"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="recipes_line_quantity_positive"
            ),
            models.CheckConstraint(
                condition=Q(waste_factor__gte=0, waste_factor__lt=1),
                name="recipes_line_waste_range",
            ),
            models.CheckConstraint(
                condition=(Q(net_base_quantity__isnull=True) & Q(gross_base_quantity__isnull=True))
                | (
                    Q(net_base_quantity__isnull=False)
                    & Q(net_base_quantity__gt=0)
                    & Q(gross_base_quantity__isnull=False)
                    & Q(gross_base_quantity__gte=models.F("net_base_quantity"))
                ),
                name="recipes_line_base_quantities_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.recipe_version_id}: {self.quantity} {self.unit_id} {self.ingredient_id}"

    def _ensure_version_is_draft(self) -> None:
        status = (
            RecipeVersion.objects.filter(pk=self.recipe_version_id)
            .values_list("status", flat=True)
            .first()
        )
        if status is not None and status != RecipeVersion.Status.DRAFT:
            raise RecipeLockedError("Lines of an approved or retired recipe cannot change.")

    def save(self, *args, **kwargs):
        # The approval service is the only writer of the frozen base quantities and sets them
        # while the version is still a draft, so this guard never blocks it.
        self._ensure_version_is_draft()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._ensure_version_is_draft()
        return super().delete(*args, **kwargs)

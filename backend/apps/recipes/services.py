"""Recipe write operations and requirement calculation (09_CODE_STANDARDS §2, ADR-012).

State machine of a recipe version::

    draft --approve--> approved --retire--> retired
                         ^ approving a newer version retires the previous approved one

Only drafts are editable; approving freezes the base-unit quantities of every line. Quantity
policy follows ADR-011: Decimal only, no intermediate rounding, one ``ROUND_HALF_UP`` at the end.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.serializers import as_serializer_error

from apps.catalog.exceptions import UnitConversionError
from apps.catalog.models import Ingredient, Product, Unit
from apps.catalog.services import QUANTITY_PLACES, convert_quantity
from apps.core.api_errors import InvalidStateTransition

from .models import RecipeLine, RecipeVersion

# Largest value that fits NUMERIC(14,4).
_MAX_QUANTITY = Decimal("10") ** 10
_WORKING_PRECISION = 50


@dataclass(frozen=True)
class LineInput:
    """Validated input for one recipe line."""

    ingredient: Ingredient
    quantity: Decimal
    unit: Unit
    waste_factor: Decimal = Decimal("0")


@dataclass(frozen=True)
class Requirement:
    ingredient: Ingredient
    base_unit: Unit
    net_quantity: Decimal  # needed in the dish
    gross_quantity: Decimal  # to take from stock, i.e. net plus preparation waste


def _full_clean(instance) -> None:
    try:
        instance.full_clean()
    except DjangoValidationError as exc:
        raise ValidationError(as_serializer_error(exc)) from exc


# --- Quantity calculation -------------------------------------------------------------------
def compute_base_quantities(
    *, ingredient: Ingredient, quantity: Decimal, unit: Unit, waste_factor: Decimal
) -> tuple[Decimal, Decimal]:
    """Return ``(net, gross)`` in the ingredient's base unit.

    ``gross = net / (1 - waste_factor)`` is computed from the *unrounded* net; both results are
    rounded once. Raises ``UnitConversionError`` when no conversion exists and
    ``ValidationError`` for out-of-range results.
    """
    if not (Decimal("0") <= waste_factor < Decimal("1")):
        raise ValidationError({"waste_factor": ["Must be at least 0 and less than 1."]})
    with localcontext() as context:
        context.prec = _WORKING_PRECISION
        raw_net = convert_quantity(quantity, unit, ingredient.base_unit, ingredient, quantize=False)
        raw_gross = raw_net / (Decimal(1) - waste_factor)
        net = raw_net.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP)
        gross = raw_gross.quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP)
    if net <= 0:
        raise UnitConversionError(
            f"Quantity of {ingredient.sku} is too small: it rounds to zero in the base unit."
        )
    if gross >= _MAX_QUANTITY:
        raise ValidationError({"quantity": [f"Quantity of {ingredient.sku} is too large."]})
    return net, gross


# --- Drafts ---------------------------------------------------------------------------------
def _replace_lines(version: RecipeVersion, lines: list[LineInput]) -> None:
    """Replace all lines of a draft.

    The caller holds the version lock inside ``transaction.atomic()``: the old lines are deleted
    first (so uniqueness validation does not trip over them) and any validation error rolls the
    whole replacement back.
    """
    RecipeLine.objects.filter(recipe_version=version).delete()
    seen: set = set()
    for entry in lines:
        if entry.ingredient.pk in seen:
            raise ValidationError(
                {"lines": [f"Ingredient {entry.ingredient.sku} appears more than once."]}
            )
        seen.add(entry.ingredient.pk)
        # Early feedback: a line that can never be converted must not be saved at all.
        compute_base_quantities(
            ingredient=entry.ingredient,
            quantity=entry.quantity,
            unit=entry.unit,
            waste_factor=entry.waste_factor,
        )
        line = RecipeLine(
            recipe_version=version,
            ingredient=entry.ingredient,
            quantity=entry.quantity,
            unit=entry.unit,
            waste_factor=entry.waste_factor,
        )
        _full_clean(line)
        line.save(force_insert=True)


def create_recipe_version(
    *,
    product: Product,
    yield_quantity: Decimal,
    yield_unit: Unit,
    lines: list[LineInput] | None = None,
) -> RecipeVersion:
    """Create the next draft version (numbers are 1, 2, 3 ... per product, never reused)."""
    with transaction.atomic():
        # Locking the product serialises number assignment for concurrent creators.
        locked = Product.objects.select_for_update().get(pk=product.pk)
        if not locked.is_active:
            raise ValidationError({"product": ["Inactive products cannot get a new recipe."]})
        last = RecipeVersion.objects.filter(product=locked).aggregate(n=Max("version_number"))["n"]
        version = RecipeVersion(
            product=locked,
            version_number=(last or 0) + 1,
            yield_quantity=yield_quantity,
            yield_unit=yield_unit,
        )
        _full_clean(version)
        version.save(force_insert=True)
        _replace_lines(version, lines or [])
    return version


def update_recipe_version(
    version: RecipeVersion,
    *,
    yield_quantity: Decimal | None = None,
    yield_unit: Unit | None = None,
    lines: list[LineInput] | None = None,
) -> RecipeVersion:
    """Edit a draft. ``lines``, when given, replaces the whole line set."""
    with transaction.atomic():
        locked = RecipeVersion.objects.select_for_update().get(pk=version.pk)
        if not locked.is_draft:
            raise InvalidStateTransition("Only a draft recipe version can be edited.")
        changed = False
        if yield_quantity is not None:
            locked.yield_quantity = yield_quantity
            changed = True
        if yield_unit is not None:
            locked.yield_unit = yield_unit
            changed = True
        if changed:
            _full_clean(locked)
            locked.save()
        if lines is not None:
            _replace_lines(locked, lines)
    return locked


# --- State transitions ----------------------------------------------------------------------
def approve_recipe_version(version: RecipeVersion, *, actor) -> RecipeVersion:
    """draft -> approved. Freezes line quantities and retires the previously approved version.

    Fails (and changes nothing) when the recipe has no lines, uses an inactive ingredient or
    product, or any line cannot be converted to its ingredient's base unit.
    """
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=version.product_id)
        locked = RecipeVersion.objects.select_for_update().get(pk=version.pk)
        if not locked.is_draft:
            raise InvalidStateTransition(
                f"Only a draft can be approved; this version is {locked.status}."
            )
        lines = list(
            locked.lines.select_related("ingredient__base_unit", "unit").order_by("ingredient__sku")
        )
        if not lines:
            raise ValidationError({"lines": ["A recipe needs at least one line to be approved."]})
        if not product.is_active:
            raise ValidationError({"product": ["The product is inactive."]})
        inactive = [line.ingredient.sku for line in lines if not line.ingredient.is_active]
        if inactive:
            raise ValidationError({"lines": [f"Inactive ingredients: {', '.join(inactive)}."]})

        frozen = []
        for line in lines:
            net, gross = compute_base_quantities(
                ingredient=line.ingredient,
                quantity=line.quantity,
                unit=line.unit,
                waste_factor=line.waste_factor,
            )
            frozen.append((line, net, gross))

        now = timezone.now()
        today = timezone.localdate(now)
        previous = (
            RecipeVersion.objects.select_for_update()
            .filter(product=product, status=RecipeVersion.Status.APPROVED)
            .first()
        )
        if previous is not None:  # retire first: one approved version per product at any time
            previous.status = RecipeVersion.Status.RETIRED
            previous.effective_to = today
            previous.retired_at = now
            previous.retired_by = actor
            previous.save(
                update_fields=["status", "effective_to", "retired_at", "retired_by", "updated_at"]
            )

        for line, net, gross in frozen:
            line.net_base_quantity = net
            line.gross_base_quantity = gross
            line.save(update_fields=["net_base_quantity", "gross_base_quantity", "updated_at"])

        locked.status = RecipeVersion.Status.APPROVED
        locked.approved_at = now
        locked.approved_by = actor
        locked.effective_from = today
        locked.save(
            update_fields=["status", "approved_at", "approved_by", "effective_from", "updated_at"]
        )
    return locked


def retire_recipe_version(version: RecipeVersion, *, actor) -> RecipeVersion:
    """approved -> retired (the product then has no approved recipe)."""
    with transaction.atomic():
        locked = RecipeVersion.objects.select_for_update().get(pk=version.pk)
        if locked.status != RecipeVersion.Status.APPROVED:
            raise InvalidStateTransition(
                f"Only an approved version can be retired; this version is {locked.status}."
            )
        now = timezone.now()
        locked.status = RecipeVersion.Status.RETIRED
        locked.effective_to = timezone.localdate(now)
        locked.retired_at = now
        locked.retired_by = actor
        locked.save(
            update_fields=["status", "effective_to", "retired_at", "retired_by", "updated_at"]
        )
    return locked


# --- Requirements ---------------------------------------------------------------------------
def calculate_requirements(version: RecipeVersion, *, quantity, unit: Unit) -> list[Requirement]:
    """Ingredient needs, in base units, to make ``quantity`` ``unit`` of the product.

    ``quantity`` must be in the same dimension as the recipe's yield unit (e.g. portions to
    portions, kg to g). Approved/retired versions use the frozen base quantities, drafts are
    computed live. Each result is rounded once, half-up, to 4 decimals.
    """
    if isinstance(quantity, float):
        raise TypeError("Quantities must be Decimal, int or str, never float.")
    amount = quantity if isinstance(quantity, Decimal) else Decimal(str(quantity))
    if amount <= 0:
        raise ValidationError({"quantity": ["Must be greater than zero."]})
    if unit.dimension != version.yield_unit.dimension:
        raise ValidationError(
            {
                "unit": [
                    f"The recipe yield is measured in {version.yield_unit.dimension}; "
                    f"'{unit.code}' is {unit.dimension}."
                ]
            }
        )

    lines = version.lines.select_related("ingredient__base_unit", "unit").order_by(
        "ingredient__sku"
    )
    results = []
    with localcontext() as context:
        context.prec = _WORKING_PRECISION
        in_yield_unit = convert_quantity(amount, unit, version.yield_unit, quantize=False)
        factor = in_yield_unit / version.yield_quantity
        for line in lines:
            if line.net_base_quantity is not None:
                net, gross = line.net_base_quantity, line.gross_base_quantity
            else:
                net, gross = compute_base_quantities(
                    ingredient=line.ingredient,
                    quantity=line.quantity,
                    unit=line.unit,
                    waste_factor=line.waste_factor,
                )
            results.append(
                Requirement(
                    ingredient=line.ingredient,
                    base_unit=line.ingredient.base_unit,
                    net_quantity=(net * factor).quantize(QUANTITY_PLACES, rounding=ROUND_HALF_UP),
                    gross_quantity=(gross * factor).quantize(
                        QUANTITY_PLACES, rounding=ROUND_HALF_UP
                    ),
                )
            )
    return results

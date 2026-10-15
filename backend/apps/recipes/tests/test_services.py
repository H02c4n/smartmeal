from decimal import Decimal

import pytest
from rest_framework.exceptions import ValidationError

from apps.catalog.exceptions import UnitConversionError
from apps.catalog.models import IngredientUnitConversion
from apps.core.api_errors import InvalidStateTransition
from apps.recipes import services
from apps.recipes.exceptions import RecipeLockedError
from apps.recipes.models import RecipeLine, RecipeVersion
from apps.recipes.services import LineInput

pytestmark = pytest.mark.django_db


# --- Quantity maths -------------------------------------------------------------------------
def test_base_quantities_with_waste(flour, kilogram):
    # 2 kg = 2000 g net; gross = 2000 / 0.9 = 2222.2222...
    net, gross = services.compute_base_quantities(
        ingredient=flour, quantity=Decimal("2"), unit=kilogram, waste_factor=Decimal("0.1")
    )
    assert net == Decimal("2000.0000")
    assert gross == Decimal("2222.2222")


def test_base_quantities_without_waste_are_equal(flour, gram):
    net, gross = services.compute_base_quantities(
        ingredient=flour, quantity=Decimal("150"), unit=gram, waste_factor=Decimal("0")
    )
    assert net == gross == Decimal("150.0000")


def test_gross_is_rounded_once_from_the_unrounded_net(milk, litre):
    # 0.3333 l of milk (1 l = 1030 g) = 343.299 g exactly; waste 0.3333.
    net, gross = services.compute_base_quantities(
        ingredient=milk, quantity=Decimal("0.3333"), unit=litre, waste_factor=Decimal("0.3333")
    )
    assert net == Decimal("343.2990")
    assert gross == (Decimal("343.299") / Decimal("0.6667")).quantize(Decimal("0.0001"))


def test_cross_dimension_line_uses_the_ingredient_conversion(egg, piece):
    net, _ = services.compute_base_quantities(
        ingredient=egg, quantity=Decimal("3"), unit=piece, waste_factor=Decimal("0")
    )
    assert net == Decimal("165.0000")  # 3 x 55 g


def test_missing_conversion_is_a_validation_error(flour, litre):
    with pytest.raises(UnitConversionError):
        services.compute_base_quantities(
            ingredient=flour, quantity=Decimal("1"), unit=litre, waste_factor=Decimal("0")
        )


@pytest.mark.parametrize("waste", [Decimal("1"), Decimal("-0.1")])
def test_waste_out_of_range_is_rejected(flour, gram, waste):
    with pytest.raises(ValidationError):
        services.compute_base_quantities(
            ingredient=flour, quantity=Decimal("1"), unit=gram, waste_factor=waste
        )


def test_quantity_rounding_to_zero_is_rejected(flour, kilogram):
    with pytest.raises(UnitConversionError):
        services.compute_base_quantities(
            ingredient=flour, quantity=Decimal("0.00000001"), unit=kilogram, waste_factor=0
        )


# --- Drafts ---------------------------------------------------------------------------------
def test_version_numbers_increase_per_product(product, other_product, piece):
    kwargs = {"yield_quantity": Decimal("4"), "yield_unit": piece}
    first = services.create_recipe_version(product=product, **kwargs)
    second = services.create_recipe_version(product=product, **kwargs)
    other = services.create_recipe_version(product=other_product, **kwargs)
    assert (first.version_number, second.version_number, other.version_number) == (1, 2, 1)
    assert first.status == "draft"


def test_inactive_product_cannot_get_a_recipe(product, piece):
    product.is_active = False
    product.save()
    with pytest.raises(ValidationError):
        services.create_recipe_version(
            product=product, yield_quantity=Decimal("1"), yield_unit=piece
        )


def test_create_rejects_duplicate_ingredient_and_leaves_nothing_behind(product, flour, gram, piece):
    with pytest.raises(ValidationError):
        services.create_recipe_version(
            product=product,
            yield_quantity=Decimal("1"),
            yield_unit=piece,
            lines=[LineInput(flour, Decimal("1"), gram), LineInput(flour, Decimal("2"), gram)],
        )
    assert RecipeVersion.objects.count() == 0
    assert RecipeLine.objects.count() == 0


def test_create_rejects_unconvertible_line(product, flour, litre, piece):
    with pytest.raises(UnitConversionError):
        services.create_recipe_version(
            product=product,
            yield_quantity=Decimal("1"),
            yield_unit=piece,
            lines=[LineInput(flour, Decimal("1"), litre)],
        )
    assert RecipeVersion.objects.count() == 0


def test_update_draft_replaces_lines_and_yield(draft, salt, gram, kilogram):
    updated = services.update_recipe_version(
        draft,
        yield_quantity=Decimal("20"),
        lines=[LineInput(salt, Decimal("5"), gram)],
    )
    assert updated.yield_quantity == Decimal("20")
    assert [line.ingredient.sku for line in updated.lines.all()] == ["SALT-001"]


def test_update_without_lines_keeps_them(draft):
    services.update_recipe_version(draft, yield_quantity=Decimal("12"))
    assert draft.lines.count() == 2


def test_failed_update_rolls_back_everything(draft, salt, flour, gram, litre):
    with pytest.raises(UnitConversionError):
        services.update_recipe_version(
            draft,
            yield_quantity=Decimal("99"),
            lines=[LineInput(salt, Decimal("5"), gram), LineInput(flour, Decimal("1"), litre)],
        )
    draft.refresh_from_db()
    assert draft.yield_quantity == Decimal("10.0000")
    assert draft.lines.count() == 2


# --- Approval -------------------------------------------------------------------------------
def test_approve_freezes_base_quantities_and_stamps_the_actor(draft, staff_user):
    approved = services.approve_recipe_version(draft, actor=staff_user)
    assert approved.status == "approved"
    assert approved.approved_by == staff_user
    assert approved.approved_at is not None
    assert approved.effective_from is not None and approved.effective_to is None
    by_sku = {line.ingredient.sku: line for line in approved.lines.all()}
    assert by_sku["FLOUR-001"].net_base_quantity == Decimal("2000.0000")
    assert by_sku["FLOUR-001"].gross_base_quantity == Decimal("2222.2222")
    assert by_sku["MILK-001"].net_base_quantity == Decimal("1030.0000")
    assert by_sku["MILK-001"].gross_base_quantity == Decimal("1030.0000")


def test_changing_a_conversion_does_not_change_an_approved_recipe(draft, staff_user, milk, litre):
    approved = services.approve_recipe_version(draft, actor=staff_user)
    IngredientUnitConversion.objects.filter(ingredient=milk, unit=litre).update(
        base_unit_quantity=Decimal("2000")
    )
    line = approved.lines.get(ingredient=milk)
    assert line.net_base_quantity == Decimal("1030.0000")
    requirement = {
        r.ingredient.sku: r
        for r in services.calculate_requirements(approved, quantity=10, unit=approved.yield_unit)
    }["MILK-001"]
    assert requirement.gross_quantity == Decimal("1030.0000")


def test_approve_requires_lines(product, piece, staff_user):
    empty = services.create_recipe_version(
        product=product, yield_quantity=Decimal("1"), yield_unit=piece
    )
    with pytest.raises(ValidationError):
        services.approve_recipe_version(empty, actor=staff_user)
    empty.refresh_from_db()
    assert empty.status == "draft"


def test_approve_rejects_inactive_ingredient_without_side_effects(draft, flour, staff_user):
    flour.is_active = False
    flour.save()
    with pytest.raises(ValidationError):
        services.approve_recipe_version(draft, actor=staff_user)
    draft.refresh_from_db()
    assert draft.status == "draft"
    assert draft.lines.filter(net_base_quantity__isnull=False).count() == 0


def test_approve_fails_when_a_conversion_disappeared(draft, milk, litre, staff_user):
    IngredientUnitConversion.objects.filter(ingredient=milk, unit=litre).delete()
    with pytest.raises(UnitConversionError):
        services.approve_recipe_version(draft, actor=staff_user)
    draft.refresh_from_db()
    assert draft.status == "draft"


def test_approving_twice_is_an_invalid_transition(draft, staff_user):
    services.approve_recipe_version(draft, actor=staff_user)
    with pytest.raises(InvalidStateTransition):
        services.approve_recipe_version(draft, actor=staff_user)


def test_approving_a_new_version_retires_the_previous_one(make_version, staff_user):
    first = services.approve_recipe_version(make_version(), actor=staff_user)
    second = services.approve_recipe_version(make_version(), actor=staff_user)
    first.refresh_from_db()
    assert first.status == "retired"
    assert first.retired_by == staff_user
    assert first.effective_to == second.effective_from
    assert second.status == "approved"
    assert RecipeVersion.objects.filter(status="approved").count() == 1


def test_other_products_are_unaffected_by_approval(
    make_version, product, other_product, staff_user
):
    a = services.approve_recipe_version(make_version(product), actor=staff_user)
    b = services.approve_recipe_version(make_version(other_product), actor=staff_user)
    a.refresh_from_db()
    assert a.status == b.status == "approved"


def test_approved_recipe_cannot_be_edited(draft, staff_user):
    services.approve_recipe_version(draft, actor=staff_user)
    with pytest.raises(InvalidStateTransition):
        services.update_recipe_version(draft, yield_quantity=Decimal("1"))
    with pytest.raises(RecipeLockedError):
        draft.lines.first().delete()


def test_retire_only_approved(draft, staff_user):
    with pytest.raises(InvalidStateTransition):
        services.retire_recipe_version(draft, actor=staff_user)
    services.approve_recipe_version(draft, actor=staff_user)
    retired = services.retire_recipe_version(draft, actor=staff_user)
    assert retired.status == "retired" and retired.effective_to is not None
    with pytest.raises(InvalidStateTransition):
        services.retire_recipe_version(draft, actor=staff_user)
    with pytest.raises(InvalidStateTransition):
        services.approve_recipe_version(draft, actor=staff_user)  # retired is final


# --- Requirements ---------------------------------------------------------------------------
def test_requirements_scale_with_quantity(draft, staff_user, piece):
    approved = services.approve_recipe_version(draft, actor=staff_user)
    # Recipe: yield 10 pcs. For 25 pcs the factor is 2.5.
    result = {
        r.ingredient.sku: r
        for r in services.calculate_requirements(approved, quantity=25, unit=piece)
    }
    assert result["FLOUR-001"].net_quantity == Decimal("5000.0000")
    assert result["FLOUR-001"].gross_quantity == Decimal("5555.5555")  # 2222.2222 x 2.5
    assert result["MILK-001"].net_quantity == Decimal("2575.0000")
    assert result["FLOUR-001"].base_unit.code == "g"


def test_requirements_for_a_draft_are_computed_live(draft, piece):
    result = {
        r.ingredient.sku: r for r in services.calculate_requirements(draft, quantity=10, unit=piece)
    }
    assert result["FLOUR-001"].gross_quantity == Decimal("2222.2222")


def test_requirements_reject_incompatible_unit_and_bad_quantity(draft, kilogram, piece):
    with pytest.raises(ValidationError):
        services.calculate_requirements(draft, quantity=1, unit=kilogram)
    for bad in (0, -1):
        with pytest.raises(ValidationError):
            services.calculate_requirements(draft, quantity=bad, unit=piece)
    with pytest.raises(TypeError):
        services.calculate_requirements(draft, quantity=1.5, unit=piece)


def test_requirements_with_a_mass_yield(product, flour, kilogram, gram, staff_user):
    version = services.create_recipe_version(
        product=product,
        yield_quantity=Decimal("2"),
        yield_unit=kilogram,
        lines=[LineInput(flour, Decimal("1.5"), kilogram)],
    )
    approved = services.approve_recipe_version(version, actor=staff_user)
    # Yield 2 kg needs 1500 g; making 500 g (factor 0.25) needs 375 g.
    [requirement] = services.calculate_requirements(approved, quantity=500, unit=gram)
    assert requirement.net_quantity == Decimal("375.0000")

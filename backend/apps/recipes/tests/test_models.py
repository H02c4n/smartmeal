from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.recipes.exceptions import RecipeLockedError
from apps.recipes.models import RecipeLine, RecipeVersion

pytestmark = pytest.mark.django_db


def _version(product, piece, number=1, **extra):
    return RecipeVersion(
        product=product,
        version_number=number,
        yield_quantity=Decimal("1"),
        yield_unit=piece,
        **extra,
    )


def test_version_numbers_are_unique_per_product(product, other_product, piece):
    _version(product, piece, 1).save()
    _version(other_product, piece, 1).save()  # another product may reuse the number
    with pytest.raises(IntegrityError), transaction.atomic():
        _version(product, piece, 1).save()


def test_yield_must_be_positive(product, piece):
    version = _version(product, piece)
    version.yield_quantity = Decimal("0")
    with pytest.raises(IntegrityError), transaction.atomic():
        version.save()


def test_only_one_approved_version_per_product(product, piece):
    now = timezone.now()
    approved = {"status": "approved", "approved_at": now, "effective_from": date(2026, 1, 1)}
    _version(product, piece, 1, **approved).save()
    with pytest.raises(IntegrityError), transaction.atomic():
        _version(product, piece, 2, **approved).save()
    # a retired or draft one next to it is fine
    _version(product, piece, 3, **{**approved, "status": "retired"}).save()
    _version(product, piece, 4).save()


def test_approved_needs_dates_and_effective_range_is_ordered(product, piece):
    with pytest.raises(IntegrityError), transaction.atomic():
        _version(product, piece, 1, status="approved").save()
    with pytest.raises(IntegrityError), transaction.atomic():
        _version(
            product,
            piece,
            2,
            status="retired",
            approved_at=timezone.now(),
            effective_from=date(2026, 2, 1),
            effective_to=date(2026, 1, 1),
        ).save()


def test_invalid_status_is_rejected_by_the_database(product, piece):
    with pytest.raises(IntegrityError), transaction.atomic():
        _version(product, piece, 1, status="published").save()


@pytest.mark.parametrize("waste", [Decimal("-0.0001"), Decimal("1"), Decimal("1.5")])
def test_waste_factor_range_is_enforced(draft, salt, gram, waste):
    line = RecipeLine(
        recipe_version=draft, ingredient=salt, quantity=Decimal("5"), unit=gram, waste_factor=waste
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        line.save()


def test_line_quantity_must_be_positive_and_ingredient_unique(draft, salt, flour, gram):
    with pytest.raises(IntegrityError), transaction.atomic():
        RecipeLine(recipe_version=draft, ingredient=salt, quantity=Decimal("0"), unit=gram).save()
    with pytest.raises(IntegrityError), transaction.atomic():
        RecipeLine(recipe_version=draft, ingredient=flour, quantity=Decimal("1"), unit=gram).save()


def test_frozen_base_quantities_must_be_consistent(draft, salt, gram):
    for net, gross in [("5", None), (None, "5"), ("0", "0"), ("5", "4")]:
        line = RecipeLine(
            recipe_version=draft,
            ingredient=salt,
            quantity=Decimal("5"),
            unit=gram,
            net_base_quantity=None if net is None else Decimal(net),
            gross_base_quantity=None if gross is None else Decimal(gross),
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            line.save()


def test_non_draft_version_fields_and_lines_are_locked(draft, salt, gram):
    RecipeVersion.objects.filter(pk=draft.pk).update(
        status="approved", approved_at=timezone.now(), effective_from=date(2026, 1, 1)
    )
    draft.refresh_from_db()
    draft.yield_quantity = Decimal("99")
    with pytest.raises(RecipeLockedError):
        draft.save()

    line = draft.lines.first()
    line.quantity = Decimal("123")
    with pytest.raises(RecipeLockedError):
        line.save()
    with pytest.raises(RecipeLockedError):
        line.delete()
    with pytest.raises(RecipeLockedError):
        RecipeLine(recipe_version=draft, ingredient=salt, quantity=Decimal("1"), unit=gram).save()


def test_non_frozen_fields_of_an_approved_version_may_still_change(draft):
    RecipeVersion.objects.filter(pk=draft.pk).update(
        status="approved", approved_at=timezone.now(), effective_from=date(2026, 1, 1)
    )
    draft.refresh_from_db()
    draft.status = "retired"
    draft.effective_to = date(2026, 6, 1)
    draft.save()  # status/effective_to are not frozen
    assert RecipeVersion.objects.get(pk=draft.pk).status == "retired"

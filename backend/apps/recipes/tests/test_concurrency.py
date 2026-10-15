"""Real concurrent transactions: needs committed data, so ``transaction=True``.

``serialized_rollback`` restores the unit dictionary seeded by migration after the flush.
"""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.db import connection

from apps.accounts.models import User
from apps.catalog.models import Ingredient, Product, Unit
from apps.recipes import services
from apps.recipes.models import RecipeVersion
from apps.recipes.services import LineInput

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


@pytest.fixture
def world(db):
    gram = Unit.objects.get(code="g")
    piece = Unit.objects.get(code="pcs")
    flour = Ingredient.objects.create(sku="FLOUR-9", name="Flour", base_unit=gram)
    product = Product.objects.create(sku="MEAL-9", name="Bowl", price=Decimal("10"), currency="SEK")
    actor = User.objects.create_user("approver@example.com", "s3cret-Pass-123", is_staff=True)
    return {"gram": gram, "piece": piece, "flour": flour, "product": product, "actor": actor}


def _run_parallel(function, count):
    def wrapped(index):
        try:
            return function(index)
        finally:
            connection.close()  # each thread owns its connection

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(wrapped, range(count)))


def test_concurrent_creates_get_distinct_version_numbers(world):
    def create(_):
        return services.create_recipe_version(
            product=world["product"], yield_quantity=Decimal("1"), yield_unit=world["piece"]
        ).version_number

    numbers = _run_parallel(create, 6)
    assert sorted(numbers) == [1, 2, 3, 4, 5, 6]


def test_concurrent_approvals_leave_exactly_one_approved_version(world):
    versions = [
        services.create_recipe_version(
            product=world["product"],
            yield_quantity=Decimal("1"),
            yield_unit=world["piece"],
            lines=[LineInput(world["flour"], Decimal("100"), world["gram"])],
        )
        for _ in range(4)
    ]

    def approve(index):
        return services.approve_recipe_version(versions[index], actor=world["actor"]).pk

    _run_parallel(approve, 4)
    statuses = list(
        RecipeVersion.objects.filter(product=world["product"]).values_list("status", flat=True)
    )
    assert statuses.count("approved") == 1
    assert statuses.count("retired") == 3

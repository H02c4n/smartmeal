"""Read queries for recipes."""

from django.db.models import QuerySet

from apps.catalog.models import IngredientAllergen

from .models import RecipeVersion


def recipe_versions(
    *, product_sku: str | None = None, status: str | None = None
) -> QuerySet[RecipeVersion]:
    queryset = RecipeVersion.objects.select_related("product", "yield_unit", "approved_by")
    if product_sku:
        queryset = queryset.filter(product__sku=product_sku.strip().upper())
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def detailed_recipe_version_queryset() -> QuerySet[RecipeVersion]:
    return RecipeVersion.objects.select_related("product", "yield_unit").prefetch_related(
        "lines__ingredient__base_unit", "lines__unit"
    )


_PRESENCE_RANK = {
    IngredientAllergen.Presence.CONTAINS: 2,
    IngredientAllergen.Presence.MAY_CONTAIN: 1,
}


def allergens_for_version(version: RecipeVersion) -> list[dict]:
    """Allergens declared on the version's ingredients; ``contains`` outranks ``may_contain``.

    Deactivated allergens stay listed: deactivation hides an entry from new declarations, it
    must never hide a declared allergen from an existing recipe. The result reflects only what
    has been declared on ingredients (no declaration = no entry), so it is an aid for staff, not
    a legal label; allergen labelling duties must be verified (05 §4).
    """
    links = IngredientAllergen.objects.filter(
        ingredient__recipe_lines__recipe_version=version
    ).select_related("allergen")
    strongest: dict = {}
    for link in links:
        current = strongest.get(link.allergen_id)
        if current is None or _PRESENCE_RANK[link.presence] > _PRESENCE_RANK[current.presence]:
            strongest[link.allergen_id] = link
    return [
        {"code": link.allergen.code, "name": link.allergen.name, "presence": link.presence}
        for link in sorted(strongest.values(), key=lambda item: item.allergen.code)
    ]

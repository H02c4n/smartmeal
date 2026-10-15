"""Read queries for catalog data."""

from django.db.models import Q, QuerySet

from .models import Allergen, Ingredient, IngredientAllergen, Product, Unit


def _search(queryset: QuerySet, q: str | None) -> QuerySet:
    q = (q or "").strip()
    if q:
        queryset = queryset.filter(Q(sku__icontains=q) | Q(name__icontains=q))
    return queryset


def active_products(*, q: str | None = None) -> QuerySet[Product]:
    return _search(Product.objects.filter(is_active=True), q)


def admin_products(*, q: str | None = None, is_active: bool | None = None) -> QuerySet[Product]:
    queryset = Product.objects.all()
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return _search(queryset, q)


def admin_ingredients(
    *, q: str | None = None, is_active: bool | None = None
) -> QuerySet[Ingredient]:
    queryset = Ingredient.objects.select_related("base_unit")
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return _search(queryset, q)


def units() -> QuerySet[Unit]:
    return Unit.objects.all()


def allergens(*, is_active: bool | None = None) -> QuerySet[Allergen]:
    queryset = Allergen.objects.all()
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def ingredient_allergen_links(ingredient: Ingredient) -> QuerySet[IngredientAllergen]:
    return IngredientAllergen.objects.filter(ingredient=ingredient).select_related("allergen")

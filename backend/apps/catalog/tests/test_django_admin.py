import pytest
from django.urls import reverse

from apps.catalog.admin import IngredientAdmin, ProductAdmin
from apps.catalog.models import Ingredient, Product

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("model", ["unit", "ingredient", "product"])
def test_superuser_can_open_changelists(client, superuser, model):
    client.force_login(superuser)
    assert client.get(reverse(f"admin:catalog_{model}_changelist")).status_code == 200


def test_unit_dictionary_is_read_only_in_admin(client, superuser, gram):
    client.force_login(superuser)
    assert client.get(reverse("admin:catalog_unit_add")).status_code == 403
    assert client.get(reverse("admin:catalog_unit_delete", args=[gram.pk])).status_code == 403


def test_admin_creates_ingredient_with_normalised_sku(client, superuser, gram):
    client.force_login(superuser)
    response = client.post(
        reverse("admin:catalog_ingredient_add"),
        {
            "sku": "oat-01",
            "name": "Oats",
            "base_unit": str(gram.pk),
            "is_active": "on",
            "unit_conversions-TOTAL_FORMS": "0",
            "unit_conversions-INITIAL_FORMS": "0",
            "unit_conversions-MIN_NUM_FORMS": "0",
            "unit_conversions-MAX_NUM_FORMS": "1000",
            "allergen_links-TOTAL_FORMS": "0",
            "allergen_links-INITIAL_FORMS": "0",
            "allergen_links-MIN_NUM_FORMS": "0",
            "allergen_links-MAX_NUM_FORMS": "1000",
        },
    )
    assert response.status_code == 302, getattr(response, "context", None)
    assert Ingredient.objects.get(sku="OAT-01").base_unit == gram


def test_sku_and_base_unit_are_read_only_after_creation(rf, superuser, flour, product):
    request = rf.get("/")
    request.user = superuser
    from django.contrib import admin

    ingredient_admin = IngredientAdmin(Ingredient, admin.site)
    assert {"sku", "base_unit"} <= set(ingredient_admin.get_readonly_fields(request, flour))
    assert "sku" not in ingredient_admin.get_readonly_fields(request, None)
    product_admin = ProductAdmin(Product, admin.site)
    assert "sku" in product_admin.get_readonly_fields(request, product)


def test_catalog_items_cannot_be_deleted_in_admin(client, superuser, flour, product):
    client.force_login(superuser)
    assert (
        client.get(reverse("admin:catalog_ingredient_delete", args=[flour.pk])).status_code == 403
    )
    assert client.get(reverse("admin:catalog_product_delete", args=[product.pk])).status_code == 403


def test_conversion_rules_apply_through_admin_change_page(client, superuser, milk):
    client.force_login(superuser)
    assert client.get(reverse("admin:catalog_ingredient_change", args=[milk.pk])).status_code == 200

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_recipe_admin_is_read_only(client, superuser, draft):
    client.force_login(superuser)
    assert client.get(reverse("admin:recipes_recipeversion_changelist")).status_code == 200
    assert (
        client.get(reverse("admin:recipes_recipeversion_change", args=[draft.pk])).status_code
        == 200
    )
    assert client.get(reverse("admin:recipes_recipeversion_add")).status_code == 403
    assert (
        client.post(reverse("admin:recipes_recipeversion_delete", args=[draft.pk])).status_code
        == 403
    )


def test_schema_documents_the_recipe_contract(api_client, staff_user):
    api_client.force_authenticate(staff_user)
    paths = api_client.get("/api/v1/schema/", {"format": "json"}).json()["paths"]
    expected = {
        "/api/v1/admin/recipe-versions/": {"get", "post"},
        "/api/v1/admin/recipe-versions/{id}/": {"get", "patch"},
        "/api/v1/admin/recipe-versions/{id}/approve/": {"post"},
        "/api/v1/admin/recipe-versions/{id}/retire/": {"post"},
        "/api/v1/admin/recipe-versions/{id}/requirements/": {"get"},
        "/api/v1/admin/allergens/": {"get", "post"},
        "/api/v1/admin/allergens/{id}/": {"get", "patch"},
        "/api/v1/admin/allergens/{id}/activate/": {"post"},
        "/api/v1/admin/allergens/{id}/deactivate/": {"post"},
        "/api/v1/admin/ingredients/{id}/allergens/": {"get", "put"},
    }
    for path, methods in expected.items():
        assert path in paths, path
        assert set(paths[path]) == methods, path

import pytest

pytestmark = pytest.mark.django_db


def test_schema_documents_the_catalog_contract(api_client, staff_user):
    api_client.force_authenticate(staff_user)
    response = api_client.get("/api/v1/schema/", {"format": "json"})
    assert response.status_code == 200
    paths = response.json()["paths"]
    expected = {
        "/api/v1/products/": {"get"},
        "/api/v1/products/{id}/": {"get"},
        "/api/v1/admin/products/": {"get", "post"},
        "/api/v1/admin/products/{id}/": {"get", "patch"},
        "/api/v1/admin/products/{id}/activate/": {"post"},
        "/api/v1/admin/products/{id}/deactivate/": {"post"},
        "/api/v1/admin/ingredients/": {"get", "post"},
        "/api/v1/admin/ingredients/{id}/": {"get", "patch"},
        "/api/v1/admin/ingredients/{id}/activate/": {"post"},
        "/api/v1/admin/ingredients/{id}/deactivate/": {"post"},
        "/api/v1/admin/units/": {"get"},
        "/api/v1/admin/units/{id}/": {"get"},
    }
    for path, methods in expected.items():
        assert path in paths, path
        assert set(paths[path]) == methods, path

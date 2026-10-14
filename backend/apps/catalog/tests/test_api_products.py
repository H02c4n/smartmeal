import uuid

import pytest

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/products/"


def detail_url(pk) -> str:
    return f"/api/v1/products/{pk}/"


def test_anonymous_gets_authentication_required_envelope(api_client):
    response = api_client.get(LIST_URL, HTTP_X_REQUEST_ID="req-products-0001")
    assert response.status_code in (401, 403)
    error = response.json()["error"]
    assert error["code"] == "AUTHENTICATION_REQUIRED"
    assert error["request_id"] == "req-products-0001"


def test_authenticated_customer_lists_only_active_products(
    api_client, user, product, inactive_product
):
    api_client.force_authenticate(user)
    response = api_client.get(LIST_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert [p["sku"] for p in body["results"]] == ["MEAL-001"]


def test_product_representation_is_customer_safe_and_money_is_a_string(api_client, user, product):
    api_client.force_authenticate(user)
    item = api_client.get(detail_url(product.pk)).json()
    assert item == {
        "id": str(product.pk),
        "sku": "MEAL-001",
        "name": "Chicken bowl",
        "description": "",
        "price": "129.00",
        "currency": "SEK",
    }


def test_inactive_product_detail_is_hidden(api_client, user, inactive_product):
    api_client.force_authenticate(user)
    response = api_client.get(detail_url(inactive_product.pk))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.parametrize("pk", [str(uuid.uuid4()), "not-a-uuid"])
def test_unknown_or_malformed_id_is_404(api_client, user, pk):
    api_client.force_authenticate(user)
    assert api_client.get(detail_url(pk)).status_code == 404


def test_search_filter(api_client, user, product):
    api_client.force_authenticate(user)
    assert api_client.get(LIST_URL, {"q": "chicken"}).json()["count"] == 1
    assert api_client.get(LIST_URL, {"q": "meal-0"}).json()["count"] == 1
    assert api_client.get(LIST_URL, {"q": "nothing"}).json()["count"] == 0


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_public_endpoints_are_read_only(api_client, user, product, method):
    api_client.force_authenticate(user)
    response = getattr(api_client, method)(detail_url(product.pk), {}, format="json")
    assert response.status_code == 405
    assert getattr(api_client, method)(LIST_URL, {}, format="json").status_code == 405


def test_list_is_paginated(api_client, user, product):
    api_client.force_authenticate(user)
    body = api_client.get(LIST_URL).json()
    assert {"count", "next", "previous", "results"} <= body.keys()

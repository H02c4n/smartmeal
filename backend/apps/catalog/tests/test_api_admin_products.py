import pytest

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/admin/products/"
VALID = {"sku": "bowl-2", "name": "Veggie bowl", "price": "119.00", "currency": "sek"}


def detail_url(pk, suffix="") -> str:
    return f"/api/v1/admin/products/{pk}/{suffix}"


@pytest.fixture
def staff_client(api_client, staff_user):
    api_client.force_authenticate(staff_user)
    return api_client


# --- Authorization --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("method", "suffix"),
    [("get", ""), ("post", ""), ("patch", "{pk}/"), ("post", "{pk}/activate/"),
     ("post", "{pk}/deactivate/")],
)  # fmt: skip
def test_anonymous_is_rejected_everywhere(api_client, product, method, suffix):
    url = LIST_URL + suffix.format(pk=product.pk)
    response = getattr(api_client, method)(url, {}, format="json")
    assert response.status_code in (401, 403)
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("get", ""), ("post", ""), ("get", "{pk}/"), ("patch", "{pk}/"),
     ("post", "{pk}/activate/"), ("post", "{pk}/deactivate/")],
)  # fmt: skip
def test_non_staff_customer_is_denied_everywhere(api_client, user, product, method, suffix):
    api_client.force_authenticate(user)
    url = LIST_URL + suffix.format(pk=product.pk)
    response = getattr(api_client, method)(url, VALID, format="json")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_denied_create_does_not_write(api_client, user):
    api_client.force_authenticate(user)
    api_client.post(LIST_URL, VALID, format="json")
    from apps.catalog.models import Product

    assert not Product.objects.exists()


# --- Create ---------------------------------------------------------------------------------
def test_create_product(staff_client):
    response = staff_client.post(LIST_URL, VALID, format="json")
    assert response.status_code == 201
    body = response.json()
    assert (body["sku"], body["currency"], body["price"]) == ("BOWL-2", "SEK", "119.00")
    assert body["is_active"] is True
    assert {"id", "created_at", "updated_at", "description"} <= body.keys()


def test_create_duplicate_sku_is_a_validation_error_case_insensitively(staff_client, product):
    response = staff_client.post(LIST_URL, {**VALID, "sku": "meal-001"}, format="json")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "sku" in error["details"]
    assert error["request_id"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("price", "-1.00"),
        ("price", "12.345"),
        ("price", "abc"),
        ("currency", "SE"),
        ("currency", "S3K"),
        ("sku", "bad sku"),
        ("sku", "x"),
        ("name", ""),
    ],
)
def test_create_validates_fields(staff_client, field, value):
    response = staff_client.post(LIST_URL, {**VALID, field: value}, format="json")
    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


@pytest.mark.parametrize("missing", ["sku", "name", "price", "currency"])
def test_create_requires_fields(staff_client, missing):
    payload = {k: v for k, v in VALID.items() if k != missing}
    response = staff_client.post(LIST_URL, payload, format="json")
    assert response.status_code == 400
    assert missing in response.json()["error"]["details"]


def test_create_cannot_set_is_active_directly(staff_client):
    response = staff_client.post(LIST_URL, {**VALID, "is_active": False}, format="json")
    assert response.status_code == 400
    assert "is_active" in response.json()["error"]["details"]


# --- Read -----------------------------------------------------------------------------------
def test_admin_sees_inactive_products_and_can_filter(staff_client, product, inactive_product):
    assert staff_client.get(LIST_URL).json()["count"] == 2
    only_inactive = staff_client.get(LIST_URL, {"is_active": "false"}).json()
    assert [p["sku"] for p in only_inactive["results"]] == ["MEAL-OLD"]
    assert staff_client.get(LIST_URL, {"is_active": "true"}).json()["count"] == 1
    assert staff_client.get(detail_url(inactive_product.pk)).status_code == 200


def test_invalid_is_active_filter_is_a_validation_error(staff_client):
    response = staff_client.get(LIST_URL, {"is_active": "maybe"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- Update ---------------------------------------------------------------------------------
def test_patch_updates_allowed_fields(staff_client, product):
    response = staff_client.patch(
        detail_url(product.pk), {"price": "135.50", "name": "Chicken bowl XL"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["price"] == "135.50"
    product.refresh_from_db()
    assert product.name == "Chicken bowl XL"


def test_patch_rejects_sku_change_but_accepts_unchanged_echo(staff_client, product):
    bad = staff_client.patch(detail_url(product.pk), {"sku": "OTHER"}, format="json")
    assert bad.status_code == 400
    assert "sku" in bad.json()["error"]["details"]
    ok = staff_client.patch(
        detail_url(product.pk), {"sku": "meal-001", "name": "Renamed"}, format="json"
    )
    assert ok.status_code == 200


def test_patch_cannot_toggle_is_active(staff_client, product):
    response = staff_client.patch(detail_url(product.pk), {"is_active": False}, format="json")
    assert response.status_code == 400
    product.refresh_from_db()
    assert product.is_active is True


def test_patch_validation_error_leaves_data_unchanged(staff_client, product):
    response = staff_client.patch(detail_url(product.pk), {"price": "-5"}, format="json")
    assert response.status_code == 400
    product.refresh_from_db()
    assert str(product.price) == "129.00"


def test_put_and_delete_are_not_allowed(staff_client, product):
    assert staff_client.put(detail_url(product.pk), VALID, format="json").status_code == 405
    assert staff_client.delete(detail_url(product.pk)).status_code == 405


# --- Activation actions ---------------------------------------------------------------------
def test_deactivate_hides_product_from_customers_and_activate_restores(
    staff_client, api_client, staff_user, user, product
):
    response = staff_client.post(detail_url(product.pk, "deactivate/"))
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    api_client.force_authenticate(user)
    assert api_client.get(f"/api/v1/products/{product.pk}/").status_code == 404

    api_client.force_authenticate(staff_user)
    assert api_client.post(detail_url(product.pk, "activate/")).json()["is_active"] is True
    api_client.force_authenticate(user)
    assert api_client.get(f"/api/v1/products/{product.pk}/").status_code == 200


def test_activation_actions_are_idempotent(staff_client, product):
    for _ in range(2):
        response = staff_client.post(detail_url(product.pk, "deactivate/"))
        assert response.status_code == 200
        assert response.json()["is_active"] is False

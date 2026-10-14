import pytest

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/admin/ingredients/"
UNITS_URL = "/api/v1/admin/units/"


def detail_url(pk, suffix="") -> str:
    return f"{LIST_URL}{pk}/{suffix}"


@pytest.fixture
def staff_client(api_client, staff_user):
    api_client.force_authenticate(staff_user)
    return api_client


@pytest.mark.parametrize(
    ("method", "url"),
    [("get", LIST_URL), ("post", LIST_URL), ("get", UNITS_URL)],
)
def test_anonymous_and_customers_are_rejected(api_client, user, method, url):
    anonymous = getattr(api_client, method)(url, {}, format="json")
    assert anonymous.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    api_client.force_authenticate(user)
    customer = getattr(api_client, method)(url, {}, format="json")
    assert customer.status_code == 403
    assert customer.json()["error"]["code"] == "PERMISSION_DENIED"


def test_customer_cannot_change_or_activate_ingredients(api_client, user, flour):
    api_client.force_authenticate(user)
    assert api_client.patch(detail_url(flour.pk), {"name": "x"}, format="json").status_code == 403
    assert api_client.post(detail_url(flour.pk, "deactivate/")).status_code == 403
    flour.refresh_from_db()
    assert flour.is_active is True
    assert flour.name == "Wheat flour"


# --- Units ----------------------------------------------------------------------------------
def test_units_are_listed_read_only(staff_client, units):
    body = staff_client.get(UNITS_URL).json()
    assert {u["code"] for u in body["results"]} == {"g", "kg", "ml", "l", "pcs"}
    kg = next(u for u in body["results"] if u["code"] == "kg")
    assert kg["dimension"] == "mass"
    assert kg["factor_to_base"] == "1000.000000000"
    for method in ("post", "put", "patch", "delete"):
        response = getattr(staff_client, method)(UNITS_URL, {}, format="json")
        assert response.status_code == 405


# --- Create ---------------------------------------------------------------------------------
def test_create_ingredient(staff_client, units):
    response = staff_client.post(
        LIST_URL, {"sku": "tom-01", "name": "Tomato", "base_unit": "g"}, format="json"
    )
    assert response.status_code == 201
    body = response.json()
    assert (body["sku"], body["base_unit"], body["is_active"]) == ("TOM-01", "g", True)


def test_create_rejects_non_base_unit_and_unknown_unit(staff_client, units):
    kg = staff_client.post(
        LIST_URL, {"sku": "TOM-02", "name": "T", "base_unit": "kg"}, format="json"
    )
    assert kg.status_code == 400
    assert "base_unit" in kg.json()["error"]["details"]
    unknown = staff_client.post(
        LIST_URL, {"sku": "TOM-03", "name": "T", "base_unit": "stone"}, format="json"
    )
    assert unknown.status_code == 400
    assert "base_unit" in unknown.json()["error"]["details"]


def test_create_duplicate_sku(staff_client, flour):
    response = staff_client.post(
        LIST_URL, {"sku": "flour-001", "name": "Dup", "base_unit": "g"}, format="json"
    )
    assert response.status_code == 400
    assert "sku" in response.json()["error"]["details"]


# --- Read / update --------------------------------------------------------------------------
def test_list_filters(staff_client, flour, milk):
    staff_client.post(detail_url(milk.pk, "deactivate/"))
    assert staff_client.get(LIST_URL).json()["count"] == 2
    active = staff_client.get(LIST_URL, {"is_active": "true"}).json()
    assert [i["sku"] for i in active["results"]] == ["FLOUR-001"]
    assert staff_client.get(LIST_URL, {"q": "milk"}).json()["count"] == 1


def test_patch_changes_name_only(staff_client, flour):
    response = staff_client.patch(detail_url(flour.pk), {"name": "Plain flour"}, format="json")
    assert response.status_code == 200
    assert response.json()["name"] == "Plain flour"


@pytest.mark.parametrize(
    ("field", "value"), [("sku", "NEW-SKU"), ("base_unit", "ml"), ("is_active", False)]
)
def test_patch_rejects_immutable_and_action_only_fields(staff_client, flour, field, value):
    response = staff_client.patch(detail_url(flour.pk), {field: value}, format="json")
    assert response.status_code == 400
    assert field in response.json()["error"]["details"]
    flour.refresh_from_db()
    assert (flour.sku, flour.base_unit.code, flour.is_active) == ("FLOUR-001", "g", True)


def test_patch_accepts_unchanged_immutable_echo(staff_client, flour):
    response = staff_client.patch(
        detail_url(flour.pk), {"sku": "flour-001", "base_unit": "g", "name": "Renamed"},
        format="json",
    )  # fmt: skip
    assert response.status_code == 200


def test_activation_is_idempotent(staff_client, flour):
    for _ in range(2):
        response = staff_client.post(detail_url(flour.pk, "deactivate/"))
        assert response.status_code == 200
        assert response.json()["is_active"] is False
    assert staff_client.post(detail_url(flour.pk, "activate/")).json()["is_active"] is True


def test_put_and_delete_are_not_allowed(staff_client, flour):
    assert staff_client.put(detail_url(flour.pk), {}, format="json").status_code == 405
    assert staff_client.delete(detail_url(flour.pk)).status_code == 405

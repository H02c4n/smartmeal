import pytest

from apps.catalog.models import Allergen, IngredientAllergen
from apps.recipes import services

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/admin/recipe-versions/"


@pytest.fixture(autouse=True)
def _catalog(units, flour, milk, product):
    """Requests refer to these catalog rows by SKU/code, so they must exist."""


def detail(pk, suffix="") -> str:
    return f"{LIST_URL}{pk}/{suffix}"


@pytest.fixture
def staff_client(api_client, staff_user):
    api_client.force_authenticate(staff_user)
    return api_client


def payload(**overrides):
    body = {
        "product": "meal-001",
        "yield_quantity": "10",
        "yield_unit": "pcs",
        "lines": [
            {"ingredient": "flour-001", "quantity": "2", "unit": "kg", "waste_factor": "0.1"},
            {"ingredient": "MILK-001", "quantity": "1", "unit": "l"},
        ],
    }
    body.update(overrides)
    return body


# --- Access ---------------------------------------------------------------------------------
@pytest.mark.parametrize("method", ["get", "post"])
def test_anonymous_and_customers_are_rejected(api_client, user, method):
    anonymous = getattr(api_client, method)(LIST_URL, {}, format="json")
    assert anonymous.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    api_client.force_authenticate(user)
    customer = getattr(api_client, method)(LIST_URL, {}, format="json")
    assert customer.status_code == 403


def test_customers_cannot_approve_or_edit(api_client, user, draft):
    api_client.force_authenticate(user)
    assert api_client.post(detail(draft.pk, "approve/")).status_code == 403
    assert (
        api_client.patch(detail(draft.pk), {"yield_quantity": "1"}, format="json").status_code
        == 403
    )
    draft.refresh_from_db()
    assert draft.status == "draft"


# --- Create / read --------------------------------------------------------------------------
def test_create_draft_with_lines(staff_client):
    response = staff_client.post(LIST_URL, payload(), format="json")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert (body["product"], body["version_number"], body["status"]) == ("MEAL-001", 1, "draft")
    assert body["yield_unit"] == "pcs"
    lines = {line["ingredient"]: line for line in body["lines"]}
    assert set(lines) == {"FLOUR-001", "MILK-001"}
    assert lines["FLOUR-001"]["waste_factor"] == "0.1000"
    assert lines["FLOUR-001"]["net_base_quantity"] is None  # not frozen before approval
    assert lines["FLOUR-001"]["base_unit"] == "g"


def test_create_without_lines_is_allowed_for_a_draft(staff_client):
    response = staff_client.post(LIST_URL, payload(lines=[]), format="json")
    assert response.status_code == 201
    assert response.json()["lines"] == []


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"product": "NOPE-1"}, "product"),
        ({"yield_quantity": "0"}, "yield_quantity"),
        ({"yield_quantity": "-3"}, "yield_quantity"),
        ({"yield_unit": "bushel"}, "yield_unit"),
        (
            {
                "lines": [
                    {"ingredient": "FLOUR-001", "quantity": "1", "unit": "g", "waste_factor": "1"}
                ]
            },
            "lines",
        ),
        ({"lines": [{"ingredient": "UNKNOWN", "quantity": "1", "unit": "g"}]}, "lines"),
        ({"lines": [{"ingredient": "FLOUR-001", "quantity": "0", "unit": "g"}]}, "lines"),
    ],
)
def test_create_validates_input(staff_client, overrides, field):
    response = staff_client.post(LIST_URL, payload(**overrides), format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert field in response.json()["error"]["details"]


def test_create_rejects_duplicate_ingredient_and_unconvertible_unit(staff_client):
    dup = [
        {"ingredient": "FLOUR-001", "quantity": "1", "unit": "g"},
        {"ingredient": "flour-001", "quantity": "2", "unit": "g"},
    ]
    assert staff_client.post(LIST_URL, payload(lines=dup), format="json").status_code == 400
    unconvertible = [{"ingredient": "FLOUR-001", "quantity": "1", "unit": "l"}]
    response = staff_client.post(LIST_URL, payload(lines=unconvertible), format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_filters_and_hides_lines(
    staff_client, make_version, product, other_product, staff_user
):
    v1 = make_version()
    services.approve_recipe_version(v1, actor=staff_user)
    make_version(other_product)
    everything = staff_client.get(LIST_URL).json()
    assert everything["count"] == 2
    assert "lines" not in everything["results"][0]
    only_mine = staff_client.get(LIST_URL, {"product": "meal-001"}).json()
    assert [r["product"] for r in only_mine["results"]] == ["MEAL-001"]
    approved = staff_client.get(LIST_URL, {"status": "approved"}).json()
    assert approved["count"] == 1
    assert staff_client.get(LIST_URL, {"status": "published"}).status_code == 400


def test_retrieve_includes_lines_and_allergens(staff_client, draft, flour):
    gluten = Allergen.objects.create(code="gluten", name="Gluten")
    nuts = Allergen.objects.create(code="nuts", name="Nuts")
    IngredientAllergen.objects.create(ingredient=flour, allergen=gluten, presence="contains")
    IngredientAllergen.objects.create(ingredient=flour, allergen=nuts, presence="may_contain")
    body = staff_client.get(detail(draft.pk)).json()
    assert len(body["lines"]) == 2
    assert body["allergens"] == [
        {"code": "gluten", "name": "Gluten", "presence": "contains"},
        {"code": "nuts", "name": "Nuts", "presence": "may_contain"},
    ]
    assert staff_client.get(detail("00000000-0000-0000-0000-000000000000")).status_code == 404


def test_allergen_contains_outranks_may_contain_across_ingredients(
    staff_client, draft, flour, milk
):
    milk_allergen = Allergen.objects.create(code="milk", name="Milk")
    IngredientAllergen.objects.create(
        ingredient=flour, allergen=milk_allergen, presence="may_contain"
    )
    IngredientAllergen.objects.create(ingredient=milk, allergen=milk_allergen, presence="contains")
    allergens = staff_client.get(detail(draft.pk)).json()["allergens"]
    assert allergens == [{"code": "milk", "name": "Milk", "presence": "contains"}]


def test_deactivated_allergen_is_still_reported(staff_client, draft, flour):
    gluten = Allergen.objects.create(code="gluten", name="Gluten", is_active=False)
    IngredientAllergen.objects.create(ingredient=flour, allergen=gluten, presence="contains")
    assert len(staff_client.get(detail(draft.pk)).json()["allergens"]) == 1


# --- Update / state changes -----------------------------------------------------------------
def test_patch_draft_replaces_lines(staff_client, draft):
    response = staff_client.patch(
        detail(draft.pk),
        {
            "yield_quantity": "20",
            "lines": [{"ingredient": "FLOUR-001", "quantity": "500", "unit": "g"}],
        },
        format="json",
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["yield_quantity"] == "20.0000"
    assert [line["ingredient"] for line in body["lines"]] == ["FLOUR-001"]


def test_status_cannot_be_written_through_patch(staff_client, draft):
    staff_client.patch(detail(draft.pk), {"status": "approved"}, format="json")
    draft.refresh_from_db()
    assert draft.status == "draft"
    assert staff_client.put(detail(draft.pk), {}, format="json").status_code == 405
    assert staff_client.delete(detail(draft.pk)).status_code == 405


def test_approve_flow(staff_client, draft, staff_user):
    response = staff_client.post(detail(draft.pk, "approve/"))
    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["status"] == "approved"
    assert body["approved_by"] == str(staff_user.pk)
    flour_line = next(line for line in body["lines"] if line["ingredient"] == "FLOUR-001")
    assert flour_line["net_base_quantity"] == "2000.0000"
    assert flour_line["gross_base_quantity"] == "2222.2222"


def test_approving_twice_returns_409(staff_client, draft):
    staff_client.post(detail(draft.pk, "approve/"))
    response = staff_client.post(detail(draft.pk, "approve/"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_editing_an_approved_version_returns_409(staff_client, draft):
    staff_client.post(detail(draft.pk, "approve/"))
    response = staff_client.patch(detail(draft.pk), {"yield_quantity": "1"}, format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_approving_an_empty_recipe_is_a_validation_error(staff_client):
    created = staff_client.post(LIST_URL, payload(lines=[]), format="json").json()
    response = staff_client.post(detail(created["id"], "approve/"))
    assert response.status_code == 400
    assert "lines" in response.json()["error"]["details"]


def test_retire(staff_client, draft):
    assert staff_client.post(detail(draft.pk, "retire/")).status_code == 409  # still a draft
    staff_client.post(detail(draft.pk, "approve/"))
    response = staff_client.post(detail(draft.pk, "retire/"))
    assert response.status_code == 200
    assert response.json()["status"] == "retired"


# --- Requirements ---------------------------------------------------------------------------
def test_requirements_endpoint(staff_client, draft, staff_user):
    services.approve_recipe_version(draft, actor=staff_user)
    response = staff_client.get(
        detail(draft.pk, "requirements/"), {"quantity": "20", "unit": "pcs"}
    )
    assert response.status_code == 200
    by_sku = {r["ingredient"]: r for r in response.json()}
    assert by_sku["FLOUR-001"] == {
        "ingredient": "FLOUR-001",
        "ingredient_name": "Wheat flour",
        "base_unit": "g",
        "net_quantity": "4000.0000",
        "gross_quantity": "4444.4444",
    }
    assert by_sku["MILK-001"]["gross_quantity"] == "2060.0000"


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"quantity": "abc", "unit": "pcs"},
        {"quantity": "NaN", "unit": "pcs"},
        {"quantity": "5", "unit": "nope"},
        {"quantity": "0", "unit": "pcs"},
        {"quantity": "5", "unit": "kg"},  # yield is a count, not a mass
    ],
)
def test_requirements_validates_query(staff_client, draft, params):
    response = staff_client.get(detail(draft.pk, "requirements/"), params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

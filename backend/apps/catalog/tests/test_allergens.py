import pytest
from django.db import DataError, IntegrityError, transaction

from apps.catalog import services
from apps.catalog.exceptions import ImmutableFieldError
from apps.catalog.models import Allergen, IngredientAllergen

pytestmark = pytest.mark.django_db

ALLERGENS_URL = "/api/v1/admin/allergens/"
INGREDIENTS_URL = "/api/v1/admin/ingredients/"


@pytest.fixture
def staff_client(api_client, staff_user):
    api_client.force_authenticate(staff_user)
    return api_client


@pytest.fixture
def gluten(db) -> Allergen:
    return Allergen.objects.create(code="gluten", name="Cereals containing gluten")


@pytest.fixture
def milk_allergen(db) -> Allergen:
    return Allergen.objects.create(code="milk", name="Milk")


# --- Model ----------------------------------------------------------------------------------
def test_allergen_code_is_normalised_and_immutable(db):
    allergen = Allergen.objects.create(code="  Nuts ", name="Tree nuts")
    assert allergen.code == "nuts"
    allergen.code = "peanuts"
    with pytest.raises(ImmutableFieldError):
        allergen.save()


@pytest.mark.parametrize("code", ["1abc", "a", "has space", "UPPER-dash", "x" * 33])
def test_allergen_code_format_is_enforced_by_the_database(db, code):
    # Over-long codes fail on the column length (DataError); the rest on the CHECK constraint.
    with pytest.raises((IntegrityError, DataError)), transaction.atomic():
        Allergen.objects.bulk_create([Allergen(code=code, name="Bad")])


def test_allergen_link_is_unique_per_ingredient_and_allergen(flour, gluten):
    IngredientAllergen.objects.create(ingredient=flour, allergen=gluten, presence="contains")
    with pytest.raises(IntegrityError), transaction.atomic():
        IngredientAllergen.objects.create(ingredient=flour, allergen=gluten, presence="may_contain")


def test_invalid_presence_is_rejected_by_the_database(flour, gluten):
    with pytest.raises(IntegrityError), transaction.atomic():
        IngredientAllergen.objects.bulk_create(
            [IngredientAllergen(ingredient=flour, allergen=gluten, presence="nope")]
        )


# --- Services -------------------------------------------------------------------------------
def test_set_allergens_replaces_the_declaration(flour, gluten, milk_allergen):
    services.set_ingredient_allergens(flour, [(gluten, "contains"), (milk_allergen, "may_contain")])
    links = services.set_ingredient_allergens(flour, [(gluten, "may_contain")])
    assert [(link.allergen.code, link.presence) for link in links] == [("gluten", "may_contain")]
    assert IngredientAllergen.objects.filter(ingredient=flour).count() == 1


def test_set_allergens_empty_list_clears(flour, gluten):
    services.set_ingredient_allergens(flour, [(gluten, "contains")])
    assert services.set_ingredient_allergens(flour, []) == []


def test_set_allergens_rejects_duplicates_and_changes_nothing(flour, gluten, milk_allergen):
    services.set_ingredient_allergens(flour, [(milk_allergen, "contains")])
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        services.set_ingredient_allergens(flour, [(gluten, "contains"), (gluten, "may_contain")])
    assert list(IngredientAllergen.objects.values_list("allergen__code", flat=True)) == ["milk"]


def test_inactive_allergen_cannot_be_newly_declared_but_existing_one_stays(flour, gluten):
    from rest_framework.exceptions import ValidationError

    services.set_ingredient_allergens(flour, [(gluten, "contains")])
    services.set_allergen_active(gluten, False)
    # Keeping an existing declaration is fine ...
    services.set_ingredient_allergens(flour, [(gluten, "contains")])
    services.set_ingredient_allergens(flour, [])
    # ... but re-adding a now-inactive allergen is not.
    with pytest.raises(ValidationError):
        services.set_ingredient_allergens(flour, [(gluten, "contains")])


# --- API: allergens -------------------------------------------------------------------------
def test_allergen_endpoints_reject_anonymous_and_customers(api_client, user):
    assert api_client.get(ALLERGENS_URL).json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    api_client.force_authenticate(user)
    assert api_client.get(ALLERGENS_URL).status_code == 403
    assert api_client.post(ALLERGENS_URL, {"code": "egg", "name": "Egg"}).status_code == 403


def test_create_list_and_update_allergen(staff_client):
    created = staff_client.post(ALLERGENS_URL, {"code": "Egg", "name": "Eggs"}, format="json")
    assert created.status_code == 201
    body = created.json()
    assert (body["code"], body["name"], body["is_active"]) == ("egg", "Eggs", True)

    listing = staff_client.get(ALLERGENS_URL).json()
    assert [a["code"] for a in listing["results"]] == ["egg"]

    url = f"{ALLERGENS_URL}{body['id']}/"
    assert staff_client.patch(url, {"name": "Egg"}, format="json").json()["name"] == "Egg"
    # Echoing the same code is accepted, changing it is not.
    assert staff_client.patch(url, {"name": "Egg", "code": "egg"}, format="json").status_code == 200
    changed = staff_client.patch(url, {"code": "eggs"}, format="json")
    assert changed.status_code == 400
    assert "code" in changed.json()["error"]["details"]


def test_duplicate_allergen_code_is_a_validation_error(staff_client, gluten):
    response = staff_client.post(ALLERGENS_URL, {"code": "GLUTEN", "name": "x"}, format="json")
    assert response.status_code == 400
    assert "code" in response.json()["error"]["details"]


def test_allergen_is_active_only_changes_through_actions(staff_client, gluten):
    url = f"{ALLERGENS_URL}{gluten.pk}/"
    assert staff_client.patch(url, {"is_active": False}, format="json").status_code == 400
    assert staff_client.post(f"{url}deactivate/").json()["is_active"] is False
    assert staff_client.post(f"{url}deactivate/").status_code == 200  # idempotent
    assert staff_client.get(ALLERGENS_URL, {"is_active": "true"}).json()["count"] == 0
    assert staff_client.post(f"{url}activate/").json()["is_active"] is True
    assert staff_client.get(ALLERGENS_URL, {"is_active": "maybe"}).status_code == 400
    assert staff_client.delete(url).status_code == 405


# --- API: ingredient allergens --------------------------------------------------------------
def test_put_and_get_ingredient_allergens(staff_client, flour, gluten, milk_allergen):
    url = f"{INGREDIENTS_URL}{flour.pk}/allergens/"
    assert staff_client.get(url).json() == []
    response = staff_client.put(
        url,
        {
            "allergens": [
                {"allergen": "gluten", "presence": "contains"},
                {"allergen": "milk", "presence": "may_contain"},
            ]
        },
        format="json",
    )
    assert response.status_code == 200
    assert {(a["allergen"], a["presence"]) for a in response.json()} == {
        ("gluten", "contains"),
        ("milk", "may_contain"),
    }
    assert len(staff_client.get(url).json()) == 2
    assert staff_client.put(url, {"allergens": []}, format="json").json() == []


@pytest.mark.parametrize(
    "payload",
    [
        {"allergens": [{"allergen": "unknown", "presence": "contains"}]},
        {"allergens": [{"allergen": "gluten", "presence": "sometimes"}]},
        {"allergens": [{"allergen": "gluten", "presence": "contains"}] * 2},
        {},
    ],
)
def test_put_ingredient_allergens_validates_input(staff_client, flour, gluten, payload):
    response = staff_client.put(f"{INGREDIENTS_URL}{flour.pk}/allergens/", payload, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert IngredientAllergen.objects.count() == 0


def test_customers_cannot_read_or_change_ingredient_allergens(api_client, user, flour):
    api_client.force_authenticate(user)
    url = f"{INGREDIENTS_URL}{flour.pk}/allergens/"
    assert api_client.get(url).status_code == 403
    assert api_client.put(url, {"allergens": []}, format="json").status_code == 403

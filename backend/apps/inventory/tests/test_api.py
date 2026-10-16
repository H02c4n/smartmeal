from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.accounts.roles import Role
from apps.inventory import services
from apps.inventory.models import InventoryLot, StockMovement

pytestmark = pytest.mark.django_db

BALANCES = "/api/v1/inventory/balances/"
LOTS = "/api/v1/inventory/lots/"
MOVEMENTS = "/api/v1/inventory/movements/"
RESERVATIONS = "/api/v1/inventory/reservations/"
ADJUSTMENTS = "/api/v1/inventory/adjustments/"
KEY = {"HTTP_IDEMPOTENCY_KEY": "adjust-key-0001"}


@pytest.mark.parametrize("url", [BALANCES, LOTS, MOVEMENTS, RESERVATIONS])
def test_anonymous_and_customers_are_rejected(api_client, user, url):
    assert api_client.get(url).json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    api_client.force_authenticate(user)
    assert api_client.get(url).status_code == 403


# --- Balances and lots ----------------------------------------------------------------------
def test_balances_show_definitions_per_ingredient(
    staff_client, make_released_lot, receive, flour, gram
):
    make_released_lot("10", "REL")
    receive("5", "PEND")
    services.reserve_stock(
        ingredient=flour,
        quantity=Decimal("2000"),
        unit=gram,
        reference_type="order",
        reference_id=uuid4(),
    )
    body = staff_client.get(BALANCES).json()
    [row] = body["results"]
    assert row == {
        "ingredient": "FLOUR-001",
        "ingredient_name": "Wheat flour",
        "base_unit": "g",
        "physical": "15000.0000",
        "reserved": "2000.0000",
        "available": "8000.0000",
        "unavailable": "5000.0000",
    }
    assert staff_client.get(BALANCES, {"ingredient": "milk-001"}).json()["count"] == 0
    assert staff_client.get(BALANCES, {"ingredient": "flour-001"}).json()["count"] == 1


def test_lot_list_filters_and_fields(staff_client, make_released_lot, receive):
    make_released_lot("10", "REL")
    receive("5", "PEND")
    assert staff_client.get(LOTS).json()["count"] == 2
    released = staff_client.get(LOTS, {"quality_status": "released"}).json()["results"]
    assert [lot["supplier_lot_code"] for lot in released] == ["REL"]
    assert released[0]["available"] == "10000.0000"
    assert released[0]["ingredient"] == "FLOUR-001"
    assert staff_client.get(LOTS, {"quality_status": "weird"}).status_code == 400
    assert staff_client.get(LOTS, {"has_stock": "maybe"}).status_code == 400
    assert staff_client.get(LOTS, {"has_stock": "true"}).json()["count"] == 2


def test_lots_are_listed_earliest_expiry_first(staff_client, make_released_lot):
    make_released_lot("1", "LATE", days=40)
    make_released_lot("1", "SOON", days=3)
    codes = [lot["supplier_lot_code"] for lot in staff_client.get(LOTS).json()["results"]]
    assert codes == ["SOON", "LATE"]


# --- Release / block need special permissions -----------------------------------------------
def test_release_and_block_are_quality_decisions(client_for, receive):
    lot = receive("10", "SUP-A")
    release = f"{LOTS}{lot.pk}/release/"
    block = f"{LOTS}{lot.pk}/block/"
    for role in (Role.ADMIN, Role.PURCHASING, Role.PLANNER, Role.PRODUCTION, Role.CUSTOMER):
        client = client_for(role)
        assert client.post(release, {"reason": "ok"}, format="json").status_code == 403, role
        assert client.post(block, {"reason": "bad"}, format="json").status_code == 403, role
    quality = client_for(Role.QUALITY)
    assert quality.post(release, {}, format="json").status_code == 400  # reason required
    done = quality.post(release, {"reason": "Temperature OK"}, format="json")
    assert done.status_code == 200 and done.json()["quality_status"] == "released"
    blocked = quality.post(block, {"reason": "Recall"}, format="json")
    assert blocked.json()["quality_status"] == "blocked"
    assert quality.post(block, {"reason": "Recall"}, format="json").status_code == 200


# --- Adjustments ----------------------------------------------------------------------------
def adjustment(lot, quantity="-1", unit="kg", reason="Stock count", **extra):
    return {"lot": str(lot.pk), "quantity": quantity, "unit": unit, "reason": reason, **extra}


def test_adjustment_needs_permission_key_and_reason(staff_client, client_for, make_released_lot):
    lot = make_released_lot("10", "SUP-A")
    for role in (Role.PLANNER, Role.PURCHASING, Role.QUALITY):
        denied = client_for(role).post(ADJUSTMENTS, adjustment(lot), format="json", **KEY)
        assert denied.status_code == 403, role
    no_key = staff_client.post(ADJUSTMENTS, adjustment(lot), format="json")
    assert no_key.status_code == 400 and "Idempotency-Key" in no_key.json()["error"]["details"]
    no_reason = staff_client.post(ADJUSTMENTS, adjustment(lot, reason=""), format="json", **KEY)
    assert no_reason.status_code == 400
    zero = staff_client.post(ADJUSTMENTS, adjustment(lot, quantity="0"), format="json", **KEY)
    assert zero.status_code == 400
    assert InventoryLot.objects.get().on_hand == Decimal("10000.0000")


def test_adjustment_is_applied_once_per_key(staff_client, make_released_lot):
    lot = make_released_lot("10", "SUP-A")
    first = staff_client.post(ADJUSTMENTS, adjustment(lot, "-2"), format="json", **KEY)
    again = staff_client.post(ADJUSTMENTS, adjustment(lot, "-2"), format="json", **KEY)
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"]
    assert first.json()["quantity_delta"] == "-2000.0000"
    assert InventoryLot.objects.get().on_hand == Decimal("8000.0000")
    conflict = staff_client.post(ADJUSTMENTS, adjustment(lot, "-3"), format="json", **KEY)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_adjustment_cannot_remove_reserved_stock(staff_client, make_released_lot, flour, gram):
    lot = make_released_lot("1", "SUP-A")
    services.reserve_stock(
        ingredient=flour,
        quantity=Decimal("800"),
        unit=gram,
        reference_type="order",
        reference_id=uuid4(),
    )
    response = staff_client.post(ADJUSTMENTS, adjustment(lot, "-500", "g"), format="json", **KEY)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert response.json()["error"]["details"]["reserved"] == "800.0000"


# --- Movements ------------------------------------------------------------------------------
def test_ledger_is_listed_and_filterable_and_read_only(
    staff_client, make_released_lot, staff_user, gram
):
    lot = make_released_lot("1", "SUP-A")
    services.adjust_stock(lot, quantity=Decimal("-10"), unit=gram, reason="Spill", actor=staff_user)
    everything = staff_client.get(MOVEMENTS, {"lot": str(lot.pk)}).json()["results"]
    assert [m["movement_type"] for m in everything] == ["receipt", "adjustment"]
    assert everything[1]["balance_after"] == "990.0000"
    assert staff_client.get(MOVEMENTS, {"movement_type": "waste"}).json()["count"] == 0
    assert staff_client.get(MOVEMENTS, {"movement_type": "nope"}).status_code == 400
    for method in ("put", "patch", "delete"):
        movement_id = everything[0]["id"]
        assert (
            getattr(staff_client, method)(
                f"{MOVEMENTS}{movement_id}/", {}, format="json"
            ).status_code
            == 405
        )


def test_reverse_movement_via_api(staff_client, client_for, make_released_lot, staff_user, gram):
    lot = make_released_lot("1", "SUP-A")
    movement = services.adjust_stock(
        lot, quantity=Decimal("-10"), unit=gram, reason="Spill", actor=staff_user
    )
    url = f"{MOVEMENTS}{movement.pk}/reverse/"
    assert (
        client_for(Role.PLANNER).post(url, {"reason": "Mistake"}, format="json").status_code == 403
    )
    done = staff_client.post(url, {"reason": "Mistake"}, format="json")
    assert done.status_code == 201
    assert done.json()["reverses"] == str(movement.pk)
    assert staff_client.post(url, {"reason": "Mistake"}, format="json").status_code == 409
    assert InventoryLot.objects.get().on_hand == Decimal("1000.0000")


# --- Reservations ---------------------------------------------------------------------------
def reservation_body(ref=None, quantity="600", unit="g", **extra):
    return {
        "ingredient": "flour-001",
        "quantity": quantity,
        "unit": unit,
        "reference_type": "order",
        "reference_id": str(ref or uuid4()),
        **extra,
    }


def test_reserve_list_release_flow(staff_client, make_released_lot):
    make_released_lot("1", "SUP-A")
    ref = uuid4()
    created = staff_client.post(RESERVATIONS, reservation_body(ref), format="json")
    assert created.status_code == 201, created.json()
    [row] = created.json()
    assert (row["status"], row["quantity"], row["ingredient"]) == (
        "active",
        "600.0000",
        "FLOUR-001",
    )
    again = staff_client.post(RESERVATIONS, reservation_body(ref), format="json")
    assert again.status_code == 200 and again.json()[0]["id"] == row["id"]
    listed = staff_client.get(RESERVATIONS, {"reference_id": str(ref)}).json()
    assert listed["count"] == 1
    released = staff_client.post(f"{RESERVATIONS}{row['id']}/release/")
    assert released.json()["status"] == "released"
    assert staff_client.post(f"{RESERVATIONS}{row['id']}/release/").status_code == 200
    assert staff_client.get(RESERVATIONS, {"status": "released"}).json()["count"] == 1
    assert staff_client.get(RESERVATIONS, {"status": "x"}).status_code == 400


def test_over_reservation_returns_409_with_numbers(staff_client, make_released_lot):
    make_released_lot("1", "SUP-A")
    response = staff_client.post(RESERVATIONS, reservation_body(quantity="1001"), format="json")
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INSUFFICIENT_STOCK"
    assert error["details"] == {
        "ingredient": "FLOUR-001",
        "requested": "1001.0000",
        "available": "1000.0000",
    }


def test_same_reference_other_quantity_is_a_conflict(staff_client, make_released_lot):
    make_released_lot("1", "SUP-A")
    ref = uuid4()
    staff_client.post(RESERVATIONS, reservation_body(ref), format="json")
    response = staff_client.post(RESERVATIONS, reservation_body(ref, quantity="700"), format="json")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


@pytest.mark.parametrize(
    "mutate",
    [
        {"quantity": "0"},
        {"quantity": "-5"},
        {"ingredient": "NOPE"},
        {"unit": "bushel"},
        {"reference_id": "not-a-uuid"},
        {"reference_type": ""},
        {"expires_at": "2000-01-01T00:00:00Z"},
    ],
)
def test_reservation_validation(staff_client, make_released_lot, mutate):
    make_released_lot("1", "SUP-A")
    response = staff_client.post(RESERVATIONS, {**reservation_body(), **mutate}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_consume_and_blocked_lot_error(staff_client, make_released_lot, staff_user):
    lot = make_released_lot("1", "SUP-A")
    [row] = staff_client.post(RESERVATIONS, reservation_body(), format="json").json()
    url = f"{RESERVATIONS}{row['id']}/consume/"
    services.block_lot(lot, actor=staff_user, reason="Recall")
    blocked = staff_client.post(url, {}, format="json")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "LOT_BLOCKED"
    services.release_lot(lot, actor=staff_user, reason="Recall lifted")
    done = staff_client.post(url, {"quantity": "550"}, format="json")
    assert done.status_code == 200
    assert (done.json()["status"], done.json()["consumed_quantity"]) == ("consumed", "550.0000")
    assert staff_client.post(url, {"quantity": "550"}, format="json").status_code == 200  # replay
    assert staff_client.post(url, {"quantity": "10"}, format="json").status_code == 409
    assert staff_client.post(f"{RESERVATIONS}{row['id']}/release/").status_code == 409
    movement = StockMovement.objects.get(movement_type="consumption")
    assert movement.quantity_delta == Decimal("-550.0000")


def test_use_by_margin_is_honoured_through_the_api(staff_client, make_released_lot, today):
    make_released_lot("1", "SHORT", days=2)
    margin = (today + timedelta(days=7)).isoformat()
    response = staff_client.post(
        RESERVATIONS, reservation_body(quantity="100", use_by_on_or_after=margin), format="json"
    )
    assert response.status_code == 409


# --- Schema ---------------------------------------------------------------------------------
def test_schema_documents_the_stock_contract(staff_client):
    paths = staff_client.get("/api/v1/schema/", {"format": "json"}).json()["paths"]
    expected = {
        "/api/v1/suppliers/": {"get", "post"},
        "/api/v1/suppliers/{id}/": {"get", "patch"},
        "/api/v1/suppliers/{id}/activate/": {"post"},
        "/api/v1/purchase-orders/": {"get", "post"},
        "/api/v1/purchase-orders/{id}/": {"get", "patch"},
        "/api/v1/purchase-orders/{id}/submit/": {"post"},
        "/api/v1/purchase-orders/{id}/cancel/": {"post"},
        "/api/v1/goods-receipts/": {"get", "post"},
        "/api/v1/goods-receipts/{id}/reverse/": {"post"},
        "/api/v1/inventory/balances/": {"get"},
        "/api/v1/inventory/lots/": {"get"},
        "/api/v1/inventory/lots/{id}/release/": {"post"},
        "/api/v1/inventory/lots/{id}/block/": {"post"},
        "/api/v1/inventory/movements/": {"get"},
        "/api/v1/inventory/movements/{id}/reverse/": {"post"},
        "/api/v1/inventory/adjustments/": {"post"},
        "/api/v1/inventory/reservations/": {"get", "post"},
        "/api/v1/inventory/reservations/{id}/release/": {"post"},
        "/api/v1/inventory/reservations/{id}/consume/": {"post"},
    }
    for path, methods in expected.items():
        assert path in paths, path
        assert set(paths[path]) == methods, path
    parameters = paths["/api/v1/goods-receipts/"]["post"]["parameters"]
    assert any(p["name"] == "Idempotency-Key" and p["required"] for p in parameters)

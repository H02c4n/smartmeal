from datetime import timedelta
from decimal import Decimal

import pytest

from apps.accounts.roles import Role
from apps.inventory.models import InventoryLot
from apps.purchasing import services
from apps.purchasing.models import GoodsReceipt

pytestmark = pytest.mark.django_db

SUPPLIERS = "/api/v1/suppliers/"
ORDERS = "/api/v1/purchase-orders/"
RECEIPTS = "/api/v1/goods-receipts/"
KEY = {"HTTP_IDEMPOTENCY_KEY": "receipt-key-0001"}


def receipt_body(po, quantity="40", unit="kg", code="SUP-1", days=30, today=None):
    from django.utils import timezone

    expiry = (today or timezone.localdate()) + timedelta(days=days)
    return {
        "purchase_order": str(po.pk),
        "lines": [
            {
                "po_line": str(po.lines.get().pk),
                "quantity": quantity,
                "unit": unit,
                "supplier_lot_code": code,
                "expiry_date": expiry.isoformat(),
            }
        ],
    }


# --- Access ---------------------------------------------------------------------------------
@pytest.mark.parametrize("url", [SUPPLIERS, ORDERS, RECEIPTS])
def test_anonymous_and_customers_are_rejected(api_client, user, url):
    assert api_client.get(url).json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    api_client.force_authenticate(user)
    assert api_client.get(url).status_code == 403
    assert api_client.post(url, {}, format="json").status_code == 403


# --- Suppliers ------------------------------------------------------------------------------
def test_supplier_crud_and_activation(staff_client):
    created = staff_client.post(SUPPLIERS, {"name": "Acme Foods"}, format="json")
    assert created.status_code == 201
    pk = created.json()["id"]
    assert staff_client.post(SUPPLIERS, {"name": "ACME FOODS"}, format="json").status_code == 400
    patched = staff_client.patch(f"{SUPPLIERS}{pk}/", {"contact_details": "a@b.se"}, format="json")
    assert patched.json()["contact_details"] == "a@b.se"
    assert (
        staff_client.patch(f"{SUPPLIERS}{pk}/", {"is_active": False}, format="json").status_code
        == 400
    )
    assert staff_client.post(f"{SUPPLIERS}{pk}/deactivate/").json()["is_active"] is False
    assert staff_client.get(SUPPLIERS, {"q": "acme"}).json()["count"] == 1
    assert staff_client.delete(f"{SUPPLIERS}{pk}/").status_code == 405


# --- Purchase orders ------------------------------------------------------------------------
def po_body(supplier, **extra):
    return {
        "supplier": str(supplier.pk),
        "currency": "sek",
        "lines": [
            {"ingredient": "flour-001", "quantity": "100", "unit": "kg", "unit_cost": "12.5"}
        ],
        **extra,
    }


def test_create_submit_cancel_flow(staff_client, supplier, flour):
    created = staff_client.post(ORDERS, po_body(supplier), format="json")
    assert created.status_code == 201, created.json()
    body = created.json()
    assert (body["status"], body["currency"]) == ("draft", "SEK")
    assert body["lines"][0]["ordered_base_quantity"] == "100000.0000"
    pk = body["id"]

    patched = staff_client.patch(
        f"{ORDERS}{pk}/",
        {"lines": [{"ingredient": "FLOUR-001", "quantity": "5", "unit": "kg", "unit_cost": "1"}]},
        format="json",
    )
    assert patched.json()["lines"][0]["ordered_quantity"] == "5.0000"

    submitted = staff_client.post(f"{ORDERS}{pk}/submit/")
    assert submitted.json()["status"] == "submitted"
    assert staff_client.post(f"{ORDERS}{pk}/submit/").status_code == 200  # idempotent
    edit_after = staff_client.patch(f"{ORDERS}{pk}/", {"lines": []}, format="json")
    assert edit_after.status_code == 409
    assert edit_after.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
    assert staff_client.post(f"{ORDERS}{pk}/cancel/").json()["status"] == "cancelled"
    assert staff_client.post(f"{ORDERS}{pk}/submit/").status_code == 409


@pytest.mark.parametrize(
    "mutate",
    [
        {"currency": "SEKK"},
        {"supplier": "00000000-0000-0000-0000-000000000000"},
        {"lines": [{"ingredient": "NOPE", "quantity": "1", "unit": "kg", "unit_cost": "1"}]},
        {"lines": [{"ingredient": "FLOUR-001", "quantity": "-1", "unit": "kg", "unit_cost": "1"}]},
        {"lines": [{"ingredient": "FLOUR-001", "quantity": "1", "unit": "kg", "unit_cost": "-1"}]},
    ],
)
def test_po_validation(staff_client, supplier, flour, mutate):
    response = staff_client.post(ORDERS, {**po_body(supplier), **mutate}, format="json")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_orders_filters_by_status(staff_client, supplier, submitted_po):
    assert staff_client.get(ORDERS, {"status": "submitted"}).json()["count"] == 1
    assert staff_client.get(ORDERS, {"status": "draft"}).json()["count"] == 0
    assert staff_client.get(ORDERS, {"status": "bogus"}).status_code == 400
    assert "lines" not in staff_client.get(ORDERS).json()["results"][0]


# --- Goods receipts -------------------------------------------------------------------------
def test_receipt_requires_an_idempotency_key(staff_client, submitted_po):
    response = staff_client.post(RECEIPTS, receipt_body(submitted_po), format="json")
    assert response.status_code == 400
    assert "Idempotency-Key" in response.json()["error"]["details"]
    assert InventoryLot.objects.count() == 0


def test_receipt_creates_pending_lots_and_returns_them(staff_client, submitted_po):
    response = staff_client.post(RECEIPTS, receipt_body(submitted_po), format="json", **KEY)
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["status"] == "posted"
    [line] = body["lines"]
    assert line["received_base_quantity"] == "40000.0000"
    assert line["lot"]["quality_status"] == "pending"
    assert line["lot"]["internal_lot_code"].startswith("L")


def test_retrying_a_receipt_with_the_same_key_does_not_duplicate_stock(staff_client, submitted_po):
    body = receipt_body(submitted_po)
    first = staff_client.post(RECEIPTS, body, format="json", **KEY)
    second = staff_client.post(RECEIPTS, body, format="json", **KEY)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]
    assert GoodsReceipt.objects.count() == 1
    assert InventoryLot.objects.get().on_hand == Decimal("40000.0000")


def test_same_key_with_another_body_is_rejected(staff_client, submitted_po):
    staff_client.post(RECEIPTS, receipt_body(submitted_po), format="json", **KEY)
    other = staff_client.post(
        RECEIPTS, receipt_body(submitted_po, quantity="41"), format="json", **KEY
    )
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert InventoryLot.objects.count() == 1


def test_failed_receipt_can_be_retried_with_the_same_key(staff_client, submitted_po):
    bad = receipt_body(submitted_po, quantity="500")  # far above the order
    assert staff_client.post(RECEIPTS, bad, format="json", **KEY).status_code == 409
    assert InventoryLot.objects.count() == 0
    good = receipt_body(submitted_po, quantity="500")
    good["lines"][0]["quantity"] = "50"
    # A *different* body under the same key is only a conflict if the first one succeeded.
    assert staff_client.post(RECEIPTS, good, format="json", **KEY).status_code == 201


def test_receipt_validation_errors(
    staff_client, submitted_po, supplier, flour, kilogram, staff_user
):
    body = receipt_body(submitted_po)
    body["lines"][0]["expiry_date"] = "2000-01-01"
    assert staff_client.post(RECEIPTS, body, format="json", **KEY).status_code == 400
    body = receipt_body(submitted_po)
    body["lines"][0]["supplier_lot_code"] = ""
    assert staff_client.post(RECEIPTS, body, format="json", **KEY).status_code == 400
    body = receipt_body(submitted_po)
    body["lines"] = []
    assert staff_client.post(RECEIPTS, body, format="json", **KEY).status_code == 400
    other = services.submit_purchase_order(
        services.create_purchase_order(
            supplier=supplier,
            currency="SEK",
            created_by=staff_user,
            lines=[services.POLineInput(flour, Decimal("1"), kilogram, Decimal("1"))],
        )
    )
    foreign = receipt_body(submitted_po)
    foreign["lines"][0]["po_line"] = str(other.lines.get().pk)
    assert staff_client.post(RECEIPTS, foreign, format="json", **KEY).status_code == 400
    assert InventoryLot.objects.count() == 0


def test_receipt_against_a_draft_order_is_a_state_error(
    staff_client, supplier, flour, kilogram, staff_user
):
    draft = services.create_purchase_order(
        supplier=supplier,
        currency="SEK",
        created_by=staff_user,
        lines=[services.POLineInput(flour, Decimal("1"), kilogram, Decimal("1"))],
    )
    response = staff_client.post(RECEIPTS, receipt_body(draft, quantity="1"), format="json", **KEY)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_reversing_a_receipt_is_an_admin_decision(staff_client, client_for, submitted_po):
    receipt = staff_client.post(RECEIPTS, receipt_body(submitted_po), format="json", **KEY).json()
    url = f"{RECEIPTS}{receipt['id']}/reverse/"
    for role in (Role.PURCHASING, Role.QUALITY, Role.PLANNER, Role.FINANCE):
        denied = client_for(role).post(url, {"reason": "Wrong delivery"}, format="json")
        assert denied.status_code == 403, role
    admin = client_for(Role.ADMIN)
    missing_reason = admin.post(url, {}, format="json")
    assert missing_reason.status_code == 400
    done = admin.post(url, {"reason": "Wrong delivery"}, format="json")
    assert done.status_code == 200
    assert done.json()["status"] == "reversed"
    assert InventoryLot.objects.get().on_hand == 0
    assert admin.post(url, {"reason": "Wrong delivery"}, format="json").status_code == 200


def test_purchasing_reads_and_writes_are_separate_permissions(client_for, supplier):
    # FINANCE and ADMIN may look at purchasing data but not change it.
    for role in (Role.FINANCE, Role.ADMIN):
        client = client_for(role)
        assert client.get(SUPPLIERS).status_code == 200, role
        assert client.post(SUPPLIERS, {"name": "X AB"}, format="json").status_code == 403, role
    assert (
        client_for(Role.PURCHASING)
        .post(SUPPLIERS, {"name": "Second AB"}, format="json")
        .status_code
        == 201
    )


def test_superuser_without_roles_has_no_api_access(api_client, superuser, submitted_po):
    api_client.force_authenticate(superuser)  # Django superuser flag grants nothing here
    assert api_client.get(SUPPLIERS).status_code == 403

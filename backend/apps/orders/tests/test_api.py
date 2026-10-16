from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.orders.models import CustomerAddress, Order

pytestmark = pytest.mark.django_db

ORDERS = "/api/v1/orders/"
ADDRESSES = "/api/v1/me/addresses/"
KEY = {"HTTP_IDEMPOTENCY_KEY": "order-key-0001"}


def signed_in(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def buyer(customer):
    return signed_in(customer)


def body(address, delivery_date, *items):
    return {
        "delivery_date": delivery_date.isoformat(),
        "delivery_address_id": str(address.pk),
        "items": [{"product_id": str(p.pk), "quantity": q} for p, q in items],
    }


def order_it(client, address, delivery_date, *items, key=KEY):
    return client.post(ORDERS, body(address, delivery_date, *items), format="json", **key)


# --- Access ----------------------------------------
def test_anonymous_gets_401(api_client):
    assert api_client.get(ORDERS).status_code == 401
    assert api_client.post(ORDERS, {}, format="json").status_code == 401
    assert api_client.get(ADDRESSES).status_code == 401


def test_users_without_the_right_role_are_refused(api_client, user, client_for):
    api_client.force_authenticate(user)  # signed in, no role
    assert api_client.get(ORDERS).status_code == 403
    assert api_client.post(ORDERS, {}, format="json").status_code == 403
    assert api_client.get(ADDRESSES).status_code == 403
    for role in (Role.PLANNER, Role.DRIVER, Role.PURCHASING):
        client = client_for(role)
        assert client.post(ORDERS, {}, format="json").status_code == 403, role


def test_back_office_cannot_place_orders_or_use_an_address_book(client_for):
    support = client_for(Role.SUPPORT)
    assert support.get(ORDERS).status_code == 200  # may read
    assert support.post(ORDERS, {}, format="json").status_code == 403  # may not place
    assert support.get(ADDRESSES).status_code == 403


# --- Placing an order ----------------------------------------
def test_place_order_returns_the_order_and_hides_internals(
    buyer, address, delivery_date, bowl, wrap, stocked
):
    response = order_it(buyer, address, delivery_date, (bowl, 2), (wrap, 1))
    assert response.status_code == 201, response.json()
    data = response.json()
    assert data["status"] == "confirmed"
    assert data["total_amount"] == "357.50"
    assert data["delivery_address"]["city"] == "Stockholm"
    assert [i["product_sku"] for i in data["items"]] == ["MEAL-001", "MEAL-002"]
    assert "customer_email" not in data and "status_history" not in data
    assert Order.objects.get().customer.email == "buyer@example.com"


def test_idempotency_key_is_required(buyer, address, delivery_date, bowl, stocked):
    response = buyer.post(ORDERS, body(address, delivery_date, (bowl, 1)), format="json")
    assert response.status_code == 400
    assert "Idempotency-Key" in response.json()["error"]["details"]
    assert Order.objects.count() == 0


def test_a_retry_with_the_same_key_does_not_order_twice(
    buyer, address, delivery_date, bowl, stocked
):
    first = order_it(buyer, address, delivery_date, (bowl, 2))
    again = order_it(buyer, address, delivery_date, (bowl, 2))
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"]
    assert Order.objects.count() == 1
    different = order_it(buyer, address, delivery_date, (bowl, 3))
    assert different.status_code == 409
    assert different.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_the_same_key_from_another_customer_is_independent(
    buyer, address, other_customer, other_address, delivery_date, bowl, stocked
):
    assert order_it(buyer, address, delivery_date, (bowl, 1)).status_code == 201
    other = signed_in(other_customer)
    assert order_it(other, other_address, delivery_date, (bowl, 1)).status_code == 201
    assert Order.objects.count() == 2


def test_insufficient_stock_is_a_409_that_leaks_no_inventory(
    buyer, address, delivery_date, bowl, make_released_lot
):
    make_released_lot("1", "SMALL")  # 5 bowls
    response = order_it(buyer, address, delivery_date, (bowl, 6))
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INSUFFICIENT_STOCK"
    assert error["details"] == {"products": [str(bowl.pk)]}
    text = response.content.decode()
    assert (
        "FLOUR" not in text
        and "1000" not in text
        and "ingredient" not in text
        and "reserved" not in text
    )
    assert Order.objects.count() == 0


def test_validation_errors_use_the_standard_envelope(
    buyer, address, other_address, delivery_date, bowl, stocked
):
    bad_items = buyer.post(
        ORDERS,
        {**body(address, delivery_date, (bowl, 1)), "items": [{"product_id": "x", "quantity": 0}]},
        format="json",
        **KEY,
    )
    assert bad_items.status_code == 400
    assert bad_items.json()["error"]["code"] == "VALIDATION_ERROR"

    foreign = order_it(
        buyer, other_address, delivery_date, (bowl, 1), key={"HTTP_IDEMPOTENCY_KEY": "k-foreign-1"}
    )
    assert foreign.status_code == 400
    assert "delivery_address_id" in foreign.json()["error"]["details"]

    soon = order_it(
        buyer, address, timezone.localdate(), (bowl, 1), key={"HTTP_IDEMPOTENCY_KEY": "k-soon-0001"}
    )
    assert soon.status_code == 400 and "delivery_date" in soon.json()["error"]["details"]


# --- Object scope: customers only ever see their own ----------------------------------------
def test_customers_see_only_their_own_orders(
    buyer, address, other_customer, other_address, delivery_date, bowl, stocked
):
    mine = order_it(buyer, address, delivery_date, (bowl, 1)).json()
    theirs = order_it(
        signed_in(other_customer),
        other_address,
        delivery_date,
        (bowl, 1),
        key={"HTTP_IDEMPOTENCY_KEY": "other-key-01"},
    ).json()

    listing = buyer.get(ORDERS).json()
    assert [o["id"] for o in listing["results"]] == [mine["id"]]
    assert buyer.get(f"{ORDERS}{mine['id']}/").status_code == 200
    stranger = buyer.get(f"{ORDERS}{theirs['id']}/")
    assert stranger.status_code == 404  # existence is not revealed
    assert stranger.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    # The customer filter must not widen a customer's scope.
    widened = buyer.get(ORDERS, {"customer": "other@example.com"}).json()
    assert [o["id"] for o in widened["results"]] == [mine["id"]]


def test_a_customer_cannot_cancel_someone_elses_order(
    buyer, other_customer, other_address, delivery_date, bowl, stocked
):
    theirs = order_it(signed_in(other_customer), other_address, delivery_date, (bowl, 1)).json()
    response = buyer.post(f"{ORDERS}{theirs['id']}/cancel/", {}, format="json")
    assert response.status_code == 404
    assert Order.objects.get(pk=theirs["id"]).status == "confirmed"


def test_back_office_sees_everything_with_customer_and_history(
    buyer, address, delivery_date, bowl, stocked, client_for
):
    order_it(buyer, address, delivery_date, (bowl, 1))
    for role in (
        Role.ADMIN,
        Role.SUPPORT,
        Role.PLANNER,
        Role.PRODUCTION,
        Role.PACKING,
        Role.FINANCE,
    ):
        client = client_for(role)
        listing = client.get(ORDERS).json()
        assert listing["count"] == 1, role
        row = listing["results"][0]
        assert row["customer_email"] == "buyer@example.com"
        assert row["status_history"][0]["to_status"] == "confirmed"
    mine_only = client_for(Role.SUPPORT).get(ORDERS, {"customer": "nobody@example.com"}).json()
    assert mine_only["count"] == 0


def test_list_filters(buyer, address, delivery_date, bowl, stocked):
    first = order_it(buyer, address, delivery_date, (bowl, 1)).json()
    later = delivery_date + timedelta(days=1)
    order_it(buyer, address, later, (bowl, 1), key={"HTTP_IDEMPOTENCY_KEY": "second-key-1"})
    buyer.post(f"{ORDERS}{first['id']}/cancel/", {}, format="json")
    assert buyer.get(ORDERS, {"status": "cancelled"}).json()["count"] == 1
    assert buyer.get(ORDERS, {"delivery_date": later.isoformat()}).json()["count"] == 1


# --- Cancelling ----------------------------------------
def test_customer_cancels_their_order_and_stock_comes_back(
    buyer, address, delivery_date, bowl, stocked
):
    from apps.inventory.models import InventoryLot

    created = order_it(buyer, address, delivery_date, (bowl, 3)).json()
    assert InventoryLot.objects.get().reserved == Decimal("600")
    url = f"{ORDERS}{created['id']}/cancel/"
    done = buyer.post(url, {"reason": "Changed my mind"}, format="json")
    assert done.status_code == 200
    assert done.json()["status"] == "cancelled"
    assert done.json()["cancellation_reason"] == "Changed my mind"
    assert InventoryLot.objects.get().reserved == 0
    assert buyer.post(url, {}, format="json").status_code == 200  # repeat is harmless


def test_customer_cancel_after_the_deadline_is_a_409(buyer, address, delivery_date, bowl, stocked):
    created = order_it(buyer, address, delivery_date, (bowl, 1)).json()
    Order.objects.filter(pk=created["id"]).update(delivery_date=timezone.localdate())
    response = buyer.post(f"{ORDERS}{created['id']}/cancel/", {}, format="json")
    assert response.status_code == 409
    assert "latest_cancellation_date" in response.json()["error"]["details"]


def test_staff_cancellation_needs_a_reason_and_ignores_the_deadline(
    buyer, address, delivery_date, bowl, stocked, client_for
):
    created = order_it(buyer, address, delivery_date, (bowl, 1)).json()
    Order.objects.filter(pk=created["id"]).update(delivery_date=timezone.localdate())
    url = f"{ORDERS}{created['id']}/cancel/"
    for role in (Role.PLANNER, Role.PRODUCTION, Role.FINANCE, Role.PACKING):
        assert client_for(role).post(url, {"reason": "x"}, format="json").status_code == 403, role
    support = client_for(Role.SUPPORT)
    assert support.post(url, {}, format="json").status_code == 400
    done = support.post(url, {"reason": "Kitchen closed"}, format="json")
    assert done.status_code == 200
    assert done.json()["status_history"][-1]["reason"] == "Kitchen closed"


# --- Address book ----------------------------------------
ADDRESS_BODY = {
    "recipient_name": "Anna Svensson",
    "line1": "Storgatan 1",
    "postal_code": "11122",
    "city": "Stockholm",
    "country_code": "se",
}


def test_address_crud_is_private_to_the_owner(buyer, other_customer, other_address):
    created = buyer.post(ADDRESSES, ADDRESS_BODY, format="json")
    assert created.status_code == 201
    assert created.json()["country_code"] == "SE"
    url = f"{ADDRESSES}{created.json()['id']}/"
    assert buyer.patch(url, {"city": "Uppsala"}, format="json").json()["city"] == "Uppsala"
    assert buyer.get(ADDRESSES).json()["count"] == 1  # never the other customer's address

    stranger_url = f"{ADDRESSES}{other_address.pk}/"
    assert buyer.get(stranger_url).status_code == 404
    assert buyer.patch(stranger_url, {"city": "X"}, format="json").status_code == 404
    assert buyer.delete(stranger_url).status_code == 404
    assert CustomerAddress.objects.get(pk=other_address.pk).city == "Malmo"

    assert buyer.delete(url).status_code == 204
    assert buyer.get(ADDRESSES).json()["count"] == 0


def test_address_validation_and_limit(buyer, settings):
    assert (
        buyer.post(ADDRESSES, {**ADDRESS_BODY, "country_code": "SWE"}, format="json").status_code
        == 400
    )
    assert buyer.post(ADDRESSES, {**ADDRESS_BODY, "city": ""}, format="json").status_code == 400
    settings.ADDRESS_MAX_PER_CUSTOMER = 2
    assert buyer.post(ADDRESSES, ADDRESS_BODY, format="json").status_code == 201
    assert buyer.post(ADDRESSES, ADDRESS_BODY, format="json").status_code == 201
    assert buyer.post(ADDRESSES, ADDRESS_BODY, format="json").status_code == 400


def test_deleting_an_address_does_not_change_past_orders(
    buyer, address, delivery_date, bowl, stocked
):
    created = order_it(buyer, address, delivery_date, (bowl, 1)).json()
    assert buyer.delete(f"{ADDRESSES}{address.pk}/").status_code == 204
    assert buyer.get(f"{ORDERS}{created['id']}/").json()["delivery_address"]["city"] == "Stockholm"


def test_address_book_works_with_a_real_browser_session(customer):
    """Regression: a session user is a lazy wrapper that force_authenticate hides."""
    browser = APIClient(enforce_csrf_checks=True)
    token = browser.get("/api/v1/auth/csrf/").json()["csrf_token"]
    login = browser.post(
        "/api/v1/auth/login/",
        {"email": "buyer@example.com", "password": "s3cret-Pass-123"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert login.status_code == 200
    token = browser.get("/api/v1/auth/csrf/").json()["csrf_token"]
    created = browser.post(ADDRESSES, ADDRESS_BODY, format="json", HTTP_X_CSRFTOKEN=token)
    assert created.status_code == 201
    assert browser.get(ADDRESSES).json()["count"] == 1

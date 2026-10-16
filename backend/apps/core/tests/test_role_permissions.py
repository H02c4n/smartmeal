"""Endpoint access matrix: which role may reach which back-office endpoint (ADR-013).

``ok`` means the permission check passes (the request then fails or succeeds on its own merits
-- an empty POST body gives 400); ``no`` means 403. Anything not named is denied.
"""

import pytest

from apps.accounts.roles import Role

pytestmark = pytest.mark.django_db

READ = {
    "catalog": "/api/v1/admin/products/",
    "recipes": "/api/v1/admin/recipe-versions/",
    "suppliers": "/api/v1/suppliers/",
    "purchase_orders": "/api/v1/purchase-orders/",
    "goods_receipts": "/api/v1/goods-receipts/",
    "balances": "/api/v1/inventory/balances/",
    "lots": "/api/v1/inventory/lots/",
    "movements": "/api/v1/inventory/movements/",
    "reservations": "/api/v1/inventory/reservations/",
}
WRITE = {
    "catalog": "/api/v1/admin/products/",
    "recipes": "/api/v1/admin/recipe-versions/",
    "suppliers": "/api/v1/suppliers/",
    "purchase_orders": "/api/v1/purchase-orders/",
    "reservations": "/api/v1/inventory/reservations/",
    "adjustments": "/api/v1/inventory/adjustments/",
}

CAN_READ = {
    "catalog": {r for r in Role if r not in (Role.CUSTOMER, Role.DRIVER, Role.FINANCE)},
    "recipes": {r for r in Role if r not in (Role.CUSTOMER, Role.DRIVER, Role.FINANCE)},
    "suppliers": {Role.ADMIN, Role.PURCHASING, Role.FINANCE},
    "purchase_orders": {Role.ADMIN, Role.PURCHASING, Role.FINANCE},
    "goods_receipts": {Role.ADMIN, Role.PURCHASING, Role.FINANCE},
    "balances": {Role.ADMIN, Role.PURCHASING, Role.QUALITY, Role.PLANNER, Role.PRODUCTION},
    "lots": {Role.ADMIN, Role.PURCHASING, Role.QUALITY, Role.PLANNER, Role.PRODUCTION},
    "movements": {Role.ADMIN, Role.PURCHASING, Role.QUALITY, Role.PLANNER, Role.PRODUCTION},
    "reservations": {Role.ADMIN, Role.PURCHASING, Role.QUALITY, Role.PLANNER, Role.PRODUCTION},
}
CAN_WRITE = {
    "catalog": {Role.ADMIN},
    "recipes": {Role.ADMIN},
    "suppliers": {Role.PURCHASING},
    "purchase_orders": {Role.PURCHASING},
    "reservations": {Role.PLANNER, Role.PRODUCTION},
    "adjustments": {Role.ADMIN},
}


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("area", list(READ))
def test_read_access_by_role(client_for, role, area):
    status = client_for(role).get(READ[area]).status_code
    if role in CAN_READ[area]:
        assert status == 200, (role, area)
    else:
        assert status == 403, (role, area)


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("area", list(WRITE))
def test_write_access_by_role(client_for, role, area):
    status = client_for(role).post(WRITE[area], {}, format="json").status_code
    if role in CAN_WRITE[area]:
        assert status != 403, (role, area)  # allowed through; the empty body is then a 400
    else:
        assert status == 403, (role, area)


def test_a_user_without_roles_reaches_nothing_back_office(user, api_client):
    api_client.force_authenticate(user)
    for url in set(READ.values()) | set(WRITE.values()):
        assert api_client.get(url).status_code == 403, url
        assert api_client.post(url, {}, format="json").status_code in (403, 405), url


def test_permissions_are_evaluated_per_request_not_cached_on_the_user(
    client_for, make_user, api_client
):
    user = make_user("shifting@example.com", Role.PLANNER)
    api_client.force_authenticate(user)
    assert api_client.get(READ["lots"]).status_code == 200
    user.role_assignments.all().delete()
    assert api_client.get(READ["lots"]).status_code == 403

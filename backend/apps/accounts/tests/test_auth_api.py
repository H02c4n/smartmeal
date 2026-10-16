import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.db import IntegrityError
from rest_framework.test import APIClient

from apps.accounts.models import RoleAssignment
from apps.accounts.roles import Role
from apps.accounts.throttles import LoginEmailThrottle, LoginIpThrottle

pytestmark = pytest.mark.django_db

CSRF = "/api/v1/auth/csrf/"
LOGIN = "/api/v1/auth/login/"
LOGOUT = "/api/v1/auth/logout/"
ME = "/api/v1/me/"
PASSWORD = "s3cret-Pass-123"


@pytest.fixture
def browser() -> APIClient:
    """A client that enforces CSRF like a real browser."""
    return APIClient(enforce_csrf_checks=True)


def csrf_headers(client: APIClient) -> dict:
    token = client.get(CSRF).json()["csrf_token"]
    return {"HTTP_X_CSRFTOKEN": token}


def log_in(client, email="customer@example.com", password=PASSWORD):
    return client.post(
        LOGIN, {"email": email, "password": password}, format="json", **csrf_headers(client)
    )


# --- 401 for anonymous requests --------------------------------------------------------------
@pytest.mark.parametrize("url", [ME, "/api/v1/products/", "/api/v1/inventory/lots/"])
def test_anonymous_requests_get_401(api_client, url):
    response = api_client.get(url)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert response["WWW-Authenticate"] == "Session"


def test_authenticated_without_permission_is_403_not_401(api_client, user):
    api_client.force_authenticate(user)
    response = api_client.get("/api/v1/inventory/lots/")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


# --- Login / me / logout ---------------------------------------------------------------------
def test_login_me_logout_round_trip(browser, make_user):
    make_user("customer@example.com", Role.CUSTOMER, Role.SUPPORT)
    response = log_in(browser)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "customer@example.com"
    assert body["roles"] == ["CUSTOMER", "SUPPORT"]
    assert "orders:place" in body["permissions"] and "catalog:read" in body["permissions"]
    assert "password" not in body

    cookie = response.cookies["sessionid"]
    assert cookie["httponly"] and cookie["samesite"] == "Lax"

    assert browser.get(ME).json()["email"] == "customer@example.com"

    out = browser.post(LOGOUT, **csrf_headers(browser))
    assert out.status_code == 204
    assert browser.get(ME).status_code == 401


def test_login_is_case_insensitive_on_email(browser, make_user):
    make_user("customer@example.com")
    assert log_in(browser, email="  Customer@Example.COM ").status_code == 200


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("customer@example.com", "wrong-password"),
        ("nobody@example.com", PASSWORD),
        ("inactive@example.com", PASSWORD),
    ],
)
def test_every_login_failure_looks_the_same(browser, make_user, email, password):
    make_user("customer@example.com")
    make_user("inactive@example.com", is_active=False)
    response = log_in(browser, email=email, password=password)
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "AUTHENTICATION_REQUIRED"
    assert error["message"] == "Invalid email or password."
    assert "sessionid" not in response.cookies


def test_login_validates_the_body(browser):
    response = browser.post(LOGIN, {"email": "x"}, format="json", **csrf_headers(browser))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_session_key_is_rotated_on_login(browser, make_user):
    """An anonymous session id (possibly planted by an attacker) must not become the login."""
    make_user("customer@example.com")
    session = browser.session  # pre-login anonymous session
    session["planted"] = True
    session.save()
    planted_key = session.session_key
    logged_in = log_in(browser).cookies["sessionid"].value
    assert logged_in != planted_key
    assert not SessionStore(session_key=planted_key).exists(planted_key)


# --- CSRF ------------------------------------------------------------------------------------
def test_login_requires_a_csrf_token(browser, make_user):
    make_user("customer@example.com")
    response = browser.post(LOGIN, {"email": "customer@example.com", "password": PASSWORD})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    assert "CSRF" in response.json()["error"]["message"]


def test_logout_and_writes_need_csrf_for_a_session(browser, make_user):
    make_user("customer@example.com")
    log_in(browser)
    assert browser.post(LOGOUT).status_code == 403  # no token
    assert browser.get(ME).status_code == 200  # still signed in
    assert browser.post(LOGOUT, **csrf_headers(browser)).status_code == 204


def test_csrf_endpoint_is_public_and_sets_the_cookie(browser):
    response = browser.get(CSRF)
    assert response.status_code == 200
    assert response.json()["csrf_token"]
    assert "csrftoken" in response.cookies


# --- Roles in /me/ ---------------------------------------------------------------------------
def test_me_reflects_role_changes_immediately(api_client, user):
    api_client.force_authenticate(user)
    assert api_client.get(ME).json()["roles"] == []
    RoleAssignment.objects.create(user=user, role_code=Role.QUALITY)
    me = api_client.get(ME).json()
    assert me["roles"] == ["QUALITY"]
    assert "inventory:release_lot" in me["permissions"]


def test_a_role_can_be_assigned_to_a_user_only_once(user):
    RoleAssignment.objects.create(user=user, role_code=Role.PLANNER)
    with pytest.raises(IntegrityError):
        RoleAssignment.objects.create(user=user, role_code=Role.PLANNER)


# --- Rate limits -----------------------------------------------------------------------------
def test_login_attempts_per_email_are_rate_limited(browser, make_user, monkeypatch):
    monkeypatch.setitem(LoginEmailThrottle.THROTTLE_RATES, "login_email", "3/min")
    make_user("customer@example.com")
    for _ in range(3):
        assert log_in(browser, password="wrong").status_code == 401
    blocked = log_in(browser, password=PASSWORD)  # even the right password is refused now
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    assert log_in(browser, email="someone-else@example.com").status_code == 401  # other email ok


def test_login_attempts_per_address_are_rate_limited(browser, monkeypatch):
    monkeypatch.setitem(LoginIpThrottle.THROTTLE_RATES, "login_ip", "2/min")
    assert log_in(browser, email="a@example.com").status_code == 401
    assert log_in(browser, email="b@example.com").status_code == 401
    assert log_in(browser, email="c@example.com").status_code == 429

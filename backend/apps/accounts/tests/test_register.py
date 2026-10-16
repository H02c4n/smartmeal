from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.accounts.models import RoleAssignment, User
from apps.accounts.roles import Role
from apps.accounts.throttles import RegisterIpThrottle

CSRF = "/api/v1/auth/csrf/"
REGISTER = "/api/v1/auth/register/"
LOGIN = "/api/v1/auth/login/"
ME = "/api/v1/me/"
GOOD = {"email": "New.Person@Example.com", "password": "A-long-unusual-pass-7391"}

pytestmark = pytest.mark.django_db


@pytest.fixture
def browser() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


def register(client, body=None, **extra):
    token = client.get(CSRF).json()["csrf_token"]
    return client.post(
        REGISTER, GOOD if body is None else body, format="json", HTTP_X_CSRFTOKEN=token, **extra
    )


def test_registration_creates_a_customer_and_signs_them_in(browser):
    response = register(browser, {**GOOD, "phone": "+46 70 123 45 67"})
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["email"] == "new.person@example.com"  # stored canonical
    assert body["roles"] == ["CUSTOMER"]
    assert body["permissions"] == ["orders:place"]
    assert "password" not in body
    user = User.objects.get(email="new.person@example.com")
    assert user.phone == "+46 70 123 45 67"
    assert user.check_password(GOOD["password"]) and user.is_active
    assert not (user.is_staff or user.is_superuser)
    assert response.cookies["sessionid"]["httponly"]
    assert browser.get(ME).json()["email"] == "new.person@example.com"  # signed in


def test_a_new_customer_can_use_the_address_book(browser):
    register(browser)
    token = browser.get(CSRF).json()["csrf_token"]
    created = browser.post(
        "/api/v1/me/addresses/",
        {
            "recipient_name": "New Person",
            "line1": "Storgatan 1",
            "postal_code": "11122",
            "city": "Stockholm",
            "country_code": "SE",
        },
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert created.status_code == 201


def test_the_body_can_never_choose_roles_or_flags(browser):
    response = register(
        browser, {**GOOD, "roles": ["ADMIN"], "is_staff": True, "is_superuser": True}
    )
    assert response.status_code == 201
    user = User.objects.get(email="new.person@example.com")
    assert not (user.is_staff or user.is_superuser)
    assert list(user.role_assignments.values_list("role_code", flat=True)) == [Role.CUSTOMER]


def test_duplicate_email_is_refused_case_insensitively(browser, make_user):
    make_user("taken@example.com", Role.CUSTOMER)
    response = register(browser, {**GOOD, "email": "  TAKEN@example.com "})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "email" in error["details"]
    assert User.objects.filter(email="taken@example.com").count() == 1


@pytest.mark.parametrize(
    ("password", "message_part"),
    [
        ("short1", "too short"),
        ("password123456", "too common"),
        ("1234567890123", "entirely numeric"),
        ("new.person@example.com", "too similar"),
    ],
)
def test_weak_passwords_are_refused(browser, password, message_part):
    response = register(browser, {**GOOD, "password": password})
    assert response.status_code == 400
    messages = " ".join(response.json()["error"]["details"]["password"])
    assert message_part in messages
    assert not User.objects.exists()


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "password": GOOD["password"]},
        {"password": GOOD["password"]},
        {"email": "ok@example.com"},
        {**GOOD, "phone": "abc"},
    ],
)
def test_invalid_input_is_a_400_and_creates_nothing(browser, body):
    assert register(browser, body).status_code == 400
    assert not User.objects.exists()


def test_registration_needs_a_csrf_token(browser):
    response = browser.post(REGISTER, GOOD, format="json")
    assert response.status_code == 403
    assert "CSRF" in response.json()["error"]["message"]
    assert not User.objects.exists()


def test_an_already_signed_in_user_cannot_register_again(browser, make_user):
    make_user("me@example.com", Role.CUSTOMER)
    token = browser.get(CSRF).json()["csrf_token"]
    browser.post(
        LOGIN,
        {"email": "me@example.com", "password": "s3cret-Pass-123"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    response = register(browser, {**GOOD, "email": "second@example.com"})
    assert response.status_code == 409
    assert not User.objects.filter(email="second@example.com").exists()


def test_registration_is_rate_limited_per_address(browser, monkeypatch):
    monkeypatch.setitem(RegisterIpThrottle.THROTTLE_RATES, "register_ip", "2/hour")
    for n in range(2):
        assert register(browser, {**GOOD, "email": f"p{n}@example.com"}).status_code == 201
        browser.cookies.clear()
    blocked = register(browser, {**GOOD, "email": "p3@example.com"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_parallel_registrations_of_one_address_create_one_account(monkeypatch):
    monkeypatch.setitem(RegisterIpThrottle.THROTTLE_RATES, "register_ip", "100/hour")

    def attempt(_):
        client = APIClient()
        try:
            token = client.get(CSRF).json()["csrf_token"]
            return client.post(
                REGISTER,
                {"email": "race@example.com", "password": GOOD["password"]},
                format="json",
                HTTP_X_CSRFTOKEN=token,
            ).status_code
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(attempt, range(6)))
    assert codes.count(201) == 1 and codes.count(400) == 5, codes
    assert User.objects.filter(email="race@example.com").count() == 1
    assert RoleAssignment.objects.filter(user__email="race@example.com").count() == 1

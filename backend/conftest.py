import itertools

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import RoleAssignment, User
from apps.accounts.roles import Role

ALL_BACK_OFFICE_ROLES = (Role.ADMIN, Role.PURCHASING, Role.PLANNER, Role.QUALITY)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Throttle counters live in the cache; start every test with a clean slate."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def make_user(db):
    """``make_user(email, *roles, **extra)`` -> User holding the given roles."""

    def _make(email: str, *roles: str, **extra) -> User:
        user = User.objects.create_user(email, "s3cret-Pass-123", **extra)
        for role in roles:
            RoleAssignment.objects.create(user=user, role_code=role)
        return user

    return _make


@pytest.fixture
def client_for(make_user):
    """``client_for(Role.PLANNER, ...)`` -> API client signed in as a new user with those roles."""
    counter = itertools.count(1)

    def _client(*roles: str) -> APIClient:
        client = APIClient()
        client.force_authenticate(make_user(f"role-user-{next(counter)}@example.com", *roles))
        return client

    return _client


@pytest.fixture
def user(db) -> User:
    """A signed-up person without any business role (e.g. a customer before Phase 3)."""
    return User.objects.create_user("customer@example.com", "s3cret-Pass-123")


@pytest.fixture
def staff_user(make_user) -> User:
    """A back-office actor holding every back-office role (all permissions except order ones).

    Tests that check *denial* use ``client_for(<single role>)`` instead.
    """
    return make_user("staff@example.com", *ALL_BACK_OFFICE_ROLES, is_staff=True)


@pytest.fixture
def superuser(db) -> User:
    return User.objects.create_superuser("root@example.com", "s3cret-Pass-123")

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user("customer@example.com", "s3cret-Pass-123")


@pytest.fixture
def staff_user(db) -> User:
    return User.objects.create_user("staff@example.com", "s3cret-Pass-123", is_staff=True)


@pytest.fixture
def superuser(db) -> User:
    return User.objects.create_superuser("root@example.com", "s3cret-Pass-123")

import uuid

import pytest
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, transaction
from django.db.models.functions import Lower

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_auth_user_model_is_accounts_user():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model() is User


def test_create_user_defaults():
    user = User.objects.create_user("a@example.com", "pw-12345-xyz")
    assert isinstance(user.id, uuid.UUID)
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.phone == ""
    assert user.created_at is not None
    assert user.updated_at is not None


def test_password_is_hashed_not_stored_plain():
    user = User.objects.create_user("a@example.com", "pw-12345-xyz")
    assert user.password != "pw-12345-xyz"
    assert user.check_password("pw-12345-xyz")


def test_create_user_without_password_has_unusable_password():
    user = User.objects.create_user("a@example.com")
    assert user.has_usable_password() is False


def test_email_is_normalised_to_lowercase():
    user = User.objects.create_user("  Mixed.Case@Example.COM ", "pw-12345-xyz")
    assert user.email == "mixed.case@example.com"


def test_email_is_required():
    with pytest.raises(ValueError):
        User.objects.create_user("", "pw-12345-xyz")
    with pytest.raises(ValueError):
        User.objects.create_user("   ", "pw-12345-xyz")


def test_email_uniqueness_is_case_insensitive():
    User.objects.create_user("dup@example.com", "pw-12345-xyz")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("DUP@example.com", "pw-12345-xyz")


def test_database_rejects_non_lowercase_email_even_via_queryset_update():
    user = User.objects.create_user("a@example.com", "pw-12345-xyz")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(pk=user.pk).update(email="A@Example.com")


def test_save_normalises_email_set_directly():
    user = User(email="Direct@Example.com")
    user.set_password("pw-12345-xyz")
    user.save()
    assert User.objects.filter(email=Lower("email")).filter(pk=user.pk).exists()
    assert user.email == "direct@example.com"


def test_create_superuser_flags():
    admin = User.objects.create_superuser("root@example.com", "pw-12345-xyz")
    assert admin.is_staff is True
    assert admin.is_superuser is True


@pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
def test_create_superuser_rejects_false_flags(flag):
    with pytest.raises(ValueError):
        User.objects.create_superuser("root@example.com", "pw-12345-xyz", **{flag: False})


def test_authenticate_with_email_is_case_insensitive():
    User.objects.create_user("login@example.com", "pw-12345-xyz")
    assert authenticate(username="LOGIN@example.com", password="pw-12345-xyz") is not None
    assert authenticate(username="login@example.com", password="wrong") is None


def test_inactive_user_cannot_authenticate():
    User.objects.create_user("gone@example.com", "pw-12345-xyz", is_active=False)
    assert authenticate(username="gone@example.com", password="pw-12345-xyz") is None


def test_str_is_email():
    assert str(User(email="x@example.com")) == "x@example.com"

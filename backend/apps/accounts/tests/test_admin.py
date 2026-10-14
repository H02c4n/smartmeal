import pytest
from django.urls import reverse

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_superuser_can_open_user_changelist_and_change_pages(client, superuser):
    client.force_login(superuser)
    assert client.get(reverse("admin:accounts_user_changelist")).status_code == 200
    assert client.get(reverse("admin:accounts_user_change", args=[superuser.pk])).status_code == 200


def test_superuser_can_create_user_via_admin_add_form(client, superuser):
    client.force_login(superuser)
    url = reverse("admin:accounts_user_add")
    assert client.get(url).status_code == 200

    response = client.post(
        url,
        {
            "email": "Created@Example.com",
            "phone": "+46700000000",
            "usable_password": "true",
            "password1": "an-Unusual-pass-9731",
            "password2": "an-Unusual-pass-9731",
        },
    )
    assert response.status_code == 302, getattr(response, "context", None)
    created = User.objects.get(email="created@example.com")
    assert created.phone == "+46700000000"
    assert created.check_password("an-Unusual-pass-9731")


def test_regular_user_cannot_use_admin(client, user):
    client.force_login(user)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 302  # redirected to admin login

import pytest
from django.db import OperationalError
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_health_ok_without_authentication(api_client):
    response = api_client.get(reverse("api-v1:health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_path_is_under_api_v1(api_client):
    assert reverse("api-v1:health") == "/api/v1/health/"


def test_health_reports_503_when_database_is_down(api_client, monkeypatch):
    from apps.core import views

    class BrokenConnection:
        def cursor(self):
            raise OperationalError("db down")

    monkeypatch.setattr(views, "connection", BrokenConnection())
    response = api_client.get(reverse("api-v1:health"))
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}

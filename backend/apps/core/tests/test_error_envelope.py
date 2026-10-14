import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions

from apps.core.exceptions import api_exception_handler

pytestmark = pytest.mark.django_db

# IsAdminUser outside local settings -> a real protected endpoint. Its responses use the OpenAPI
# renderer, so assertions read response.data instead of response.json().
SCHEMA_URL = "/api/v1/schema/"


def test_anonymous_gets_authentication_required_envelope(api_client):
    response = api_client.get(SCHEMA_URL, HTTP_X_REQUEST_ID="req-for-error-1")
    assert response.status_code in (401, 403)
    error = response.data["error"]
    assert error["code"] == "AUTHENTICATION_REQUIRED"
    assert error["request_id"] == "req-for-error-1"
    assert error["request_id"] == response["X-Request-ID"]
    assert isinstance(error["message"], str) and error["message"]
    assert "details" not in error


def test_non_staff_gets_permission_denied_envelope(api_client, user):
    api_client.force_authenticate(user)
    response = api_client.get(SCHEMA_URL)
    assert response.status_code == 403
    assert response.data["error"]["code"] == "PERMISSION_DENIED"


def test_staff_can_read_schema_outside_local(api_client, staff_user):
    api_client.force_authenticate(staff_user)
    response = api_client.get(SCHEMA_URL)
    assert response.status_code == 200


def test_unknown_api_path_is_not_an_html_500(api_client):
    response = api_client.get("/api/v1/does-not-exist/")
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (exceptions.ValidationError({"email": ["Required."]}), 400, "VALIDATION_ERROR"),
        (exceptions.ParseError(), 400, "VALIDATION_ERROR"),
        (exceptions.NotAuthenticated(), 401, "AUTHENTICATION_REQUIRED"),
        (exceptions.PermissionDenied(), 403, "PERMISSION_DENIED"),
        (DjangoPermissionDenied(), 403, "PERMISSION_DENIED"),
        (exceptions.NotFound(), 404, "RESOURCE_NOT_FOUND"),
        (Http404(), 404, "RESOURCE_NOT_FOUND"),
        (exceptions.Throttled(), 429, "RATE_LIMITED"),
        (exceptions.MethodNotAllowed("PUT"), 405, "METHOD_NOT_ALLOWED"),
    ],
)
def test_handler_maps_exceptions_to_contract_codes(exc, status, code):
    response = api_exception_handler(exc, {})
    assert response.status_code == status
    assert response.data["error"]["code"] == code
    assert set(response.data["error"]) >= {"code", "message", "request_id"}


def test_validation_error_exposes_field_details():
    response = api_exception_handler(exceptions.ValidationError({"email": ["Required."]}), {})
    error = response.data["error"]
    assert error["message"] == "Validation failed."
    assert error["details"] == {"email": ["Required."]}


def test_non_api_exception_is_left_to_django():
    assert api_exception_handler(RuntimeError("boom"), {}) is None

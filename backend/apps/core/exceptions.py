"""API error envelope (03_API_CONTRACTS §1, §2, §5).

Every error response has the shape::

    {"error": {"code": "...", "message": "...", "details": {...}, "request_id": "..."}}

``details`` is present only when there is something to say (e.g. field errors).
"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.views import exception_handler as drf_exception_handler

from .request_id import get_request_id


def _error_code(exc: Exception) -> str:
    if isinstance(exc, Http404 | exceptions.NotFound):
        return "RESOURCE_NOT_FOUND"
    if isinstance(exc, DjangoPermissionDenied | exceptions.PermissionDenied):
        return "PERMISSION_DENIED"
    if isinstance(exc, exceptions.NotAuthenticated | exceptions.AuthenticationFailed):
        return "AUTHENTICATION_REQUIRED"
    if isinstance(exc, exceptions.ValidationError | exceptions.ParseError):
        return "VALIDATION_ERROR"
    if isinstance(exc, exceptions.Throttled):
        return "RATE_LIMITED"
    if isinstance(exc, exceptions.APIException):
        return str(exc.default_code).upper()
    return "ERROR"


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> Django's normal 500 handling

    code = _error_code(exc)
    body: dict = {"code": code, "request_id": get_request_id()}

    if isinstance(exc, exceptions.ValidationError):
        body["message"] = "Validation failed."
        body["details"] = response.data
    else:
        data = response.data
        detail = data.get("detail") if isinstance(data, dict) else None
        body["message"] = str(detail) if detail else "Request could not be processed."

    response.data = {"error": body}
    return response

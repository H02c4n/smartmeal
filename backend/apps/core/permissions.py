"""Shared permission building blocks (ADR-013).

Role-based and deny-by-default: access comes only from the fixed role -> permission table in
``apps.accounts.roles``. ``is_staff`` and Django model permissions play no part in API
authorisation any more (``is_staff`` only opens the Django admin).

Object/ownership scope (a customer's own orders, a courier's assigned stops) is NOT decided
here; the owning module narrows its queryset or adds an object-level check.
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.roles import permissions_for_roles

_CACHE_ATTR = "_smartmeal_permissions"


def user_permissions(request) -> frozenset[str]:
    """Permissions granted by the requester's roles (one query per request, then cached)."""
    cached = getattr(request, _CACHE_ATTR, None)
    if cached is None:
        user = request.user
        if not (user and user.is_authenticated):
            cached = frozenset()
        else:
            cached = permissions_for_roles(
                user.role_assignments.values_list("role_code", flat=True)
            )
        setattr(request, _CACHE_ATTR, cached)
    return cached


def has_permission(code: str) -> type[BasePermission]:
    """Permission class: authenticated user whose roles grant ``code``."""

    class _HasPermission(BasePermission):
        message = f"This action requires the '{code}' permission."

        def has_permission(self, request, view) -> bool:
            return code in user_permissions(request)

    _HasPermission.__name__ = f"Has_{code.replace(':', '_')}"
    return _HasPermission


def has_permission_by_method(*, read: str, write: str) -> type[BasePermission]:
    """``read`` for GET/HEAD/OPTIONS, ``write`` for every other method."""

    class _ByMethod(BasePermission):
        def has_permission(self, request, view) -> bool:
            required = read if request.method in SAFE_METHODS else write
            return required in user_permissions(request)

        @property
        def message(self) -> str:
            return f"This action requires the '{read}' or '{write}' permission."

    _ByMethod.__name__ = f"ByMethod_{read.replace(':', '_')}_{write.replace(':', '_')}"
    return _ByMethod

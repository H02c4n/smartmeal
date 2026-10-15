"""Shared permission building blocks.

PLACEHOLDER (ADR-009/010): business roles (``RoleAssignment``) and the auth strategy are not
decided yet. Until then back-office endpoints require ``is_staff`` and, for the sensitive
operations 05 §1 reserves for special permission (stock adjustment, lot release/block, receipt
reversal), an explicit Django model permission granted by an administrator. Superusers hold
every permission. Replace these with role-based permissions once roles exist.
"""

from rest_framework.permissions import BasePermission, IsAdminUser


class IsBackOfficeStaff(IsAdminUser):
    """Authenticated ``is_staff`` user (placeholder for a role check)."""


def staff_with_permission(codename: str) -> type[BasePermission]:
    """Permission class: staff user holding the Django permission ``app_label.codename``."""

    class _StaffWithPermission(BasePermission):
        message = f"This action requires the '{codename}' permission."

        def has_permission(self, request, view) -> bool:
            user = request.user
            return bool(
                user and user.is_authenticated and user.is_staff and user.has_perm(codename)
            )

    _StaffWithPermission.__name__ = f"StaffWith_{codename.replace('.', '_')}"
    return _StaffWithPermission

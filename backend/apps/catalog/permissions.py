from rest_framework.permissions import IsAdminUser


class IsCatalogAdmin(IsAdminUser):
    """May manage catalog master data.

    PLACEHOLDER: roles (``RoleAssignment``) do not exist yet and the auth strategy is still an
    open decision (ADR-009/ADR-010), so this falls back to ``is_staff``. ``is_staff`` is meant
    for the Django admin only; replace this class with a role-based permission as soon as roles
    exist. Every catalog write endpoint goes through this single class on purpose.
    """

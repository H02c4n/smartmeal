from apps.accounts.roles import Perm
from apps.core.permissions import has_permission_by_method


class IsCatalogAdmin(has_permission_by_method(read=Perm.CATALOG_READ, write=Perm.CATALOG_MANAGE)):
    """Back-office catalog and recipe endpoints (ADR-013).

    Reading needs ``catalog:read`` (most operational roles); every write needs
    ``catalog:manage`` (``ADMIN``). Every catalog/recipe back-office endpoint goes through this
    single class on purpose. The name is kept from the placeholder era.
    """

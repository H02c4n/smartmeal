"""Roles and the fixed role -> permission table (ADR-013 §4-5).

Pure data and pure functions: no model imports, so any module may import this safely.

* Permissions are action codes (``"inventory:adjust_stock"``), not Django model permissions.
* The table is code, not data: it is not editable from any screen and is pinned by
  ``accounts/tests/test_roles.py``. Anything not listed is denied (05_SECURITY §1).
* A role alone is not enough for customer/courier data: object scope (own orders, assigned
  deliveries) is checked separately by the owning module's queryset/permission.
"""

from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType

from django.db import models


class Role(models.TextChoices):
    CUSTOMER = "CUSTOMER"
    ADMIN = "ADMIN"
    PLANNER = "PLANNER"
    PURCHASING = "PURCHASING"
    PRODUCTION = "PRODUCTION"
    QUALITY = "QUALITY"
    PACKING = "PACKING"
    DRIVER = "DRIVER"
    SUPPORT = "SUPPORT"
    FINANCE = "FINANCE"


class Perm:
    """Permission codes. Read and write are separate on purpose (least privilege)."""

    CATALOG_READ = "catalog:read"  # products, ingredients, allergens, recipes (back-office view)
    CATALOG_MANAGE = "catalog:manage"  # create/edit/(de)activate catalog data, recipe lifecycle

    PURCHASING_READ = "purchasing:read"
    PURCHASING_MANAGE = "purchasing:manage"  # suppliers, purchase orders, goods receipts
    PURCHASING_REVERSE_RECEIPT = "purchasing:reverse_receipt"

    INVENTORY_READ = "inventory:read"  # balances, lots, movements, reservations
    INVENTORY_RESERVE = "inventory:reserve"  # reservations and consumption
    INVENTORY_RELEASE_LOT = "inventory:release_lot"  # quality release (pending/blocked -> released)
    INVENTORY_BLOCK_LOT = "inventory:block_lot"
    INVENTORY_ADJUST_STOCK = "inventory:adjust_stock"  # adjustments and movement reversals

    ORDERS_PLACE = "orders:place"  # a customer creating/cancelling their OWN orders
    ORDERS_READ_ALL = "orders:read_all"  # every customer's orders (back-office)
    ORDERS_CANCEL_ANY = "orders:cancel_any"


ALL_PERMISSIONS: frozenset[str] = frozenset(
    value for name, value in vars(Perm).items() if not name.startswith("_")
)

# The approved table (product owner, 2026-10-15) plus the read access and the remaining roles
# chosen under least privilege. ADMIN is deliberately NOT a super-role: it holds what the table
# gives it and read access; role changes are the control for anything more.
_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.ADMIN: frozenset(
        {
            Perm.CATALOG_READ,
            Perm.CATALOG_MANAGE,
            Perm.PURCHASING_READ,
            Perm.PURCHASING_REVERSE_RECEIPT,
            Perm.INVENTORY_READ,
            Perm.INVENTORY_ADJUST_STOCK,
            Perm.ORDERS_READ_ALL,
            Perm.ORDERS_CANCEL_ANY,
        }
    ),
    Role.PURCHASING: frozenset(
        {
            Perm.CATALOG_READ,
            Perm.PURCHASING_READ,
            Perm.PURCHASING_MANAGE,
            Perm.INVENTORY_READ,
        }
    ),
    Role.QUALITY: frozenset(
        {
            Perm.CATALOG_READ,
            Perm.INVENTORY_READ,
            Perm.INVENTORY_RELEASE_LOT,
            Perm.INVENTORY_BLOCK_LOT,
        }
    ),
    Role.PLANNER: frozenset(
        {
            Perm.CATALOG_READ,
            Perm.INVENTORY_READ,
            Perm.INVENTORY_RESERVE,
            Perm.ORDERS_READ_ALL,
        }
    ),
    Role.PRODUCTION: frozenset(
        {
            Perm.CATALOG_READ,
            Perm.INVENTORY_READ,
            Perm.INVENTORY_RESERVE,
            Perm.ORDERS_READ_ALL,
        }
    ),
    Role.PACKING: frozenset({Perm.CATALOG_READ, Perm.ORDERS_READ_ALL}),
    Role.SUPPORT: frozenset({Perm.CATALOG_READ, Perm.ORDERS_READ_ALL, Perm.ORDERS_CANCEL_ANY}),
    Role.FINANCE: frozenset({Perm.PURCHASING_READ, Perm.ORDERS_READ_ALL}),
    Role.DRIVER: frozenset(),  # courier access is object-scoped (assigned deliveries), Phase 6
    Role.CUSTOMER: frozenset({Perm.ORDERS_PLACE}),
}

ROLE_PERMISSIONS = MappingProxyType(_ROLE_PERMISSIONS)


def permissions_for_roles(role_codes: Iterable[str]) -> frozenset[str]:
    """Union of the permissions of the given roles; unknown role codes grant nothing."""
    granted: set[str] = set()
    for code in role_codes:
        granted |= ROLE_PERMISSIONS.get(code, frozenset())
    return frozenset(granted)

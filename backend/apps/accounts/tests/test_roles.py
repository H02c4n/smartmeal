"""The role -> permission table is a contract: any change here must be a deliberate edit."""

import pytest

from apps.accounts.roles import ALL_PERMISSIONS, ROLE_PERMISSIONS, Perm, Role, permissions_for_roles

EXPECTED = {
    Role.ADMIN: {
        Perm.CATALOG_READ,
        Perm.CATALOG_MANAGE,
        Perm.PURCHASING_READ,
        Perm.PURCHASING_REVERSE_RECEIPT,
        Perm.INVENTORY_READ,
        Perm.INVENTORY_ADJUST_STOCK,
        Perm.ORDERS_READ_ALL,
        Perm.ORDERS_CANCEL_ANY,
    },
    Role.PURCHASING: {
        Perm.CATALOG_READ,
        Perm.PURCHASING_READ,
        Perm.PURCHASING_MANAGE,
        Perm.INVENTORY_READ,
    },
    Role.QUALITY: {
        Perm.CATALOG_READ,
        Perm.INVENTORY_READ,
        Perm.INVENTORY_RELEASE_LOT,
        Perm.INVENTORY_BLOCK_LOT,
    },
    Role.PLANNER: {
        Perm.CATALOG_READ,
        Perm.INVENTORY_READ,
        Perm.INVENTORY_RESERVE,
        Perm.ORDERS_READ_ALL,
    },
    Role.PRODUCTION: {
        Perm.CATALOG_READ,
        Perm.INVENTORY_READ,
        Perm.INVENTORY_RESERVE,
        Perm.ORDERS_READ_ALL,
    },
    Role.PACKING: {Perm.CATALOG_READ, Perm.ORDERS_READ_ALL},
    Role.SUPPORT: {Perm.CATALOG_READ, Perm.ORDERS_READ_ALL, Perm.ORDERS_CANCEL_ANY},
    Role.FINANCE: {Perm.PURCHASING_READ, Perm.ORDERS_READ_ALL},
    Role.DRIVER: set(),
    Role.CUSTOMER: {Perm.ORDERS_PLACE},
}


def test_every_role_is_in_the_table_and_nothing_else():
    assert set(ROLE_PERMISSIONS) == set(Role.values) == set(EXPECTED)


@pytest.mark.parametrize("role", list(Role))
def test_role_grants_exactly_the_approved_permissions(role):
    assert ROLE_PERMISSIONS[role] == EXPECTED[role]


def test_table_only_uses_defined_permissions():
    used = set().union(*ROLE_PERMISSIONS.values())
    assert used <= ALL_PERMISSIONS
    assert ALL_PERMISSIONS - used == set(), "a permission no role holds is dead code"


def test_approved_owner_table_rows():
    """The product owner's approved rows (2026-10-15), role by role."""
    holders = {
        permission: {r for r, granted in ROLE_PERMISSIONS.items() if permission in granted}
        for permission in ALL_PERMISSIONS
    }
    assert holders[Perm.CATALOG_MANAGE] == {Role.ADMIN}
    assert holders[Perm.PURCHASING_MANAGE] == {Role.PURCHASING}
    assert holders[Perm.INVENTORY_RELEASE_LOT] == {Role.QUALITY}
    assert holders[Perm.INVENTORY_BLOCK_LOT] == {Role.QUALITY}
    assert holders[Perm.INVENTORY_ADJUST_STOCK] == {Role.ADMIN}
    assert holders[Perm.PURCHASING_REVERSE_RECEIPT] == {Role.ADMIN}
    assert holders[Perm.INVENTORY_RESERVE] == {Role.PLANNER, Role.PRODUCTION}


def test_table_is_immutable_and_unknown_roles_grant_nothing():
    with pytest.raises(TypeError):
        ROLE_PERMISSIONS["ADMIN"] = frozenset()  # type: ignore[index]
    assert permissions_for_roles(["NOT_A_ROLE"]) == frozenset()
    assert permissions_for_roles([]) == frozenset()


def test_roles_combine_as_a_union():
    combined = permissions_for_roles([Role.QUALITY, Role.PLANNER])
    assert combined == ROLE_PERMISSIONS[Role.QUALITY] | ROLE_PERMISSIONS[Role.PLANNER]

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.tests.conftest import (  # noqa: F401
    egg,
    flour,
    gram,
    kilogram,
    litre,
    milk,
    millilitre,
    piece,
    product,
    units,
)
from apps.inventory import services as inventory_services
from apps.purchasing import services as purchasing_services
from apps.purchasing.models import Supplier
from apps.purchasing.services import POLineInput, ReceiptLineInput


@pytest.fixture
def supplier(db) -> Supplier:
    return purchasing_services.create_supplier(name="Fresh Farms AB")


@pytest.fixture
def today():
    return timezone.localdate()


@pytest.fixture
def submitted_po(supplier, flour, gram, kilogram, staff_user):
    """Order for 100 kg flour (= 100 000 g)."""
    po = purchasing_services.create_purchase_order(
        supplier=supplier,
        currency="SEK",
        created_by=staff_user,
        lines=[POLineInput(flour, Decimal("100"), kilogram, Decimal("12.5"))],
    )
    return purchasing_services.submit_purchase_order(po)


@pytest.fixture
def receive(submitted_po, staff_user, kilogram, today):
    """Receive flour lots: ``receive(kg, lot_code, days_to_expiry)`` -> InventoryLot."""

    def _receive(quantity, lot_code="SUP-1", days=30, po=None):
        po = po or submitted_po
        receipt = purchasing_services.post_goods_receipt(
            purchase_order=po,
            actor=staff_user,
            lines=[
                ReceiptLineInput(
                    po.lines.get(),
                    Decimal(quantity),
                    kilogram,
                    lot_code,
                    today + timedelta(days=days),
                )
            ],
        )
        return receipt.lines.get().lot

    return _receive


@pytest.fixture
def make_released_lot(receive, staff_user):
    """Create and release a flour lot holding ``kg`` kilograms (base unit g)."""

    def _make(quantity, lot_code, days=30):
        lot = receive(quantity, lot_code, days)
        return inventory_services.release_lot(lot, actor=staff_user, reason="QC passed")

    return _make


@pytest.fixture
def staff_client(api_client, staff_user):
    api_client.force_authenticate(staff_user)
    return api_client


@pytest.fixture
def grant(staff_user):
    """Grant Django permissions (``'inventory.adjust_stock'``...) to the staff user."""
    from django.contrib.auth.models import Permission

    from apps.accounts.models import User

    def _grant(*codes, user=None):
        user = user or staff_user
        for code in codes:
            app_label, codename = code.split(".")
            user.user_permissions.add(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )
        return User.objects.get(pk=user.pk)  # drop the cached permission set

    return _grant

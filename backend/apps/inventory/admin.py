"""Django admin: read-only inspection of stock (developer tool, ADR-003).

Lots, ledger and reservations are written only by ``inventory.services``; the admin must not
be a back door around the ledger, the quality log or the stock invariants.
"""

from django.contrib import admin

from .models import InventoryLot, LotQualityEvent, StockMovement, StockReservation


class _ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InventoryLot)
class InventoryLotAdmin(_ReadOnly):
    list_display = ("internal_lot_code", "ingredient", "quality_status", "expiry_date", "on_hand")
    list_filter = ("quality_status",)
    search_fields = ("internal_lot_code", "supplier_lot_code", "ingredient__sku")


@admin.register(StockMovement)
class StockMovementAdmin(_ReadOnly):
    list_display = ("lot", "movement_type", "quantity_delta", "occurred_at")
    list_filter = ("movement_type",)


@admin.register(StockReservation)
class StockReservationAdmin(_ReadOnly):
    list_display = ("lot", "quantity", "status", "reference_type", "reference_id")
    list_filter = ("status",)


@admin.register(LotQualityEvent)
class LotQualityEventAdmin(_ReadOnly):
    list_display = ("lot", "from_status", "to_status", "actor", "created_at")

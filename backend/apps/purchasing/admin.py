"""Django admin: read-only inspection (developer tool, ADR-003).

Orders and receipts change only through ``purchasing.services`` (state machine, lots, ledger).
Suppliers are editable here but not deletable.
"""

from django.contrib import admin

from .models import GoodsReceipt, PurchaseOrder, Supplier


class _ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(_ReadOnly):
    list_display = ("po_number", "supplier", "status", "currency", "ordered_at")
    list_filter = ("status",)
    search_fields = ("po_number", "supplier__name")


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(_ReadOnly):
    list_display = ("id", "purchase_order", "status", "received_at")
    list_filter = ("status",)

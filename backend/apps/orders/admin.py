"""Django admin: read-only inspection of orders (developer tool, ADR-003).

Orders change only through ``orders.services`` (state machine, reservations, event log).
"""

from django.contrib import admin

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "customer", "status", "delivery_date", "total_amount")
    list_filter = ("status",)
    search_fields = ("order_number", "customer__email")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

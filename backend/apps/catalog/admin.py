"""Django admin: developer/back-office tool only (the product admin is the Next.js app, ADR-003).

Catalog items cannot be deleted here; deactivate them instead. SKU and an ingredient's base
unit become read-only after creation, and the unit dictionary is read-only (change it by
migration).
"""

from django.contrib import admin

from .models import Ingredient, IngredientUnitConversion, Product, Unit


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "dimension", "factor_to_base")
    list_filter = ("dimension",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class IngredientUnitConversionInline(admin.TabularInline):
    model = IngredientUnitConversion
    extra = 0
    can_delete = False


class _CatalogItemAdmin(admin.ModelAdmin):
    search_fields = ("sku", "name")
    list_filter = ("is_active",)
    base_readonly_fields = ("id", "created_at", "updated_at")
    immutable_after_create: tuple[str, ...] = ("sku",)

    def get_readonly_fields(self, request, obj=None):
        if obj is not None:
            return (*self.base_readonly_fields, *self.immutable_after_create)
        return self.base_readonly_fields

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Ingredient)
class IngredientAdmin(_CatalogItemAdmin):
    list_display = ("sku", "name", "base_unit", "is_active")
    immutable_after_create = ("sku", "base_unit")
    inlines = [IngredientUnitConversionInline]


@admin.register(Product)
class ProductAdmin(_CatalogItemAdmin):
    list_display = ("sku", "name", "price", "currency", "is_active")

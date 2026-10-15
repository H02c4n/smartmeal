"""Django admin: read-only inspection of recipes (developer tool, ADR-003).

Recipes are created, edited and approved only through ``recipes.services`` (the API), so the
admin cannot bypass the draft/approved state machine or the frozen quantities.
"""

from django.contrib import admin

from .models import RecipeLine, RecipeVersion


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RecipeLineInline(admin.TabularInline):
    model = RecipeLine
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RecipeVersion)
class RecipeVersionAdmin(_ReadOnlyAdmin):
    list_display = ("product", "version_number", "status", "effective_from", "effective_to")
    list_filter = ("status",)
    search_fields = ("product__sku", "product__name")
    inlines = [RecipeLineInline]

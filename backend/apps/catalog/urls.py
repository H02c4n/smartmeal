from rest_framework.routers import SimpleRouter

from .views import (
    AdminAllergenViewSet,
    AdminIngredientViewSet,
    AdminProductViewSet,
    AdminUnitViewSet,
    ProductViewSet,
)

router = SimpleRouter()
router.register("products", ProductViewSet, basename="product")
router.register("admin/products", AdminProductViewSet, basename="admin-product")
router.register("admin/ingredients", AdminIngredientViewSet, basename="admin-ingredient")
router.register("admin/allergens", AdminAllergenViewSet, basename="admin-allergen")
router.register("admin/units", AdminUnitViewSet, basename="admin-unit")

urlpatterns = router.urls

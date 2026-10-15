from rest_framework.routers import SimpleRouter

from .views import AdminRecipeVersionViewSet

router = SimpleRouter()
router.register("admin/recipe-versions", AdminRecipeVersionViewSet, basename="admin-recipe-version")

urlpatterns = router.urls

from rest_framework.routers import SimpleRouter

from .views import AddressViewSet, OrderViewSet

router = SimpleRouter()
router.register("orders", OrderViewSet, basename="order")
router.register("me/addresses", AddressViewSet, basename="address")

urlpatterns = router.urls

from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AdjustmentView, BalanceView, LotViewSet, MovementViewSet, ReservationViewSet

router = SimpleRouter()
router.register("inventory/lots", LotViewSet, basename="inventory-lot")
router.register("inventory/movements", MovementViewSet, basename="inventory-movement")
router.register("inventory/reservations", ReservationViewSet, basename="inventory-reservation")

urlpatterns = [
    path("inventory/balances/", BalanceView.as_view(), name="inventory-balances"),
    path("inventory/adjustments/", AdjustmentView.as_view(), name="inventory-adjustments"),
    *router.urls,
]

from rest_framework.routers import SimpleRouter

from .views import GoodsReceiptViewSet, PurchaseOrderViewSet, SupplierViewSet

router = SimpleRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("goods-receipts", GoodsReceiptViewSet, basename="goods-receipt")

urlpatterns = router.urls

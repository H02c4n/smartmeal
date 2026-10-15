"""Read queries for purchasing."""

from django.db.models import QuerySet

from .models import GoodsReceipt, PurchaseOrder, Supplier


def suppliers(*, q: str | None = None) -> QuerySet[Supplier]:
    queryset = Supplier.objects.all()
    q = (q or "").strip()
    return queryset.filter(name__icontains=q) if q else queryset


def purchase_orders(*, status: str | None = None) -> QuerySet[PurchaseOrder]:
    queryset = PurchaseOrder.objects.select_related("supplier").prefetch_related(
        "lines__ingredient__base_unit", "lines__unit"
    )
    return queryset.filter(status=status) if status else queryset


def goods_receipts(*, purchase_order_id=None, status: str | None = None) -> QuerySet[GoodsReceipt]:
    queryset = GoodsReceipt.objects.prefetch_related(
        "lines__ingredient", "lines__unit", "lines__lot"
    )
    if purchase_order_id:
        queryset = queryset.filter(purchase_order_id=purchase_order_id)
    if status:
        queryset = queryset.filter(status=status)
    return queryset

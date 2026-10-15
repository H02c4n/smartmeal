"""Read queries for inventory: stock levels, lots, ledger and reconciliation (05 §2)."""

from datetime import date
from decimal import Decimal

from django.db.models import DecimalField, F, OuterRef, Q, QuerySet, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import InventoryLot, StockMovement, StockReservation

ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=4))


def usable_lot_filter(today: date | None = None) -> Q:
    """Lots whose free stock counts as available: released and not past expiry."""
    return Q(
        quality_status=InventoryLot.QualityStatus.RELEASED,
        expiry_date__gte=today or timezone.localdate(),
    )


def stock_levels(*, ingredient_sku: str | None = None, today: date | None = None) -> QuerySet:
    """Per ingredient, in its base unit. One definition for every module (05 §2)::

        physical    = sum(on_hand)                       all lots incl. pending/blocked/expired
        reserved    = sum(reserved)                      active reservations
        available   = sum(on_hand - reserved)            over released, unexpired lots
        unavailable = sum(on_hand - reserved)            over pending, blocked or expired lots

    so ``physical == reserved + available + unavailable`` always holds.
    """
    usable = usable_lot_filter(today)
    queryset = InventoryLot.objects.all()
    if ingredient_sku:
        queryset = queryset.filter(ingredient__sku=ingredient_sku.strip().upper())
    free = F("on_hand") - F("reserved")
    return (
        queryset.values(
            "ingredient_id",
            "ingredient__sku",
            "ingredient__name",
            "ingredient__base_unit__code",
        )
        .annotate(
            physical=Sum("on_hand"),
            reserved_total=Sum("reserved"),
            available=Coalesce(Sum(free, filter=usable), ZERO),
            unavailable=Coalesce(Sum(free, filter=~usable), ZERO),
        )
        .order_by("ingredient__sku")
    )


def lots(
    *,
    ingredient_sku: str | None = None,
    quality_status: str | None = None,
    has_stock: bool | None = None,
) -> QuerySet[InventoryLot]:
    queryset = InventoryLot.objects.select_related("ingredient__base_unit", "supplier")
    if ingredient_sku:
        queryset = queryset.filter(ingredient__sku=ingredient_sku.strip().upper())
    if quality_status:
        queryset = queryset.filter(quality_status=quality_status)
    if has_stock is True:
        queryset = queryset.filter(on_hand__gt=0)
    elif has_stock is False:
        queryset = queryset.filter(on_hand=0)
    return queryset


def movements(*, lot_id=None, movement_type: str | None = None) -> QuerySet[StockMovement]:
    queryset = StockMovement.objects.select_related("lot", "unit")
    if lot_id:
        queryset = queryset.filter(lot_id=lot_id)
    if movement_type:
        queryset = queryset.filter(movement_type=movement_type)
    return queryset


def reservations(
    *, reference_type: str | None = None, reference_id=None, status: str | None = None
) -> QuerySet[StockReservation]:
    queryset = StockReservation.objects.select_related("lot__ingredient")
    if reference_type:
        queryset = queryset.filter(reference_type=reference_type)
    if reference_id:
        queryset = queryset.filter(reference_id=reference_id)
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def reconcile() -> list[dict]:
    """Compare the lot projections with their sources of truth; empty list means consistent.

    * ``on_hand`` must equal the sum of the lot's ledger movements.
    * ``reserved`` must equal the sum of the lot's active reservations.
    """
    ledger = (
        StockMovement.objects.filter(lot=OuterRef("pk"))
        .values("lot")
        .annotate(total=Sum("quantity_delta"))
        .values("total")
    )
    held = (
        StockReservation.objects.filter(lot=OuterRef("pk"), status="active")
        .values("lot")
        .annotate(total=Sum("quantity"))
        .values("total")
    )
    broken = (
        InventoryLot.objects.annotate(
            ledger_total=Coalesce(Subquery(ledger), ZERO),
            held_total=Coalesce(Subquery(held), ZERO),
        )
        .exclude(Q(on_hand=F("ledger_total")) & Q(reserved=F("held_total")))
        .order_by("internal_lot_code")
    )
    return [
        {
            "lot": lot.internal_lot_code,
            "on_hand": lot.on_hand,
            "ledger_total": lot.ledger_total,
            "reserved": lot.reserved,
            "active_reservations_total": lot.held_total,
        }
        for lot in broken
    ]

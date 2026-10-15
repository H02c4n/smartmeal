"""Inventory write operations (09_CODE_STANDARDS §2, 05 §2, ADR-012).

Concurrency strategy
--------------------
* Every operation that changes a lot first takes a row lock on that lot
  (``SELECT ... FOR UPDATE``). Operations touching several lots lock them in primary-key order,
  so two of them can never wait for each other.
* ``reserve_stock`` additionally takes a transaction-scoped advisory lock per
  (consumer, ingredient), which serialises identical retries so the second one sees the first
  one's result and returns it (idempotency) instead of reserving twice.
* Database CHECK constraints (``on_hand >= 0``, ``reserved <= on_hand``) are the last line of
  defence; the services raise friendly 409 errors before they are reached.

All quantities handed to / stored by this module are in the ingredient's base unit.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalog.models import Ingredient, Unit
from apps.catalog.services import convert_quantity
from apps.core.api_errors import (
    Conflict,
    IdempotencyConflict,
    InsufficientStock,
    InvalidStateTransition,
    LotBlocked,
)

from .models import (
    InventoryLot,
    LotQualityEvent,
    StockMovement,
    StockReservation,
    generate_internal_lot_code,
)

MOVEMENT_TYPES_FOR_ADJUSTMENT = (StockMovement.Type.ADJUSTMENT, StockMovement.Type.WASTE)


def _q(value: Decimal) -> str:
    return format(value, "f")


def _lock_lot(lot_id) -> InventoryLot:
    """Lock one lot row (not the joined ingredient) and return it with its base unit loaded."""
    return (
        InventoryLot.objects.select_for_update(of=("self",))
        .select_related("ingredient__base_unit")
        .get(pk=lot_id)
    )


def _require_reason(reason: str, field: str = "reason") -> str:
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({field: ["A reason is required."]})
    return reason


def _post_movement(
    lot: InventoryLot,
    *,
    movement_type: str,
    delta: Decimal,
    actor,
    reason: str = "",
    reference_type: str = "",
    reference_id=None,
    reverses: StockMovement | None = None,
    occurred_at: datetime | None = None,
) -> StockMovement:
    """Apply ``delta`` to a *locked* lot and append the ledger row. Persists ``reserved`` too."""
    new_on_hand = lot.on_hand + delta
    if new_on_hand < lot.reserved:
        raise InsufficientStock(
            "The change would leave less stock than is reserved.",
            extra={
                "lot": lot.internal_lot_code,
                "on_hand": _q(lot.on_hand),
                "reserved": _q(lot.reserved),
                "requested_change": _q(delta),
            },
        )
    lot.on_hand = new_on_hand
    lot.save(update_fields=["on_hand", "reserved", "updated_at"])
    return StockMovement.objects.create(
        lot=lot,
        movement_type=movement_type,
        quantity_delta=delta,
        unit=lot.ingredient.base_unit,
        balance_after=new_on_hand,
        reference_type=reference_type,
        reference_id=reference_id,
        occurred_at=occurred_at or timezone.now(),
        actor=actor,
        reason=reason,
        reverses=reverses,
    )


def to_base_quantity(ingredient: Ingredient, quantity: Decimal, unit: Unit) -> Decimal:
    """Convert a positive quantity to the ingredient's base unit (ADR-011 rounding)."""
    result = convert_quantity(quantity, unit, ingredient.base_unit, ingredient)
    if result <= 0:
        raise ValidationError({"quantity": ["Quantity is too small to be stored."]})
    return result


# --- Receiving ------------------------------------------------------------------------------
def receive_lot(
    *,
    ingredient: Ingredient,
    supplier,
    receipt_line,
    base_quantity: Decimal,
    supplier_lot_code: str,
    expiry_date: date,
    received_at: datetime,
    actor,
) -> InventoryLot:
    """Create the lot for one goods-receipt line and post its RECEIPT movement.

    The lot starts ``pending`` (quality check outstanding, 05 §4): it is physical stock but not
    available until released. Called by ``purchasing.services`` inside its transaction.
    """
    if base_quantity <= 0:
        raise ValidationError({"quantity": ["Must be greater than zero."]})
    for _attempt in range(3):  # internal code collisions are astronomically rare; retry anyway
        try:
            with transaction.atomic():
                lot = InventoryLot.objects.create(
                    ingredient=ingredient,
                    supplier=supplier,
                    receipt_line=receipt_line,
                    supplier_lot_code=supplier_lot_code,
                    internal_lot_code=generate_internal_lot_code(),
                    received_at=received_at,
                    expiry_date=expiry_date,
                    initial_quantity=base_quantity,
                    on_hand=0,
                    reserved=0,
                )
            break
        except IntegrityError as exc:
            if "internal_lot_code" not in str(exc):
                raise
    else:  # pragma: no cover
        raise RuntimeError("Could not allocate a unique internal lot code.")
    lot.ingredient = ingredient
    _post_movement(
        lot,
        movement_type=StockMovement.Type.RECEIPT,
        delta=base_quantity,
        actor=actor,
        reference_type="goods_receipt",
        reference_id=receipt_line.goods_receipt_id,
        occurred_at=received_at,
    )
    return lot


def reverse_receipt(lot_id, *, reason: str, actor) -> StockMovement:
    """Undo the receipt of a lot that has not been touched since (used by receipt reversal)."""
    reason = _require_reason(reason)
    with transaction.atomic():
        lot = _lock_lot(lot_id)
        movements = list(lot.movements.all())
        receipt = next(
            (m for m in movements if m.movement_type == StockMovement.Type.RECEIPT), None
        )
        if receipt is None:  # pragma: no cover - every lot is created with a receipt
            raise Conflict("The lot has no receipt movement.")
        if len(movements) != 1 or lot.reserved != 0 or lot.on_hand != lot.initial_quantity:
            raise Conflict(
                "Stock of this lot has been used, reserved or adjusted; "
                "the receipt can no longer be reversed.",
                extra={"lot": lot.internal_lot_code},
            )
        return _post_movement(
            lot,
            movement_type=StockMovement.Type.REVERSAL,
            delta=-receipt.quantity_delta,
            actor=actor,
            reason=reason,
            reference_type="goods_receipt",
            reference_id=receipt.reference_id,
            reverses=receipt,
        )


# --- Quality status -------------------------------------------------------------------------
def _change_quality(lot, *, to_status: str, allowed_from: set, actor, reason: str) -> InventoryLot:
    reason = _require_reason(reason)
    with transaction.atomic():
        locked = _lock_lot(lot.pk)
        if locked.quality_status == to_status:
            return locked  # idempotent
        if locked.quality_status not in allowed_from:
            raise InvalidStateTransition(
                f"A {locked.quality_status} lot cannot become {to_status}."
            )
        LotQualityEvent.objects.create(
            lot=locked,
            from_status=locked.quality_status,
            to_status=to_status,
            reason=reason,
            actor=actor,
        )
        locked.quality_status = to_status
        locked.save(update_fields=["quality_status", "updated_at"])
    return locked


def release_lot(lot: InventoryLot, *, actor, reason: str) -> InventoryLot:
    """pending/blocked -> released. Needs a reason; recorded in the quality event log."""
    status = InventoryLot.QualityStatus
    return _change_quality(
        lot,
        to_status=status.RELEASED,
        allowed_from={status.PENDING, status.BLOCKED},
        actor=actor,
        reason=reason,
    )


def block_lot(lot: InventoryLot, *, actor, reason: str) -> InventoryLot:
    """pending/released -> blocked. Existing reservations stay but cannot be consumed."""
    status = InventoryLot.QualityStatus
    return _change_quality(
        lot,
        to_status=status.BLOCKED,
        allowed_from={status.PENDING, status.RELEASED},
        actor=actor,
        reason=reason,
    )


# --- Corrections ----------------------------------------------------------------------------
def adjust_stock(
    lot: InventoryLot,
    *,
    quantity: Decimal,
    unit: Unit,
    reason: str,
    actor,
    movement_type: str = StockMovement.Type.ADJUSTMENT,
) -> StockMovement:
    """Add (positive) or remove (negative) stock of a lot, e.g. after a stock count.

    ``quantity`` is signed and may use any unit compatible with the ingredient. Reserved stock
    cannot be removed (``INSUFFICIENT_STOCK``). ``waste`` must be negative.
    """
    if movement_type not in MOVEMENT_TYPES_FOR_ADJUSTMENT:
        raise ValidationError({"movement_type": ["Must be adjustment or waste."]})
    reason = _require_reason(reason)
    if quantity == 0:
        raise ValidationError({"quantity": ["Must not be zero."]})
    if movement_type == StockMovement.Type.WASTE and quantity > 0:
        raise ValidationError({"quantity": ["Waste must be a negative quantity."]})
    with transaction.atomic():
        locked = _lock_lot(lot.pk)
        magnitude = to_base_quantity(locked.ingredient, abs(quantity), unit)
        delta = magnitude if quantity > 0 else -magnitude
        return _post_movement(
            locked, movement_type=movement_type, delta=delta, actor=actor, reason=reason
        )


def reverse_movement(movement: StockMovement, *, reason: str, actor) -> StockMovement:
    """Cancel a movement with an opposite one (the ledger is never edited)."""
    reason = _require_reason(reason)
    with transaction.atomic():
        original = StockMovement.objects.select_for_update().get(pk=movement.pk)
        if original.movement_type == StockMovement.Type.REVERSAL:
            raise InvalidStateTransition("A reversal cannot be reversed; post a new adjustment.")
        if StockMovement.objects.filter(reverses=original).exists():
            raise InvalidStateTransition("This movement has already been reversed.")
        lot = _lock_lot(original.lot_id)
        return _post_movement(
            lot,
            movement_type=StockMovement.Type.REVERSAL,
            delta=-original.quantity_delta,
            actor=actor,
            reason=reason,
            reference_type=original.reference_type,
            reference_id=original.reference_id,
            reverses=original,
        )


# --- Reservations ---------------------------------------------------------------------------
def _advisory_lock(key: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [key])


@dataclass(frozen=True)
class Allocation:
    lot: InventoryLot
    quantity: Decimal


def plan_fefo_allocation(
    lots: list[InventoryLot], quantity: Decimal
) -> tuple[list[Allocation], Decimal]:
    """Allocate ``quantity`` from lots, earliest expiry first (FEFO); pure function.

    Ties on expiry are broken by receipt time, then id, so the result is deterministic. Returns
    the allocations and the total available (so callers can report a shortfall).
    """
    ordered = sorted(lots, key=lambda lot: (lot.expiry_date, lot.received_at, str(lot.pk)))
    total_available = sum((lot.available for lot in ordered), Decimal("0"))
    remaining = quantity
    allocations: list[Allocation] = []
    for lot in ordered:
        if remaining <= 0:
            break
        take = min(lot.available, remaining)
        if take > 0:
            allocations.append(Allocation(lot, take))
            remaining -= take
    return allocations, total_available


def reserve_stock(
    *,
    ingredient: Ingredient,
    quantity: Decimal,
    unit: Unit,
    reference_type: str,
    reference_id,
    expires_at: datetime | None = None,
    use_by_on_or_after: date | None = None,
) -> list[StockReservation]:
    """Reserve ``quantity`` of an ingredient for a consumer, first-expired-first-out.

    * Only released, unexpired lots with free stock are used (05 §4). ``use_by_on_or_after``
      raises the minimum expiry date (e.g. to keep a shelf-life margin); default is today.
    * All-or-nothing: if the available stock is short, ``INSUFFICIENT_STOCK`` is raised and
      nothing is reserved.
    * Idempotent per (reference, ingredient): repeating the same request returns the existing
      reservations; a different quantity for the same reference is ``IDEMPOTENCY_CONFLICT``.
    """
    reference_type = (reference_type or "").strip()
    if not reference_type or len(reference_type) > 32:
        raise ValidationError({"reference_type": ["1-32 characters required."]})
    if expires_at is not None and expires_at <= timezone.now():
        raise ValidationError({"expires_at": ["Must be in the future."]})
    wanted = to_base_quantity(ingredient, quantity, unit)
    cutoff = use_by_on_or_after or timezone.localdate()

    with transaction.atomic():
        _advisory_lock(f"reserve:{reference_type}:{reference_id}:{ingredient.pk}")

        existing = list(
            StockReservation.objects.filter(
                reference_type=reference_type,
                reference_id=reference_id,
                lot__ingredient=ingredient,
                status=StockReservation.Status.ACTIVE,
            ).select_related("lot")
        )
        if existing:
            held = sum((r.quantity for r in existing), Decimal("0"))
            if held != wanted:
                raise IdempotencyConflict(
                    "This consumer already holds a different quantity of this ingredient.",
                    extra={"held": _q(held), "requested": _q(wanted)},
                )
            return existing

        candidate_ids = list(
            InventoryLot.objects.filter(
                ingredient=ingredient,
                quality_status=InventoryLot.QualityStatus.RELEASED,
                expiry_date__gte=cutoff,
                on_hand__gt=F("reserved"),
            ).values_list("pk", flat=True)
        )
        # Lock in primary-key order (deadlock-free), then re-check under the lock: a concurrent
        # reservation, block or adjustment may have changed the lot since the first look.
        locked = list(
            InventoryLot.objects.select_for_update(of=("self",))
            .select_related("ingredient__base_unit")
            .filter(pk__in=candidate_ids)
            .order_by("pk")
        )
        usable = [
            lot
            for lot in locked
            if lot.quality_status == InventoryLot.QualityStatus.RELEASED
            and lot.expiry_date >= cutoff
            and lot.available > 0
        ]
        allocations, total_available = plan_fefo_allocation(usable, wanted)
        if total_available < wanted:
            raise InsufficientStock(
                extra={
                    "ingredient": ingredient.sku,
                    "requested": _q(wanted),
                    "available": _q(total_available),
                }
            )

        reservations = []
        for allocation in allocations:
            lot = allocation.lot
            lot.reserved += allocation.quantity
            lot.save(update_fields=["reserved", "updated_at"])
            reservations.append(
                StockReservation.objects.create(
                    lot=lot,
                    quantity=allocation.quantity,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    expires_at=expires_at,
                )
            )
        return reservations


def _release(reservation: StockReservation) -> tuple[StockReservation, bool]:
    """Release one reservation; returns it and whether this call changed anything."""
    with transaction.atomic():
        lot_id = StockReservation.objects.values_list("lot_id", flat=True).get(pk=reservation.pk)
        lot = _lock_lot(lot_id)
        current = StockReservation.objects.select_for_update().get(pk=reservation.pk)
        if current.status == StockReservation.Status.RELEASED:
            return current, False
        if current.status == StockReservation.Status.CONSUMED:
            raise InvalidStateTransition("A consumed reservation cannot be released.")
        lot.reserved -= current.quantity
        lot.save(update_fields=["reserved", "updated_at"])
        current.status = StockReservation.Status.RELEASED
        current.released_at = timezone.now()
        current.save(update_fields=["status", "released_at", "updated_at"])
        return current, True


def release_reservation(reservation: StockReservation) -> StockReservation:
    """Give the held quantity back. Idempotent; a consumed reservation cannot be released."""
    return _release(reservation)[0]


def release_reservations_for(*, reference_type: str, reference_id) -> int:
    """Release every active reservation of a consumer (e.g. a cancelled order); idempotent.

    All-or-nothing. Returns how many reservations were released by this call (0 on a repeat).
    """
    with transaction.atomic():
        active = list(
            StockReservation.objects.filter(
                reference_type=reference_type,
                reference_id=reference_id,
                status=StockReservation.Status.ACTIVE,
            ).order_by("lot_id", "pk")
        )
        return sum(1 for reservation in active if _release(reservation)[1])


def consume_reservation(
    reservation: StockReservation, *, actor, quantity: Decimal | None = None
) -> StockReservation:
    """Turn a reservation into a CONSUMPTION movement.

    ``quantity`` (base unit) defaults to the whole reservation; consuming less releases the
    rest. The lot must be released and unexpired, otherwise ``LOT_BLOCKED`` (05 §4). Idempotent:
    repeating with the same quantity returns the consumed reservation, a different quantity is
    ``IDEMPOTENCY_CONFLICT``.
    """
    with transaction.atomic():
        lot_id = StockReservation.objects.values_list("lot_id", flat=True).get(pk=reservation.pk)
        lot = _lock_lot(lot_id)
        current = StockReservation.objects.select_for_update().get(pk=reservation.pk)
        if current.status == StockReservation.Status.CONSUMED:
            if quantity is None or quantity == current.consumed_quantity:
                return current
            raise IdempotencyConflict(
                "This reservation was already consumed with a different quantity.",
                extra={"consumed": _q(current.consumed_quantity)},
            )
        if current.status == StockReservation.Status.RELEASED:
            raise InvalidStateTransition("A released reservation cannot be consumed.")

        amount = current.quantity if quantity is None else quantity
        if amount <= 0 or amount > current.quantity:
            raise ValidationError(
                {"quantity": [f"Must be greater than 0 and at most {_q(current.quantity)}."]}
            )
        if not lot.is_usable():
            raise LotBlocked(
                f"Lot {lot.internal_lot_code} is {lot.quality_status} or expired and cannot "
                "be used.",
                extra={"lot": lot.internal_lot_code, "quality_status": lot.quality_status},
            )

        lot.reserved -= current.quantity  # the whole hold ends; any remainder is freed
        _post_movement(
            lot,
            movement_type=StockMovement.Type.CONSUMPTION,
            delta=-amount,
            actor=actor,
            reference_type=current.reference_type,
            reference_id=current.reference_id,
        )
        current.status = StockReservation.Status.CONSUMED
        current.consumed_at = timezone.now()
        current.consumed_quantity = amount
        current.save(update_fields=["status", "consumed_at", "consumed_quantity", "updated_at"])
        return current


def release_expired_reservations(now: datetime | None = None) -> int:
    """Release active reservations whose ``expires_at`` has passed; returns the count.

    No scheduler exists yet (Celery is introduced when needed, 01 §1); run this from a
    management command or cron until then.
    """
    now = now or timezone.now()
    due = list(
        StockReservation.objects.filter(
            status=StockReservation.Status.ACTIVE, expires_at__lte=now
        ).order_by("lot_id", "pk")
    )
    return sum(1 for reservation in due if _release(reservation)[1])

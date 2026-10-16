"""Inventory API (03_API_CONTRACTS, section "Stock and purchasing").

Back-office only, role-based (ADR-013; table in ``apps.accounts.roles``): reading needs
``inventory:read``, reservations ``inventory:reserve``, and the operations 05 §1 reserves for
special permission need their own: ``inventory:adjust_stock`` (adjustments, movement reversal),
``inventory:release_lot``, ``inventory:block_lot``.
Stock-changing creates require an ``Idempotency-Key`` header.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from apps.accounts.roles import Perm
from apps.core.idempotency import request_key, run_idempotent
from apps.core.permissions import has_permission, has_permission_by_method
from apps.core.serializers import ReasonSerializer

from . import selectors, services
from .models import InventoryLot, StockMovement, StockReservation
from .serializers import (
    AdjustmentSerializer,
    BalanceSerializer,
    LotSerializer,
    MovementSerializer,
    ReservationConsumeSerializer,
    ReservationCreateSerializer,
    ReservationSerializer,
)

CanAdjustStock = has_permission(Perm.INVENTORY_ADJUST_STOCK)
CanReleaseLot = has_permission(Perm.INVENTORY_RELEASE_LOT)
CanBlockLot = has_permission(Perm.INVENTORY_BLOCK_LOT)
CanReadInventory = has_permission(Perm.INVENTORY_READ)
ReservationAccess = has_permission_by_method(read=Perm.INVENTORY_READ, write=Perm.INVENTORY_RESERVE)

IDEMPOTENCY_HEADER = OpenApiParameter(
    "Idempotency-Key",
    OpenApiTypes.STR,
    OpenApiParameter.HEADER,
    required=True,
    description="Unique key (8-128 chars). Repeating a request with the same key and body "
    "returns the original result without repeating its effect; a different body is a 409.",
)
INGREDIENT_PARAM = OpenApiParameter("ingredient", OpenApiTypes.STR, description="Filter by SKU.")


def _schema(view) -> bool:
    return getattr(view, "swagger_fake_view", False)


def _bool_param(request, name: str) -> bool | None:
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return None
    if raw.lower() in {"true", "1"}:
        return True
    if raw.lower() in {"false", "0"}:
        return False
    raise ValidationError({name: ["Must be true or false."]})


def _choice_param(request, name: str, allowed) -> str | None:
    value = request.query_params.get(name)
    if value and value not in allowed:
        raise ValidationError({name: [f"Must be one of {sorted(allowed)}."]})
    return value or None


class BalanceView(GenericAPIView):
    """Stock per ingredient in base units: physical, reserved, available, unavailable."""

    permission_classes = [CanReadInventory]
    serializer_class = BalanceSerializer

    @extend_schema(parameters=[INGREDIENT_PARAM], responses={200: BalanceSerializer(many=True)})
    def get(self, request):
        queryset = selectors.stock_levels(ingredient_sku=request.query_params.get("ingredient"))
        page = self.paginate_queryset(queryset)
        rows = [
            {
                "ingredient": row["ingredient__sku"],
                "ingredient_name": row["ingredient__name"],
                "base_unit": row["ingredient__base_unit__code"],
                "physical": row["physical"],
                "reserved": row["reserved_total"],
                "available": row["available"],
                "unavailable": row["unavailable"],
            }
            for row in page
        ]
        return self.get_paginated_response(BalanceSerializer(rows, many=True).data)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            INGREDIENT_PARAM,
            OpenApiParameter(
                "quality_status", OpenApiTypes.STR, description="pending, released or blocked."
            ),
            OpenApiParameter("has_stock", OpenApiTypes.BOOL),
        ]
    )
)
class LotViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [CanReadInventory]
    serializer_class = LotSerializer

    def get_permissions(self):
        if self.action == "release":
            return [CanReleaseLot()]
        if self.action == "block":
            return [CanBlockLot()]
        return super().get_permissions()

    def get_queryset(self):
        if _schema(self):
            return InventoryLot.objects.none()
        params = self.request
        return selectors.lots(
            ingredient_sku=params.query_params.get("ingredient"),
            quality_status=_choice_param(
                params, "quality_status", InventoryLot.QualityStatus.values
            ),
            has_stock=_bool_param(params, "has_stock"),
        )

    @extend_schema(request=ReasonSerializer, responses={200: LotSerializer})
    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        """End a quality hold (pending/blocked -> released). Needs a reason; idempotent."""
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.release_lot(
            self.get_object(), actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(LotSerializer(selectors.lots().get(pk=pk)).data)

    @extend_schema(request=ReasonSerializer, responses={200: LotSerializer})
    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):
        """Put a lot on quality hold (pending/released -> blocked). Needs a reason; idempotent."""
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.block_lot(
            self.get_object(), actor=request.user, reason=serializer.validated_data["reason"]
        )
        return Response(LotSerializer(selectors.lots().get(pk=pk)).data)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("lot", OpenApiTypes.UUID),
            OpenApiParameter("movement_type", OpenApiTypes.STR),
        ]
    )
)
class MovementViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The append-only stock ledger."""

    permission_classes = [CanReadInventory]
    serializer_class = MovementSerializer

    def get_permissions(self):
        if self.action == "reverse":
            return [CanAdjustStock()]
        return super().get_permissions()

    def get_queryset(self):
        if _schema(self):
            return StockMovement.objects.none()
        return selectors.movements(
            lot_id=self.request.query_params.get("lot"),
            movement_type=_choice_param(self.request, "movement_type", StockMovement.Type.values),
        )

    @extend_schema(request=ReasonSerializer, responses={201: MovementSerializer})
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        """Cancel a movement with an opposite one; a movement can be reversed once."""
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reversal = services.reverse_movement(
            self.get_object(), reason=serializer.validated_data["reason"], actor=request.user
        )
        return Response(MovementSerializer(reversal).data, status=status.HTTP_201_CREATED)


class AdjustmentView(GenericAPIView):
    permission_classes = [CanAdjustStock]
    serializer_class = AdjustmentSerializer

    @extend_schema(
        parameters=[IDEMPOTENCY_HEADER],
        request=AdjustmentSerializer,
        responses={201: MovementSerializer, 200: MovementSerializer},
    )
    def post(self, request):
        """Add (positive) or remove (negative) stock of a lot, e.g. after a stock count."""
        key = request_key(request)
        serializer = AdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        movement, created = run_idempotent(
            scope="stock_adjustment.create",
            key=key,
            actor=request.user,
            fingerprint=request.data,
            create=lambda: services.adjust_stock(
                data["lot"],
                quantity=data["quantity"],
                unit=data["unit"],
                reason=data["reason"],
                actor=request.user,
                movement_type=data["movement_type"],
            ),
            load=lambda pk: StockMovement.objects.get(pk=pk),
        )
        code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(MovementSerializer(movement).data, status=code)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("reference_type", OpenApiTypes.STR),
            OpenApiParameter("reference_id", OpenApiTypes.UUID),
            OpenApiParameter("status", OpenApiTypes.STR),
        ]
    )
)
class ReservationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [ReservationAccess]
    serializer_class = ReservationSerializer

    def get_queryset(self):
        if _schema(self):
            return StockReservation.objects.none()
        return selectors.reservations(
            reference_type=self.request.query_params.get("reference_type"),
            reference_id=self.request.query_params.get("reference_id"),
            status=_choice_param(self.request, "status", StockReservation.Status.values),
        )

    @extend_schema(
        request=ReservationCreateSerializer,
        responses={201: ReservationSerializer(many=True), 200: ReservationSerializer(many=True)},
    )
    def create(self, request):
        """Reserve stock first-expired-first-out, all or nothing.

        Idempotent per (reference_type, reference_id, ingredient): repeating the request returns
        the existing reservations (200); a different quantity for the same reference is a 409.
        """
        serializer = ReservationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        existing_before = StockReservation.objects.filter(
            reference_type=data["reference_type"].strip(),
            reference_id=data["reference_id"],
            lot__ingredient=data["ingredient"],
            status="active",
        ).exists()
        reservations = services.reserve_stock(
            ingredient=data["ingredient"],
            quantity=data["quantity"],
            unit=data["unit"],
            reference_type=data["reference_type"],
            reference_id=data["reference_id"],
            expires_at=data.get("expires_at"),
            use_by_on_or_after=data.get("use_by_on_or_after"),
        )
        fresh = selectors.reservations().filter(pk__in=[r.pk for r in reservations])
        code = status.HTTP_200_OK if existing_before else status.HTTP_201_CREATED
        return Response(ReservationSerializer(fresh, many=True).data, status=code)

    @extend_schema(request=None, responses={200: ReservationSerializer})
    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        reservation = services.release_reservation(self.get_object())
        return Response(ReservationSerializer(reservation).data)

    @extend_schema(request=ReservationConsumeSerializer, responses={200: ReservationSerializer})
    @action(detail=True, methods=["post"])
    def consume(self, request, pk=None):
        """Turn the reservation into a consumption movement (blocked/expired lot: LOT_BLOCKED)."""
        serializer = ReservationConsumeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reservation = services.consume_reservation(
            self.get_object(),
            actor=request.user,
            quantity=serializer.validated_data.get("quantity"),
        )
        return Response(ReservationSerializer(reservation).data)

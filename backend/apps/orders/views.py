"""Orders API (03_API_CONTRACTS, ADR-014).

Customers act on their own orders only (object scope is the queryset: another customer's order
is a 404, never a 403, so existence is not revealed). Back-office roles see every order.
Placing an order requires an ``Idempotency-Key`` so a retried request cannot order twice.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from apps.accounts.roles import Perm
from apps.core.idempotency import request_key, run_idempotent
from apps.core.permissions import has_permission, user_permissions

from . import selectors, services
from .models import CustomerAddress, Order
from .serializers import (
    AddressSerializer,
    CancelSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    OrderStaffSerializer,
)

IDEMPOTENCY_HEADER = OpenApiParameter(
    "Idempotency-Key",
    OpenApiTypes.STR,
    OpenApiParameter.HEADER,
    required=True,
    description="Unique key (8-128 chars). Repeating a request with the same key and body "
    "returns the original order without ordering again; a different body is a 409.",
)


def _schema(view) -> bool:
    return getattr(view, "swagger_fake_view", False)


class OrderAccess(BasePermission):
    """create: customers; list/retrieve: customers + back-office; cancel: customer or any."""

    def has_permission(self, request, view) -> bool:
        granted = user_permissions(request)
        if view.action == "create":
            return Perm.ORDERS_PLACE in granted
        if view.action == "cancel":
            return bool(granted & {Perm.ORDERS_PLACE, Perm.ORDERS_CANCEL_ANY})
        return bool(granted & {Perm.ORDERS_PLACE, Perm.ORDERS_READ_ALL})


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, description="Filter by status."),
            OpenApiParameter("delivery_date", OpenApiTypes.DATE, description="Filter by date."),
            OpenApiParameter(
                "customer", OpenApiTypes.STR, description="Customer e-mail (back-office only)."
            ),
        ]
    ),
)
class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [OrderAccess]

    def get_serializer_class(self):
        if self.action == "create":
            return OrderCreateSerializer
        if self.action == "cancel":
            return CancelSerializer
        if not _schema(self) and Perm.ORDERS_READ_ALL in user_permissions(self.request):
            return OrderStaffSerializer
        return OrderSerializer

    def get_queryset(self):
        if _schema(self):
            return Order.objects.none()
        permissions = user_permissions(self.request)
        queryset = selectors.orders_visible_to(
            self.request.user, permissions, for_cancel=self.action == "cancel"
        )
        if self.action != "list":
            return queryset
        params = self.request.query_params
        # Only back-office roles may filter by customer; for a customer it is already their own.
        customer = params.get("customer") if Perm.ORDERS_READ_ALL in permissions else None
        return selectors.filter_orders(
            queryset,
            status=params.get("status"),
            delivery_date=params.get("delivery_date"),
            customer=customer,
        )

    @extend_schema(
        parameters=[IDEMPOTENCY_HEADER],
        request=OrderCreateSerializer,
        responses={201: OrderSerializer, 200: OrderSerializer},
    )
    def create(self, request):
        key = request_key(request)
        serializer = OrderCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        order, created = run_idempotent(
            scope="order.create",
            key=key,
            actor=request.user,
            fingerprint=request.data,
            create=lambda: services.place_order(
                customer=request.user,
                items=[
                    services.OrderItemInput(product=product, quantity=quantity)
                    for product, quantity in data["resolved_items"]
                ],
                delivery_date=data["delivery_date"],
                address=data["address"],
            ),
            load=lambda pk: Order.objects.get(pk=pk),
        )
        fresh = selectors.orders_visible_to(request.user, user_permissions(request)).get(
            pk=order.pk
        )
        code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(OrderSerializer(fresh).data, status=code)

    @extend_schema(request=CancelSerializer, responses={200: OrderSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Cancel an order and release its stock reservation; repeating it is harmless."""
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = self.get_object()
        # Anyone who may cancel any order acts as back-office (reason needed, no deadline).
        back_office = Perm.ORDERS_CANCEL_ANY in user_permissions(request)
        services.cancel_order(
            order,
            actor=request.user,
            reason=serializer.validated_data["reason"],
            customer_rules=not back_office,
        )
        fresh = selectors.orders_visible_to(
            request.user, user_permissions(request), for_cancel=True
        ).get(pk=order.pk)
        serializer_class = OrderStaffSerializer if back_office else OrderSerializer
        return Response(serializer_class(fresh).data)


class AddressViewSet(viewsets.ModelViewSet):
    """The signed-in customer's own address book (never anyone else's)."""

    permission_classes = [has_permission(Perm.ORDERS_PLACE)]
    serializer_class = AddressSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        if _schema(self):
            return CustomerAddress.objects.none()
        return selectors.addresses_of(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        address = services.create_address(user=request.user, **serializer.validated_data)
        return Response(self.get_serializer(address).data, status=status.HTTP_201_CREATED)

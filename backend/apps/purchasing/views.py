"""Purchasing API (03_API_CONTRACTS, section "Stock and purchasing").

Back-office only (placeholder ``IsBackOfficeStaff``, ADR-009/010); reversing a receipt needs the
explicit ``purchasing.reverse_goodsreceipt`` permission (05 §1). Receiving goods requires an
``Idempotency-Key`` header so a retried request cannot receive the same delivery twice.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.idempotency import request_key, run_idempotent
from apps.core.permissions import IsBackOfficeStaff, staff_with_permission
from apps.core.serializers import ReasonSerializer

from . import selectors, services
from .models import GoodsReceipt, PurchaseOrder, PurchaseOrderLine, Supplier
from .serializers import (
    GoodsReceiptCreateSerializer,
    GoodsReceiptSerializer,
    PurchaseOrderCreateSerializer,
    PurchaseOrderListSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderUpdateSerializer,
    SupplierSerializer,
    SupplierWriteSerializer,
)

IDEMPOTENCY_HEADER = OpenApiParameter(
    "Idempotency-Key",
    OpenApiTypes.STR,
    OpenApiParameter.HEADER,
    required=True,
    description="Unique key (8-128 chars). Repeating a request with the same key and body "
    "returns the original result without repeating its effect; a different body is a 409.",
)
STATUS_PARAM = OpenApiParameter("status", OpenApiTypes.STR, description="Filter by status.")
CanReverseReceipt = staff_with_permission("purchasing.reverse_goodsreceipt")


def _schema(view) -> bool:
    return getattr(view, "swagger_fake_view", False)


# --- Suppliers ------------------------------------------------------------------------------
class SupplierViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsBackOfficeStaff]
    serializer_class = SupplierSerializer

    def get_queryset(self):
        if _schema(self):
            return Supplier.objects.none()
        return selectors.suppliers(q=self.request.query_params.get("q"))

    @extend_schema(request=SupplierWriteSerializer, responses={201: SupplierSerializer})
    def create(self, request):
        serializer = SupplierWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        supplier = services.create_supplier(**serializer.validated_data)
        return Response(SupplierSerializer(supplier).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=SupplierWriteSerializer, responses={200: SupplierSerializer})
    def partial_update(self, request, pk=None):
        supplier = self.get_object()
        serializer = SupplierWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        supplier = services.update_supplier(supplier, **serializer.validated_data)
        return Response(SupplierSerializer(supplier).data)

    @extend_schema(request=None, responses={200: SupplierSerializer})
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return Response(
            SupplierSerializer(services.set_supplier_active(self.get_object(), True)).data
        )

    @extend_schema(request=None, responses={200: SupplierSerializer})
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        return Response(
            SupplierSerializer(services.set_supplier_active(self.get_object(), False)).data
        )


# --- Purchase orders ------------------------------------------------------------------------
@extend_schema_view(list=extend_schema(parameters=[STATUS_PARAM]))
class PurchaseOrderViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsBackOfficeStaff]

    def get_serializer_class(self):
        return PurchaseOrderListSerializer if self.action == "list" else PurchaseOrderSerializer

    def get_queryset(self):
        if _schema(self):
            return PurchaseOrder.objects.none()
        status_filter = self.request.query_params.get("status")
        if status_filter and status_filter not in PurchaseOrder.Status.values:
            raise ValidationError({"status": [f"Must be one of {PurchaseOrder.Status.values}."]})
        return selectors.purchase_orders(status=status_filter)

    def _respond(self, po, code=status.HTTP_200_OK):
        fresh = selectors.purchase_orders().get(pk=po.pk)
        return Response(PurchaseOrderSerializer(fresh).data, status=code)

    @staticmethod
    def _lines(items):
        return [services.POLineInput(**item) for item in items]

    @extend_schema(request=PurchaseOrderCreateSerializer, responses={201: PurchaseOrderSerializer})
    def create(self, request):
        serializer = PurchaseOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        po = services.create_purchase_order(
            supplier=data["supplier"],
            currency=data["currency"],
            created_by=request.user,
            expected_at=data.get("expected_at"),
            lines=self._lines(data.get("lines", [])),
        )
        return self._respond(po, status.HTTP_201_CREATED)

    @extend_schema(request=PurchaseOrderUpdateSerializer, responses={200: PurchaseOrderSerializer})
    def partial_update(self, request, pk=None):
        po = self.get_object()
        serializer = PurchaseOrderUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.update_purchase_order(
            po,
            expected_at=data.get("expected_at"),
            set_expected_at="expected_at" in data,
            lines=self._lines(data["lines"]) if "lines" in data else None,
        )
        return self._respond(po)

    @extend_schema(request=None, responses={200: PurchaseOrderSerializer})
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return self._respond(services.submit_purchase_order(self.get_object()))

    @extend_schema(request=None, responses={200: PurchaseOrderSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._respond(services.cancel_purchase_order(self.get_object()))


# --- Goods receipts -------------------------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        parameters=[OpenApiParameter("purchase_order", OpenApiTypes.UUID), STATUS_PARAM]
    )
)
class GoodsReceiptViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsBackOfficeStaff]
    serializer_class = GoodsReceiptSerializer

    def get_permissions(self):
        if self.action == "reverse":
            return [CanReverseReceipt()]
        return super().get_permissions()

    def get_queryset(self):
        if _schema(self):
            return GoodsReceipt.objects.none()
        return selectors.goods_receipts(
            purchase_order_id=self.request.query_params.get("purchase_order"),
            status=self.request.query_params.get("status"),
        )

    @extend_schema(
        parameters=[IDEMPOTENCY_HEADER],
        request=GoodsReceiptCreateSerializer,
        responses={201: GoodsReceiptSerializer, 200: GoodsReceiptSerializer},
    )
    def create(self, request):
        key = request_key(request)
        serializer = GoodsReceiptCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        po = data["purchase_order"]
        po_lines = {
            str(line.pk): line for line in PurchaseOrderLine.objects.filter(purchase_order=po)
        }
        lines = []
        for item in data["lines"]:
            po_line = po_lines.get(str(item["po_line"]))
            if po_line is None:
                raise ValidationError({"lines": ["A line does not belong to this purchase order."]})
            lines.append(
                services.ReceiptLineInput(
                    po_line=po_line,
                    quantity=item["quantity"],
                    unit=item["unit"],
                    supplier_lot_code=item["supplier_lot_code"],
                    expiry_date=item["expiry_date"],
                )
            )
        receipt, created = run_idempotent(
            scope="goods_receipt.create",
            key=key,
            actor=request.user,
            fingerprint=request.data,
            create=lambda: services.post_goods_receipt(
                purchase_order=po,
                lines=lines,
                actor=request.user,
                received_at=data.get("received_at"),
            ),
            load=lambda pk: GoodsReceipt.objects.get(pk=pk),
        )
        fresh = selectors.goods_receipts().get(pk=receipt.pk)
        code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(GoodsReceiptSerializer(fresh).data, status=code)

    @extend_schema(request=ReasonSerializer, responses={200: GoodsReceiptSerializer})
    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        """Undo a receipt whose stock has not been touched; idempotent."""
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = services.reverse_goods_receipt(
            self.get_object(), reason=serializer.validated_data["reason"], actor=request.user
        )
        fresh = selectors.goods_receipts().get(pk=receipt.pk)
        return Response(GoodsReceiptSerializer(fresh).data)

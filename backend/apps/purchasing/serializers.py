from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import Ingredient, Unit

from .models import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine, Supplier

QUANTITY = {"max_digits": 14, "decimal_places": 4, "min_value": Decimal("0.0001")}


def _upper(value):
    return value.strip().upper() if isinstance(value, str) else value


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "contact_details", "is_active", "created_at", "updated_at"]
        read_only_fields = fields


class SupplierWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    contact_details = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if "is_active" in (getattr(self, "initial_data", None) or {}):
            raise serializers.ValidationError(
                {"is_active": ["Use the activate/deactivate actions."]}
            )
        return attrs


# --- Purchase orders ------------------------------------------------------------------------
class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    ingredient = serializers.CharField(source="ingredient.sku", read_only=True)
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    unit = serializers.CharField(source="unit.code", read_only=True)
    base_unit = serializers.CharField(source="ingredient.base_unit.code", read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = [
            "id",
            "ingredient",
            "ingredient_name",
            "ordered_quantity",
            "unit",
            "unit_cost",
            "base_unit",
            "ordered_base_quantity",
            "received_base_quantity",
        ]
        read_only_fields = fields


class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier = serializers.UUIDField(source="supplier_id", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    created_by = serializers.UUIDField(source="created_by_id", read_only=True)
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "po_number",
            "supplier",
            "supplier_name",
            "status",
            "currency",
            "ordered_at",
            "expected_at",
            "created_by",
            "cancelled_at",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PurchaseOrderListSerializer(PurchaseOrderSerializer):
    class Meta(PurchaseOrderSerializer.Meta):
        fields = [f for f in PurchaseOrderSerializer.Meta.fields if f != "lines"]
        read_only_fields = fields


class POLineWriteSerializer(serializers.Serializer):
    ingredient = serializers.SlugRelatedField(slug_field="sku", queryset=Ingredient.objects.all())
    quantity = serializers.DecimalField(**QUANTITY)
    unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all())
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=4, min_value=Decimal("0"))

    def to_internal_value(self, data):
        if isinstance(data, dict) and "ingredient" in data:
            data = {**data, "ingredient": _upper(data["ingredient"])}
        return super().to_internal_value(data)


class PurchaseOrderCreateSerializer(serializers.Serializer):
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.all())
    currency = serializers.RegexField(r"^[A-Za-z]{3}$")
    expected_at = serializers.DateField(required=False, allow_null=True)
    lines = POLineWriteSerializer(many=True, required=False)


class PurchaseOrderUpdateSerializer(serializers.Serializer):
    expected_at = serializers.DateField(allow_null=True)
    lines = POLineWriteSerializer(many=True)


# --- Goods receipts -------------------------------------------------------------------------
class GoodsReceiptLineSerializer(serializers.ModelSerializer):
    ingredient = serializers.CharField(source="ingredient.sku", read_only=True)
    unit = serializers.CharField(source="unit.code", read_only=True)
    po_line = serializers.UUIDField(source="po_line_id", read_only=True)
    lot = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceiptLine
        fields = [
            "id",
            "po_line",
            "ingredient",
            "received_quantity",
            "unit",
            "received_base_quantity",
            "supplier_lot_code",
            "expiry_date",
            "lot",
        ]
        read_only_fields = fields

    def get_lot(self, obj) -> dict | None:
        lot = getattr(obj, "lot", None)
        if lot is None:
            return None
        return {
            "id": str(lot.pk),
            "internal_lot_code": lot.internal_lot_code,
            "quality_status": lot.quality_status,
        }


class GoodsReceiptSerializer(serializers.ModelSerializer):
    purchase_order = serializers.UUIDField(source="purchase_order_id", read_only=True)
    received_by = serializers.UUIDField(source="received_by_id", read_only=True)
    lines = GoodsReceiptLineSerializer(many=True, read_only=True)

    class Meta:
        model = GoodsReceipt
        fields = [
            "id",
            "purchase_order",
            "status",
            "received_at",
            "received_by",
            "reversed_at",
            "reversal_reason",
            "lines",
            "created_at",
        ]
        read_only_fields = fields


class ReceiptLineWriteSerializer(serializers.Serializer):
    po_line = serializers.UUIDField()
    quantity = serializers.DecimalField(**QUANTITY)
    unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all())
    supplier_lot_code = serializers.CharField(max_length=64)
    expiry_date = serializers.DateField()


class GoodsReceiptCreateSerializer(serializers.Serializer):
    purchase_order = serializers.PrimaryKeyRelatedField(queryset=PurchaseOrder.objects.all())
    received_at = serializers.DateTimeField(required=False)
    lines = ReceiptLineWriteSerializer(many=True, allow_empty=False)

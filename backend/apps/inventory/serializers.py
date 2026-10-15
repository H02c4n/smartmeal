from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import Ingredient, Unit

from .models import InventoryLot, StockMovement, StockReservation

QUANTITY = {"max_digits": 14, "decimal_places": 4}


def _upper(value):
    return value.strip().upper() if isinstance(value, str) else value


class BalanceSerializer(serializers.Serializer):
    """Stock per ingredient in its base unit (see ``selectors.stock_levels`` for definitions)."""

    ingredient = serializers.CharField()
    ingredient_name = serializers.CharField()
    base_unit = serializers.CharField()
    physical = serializers.DecimalField(**QUANTITY)
    reserved = serializers.DecimalField(**QUANTITY)
    available = serializers.DecimalField(**QUANTITY)
    unavailable = serializers.DecimalField(**QUANTITY)


class LotSerializer(serializers.ModelSerializer):
    ingredient = serializers.CharField(source="ingredient.sku", read_only=True)
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    base_unit = serializers.CharField(source="ingredient.base_unit.code", read_only=True)
    supplier = serializers.UUIDField(source="supplier_id", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    available = serializers.DecimalField(max_digits=14, decimal_places=4, read_only=True)

    class Meta:
        model = InventoryLot
        fields = [
            "id",
            "internal_lot_code",
            "supplier_lot_code",
            "ingredient",
            "ingredient_name",
            "base_unit",
            "supplier",
            "supplier_name",
            "received_at",
            "expiry_date",
            "quality_status",
            "initial_quantity",
            "on_hand",
            "reserved",
            "available",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class MovementSerializer(serializers.ModelSerializer):
    lot = serializers.CharField(source="lot.internal_lot_code", read_only=True)
    lot_id = serializers.UUIDField(read_only=True)
    unit = serializers.CharField(source="unit.code", read_only=True)
    actor = serializers.UUIDField(source="actor_id", read_only=True)
    reverses = serializers.UUIDField(source="reverses_id", read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "lot",
            "lot_id",
            "movement_type",
            "quantity_delta",
            "unit",
            "balance_after",
            "reference_type",
            "reference_id",
            "occurred_at",
            "actor",
            "reason",
            "reverses",
        ]
        read_only_fields = fields


class ReservationSerializer(serializers.ModelSerializer):
    lot = serializers.CharField(source="lot.internal_lot_code", read_only=True)
    ingredient = serializers.CharField(source="lot.ingredient.sku", read_only=True)

    class Meta:
        model = StockReservation
        fields = [
            "id",
            "lot",
            "ingredient",
            "quantity",
            "status",
            "reference_type",
            "reference_id",
            "expires_at",
            "released_at",
            "consumed_at",
            "consumed_quantity",
            "created_at",
        ]
        read_only_fields = fields


class AdjustmentSerializer(serializers.Serializer):
    lot = serializers.PrimaryKeyRelatedField(queryset=InventoryLot.objects.all())
    quantity = serializers.DecimalField(**QUANTITY)  # signed: negative removes stock
    unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all())
    movement_type = serializers.ChoiceField(
        choices=["adjustment", "waste"], required=False, default="adjustment"
    )
    reason = serializers.CharField(max_length=1000)

    def validate_quantity(self, value: Decimal) -> Decimal:
        if value == 0:
            raise serializers.ValidationError("Must not be zero.")
        return value


class ReservationCreateSerializer(serializers.Serializer):
    ingredient = serializers.SlugRelatedField(slug_field="sku", queryset=Ingredient.objects.all())
    quantity = serializers.DecimalField(**QUANTITY, min_value=Decimal("0.0001"))
    unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all())
    reference_type = serializers.CharField(max_length=32)
    reference_id = serializers.UUIDField()
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
    use_by_on_or_after = serializers.DateField(required=False, allow_null=True)

    def to_internal_value(self, data):
        if isinstance(data, dict) and "ingredient" in data:
            data = {**data, "ingredient": _upper(data["ingredient"])}
        return super().to_internal_value(data)


class ReservationConsumeSerializer(serializers.Serializer):
    quantity = serializers.DecimalField(
        **QUANTITY, min_value=Decimal("0.0001"), required=False, allow_null=True
    )

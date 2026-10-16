from django.conf import settings
from rest_framework import serializers

from apps.catalog.models import Product

from .models import CustomerAddress, Order, OrderLine, OrderStatusEvent
from .services import UNAVAILABLE_MESSAGE


class AddressSerializer(serializers.ModelSerializer):
    country_code = serializers.RegexField(
        r"^[A-Za-z]{2}$",
        help_text="ISO 3166-1 alpha-2, e.g. SE",
        error_messages={"invalid": "Must be a 2-letter country code."},
    )

    class Meta:
        model = CustomerAddress
        fields = [
            "id",
            "recipient_name",
            "line1",
            "line2",
            "postal_code",
            "city",
            "country_code",
            "phone",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_country_code(self, value: str) -> str:
        return value.upper()


class OrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    delivery_date = serializers.DateField()
    delivery_address_id = serializers.UUIDField()
    items = OrderItemInputSerializer(many=True, allow_empty=False)

    def validate_items(self, items):
        if len(items) > settings.ORDER_MAX_LINES:
            raise serializers.ValidationError(
                f"At most {settings.ORDER_MAX_LINES} items per order."
            )
        return items

    def validate(self, attrs):
        user = self.context["request"].user
        address = CustomerAddress.objects.filter(pk=attrs["delivery_address_id"], user=user).first()
        if address is None:  # another customer's address looks exactly like a missing one
            raise serializers.ValidationError({"delivery_address_id": "Address not found."})
        products = Product.objects.in_bulk([item["product_id"] for item in attrs["items"]])
        errors, resolved = [], []
        for item in attrs["items"]:
            product = products.get(item["product_id"])
            if product is None or not product.is_active:
                errors.append({"product_id": [UNAVAILABLE_MESSAGE]})
            else:
                errors.append({})
                resolved.append((product, item["quantity"]))
        if any(errors):
            raise serializers.ValidationError({"items": errors})
        attrs["address"] = address
        attrs["resolved_items"] = resolved
        return attrs


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class OrderLineSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(read_only=True)
    product_sku = serializers.CharField(source="product_sku_snapshot", read_only=True)
    product_name = serializers.CharField(source="product_name_snapshot", read_only=True)
    recipe_version_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = OrderLine
        fields = [
            "product_id",
            "product_sku",
            "product_name",
            "quantity",
            "unit_price",
            "line_total",
            "recipe_version_id",
        ]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    delivery_address = serializers.JSONField(source="delivery_address_snapshot", read_only=True)
    items = OrderLineSerializer(source="lines", many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "delivery_date",
            "delivery_address",
            "currency",
            "subtotal",
            "tax_amount",
            "delivery_fee",
            "total_amount",
            "items",
            "created_at",
            "confirmed_at",
            "cancelled_at",
            "cancellation_reason",
        ]
        read_only_fields = fields


class OrderStatusEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = OrderStatusEvent
        fields = ["from_status", "to_status", "reason", "actor_email", "created_at"]
        read_only_fields = fields


class OrderStaffSerializer(OrderSerializer):
    """Back-office view: adds the customer and the status history."""

    customer_id = serializers.UUIDField(read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    status_history = OrderStatusEventSerializer(source="events", many=True, read_only=True)

    class Meta(OrderSerializer.Meta):
        fields = [*OrderSerializer.Meta.fields, "customer_id", "customer_email", "status_history"]
        read_only_fields = fields

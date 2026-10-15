from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import Ingredient, Product, Unit

from .models import RecipeLine, RecipeVersion
from .services import LineInput, Requirement

QUANTITY_FIELD = {"max_digits": 14, "decimal_places": 4, "min_value": Decimal("0.0001")}


class RecipeLineSerializer(serializers.ModelSerializer):
    ingredient = serializers.SlugRelatedField(slug_field="sku", read_only=True)
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    unit = serializers.SlugRelatedField(slug_field="code", read_only=True)
    base_unit = serializers.CharField(source="ingredient.base_unit.code", read_only=True)

    class Meta:
        model = RecipeLine
        fields = [
            "ingredient",
            "ingredient_name",
            "quantity",
            "unit",
            "waste_factor",
            "base_unit",
            "net_base_quantity",
            "gross_base_quantity",
        ]
        read_only_fields = fields


class AllergenSummarySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    presence = serializers.CharField()


class RecipeVersionSerializer(serializers.ModelSerializer):
    product = serializers.SlugRelatedField(slug_field="sku", read_only=True)
    yield_unit = serializers.SlugRelatedField(slug_field="code", read_only=True)
    approved_by = serializers.UUIDField(source="approved_by_id", read_only=True, allow_null=True)
    lines = RecipeLineSerializer(many=True, read_only=True)
    allergens = serializers.SerializerMethodField()

    class Meta:
        model = RecipeVersion
        fields = [
            "id",
            "product",
            "version_number",
            "status",
            "yield_quantity",
            "yield_unit",
            "effective_from",
            "effective_to",
            "approved_at",
            "approved_by",
            "retired_at",
            "lines",
            "allergens",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_allergens(self, obj) -> list[dict]:
        from .selectors import allergens_for_version

        return allergens_for_version(obj)


class RecipeVersionListSerializer(RecipeVersionSerializer):
    """List items omit lines and allergens (one query per row otherwise)."""

    class Meta(RecipeVersionSerializer.Meta):
        fields = [f for f in RecipeVersionSerializer.Meta.fields if f not in {"lines", "allergens"}]
        read_only_fields = fields


class RecipeLineWriteSerializer(serializers.Serializer):
    ingredient = serializers.SlugRelatedField(slug_field="sku", queryset=Ingredient.objects.all())
    quantity = serializers.DecimalField(**QUANTITY_FIELD)
    unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all())
    waste_factor = serializers.DecimalField(
        max_digits=5,
        decimal_places=4,
        min_value=Decimal("0"),
        max_value=Decimal("0.9999"),
        required=False,
        default=Decimal("0"),
    )

    def to_internal_value(self, data):
        # SKUs are stored upper-case; accept any case like the catalog API does.
        if isinstance(data, dict) and isinstance(data.get("ingredient"), str):
            data = {**data, "ingredient": data["ingredient"].strip().upper()}
        return super().to_internal_value(data)

    def create_input(self) -> LineInput:  # pragma: no cover - convenience, exercised via views
        return LineInput(**self.validated_data)


def _normalise_sku(value):
    return value.strip().upper() if isinstance(value, str) else value


class RecipeVersionCreateSerializer(serializers.Serializer):
    product = serializers.SlugRelatedField(slug_field="sku", queryset=Product.objects.all())
    yield_quantity = serializers.DecimalField(**QUANTITY_FIELD)
    yield_unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all())
    lines = RecipeLineWriteSerializer(many=True, required=False)

    def to_internal_value(self, data):
        if isinstance(data, dict) and "product" in data:
            data = {**data, "product": _normalise_sku(data["product"])}
        return super().to_internal_value(data)


class RecipeVersionUpdateSerializer(serializers.Serializer):
    """Used with ``partial=True``. ``lines`` replaces the whole line set."""

    yield_quantity = serializers.DecimalField(**QUANTITY_FIELD)
    yield_unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all())
    lines = RecipeLineWriteSerializer(many=True)


def line_inputs(items: list[dict]) -> list[LineInput]:
    return [LineInput(**item) for item in items]


class RequirementSerializer(serializers.Serializer):
    ingredient = serializers.CharField(source="ingredient.sku", read_only=True)
    ingredient_name = serializers.CharField(source="ingredient.name", read_only=True)
    base_unit = serializers.CharField(source="base_unit.code", read_only=True)
    net_quantity = serializers.DecimalField(max_digits=14, decimal_places=4)
    gross_quantity = serializers.DecimalField(max_digits=14, decimal_places=4)


def requirements_payload(requirements: list[Requirement]) -> list[dict]:
    return RequirementSerializer(requirements, many=True).data

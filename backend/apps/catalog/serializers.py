from decimal import Decimal

from django.core.validators import RegexValidator
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import (
    ALLERGEN_CODE_PATTERN,
    CURRENCY_PATTERN,
    SKU_PATTERN,
    Allergen,
    Ingredient,
    IngredientAllergen,
    Product,
    Unit,
    normalize_currency,
    normalize_sku,
)

SKU_VALIDATOR = RegexValidator(
    SKU_PATTERN, message="SKU must be 2-40 characters: A-Z, 0-9, '_' or '-'."
)


class SkuField(serializers.CharField):
    """Strips and upper-cases the SKU before validators (incl. uniqueness) run."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 40)
        kwargs.setdefault("validators", [SKU_VALIDATOR])
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        return normalize_sku(super().to_internal_value(data))


class CurrencyField(serializers.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault("min_length", 3)
        kwargs.setdefault("max_length", 3)
        kwargs.setdefault(
            "validators",
            [RegexValidator(CURRENCY_PATTERN, message="Must be a 3-letter ISO 4217 code.")],
        )
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        return normalize_currency(super().to_internal_value(data))


def unique_sku_field(model) -> SkuField:
    return SkuField(
        validators=[
            SKU_VALIDATOR,
            UniqueValidator(
                queryset=model.objects.all(), message="An item with this SKU already exists."
            ),
        ]
    )


class WriteGuardMixin:
    """Rejects writes to fields that must not be written through a plain body.

    * ``is_active`` changes only through the activate/deactivate actions (09 §3).
    * ``immutable_fields`` may be echoed back unchanged but never changed.
    """

    immutable_fields: tuple[str, ...] = ()
    action_only_fields = {"is_active": "Use the activate/deactivate actions."}

    def current_values(self) -> dict[str, str]:
        return {}

    def validate(self, attrs):
        attrs = super().validate(attrs)
        initial = getattr(self, "initial_data", None) or {}
        errors: dict[str, list[str]] = {}
        for field, message in self.action_only_fields.items():
            if field in initial:
                errors[field] = [message]
        if self.instance is not None:
            current = self.current_values()
            for field in self.immutable_fields:
                if (
                    field in initial
                    and str(initial[field]).strip().lower() != current[field].lower()
                ):
                    errors[field] = ["This field cannot be changed after creation."]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


# --- Unit -----------------------------------------------------------------------------------
class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "code", "name", "dimension", "factor_to_base"]
        read_only_fields = fields


# --- Ingredient -----------------------------------------------------------------------------
class IngredientSerializer(serializers.ModelSerializer):
    base_unit = serializers.SlugRelatedField(slug_field="code", read_only=True)

    class Meta:
        model = Ingredient
        fields = ["id", "sku", "name", "base_unit", "is_active", "created_at", "updated_at"]
        read_only_fields = fields


class IngredientCreateSerializer(WriteGuardMixin, serializers.Serializer):
    sku = unique_sku_field(Ingredient)
    name = serializers.CharField(max_length=200)
    base_unit = serializers.SlugRelatedField(slug_field="code", queryset=Unit.objects.all())

    def validate_base_unit(self, unit: Unit) -> Unit:
        if not unit.is_base_unit:
            raise serializers.ValidationError(
                "Must be a base unit of its dimension (g, ml or pcs)."
            )
        return unit


class IngredientUpdateSerializer(WriteGuardMixin, serializers.Serializer):
    name = serializers.CharField(max_length=200)
    immutable_fields = ("sku", "base_unit")

    def current_values(self) -> dict[str, str]:
        return {"sku": self.instance.sku, "base_unit": self.instance.base_unit.code}


# --- Product --------------------------------------------------------------------------------
class ProductSerializer(serializers.ModelSerializer):
    """Customer-facing representation: no internal flags or timestamps."""

    class Meta:
        model = Product
        fields = ["id", "sku", "name", "description", "price", "currency"]
        read_only_fields = fields


class ProductAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "description",
            "price",
            "currency",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProductUpdateSerializer(WriteGuardMixin, serializers.Serializer):
    """Used with ``partial=True``: only the fields sent are changed."""

    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    currency = CurrencyField()
    immutable_fields = ("sku",)

    def current_values(self) -> dict[str, str]:
        return {"sku": self.instance.sku}


class ProductCreateSerializer(ProductUpdateSerializer):
    sku = unique_sku_field(Product)


# --- Allergens ------------------------------------------------------------------------------
class AllergenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Allergen
        fields = ["id", "code", "name", "is_active", "created_at", "updated_at"]
        read_only_fields = fields


class AllergenUpdateSerializer(WriteGuardMixin, serializers.Serializer):
    name = serializers.CharField(max_length=100)
    immutable_fields = ("code",)

    def current_values(self) -> dict[str, str]:
        return {"code": self.instance.code}


class _AllergenCodeField(serializers.CharField):
    def to_internal_value(self, data):
        return super().to_internal_value(data).strip().lower()


class AllergenCreateSerializer(AllergenUpdateSerializer):
    code = _AllergenCodeField(
        max_length=32,
        validators=[
            RegexValidator(
                ALLERGEN_CODE_PATTERN,
                message="Code must be 2-32 characters: a-z, 0-9, '_', starting with a letter.",
            ),
            UniqueValidator(
                queryset=Allergen.objects.all(), message="An allergen with this code exists."
            ),
        ],
    )


class IngredientAllergenSerializer(serializers.ModelSerializer):
    allergen = serializers.SlugRelatedField(slug_field="code", read_only=True)
    name = serializers.CharField(source="allergen.name", read_only=True)

    class Meta:
        model = IngredientAllergen
        fields = ["allergen", "name", "presence"]
        read_only_fields = fields


class IngredientAllergenEntrySerializer(serializers.Serializer):
    allergen = serializers.SlugRelatedField(slug_field="code", queryset=Allergen.objects.all())
    presence = serializers.ChoiceField(choices=IngredientAllergen.Presence.choices)


class IngredientAllergenSetSerializer(serializers.Serializer):
    """Full replacement of the ingredient's allergen declaration (empty list clears it)."""

    allergens = IngredientAllergenEntrySerializer(many=True)

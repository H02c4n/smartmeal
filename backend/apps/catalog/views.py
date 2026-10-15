"""Catalog API (03_API_CONTRACTS "Katalog ve reçete").

Public read endpoints need only authentication. Admin endpoints use ``IsCatalogAdmin``
(placeholder, see permissions.py). Nothing here deletes rows or writes ``is_active`` directly;
activation is an explicit action. All writes go through ``catalog.services``.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import selectors, services
from .models import Allergen, Ingredient, Product, Unit
from .permissions import IsCatalogAdmin
from .serializers import (
    AllergenCreateSerializer,
    AllergenSerializer,
    AllergenUpdateSerializer,
    IngredientAllergenSerializer,
    IngredientAllergenSetSerializer,
    IngredientCreateSerializer,
    IngredientSerializer,
    IngredientUpdateSerializer,
    ProductAdminSerializer,
    ProductCreateSerializer,
    ProductSerializer,
    ProductUpdateSerializer,
    UnitSerializer,
)

Q_PARAM = OpenApiParameter(
    "q", OpenApiTypes.STR, description="Case-insensitive match on SKU or name."
)
IS_ACTIVE_PARAM = OpenApiParameter(
    "is_active", OpenApiTypes.BOOL, description="Filter by active flag (true/false)."
)


def _parse_is_active(request) -> bool | None:
    raw = request.query_params.get("is_active")
    if raw is None or raw == "":
        return None
    value = raw.strip().lower()
    if value in {"true", "1"}:
        return True
    if value in {"false", "0"}:
        return False
    raise ValidationError({"is_active": ["Must be true or false."]})


def _is_schema_generation(view) -> bool:
    return getattr(view, "swagger_fake_view", False)


# --- Public ---------------------------------------------------------------------------------
@extend_schema_view(list=extend_schema(parameters=[Q_PARAM]))
class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """Active products. Inactive products are hidden (404), including from detail lookups."""

    permission_classes = [IsAuthenticated]
    serializer_class = ProductSerializer

    def get_queryset(self):
        if _is_schema_generation(self):
            return Product.objects.none()
        return selectors.active_products(q=self.request.query_params.get("q"))


# --- Admin: units ---------------------------------------------------------------------------
class AdminUnitViewSet(viewsets.ReadOnlyModelViewSet):
    """The unit dictionary is reference data: read-only, changed only by migration."""

    permission_classes = [IsCatalogAdmin]
    serializer_class = UnitSerializer
    queryset = Unit.objects.all()


# --- Admin: products ------------------------------------------------------------------------
@extend_schema_view(list=extend_schema(parameters=[Q_PARAM, IS_ACTIVE_PARAM]))
class AdminProductViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsCatalogAdmin]
    serializer_class = ProductAdminSerializer

    def get_queryset(self):
        if _is_schema_generation(self):
            return Product.objects.none()
        if self.action == "list":
            return selectors.admin_products(
                q=self.request.query_params.get("q"), is_active=_parse_is_active(self.request)
            )
        return Product.objects.all()

    @extend_schema(request=ProductCreateSerializer, responses={201: ProductAdminSerializer})
    def create(self, request):
        serializer = ProductCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = services.create_product(**serializer.validated_data)
        return Response(ProductAdminSerializer(product).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ProductUpdateSerializer, responses={200: ProductAdminSerializer})
    def partial_update(self, request, pk=None):
        product = self.get_object()
        serializer = ProductUpdateSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        product = services.update_product(product, **serializer.validated_data)
        return Response(ProductAdminSerializer(product).data)

    @extend_schema(request=None, responses={200: ProductAdminSerializer})
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        product = services.set_product_active(self.get_object(), True)
        return Response(ProductAdminSerializer(product).data)

    @extend_schema(request=None, responses={200: ProductAdminSerializer})
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        product = services.set_product_active(self.get_object(), False)
        return Response(ProductAdminSerializer(product).data)


# --- Admin: ingredients ---------------------------------------------------------------------
@extend_schema_view(list=extend_schema(parameters=[Q_PARAM, IS_ACTIVE_PARAM]))
class AdminIngredientViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsCatalogAdmin]
    serializer_class = IngredientSerializer

    def get_queryset(self):
        if _is_schema_generation(self):
            return Ingredient.objects.none()
        if self.action == "list":
            return selectors.admin_ingredients(
                q=self.request.query_params.get("q"), is_active=_parse_is_active(self.request)
            )
        return Ingredient.objects.select_related("base_unit")

    @extend_schema(request=IngredientCreateSerializer, responses={201: IngredientSerializer})
    def create(self, request):
        serializer = IngredientCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ingredient = services.create_ingredient(**serializer.validated_data)
        return Response(IngredientSerializer(ingredient).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=IngredientUpdateSerializer, responses={200: IngredientSerializer})
    def partial_update(self, request, pk=None):
        ingredient = self.get_object()
        serializer = IngredientUpdateSerializer(ingredient, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        ingredient = services.update_ingredient(ingredient, **serializer.validated_data)
        return Response(IngredientSerializer(ingredient).data)

    @extend_schema(request=None, responses={200: IngredientSerializer})
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        ingredient = services.set_ingredient_active(self.get_object(), True)
        return Response(IngredientSerializer(ingredient).data)

    @extend_schema(request=None, responses={200: IngredientSerializer})
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        ingredient = services.set_ingredient_active(self.get_object(), False)
        return Response(IngredientSerializer(ingredient).data)

    @extend_schema(responses={200: IngredientAllergenSerializer(many=True)})
    @action(detail=True, methods=["get", "put"], url_path="allergens")
    def allergens(self, request, pk=None):
        """GET: the declared allergens. PUT: replace the whole declaration atomically."""
        ingredient = self.get_object()
        if request.method == "PUT":
            serializer = IngredientAllergenSetSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            links = services.set_ingredient_allergens(
                ingredient,
                [(e["allergen"], e["presence"]) for e in serializer.validated_data["allergens"]],
            )
        else:
            links = selectors.ingredient_allergen_links(ingredient)
        return Response(IngredientAllergenSerializer(links, many=True).data)


# --- Admin: allergens -----------------------------------------------------------------------
@extend_schema_view(list=extend_schema(parameters=[IS_ACTIVE_PARAM]))
class AdminAllergenViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsCatalogAdmin]
    serializer_class = AllergenSerializer

    def get_queryset(self):
        if _is_schema_generation(self):
            return Allergen.objects.none()
        if self.action == "list":
            return selectors.allergens(is_active=_parse_is_active(self.request))
        return Allergen.objects.all()

    @extend_schema(request=AllergenCreateSerializer, responses={201: AllergenSerializer})
    def create(self, request):
        serializer = AllergenCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        allergen = services.create_allergen(**serializer.validated_data)
        return Response(AllergenSerializer(allergen).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=AllergenUpdateSerializer, responses={200: AllergenSerializer})
    def partial_update(self, request, pk=None):
        allergen = self.get_object()
        serializer = AllergenUpdateSerializer(allergen, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        allergen = services.update_allergen(allergen, **serializer.validated_data)
        return Response(AllergenSerializer(allergen).data)

    @extend_schema(request=None, responses={200: AllergenSerializer})
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return Response(
            AllergenSerializer(services.set_allergen_active(self.get_object(), True)).data
        )

    @extend_schema(request=None, responses={200: AllergenSerializer})
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        return Response(
            AllergenSerializer(services.set_allergen_active(self.get_object(), False)).data
        )

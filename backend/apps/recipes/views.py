"""Recipe API (03_API_CONTRACTS "Katalog ve reçete").

Admin-only for now: uses the placeholder ``IsCatalogAdmin`` until roles exist (ADR-009/010).
State changes are actions (``approve``/``retire``); ``status`` is never written through a body.
"""

from decimal import Decimal, InvalidOperation

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.catalog.models import Unit
from apps.catalog.permissions import IsCatalogAdmin

from . import selectors, services
from .models import RecipeVersion
from .serializers import (
    RecipeVersionCreateSerializer,
    RecipeVersionListSerializer,
    RecipeVersionSerializer,
    RecipeVersionUpdateSerializer,
    RequirementSerializer,
    line_inputs,
    requirements_payload,
)

PRODUCT_PARAM = OpenApiParameter("product", OpenApiTypes.STR, description="Filter by product SKU.")
STATUS_PARAM = OpenApiParameter(
    "status", OpenApiTypes.STR, description="Filter by status: draft, approved or retired."
)
QUANTITY_PARAM = OpenApiParameter(
    "quantity", OpenApiTypes.STR, required=True, description="Amount of product to make (decimal)."
)
UNIT_PARAM = OpenApiParameter(
    "unit", OpenApiTypes.STR, required=True, description="Unit code, same dimension as the yield."
)


@extend_schema_view(list=extend_schema(parameters=[PRODUCT_PARAM, STATUS_PARAM]))
class AdminRecipeVersionViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsCatalogAdmin]

    def get_serializer_class(self):
        return RecipeVersionListSerializer if self.action == "list" else RecipeVersionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return RecipeVersion.objects.none()
        if self.action == "list":
            status_filter = self.request.query_params.get("status")
            if status_filter and status_filter not in RecipeVersion.Status.values:
                raise ValidationError({"status": ["Must be draft, approved or retired."]})
            return selectors.recipe_versions(
                product_sku=self.request.query_params.get("product"), status=status_filter
            )
        return selectors.detailed_recipe_version_queryset()

    def _respond(self, version, code=status.HTTP_200_OK):
        fresh = selectors.detailed_recipe_version_queryset().get(pk=version.pk)
        return Response(RecipeVersionSerializer(fresh).data, status=code)

    @extend_schema(request=RecipeVersionCreateSerializer, responses={201: RecipeVersionSerializer})
    def create(self, request):
        serializer = RecipeVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        version = services.create_recipe_version(
            product=data["product"],
            yield_quantity=data["yield_quantity"],
            yield_unit=data["yield_unit"],
            lines=line_inputs(data.get("lines", [])),
        )
        return self._respond(version, status.HTTP_201_CREATED)

    @extend_schema(request=RecipeVersionUpdateSerializer, responses={200: RecipeVersionSerializer})
    def partial_update(self, request, pk=None):
        version = self.get_object()
        serializer = RecipeVersionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        version = services.update_recipe_version(
            version,
            yield_quantity=data.get("yield_quantity"),
            yield_unit=data.get("yield_unit"),
            lines=line_inputs(data["lines"]) if "lines" in data else None,
        )
        return self._respond(version)

    @extend_schema(request=None, responses={200: RecipeVersionSerializer})
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        version = services.approve_recipe_version(self.get_object(), actor=request.user)
        return self._respond(version)

    @extend_schema(request=None, responses={200: RecipeVersionSerializer})
    @action(detail=True, methods=["post"])
    def retire(self, request, pk=None):
        version = services.retire_recipe_version(self.get_object(), actor=request.user)
        return self._respond(version)

    @extend_schema(
        parameters=[QUANTITY_PARAM, UNIT_PARAM], responses={200: RequirementSerializer(many=True)}
    )
    @action(detail=True, methods=["get"])
    def requirements(self, request, pk=None):
        """Ingredient needs (base units) to make the given amount of the product."""
        raw_quantity = request.query_params.get("quantity")
        unit_code = request.query_params.get("unit")
        errors = {}
        quantity = None
        try:
            quantity = Decimal(raw_quantity) if raw_quantity else None
            if quantity is not None and not quantity.is_finite():
                quantity = None
        except InvalidOperation:
            quantity = None
        if quantity is None:
            errors["quantity"] = ["A decimal quantity is required."]
        unit = Unit.objects.filter(code=(unit_code or "").strip().lower()).first()
        if unit is None:
            errors["unit"] = ["A valid unit code is required."]
        if errors:
            raise ValidationError(errors)
        results = services.calculate_requirements(self.get_object(), quantity=quantity, unit=unit)
        return Response(requirements_payload(results))

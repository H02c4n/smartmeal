from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

api_v1_patterns = [
    path("", include("apps.core.urls")),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api-v1:schema"), name="docs"),
]

urlpatterns = [
    # Django admin is a developer convenience only; the product admin is the Next.js app (ADR-003).
    path("django-admin/", admin.site.urls),
    path("api/v1/", include((api_v1_patterns, "api-v1"))),
]

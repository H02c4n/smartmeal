"""Local development (Docker Compose). Never use for staging or production."""

from .base import *  # noqa: F403

DEBUG = env.bool("DJANGO_DEBUG", default=True)  # noqa: F405
ALLOWED_HOSTS = env.list(  # noqa: F405
    "DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]", "backend"]
)

# The OpenAPI schema and Swagger UI are open in local development only.
SPECTACULAR_SETTINGS = {
    **SPECTACULAR_SETTINGS,  # noqa: F405
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
}

# Plain-http local development: cookies cannot be Secure (production defaults to Secure).
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

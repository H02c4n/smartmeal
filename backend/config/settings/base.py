"""Settings shared by every environment. Environment-specific files import from here."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Convenience for running commands on the host (outside Docker): load <repo>/.env if present.
# Real environment variables always win; in Docker/CI/production no .env file is mounted.
environ.Env.read_env(BASE_DIR.parent / ".env")

# --- Core -------------------------------------------------------------------
# No default: a missing secret must fail loudly, never fall back to a known value.
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "drf_spectacular",
    # SmartMeal modules (see docs/architecture/01_ARCHITECTURE.md)
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.recipes",
    "apps.purchasing",
    "apps.inventory",
    "apps.orders",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------
# Discrete variables instead of a URL so passwords never need URL-escaping.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": env.int("POSTGRES_CONN_MAX_AGE", default=0),
        "ATOMIC_REQUESTS": False,  # transaction boundaries are explicit (09_CODE_STANDARDS §2)
    }
}

# Django's own tables keep BigAutoField. SmartMeal domain models use UUID primary keys
# through apps.core.models.UUIDTimestampedModel (ADR-007).
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth -------------------------------------------------------------------
# Must be defined before the first migration is ever created.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Session and CSRF cookies (ADR-013 §1). The session cookie is HttpOnly (Django default) and
# SameSite=Lax; both are Secure whenever DEBUG is off. The CSRF cookie must stay readable by the
# client script. Web and API are deployed under one registrable domain; list the web origins in
# DJANGO_CSRF_TRUSTED_ORIGINS (e.g. https://app.example.com).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = env.bool("DJANGO_CSRF_COOKIE_SECURE", default=not DEBUG)
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# --- i18n / time ------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"  # stored and served in UTC; clients localise
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Django REST Framework --------------------------------------------------
REST_FRAMEWORK = {
    # Deny by default: every endpoint must opt in to being public (05_SECURITY §1).
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # ADR-013: web clients use the server-side session cookie + CSRF; anonymous -> 401.
    # Mobile token authentication is added in Phase 6.
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.accounts.authentication.SessionAuthentication401"],
    "DEFAULT_THROTTLE_RATES": {
        "login_ip": env("LOGIN_THROTTLE_RATE_IP", default="20/min"),
        "login_email": env("LOGIN_THROTTLE_RATE_EMAIL", default="5/min"),
        "register_ip": env("REGISTER_THROTTLE_RATE_IP", default="5/hour"),
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SmartMeal API",
    "DESCRIPTION": "SmartMeal backend API. Draft contract: docs/architecture/03_API_CONTRACTS.md",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Several modules have a ``status`` field; give each choice set an explicit, stable name.
    "ENUM_NAME_OVERRIDES": {
        "RecipeVersionStatusEnum": "apps.recipes.models.RecipeVersion.Status",
        "PurchaseOrderStatusEnum": "apps.purchasing.models.PurchaseOrder.Status",
        "GoodsReceiptStatusEnum": "apps.purchasing.models.GoodsReceipt.Status",
        "ReservationStatusEnum": "apps.inventory.models.StockReservation.Status",
        "LotQualityStatusEnum": "apps.inventory.models.InventoryLot.QualityStatus",
        "StockMovementTypeEnum": "apps.inventory.models.StockMovement.Type",
        "OrderStatusEnum": "apps.orders.models.Order.Status",
    },
    # Schema is not public by default; local settings relax this.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
}

# --- Orders (ADR-014) -------------------------------------------------------------------------
# PROVISIONAL product assumptions (00 §8): confirm or change per business decision.
ORDER_MIN_LEAD_DAYS = env.int("ORDER_MIN_LEAD_DAYS", default=1)  # earliest delivery: today + N
# A customer may cancel while delivery is at least N days away; staff are not bound by this.
ORDER_CUSTOMER_CANCEL_MIN_DAYS = env.int("ORDER_CUSTOMER_CANCEL_MIN_DAYS", default=1)
# Abuse guards (not business rules): keep one request's reservation work bounded.
ORDER_MAX_LINES = env.int("ORDER_MAX_LINES", default=30)
ORDER_MAX_LINE_QUANTITY = env.int("ORDER_MAX_LINE_QUANTITY", default=100)
ADDRESS_MAX_PER_CUSTOMER = env.int("ADDRESS_MAX_PER_CUSTOMER", default=10)

# --- Logging ----------------------------------------------------------------
# Every record carries request_id (01_ARCHITECTURE §7). Never log passwords, tokens
# or payment data.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.logging.RequestIdFilter"}},
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
}

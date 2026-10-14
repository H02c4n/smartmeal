"""Guards for Phase 0 foundations that are easy to break silently."""

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection

from apps.core.models import UUIDTimestampedModel


@pytest.mark.django_db
def test_no_pending_model_changes():
    # Fails if a model changed without a migration (09_CODE_STANDARDS §2).
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)


def test_database_engine_is_postgresql():
    assert connection.vendor == "postgresql"


def test_rest_framework_denies_by_default():
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]


def test_timezone_support_is_on():
    assert settings.USE_TZ is True


def test_openapi_schema_generates_without_warnings():
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", "/dev/null")


def test_uuid_base_model_is_abstract_with_uuid_pk():
    assert UUIDTimestampedModel._meta.abstract is True
    assert UUIDTimestampedModel._meta.pk.get_internal_type() == "UUIDField"


@pytest.mark.django_db
def test_core_has_no_tables_of_its_own():
    from django.apps import apps

    assert list(apps.get_app_config("core").get_models()) == []

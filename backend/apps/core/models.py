import uuid

from django.db import models


class UUIDTimestampedModel(models.Model):
    """Abstract base for SmartMeal domain models (ADR-007, 02_DATA_MODEL §1).

    UUID primary key plus timezone-aware ``created_at`` / ``updated_at``.
    Note: ``QuerySet.update()`` and ``bulk_update()`` do not touch ``updated_at``
    automatically; include it explicitly when using them.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

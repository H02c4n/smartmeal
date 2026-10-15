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


class IdempotencyRecord(UUIDTimestampedModel):
    """Remembers the outcome of a mutating request so a retry cannot repeat its effect.

    One row per (scope, key, actor): ``scope`` names the operation (``"goods_receipt.create"``),
    ``key`` is the client's ``Idempotency-Key``. ``request_hash`` fingerprints the request body;
    the same key with a different body is rejected (``IDEMPOTENCY_CONFLICT``). The row stores a
    reference to the created resource (``resource_id``), not a response copy, so replays return
    the current state of that resource. See ``apps.core.idempotency``.
    """

    scope = models.CharField(max_length=64)
    key = models.CharField(max_length=128)
    actor = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    request_hash = models.CharField(max_length=64)
    resource_id = models.UUIDField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "core_idempotency_record"
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "key", "actor"], name="core_idempotency_unique_scope_key_actor"
            ),
        ]
        indexes = [models.Index(fields=["expires_at"], name="core_idempotency_expires_idx")]

    def __str__(self) -> str:
        return f"{self.scope}:{self.key}"

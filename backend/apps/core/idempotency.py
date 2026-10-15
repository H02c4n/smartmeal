"""Idempotent execution of create-style operations (05_SECURITY §2/§5, 09 §3).

Usage in a view::

    instance, created = run_idempotent(
        scope="goods_receipt.create", key=request_key(request), actor=request.user,
        fingerprint=serializer.validated_data, create=lambda: services.receive(...),
        load=lambda pk: GoodsReceipt.objects.get(pk=pk),
    )
    return Response(..., status=201 if created else 200)

* First call: ``create()`` runs in the same transaction as the idempotency row, so either both
  are committed or neither is (a failed attempt leaves no record and can be retried).
* Repeat with the same key and body: ``load(resource_id)`` returns the already created resource,
  ``created`` is False and nothing is executed twice.
* Same key, different body: ``IdempotencyConflict`` (409).
* Two simultaneous requests with one key: the unique index makes the second wait for the first;
  after the first commits it sees the stored result.
"""

import hashlib
import json
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .api_errors import Conflict, IdempotencyConflict
from .models import IdempotencyRecord

KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
RETENTION = timedelta(days=7)


def request_key(request, *, required: bool = True) -> str | None:
    """Read and validate the ``Idempotency-Key`` header."""
    key = request.headers.get("Idempotency-Key")
    if key is None or key == "":
        if required:
            raise ValidationError(
                {"Idempotency-Key": ["This header is required for this operation."]}
            )
        return None
    if not KEY_PATTERN.fullmatch(key):
        raise ValidationError(
            {"Idempotency-Key": ["Use 8-128 characters: letters, digits, '.', '_', ':' or '-'."]}
        )
    return key


def fingerprint_of(payload) -> str:
    """Stable hash of a request payload (order of keys does not matter)."""
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def run_idempotent(*, scope: str, key: str | None, actor, fingerprint, create, load):
    """Run ``create`` at most once per (scope, key, actor); returns ``(instance, created)``."""
    if key is None:
        return create(), True
    request_hash = fingerprint_of(fingerprint)
    with transaction.atomic():
        try:
            with transaction.atomic():  # savepoint: a duplicate key must not poison the outer one
                record = IdempotencyRecord.objects.create(
                    scope=scope,
                    key=key,
                    actor=actor,
                    request_hash=request_hash,
                    expires_at=timezone.now() + RETENTION,
                )
        except IntegrityError:
            record = IdempotencyRecord.objects.get(scope=scope, key=key, actor=actor)
            if record.request_hash != request_hash:
                raise IdempotencyConflict() from None
            if record.resource_id is None:  # pragma: no cover - cannot be committed half-done
                raise Conflict("The original request is still being processed.") from None
            return load(record.resource_id), False
        instance = create()
        record.resource_id = instance.pk
        record.save(update_fields=["resource_id", "updated_at"])
        return instance, True


def purge_expired(now=None) -> int:
    """Delete records past their retention; returns how many were removed."""
    deleted, _ = IdempotencyRecord.objects.filter(expires_at__lte=now or timezone.now()).delete()
    return deleted

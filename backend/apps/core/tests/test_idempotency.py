from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.core.api_errors import IdempotencyConflict
from apps.core.idempotency import (
    fingerprint_of,
    purge_expired,
    request_key,
    run_idempotent,
)
from apps.core.models import IdempotencyRecord

pytestmark = pytest.mark.django_db


class Box:
    """Stand-in for a created resource."""

    counter = 0

    def __init__(self):
        import uuid

        Box.counter += 1
        self.pk = uuid.uuid4()


def run(user, key="key-12345678", payload=None, scope="t.create", calls=None, store=None):
    store = {} if store is None else store

    def create():
        if calls is not None:
            calls.append(1)
        box = Box()
        store[box.pk] = box
        return box

    return run_idempotent(
        scope=scope,
        key=key,
        actor=user,
        fingerprint=payload or {"a": 1},
        create=create,
        load=lambda pk: store[pk],
    ), store


def test_first_call_creates_and_repeat_replays(user):
    calls: list = []
    (first, created_first), store = run(user, calls=calls)
    (again, created_again), _ = run(user, calls=calls, store=store)
    assert created_first is True and created_again is False
    assert again is first
    assert len(calls) == 1
    assert IdempotencyRecord.objects.count() == 1


def test_same_key_different_body_is_a_conflict(user):
    (_, _), store = run(user, payload={"a": 1})
    with pytest.raises(IdempotencyConflict):
        run(user, payload={"a": 2}, store=store)


def test_key_order_in_body_does_not_matter():
    assert fingerprint_of({"a": 1, "b": [1, 2]}) == fingerprint_of({"b": [1, 2], "a": 1})
    assert fingerprint_of({"a": Decimal("1.0")}) != fingerprint_of({"a": Decimal("2.0")})


def test_keys_are_scoped_per_actor_and_per_operation(user, staff_user):
    calls: list = []
    run(user, calls=calls)
    run(staff_user, calls=calls)  # another actor may reuse the key
    run(user, scope="other.create", calls=calls)  # another operation may reuse the key
    assert len(calls) == 3


def test_failed_create_leaves_no_record_so_the_retry_runs_again(user):
    def boom():
        raise ValueError("fails")

    with pytest.raises(ValueError):
        run_idempotent(
            scope="t.create",
            key="key-12345678",
            actor=user,
            fingerprint={},
            create=boom,
            load=lambda pk: None,
        )
    assert IdempotencyRecord.objects.count() == 0
    (_, created), _ = run(user)
    assert created is True


def test_without_a_key_nothing_is_remembered(user):
    calls: list = []
    for _ in range(2):
        run_idempotent(
            scope="t.create",
            key=None,
            actor=user,
            fingerprint={},
            create=lambda: (calls.append(1), Box())[1],
            load=lambda pk: None,
        )
    assert len(calls) == 2
    assert IdempotencyRecord.objects.count() == 0


@pytest.mark.parametrize("key", ["short", "has space 123", "x" * 129, "ünicode-key-1"])
def test_invalid_keys_are_rejected(key):
    request = APIRequestFactory().post("/", HTTP_IDEMPOTENCY_KEY=key)
    with pytest.raises(ValidationError):
        request_key(request)


def test_missing_key_is_rejected_when_required_and_allowed_when_optional():
    request = APIRequestFactory().post("/")
    with pytest.raises(ValidationError):
        request_key(request)
    assert request_key(request, required=False) is None
    ok = APIRequestFactory().post("/", HTTP_IDEMPOTENCY_KEY="abc-12345678")
    assert request_key(ok) == "abc-12345678"


def test_expired_records_are_purged(user):
    run(user)
    assert purge_expired() == 0
    assert purge_expired(timezone.now() + timedelta(days=8)) == 1
    assert User.objects.count() == 1

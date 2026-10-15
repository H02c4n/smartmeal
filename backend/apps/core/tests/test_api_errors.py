import pytest

from apps.core.api_errors import (
    Conflict,
    IdempotencyConflict,
    InsufficientStock,
    InvalidStateTransition,
    LotBlocked,
)
from apps.core.exceptions import api_exception_handler


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (Conflict(), "CONFLICT"),
        (InvalidStateTransition(), "INVALID_STATE_TRANSITION"),
        (InsufficientStock(), "INSUFFICIENT_STOCK"),
        (LotBlocked(), "LOT_BLOCKED"),
        (IdempotencyConflict(), "IDEMPOTENCY_CONFLICT"),
    ],
)
def test_business_errors_map_to_contract_codes_with_409(exc, code):
    response = api_exception_handler(exc, {})
    assert response.status_code == 409
    error = response.data["error"]
    assert error["code"] == code
    assert error["message"]
    assert "details" not in error


def test_extra_is_rendered_as_details():
    exc = InsufficientStock("Not enough.", extra={"requested": "5.0000", "available": "2.0000"})
    error = api_exception_handler(exc, {}).data["error"]
    assert error["message"] == "Not enough."
    assert error["details"] == {"requested": "5.0000", "available": "2.0000"}

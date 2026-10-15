"""Shared business-rule errors with stable API codes (03_API_CONTRACTS §2).

Each class maps to one ``error.code`` through its ``default_code`` (upper-cased by the error
envelope). ``extra`` (optional) is rendered as ``error.details``; keep it free of personal data.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class BusinessRuleError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"

    def __init__(self, detail=None, *, extra: dict | None = None):
        super().__init__(detail)
        self.extra = extra


class Conflict(BusinessRuleError):
    default_code = "conflict"


class InvalidStateTransition(BusinessRuleError):
    default_detail = "This state transition is not allowed."
    default_code = "invalid_state_transition"


class InsufficientStock(BusinessRuleError):
    default_detail = "Not enough available stock."
    default_code = "insufficient_stock"


class LotBlocked(BusinessRuleError):
    default_detail = "The lot cannot be used for quality reasons."
    default_code = "lot_blocked"


class IdempotencyConflict(BusinessRuleError):
    default_detail = "This idempotency key was already used with a different request."
    default_code = "idempotency_conflict"

from rest_framework.exceptions import ValidationError


class ImmutableFieldError(ValueError):
    """An immutable field (e.g. SKU, ingredient base unit) was changed after creation."""


class UnitConversionError(ValidationError):
    """A quantity cannot be converted (incompatible dimensions, missing/ambiguous conversion).

    Subclasses DRF's ``ValidationError`` so the API error envelope renders it as
    ``VALIDATION_ERROR`` (03_API_CONTRACTS §2) wherever it is raised from a request.
    """

    def __init__(self, message: str):
        super().__init__({"unit": [message]})

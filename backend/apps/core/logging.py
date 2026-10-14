import logging

from .request_id import get_request_id


class RequestIdFilter(logging.Filter):
    """Inject the current request_id into every log record ('-' outside a request)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True

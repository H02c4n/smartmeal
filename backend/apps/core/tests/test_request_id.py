import logging
import uuid

import pytest

pytestmark = pytest.mark.django_db

URL = "/api/v1/health/"


def test_response_has_generated_request_id(api_client):
    response = api_client.get(URL)
    rid = response["X-Request-ID"]
    assert uuid.UUID(rid)


def test_valid_incoming_request_id_is_echoed(api_client):
    response = api_client.get(URL, HTTP_X_REQUEST_ID="client-req-12345")
    assert response["X-Request-ID"] == "client-req-12345"


@pytest.mark.parametrize("bad", ["short", "has spaces in it!!", "x" * 65, "log\\injection-attempt"])
def test_invalid_incoming_request_id_is_replaced(api_client, bad):
    response = api_client.get(URL, HTTP_X_REQUEST_ID=bad)
    assert response["X-Request-ID"] != bad
    assert uuid.UUID(response["X-Request-ID"])


def test_each_request_gets_its_own_id(api_client):
    first = api_client.get(URL)["X-Request-ID"]
    second = api_client.get(URL)["X-Request-ID"]
    assert first != second


def test_log_records_carry_request_id(api_client, monkeypatch):
    from apps.core import views
    from apps.core.logging import RequestIdFilter

    class Broken:
        def cursor(self):
            from django.db import OperationalError

            raise OperationalError("db down")

    monkeypatch.setattr(views, "connection", Broken())
    captured = []

    class Capture(logging.Handler):
        def emit(self, record):
            captured.append(record)

    handler = Capture()
    handler.addFilter(RequestIdFilter())
    logging.getLogger("apps.core.views").addHandler(handler)
    try:
        api_client.get(URL, HTTP_X_REQUEST_ID="trace-me-123456")
    finally:
        logging.getLogger("apps.core.views").removeHandler(handler)

    assert captured and captured[0].request_id == "trace-me-123456"


def test_filter_uses_dash_outside_a_request():
    from apps.core.logging import RequestIdFilter

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    RequestIdFilter().filter(record)
    assert record.request_id == "-"

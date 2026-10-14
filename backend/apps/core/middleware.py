import re
import uuid

from .request_id import REQUEST_ID_HEADER, reset_request_id, set_request_id

# Client-supplied ids are accepted only in a conservative format so they are safe to log.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")


class RequestIdMiddleware:
    """Attach a request_id to every request, log record, error body and response header."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else str(uuid.uuid4())
        request.request_id = request_id

        token = set_request_id(request_id)
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)

        response[REQUEST_ID_HEADER] = request_id
        return response

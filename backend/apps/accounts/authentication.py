from rest_framework.authentication import SessionAuthentication


class SessionAuthentication401(SessionAuthentication):
    """Session cookie authentication that answers 401 (not 403) when no session is present.

    DRF turns ``NotAuthenticated`` into 403 unless the first authenticator provides a
    ``WWW-Authenticate`` value; ``Session`` is a non-challenging scheme name, so browsers show
    no login dialog (ADR-013 §3). CSRF is enforced for authenticated session requests.
    """

    def authenticate_header(self, request) -> str:
        return "Session"


class CsrfEnforcedSessionAuthentication(SessionAuthentication401):
    """Like the above, but CSRF is checked even for anonymous requests (used by login)."""

    def authenticate(self, request):
        self.enforce_csrf(request)
        return super().authenticate(request)

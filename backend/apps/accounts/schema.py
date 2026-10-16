"""OpenAPI description of the session-cookie authentication classes (loaded in ``ready``)."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SessionAuthentication401Scheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.SessionAuthentication401"
    match_subclasses = True
    name = "cookieAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "sessionid",
            "description": "Server-side session (log in via POST /auth/login/). Unsafe methods "
            "also need the X-CSRFToken header (GET /auth/csrf/).",
        }

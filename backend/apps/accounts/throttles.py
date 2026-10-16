"""Login attempt rate limits (ADR-013 §3).

Two independent limits: per client address (spraying many accounts) and per target e-mail
(guessing one account's password from many addresses). Counters use Django's cache; with more
than one backend process a shared cache (Redis) is required for the limits to hold.
"""

from rest_framework.throttling import SimpleRateThrottle

from .managers import normalize_email


class LoginIpThrottle(SimpleRateThrottle):
    scope = "login_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginEmailThrottle(SimpleRateThrottle):
    scope = "login_email"

    def get_cache_key(self, request, view):
        email = request.data.get("email") if hasattr(request.data, "get") else None
        if not isinstance(email, str) or not email.strip():
            return None  # nothing to key on; the per-IP limit still applies
        return self.cache_format % {"scope": self.scope, "ident": normalize_email(email)}


class RegisterIpThrottle(SimpleRateThrottle):
    """Registration per client address: it is the only defence against address harvesting."""

    scope = "register_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}

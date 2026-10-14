"""ASGI entry point. See wsgi.py for why there is no settings default."""

import os

from django.core.asgi import get_asgi_application

if "DJANGO_SETTINGS_MODULE" not in os.environ:
    raise RuntimeError("DJANGO_SETTINGS_MODULE must be set explicitly.")

application = get_asgi_application()

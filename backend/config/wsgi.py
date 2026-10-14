"""WSGI entry point.

DJANGO_SETTINGS_MODULE intentionally has no default here: a deployment must
state explicitly which settings it runs with.
"""

import os

from django.core.wsgi import get_wsgi_application

if "DJANGO_SETTINGS_MODULE" not in os.environ:
    raise RuntimeError("DJANGO_SETTINGS_MODULE must be set explicitly.")

application = get_wsgi_application()

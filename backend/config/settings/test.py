"""Test settings: isolated database (pytest-django creates test_<name>), fast hashing."""

from .base import *  # noqa: F403

SECRET_KEY = "test-only-secret-key-not-used-anywhere-else"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]

# Speed only; production keeps Django's default (PBKDF2) hashers.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LOGGING["root"]["level"] = "WARNING"  # noqa: F405

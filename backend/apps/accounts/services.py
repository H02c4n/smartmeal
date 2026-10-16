"""Account creation (ADR-015). The only place customers are registered."""

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from .managers import normalize_email
from .models import RoleAssignment, User
from .roles import Role

EMAIL_TAKEN_MESSAGE = "An account with this email address may already exist."


def register_customer(*, email: str, password: str, phone: str = "") -> User:
    """Create an active user holding only the ``CUSTOMER`` role.

    A duplicate e-mail is reported as a validation error. Until e-mail verification exists
    (Phase 6 notifications) registration cannot hide that an address is registered, so the
    endpoint is rate limited instead. The duplicate path still hashes the password so response
    time does not reveal the difference.
    """
    email = normalize_email(email)
    if User.objects.filter(email=email).exists():
        make_password(password)
        raise ValidationError({"email": [EMAIL_TAKEN_MESSAGE]})
    try:
        with transaction.atomic():
            user = User.objects.create_user(email, password, phone=phone)
            RoleAssignment.objects.create(user=user, role_code=Role.CUSTOMER)
    except IntegrityError:  # a parallel request registered the same address first
        raise ValidationError({"email": [EMAIL_TAKEN_MESSAGE]}) from None
    return user

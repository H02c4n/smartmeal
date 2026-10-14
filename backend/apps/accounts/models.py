from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import UUIDTimestampedModel

from .managers import UserManager, normalize_email


class User(UUIDTimestampedModel, AbstractBaseUser, PermissionsMixin):
    """SmartMeal user (02_DATA_MODEL §2).

    * Email is the login identifier. It is always stored lower-cased, so the plain
      ``unique=True`` constraint is effectively case-insensitive; a CHECK constraint
      enforces this at database level even for queryset ``update()`` calls.
    * ``password`` / ``last_login`` come from AbstractBaseUser (hashing is Django's).
    * Business roles are NOT modelled here; they will live in ``RoleAssignment``
      (separate task). ``is_staff`` only means "may open the Django admin"
      (developer tool); ``is_superuser`` is Django's all-permissions flag.
    """

    email = models.EmailField("email address", max_length=254, unique=True)
    phone = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        "staff status", default=False, help_text="Allows access to the Django admin site."
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        db_table = "accounts_user"
        ordering = ["email"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(email=Lower("email")),
                name="accounts_user_email_lowercase",
            ),
        ]

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        self.email = normalize_email(self.email)

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)

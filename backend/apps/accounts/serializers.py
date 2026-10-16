from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .managers import normalize_email
from .models import User


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField(max_length=254)
    password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)


class CsrfSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


class MeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    phone = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())
    permissions = serializers.ListField(child=serializers.CharField())


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)
    phone = serializers.RegexField(
        r"^\+?[0-9][0-9 ()-]{5,30}$",
        max_length=32,
        required=False,
        allow_blank=True,
        default="",
        error_messages={"invalid": "Enter a valid phone number, e.g. +46 70 123 45 67."},
    )

    def validate_email(self, value: str) -> str:
        return normalize_email(value)

    def validate(self, attrs):
        # Judged against the would-be user so "password similar to e-mail" is caught too.
        try:
            validate_password(attrs["password"], user=User(email=attrs["email"]))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from None
        return attrs

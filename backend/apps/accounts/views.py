"""Session authentication endpoints for web clients (ADR-013 §1, §3).

Login/logout use the server-side session cookie plus Django CSRF; no token is ever placed in
browser storage. Passwords and session identifiers are never logged or echoed.
"""

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api_errors import Conflict
from apps.core.permissions import user_permissions

from . import services
from .authentication import CsrfEnforcedSessionAuthentication
from .serializers import CsrfSerializer, LoginSerializer, MeSerializer, RegisterSerializer
from .throttles import LoginEmailThrottle, LoginIpThrottle, RegisterIpThrottle


def _me_payload(request) -> dict:
    user = request.user
    return {
        "id": user.pk,
        "email": user.email,
        "phone": user.phone,
        "roles": sorted(user.role_assignments.values_list("role_code", flat=True)),
        "permissions": sorted(user_permissions(request)),
    }


class CsrfView(APIView):
    """Hands the client a CSRF token (also set as the ``csrftoken`` cookie)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(operation_id="auth_csrf", auth=[], responses={200: CsrfSerializer})
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


class LoginView(APIView):
    """Start a session. The same message is returned for every kind of failure."""

    permission_classes = [AllowAny]
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    throttle_classes = [LoginIpThrottle, LoginEmailThrottle]

    @extend_schema(
        operation_id="auth_login",
        auth=[],
        request=LoginSerializer,
        responses={200: MeSerializer, 401: OpenApiResponse(description="Invalid credentials.")},
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=serializer.validated_data["email"].strip().lower(),
            password=serializer.validated_data["password"],
        )
        if user is None:  # unknown e-mail, wrong password and inactive account look identical
            raise AuthenticationFailed("Invalid email or password.")
        login(request, user)  # rotates the session key (no session fixation)
        return Response(_me_payload(request))


class RegisterView(APIView):
    """Create a customer account and sign it in (ADR-015).

    The body can never choose roles or flags: every new account holds exactly ``CUSTOMER``.
    """

    permission_classes = [AllowAny]
    authentication_classes = [CsrfEnforcedSessionAuthentication]
    throttle_classes = [RegisterIpThrottle]

    @extend_schema(
        operation_id="auth_register",
        auth=[],
        request=RegisterSerializer,
        responses={201: MeSerializer, 409: OpenApiResponse(description="Already signed in.")},
    )
    def post(self, request):
        if request.user.is_authenticated:
            raise Conflict("You are already signed in.")
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.register_customer(**serializer.validated_data)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(_me_payload(request), status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="auth_logout", request=None, responses={204: None})
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """The signed-in user with roles and the permissions those roles grant."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="me_retrieve", responses={200: MeSerializer})
    def get(self, request):
        return Response(_me_payload(request))

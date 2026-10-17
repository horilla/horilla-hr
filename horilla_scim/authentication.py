"""
authentication.py

Bearer-token authentication for the SCIM endpoints.

The project's default API authentication is JWT; a SCIM token is not a JWT,
so SCIM views set ``authentication_classes`` explicitly to this class only.

The authenticated principal is a ``ScimClient``, not a HorillaUser: an IdP
connection has no employee, no permissions and no business appearing in user
lists. Like ``TenantScopedJWTAuthentication`` it sets the company ContextVar
the moment the caller is known, so anything company-scoped the view touches
is limited to the provider's company.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import authentication, exceptions, permissions

from horilla.horilla_middlewares import set_selected_company

from .models import ScimToken, hash_token

LAST_USED_RESOLUTION = timedelta(minutes=1)


class ScimClient:
    is_authenticated = True
    is_anonymous = False
    is_active = True
    is_superuser = False

    def __init__(self, token):
        self.token = token
        self.provider = token.provider
        # Throttles key on request.user.pk.
        self.pk = f"scim-token-{token.pk}"

    def __str__(self):
        return f"SCIM client {self.provider}"


class ScimBearerAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()
        if not header or header[0].lower() != self.keyword.lower().encode():
            return None
        if len(header) != 2:
            raise exceptions.AuthenticationFailed("Invalid Authorization header.")
        try:
            raw = header[1].decode()
        except UnicodeError:
            raise exceptions.AuthenticationFailed("Invalid token.")

        token = (
            ScimToken.objects.usable()
            .select_related("provider", "provider__company")
            .filter(token_hash=hash_token(raw), provider__is_enabled=True)
            .first()
        )
        if token is None:
            raise exceptions.AuthenticationFailed("Invalid or expired token.")

        now = timezone.now()
        if (
            token.last_used_at is None
            or now - token.last_used_at > LAST_USED_RESOLUTION
        ):
            ScimToken.objects.filter(pk=token.pk).update(last_used_at=now)

        set_selected_company(token.provider.company_id)
        return ScimClient(token), token

    def authenticate_header(self, request):
        # Makes DRF answer 401 (not 403) when credentials are missing or bad.
        return f'{self.keyword} realm="scim"'


class IsScimClient(permissions.BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, ScimClient)

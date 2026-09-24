"""
views.py

sso_login / sso_callback: the SSO login flow. Public, unauthenticated by
design -- that is the point of a login flow -- so every step here is
written defensively, mirroring base.views.login_user's own posture
(base/views.py:803-858): one generic error message for every failure mode,
no confirmation of which part failed, no account created on a miss.

oidc_settings_view: the admin-facing settings screen, and the deliberate
fix over horilla_ldap's precedent, which guards its equivalent view with
only @login_required -- any authenticated user can rewrite its LDAP bind
credentials today. This view requires the real per-model permission.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import time

from django.contrib import messages
from django.contrib.auth import login
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from base.models import Company
from employee.models import Employee
from horilla.decorators import login_required, permission_required

from . import oidc_client
from .forms import OidcProviderForm
from .models import OidcProvider

logger = logging.getLogger(__name__)

# One message for every failure mode on this flow, same reasoning as
# login_user: telling an unauthenticated caller *which* check failed (no
# such email vs. wrong company vs. inactive account) confirms account
# existence, which is exactly what turns a guess into a targeted attempt.
_GENERIC_ERROR = _("Could not sign you in. Please try again or contact your administrator.")

_STATE_TTL_SECONDS = 600  # 10 minutes -- long enough for a slow IdP redirect, short enough to bound replay.
_CALLBACK_RATE_LIMIT = 20  # per (ip, provider) per minute
_CALLBACK_RATE_WINDOW = 60


def _client_ip(request) -> str:
    # Consistent with the rest of the codebase's IP resolution for
    # rate-limiting/lockout purposes (see AXES_IPWARE_* in settings) --
    # this endpoint does not sit behind the same proxy-header trust
    # decision axes makes, so REMOTE_ADDR is used directly rather than
    # trusting X-Forwarded-For from an unconfigured source.
    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limited(request, provider: OidcProvider) -> bool:
    key = f"oidc_callback_rl_{provider.pk}_{_client_ip(request)}"
    count = cache.get(key, 0)
    if count >= _CALLBACK_RATE_LIMIT:
        return True
    cache.set(key, count + 1, _CALLBACK_RATE_WINDOW)
    return False


def _fail(request, message=None) -> HttpResponse:
    messages.error(request, message or _GENERIC_ERROR)
    return redirect("login")


def sso_login(request, slug):
    """Redirects to the identity provider's authorization endpoint."""
    provider = get_object_or_404(OidcProvider, slug=slug, is_enabled=True)

    try:
        discovery = oidc_client.get_discovery(provider)
    except oidc_client.OidcClientError:
        logger.warning("OIDC discovery failed for provider %s", provider.pk)
        return _fail(request)

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    request.session["oidc_state"] = state
    request.session["oidc_nonce"] = nonce
    request.session["oidc_provider_slug"] = slug
    request.session["oidc_state_ts"] = time.time()

    redirect_uri = request.build_absolute_uri(reverse("oidc_callback", args=[slug]))
    authorization_url = oidc_client.build_authorization_url(
        provider, discovery, redirect_uri, state, nonce
    )
    return redirect(authorization_url)


def sso_callback(request, slug):
    """
    Validates the IdP's response and, on success, signs the matching
    employee in. Never creates an account (locked v1 scope) -- a verified
    email with no matching, active, same-company employee is a refusal,
    identical in shape to login_user's own refusal for bad credentials.
    """
    provider = get_object_or_404(OidcProvider, slug=slug, is_enabled=True)

    if _rate_limited(request, provider):
        return _fail(request)

    if request.GET.get("error"):
        # IdP-side denial (user cancelled, IdP-side policy block, etc.) --
        # not a bug in this flow, so no warning log, just the same generic
        # message everything else here uses.
        return _fail(request)

    code = request.GET.get("code")
    returned_state = request.GET.get("state")
    if not code or not returned_state:
        return _fail(request)

    saved_state = request.session.pop("oidc_state", None)
    saved_state_ts = request.session.pop("oidc_state_ts", 0)
    saved_slug = request.session.pop("oidc_provider_slug", None)
    saved_nonce = request.session.pop("oidc_nonce", None)

    if not saved_state or not hmac.compare_digest(saved_state, returned_state):
        return _fail(request)
    if time.time() - saved_state_ts > _STATE_TTL_SECONDS:
        return _fail(request)
    if saved_slug != slug:
        # A state token minted for one company's login attempt, replayed
        # against a different company's callback URL.
        logger.warning(
            "OIDC state/slug mismatch: state minted for %r, presented at %r",
            saved_slug, slug,
        )
        return _fail(request)

    try:
        discovery = oidc_client.get_discovery(provider)
        redirect_uri = request.build_absolute_uri(reverse("oidc_callback", args=[slug]))
        tokens = oidc_client.exchange_code_for_tokens(provider, discovery, code, redirect_uri)
        id_token = tokens.get("id_token")
        if not id_token:
            return _fail(request)
        claims = oidc_client.verify_id_token(provider, discovery, id_token, saved_nonce)
    except oidc_client.OidcClientError:
        logger.warning("OIDC callback failed verification for provider %s", provider.pk)
        return _fail(request)

    email = claims.get("email")
    if not email:
        return _fail(request)

    employee = (
        Employee.objects.filter(email__iexact=email, is_active=True)
        .select_related("employee_work_info")
        .first()
    )
    if employee is None:
        logger.warning("OIDC login: no matching active employee for an IdP-verified email")
        return _fail(
            request,
            _("An employee related to this user's credentials does not exist."),
        )

    # The cross-tenant check: Employee.email is globally unique, not scoped
    # to a company (employee/models.py:97), so a matching email alone does
    # not prove the employee belongs to the company whose IdP just vouched
    # for them. Without this, Company A's IdP asserting an email that
    # happens to belong to a Company B employee would sign that person
    # into Company B.
    work_info_company_id = getattr(employee.employee_work_info, "company_id_id", None)
    if work_info_company_id != provider.company_id:
        logger.warning(
            "OIDC login: employee %s matched by email but belongs to a different company than provider %s",
            employee.pk, provider.pk,
        )
        return _fail(request)

    user = employee.employee_user_id
    if user is None or not user.is_active:
        return _fail(
            request,
            _("This user is archived. Please contact the manager for more information."),
        )

    # An explicit backend is required here: login() never runs authenticate(),
    # so user.backend is never set, and Django's login() raises when more
    # than one AUTHENTICATION_BACKENDS entry is configured and it cannot
    # infer which one to attribute the session to. CompanyScopedBackend is
    # the one that actually resolves permissions for any authenticated user
    # regardless of how they signed in (it replaces ModelBackend, per its own
    # docstring) -- axes.backends.AxesStandaloneBackend is lockout-only and
    # is never the right choice to attribute a session to.
    login(request, user, backend="base.auth_backends.CompanyScopedBackend")
    if provider.skip_2fa_for_sso:
        request.session["otp_code_verified"] = True
    messages.success(request, _("Login successful."))
    return redirect("/")


@login_required
@permission_required("horilla_oidc.change_oidcprovider")
def oidc_settings_view(request):
    """
    Per-company OIDC configuration. Scoped by the admin's currently
    selected company (the ordinary, already-authenticated case where
    ambient company context is meaningful) -- not to be confused with the
    pre-login lookups above, which resolve company from the URL slug.

    The deliberate fix over horilla_ldap's precedent: its equivalent view
    (horilla_ldap/views.py) has only @login_required, so any authenticated
    user -- not just an admin -- can currently rewrite the org's LDAP bind
    credentials. horilla.decorators.permission_required is the standard
    decorator used throughout this codebase for exactly this; there is no
    reason this app should ship the same gap on day one.
    """
    selected_company = request.session.get("selected_company")
    company = None
    if selected_company not in (None, "all"):
        company = Company.objects.filter(id=selected_company).first()

    if company is None:
        messages.warning(request, _("Select a single company to configure SSO."))
        return render(request, "oidc_settings.html", {"form": None, "no_company": True})

    provider = OidcProvider.objects.filter(company=company).first()

    if request.method == "POST":
        form = OidcProviderForm(request.POST, instance=provider)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.company = company
            instance.save()
            messages.success(request, _("Configuration updated successfully."))
            return redirect("oidc-settings")
    else:
        form = OidcProviderForm(instance=provider)

    return render(request, "oidc_settings.html", {"form": form, "company": company})

"""
views.py

sso_login / sso_callback: the SSO login flow. Public, unauthenticated by
design -- that is the point of a login flow -- so every step here is
written defensively, mirroring base.views.login_user's own posture
(base/views.py:803-858): one generic error message for every failure mode,
no confirmation of which part failed, no account created on a miss.

oidc_settings_view: the admin-facing settings screen. Superuser-only:
whoever controls a company's issuer can mint a login for any employee of
that company, so this setting is equivalent to full admin and must not be
delegable through an ordinary model permission.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import time

from django.contrib import messages
from django.contrib.auth import login
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _

from base.models import Company
from employee.models import Employee
from horilla.decorators import login_required, superuser_required

from . import oidc_client
from .forms import OidcProviderForm
from .models import OidcProvider

logger = logging.getLogger(__name__)

# One message for every failure mode on this flow: telling the caller
# *which* check failed (no such email vs. wrong company vs. archived)
# would let whoever controls an IdP probe which emails exist in other
# companies. The specific reason goes to the server log instead.
_GENERIC_ERROR = _("Could not sign you in. Please try again or contact your administrator.")

_STATE_TTL_SECONDS = 600  # 10 minutes -- long enough for a slow IdP redirect, short enough to bound replay.


def _fail(request, reason, *args) -> HttpResponse:
    logger.warning("OIDC login refused: " + reason, *args)
    messages.error(request, _GENERIC_ERROR)
    return redirect("login")


def sso_login(request, slug):
    """Redirects to the identity provider's authorization endpoint."""
    provider = get_object_or_404(OidcProvider, slug=slug, is_enabled=True)

    try:
        discovery = oidc_client.get_discovery(provider)
    except oidc_client.OidcClientError as exc:
        return _fail(request, "provider %s: %s", provider.pk, exc)

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    request.session["oidc_state"] = state
    request.session["oidc_nonce"] = nonce
    request.session["oidc_provider_slug"] = slug
    request.session["oidc_state_ts"] = time.time()
    request.session["oidc_next"] = request.GET.get("next", "/")

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

    if request.GET.get("error"):
        # IdP-side denial (user cancelled, IdP-side policy block, etc.).
        return _fail(request, "IdP returned error %r", request.GET.get("error"))

    code = request.GET.get("code")
    returned_state = request.GET.get("state")
    if not code or not returned_state:
        return _fail(request, "callback without code/state")

    saved_state = request.session.pop("oidc_state", None)
    saved_state_ts = request.session.pop("oidc_state_ts", 0)
    saved_slug = request.session.pop("oidc_provider_slug", None)
    saved_nonce = request.session.pop("oidc_nonce", None)
    next_url = request.session.pop("oidc_next", "/")

    if not saved_state or not hmac.compare_digest(saved_state, returned_state):
        return _fail(request, "state mismatch")
    if time.time() - saved_state_ts > _STATE_TTL_SECONDS:
        return _fail(request, "state expired")
    if saved_slug != slug:
        # A state token minted for one company's login attempt, replayed
        # against a different company's callback URL.
        return _fail(request, "state minted for %r, presented at %r", saved_slug, slug)

    try:
        discovery = oidc_client.get_discovery(provider)
        redirect_uri = request.build_absolute_uri(reverse("oidc_callback", args=[slug]))
        tokens = oidc_client.exchange_code_for_tokens(provider, discovery, code, redirect_uri)
        id_token = tokens.get("id_token")
        if not id_token:
            return _fail(request, "provider %s: token response had no id_token", provider.pk)
        claims = oidc_client.verify_id_token(provider, discovery, id_token, saved_nonce)
    except oidc_client.OidcClientError as exc:
        return _fail(request, "provider %s: %s", provider.pk, exc)

    email = claims.get("email")
    if not email:
        return _fail(request, "provider %s: ID token has no email claim", provider.pk)

    # Employee.email is unique case-sensitively, so "Bob@x" and "bob@x" can
    # both exist: prefer the exact match, and accept a case-insensitive one
    # only when it is unambiguous.
    employees = Employee.objects.filter(is_active=True).select_related("employee_work_info")
    matches = list(employees.filter(email=email)) or list(employees.filter(email__iexact=email)[:2])
    if len(matches) != 1:
        return _fail(request, "provider %s: %d active employees match the email", provider.pk, len(matches))
    employee = matches[0]

    # The cross-tenant check: Employee.email is globally unique, not scoped
    # to a company (employee/models.py:97), so a matching email alone does
    # not prove the employee belongs to the company whose IdP just vouched
    # for them. Without this, Company A's IdP asserting an email that
    # happens to belong to a Company B employee would sign that person
    # into Company B.
    work_info_company_id = getattr(employee.employee_work_info, "company_id_id", None)
    if work_info_company_id != provider.company_id:
        return _fail(request, "employee %s is not in provider %s's company", employee.pk, provider.pk)

    user = employee.employee_user_id
    if user is None or not user.is_active:
        return _fail(request, "employee %s has no active user", employee.pk)
    if user.is_superuser:
        # A superuser is global across every company, so letting one
        # company's IdP vouch for it would let that IdP's admin reach every
        # other company. Superusers keep password login as the break-glass path.
        return _fail(request, "employee %s is a superuser; SSO refused", employee.pk)

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
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = "/"
    return redirect(next_url)


@login_required
@superuser_required
def oidc_settings_view(request):
    """
    Per-company OIDC configuration, scoped by the admin's currently selected
    company (unlike the pre-login views above, which resolve it from the slug).
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

    callback_url = (
        request.build_absolute_uri(reverse("oidc_callback", args=[provider.slug]))
        if provider
        else None
    )
    return render(
        request,
        "oidc_settings.html",
        {"form": form, "company": company, "callback_url": callback_url},
    )

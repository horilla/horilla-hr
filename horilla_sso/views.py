import logging

from django.contrib import messages
from django.contrib.auth import login
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _

from horilla.decorators import login_required, superuser_required
from horilla_sso import methods, providers
from horilla_sso.forms import FORMS

logger = logging.getLogger(__name__)

SESSION_KEYS = ("sso_state", "sso_nonce", "sso_next", "sso_provider")
BACKEND = "base.auth_backends.CompanyScopedBackend"


def _provider(key):
    try:
        return providers.PROVIDERS[key]
    except KeyError:
        raise Http404 from None


def callback_uri(request, provider):
    """The address the provider sends the user back to; it must be registered exactly in the provider's console."""
    return request.build_absolute_uri(reverse(provider.callback_url))


def _back_to_login(request, message, level=messages.ERROR):
    """Ends a sign-in that cannot go ahead, with one message for the user."""
    for key in SESSION_KEYS:
        request.session.pop(key, None)
    messages.add_message(request, level, message)
    return redirect("login")


def _unavailable(request, provider):
    return _back_to_login(
        request,
        _("%(provider)s Sign-In Is Not Available.") % {"provider": provider.label},
    )


def sso_login(request, provider):
    """Starts the sign-in by sending the user to the provider."""
    provider = _provider(provider)
    config = provider.config()
    if not config or not config.is_ready():
        return _unavailable(request, provider)
    url, state, nonce = methods.build_authorization_url(
        config, callback_uri(request, provider)
    )
    request.session["sso_state"] = state
    request.session["sso_nonce"] = nonce
    request.session["sso_provider"] = provider.key
    request.session["sso_next"] = request.GET.get("next", "/")
    return redirect(url)


def sso_callback(request, provider):
    """Finishes the sign-in: checks the reply, finds the employee and logs them in."""
    provider = _provider(provider)
    config = provider.config()
    state = request.session.get("sso_state", "")
    nonce = request.session.get("sso_nonce", "")
    next_url = request.session.get("sso_next", "/")
    started_with = request.session.get("sso_provider", "")
    if not config or not config.is_ready():
        return _unavailable(request, provider)
    received = request.GET.get("state", "")
    # A sign-in started with one provider can never be finished on another provider's address.
    state_ok = (
        bool(state) and started_with == provider.key and methods.same(received, state)
    )
    if request.GET.get("error"):
        reason = " ".join(
            (request.GET.get("error_description") or request.GET["error"]).split()
        )[:300]
        logger.info("%s sign-in refused: %s", provider.label, reason)
        message = str(
            _("The %(provider)s Sign-In Was Not Completed.")
            % {"provider": provider.label}
        )
        # The provider's reason is shown only for a sign-in this browser started, so a crafted link cannot put text here.
        return _back_to_login(request, f"{message} {reason}" if state_ok else message)
    if not state_ok or not request.GET.get("code"):
        return _back_to_login(
            request,
            _("The %(provider)s Sign-In Could Not Be Verified.")
            % {"provider": provider.label},
        )
    for key in SESSION_KEYS:
        request.session.pop(key, None)

    try:
        token = methods.exchange_code(
            config, request.GET["code"], callback_uri(request, provider)
        )
        claims = methods.validate_id_token(config, token, nonce)
    except methods.SSOError as error:
        logger.info("%s sign-in failed: %s", provider.label, error)
        return _back_to_login(request, _(str(error)))

    if not methods.domain_allowed(config, claims):
        return _back_to_login(
            request,
            _("This %(provider)s Account Is Not Allowed To Sign In.")
            % {"provider": provider.label},
        )
    employee = methods.find_employee(
        claims, trust_email=provider.trust_email(config), provider=provider.key
    )
    user = getattr(employee, "employee_user_id", None)
    if employee is None or user is None:
        return _back_to_login(
            request,
            _("No Employee Matches This %(provider)s Account.")
            % {"provider": provider.label},
        )
    if not employee.is_active or not user.is_active:
        return _back_to_login(
            request,
            _(
                "This User Is Archived. Please Contact The Manager For More Information."
            ),
            messages.WARNING,
        )

    login(request, user, backend=BACKEND)
    request.session["otp_code_verified"] = True
    if user.is_new_employee:
        user.is_new_employee = False
        user.save(update_fields=["is_new_employee"])
    messages.success(request, _("Login Successful."))
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        next_url = "/"
    return redirect(next_url)


@login_required
@superuser_required
def sso_settings(request, provider):
    """The page where an administrator sets up one sign-in provider."""
    provider = _provider(provider)
    config = provider.config()
    form_class = FORMS[provider.key]
    if request.method == "POST":
        form = form_class(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, _("Configuration Updated Successfully."))
            return redirect(provider.settings_url)
    else:
        form = form_class(instance=config)
    return render(
        request,
        "sso_settings.html",
        {
            "form": form,
            "provider": provider,
            "redirect_uri": callback_uri(request, provider),
            "has_secret": bool(config and config.client_secret_encrypted),
        },
    )

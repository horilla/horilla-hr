"""
views.py

Admin settings page for SCIM provisioning. Superuser-only: a SCIM token can
create, change and remove any non-superuser employee of the company, so
issuing one is equivalent to full employee administration and must not be
delegable through an ordinary model permission.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from base.models import Company
from horilla.decorators import login_required, superuser_required

from .forms import ScimProviderForm
from .models import ScimProvider, ScimToken

RECENT_EVENTS = 25


def _selected_company(request):
    selected = request.session.get("selected_company")
    if selected in (None, "all"):
        return None
    return Company.objects.filter(id=selected).first()


@login_required
@superuser_required
def scim_settings_view(request):
    company = _selected_company(request)
    if company is None:
        return render(request, "scim_settings.html", {"no_company": True})

    provider = ScimProvider.objects.filter(company=company).order_by("pk").first()
    if request.method == "POST":
        form = ScimProviderForm(request.POST, instance=provider, company=company)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.company = company
            instance.save()
            messages.success(request, _("Configuration updated successfully."))
            return redirect("scim-settings")
    else:
        form = ScimProviderForm(
            instance=provider,
            company=company,
            initial=None if provider else {"name": _("Identity provider")},
        )

    context = {
        "form": form,
        "company": company,
        "provider": provider,
        "base_url": request.build_absolute_uri("/scim/v2"),
        # Shown once, right after generation; popped so a reload hides it.
        "new_token": request.session.pop("scim_new_token", None),
    }
    if provider is not None:
        context["tokens"] = provider.tokens.all()
        context["events"] = provider.events.all()[:RECENT_EVENTS]
    return render(request, "scim_settings.html", context)


@login_required
@superuser_required
@require_POST
def scim_token_create(request):
    company = _selected_company(request)
    provider = get_object_or_404(ScimProvider.objects.order_by("pk"), company=company)
    _token, raw = ScimToken.issue(provider)
    request.session["scim_new_token"] = raw
    messages.success(
        request, _("Token generated. Copy it now; it will not be shown again.")
    )
    return redirect("scim-settings")


@login_required
@superuser_required
@require_POST
def scim_token_revoke(request, token_id):
    company = _selected_company(request)
    token = get_object_or_404(
        ScimToken, pk=token_id, provider__company=company, revoked_at__isnull=True
    )
    token.revoked_at = timezone.now()
    token.save(update_fields=["revoked_at"])
    messages.success(request, _("Token revoked."))
    return redirect("scim-settings")

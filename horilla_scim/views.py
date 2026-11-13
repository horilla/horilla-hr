"""
views.py

Admin settings page for SCIM provisioning. Superuser-only: a SCIM token can
create, change and remove any non-superuser employee of the company, so
issuing one is equivalent to full employee administration and must not be
delegable through an ordinary model permission.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
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


def _render_settings(request, company, provider, form, new_token=None):
    context = {
        "form": form,
        "company": company,
        "provider": provider,
        "base_url": request.build_absolute_uri("/scim/v2"),
        # Only set in the response to Generate/Reset itself, so the raw
        # token is never written to the session or the database.
        "new_token": new_token,
    }
    if provider is not None:
        context["has_token"] = ScimToken.objects.filter(provider=provider).exists()
        context["events"] = provider.events.all()[:RECENT_EVENTS]
    return render(request, "scim_settings.html", context)


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

    return _render_settings(request, company, provider, form)


@never_cache
@login_required
@superuser_required
@require_POST
def scim_token_create(request):
    """Generate the provider's token, or reset it (the old one stops working)."""
    company = _selected_company(request)
    provider = get_object_or_404(ScimProvider.objects.order_by("pk"), company=company)
    _token, raw = ScimToken.issue(provider)
    messages.success(
        request, _("Token generated. Copy it now; it will not be shown again.")
    )
    # Rendered here rather than redirected, so the raw value only ever
    # travels in this one response.
    form = ScimProviderForm(instance=provider, company=company)
    return _render_settings(request, company, provider, form, new_token=raw)

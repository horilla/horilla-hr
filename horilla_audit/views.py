"""
views.py
"""

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from horilla.decorators import login_required
from horilla.http.response import HorillaRedirect
from horilla_audit.forms import (
    AuditModelConfigForm,
    AuditModelFieldsForm,
    field_choices_for,
)
from horilla_audit.models import AuditModelConfig
from horilla_audit.registry import DEFAULT_TRACKED_MODELS


def _audit_tracking_context():
    """Shared context for the audit-tracking section on Audit & History."""
    return {
        "audit_model_form": AuditModelConfigForm(),
        "audit_model_configs": AuditModelConfig.objects.all().order_by(
            "app_label", "model_name"
        ),
    }


@login_required
def audit_history_settings_view(request):
    """
    Merged "Audit & History" settings page grouping History Tags and Audit
    Tracking under a single header.
    """
    context = {}
    if request.user.has_perm("horilla_audit.view_auditmodelconfig"):
        context.update(_audit_tracking_context())
    return render(request, "base/settings/audit_history.html", context)


@login_required
@permission_required("horilla_audit.view_auditmodelconfig")
def audit_model_settings(request):
    """
    Legacy standalone Audit Tracking settings page. Merged into Audit & History;
    redirect direct visits to the merged page.
    """
    return redirect("audit-history-view")


@login_required
@permission_required("horilla_audit.change_auditmodelconfig")
@require_http_methods(["POST"])
def save_audit_models(request):
    """Persist the list of audit-tracked models."""

    selected = request.POST.getlist("model_paths")
    selected_pairs = []
    for path in selected:
        if "." not in path:
            continue
        app_label, model_name = path.split(".", 1)
        selected_pairs.append((app_label, model_name))

    # Built-in defaults are always tracked — they cannot be turned off here
    # so audit history never silently disappears for the core Employee models.
    default_set = set(DEFAULT_TRACKED_MODELS)
    selected_set = set(selected_pairs) | default_set
    existing = {(c.app_label, c.model_name): c for c in AuditModelConfig.objects.all()}

    # Remove configs that were unchecked, but never delete defaults.
    for key, cfg in existing.items():
        if key in selected_set or key in default_set:
            continue
        cfg.delete()

    # Create new configs for newly checked entries (and ensure defaults exist).
    for app_label, model_name in selected_set:
        if (app_label, model_name) not in existing:
            AuditModelConfig.objects.create(
                app_label=app_label,
                model_name=model_name,
                is_enabled=True,
                tracked_fields=[],
            )

    messages.success(request, _("Audit tracking configuration updated."))

    if request.headers.get("HX-Request"):
        return HttpResponse(
            status=200,
            headers={"HX-Redirect": reverse("audit-history-view")},
        )
    return HorillaRedirect(request)


@login_required
@permission_required("horilla_audit.change_auditmodelconfig")
def edit_audit_model_fields(request, pk):
    """Edit which fields of a single model are tracked."""

    try:
        config = AuditModelConfig.objects.get(pk=pk)
    except AuditModelConfig.DoesNotExist:
        messages.error(request, _("Audit configuration not found."))
        return redirect("audit-history-view")

    if request.method == "POST":
        form = AuditModelFieldsForm(
            request.POST,
            app_label=config.app_label,
            model_name=config.model_name,
        )
        if form.is_valid():
            config.tracked_fields = form.cleaned_data["fields_to_track"]
            config.save()
            messages.success(
                request,
                _("Tracked fields updated for %(model)s.")
                % {"model": config.model_name},
            )
            if request.headers.get("HX-Request"):
                return HttpResponse(
                    status=200,
                    headers={"HX-Redirect": reverse("audit-history-view")},
                )
            return HorillaRedirect(request)
    else:
        form = AuditModelFieldsForm(
            initial={"fields_to_track": config.tracked_fields or []},
            app_label=config.app_label,
            model_name=config.model_name,
        )

    return render(
        request,
        "horilla_audit/audit_model_fields_form.html",
        {"form": form, "config": config},
    )

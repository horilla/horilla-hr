"""
Build-time guard against unscoped tenant models.

Tenancy is opt-in: a model is isolated only if someone remembered to give it a
``HorillaCompanyManager``. Across 233 models that is 233 chances to forget, and
forgetting is silent -- the model works fine and leaks across tenants. EmailLog
had a ``company_id`` FK and a plain ``Manager()`` for exactly this reason.

This turns the omission into a failed ``manage.py check``. Models that are
legitimately global are listed in ``EXEMPT`` with a reason, so the exception is
reviewed once rather than rediscovered.
"""

from __future__ import annotations

from django.core.checks import Warning as CheckWarning
from django.core.checks import register

# "<app_label>.<ModelName>": why it is intentionally not company-scoped.
EXEMPT = {
    "base.Company": "It is the tenant root; scoping it by itself is circular.",
    "horilla_audit.AuditTag": "Global audit vocabulary, shared across tenants.",
    "horilla_audit.AccountBlockUnblock": "Global account-level switch.",
    "horilla_dbtemplate.TemplateVersion": "Versions inherit their template's scope.",
    "biometric.BiometricDevices": "Device registry is deployment-wide.",
    "biometric.BiometricEmployees": "Rows are reached via a scoped device.",
    "base.RosterPublishLog": "Audit trail reached via a scoped roster.",
    "base.AnnouncementView": "Read receipts reached via a scoped announcement.",
    "base.BaserequestFile": "Attachment reached via its scoped parent request.",
    "employee.NoteFiles": "Attachment reached via its scoped parent note.",
    "asset.AssetDocuments": "Attachment reached via its scoped parent asset.",
    "payroll.ReimbursementFile": "Attachment reached via its scoped parent claim.",
    "payroll.ReimbursementMultipleAttachment": (
        "Attachment reached via its scoped parent claim."
    ),
    "pms.AnonymousFeedback": "Anonymity is the point; scoping would deanonymise.",
    "horilla.HorillaModel": "Abstract base.",
    # Per-company settings singletons. These are always looked up by an
    # explicit company_id (a settings row for company X, fetched deliberately),
    # never listed under ambient scope, so the manager filter would add nothing.
    "base.CompanyGroupAssignment": "Looked up by explicit company + user.",
    "base.CompanyLanguageSetting": "Per-company settings singleton.",
    "base.DefaultExportPermission": "Per-company settings singleton.",
    "base.DynamicEmailConfiguration": "Per-company mail-server singleton.",
    "base.IntegrationApps": "Per-company integration toggle.",
    "base.SetupChecklistDismissal": "Per-user, per-company UI dismissal flag.",
    "horilla_theme.CompanyTheme": "Per-company theme singleton.",
    "facedetection.FaceDetection": "Per-company OneToOne settings row.",
    "geofencing.GeoFencing": "Per-company OneToOne settings row.",
    "horilla_audit.HistoryTrackingFields": "Per-company audit configuration.",
    # django-simple-history shadow tables. They mirror a scoped model and are
    # only ever read through that model's history manager.
    "employee.HistoricalEmployeeWorkInformation": "simple_history shadow table.",
    "pms.HistoricalKeyResult": "simple_history shadow table.",
    "pms.HistoricalObjective": "simple_history shadow table.",
}


@register("horilla.tenancy")
def check_company_scoped_managers(app_configs, **kwargs):
    """Warn when a model has a company FK but no company-scoped manager."""
    from django.apps import apps

    from base.horilla_company_manager import HorillaCompanyManager

    problems = []
    models = (
        apps.get_models()
        if app_configs is None
        else [model for config in app_configs for model in config.get_models()]
    )

    for model in models:
        label = f"{model._meta.app_label}.{model.__name__}"
        if label in EXEMPT:
            continue

        try:
            model._meta.get_field("company_id")
        except Exception:
            # No company field at all: nothing to scope against. Models that
            # reach a company through a relation are the reason this check
            # warns rather than errors.
            continue

        if isinstance(model._default_manager, HorillaCompanyManager):
            continue

        problems.append(
            CheckWarning(
                f"{label} has a company_id field but its default manager is "
                f"{type(model._default_manager).__name__}, so queries are not "
                f"company-scoped.",
                hint=(
                    "Set `objects = HorillaCompanyManager()` on the model, or "
                    "add it to base.checks.EXEMPT with the reason it is global."
                ),
                obj=model,
                id="horilla.tenancy.W001",
            )
        )

    return problems

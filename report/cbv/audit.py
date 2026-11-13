"""CBV-based Report Audit log — HR-admin read-only view of report activity."""

from typing import Any

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from report.filters import ReportAuditFilter
from report.models import ReportRunLog


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="employee.view_employee"), name="dispatch")
class ReportAuditView(TemplateView):
    """Thin page shell — HTMX-loads the Nav and List fragments below."""

    template_name = "cbv/audit/audit_home.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="employee.view_employee"), name="dispatch")
class ReportAuditNav(HorillaNavView):
    nav_title = _("Report Audit")
    filter_instance = ReportAuditFilter()
    filter_body_template = "cbv/audit/audit_filter.html"
    filter_form_context_name = "form"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("report-audit-list")
        self.search_swap_target = "#listContainer"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="employee.view_employee"), name="dispatch")
class ReportAuditListView(HorillaListView):
    """Read-only — no bulk select, no row actions, no create."""

    model = ReportRunLog
    filter_class = ReportAuditFilter
    bulk_select_option = False
    show_toggle_form = False

    columns = [
        (_("Report"), "report_name"),
        (_("Action"), "get_action_display"),
        (_("Employee"), "employee_label"),
        (_("Format"), "format_label"),
        (_("When"), "created_at"),
        (_("Company"), "company_label"),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "reportAudit"
        self.search_url = reverse("report-audit-list")

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        queryset = super().get_queryset(queryset, filtered, *args, **kwargs)
        return queryset.select_related("user__employee_get", "company_id")

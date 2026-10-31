"""
One page for payslips and payroll batches: a tab for each, in the standard tab structure.
"""

from typing import Any

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.methods import filter_own_records
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import HorillaTabContentShell, HorillaTabView
from payroll.models.models import Payslip
from payroll.models.payroll_batch import PayrollBatch

TABS_ROOT_ID = "payslipBatchContainer"


@method_decorator(login_required, name="dispatch")
class PayslipsAndBatchesTabView(HorillaTabView):
    """The Payslips and Batches tabs, with a count on each."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = TABS_ROOT_ID
        self.tabs = [
            {"title": _("Payslips"), "url": reverse("payslip-tab-shell")},
        ]
        if self.request and self.request.user.has_perm("payroll.view_payslip"):
            self.tabs.append(
                {"title": _("Batches"), "url": reverse("payroll-batch-tab-shell")}
            )

    def get_context_data(self, **kwargs):
        payslips = filter_own_records(
            self.request, Payslip.objects.all(), "payroll.view_payslip"
        ).count()
        self.tabs[0]["badge"] = payslips
        if len(self.tabs) > 1:
            self.tabs[1]["badge"] = PayrollBatch.objects.count()
        return super().get_context_data(**kwargs)


@method_decorator(login_required, name="dispatch")
class PayslipTabShell(HorillaTabContentShell):
    nav_url_name = "payslip-navbar"
    # The payslip list keeps the id its own actions and scripts already target.
    container_id = "listContainer"
    tabs_root_id = TABS_ROOT_ID


@method_decorator(login_required, name="dispatch")
class PayrollBatchTabShell(HorillaTabContentShell):
    """The batches tab: the pay period, then the batch list under its own nav."""

    template_name = "payroll/batch/_batch_tab_shell.html"
    nav_url_name = "payroll-batch-navbar"
    container_id = "batchListContainer"
    tabs_root_id = TABS_ROOT_ID

    def get_context_data(self, **kwargs: Any):
        from datetime import date

        from payroll.views.batch_views import _settings_for

        context = super().get_context_data(**kwargs)
        context["period"] = _settings_for(self.request).period_for(date.today())
        return context

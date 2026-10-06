"""
The payroll runs list: the standard search, filter panel and list, on the runs page.
"""

from typing import Any

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import HorillaListView, HorillaNavView
from payroll.filters import PayrollBatchFilter
from payroll.models.payroll_batch import PayrollBatch


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_payslip"), name="dispatch")
class PayrollBatchList(HorillaListView):
    """Every run, newest first."""

    model = PayrollBatch
    filter_class = PayrollBatchFilter
    view_id = "payroll-batch-div"
    selected_instances_key_id = "selectedInstances"
    quick_export = False
    bulk_select_option = False

    columns = [
        (_("Run"), "batch_name"),
        (_("Period"), "period_display"),
        (_("Pay date"), "pay_date_display"),
        (_("People"), "people_display"),
        (_("Gross"), "gross_display"),
        (_("Deductions"), "deductions_display"),
        (_("Net"), "net_display"),
        (_("Status"), "status_pill"),
    ]
    sortby_mapping = [
        (_("Run"), "batch_name"),
        (_("Period"), "period_start"),
        (_("Pay date"), "pay_date"),
        (_("People"), "generated_count"),
        (_("Gross"), "total_gross"),
        (_("Net"), "total_net"),
        (_("Status"), "status"),
    ]
    row_attrs = """
        onclick="window.location.href='{get_detail_url}'"
        style="cursor:pointer;"
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("payroll-batch-list")
        # Deleting a run (a paid one is refused, and shows no button) -- it was
        # on the old table's rows and went with it.
        if self.request.user.has_perm("payroll.delete_payslip"):
            self.action_method = "run_actions"
        else:
            self.action_method = None

    def get_queryset(self):
        return super().get_queryset().order_by("-period_start", "-id")


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_payslip"), name="dispatch")
class PayrollBatchNav(HorillaNavView):
    """Search and the slide-over filter for the runs list."""

    nav_title = " "
    create_label = _("Generate")
    create_icon = "play-outline"
    filter_body_template = "payroll/batch/_batch_filter.html"
    filter_instance = PayrollBatchFilter()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    modern_filter = True
    group_by_fields = [("status", _("Status"))]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("payroll-batch-list")
        self.actions = []
        if self.request.user.has_perm("payroll.add_payslip"):
            self.create_attrs = f"""
                onclick="window.location.href='{reverse('payroll-batch-scope')}'"
                style="cursor:pointer;"
            """
        else:
            self.create_attrs = None

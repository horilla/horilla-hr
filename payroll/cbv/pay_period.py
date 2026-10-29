"""
The pay period settings, listed in the Payroll Settings "Payslip Auto Generation" tab: one row
per company, and one for all companies.
"""

from typing import Any

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import HorillaListView, HorillaNavView
from payroll.filters import PayPeriodSettingsFilter
from payroll.models.models import PayPeriodSettings


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="payroll.view_payslipautogenerate"), name="dispatch"
)
class PayPeriodListView(HorillaListView):
    """One row per company: when its pay period starts and when people are paid."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "pay_period_id"
        self.search_url = reverse("pay-period-list")

    model = PayPeriodSettings
    filter_class = PayPeriodSettingsFilter
    show_toggle_form = False
    delete_confirm = _("Are you sure you want to delete this pay period?")

    columns = [
        (_("Company"), "get_company"),
        (_("Period Runs"), "get_cycle_start_day_display"),
        (_("Pay Day"), "pay_day_display"),
        (_("Auto Generate Payslips"), "auto_generate_display"),
    ]

    header_attrs = {"action": """ style="width:200px !important" """}

    actions = [
        {
            "action": _("Generate Payslips"),
            "icon": "play-circle-outline",
            "attrs": f"""
                    class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                    title="{{generate_title}}"
                    hx-confirm="{_('Generate payslips now for the last completed period?')}"
                    hx-post="{{get_generate_url}}"
                    hx-swap="none"
                    """,
        },
        {
            "action": _("Edit"),
            "icon": "create-outline",
            "attrs": """
                    class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                    hx-get="{get_update_url}?modal=1&then=list"
                    hx-target="#genericModalBody"
                    data-toggle="oh-modal-toggle"
                    data-target="#genericModal"
                    """,
        },
        {
            "action": _("Delete"),
            "icon": "trash-outline",
            "attrs": f"""
                    class="oh-btn oh-btn--danger oh-btn--sq-sm"
                    hx-confirm="{delete_confirm}"
                    hx-target="#payPeriodTr{{get_instance_id}}"
                    hx-post="{{get_delete_url}}"
                    hx-swap="delete"
                    """,
        },
    ]

    row_attrs = """
                id = "payPeriodTr{get_instance_id}"
                """


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="payroll.view_payslipautogenerate"), name="dispatch"
)
class PayPeriodNav(HorillaNavView):
    """The bar above the list: its title, search and the Create button."""

    template_name = "generic/inline_nav.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("pay-period-list")
        self.create_attrs = f"""
                            onclick = "event.stopPropagation();"
                            data-toggle="oh-modal-toggle"
                            data-target="#genericModal"
                            hx-target="#genericModalBody"
                            hx-get="{reverse('pay-period-settings')}?modal=1&then=list&new=1"
                            """

    nav_title = _("Pay Period & Payslip Automation")
    filter_instance = PayPeriodSettingsFilter()
    search_swap_target = "#payPeriodListContainer"

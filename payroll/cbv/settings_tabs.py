"""
this page is handling the cbv methods for the payroll settings page,
which lists payslip auto generation as a tab
"""

from typing import Any

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from horilla_views.cbv_methods import hx_request_required, login_required
from horilla_views.generic.cbv.views import HorillaTabView, TemplateView
from payroll.cbv.allowances import AllowanceListView
from payroll.cbv.deduction import DeductionListView
from payroll.cbv.payslip_automation import PaySlipAutomationListView
from payroll.cbv.salary_structure import SalaryStructureListView


def always_applied_rows(kind):
    """
    The standard pay items of one kind ("allowance" or "deduction"), for the "Always Applied"
    tab. They apply to everybody, whenever the event happens, so they are not rows of the
    Allowances and Deductions lists; the tab is where they are listed, and where their tax
    treatment is still reached.
    """
    from payroll.models.models import Allowance, Deduction
    from payroll.system_components import BY_KEY

    model = Allowance if kind == "allowance" else Deduction
    rows = []
    for item in (
        model.objects.entire().filter(is_system=True).order_by("sequence", "pk")
    ):
        if kind == "allowance":
            type_label = _("Earning")
            treatment = _("Taxable") if item.is_taxable else _("Not Taxable")
        elif item.is_tax:
            type_label = _("Tax")
            treatment = "—"
        elif item.is_pretax:
            type_label = _("Pre-Tax Deduction")
            treatment = _("Pre-Tax")
        else:
            type_label = _("Deduction")
            treatment = _("Post-Tax")
        rows.append(
            {
                "kind": kind,
                "pk": item.pk,
                "title": item.title,
                "code": item.code,
                "summary": (BY_KEY.get(item.system_key) or {}).get("summary", ""),
                "type_label": type_label,
                "treatment": treatment,
            }
        )
    return rows


def all_always_applied_rows():
    """Both kinds in one list: the earnings first, then the deductions."""
    return always_applied_rows("allowance") + always_applied_rows("deduction")


def _payroll_settings_tab_badge_count(request, view_cls):
    """Same queryset rules as the tab's HorillaListView (filters, permissions)."""
    view = view_cls()
    view.request = request
    view.args = ()
    view.kwargs = {}
    view.queryset = None
    return view.get_queryset().count()


@method_decorator(login_required, name="dispatch")
class PayrollSettingsView(TemplateView):
    """
    page for payroll settings (Payslip Auto Generation tab)
    """

    template_name = "cbv/payroll_settings/payroll_settings_main.html"


@method_decorator(login_required, name="dispatch")
class PayrollSettingsTabView(HorillaTabView):
    """
    tab view for payroll settings, shows payslip auto generation as a tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.tabs = [
            {
                "title": _("Salary Structures"),
                "url": f"{reverse('payroll-settings-salary-structure-tab')}",
            },
            {
                "title": _("Allowances"),
                "url": f"{reverse('payroll-settings-allowance-tab')}",
            },
            {
                "title": _("Deductions"),
                "url": f"{reverse('payroll-settings-deduction-tab')}",
            },
            {
                "title": _("Always Applied"),
                "url": f"{reverse('payroll-settings-always-applied-tab')}",
            },
            {
                "title": _("Payslip Auto Generation"),
                "url": f"{reverse('payroll-settings-auto-payslip-tab')}",
            },
        ]

    def get_context_data(self, **kwargs: Any):
        """
        Eagerly compute each tab's real record count so its badge shows the
        right number on first load — lazy-loaded (non-active) tabs don't run
        the count-updating script embedded in their list template until the
        user actually clicks them, so without this they'd sit at "0".

        view_classes lines up with self.tabs position for position (Salary
        Structures, Allowances, Deductions, Payslip Auto Generation). It used
        to start one entry short of self.tabs, which shifted every pairing by
        one: Salary Structures showed Allowances' count, Allowances showed
        Deductions', Deductions showed Payslip Auto Generation's, and that
        last tab was left with no count at all.
        """
        context = super().get_context_data(**kwargs)
        # None: the Always Applied tab is not a list; its count is its rows.
        view_classes = [
            SalaryStructureListView,
            AllowanceListView,
            DeductionListView,
            None,
            PaySlipAutomationListView,
        ]
        for tab, view_cls in zip(self.tabs, view_classes):
            if view_cls is None:
                tab["badge"] = len(all_always_applied_rows())
            else:
                tab["badge"] = _payroll_settings_tab_badge_count(self.request, view_cls)
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class PayrollSettingsSalaryStructureTab(TemplateView):
    """
    salary structure tab content, embeds the nav + list
    """

    template_name = "cbv/payroll_settings/salary_structure_tab.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class PayrollSettingsAllowanceTab(TemplateView):
    """
    payslip auto generation tab content, embeds the existing nav + list
    """

    template_name = "cbv/payroll_settings/allowance_tab.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class PayrollSettingsDeductionTab(TemplateView):
    """
    payslip auto generation tab content, embeds the existing nav + list
    """

    template_name = "cbv/payroll_settings/deduction_tab.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class PayrollSettingsAlwaysAppliedTab(TemplateView):
    """
    The standard pay items, earnings and deductions together: on for everybody, whenever the
    event happens, so listed apart from the Allowances and Deductions tabs.
    """

    template_name = "cbv/payroll_settings/always_applied_tab.html"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        context["rows"] = all_always_applied_rows()
        context["headings"] = [_("Component"), _("Type"), _("Tax"), _("Applies")]
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class PayrollSettingsAutoPayslipTab(TemplateView):
    """
    payslip auto generation tab content, embeds the existing nav + list
    """

    template_name = "cbv/payroll_settings/auto_payslip_tab.html"

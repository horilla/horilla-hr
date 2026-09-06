"""
this page handles cbv methods of payslip page
"""

import json
from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.methods import has_export_access
from employee import views as employee_view
from employee.cbv.employee_profile import EmployeeProfileView
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import (
    hx_request_required,
    login_required,
    permission_required,
)
from horilla_views.generic.cbv.views import (
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from notifications.signals import notify
from payroll.cbv.allowance_deduction import AllowanceDeductionTabView
from payroll.filters import PayslipFilter
from payroll.forms import component_forms as forms
from payroll.methods.methods import calculate_employer_contribution, save_payslip
from payroll.models.models import Contract, Payslip
from payroll.views.component_views import payroll_calculation


@method_decorator(login_required, name="dispatch")
class PayslipView(TemplateView):
    """
    payslip page
    """

    def get_context_data(self, **kwargs: Any):
        """
        Return context for rendering payslip generation forms.
        """
        form = forms.GeneratePayslipForm()
        individual_form = forms.PayslipForm()
        bulk_form = forms.GeneratePayslipForm()
        group_name = form["group_name"]
        context = super().get_context_data(**kwargs)
        context["individual_form"] = individual_form
        context["group_name"] = group_name
        context["bulk_form"] = bulk_form
        return context

    template_name = "cbv/payslip/payslip_home.html"


@method_decorator(login_required, name="dispatch")
class PayslipList(HorillaListView):
    """
    list view
    """

    selected_instances_key_id = "selectedInstances"
    quick_export = False
    bulk_update_fields = [
        "status",
        "start_date",
        "end_date",
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("payslip-list")
        self.view_id = "payslip-div"

    def get_queryset(self):
        """
        Return the queryset of Payslip objects based on user permissions.
        """
        queryset = super().get_queryset()
        if not self.request.user.has_perm("payroll.view_payslip"):
            queryset = queryset.filter(employee_id__employee_user_id=self.request.user)
        return queryset

    model = Payslip
    filter_class = PayslipFilter
    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Start date"), "start_date"),
        (_("End Date"), "end_date"),
        (_("Batch"), "group_name"),
        (_("Gross Pay"), "gross_pay_display"),
        (_("Deduction"), "deduction_display"),
        (_("Net Pay"), "net_pay_display"),
        (_("Status"), "custom_status_col"),
    ]

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Start date"), "start_date"),
        (_("End Date"), "end_date"),
        (_("Gross Pay"), "gross_pay_display"),
        (_("Deduction"), "deduction_display"),
        (_("Net Pay"), "net_pay_display"),
        (_("Status"), "custom_status_col"),
    ]
    action_method = "custom_actions_col"

    row_status_indications = [
        (
            "draft--dot",
            _("Draft"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('draft');
            $('[name=review_ongoing]').val('unknown').change();
            $('[name=confirmed]').val('unknown').change();
            $('[name=paid]').val('unknown').change();
            $('#applyFilter').click();
            "
            """,
        ),
        (
            "review_ongoing--dot",
            _("Review Ongoing"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('review_ongoing');
            $('[name=draft]').val('unknown').change();
            $('[name=confirmed]').val('unknown').change();
            $('[name=paid]').val('unknown').change();
            $('#applyFilter').click();
            "
            """,
        ),
        (
            "confirmed--dot",
            _("Confirmed"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('confirmed');
            $('[name=draft]').val('unknown').change();
            $('[name=review_ongoing]').val('unknown').change();
            $('[name=paid]').val('unknown').change();
            $('#applyFilter').click();
            "
            """,
        ),
        (
            "paid--dot",
            _("Paid"),
            """
            onclick="
            $('#applyFilter').closest('form').find('[name=status]').val('paid');
            $('[name=draft]').val('unknown').change();
            $('[name=review_ongoing]').val('unknown').change();
            $('[name=confirmed]').val('unknown').change();
            $('#applyFilter').click();
            "
            """,
        ),
    ]

    row_attrs = """

                onclick="
                event.stopPropagation();
                window.location.href='{get_individual_payslip}'"

                """

    row_status_class = "status-{status} sent_to_employee-{sent_to_employee}"
    # Mirrors PayslipNav.nested_group_by_fields -- needed here too since
    # this (List) and Nav are separate classes; see the same split in
    # employee/cbv/employees.py's EmployeesList/EmployeeNav.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("group_name", _("Pay Slip Batch")),
        ("start_date", _("Start date")),
        ("end_date", _("End Date")),
        ("basic_pay", _("Basic Pay")),
        ("gross_pay", _("Gross Pay")),
        ("net_pay", _("Net Pay")),
        ("status", _("Status")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__job_role_id", _("Job Role")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
class PayslipNav(HorillaNavView):
    """
    navbar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("payslip-list")
        self.actions = []
        if self.request.user.has_perm("payroll.add_payslip"):
            # self.create_attrs = f"""
            #     data-target="#genericModal"
            #     data-toggle="oh-modal-toggle"
            #     hx-get="{reverse('payroll-create-form-view')}"
            #     hx-target="#genericModalBody"
            # """
            self.create_attrs = """
                data-toggle="oh-modal-toggle"
                data-target="#bulkPayslipModal"
                style="cursor:pointer;"
            """

            self.actions.extend(
                [
                    {
                        "action": _("Generate"),
                        "attrs": """
                    data-toggle = "oh-modal-toggle"
                    data-target = "#bulkPayslipModal"
                    style="cursor: pointer;"
                """,
                    },
                    {
                        "action": _("Payslip Report"),
                        "attrs": f"""
                            data-toggle = "oh-modal-toggle"
                            data-target = "#genericModal"
                            hx-target="#genericModalBody"
                            hx-get ="{reverse('payslip-detailed-export')}"
                            style="cursor: pointer;"
                """,
                    },
                    {
                        "action": _("Send Via Mail"),
                        "attrs": """
                   onclick="bulkSendViaMail()"
                    style="cursor: pointer;"
                """,
                    },
                ]
            )
        else:
            self.create_attrs = None

        if has_export_access(self.request, Payslip):
            self.actions.append(
                {
                    "action": _("Export"),
                    "attrs": f"""
                    data-toggle = "oh-modal-toggle"
                    data-target = "#payslipExport"
                    hx-target="#payslipExportForm"
                    hx-get ="{reverse('payslip-bulk-export-data')}"
                    hx-vals='js:{{"has_selection": (JSON.parse(document.getElementById("selectedInstances")?.getAttribute("data-ids")||"[]").length>0)}}'
                    style="cursor: pointer;"
                """,
                }
            )

        if self.request.user.has_perm("payroll.add_payslip"):
            self.actions.append(
                {
                    "action": _("Delete"),
                    "attrs": """
                            onclick="payslipBulkDelete()"
                            data-action ="delete"
                            style="cursor: pointer; color:red !important"
                             """,
                }
            )

    nav_title = _("Payslip")
    filter_body_template = "cbv/payslip/payslip_filter.html"
    filter_instance = PayslipFilter()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. PayslipFilter.ajax_fields carries the
    # AJAX-loaded Employee combobox this needs.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("group_name", _("Pay Slip Batch")),
        ("start_date", _("Start date")),
        ("end_date", _("End Date")),
        ("basic_pay", _("Basic Pay")),
        ("gross_pay", _("Gross Pay")),
        ("net_pay", _("Net Pay")),
        ("status", _("Status")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__job_role_id", _("Job Role")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]
    # Mirrors PayslipList.nested_group_by_fields below -- List and Nav are
    # separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split), so the inline
    # "add/change field" dropdowns in the "Grouped by" breadcrumb
    # (nested_group_by_table.html, rendered by the List view) need this
    # here too, not just the currently-active fields it already had access
    # to via nested_fields_active.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("group_name", _("Pay Slip Batch")),
        ("start_date", _("Start date")),
        ("end_date", _("End Date")),
        ("basic_pay", _("Basic Pay")),
        ("gross_pay", _("Gross Pay")),
        ("net_pay", _("Net Pay")),
        ("status", _("Status")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__job_role_id", _("Job Role")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(login_required, name="dispatch")
class PayslipBulkExport(TemplateView):
    """
    bulk export
    """

    template_name = "cbv/payslip/payslip_export.html"

    def get(self, request, *args, **kwargs):
        if not has_export_access(request, Payslip):
            return HorillaRedirect(
                request, message=_("You dont have access to export this data")
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any):
        """
        Override the get_context_data method to add Payslip export related data to the context
        Args:
            **kwargs (Dict[str, Any]): Keyword arguments passed to the method
        Returns:
            Dict[str, Any]: Updated context dictionary containing export form and filter.
        """
        payslip = Payslip.objects.all()
        export_column = forms.PayslipExportColumnForm
        export_filter = PayslipFilter(queryset=payslip)
        context = super().get_context_data(**kwargs)
        context["export_column"] = export_column
        context["export_filter"] = export_filter
        context["hide_export_filters"] = self.request.GET.get("has_selection") == "true"
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.add_payslip"), name="dispatch")
class PayrollCreateFormView(HorillaFormView):
    """
    form view for creating payslip
    """

    model = Payslip
    form_class = forms.PayslipForm
    new_display_title = _("Create Payslip")
    template_name = "cbv/payslip/payslip_inherit_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["view_id"] = "payslipCreate"

        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        """
        form invalid function
        """
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: forms.PayslipForm) -> HttpResponse:
        """
        form valid function
        """
        if form.is_valid():
            employee = form.cleaned_data["employee_id"]
            start_date = form.cleaned_data["start_date"]
            end_date = form.cleaned_data["end_date"]
            payslip = Payslip.objects.filter(
                employee_id=employee, start_date=start_date, end_date=end_date
            ).first()
            contract = Contract.objects.filter(
                employee_id=employee, contract_status="active"
            ).first()
            if start_date < contract.contract_start_date:
                start_date = contract.contract_start_date
            payslip_data = payroll_calculation(employee, start_date, end_date)
            payslip_data["payslip"] = payslip
            data = {}
            data["employee"] = employee
            data["start_date"] = payslip_data["start_date"]
            data["end_date"] = payslip_data["end_date"]
            data["status"] = (
                "draft"
                if self.request.GET.get("status") is None
                else self.request.GET["status"]
            )
            data["contract_wage"] = payslip_data["contract_wage"]
            data["basic_pay"] = payslip_data["basic_pay"]
            data["gross_pay"] = payslip_data["gross_pay"]
            data["deduction"] = payslip_data["total_deductions"]
            data["net_pay"] = payslip_data["net_pay"]
            data["pay_data"] = json.loads(payslip_data["json_data"])
            calculate_employer_contribution(data)
            data["installments"] = payslip_data["installments"]
            payslip_data["instance"] = save_payslip(**data)
            form = forms.PayslipForm()
            messages.success(self.request, _("Payslip Saved"))
            payslip = payslip_data["instance"]
            notify.send(
                self.request.user.employee_get,
                recipient=employee.employee_user_id,
                verb="Payslip has been generated for you.",
                verb_ar="تم إصدار كشف راتب لك.",
                verb_de="Gehaltsabrechnung wurde für Sie erstellt.",
                verb_es="Se ha generado la nómina para usted.",
                verb_fr="La fiche de paie a été générée pour vous.",
                redirect=reverse(
                    "view-created-payslip", kwargs={"payslip_id": payslip.pk}
                ),
                icon="close",
            )
            # form.save()
            return self.HttpResponse()
        return super().form_valid(form)


class PayrollTab(PayslipList):
    """
    class for rendering payroll tab in employee profile
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        queryset = self.model.objects.filter(employee_id=pk)
        return queryset

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse("individual-payslip-tab-list", kwargs={"pk": pk})

    columns = [col for col in PayslipList.columns if col[0] != _("Status")]
    columns.append((_("Status"), "get_status"))

    action_method = "get_download_url"


EmployeeProfileView.add_tab(
    tabs=[
        {
            "title": _("Payroll"),
            "view": PayrollTab.as_view(),
            "accessibility": "payroll.cbv.accessibility.payroll_accessibility",
        },
        {
            "title": _("Allowance & Deduction"),
            "view": AllowanceDeductionTabView.as_view(),
            # "view": views.allowances_deductions_tab,
            "accessibility": "payroll.cbv.accessibility.allowance_and_deduction_accessibility",
        },
        {
            "title": _("Bonus Points"),
            "view": employee_view.bonus_points_tab,
            "accessibility": "payroll.cbv.accessibility.bonus_accessibility",
        },
    ]
)

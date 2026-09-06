"""
this page is handling the cbv methods of loan/advanced salary page
"""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from attendance.cbv.tab_shell import AttendanceTabContentShell
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
)
from payroll.filters import LoanAccountFilter
from payroll.forms.component_forms import LoanAccountForm
from payroll.models.models import LoanAccount, Payslip


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class AdvanceSalaryView(TemplateView):
    """
    for loan/advance salary page
    """

    template_name = "cbv/loan/loan_main.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class LoansGenericTab(HorillaTabView):
    """
    Tab view for loans/advanced salary
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "loan-generic-tab-view"
        self.tabs = [
            {
                "title": _("Loan"),
                "url": f"{reverse('loan-tab-shell')}",
            },
            {
                "title": _("Salary Advance"),
                "url": f"{reverse('advanced-salary-tab-shell')}",
            },
            {
                "title": _("Fine"),
                "url": f"{reverse('fine-tab-shell')}",
            },
        ]

    def get_context_data(self, **kwargs):
        qs = LoanAccount.objects.all()
        filter_class = LoanAccountFilter
        if filter_class:
            qs = filter_class(
                data=self.request.GET, queryset=qs, request=self.request
            ).qs

        loan_count = qs.filter(type="loan").count()
        adv_count = qs.filter(type="advanced_salary").count()
        fine_count = qs.filter(type="fine").count()

        loan_url = reverse("loan-tab-shell")
        adv_url = reverse("advanced-salary-tab-shell")
        fine_url = reverse("fine-tab-shell")

        for tab in self.tabs:
            url = tab.get("url", "")
            if loan_url in url:
                tab["badge"] = loan_count
            elif adv_url in url:
                tab["badge"] = adv_count
            elif fine_url in url:
                tab["badge"] = fine_count

        context = super().get_context_data(**kwargs)
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class LoanListView(HorillaListView):
    """
    List view for loan tab
    """

    bulk_update_fields = [
        "provided_date",
        "installment_start_date",
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("loan-tab-list-view")

    def get_queryset(self):
        """
        queryset for rendering loan data only
        """
        queryset = super().get_queryset()
        queryset = queryset.filter(type="loan")
        return queryset

    filter_class = LoanAccountFilter
    model = LoanAccount

    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Title"), "title"),
        (_("Provided Date"), "provided_date"),
        (_("Installment Start Date"), "installment_start_date"),
        (_("Toatal Installments"), "installments"),
        (_("Amount"), "loan_amount"),
        (_("Description"), "description"),
        (_("Progress Bar"), "progress_bar_col"),
    ]

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Provided Date"), "provided_date"),
        (_("Installment Start Date"), "installment_start_date"),
        (_("Toatal Installments"), "installments"),
        (_("Amount"), "loan_amount"),
    ]

    action_method = "loan_actions"

    row_attrs = """
                hx-get='{loan_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """
    # Mirrors LoanNavView.nested_group_by_fields -- needed here too since
    # this (List) and Nav are separate classes; see the same split in
    # employee/cbv/employees.py's EmployeesList/EmployeeNav. Inherited by
    # AdvancedSalaryList/FinesListView below, covering all 3 tabs.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("title", _("Title")),
        ("provided_date", _("Provided Date")),
        ("installment_start_date", _("Installment Start Date")),
        ("installments", _("Total Installments")),
        ("loan_amount", _("Amount")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employment Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class AdvancedSalaryList(LoanListView):
    """
    List view for advanced salary
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("advanced-salary-list-view")

    def get_queryset(self):
        queryset = HorillaListView.get_queryset(self)
        queryset = queryset.filter(type="advanced_salary")
        return queryset


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class FinesListView(LoanListView):
    """
    List view for fines tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("fines-list-view")

    def get_queryset(self):
        queryset = HorillaListView.get_queryset(self)
        queryset = queryset.filter(type="fine")
        return queryset


class _LoanTabNavBase(HorillaNavView):
    """
    Shared Search/Filter wiring for each Loans & Salary Advances tab's own,
    independent Nav - nav_title/search_url/search_swap_target/create_attrs
    differ per tab, since each tab's Create button must open its own
    type-scoped form (see LoanFormView.loan_type) and its heading should
    read as that tab's own name, not the page's combined name.
    """

    filter_body_template = "cbv/loan/loan_filter.html"
    filter_instance = LoanAccountFilter()
    filter_form_context_name = "form"

    def _set_create_attrs(self, create_url_name: str) -> None:
        self.create_attrs = f"""
             hx-get="{reverse_lazy(create_url_name)}"
             hx-target="#genericModalBody"
             data-target="#genericModal"
             data-toggle="oh-modal-toggle"
         """

    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. LoanAccountFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class LoanNav(_LoanTabNavBase):
    """
    Independent Nav for the Loan tab.
    """

    nav_title = _("Loan")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("loan-tab-list-view")
        self.search_swap_target = "#loanListContainer"
        self._set_create_attrs("loan-create-form")


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class AdvancedSalaryNav(_LoanTabNavBase):
    """
    Independent Nav for the Salary Advance tab.
    """

    nav_title = _("Salary Advance")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("advanced-salary-list-view")
        self.search_swap_target = "#advancedSalaryListContainer"
        self._set_create_attrs("advanced-salary-create-form")


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class FineNav(_LoanTabNavBase):
    """
    Independent Nav for the Fine tab.
    """

    nav_title = _("Fine")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("fines-list-view")
        self.search_swap_target = "#fineListContainer"
        self._set_create_attrs("fine-create-form")


class LoanTabShell(AttendanceTabContentShell):
    nav_url_name = "loan-nav"
    container_id = "loanListContainer"
    tabs_root_id = "loan-generic-tab-view"


class AdvancedSalaryTabShell(AttendanceTabContentShell):
    nav_url_name = "advanced-salary-nav"
    container_id = "advancedSalaryListContainer"
    tabs_root_id = "loan-generic-tab-view"


class FineTabShell(AttendanceTabContentShell):
    nav_url_name = "fine-nav"
    container_id = "fineListContainer"
    tabs_root_id = "loan-generic-tab-view"

    # Mirrors LoanListView.nested_group_by_fields below -- List and Nav
    # are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split), so the inline
    # "add/change field" dropdowns in the "Grouped by" breadcrumb
    # (nested_group_by_table.html, rendered by the List view) need this
    # here too, not just the currently-active fields it already had
    # access to via nested_fields_active.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("title", _("Title")),
        ("provided_date", _("Provided Date")),
        ("installment_start_date", _("Installment Start Date")),
        ("installments", _("Total Installments")),
        ("loan_amount", _("Amount")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employment Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class LoanDetailView(HorillaDetailedView):
    """
    detail view for the loan page
    """

    model = LoanAccount
    template_name = "cbv/loan/loan_detail_view.html"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        pk = self.kwargs.get("pk")
        loan = LoanAccount.objects.get(id=pk)
        installments = list(loan.deduction_ids.all())
        self._attach_installment_payslips(installments)
        loan_id = self.request.GET.get("loan_id")
        ded_id = self.request.GET.get("ded_id")
        context["loan"] = loan
        context["loan_id"] = loan_id
        context["ded_id"] = ded_id
        context["installments"] = installments
        return context

    @staticmethod
    def _attach_installment_payslips(installments: list) -> None:
        """
        Loans can have hundreds of installments, and the repayment schedule
        template/filters check `deduction.installment_payslip` per row (and
        twice more for the paid/balance totals) -- left alone, that's a
        `Payslip.objects.filter(...).first()` query per check, so one loan
        with N installments cost 3N+ queries to render. Resolve all of them
        here in a single query against the M2M through table and pre-set
        the cached_property so no per-installment query happens later.
        """
        if not installments:
            return
        payslip_id_by_deduction_id = dict(
            Payslip.installment_ids.through.objects.filter(
                deduction_id__in=[installment.id for installment in installments]
            ).values_list("deduction_id", "payslip_id")
        )
        payslip_by_id = Payslip.objects.in_bulk(payslip_id_by_deduction_id.values())
        for installment in installments:
            installment.installment_payslip = payslip_by_id.get(
                payslip_id_by_deduction_id.get(installment.id)
            )


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class LoanFormView(HorillaFormView):
    """
    Form view for creating and editing loans. Also the base class for
    AdvancedSalaryFormView/FineFormView below, which reuse everything here
    and only override `new_display_title`/`loan_type` to scope their tab's
    Create button to that type. The Type field is never shown - fixed to
    the tab's own type on create, and left as-is (unchanged) on edit, since
    which type a record is doesn't change after creation either.
    """

    form_class = LoanAccountForm
    model = LoanAccount
    new_display_title = _("Loan")
    loan_type = "loan"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if not form.instance.pk:
            # Each tab only ever creates its own type, so there's nothing
            # for the user to choose here.
            form.instance.type = self.loan_type
        form.fields.pop("type", None)
        return form

    def form_valid(self, form: LoanAccountForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("%(title)s Updated Successfully") % {
                    "title": form.instance.get_type_display()
                }
            else:
                message = _("New %(title)s Created Successfully") % {
                    "title": self.new_display_title
                }
            form.save()

            messages.success(self.request, message)
            return self.HttpResponse(
                "<script>$('#reloadMessagesButton').click();</script>"
            )
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class AdvancedSalaryFormView(LoanFormView):
    """
    Create form view scoped to the Salary Advance tab.
    """

    new_display_title = _("Salary Advance")
    loan_type = "advanced_salary"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("payroll.view_loanaccount"), name="dispatch")
class FineFormView(LoanFormView):
    """
    Create form view scoped to the Fine tab.
    """

    new_display_title = _("Fine")
    loan_type = "fine"

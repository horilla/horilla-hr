"""
Contracts page
"""

from typing import Any

from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from base.methods import has_export_access
from horilla_views.cbv_methods import (
    hx_request_required,
    login_required,
    permission_required,
)
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)
from payroll.filters import ContractFilter
from payroll.forms.component_forms import ContractExportFieldForm
from payroll.models.models import Contract


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.view_contract"), name="dispatch")
class ContractsView(TemplateView):
    """
    Contracts
    """

    template_name = "cbv/contracts/contracts.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.view_contract"), name="dispatch")
class ContractsList(HorillaListView):
    """
    List view
    """

    quick_export = False

    bulk_update_fields = [
        "contract_start_date",
        "contract_end_date",
        "wage_type",
        "filing_status",
        "wage",
        "contract_status",
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("contract-filter")
        self.view_id = "contract-container"

    model = Contract
    filter_class = ContractFilter

    columns = [
        (_("Contract"), "contract_name"),
        (_("Employee"), "employee_id"),
        (_("Start Date"), "contract_start_date"),
        (_("End Date"), "contract_end_date"),
        (_("Wage Type"), "get_wage_type_display"),
        (_("Basic Salary"), "wage"),
        (_("Filing Status"), "filing_status"),
        (_("Salary Structure"), "salary_structure_id"),
        (_("Status"), "status_col"),
    ]

    header_attrs = {
        "contract_name": """
                          style="width:250px !important;"
                          """
    }

    sortby_mapping = [
        (_("Contract"), "contract_name"),
        (_("Employee"), "employee_id__get_full_name"),
        (_("Start Date"), "contract_start_date"),
        (_("End Date"), "contract_end_date"),
        (_("Basic Salary"), "wage"),
        (_("Status"), "status_col"),
    ]

    action_method = "actions_col"

    row_status_indications = [
        (
            "terminated--dot",
            _("Terminated"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=contract_status]').val('terminated');
                $('#applyFilter').click();

            "
            """,
        ),
        (
            "expired--dot",
            _("Expired"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=contract_status]').val('expired');
                $('#applyFilter').click();

            "
            """,
        ),
        (
            "draft--dot",
            _("Draft"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=contract_status]').val('draft');
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "active--dot",
            _("Active"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=contract_status]').val('active');
                $('#applyFilter').click();

            "
            """,
        ),
    ]

    row_status_class = "status-{contract_status}"

    row_attrs = """
                hx-get='{contracts_detail}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    # Mirrors ContractsNav.nested_group_by_fields below -- List and Nav
    # are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split).
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("contract_status", _("Status")),
        ("employee_id__employee_work_info__shift_id", _("Shift")),
        ("employee_id__employee_work_info__work_type_id", _("Work Type")),
        ("employee_id__employee_work_info__job_role_id", _("Job Role")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.view_contract"), name="dispatch")
class ContractsNav(HorillaNavView):
    """
    Nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("contract-filter")
        if self.request.user.has_perm("payroll.add_contract"):
            self.create_attrs = f"""
                            href="#"
                            hx-get="{reverse('contract-create')}"
                            hx-target="#listContainer"
                            hx-swap="innerHTML"
                            """
        self.actions = []
        if has_export_access(self.request, Contract):
            self.actions.append(
                {
                    "action": _("Export"),
                    "attrs": f"""
                        data-toggle="oh-modal-toggle"
                        data-target="#hxContractExport"
                        hx-get="{reverse_lazy('contracts-export')}"
                        hx-target="#hxContractExportForm"
                        hx-vals='js:{{"has_selection": (JSON.parse(document.getElementById("selectedInstances")?.getAttribute("data-ids")||"[]").length>0)}}'
                        style="cursor: pointer;"
                        """,
                }
            )
        self.actions.append(
            {
                "action": _("Delete"),
                "attrs": """
                    onclick="
                    DeleteContractBulk();
                    "
                    data-action ="delete"
                    style="cursor: pointer; color:red !important"
                    """,
            }
        )

    nav_title = _("Contracts")
    filter_body_template = "cbv/contracts/filter.html"
    filter_instance = ContractFilter()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. ContractFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("contract_status", _("Status")),
        ("employee_id__employee_work_info__shift_id", _("Shift")),
        ("employee_id__employee_work_info__work_type_id", _("Work Type")),
        ("employee_id__employee_work_info__job_role_id", _("Job Role")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]

    # Mirrors ContractsList.nested_group_by_fields above
    nested_group_by_fields = group_by_fields


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.view_contract"), name="dispatch")
class ContractsExportView(TemplateView):
    """
    For contracts export
    """

    template_name = "cbv/contracts/export.html"

    def get_context_data(self, **kwargs: Any):
        """
        Return context data for rendering contract export fields and filters.
        """
        context = super().get_context_data(**kwargs)
        conracts = Contract.objects.all()
        export_column = ContractExportFieldForm
        export_filter = ContractFilter(queryset=conracts)
        context["export_column"] = export_column
        context["export_filter"] = export_filter
        context["hide_export_filters"] = self.request.GET.get("has_selection") == "true"
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="payroll.view_contract"), name="dispatch")
class ContractsDetailView(HorillaDetailedView):
    """
    Detail View
    """

    def get_context_data(self, **kwargs: Any):
        """
        Return context data with the title set to the contract's name.
        """
        context = super().get_context_data(**kwargs)
        contract_name = context["contract"].contract_name
        context["title"] = contract_name
        return context

    model = Contract
    detail_view_url_name = "contracts-detail-view"
    detail_view_permission = "payroll.view_contract"
    # title = _("Details")

    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "conract_subtitle",
        "avatar": "employee_id__get_avatar",
    }

    body = [
        (_("Start Date"), "contract_start_date"),
        (_("End Date"), "contract_end_date"),
        (_("Wage Type"), "get_wage_type_display"),
        (_("Basic Salary"), "wage"),
        (_("Deduct From Basic Pay"), "deduct_leave_from_basic_pay_col"),
        (_("Department"), "department"),
        (_("Job Position"), "job_position"),
        (_("Job Role"), "job_role"),
        (_("Shift"), "shift"),
        (_("Work Type"), "work_type"),
        (_("Filing Status"), "filing_status"),
        (_("Salary Structure"), "salary_structure_id"),
        (_("Pay Frequency"), "get_pay_frequency_display"),
        (_("Status"), "get_status_display"),
        (_("Calculate Leave Amount"), "cal_leave_amount", True),
        (_("Note"), "note_col", True),
        (_("Document"), "edocument_col", True),
    ]

    action_method = "detail_action"

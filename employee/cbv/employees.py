"""
employee view page
"""

import logging
import threading
from typing import Any

from django import forms
from django.apps import apps
from django.contrib.auth.hashers import identify_hasher, make_password
from django.core.cache import cache as CACHE
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.dispatch import receiver
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from accessibility.cbv_decorators import enter_if_accessible
from accessibility.models import DefaultAccessibility
from base.context_processors import enable_profile_edit
from base.methods import eval_validate, has_export_access, is_reportingmanager
from employee.filters import EmployeeFilter
from employee.forms import BulkUpdateFieldForm, EmployeeExportExcelForm
from employee.models import Employee, EmployeeBankDetails, EmployeeWorkInformation
from employee.templatetags.employee_filter import edit_accessibility
from employee.views import _check_reporting_manager
from horilla.horilla_middlewares import _thread_locals
from horilla.signals import post_generic_delete, post_generic_import
from horilla_auth.models import HorillaUser
from horilla_views.cbv_methods import hx_request_required, login_required
from horilla_views.forms import DynamicBulkUpdateForm
from horilla_views.generic.cbv.views import (
    HorillaCardView,
    HorillaDetailedView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
)

logger = logging.getLogger(__name__)


def profile_edit_accessibility_display(self):
    """
    Profile edit accessible
    """
    request = _thread_locals.request
    if self.pk in request.all_edit_accessible_employees:
        return _("Revoke Profile Edit Access")
    return _("Add Profile Edit Access")


def toggle_profile_edit_access_url(self):
    """
    toggle profiel edit access url get method
    """
    return (
        reverse("profile-edit-access", kwargs={"emp_id": self.pk})
        + "?feature=profile_edit"
    )


Employee.profile_edit_accessibility_display = profile_edit_accessibility_display
Employee.toggle_profile_edit_access_url = toggle_profile_edit_access_url


@method_decorator(login_required, name="dispatch")
@method_decorator(
    enter_if_accessible(
        feature="employee_view",
        perm="employee.view_employee",
        method=_check_reporting_manager,
    ),
    name="dispatch",
)
class EmployeesView(TemplateView):
    """
    Employees view

    """

    template_name = "cbv/employees_view/view_employees.html"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        update_fields = BulkUpdateFieldForm()
        context["update_fields_form"] = update_fields
        if not self.request.GET and self.request.session.session_key:
            cached = CACHE.get(
                self.request.session.session_key + reverse("employees-list") + "cbv"
            )
            if cached and cached.get("query_dict"):
                context["initial_nav_query"] = cached["query_dict"].urlencode()
        return context


from base import models as base_models


@method_decorator(login_required, name="dispatch")
@method_decorator(
    enter_if_accessible(
        feature="employee_view",
        perm="employee.view_employee",
        method=_check_reporting_manager,
    ),
    name="dispatch",
)
class EmployeesList(HorillaListView):
    """
    List view of employees
    """

    model = Employee
    filter_class = EmployeeFilter
    view_id = "view-container"
    # Mirrors EmployeeNav.nested_group_by_fields below -- needed here too
    # since this (List) and EmployeeNav are separate classes, and the
    # inline "add/change field" dropdowns in the "Grouped by" breadcrumb
    # (nested_group_by_table.html, rendered by this List view) need the
    # full set of available fields, not just whichever ones are active.
    nested_group_by_fields = [
        ("employee_work_info__department_id", _("Department")),
        ("employee_work_info__job_position_id", _("Job Position")),
        ("employee_work_info__job_role_id", _("Job Role")),
        ("employee_work_info__shift_id", _("Shift")),
        ("employee_work_info__work_type_id", _("Work Type")),
        ("employee_work_info__reporting_manager_id", _("Reporting Manager")),
        ("employee_work_info__company_id", _("Company")),
    ]
    # The "Actions" dropdown already has an Export entry that exports the
    # selected employees (falling back to the full filtered list when nothing
    # is selected), so this standalone quick-action button would just be a
    # second, redundant way to do the same thing.
    quick_export = False
    bulk_template = "cbv/employees_view/bulk_update_page.html"
    bulk_update_fields = [
        "experience",
        "gender",
        "dob",
        "country",
        "state",
        "city",
        "address",
        "zip",
        "marital_status",
        "children",
        "emergency_contact",
        "emergency_contact_name",
        "emergency_contact_relation",
        "employee_work_info__email",
        "employee_work_info__mobile",
        "employee_work_info__department_id",
        "employee_work_info__job_position_id",
        "employee_work_info__job_role_id",
        "employee_work_info__shift_id",
        "employee_work_info__work_type_id",
        "employee_work_info__reporting_manager_id",
        "employee_work_info__employee_type_id",
        "employee_work_info__location",
        "employee_work_info__date_joining",
        "employee_work_info__basic_salary",
        "employee_work_info__salary_hour",
        "employee_work_info__contract_end_date",
        "employee_work_info__company_id",
        "employee_bank_details__bank_name",
        "employee_bank_details__branch",
        "employee_bank_details__any_other_code1",
        "employee_bank_details__any_other_code2",
        "employee_bank_details__country",
        "employee_bank_details__state",
        "employee_bank_details__city",
    ]

    import_fields = [
        "badge_id",
        # "test",
        "employee_first_name",
        "employee_last_name",
        "employee_user_id__username",
        "employee_user_id__password",
        "email",
        "phone",
        "address",
        "country",
        "state",
        "city",
        "zip",
        "dob",
        "gender",
        "qualification",
        "experience",
        "marital_status",
        "children",
        "emergency_contact",
        "emergency_contact_name",
        "emergency_contact_relation",
        "is_active",
        "employee_work_info__department_id",
        "employee_work_info__job_position_id",
        "employee_work_info__job_role_id",
        "employee_work_info__reporting_manager_id",
        "employee_work_info__shift_id",
        "employee_work_info__work_type_id",
        "employee_work_info__employee_type_id",
        "employee_work_info__location",
        "employee_work_info__company_id",
        "employee_work_info__email",
        "employee_work_info__mobile",
        "employee_work_info__date_joining",
        "employee_work_info__contract_end_date",
        "employee_work_info__basic_salary",
        "employee_work_info__salary_hour",
        "employee_bank_details__bank_name",
        "employee_bank_details__account_number",
        "employee_bank_details__branch",
        "employee_bank_details__address",
        "employee_bank_details__country",
        "employee_bank_details__state",
        "employee_bank_details__city",
        "employee_bank_details__any_other_code1",
        "employee_bank_details__any_other_code2",
    ]
    import_file_name = "Employee Import"
    update_reference = "id"

    import_help = {
        "Id | Reference": ["Dont Alter this column"],
        "Badge ID": ["Ensure no Duplicate Codes"],
        "Reporting Manager": ["Ensure Badge ID with employee exists"],
        "Gender": ["male", "female", "other"],
        "Marital Status": ["single", "married", "divorced"],
        "Date Formats": ["yyyy-mm-dd"],
    }

    import_related_model_column_mapping = {
        "employee_user_id": base_models.HorillaUser,
        # "test": base_models.Department,
        "employee_work_info": EmployeeWorkInformation,
        "employee_bank_details": EmployeeBankDetails,
        "employee_work_info__reporting_manager_id": Employee,
        "employee_work_info__department_id": base_models.Department,
        "employee_work_info__job_position_id": base_models.JobPosition,
        "employee_work_info__job_role_id": base_models.JobRole,
        "employee_work_info__shift_id": base_models.EmployeeShift,
        "employee_work_info__work_type_id": base_models.WorkType,
        "employee_work_info__employee_type_id": base_models.EmployeeType,
        "employee_work_info__company_id": base_models.Company,
    }
    import_related_column_export_mapping = {
        "employee_work_info__reporting_manager_id": "employee_work_info__reporting_manager_id__badge_id",
        "employee_work_info__department_id": "employee_work_info__department_id__department",
        "employee_work_info__job_position_id": "employee_work_info__job_position_id__job_position",
        "employee_work_info__job_role_id": "employee_work_info__job_role_id__job_role",
        "employee_work_info__shift_id": "employee_work_info__shift_id__employee_shift",
        "employee_work_info__work_type_id": "employee_work_info__work_type_id__work_type",
        "employee_work_info__employee_type_id": "employee_work_info__employee_type_id__employee_type",
        "employee_work_info__company_id": "employee_work_info__company_id__company",
    }

    primary_key_mapping = {
        "employee_user_id": "username",
        # "test":"department",
        "employee_work_info__reporting_manager_id": "badge_id",
        "employee_work_info__department_id": "department",
        "employee_work_info__job_position_id": "job_position",
        "employee_work_info__job_role_id": "job_role",
        "employee_work_info__shift_id": "employee_shift",
        "employee_work_info__work_type_id": "work_type",
        "employee_work_info__employee_type_id": "employee_type",
        "employee_work_info__company_id": "company",
    }

    reverse_model_relation_to_base_model = {
        "employee_work_info": "employee_id",
        "employee_bank_details": "employee_id",
    }

    o2o_related_name_mapping = {"employee_user_id": "employee_get"}

    # fk_o2o_field_in_base_model = ["employee_user_id", "test"]
    fk_o2o_field_in_base_model = ["employee_user_id"]
    # Excel column value mapping to the table, one to one relation
    fk_mapping = {
        # "test": "department",
    }

    def get_bulk_form(self):
        """
        Bulk from generating method
        """

        form = DynamicBulkUpdateForm(
            root_model=Employee, bulk_update_fields=self.bulk_update_fields
        )

        form.fields["country"] = forms.ChoiceField(
            required=False,
            widget=forms.Select(
                attrs={
                    "class": "oh-select oh-select-2",
                    "style": "width: 100%; height:45px;",
                }
            ),
        )

        form.fields["state"] = forms.ChoiceField(
            required=False,
            widget=forms.Select(
                attrs={
                    "class": "oh-select oh-select-2",
                    "style": "width: 100%; height:45px;",
                }
            ),
        )

        form.fields["employee_bank_details__country"] = forms.ChoiceField(
            required=False,
            widget=forms.Select(
                attrs={
                    "class": "oh-select oh-select-2",
                    "style": "width: 100%; height:45px;",
                }
            ),
        )

        form.fields["employee_bank_details__state"] = forms.ChoiceField(
            required=False,
            widget=forms.Select(
                attrs={
                    "class": "oh-select oh-select-2",
                    "style": "width: 100%; height:45px;",
                }
            ),
        )

        return form

    def handle_bulk_submission(self, request):
        """
        Ensure work info / bank details rows exist for every selected employee
        before the bulk update runs, mirroring the legacy bulk-update view, so
        `employee_work_info__*` and `employee_bank_details__*` fields also get
        applied to employees who don't have those related rows yet.
        """
        instance_ids = eval_validate(request.POST.get("instance_ids", "[]"))
        for employee_id in instance_ids:
            EmployeeWorkInformation.objects.get_or_create(employee_id_id=employee_id)
            EmployeeBankDetails.objects.get_or_create(employee_id_id=employee_id)
        return super().handle_bulk_submission(request)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("employees-list")

    def get_queryset(self, *args, **kwargs):
        return (
            super()
            .get_queryset(*args, **kwargs)
            .select_related(
                "employee_work_info",
                "employee_work_info__department_id",
                "employee_work_info__job_position_id",
                "employee_work_info__job_role_id",
                "employee_work_info__reporting_manager_id",
                "employee_work_info__shift_id",
                "employee_work_info__work_type_id",
                "employee_work_info__employee_type_id",
                "employee_work_info__company_id",
            )
        )

    columns = [
        (_("Employee"), "employee_name_with_badge_id", "get_avatar"),
        (_("Email"), "get_email"),
        (_("Phone"), "phone"),
        (_("Badge Id"), "badge_id"),
        (_("Job Position"), "employee_work_info__job_position_id"),
        (_("Department"), "employee_work_info__department_id"),
        (_("Shift"), "employee_work_info__shift_id"),
        (_("Work Type"), "employee_work_info__work_type_id"),
        (_("Employee Type"), "employee_work_info__employee_type_id"),
        (_("Job Role"), "employee_work_info__job_role_id"),
        (_("Reporting Manager"), "employee_work_info__reporting_manager_id"),
        (_("Company"), "employee_work_info__company_id"),
        (_("Date of Joining"), "employee_work_info__date_joining"),
        (_("History"), "get_history_col"),
    ]

    default_columns = [
        (_("Employee"), "employee_name_with_badge_id", "get_avatar"),
        (_("Email"), "get_email"),
        (_("Phone"), "phone"),
        (_("Department"), "employee_work_info__department_id"),
        (_("Shift"), "employee_work_info__shift_id"),
        (_("Reporting Manager"), "employee_work_info__reporting_manager_id"),
        (_("Company"), "employee_work_info__company_id"),
    ]

    action_method = "employee_actions"

    header_attrs = {
        "action": """
                   style="width:180px !important;"
                   """
    }

    row_attrs = """
                {diff_cell}
                hx-get="{get_profile_url}"
                hx-target="#listContainer"
                hx-swap="innerHTML"
                hx-push-url="{get_individual_url}"
                class="cursor-pointer"
                """
    sortby_mapping = [
        (_("Employee"), "get_full_name", "get_avatar"),
        (_("Badge Id"), "badge_id"),
        (
            _("Reporting Manager"),
            "employee_work_info__reporting_manager_id__get_full_name",
        ),
        (
            _("Department"),
            "employee_work_info__department_id__department",
        ),
        (
            _("Job Position"),
            "employee_work_info__job_position_id__job_position",
        ),
        (_("Date of Joining"), "employee_work_info__date_joining"),
    ]


def get_detailed_work_url(self):
    """
    Get detailed work url
    """
    return reverse("employee-work-detailed", kwargs={"pk": self.pk})


Employee.get_detailed_work_url = get_detailed_work_url


@method_decorator(login_required, name="dispatch")
class TabEmployeeWorkList(HorillaListView):
    """
    Self Employee Work List
    """

    model = Employee
    filter_class = EmployeeFilter
    # bulk_select_option = False
    filter_selected = False
    show_filter_tags = False

    columns = [
        (_("Badge Id"), "badge_id"),
        (_("Work Email"), "employee_work_info__email"),
        (
            _("Reporting Manager"),
            "employee_work_info__reporting_manager_id__get_full_name",
        ),
        (_("Department"), "employee_work_info__department_id"),
        (_("Job Position"), "employee_work_info__job_position_id__job_position"),
        (_("Job Role"), "employee_work_info__job_role_id__job_role"),
        (_("Shift"), "employee_work_info__shift_id"),
        (_("Work Type"), "employee_work_info__work_type_id"),
        (_("Employee Type"), "employee_work_info__employee_type_id"),
        (_("Company"), "employee_work_info__company_id"),
        (_("Date of Joining"), "employee_work_info__date_joining"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ordered_ids_key = "work_tab_instance_ids"
        self.row_attrs = """
            hx-get="{get_detailed_work_url}"
            hx-target="#genericModalBody"
            data-toggle="oh-modal-toggle"
            data-target="#genericModal"
            style = "cursor:pointer"
        """

    def get_queryset(self):
        """
        Get Queryset
        """

        return super().get_queryset().filter(id=self.request.GET.get("pk"))


@method_decorator(login_required, name="dispatch")
class EmployeeWorkDetails(HorillaDetailedView):
    """
    Employee Detail View
    """

    title = _("Work Information")
    model = Employee

    body = [
        (_("Badge Id"), "badge_id"),
        (_("Work Email"), "employee_work_info__email"),
        (
            _("Reporting Manager"),
            "employee_work_info__reporting_manager_id__get_full_name",
        ),
        (_("Department"), "employee_work_info__department_id"),
        (_("Job Position"), "employee_work_info__job_position_id__job_position"),
        (_("Job Role"), "employee_work_info__job_role_id__job_role"),
        (_("Shift"), "employee_work_info__shift_id"),
        (_("Work Type"), "employee_work_info__work_type_id"),
        (_("Employee Type"), "employee_work_info__employee_type_id"),
        (_("Company"), "employee_work_info__company_id"),
        (_("Date of Joining"), "employee_work_info__date_joining"),
    ]

    def get_queryset(self):
        """
        Get Queryset
        """
        return super().get_queryset().filter(id=self.kwargs.get("pk"))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["instance_ids"] = None
        return context


@method_decorator(login_required, name="dispatch")
class WorkTab(HorillaTabView):
    """
    Work Tab
    """

    model = Employee
    additional_tabs = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tabs = [
            {
                "title": _("Work Information"),
                "url": f"{reverse_lazy('employee-work-tab')}",
            },
        ] + self.additional_tabs

    # def get_context_data(self, **kwargs):
    #     if apps.is_installed("payroll"):
    #         employee = self.model.objects.get(id=self.request.GET.get("pk"))
    #         self.tabs.append(
    #             {
    #                 "title": _("Contract details"),
    #                 "url": f"{reverse_lazy('contract-filter')}?search={employee.get_full_name()}",
    #             },
    #         )
    #     return super().get_context_data(**kwargs)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    enter_if_accessible(
        feature="employee_view",
        perm="employee.view_employee",
        method=_check_reporting_manager,
    ),
    name="dispatch",
)
class EmployeeNav(HorillaNavView):
    """
    For nav bar
    """

    modern_filter = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("employees-list")
        self.search_in = [
            ("employee_work_info__reporting_manager_id", _("Reporting Manager")),
            (
                "employee_work_info__department_id",
                "Department",
            ),
            ("employee_work_info__job_position_id", _("Job Position")),
            ("employee_work_info__job_role_id", _("Job Role")),
            ("employee_work_info__shift_id", _("Shift")),
            ("employee_work_info__work_type_id", _("Work Type")),
            ("employee_work_info__company_id", _("Company")),
        ]
        if self.request.user.has_perm("employee.add_employee"):
            self.create_attrs = f"""
                                href="{reverse_lazy('employee-view-new')}"
                                """
        else:
            self.create_attrs = None

        actions = []
        if self.request.user.has_perm("employee.change_employee"):
            actions.append(
                {
                    "action": _("Import"),
                    "attrs": f"""
                        href="#"
                        data-toggle="oh-modal-toggle"
                        data-target="#objectCreateModal"
                        hx-get="{reverse('work-info-import')}"
                        hx-target="#objectCreateModalTarget"
                        style="cursor: pointer;"
                    """,
                }
            )
        if has_export_access(self.request, Employee):
            actions.append(
                {
                    "action": _("Export"),
                    "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#employeeExport"
                    hx-get="{reverse('employees-export')}"
                    hx-target="#employeeExportForm"
                    hx-vals='js:{{"has_selection": (JSON.parse(document.getElementById("selectedInstances")?.getAttribute("data-ids")||"[]").length>0)}}'
                    style="cursor: pointer;"
                    """,
                }
            )
        if self.request.user.has_perm("employee.change_employee"):
            actions.extend(
                [
                    {
                        "action": _("Archive"),
                        "attrs": """
                        id="archiveEmployees"
                        style="cursor: pointer;"
                        """,
                    },
                    {
                        "action": _("Un-archive"),
                        "attrs": """
                        id="unArchiveEmployees"
                        style="cursor: pointer;"
                        """,
                    },
                    {
                        "action": _("Bulk mail"),
                        "attrs": f"""
                        data-toggle="oh-modal-toggle"
                        data-target="#sendMailModal"
                        hx-get="{reverse('employee-bulk-mail')}"
                        hx-target="#mail-content"
                        style="cursor: pointer;"
                        """,
                    },
                    {
                        "action": _("Delete"),
                        "attrs": """
                        class="oh-dropdown__link--danger"
                        data-action ="delete"
                        id="deleteEmployees"
                        style="cursor: pointer; color:red !important"
                        """,
                    },
                ]
            )
        self.actions = actions or None

        self.view_types = [
            {
                "type": "list",
                "icon": "list-outline",
                "url": reverse("employees-list"),
                "attrs": f"""
                            title ='{_("List")}'
                            """,
            },
            {
                "type": "card",
                "icon": "grid-outline",
                "url": reverse("employees-card"),
                "attrs": f"""
                          title ='{_("Card")}'
                          """,
            },
        ]

    nav_title = _("Employees")
    filter_body_template = "cbv/employees_view/filter_employee.html"
    filter_instance = EmployeeFilter()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    group_by_fields = [
        ("employee_work_info__job_position_id", _("Job Position")),
        (
            "employee_work_info__department_id",
            _("Department"),
        ),
        ("employee_work_info__shift_id", _("Shift")),
        ("employee_work_info__work_type_id", _("Work Type")),
        ("employee_work_info__job_role_id", _("Job Role")),
        ("employee_work_info__reporting_manager_id", _("Reporting Manager")),
        ("employee_work_info__company_id", _("Company")),
    ]
    nested_group_by_fields = [
        ("employee_work_info__department_id", _("Department")),
        ("employee_work_info__job_position_id", _("Job Position")),
        ("employee_work_info__job_role_id", _("Job Role")),
        ("employee_work_info__shift_id", _("Shift")),
        ("employee_work_info__work_type_id", _("Work Type")),
        ("employee_work_info__reporting_manager_id", _("Reporting Manager")),
        ("employee_work_info__company_id", _("Company")),
    ]


@receiver(post_generic_import, sender=HorillaUser)
def user_generic_import_or_update(sender, **kwargs):
    """
    Handle bulk user imports
    """
    records = kwargs["records"]

    def _set_password(records):
        # Create a list to store users that need to be updated
        users_to_update = []

        for instance in records:
            try:
                password = str(instance.password)
                # Try to detect if the password is already hashed
                identify_hasher(password)
            except (ValueError, ImproperlyConfigured):
                # Password is raw, so hash and update it
                instance.password = make_password(password)
                users_to_update.append(instance)

        if users_to_update:
            # Bulk update only the users that were changed
            with transaction.atomic():
                HorillaUser.objects.bulk_update(users_to_update, ["password"])
                logger.info(
                    f"{len(users_to_update)} user passwords were successfully updated."
                )

    thread = threading.Thread(target=_set_password, args=(records,))
    thread.start()


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(
    enter_if_accessible(
        feature="employee_view",
        perm="employee.view_employee",
        method=_check_reporting_manager,
    ),
    name="dispatch",
)
class ExportView(TemplateView):
    """
    For candidate export
    """

    template_name = "cbv/employees_view/employee_export.html"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        employee = Employee.objects.filter(is_active=True)
        export_form = EmployeeExportExcelForm()
        export_filter = EmployeeFilter(queryset=employee)
        context["export_form"] = export_form
        context["export_filter"] = export_filter
        context["hide_export_filters"] = self.request.GET.get("has_selection") == "true"
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(
    enter_if_accessible(
        feature="employee_view",
        perm="employee.view_employee",
        method=_check_reporting_manager,
    ),
    name="dispatch",
)
class EmployeeCard(HorillaCardView):
    """
    For card view
    """

    model = Employee
    filter_class = EmployeeFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("employees-card")
        employee_confirm = _("Do you want to %(status)s this employee?") % {
            "status": "{archive_status}",
        }
        self.request.all_edit_accessible_employees = (
            DefaultAccessibility.objects.filter(feature="profile_edit").values_list(
                "employees__pk", flat=True
            )
        )
        if self.request.user.has_perm(
            "employee.change_employee"
        ) or is_reportingmanager(self.request):
            self.actions = [
                {
                    "action": _("Edit"),
                    "accessibility": "employee.cbv.accessibility.edit_accessibility",
                    "attrs": """
                    onclick="event.stopPropagation()"
                    hx-get="{get_update_url}?container=true"
                    hx-target="#listContainer"
                    hx-swap="innerHTML"
                    hx-push-url="{get_update_url}?container=true"
                    class="oh-dropdown__link"
                """,
                },
                {
                    "action": "archive_status",
                    "accessibility": "employee.cbv.accessibility.action_accessible",
                    "attrs": f"""
                    hx-confirm="{employee_confirm}"
                    hx-post="{{get_archive_url}}"
                    class="oh-dropdown__link"
                    hx-target="#relatedModel"
                    """,
                },
                {
                    "action": _("Delete"),
                    "accessibility": "employee.cbv.accessibility.action_accessible",
                    "attrs": """
                        onclick="event.stopPropagation()"
                        hx-get="{get_delete_url}?model=employee.Employee&pk={pk}"
                        data-toggle="oh-modal-toggle"
                        data-target="#deleteConfirmation"
                        hx-target="#deleteConfirmationBody"
                        class="oh-dropdown__link"
                        style="cursor: pointer;"
                    """,
                },
            ]
            if enable_profile_edit(self.request).get("profile_edit_enabled"):
                self.actions.append(
                    {
                        "action": "profile_edit_accessibility_display",
                        "accessibility": "employee.cbv.accessibility.action_accessible",
                        "attrs": """
                        href="{toggle_profile_edit_access_url}"
                        class="oh-dropdown__link"
                        style="cursor: pointer;"
                    """,
                    }
                )
        else:
            self.actions = None

    details = {
        "image_src": "get_avatar",
        "title": "{employee_name_with_badge_id}",
        "subtitle": "<span class='oh-kanban-card__subtitle'>{get_email}</span><span class='oh-kanban-card__subtitle'>{employee_work_info__job_position_id}</span>",
    }

    custom_body_template = "cbv/employees_view/card_body.html"

    card_attrs = """
                {diff_cell}
                hx-get="{get_profile_url}"
                hx-target="#listContainer"
                hx-swap="innerHTML"
                hx-push-url="{get_individual_url}"
                """


@receiver(post_generic_delete, sender=Employee)
def employee_generic_post_delete(sender, instance, *args, view_instance=None, **kwargs):
    """
    Employee genric post delete signal to handle the deletion of user instance
    """
    if instance.employee_user_id:
        instance.employee_user_id.delete()

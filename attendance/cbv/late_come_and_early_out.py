"""
Late come and early out page
"""

from typing import Any

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from attendance.filters import LateComeEarlyOutFilter
from attendance.forms import LateComeEarlyOutExportForm
from attendance.models import AttendanceLateComeEarlyOut
from base.decorators import manager_can_enter
from base.filters import PenaltyFilter
from base.methods import filtersubordinates, has_export_access, is_reportingmanager
from base.models import PenaltyAccounts
from horilla_views.cbv_methods import hx_request_required, login_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="attendance.view_attendancelatecomeearlyout"),
    name="dispatch",
)
class LateComeAndEarlyOut(TemplateView):
    """
    Late come and early out
    """

    template_name = "cbv/late_come_and_early_out/late_come_and_early_out.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="attendance.view_attendancelatecomeearlyout"),
    name="dispatch",
)
class LateComeAndEarlyOutList(HorillaListView):
    """
    List view
    """

    filter_keys_to_remove = ["late_early_id"]
    quick_export = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("late-come-early-out-search")
        self.view_id = "late-container"
        if (
            not self.request.user.has_perm("base.change_penaltyaccounts")
            and not is_reportingmanager(self.request)
            and not self.request.user.has_perm(
                "perms.attendance.delete_attendancelatecomeearlyout"
            )
        ):
            self.action_method = None
        else:
            self.action_method = "actions_column"

    def get_queryset(self):
        queryset = super().get_queryset().filter(attendance_id__shift_id__isnull=False)
        reports = queryset
        self_reports = queryset.filter(employee_id__employee_user_id=self.request.user)
        reports = filtersubordinates(
            self.request, reports, "attendance.view_attendancelatecomeearlyout"
        )
        queryset = self_reports | reports
        return queryset

    row_attrs = """
                hx-get='{late_come_detail}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    model = AttendanceLateComeEarlyOut
    filter_class = LateComeEarlyOutFilter
    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Type"), "get_type"),
        (_("Attendance Date"), "attendance_id__attendance_date"),
        (_("Check-In"), "attendance_id__attendance_clock_in"),
        (_("In Date"), "attendance_id__attendance_clock_in_date"),
        (_("Check-Out"), "attendance_id__attendance_clock_out"),
        (_("Out Date"), "attendance_id__attendance_clock_out_date"),
        (_("Min Hour"), "attendance_id__minimum_hour"),
        (_("At Work"), "attendance_id__attendance_worked_hour"),
        (_("Penalities"), "penalities_column"),
    ]

    default_columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Type"), "get_type"),
        (_("Attendance Date"), "attendance_id__attendance_date"),
        (_("Check-In"), "attendance_id__attendance_clock_in"),
        (_("Check-Out"), "attendance_id__attendance_clock_out"),
    ]

    header_attrs = {"penalities_column": """ style ="width:170px !important" """}

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Type"), "get_type"),
        (_("Attendance Date"), "attendance_id__attendance_date"),
        (_("Check-In"), "attendance_id__attendance_clock_in"),
        (_("In Date"), "attendance_id__attendance_clock_in_date"),
        (_("Check-Out"), "attendance_id__attendance_clock_out"),
        (_("Out Date"), "attendance_id__attendance_clock_out_date"),
        (_("At Work"), "attendance_id__attendance_worked_hour"),
        (_("Min Hour"), "attendance_id__minimum_hour"),
    ]
    # Mirrors LateComeAndEarlyOutListNav.nested_group_by_fields -- needed
    # here too since this (List) and Nav are separate classes; see the
    # same split in employee/cbv/employees.py's EmployeesList/EmployeeNav.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("type", _("Type")),
        ("attendance_id__attendance_date", _("Attendance Date")),
        ("attendance_id__shift_id", _("Shift")),
        ("attendance_id__work_type_id", _("Work Type")),
        ("attendance_id__minimum_hour", _("Minimum Hour")),
        ("attendance_id__employee_id__country", _("Country")),
        (
            "attendance_id__employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        (
            "attendance_id__employee_id__employee_work_info__department_id",
            _("Department"),
        ),
        (
            "attendance_id__employee_id__employee_work_info__job_position_id",
            _("Job Position"),
        ),
        (
            "attendance_id__employee_id__employee_work_info__employee_type_id",
            _("Employment Type"),
        ),
        ("attendance_id__employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter(perm="attendance.view_attendancelatecomeearlyout"),
    name="dispatch",
)
class LateComeAndEarlyOutListNav(HorillaNavView):
    """
    Nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("late-come-early-out-search")
        actions = []
        if has_export_access(self.request, AttendanceLateComeEarlyOut):
            actions.append(
                {
                    "action": _("Export"),
                    "attrs": f"""
                data-toggle="oh-modal-toggle"
                data-target="#attendanceExport"
                hx-get="{reverse('late-come-and-early-out-export')}"
                hx-target="#attendanceExportForm"
                hx-vals='js:{{"has_selection": (JSON.parse(document.getElementById("selectedInstances")?.getAttribute("data-ids")||"[]").length>0)}}'
                style="cursor: pointer;"
                """,
                }
            )

        if self.request.user.has_perm(
            "base.change_penaltyaccounts"
        ) or self.request.user.has_perm(
            "perms.attendance.delete_attendancelatecomeearlyout"
        ):
            actions.append(
                {
                    "action": _("Delete"),
                    "attrs": """
                    onclick="
                    lateComeBulkDelete();
                    "
                    data-action = "delete"
                    style="cursor: pointer; color:red !important"
                    """,
                },
            )

        self.actions = actions or None

    nav_title = _("Late Arrival & Early Departure")
    filter_instance = LateComeEarlyOutFilter()
    filter_body_template = "cbv/late_come_and_early_out/late_early_filter.html"
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel (horilla_nav.html's .oh-filter-modern
    # styles) -- LateComeEarlyOutFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs, same as AttendancesNavView/
    # AttendanceActivityNavView.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("type", _("Type")),
        ("attendance_id__attendance_date", _("Attendance Date")),
        ("attendance_id__shift_id", _("Shift")),
        ("attendance_id__work_type_id", _("Work Type")),
        ("attendance_id__minimum_hour", _("Minimum Hour")),
        ("attendance_id__employee_id__country", _("Country")),
        (
            "attendance_id__employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        (
            "attendance_id__employee_id__employee_work_info__department_id",
            _("Department"),
        ),
        (
            "attendance_id__employee_id__employee_work_info__job_position_id",
            _("Job Position"),
        ),
        (
            "attendance_id__employee_id__employee_work_info__employee_type_id",
            _("Employment Type"),
        ),
        ("attendance_id__employee_id__employee_work_info__company_id", _("Company")),
    ]
    # Mirrors LateComeAndEarlyOutList.nested_group_by_fields below -- List
    # and Nav are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split), so the inline
    # "add/change field" dropdowns in the "Grouped by" breadcrumb
    # (nested_group_by_table.html, rendered by the List view) need this
    # here too, not just the currently-active fields it already had access
    # to via nested_fields_active.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("type", _("Type")),
        ("attendance_id__attendance_date", _("Attendance Date")),
        ("attendance_id__shift_id", _("Shift")),
        ("attendance_id__work_type_id", _("Work Type")),
        ("attendance_id__minimum_hour", _("Minimum Hour")),
        ("attendance_id__employee_id__country", _("Country")),
        (
            "attendance_id__employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        (
            "attendance_id__employee_id__employee_work_info__department_id",
            _("Department"),
        ),
        (
            "attendance_id__employee_id__employee_work_info__job_position_id",
            _("Job Position"),
        ),
        (
            "attendance_id__employee_id__employee_work_info__employee_type_id",
            _("Employment Type"),
        ),
        ("attendance_id__employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class LateEarlyExportView(TemplateView):
    """
    For  export records
    """

    template_name = "cbv/late_come_and_early_out/late_early_export.html"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        data = AttendanceLateComeEarlyOut.objects.all()
        export_form = LateComeEarlyOutExportForm
        export = LateComeEarlyOutFilter(queryset=data)
        context["export_form"] = export_form
        context["export"] = export
        context["hide_export_filters"] = self.request.GET.get("has_selection") == "true"
        return context


@method_decorator(login_required, name="dispatch")
class LateComeEarlyOutDetailView(HorillaDetailedView):
    """
    Detail View
    """

    model = AttendanceLateComeEarlyOut
    title = _("Details")

    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "late_come_subtitle",
        "avatar": "employee_id__get_avatar",
    }

    body = [
        (_("Type"), "get_type"),
        (_("Attendance Date"), "attendance_id__attendance_date"),
        (_("Check-In"), "attendance_id__attendance_clock_in"),
        (_("Chen-in Date"), "attendance_id__attendance_clock_in_date"),
        (_("Check-Out"), "attendance_id__attendance_clock_out"),
        (_("Check-out Date"), "attendance_id__attendance_clock_out_date"),
        (_("Min Hour"), "attendance_id__minimum_hour"),
        (_("At Work"), "attendance_id__attendance_worked_hour"),
        (_("Shift"), "attendance_id__shift_id"),
        (_("Work Type"), "attendance_id__work_type_id"),
        (_("Attendance Validated"), "attendance_validated_check"),
        (_("Penalities"), "penalities_column"),
    ]

    action_method = "detail_actions"

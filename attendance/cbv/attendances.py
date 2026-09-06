"""
this page is handling the cbv methods of  attendances page
"""

from datetime import datetime, timedelta
from typing import Any

import django_filters
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import resolve, reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from attendance.cbv.attendance_activity import AttendanceActivityListView
from attendance.cbv.attendance_tab import AttendanceTabView
from attendance.cbv.tab_shell import AttendanceTabContentShell
from attendance.filters import AttendanceFilters
from attendance.forms import AttendanceExportForm, AttendanceForm, AttendanceUpdateForm
from attendance.models import Attendance, AttendanceValidationCondition, strtime_seconds
from base.decorators import manager_can_enter
from base.filters import PenaltyFilter
from base.methods import (
    choosesubordinates,
    filtersubordinates,
    has_export_access,
    is_reportingmanager,
)
from base.models import PenaltyAccounts
from employee.cbv.employee_profile import EmployeeProfileView
from employee.cbv.employees import EmployeeCard, EmployeeNav, EmployeesList
from employee.filters import EmployeeFilter
from employee.models import Employee
from horilla.filters import HorillaFilterSet
from horilla_views.cbv_methods import (
    hx_request_required,
    login_required,
    render_template,
)
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
)


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class AttendancesView(TemplateView):
    """
    for attendances page
    """

    template_name = "cbv/attendances/attendance_view_page.html"


@method_decorator(login_required, name="dispatch")
class AttendancesListView(HorillaListView):
    """
    list view
    """

    export_file_name = _("Attendance Report")
    quick_export = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("attendances-list-view")
        if self.request.user.has_perm(
            "attendance.change_attendance"
        ) or is_reportingmanager(self.request):
            self.option_method = "attendance_actions"

    filter_class = AttendanceFilters
    model = Attendance
    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Date"), "attendance_date"),
        (_("Day"), "attendance_day"),
        (_("Check-In"), "attendance_clock_in"),
        (_("In Date"), "attendance_clock_in_date"),
        (_("Check-Out"), "attendance_clock_out"),
        (_("Out Date"), "attendance_clock_out_date"),
        (_("Shift"), "shift_id"),
        (_("Work Type"), "work_type_id"),
        (_("Min Hour"), "minimum_hour"),
        (_("At Work"), "attendance_worked_hour"),
        (_("Pending Hour"), "hours_pending"),
        (_("Overtime"), "attendance_overtime"),
    ]
    default_columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Date"), "attendance_date"),
        (_("Check-In"), "attendance_clock_in"),
        (_("Check-Out"), "attendance_clock_out"),
        (_("Shift"), "shift_id"),
        (_("At Work"), "attendance_worked_hour"),
    ]
    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Date"), "attendance_date"),
        (_("Day"), "attendance_day__day"),
        (_("Check-In"), "attendance_clock_in"),
        (_("In Date"), "attendance_clock_in_date"),
        (_("Check-Out"), "attendance_clock_out"),
        (_("Out Date"), "attendance_clock_out_date"),
        (_("Shift"), "shift_id__employee_shift"),
        (_("Work Type"), "work_type_id__work_type"),
        (_("Min Hour"), "minimum_hour"),
        (_("At Work"), "attendance_worked_hour"),
        (_("Pending Hour"), "hours_pending"),
        (_("Overtime"), "attendance_overtime"),
    ]
    records_per_page = 20
    # Mirrors AttendancesNavView.nested_group_by_fields -- needed here too
    # since this (List) and Nav are separate classes; see the same split
    # in employee/cbv/employees.py's EmployeesList/EmployeeNav.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("attendance_date", _("Attendance Date")),
        ("shift_id", _("Shift")),
        ("work_type_id", _("Work Type")),
        ("minimum_hour", _("Min Hour")),
        ("employee_id__country", _("Country")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        (
            "employee_id__employee_work_info__employee_type_id",
            _("Employement Type"),
        ),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]

    # def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
    #     """
    #     Get queryset
    #     """
    #     get_data = self.request.GET.copy()
    #     # Check if user has set any range filter
    #     has_min = (
    #         "attendance_date__gte" in get_data and get_data["attendance_date__gte"]
    #     )
    #     has_max = (
    #         "attendance_date__lte" in get_data and get_data["attendance_date__lte"]
    #     )

    #     # If no date range is specified, set default to last 2 days
    #     if not has_min and not has_max:
    #         today = datetime.now().date()
    #         two_days_ago = today - timedelta(days=32)
    #         get_data["attendance_date__gte"] = two_days_ago.strftime("%Y-%m-%d")
    #         get_data["attendance_date__lte"] = today.strftime("%Y-%m-%d")

    #     if get_data.get("attendance_date"):
    #         get_data["attendance_date__gte"] = get_data["attendance_date"]
    #         get_data["attendance_date__lte"] = get_data["attendance_date"]

    #     if not self.queryset:
    #         self.queryset = super().get_queryset(
    #             filtered=True, queryset=self.filter_class(get_data).qs
    #         )
    #     return self.queryset


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class AttendancesTabView(HorillaTabView):
    """
    tabview of candidate page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "attendances-tab"
        self.tabs = [
            {
                "title": _("Attendance To Validate"),
                "url": f"{reverse('validate-attendance-tab-shell')}",
            },
            {
                "title": _(" OT Attendances"),
                "url": f"{reverse('ot-attendance-tab-shell')}",
            },
            {
                "title": _(" Validated Attendances"),
                "url": f"{reverse('validated-attendance-tab-shell')}",
            },
        ]

    def get_context_data(self, **kwargs: Any):
        """
        Populate tab badges with list counts so they show before each tab loads.
        """
        context = super().get_context_data(**kwargs)
        counts = attendance_tabs_badge_counts(self.request)
        for idx, tab in enumerate(self.tabs):
            tab["badge"] = counts[idx] if idx < len(counts) else 0
        return context


def _attendance_nav_common_actions(request, extra_action=None):
    """
    Import/Export/Delete, plus one optional bulk action that only makes
    sense on one specific tab (Validate on the Validate tab, Approve OT on
    the OT tab) - duplicated into every Attendances tab's own Nav now that
    each tab carries its own independent Search/Filter/Actions bar instead
    of one bar shared above all three (matches Employee Configuration,
    where every settings tab loads its own Nav rather than sharing one).
    """
    actions = []
    if extra_action:
        actions.append(extra_action)
    actions.append(
        {
            "action": _("Import"),
            "attrs": """
                onclick="
                importAttendanceNav();
                "
                data-toggle = "oh-modal-toggle"
                data-target = "#attendanceImport
                "
                style="cursor: pointer;"
            """,
        }
    )
    if has_export_access(request, Attendance):
        actions.append(
            {
                "action": _("Export"),
                "attrs": f"""
                data-toggle = "oh-modal-toggle"
                data-target = "#genericModal"
                hx-target="#genericModalBody"
                hx-get ="{reverse('attendences-navbar-export')}"
                hx-vals='js:{{"has_selection": (function(){{var t=document.querySelector(".oh-tabs__content--active");var l=(t||document).querySelector("[data-selected-instances-key]");var k=(l&&l.getAttribute("data-selected-instances-key"))||"selectedInstances";var el=document.getElementById(k);return JSON.parse((el&&el.getAttribute("data-ids"))||"[]").length>0;}})()}}'
                style="cursor: pointer;"
            """,
            }
        )
    if request.user.has_perm("attendance.add_attendance"):
        actions.append(
            {
                "action": _("Delete"),
                "attrs": """
                    onclick="
                    bulkDeleteAttendanceNav();
                    "
                    data-action="delete"
                    style="cursor: pointer; color:red !important"
                """,
            }
        )
    return actions


def _attendance_validate_bulk_action():
    return {
        "action": _("Validate"),
        "attrs": """
            onclick="
            bulkValidateTabAttendance();
            "
            style="cursor: pointer;"
        """,
    }


def _attendance_ot_bulk_action():
    return {
        "action": _("Approve OT"),
        "attrs": """
            onclick="
            otBulkValidateTabAttendance();
            "
            style="cursor: pointer;"
        """,
    }


class _AttendanceTabNavBase(HorillaNavView):
    """
    Shared Search/Filter/Create wiring for each Attendances tab's own,
    independent Nav - only search_url/search_swap_target/actions differ
    per tab.
    """

    nav_title = _("Attendances")
    filter_body_template = "cbv/attendances/attendances_filter_page.html"
    filter_instance = AttendanceFilters()
    filter_form_context_name = "form"
    # Opts Attendance into the same modern slide-over filter panel built
    # for Employee (horilla_nav.html's .oh-filter-modern styles) --
    # AttendanceFilters.ajax_fields carries the AJAX-loaded comboboxes
    # this needs.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("attendance_date", _("Attendance Date")),
        ("shift_id", _("Shift")),
        ("work_type_id", _("Work Type")),
        ("minimum_hour", _("Min Hour")),
        ("employee_id__country", _("Country")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        (
            "employee_id__employee_work_info__employee_type_id",
            _("Employement Type"),
        ),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]
    # Mirrors AttendancesListView.nested_group_by_fields below -- List and
    # Nav are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split), so the inline
    # "add/change field" dropdowns in the "Grouped by" breadcrumb
    # (nested_group_by_table.html, rendered by the List view) need this
    # here too, not just the currently-active fields it already had access
    # to via nested_fields_active.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("attendance_date", _("Attendance Date")),
        ("shift_id", _("Shift")),
        ("work_type_id", _("Work Type")),
        ("minimum_hour", _("Min Hour")),
        ("employee_id__country", _("Country")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        (
            "employee_id__employee_work_info__employee_type_id",
            _("Employement Type"),
        ),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_in = [
            ("attendance_day", _("Day")),
            ("shift_id", _("Shift")),
            ("work_type_id", _("Work Type")),
            ("employee_id__employee_work_info__department_id", _("Department")),
            (
                "employee_id__employee_work_info__job_position_id",
                _("Job Position"),
            ),
            ("employee_id__employee_work_info__company_id", _("Company")),
        ]
        self.create_attrs = f"""
             hx-get="{reverse_lazy("attendance-create")}"
             hx-target="#genericModalBody"
             data-target="#genericModal"
             data-toggle="oh-modal-toggle"
         """


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class ValidateAttendanceNav(_AttendanceTabNavBase):
    """
    Independent Nav for the Attendance To Validate tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("validate-attendance-tab")
        self.search_swap_target = "#validateListContainer"
        self.actions = _attendance_nav_common_actions(
            self.request, _attendance_validate_bulk_action()
        )


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class OTAttendanceNav(_AttendanceTabNavBase):
    """
    Independent Nav for the OT Attendances tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("ot-attendance-tab")
        self.search_swap_target = "#otListContainer"
        self.actions = _attendance_nav_common_actions(
            self.request, _attendance_ot_bulk_action()
        )


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class ValidatedAttendanceNav(_AttendanceTabNavBase):
    """
    Independent Nav for the Validated Attendances tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("validated-attendance-tab")
        self.search_swap_target = "#validatedListContainer"
        self.actions = _attendance_nav_common_actions(self.request)


class ValidateAttendanceTabShell(AttendanceTabContentShell):
    nav_url_name = "validate-attendance-nav"
    container_id = "validateListContainer"
    tabs_root_id = "attendances-tab"
    selected_instances_key_id = "validateselectedInstances"


class OTAttendanceTabShell(AttendanceTabContentShell):
    nav_url_name = "ot-attendance-nav"
    container_id = "otListContainer"
    tabs_root_id = "attendances-tab"
    selected_instances_key_id = "overtimeselectedInstances"


class ValidatedAttendanceTabShell(AttendanceTabContentShell):
    nav_url_name = "validated-attendance-nav"
    container_id = "validatedListContainer"
    tabs_root_id = "attendances-tab"
    selected_instances_key_id = "validatedselectedInstances"


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class AttendancesExportNav(TemplateView):
    """
    for bulk export
    """

    template_name = "cbv/attendances/attendances_export_page.html"

    def get_context_data(self, **kwargs: Any):
        """
        get data for export
        """

        attendances = Attendance.objects.all()
        export_form = AttendanceExportForm
        export = AttendanceFilters(queryset=attendances)
        context = super().get_context_data(**kwargs)
        context["export_form"] = export_form
        context["export"] = export
        context["hide_export_filters"] = self.request.GET.get("has_selection") == "true"
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class ValidateAttendancesList(AttendancesListView):
    """
    validate tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("validate-attendance-tab")
        self.option_method = None

    def get_queryset(self):
        if not self.queryset:
            self.queryset = super().get_queryset()
            self.queryset = self.queryset.filter(
                attendance_validated=False, employee_id__is_active=True
            )
            self.queryset = filtersubordinates(
                self.request, self.queryset, "attendance.view_attendance"
            )
        return self.queryset

    selected_instances_key_id = "validateselectedInstances"
    action_method = "validate_actions"
    row_attrs = """
                hx-get='{validate_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    header_attrs = {
        "action": """
                    style="width:150px !important;"
                """
    }


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class OTAttendancesList(AttendancesListView):
    """
    OT tab
    """

    selected_instances_key_id = "overtimeselectedInstances"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("ot-attendance-tab")
        self.action_method = "ot_actions"
        self.option_method = None
        self.ordered_ids_key = "overtime_instance_ids"

    def get_queryset(self):
        if not self.queryset:
            self.queryset = super().get_queryset()
            minot = strtime_seconds("00:30")
            condition = (
                AttendanceValidationCondition.objects.first()
            )  # and condition.minimum_overtime_to_approve is not None
            if condition is not None:
                minot = strtime_seconds(condition.minimum_overtime_to_approve)
            self.queryset = self.queryset.filter(
                overtime_second__gt=0,
                attendance_validated=True,
            )
            self.queryset = filtersubordinates(
                self.request, self.queryset, "attendance.view_attendance"
            )
        return self.queryset

    row_attrs = """
                hx-get='{ot_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """
    header_attrs = {
        "action": """
                    style="width:150px !important;"
                """
    }


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class ValidatedAttendancesList(AttendancesListView):
    """
    validated tab
    """

    selected_instances_key_id = "validatedselectedInstances"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("validated-attendance-tab")
        if self.option_method:
            self.action_method = self.option_method
            self.option_method = None

    def get_queryset(self):

        if not self.queryset:
            self.queryset = super().get_queryset()
            self.queryset = self.queryset.filter(
                attendance_validated=True, employee_id__is_active=True
            )
            self.queryset = filtersubordinates(
                self.request, self.queryset, "attendance.view_attendance"
            )
        return self.queryset

    row_attrs = """
                hx-get='{validated_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


def _badge_count_from_attendance_list_view(request, view_cls):
    """
    Use the same queryset rules as each tab's HorillaListView (filters, subordinates).
    """
    view = view_cls()
    view.request = request
    view.args = ()
    view.kwargs = {}
    view.queryset = None
    return view.get_queryset().count()


def attendance_tabs_badge_counts(request):
    """
    Badge order matches AttendancesTabView.tabs: validate, OT, validated.
    """
    return [
        _badge_count_from_attendance_list_view(request, ValidateAttendancesList),
        _badge_count_from_attendance_list_view(request, OTAttendancesList),
        _badge_count_from_attendance_list_view(request, ValidatedAttendancesList),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class GenericAttendancesDetailView(HorillaDetailedView):
    """
    Generic Detail view of page
    """

    model = Attendance

    title = _("Details")
    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "attendances_detail_subtitle",
        "avatar": "employee_id__get_avatar",
    }
    body = [
        (_("Date"), "attendance_date"),
        (_("Day"), "attendance_day"),
        (_("Check-In"), "attendance_clock_in"),
        (_("Check In Date"), "attendance_clock_in_date"),
        (_("Check-Out"), "attendance_clock_out"),
        (_("Check Out Date"), "attendance_clock_out_date"),
        (_("Shift"), "shift_id"),
        (_("Work Type"), "work_type_id"),
        (_("Min Hour"), "minimum_hour"),
        (_("At Work"), "attendance_worked_hour"),
        (_("Overtime"), "attendance_overtime"),
        (_("Activities"), "attendance_detail_activity_col", True),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class ValidateDetailView(GenericAttendancesDetailView):
    """
    detail view for validate tab
    """

    action_method = "validate_detail_actions"


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class OtDetailView(GenericAttendancesDetailView):
    """
    detail view for OT tab
    """

    action_method = "ot_detail_actions"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ordered_ids_key = "overtime_instance_ids"


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.view_attendance"), name="dispatch")
class ValidatedDetailView(GenericAttendancesDetailView):
    """
    detail view for validate tab
    """

    action_method = "validated_detail_actions"


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.add_attendance"), name="dispatch")
class AttendancesFormView(HorillaFormView):
    """
    form view
    """

    form_class = AttendanceForm
    model = Attendance
    new_display_title = _("Add Attendances")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.form = choosesubordinates(
            self.request, self.form, "attendance.add_attendance"
        )

        context["form"] = self.form
        context["view_id"] = "attendanceCreate"

        return context

    def form_valid(self, form: AttendanceForm) -> HttpResponse:
        if form.is_valid():
            message = _("Attendance Added")
            form.save()
            messages.success(self.request, message)
            return self.HttpResponse(
                script="if(typeof refreshAttendanceListContainer==='function'){refreshAttendanceListContainer();}"
            )
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(manager_can_enter("attendance.change_attendance"), name="dispatch")
class AttendanceUpdateFormView(HorillaFormView):
    """
    form for update
    """

    model = Attendance
    form_class = AttendanceUpdateForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Edit Attendance")

        context["view_id"] = "attendanceUpdate"

        return context

    def form_valid(self, form: AttendanceUpdateForm) -> HttpResponse:
        if form.is_valid():
            message = _("Attandance Updated")
            form.save()
            messages.success(self.request, message)
            return self.HttpResponse(
                script="if(typeof refreshAttendanceListContainer==='function'){refreshAttendanceListContainer();}"
            )
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class AttendanceDetailActivityList(AttendanceActivityListView):
    """
    List view for activity col in detail view
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.action_method = None
        resolved = resolve(self.request.path_info)
        kwargs = {
            "pk": resolved.kwargs.get("pk"),
        }
        self.search_url = reverse("get-attendance-activities", kwargs=kwargs)

    bulk_select_option = None
    row_attrs = ""

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = Attendance.find(self.kwargs.get("pk"))
        if not pk:
            return queryset.none()
        queryset = queryset.filter(
            attendance_date=pk.attendance_date, employee_id=pk.employee_id
        )

        return queryset


@method_decorator(login_required, name="dispatch")
class PenaltyAccountListView(HorillaListView):
    """
    list view for penalty tab
    """

    filter_class = PenaltyFilter
    model = PenaltyAccounts
    columns = [
        (_("Leave Type"), "leave_type_id"),
        (_("Minus Days"), "minus_leaves"),
        (_("Deducted From CFD"), "get_deduct_from_carry_forward"),
        (_("Penalty amount"), "penalty_amount"),
        (_("Created Date"), "created_at"),
        (_("Penalty Type"), "penalty_type_col"),
    ]

    confirm_text = _("Are you sure you want to delete this penalty?")
    actions = [
        {
            "action": _("Delete"),
            "icon": "trash-outline",
            "attrs": f"""
                        class="oh-btn oh-btn--danger oh-btn--sq-sm"
                        hx-confirm="{confirm_text}"
                        hx-post="{{get_delete_url}}"
                        hx-target="#penaltyTr{{get_delete_instance}}"
                        hx-swap="delete"
                      """,
        }
    ]

    row_attrs = """
                id = "penaltyTr{get_delete_instance}"
                """

    header_attrs = {
        "action": """ style="width:180px !important" """,
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse("individual-panalty-list-view", kwargs={"pk": pk})

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        queryset = queryset.filter(employee_id=pk)
        return queryset


@method_decorator(login_required, name="dispatch")
class ValidateAttendancesIndividualTabView(AttendancesListView):
    """
    list view for validate attendance tab view
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        queryset = self.model.objects.filter(
            employee_id=pk,
            attendance_validated=False,
        )
        queryset = (
            filtersubordinates(self.request, queryset, "attendance.view_attendance")
            | queryset
        )
        return queryset

    selected_instances_key_id = "validateselectedInstances"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        pk = self.request.resolver_match.kwargs.get("pk")
        self.search_url = reverse(
            "validate-attendance-individual-tab", kwargs={"pk": pk}
        )
        if self.request.user.has_perm(
            "attendance.change_attendance"
        ) or is_reportingmanager(self.request):
            self.action_method = "validate_button"
            self.option_method = None
        self.view_id = "validate-container"

    row_attrs = """
                hx-get='{individual_validate_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


@method_decorator(login_required, name="dispatch")
class ValidateAttendancesIndividualDetailView(GenericAttendancesDetailView):
    """
    Validate tab detail view in single view of employee
    """

    action_method = "validate_detail_actions"

    def get_queryset(self):
        queryset = super().get_queryset()
        pk = self.kwargs.get("pk")
        obj = queryset.get(pk=pk)
        employee_id = obj.employee_id
        if is_reportingmanager(self.request):
            queryset = filtersubordinates(
                self.request, queryset, "attendance.view_attendance"
            ) | queryset.filter(employee_id=self.request.user.employee_get)
        elif self.request.user.has_perm("attendance.view_attendance"):
            queryset = queryset.filter(employee_id=employee_id)
        else:
            queryset = queryset.filter(employee_id=self.request.user.employee_get)
        return queryset

    @method_decorator(login_required, name="dispatch")
    def dispatch(self, *args, **kwargs):
        return super(GenericAttendancesDetailView, self).dispatch(*args, **kwargs)


EmployeeProfileView.add_tab(
    tabs=[
        {
            "title": _("Attendance"),
            # "view": views.attendance_tab,
            "view": AttendanceTabView.as_view(),
            "accessibility": "attendance.cbv.accessibility.attendance_accessibility",
        },
        {
            "title": _("Penalty Account"),
            "view": PenaltyAccountListView.as_view(),
            "accessibility": "attendance.cbv.accessibility.penalty_accessibility",
        },
    ]
)


def get_working_today(queryset, _name, value):
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    working_employees = Attendance.objects.filter(
        attendance_date__gte=yesterday,
        attendance_date__lte=today,
        attendance_clock_out_date__isnull=True,
    ).values_list("employee_id", flat=True)

    if value:
        queryset = queryset.filter(id__in=working_employees)
    else:
        queryset = queryset.exclude(id__in=working_employees)
    return queryset


og_init = EmployeeFilter.__init__


def online_init(self, *args, **kwargs):
    og_init(self, *args, **kwargs)
    custom_field = django_filters.BooleanFilter(
        label="Working", method=get_working_today
    )
    self.filters["working_today"] = custom_field
    self.form.fields["working_today"] = custom_field.field
    self.form.fields["working_today"].widget.attrs.update(
        {
            "class": "oh-select oh-select-2 w-100",
        }
    )


status_indications = [
    (
        "offline--dot",
        _("Offline"),
        """
            onclick="
                $('#applyFilter').closest('form').find('[name=working_today]').val('false');
                $('#applyFilter').click();
            "
            """,
    ),
    (
        "online--dot",
        _("Online"),
        """
            onclick="$('#applyFilter').closest('form').find('[name=working_today]').val('true');
                $('#applyFilter').click();
            "
            """,
    ),
]


def offline_online(self):
    """
    This method for get custome coloumn for rating.
    """

    return render_template(
        path="cbv/employees_view/offline_online.html",
        context={"instance": self},
    )


EmployeeFilter.__init__ = online_init
EmployeeNav.filter_instance = EmployeeFilter()
EmployeeCard.card_status_indications = status_indications
EmployeesList.row_status_indications = status_indications
Employee.offline_online = offline_online

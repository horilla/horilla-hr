"""
Attendance requests
"""

import json
from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from attendance.cbv.tab_shell import AttendanceTabContentShell
from attendance.filters import AttendanceFilters
from attendance.forms import (
    AttendanceRequestForm,
    BulkAttendanceRequestForm,
    NewRequestForm,
)
from attendance.methods.utils import get_employee_last_name
from attendance.models import Attendance
from base.methods import (
    choosesubordinates,
    filtersubordinates,
    has_export_access,
    is_reportingmanager,
)
from employee.models import Employee
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
)
from notifications.signals import notify


@method_decorator(login_required, name="dispatch")
class AttendancesRequestView(TemplateView):
    """
    for attendance request page
    """

    template_name = "cbv/attendance_request/attendance_request.html"


@method_decorator(login_required, name="dispatch")
class AttendancesRequestTabView(HorillaTabView):
    """
    tabview of attendance request page
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "attendance-container"
        self.tabs = [
            {
                "title": _("Requested Attendances"),
                "url": f"{reverse('requested-attendance-tab-shell')}",
            },
            {
                "title": _("All Attendances"),
                "url": f"{reverse('all-attendance-tab-shell')}",
            },
        ]

    def get_context_data(self, **kwargs: Any):
        """Tab badges: counts match each tab list before HTMX loads the pane."""
        context = super().get_context_data(**kwargs)
        counts = attendance_request_tabs_badge_counts(self.request)
        for idx, tab in enumerate(self.tabs):
            tab["badge"] = counts[idx] if idx < len(counts) else 0
        return context


def request_approved_by(self):
    """
    Approve the attendance request
    """
    return self.approved_by if self.approved_by else "-"


Attendance.request_approved_by = request_approved_by


@method_decorator(login_required, name="dispatch")
class AttendancesRequestListView(HorillaListView):
    """
    list view
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("attendance-list-tab")

    filter_class = AttendanceFilters
    model = Attendance
    quick_export = False
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
        (_("Overtime"), "attendance_overtime"),
        (_("Approved By"), "request_approved_by"),
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
        (_("In Date"), "attendance_clock_in_date"),
        (_("Out Date"), "attendance_clock_out_date"),
        (_("At Work"), "attendance_worked_hour"),
        (_("Overtime"), "attendance_overtime"),
    ]
    # [name=attendance_validated] is now the Any/Yes/No segmented radio
    # group (AttendanceFilters.attendance_validated -- see the modern
    # filter panel work), whose rendered radio values are ""/"True"/
    # "False" (Python's str(True)/str(False) for the ("", "Any"),
    # (True, "Yes"), (False, "No") choices), not NullBooleanSelect's own
    # "unknown"/"true"/"false" -- these .val(...) calls need to match
    # whichever encoding [name=is_bulk_request] still uses (unchanged, so
    # still lowercase).
    row_status_indications = [
        (
            "bulk-request--dot",
            _("Bulk-Requests"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=is_bulk_request]').val('true');
                $('[name=attendance_validated]').val('').change();
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "not-validated--dot",
            _("Not Validated"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=attendance_validated]').val('False');
                $('[name=is_bulk_request]').val('unknown').change();
                $('#applyFilter').click();
            "
            """,
        ),
        (
            "validated--dot",
            _("Validated"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=attendance_validated]').val('True');
                $('[name=is_bulk_request]').val('unknown').change();
                $('#applyFilter').click();

            "
            """,
        ),
    ]

    row_status_class = "validated-{attendance_validated}"
    # Mirrors _AttendanceRequestTabNavBase.nested_group_by_fields -- needed
    # here too since this (List) and Nav are separate classes; see the same
    # split in employee/cbv/employees.py's EmployeesList/EmployeeNav.
    nested_group_by_fields = [
        ("employee_id", _("Employee")),
        ("attendance_date", _("Attendance Date")),
        ("attendance_clock_in_date", _("In Date")),
        ("attendance_clock_out_date", _("Out Date")),
        ("employee_id__country", _("Country")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("shift_id", _("Shift")),
        ("work_type_id", _("Work Type")),
        ("minimum_hour", _("Min Hour")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employement Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
class AttendanceRequestListTab(AttendancesRequestListView):
    """
    Attendance request tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "attendance-requests-container"
        self.search_url = reverse("attendance-request-list-tab")

    template_name = "cbv/attendance_request/attendance_request_tab.html"

    columns = [
        col for col in AttendancesRequestListView.columns if col[1] != "status_col"
    ]
    action_method = "request_actions"
    row_attrs = """
                id = "requestedattendanceTr{get_instance_id}"
                data-attendance-id="{get_instance_id}"
                data-toggle="oh-modal-toggle"
                data-target="#validateAttendanceRequest"
                hx-get = "{detail_view}?instance_ids={ordered_ids}"
                hx-trigger ="click"
                hx-target="#validateAttendanceRequestModalBody"
                """

    def get_queryset(self):
        queryset = super().get_queryset()
        self_data = queryset
        queryset = queryset.filter(
            is_validate_request=True,
        )
        queryset = filtersubordinates(
            request=self.request,
            perm="attendance.view_attendance",
            queryset=queryset,
        )
        queryset = queryset | self_data.filter(
            employee_id__employee_user_id=self.request.user,
            is_validate_request=True,
        )
        return queryset


def change_accessibility(request, instance: object = None, *args, **kwargs) -> bool:

    if (
        request.user.has_perm("attendance.change_attendance")
        or is_reportingmanager(request)
        or request.user == instance.employee_id.employee_user_id
    ):
        return True
    else:
        return False


@method_decorator(login_required, name="dispatch")
class AttendanceListTab(AttendancesRequestListView):
    """
    Attendance tab
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        data = queryset
        attendances = filtersubordinates(
            request=self.request,
            perm="attendance.view_attendance",
            queryset=queryset,
        )
        queryset = attendances | data.filter(
            employee_id__employee_user_id=self.request.user
        )
        queryset = queryset.filter(
            employee_id__is_active=True,
        )
        return queryset

    actions = [
        {
            "action": _("Edit"),
            "icon": "create-outline",
            "accessibility": "attendance.cbv.attendance_request.change_accessibility",
            "attrs": """
                class="oh-btn oh-btn--light-bkg oh-btn--sq-sm"
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-get="{change_attendance}"
                hx-target="#genericModalBody"

                """,
        }
    ]

    header_attrs = {
        # Wide enough for the "Actions" label plus the column-toggle dropdown
        # button that now renders inside this header cell.
        "action": """ style="width:120px !important" """,
    }

    row_attrs = """
                {diff_cell}
                id = "allattendanceTr{get_instance_id}"
                hx-get='{attendance_detail_view}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                hx-trigger ="click"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """


def _request_tab_badge_count(request, view_cls):
    """Same queryset rules as the tab's HorillaListView (filters, subordinates)."""
    view = view_cls()
    view.request = request
    view.args = ()
    view.kwargs = {}
    view.queryset = None
    return view.get_queryset().count()


def attendance_request_tabs_badge_counts(request):
    """
    Order matches AttendancesRequestTabView.tabs: requested, all attendances.
    """
    return [
        _request_tab_badge_count(request, AttendanceRequestListTab),
        _request_tab_badge_count(request, AttendanceListTab),
    ]


def _attendance_request_common_actions(request):
    """
    Export - duplicated into every Attendance Requests tab's own Nav now
    that each tab carries its own independent Search/Filter/Actions bar
    instead of one bar shared above both (matches Employee Configuration,
    where every settings tab loads its own Nav rather than sharing one).
    """
    actions = []
    if has_export_access(request, Attendance):
        actions.append(
            {
                "action": _("Export"),
                "attrs": f"""
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
                hx-get="{reverse('attendences-navbar-export')}"
                hx-vals='js:{{"has_selection": (function(){{var t=document.querySelector(".oh-tabs__content--active");var l=(t||document).querySelector("[data-selected-instances-key]");var k=(l&&l.getAttribute("data-selected-instances-key"))||"selectedInstances";var el=document.getElementById(k);return JSON.parse((el&&el.getAttribute("data-ids"))||"[]").length>0;}})()}}'
                style="cursor: pointer;"
            """,
            }
        )
    return actions


class _AttendanceRequestTabNavBase(HorillaNavView):
    """
    Shared Search/Filter/Create wiring for each Attendance Requests tab's
    own, independent Nav - only search_url/search_swap_target/actions
    differ per tab.
    """

    nav_title = _("Attendances")
    filter_body_template = "cbv/attendances/attendances_filter_page.html"
    filter_instance = AttendanceFilters()
    filter_form_context_name = "form"
    # This shares attendances_filter_page.html with AttendancesNavView,
    # which is now built for the modern slide-over panel (accordions,
    # segmented toggles, AJAX combos) -- without this flag it would still
    # render that same content, just unstyled/half-broken, since those
    # rules are scoped under .oh-filter-modern.
    modern_filter = True

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("attendance_date", _("Attendance Date")),
        ("attendance_clock_in_date", _("In Date")),
        ("attendance_clock_out_date", _("Out Date")),
        ("employee_id__country", _("Country")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("shift_id", _("Shift")),
        ("work_type_id", _("Work Type")),
        ("minimum_hour", _("Min Hour")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employement Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]
    # Mirrors AttendancesRequestListView.nested_group_by_fields below --
    # List and Nav are separate classes/templates (see
    # employee/cbv/employees.py's EmployeesList/EmployeeNav for the same
    # split), so the inline "add/change field" dropdowns in the "Grouped
    # by" breadcrumb (nested_group_by_table.html, rendered by the List
    # view) need this here too, not just the currently-active fields it
    # already had access to via nested_fields_active.
    nested_group_by_fields = group_by_fields

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.create_attrs = f"""
                        data-toggle="oh-modal-toggle"
                        data-target="#genericModal"
                        hx-get="{reverse('request-new-attendance')}"
                        hx-target="#genericModalBody"
                        """


@method_decorator(login_required, name="dispatch")
class RequestedAttendanceNav(_AttendanceRequestTabNavBase):
    """
    Independent Nav for the Requested Attendances tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("attendance-request-list-tab")
        self.search_swap_target = "#requestedAttendanceListContainer"
        self.actions = _attendance_request_common_actions(self.request)
        if self.request.user.has_perm(
            "attendance.add_attendanceovertime"
        ) or is_reportingmanager(self.request):
            self.actions += [
                {
                    "action": _("Bulk Approve"),
                    "attrs": """
                        onclick="
                        reqAttendanceBulkApprove();
                        "
                        style="cursor: pointer;"
                    """,
                },
                {
                    "action": _("Bulk Reject"),
                    "attrs": """
                        onclick="reqAttendanceBulkReject();"
                        style="color:red !important"
                    """,
                },
            ]


@method_decorator(login_required, name="dispatch")
class AllAttendanceRequestNav(_AttendanceRequestTabNavBase):
    """
    Independent Nav for the All Attendances tab.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("attendance-list-tab")
        self.search_swap_target = "#allAttendanceListContainer"
        self.actions = _attendance_request_common_actions(self.request)


class RequestedAttendanceTabShell(AttendanceTabContentShell):
    nav_url_name = "requested-attendance-nav"
    container_id = "requestedAttendanceListContainer"
    tabs_root_id = "attendance-container"


class AllAttendanceTabShell(AttendanceTabContentShell):
    nav_url_name = "all-attendance-request-nav"
    container_id = "allAttendanceListContainer"
    tabs_root_id = "attendance-container"


@method_decorator(login_required, name="dispatch")
class AttendanceListTabDetailView(HorillaDetailedView):
    """
    Detail view of page
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
        (_("Approved By"), "request_approved_by"),
        (_("Activities"), "attendance_detail_activity_col", True),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # detail_actions.html carries the same accessibility rule as the
        # row's Edit action (AttendanceListTab.actions), restyled to the
        # modal's labeled pill-button convention.
        self.action_method = "detail_actions"


@method_decorator(login_required, name="dispatch")
class NewAttendanceRequestFormView(HorillaFormView):
    """
    form view for create  attendance request
    """

    form_class = NewRequestForm
    model = Attendance
    new_display_title = _("New Attendance Request")
    template_name = "requests/attendance/request_form.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "attendanceRequest"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.form = choosesubordinates(
            self.request, self.form, "attendance.change_attendance"
        )
        self.form.fields["employee_id"].queryset = (
            self.form.fields["employee_id"].queryset
        ).distinct() | (
            Employee.objects.filter(employee_user_id=self.request.user)
        ).distinct()
        self.form.fields["employee_id"].initial = self.request.user.employee_get.id
        if self.request.GET.get("emp_id"):
            emp_id = self.request.GET.get("emp_id")
            self.form.fields["employee_id"].queryset = Employee.objects.filter(
                id=emp_id
            )
            self.form.fields["employee_id"].initial = emp_id
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Attendance Request")
        return context

    def form_valid(self, form: NewRequestForm) -> HttpResponse:
        if form.is_valid():
            message = _("New Attendance request created")
            if form.new_instance is not None:
                form.new_instance.save()
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class BulkAttendanceRequestFormView(HorillaFormView):
    """
    form view for create bulk  attendance request
    """

    form_class = BulkAttendanceRequestForm
    model = Attendance
    new_display_title = _("New Attendance Request")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.form = choosesubordinates(
            self.request, self.form, "attendance.change_attendance"
        )
        self.form.fields["employee_id"].queryset = self.form.fields[
            "employee_id"
        ].queryset | Employee.objects.filter(employee_user_id=self.request.user)
        self.form.fields["employee_id"].initial = self.request.user.employee_get.id
        return context

    def post(self, request, *args, pk=None, **kwargs):
        self.get_form()
        form = self.form
        form.instance.attendance_clock_in_date = self.request.POST.get("from_date")
        form.instance.attendance_date = self.request.POST.get("from_date")
        if form.is_valid():
            if form.instance.pk:
                message = _("New Attendance request updated")
            else:
                message = _("New Attendance request created")
                instance = form.save(commit=False)
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().post(request, *args, pk=pk, **kwargs)

    def form_valid(self, form: BulkAttendanceRequestForm) -> HttpResponse:
        form.instance.attendance_clock_in_date = self.request.POST.get("from_date")
        form.instance.attendance_date = self.request.POST.get("from_date")
        if form.is_valid():
            if form.instance.pk:
                message = _("New Attendance request updated")
            else:
                message = _("New Attendance request created")
                instance = form.save(commit=False)
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
class UpdateAttendanceRequestFormView(HorillaFormView):
    """
    form view for update attendance request
    """

    form_class = AttendanceRequestForm
    model = Attendance

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "attendanceRequest"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Update Attendance Request")
        return context

    def form_valid(self, form: AttendanceRequestForm) -> HttpResponse:
        if form.is_valid():
            attendance = Attendance.objects.get(id=self.form.instance.pk)
            instance = form.save()
            instance.employee_id = attendance.employee_id
            instance.id = attendance.id
            if attendance.request_type != "create_request":
                attendance.requested_data = json.dumps(instance.serialize())
                attendance.request_description = instance.request_description
                # set the user level validation here
                attendance.is_validate_request = True
                attendance.save()
            else:
                instance.is_validate_request_approved = False
                instance.is_validate_request = True
                instance.save()
            messages.success(self.request, _("Attendance update request created."))
            employee = attendance.employee_id
            if attendance.employee_id.employee_work_info.reporting_manager_id:
                reporting_manager = (
                    attendance.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                )
                user_last_name = get_employee_last_name(attendance)
                notify.send(
                    self.request.user,
                    recipient=reporting_manager,
                    verb=f"{employee.employee_first_name} {user_last_name}'s\
                          attendance update request for {attendance.attendance_date} is created",
                    verb_ar=f"تم إنشاء طلب تحديث الحضور لـ {employee.employee_first_name} \
                        {user_last_name }في {attendance.attendance_date}",
                    verb_de=f"Die Anfrage zur Aktualisierung der Anwesenheit von \
                        {employee.employee_first_name} {user_last_name} \
                            für den {attendance.attendance_date} wurde erstellt",
                    verb_es=f"Se ha creado la solicitud de actualización de asistencia para {employee.employee_first_name}\
                          {user_last_name} el {attendance.attendance_date}",
                    verb_fr=f"La demande de mise à jour de présence de {employee.employee_first_name}\
                          {user_last_name} pour le {attendance.attendance_date} a été créée",
                    redirect=reverse("request-attendance-view")
                    + f"?id={attendance.id}",
                    icon="checkmark-circle-outline",
                )
            detail_view = self.request.GET.get("detail_view")
            all_attendance = self.request.GET.get("all_attendance")
            if detail_view == "true":
                return HttpResponse(
                    f"""<script>
                                            var reqModal = $('#requestedattendanceTr{form.instance.pk}');
                                            reqModal[0].click();
                                            $('#genericModalEdit').removeClass('oh-modal--show');
                                            $('.reload-record').click();
                                            $('#reloadMessagesButton').click();
                                        </script>
                                    """
                )
            elif all_attendance == "true":
                return HttpResponse(
                    f"""<script>
                                            var attendaceModal = $('#allattendanceTr{form.instance.pk}');
                                            attendaceModal[0].click();
                                            $('#genericModalEdit').removeClass('oh-modal--show');
                                            $('.reload-record').click();
                                            $('#reloadMessagesButton').click();
                                        </script>
                                    """
                )

            return self.HttpResponse()
        return super().form_valid(form)

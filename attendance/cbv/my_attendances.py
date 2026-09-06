"""
My attendances
"""

from typing import Any

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from attendance.filters import AttendanceFilters
from attendance.models import Attendance
from horilla_views.cbv_methods import login_required
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)


@method_decorator(login_required, name="dispatch")
class MyAttendances(TemplateView):
    """
    My attendances
    """

    template_name = "cbv/my_attendances/my_attendances.html"


class MyAttendancesListView(HorillaListView):

    model = Attendance
    filter_class = AttendanceFilters
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

    row_attrs = """
                hx-get='{my_attendance_detail}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """

    sortby_mapping = [
        (_("Employee"), "employee_id__get_full_name", "employee_id__get_avatar"),
        (_("Date"), "attendance_date"),
        (_("Day"), "attendance_day__day"),
        (_("Check-In"), "attendance_clock_in"),
        (_("Shift"), "shift_id__employee_shift"),
        (_("Work Type"), "work_type_id__work_type"),
        (_("Min Hour"), "minimum_hour"),
        (_("Pending Hour"), "hours_pending"),
        (_("In Date"), "attendance_clock_in_date"),
        (_("Check-Out"), "attendance_clock_out"),
        (_("Out Date"), "attendance_clock_out_date"),
        (_("At Work"), "attendance_worked_hour"),
        (_("Overtime"), "attendance_overtime"),
    ]


@method_decorator(login_required, name="dispatch")
class MyAttendanceList(MyAttendancesListView):
    """
    List view
    """

    # Mirrors MyAttendancestNav.nested_group_by_fields -- needed here too
    # since this (List) and Nav are separate classes; see the same split
    # in employee/cbv/employees.py's EmployeesList/EmployeeNav. No
    # Employee/Reporting Manager/Department/Company/... fields, unlike
    # AttendancesNavView's own list -- this page is self-scoped to the
    # current user (get_queryset() below filters to employee_id=self), so
    # every record already shares the same employee and org structure.
    nested_group_by_fields = [
        ("attendance_date", _("Attendance Date")),
        ("attendance_day", _("Attendance Day")),
        ("shift_id", _("Shift")),
        ("work_type_id", _("Work Type")),
        ("minimum_hour", _("Min Hour")),
        ("attendance_validated", _("Validated")),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("my-attendance-list")

    # attendance_validated/is_validate_request/is_validate_request_approved
    # are all now Any/Yes/No segmented radio groups (AttendanceFilters --
    # see the modern filter panel work), whose rendered radio values are
    # ""/"True"/"False" (Python's str(True)/str(False) for the
    # ("", "Any"), (True, "Yes"), (False, "No") choices) -- not
    # NullBooleanSelect's own "unknown"/"true"/"false" these onclick
    # handlers originally targeted.
    row_status_indications = [
        (
            "approved-request--dot",
            _("Approved Request"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=is_validate_request_approved]').val('True');
                $('[name=attendance_validated]').val('').change();
                $('[name=is_validate_request]').val('').change();
                $('#applyFilter').click();

            "
            """,
        ),
        (
            "requested--dot",
            _("Requested"),
            """
            onclick="
                $('#applyFilter').closest('form').find('[name=is_validate_request]').val('True');
                $('[name=attendance_validated]').val('').change();
                $('[name=is_validate_request_approved]').val('').change();
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
                $('[name=is_validate_request]').val('').change();
                $('[name=is_validate_request_approved]').val('').change();
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
                $('[name=is_validate_request]').val('').change();
                $('[name=is_validate_request_approved]').val('').change();
                $('#applyFilter').click();

            "
            """,
        ),
    ]

    row_status_class = "validated-{attendance_validated}  requested-{is_validate_request} approved-request-{is_validate_request_approved}"

    def get_queryset(self):
        queryset = super().get_queryset()
        employee = self.request.user.employee_get
        queryset = queryset.filter(employee_id=employee)
        return queryset


@method_decorator(login_required, name="dispatch")
class MyAttendancestNav(HorillaNavView):
    """
    Nav bar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("my-attendance-list")
        self.search_in = [
            ("shift_id__employee_shift", "Shift"),
            ("work_type_id__work_type", "Work Type"),
        ]

    nav_title = _("My Attendances")
    filter_body_template = "cbv/my_attendances/my_attendance_filter.html"
    filter_instance = AttendanceFilters()
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"
    search_input_attrs = """ hidden """
    # Opts into the same modern slide-over filter panel built for
    # Employee/Attendance (horilla_nav.html's .oh-filter-modern styles).
    modern_filter = True

    # Mirrors MyAttendanceList.nested_group_by_fields above -- List and Nav
    # are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split), so the "Group By"
    # section rendered inside this page's own filter panel
    # (horilla_nav.html) needs this here too, not just the List view.
    nested_group_by_fields = [
        ("attendance_date", _("Attendance Date")),
        ("attendance_day", _("Attendance Day")),
        ("shift_id", _("Shift")),
        ("work_type_id", _("Work Type")),
        ("minimum_hour", _("Min Hour")),
        ("attendance_validated", _("Validated")),
    ]


@method_decorator(login_required, name="dispatch")
class MyAttendancesDetailView(HorillaDetailedView):
    """
    Detail View
    """

    model = Attendance

    title = _("Details")

    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "my_attendance_subtitle",
        "avatar": "employee_id__get_avatar",
    }

    body = [
        (_("Date"), "attendance_date"),
        (_("Day"), "attendance_day"),
        (_("Check-In"), "attendance_clock_in"),
        (_("Check-in Date"), "attendance_clock_in_date"),
        (_("Check-Out"), "attendance_clock_out"),
        (_("Check-out Date"), "attendance_clock_out_date"),
        (_("Shift"), "shift_id"),
        (_("Work Type"), "work_type_id"),
        (_("Min Hour"), "minimum_hour"),
        (_("At Work"), "attendance_worked_hour"),
        (_("Pending Hour"), "hours_pending"),
        (_("Overtime"), "attendance_overtime"),
    ]

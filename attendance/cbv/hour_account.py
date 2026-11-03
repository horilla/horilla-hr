"""
Hour account page
"""

from typing import Any

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from attendance.filters import AttendanceOverTimeFilter
from attendance.forms import AttendanceOverTimeExportForm, AttendanceOverTimeForm
from attendance.models import AttendanceOverTime
from base.decorators import manager_can_enter
from base.methods import (
    choosesubordinates,
    filtersubordinates,
    has_export_access,
    is_reportingmanager,
)
from horilla_views.cbv_methods import (
    EmployeeScopeMixin,
    hx_request_required,
    login_required,
)
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)


@method_decorator(login_required, name="dispatch")
class HourAccount(TemplateView):
    """
    Hours Balance
    """

    template_name = "cbv/hour_account/hour_account.html"


@method_decorator(login_required, name="dispatch")
class HourAccountList(HorillaListView):
    """
    List view
    """

    model = AttendanceOverTime
    filter_class = AttendanceOverTimeFilter
    action_method = "hour_actions"
    quick_export = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("attendance-ot-search")
        self.view_id = "ot-table"

        if self.request.user.has_perm("attendance.add_attendanceovertime"):
            self.action_method = "hour_actions"

    def get_queryset(self):
        queryset = super().get_queryset()
        data = queryset
        queryset = queryset.filter(employee_id__employee_user_id=self.request.user)
        accounts = filtersubordinates(
            self.request, data, "attendance.view_attendanceovertime"
        )
        return queryset | accounts

    columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Month"), "get_month_capitalized"),
        (_("Year"), "year"),
        (_("Worked Hours"), "worked_hours"),
        (_("Hours to Validate"), "not_validated_hrs"),
        (_("Pending Hours"), "pending_hours"),
        (_("Overtime Hours"), "overtime"),
        (_("Not Approved OT Hours"), "not_approved_ot_hrs"),
    ]

    default_columns = [
        (_("Employee"), "employee_id", "employee_id__get_avatar"),
        (_("Worked Hours"), "worked_hours"),
        (_("Hours to Validate"), "not_validated_hrs"),
        (_("Pending Hours"), "pending_hours"),
        (_("Overtime Hours"), "overtime"),
        (_("Not Approved OT Hours"), "not_approved_ot_hrs"),
    ]

    header_attrs = {
        "employee_id": """
                      style='width:200px !important'
                      """,
        "not_approved_ot_hrs": """
                      style='width:180px !important'
                      """,
        "action": """
                   style="width:160px !important"
                   """,
    }

    row_attrs = """
                hx-get='{hour_account_detail}?instance_ids={ordered_ids}'
                hx-target="#genericModalBody"
                data-target="#genericModal"
                data-toggle="oh-modal-toggle"
                """
    sortby_mapping = [
        ("Employee", "employee_id__get_full_name", "employee_id__get_avatar"),
        ("Month", "get_month_capitalized"),
        ("Year", "year"),
        ("Worked Hours", "worked_hours"),
        ("Overtime Hours", "overtime"),
    ]


@method_decorator(login_required, name="dispatch")
class HourAccountNav(HorillaNavView):
    """
    Nav bar
    """

    template_name = "cbv/hour_account/nav_hour_account.html"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("attendance-ot-search")
        if not self.request.user.has_perm(
            "attendance.add_attendanceovertime"
        ) and not is_reportingmanager(self.request):
            self.create_attrs = None
        else:
            self.create_attrs = f"""
                data-toggle="oh-modal-toggle"
                data-target="#genericModal"
                hx-target="#genericModalBody"
                hx-get="{reverse_lazy('attendance-overtime-create')}"
            """
        actions = []
        if has_export_access(self.request, AttendanceOverTime):
            actions.append(
                {
                    "action": _("Export"),
                    "attrs": f"""
                data-toggle="oh-modal-toggle"
                data-target="#hourAccountExport"
                hx-get="{reverse('hour-account-export')}"
                hx-target="#hourAccountExportModalBody"
                style="cursor: pointer;"
                """,
                }
            )

        if self.request.user.has_perm("attendance.add_attendanceovertime"):
            actions.append(
                {
                    "action": _("Delete"),
                    "attrs": """
                    onclick="
                    hourAccountbulkDelete();
                    "
                    data-action = "delete"
                    style="cursor: pointer; color:red !important"
                    """,
                },
            )

        self.actions = actions or None

    nav_title = _("Hours Balance")
    filter_instance = AttendanceOverTimeFilter()
    filter_body_template = "cbv/hour_account/hour_filter.html"
    filter_form_context_name = "form"
    search_swap_target = "#listContainer"

    group_by_fields = [
        ("employee_id", _("Employee")),
        ("month", _("Month")),
        ("year", _("Year")),
        ("employee_id__country", _("Country")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__shift_id", _("Shift")),
        ("employee_id__employee_work_info__work_type_id", _("Work Type")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employment Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
class HourExportView(TemplateView):
    """
    For candidate export
    """

    template_name = "cbv/hour_account/hour_export.html"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        attendances = AttendanceOverTime.objects.all()
        export_fields = AttendanceOverTimeExportForm
        export_obj = AttendanceOverTimeFilter(queryset=attendances)
        context["export_fields"] = export_fields
        context["export_obj"] = export_obj
        return context


@method_decorator(login_required, name="dispatch")
class HourAccountDetailView(HorillaDetailedView):
    """
    Detail View
    """

    model = AttendanceOverTime
    title = _("Details")

    header = {
        "title": "employee_id__get_full_name",
        "subtitle": "hour_account_subtitle",
        "avatar": "employee_id__get_avatar",
    }

    body = [
        (_("Month"), "get_month_capitalized"),
        (_("Year"), "year"),
        (_("Worked Hours"), "worked_hours"),
        (_("Pending Hours"), "pending_hours"),
        (_("Over time"), "overtime"),
    ]

    action_method = "hour_detail_actions"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    manager_can_enter("attendance.add_attendanceovertime"), name="dispatch"
)
class HourAccountFormView(EmployeeScopeMixin, HorillaFormView):
    """
    Form View
    """

    scope_perm = "attendance.add_attendanceovertime"
    scope_include_self = False

    model = AttendanceOverTime
    form_class = AttendanceOverTimeForm
    # template_name = "cbv/recruitment/forms/create_form.html"
    new_display_title = _("Hours Balance")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.form_class(initial={"employee_id": self.request.user.employee_get})
        if self.form.instance.pk:
            self.form_class.verbose_name = _("Hour account update")
            self.form_class(instance=self.form.instance)
        self.form = choosesubordinates(
            self.request, self.form, "attendance.add_attendanceovertime"
        )
        context["form"] = self.form
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        # form = self.form_class(self.request.POST)
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: AttendanceOverTimeForm) -> HttpResponse:
        if form.is_valid():
            if form.instance.pk:
                message = _("Attendance account updated")
            else:
                message = _("Attendance account added")
            form.save()
            messages.success(self.request, _(message))
            return self.HttpResponse()
        return super().form_valid(form)

"""
views.py

This module contains the view functions for handling HTTP requests and rendering
responses in your application.

Each view function corresponds to a specific URL route and performs the necessary
actions to handle the request, process data, and generate a response.

This module is part of the recruitment project and is intended to
provide the main entry points for interacting with the application's functionality.
"""

import logging
import uuid

from horilla.http.response import HorillaRedirect
from horilla.methods import remove_dynamic_url

logger = logging.getLogger(__name__)

import calendar
import contextlib
import io
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.validators import validate_ipv46_address
from django.db import transaction
from django.db.models import ProtectedError
from django.forms import ValidationError
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone as django_timezone
from django.utils.timezone import now
from django.utils.translation import gettext as __
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from PIL import Image
from xlsxwriter.utility import xl_range

from attendance.filters import (
    AttendanceActivityFilter,
    AttendanceActivityReGroup,
    AttendanceFilters,
    AttendanceOverTimeFilter,
    AttendanceOvertimeReGroup,
    AttendanceReGroup,
    LateComeEarlyOutFilter,
    LateComeEarlyOutReGroup,
)
from attendance.forms import (
    AttendanceActivityExportForm,
    AttendanceExportForm,
    AttendanceForm,
    AttendanceOverTimeExportForm,
    AttendanceOverTimeForm,
    AttendanceRequestCommentForm,
    AttendanceUpdateForm,
    AttendanceValidationConditionForm,
    GraceTimeAssignForm,
    GraceTimeForm,
    LateComeEarlyOutExportForm,
    NewRequestForm,
)
from attendance.methods.utils import (
    Request,
    attendance_day_checking,
    format_time,
    is_reportingmanger,
    monthly_leave_days,
    paginator_qry,
    parse_date,
    parse_datetime,
    parse_time,
    sort_activity_dicts,
    strtime_seconds,
)
from attendance.models import (
    Attendance,
    AttendanceActivity,
    AttendanceGeneralSetting,
    AttendanceLateComeEarlyOut,
    AttendanceOverTime,
    AttendanceRequestComment,
    AttendanceRequestFile,
    AttendanceValidationCondition,
    BatchAttendance,
    GraceTime,
    WorkRecords,
)
from attendance.views.handle_attendance_errors import handle_attendance_errors
from attendance.views.process_attendance_data import process_attendance_data
from base.forms import AttendanceAllowedIPForm, TrackLateComeEarlyOutForm
from base.methods import (
    choosesubordinates,
    closest_numbers,
    eval_validate,
    export_data,
    filtersubordinates,
    filtersubordinatesemployeemodel,
    get_key_instances,
    get_pagination,
    get_session_company,
)
from base.models import (
    AttendanceAllowedIP,
    EmployeeShiftSchedule,
    Holidays,
    TrackLateComeEarlyOut,
    WorkType,
)
from employee.filters import EmployeeFilter
from employee.models import Employee, EmployeeWorkInformation
from horilla.decorators import (
    hx_request_required,
    install_required,
    login_required,
    manager_can_enter,
    permission_required,
)
from notifications.signals import notify


def attendance_validate(attendance):
    """
    This method is is used to check condition for at work in AttendanceValidationCondition
    model instance it return true if at work is smaller than condition
    args:
        attendance : attendance object
    """

    conditions = AttendanceValidationCondition.objects.all()
    # Set the default condition for 'at work' to 9:00 AM
    condition_for_at_work = strtime_seconds("09:00")
    if conditions.exists():
        condition_for_at_work = strtime_seconds(conditions[0].validation_at_work)
    at_work = strtime_seconds(attendance.attendance_worked_hour)
    return condition_for_at_work >= at_work


@login_required
@hx_request_required
def profile_attendance_tab(request):
    """
    This function is used to view attendance tab of an employee in profile view.

    Parameters:
    request (HttpRequest): The HTTP request object.
    emp_id (int): The id of the employee.

    Returns: return asset-request-tab template

    """
    user = request.user
    employee = user.employee_get
    employee_attendances = employee.employee_attendances.all()
    attendances_ids = json.dumps([instance.id for instance in employee_attendances])
    context = {
        "attendances": employee_attendances,
        "attendances_ids": attendances_ids,
    }
    return render(request, "tabs/profile-attendance-tab.html", context)


@login_required
@hx_request_required
@manager_can_enter("employee.view_employee")
def attendance_tab(request, pk):
    """
    This function is used to view attendance tab of an employee in individual view.

    Parameters:
    request (HttpRequest): The HTTP request object.
    emp_id (int): The id of the employee.

    Returns: return attendance-tab template
    """

    requests = Attendance.objects.filter(
        is_validate_request=True,
        employee_id=pk,
    )
    attendances_ids = json.dumps([instance.id for instance in requests])
    validate_attendances = Attendance.objects.filter(
        attendance_validated=False, employee_id=pk
    )
    validate_attendances_ids = json.dumps(
        [instance.id for instance in validate_attendances]
    )
    accounts = AttendanceOverTime.objects.filter(employee_id=pk)
    accounts_ids = json.dumps([instance.id for instance in accounts])

    context = {
        "requests": requests,
        "attendances_ids": attendances_ids,
        "accounts": accounts,
        "accounts_ids": accounts_ids,
        "validate_attendances": validate_attendances,
        "validate_attendances_ids": validate_attendances_ids,
    }
    return render(request, "tabs/attendance-tab.html", context=context)


@login_required
@hx_request_required
@manager_can_enter("attendance.add_attendance")
def attendance_create(request):
    """
    This method is used to render attendance create form and save if it is valid
    """
    if request.GET.get("previous_url"):
        data = request.GET.dict()
        employee_list = request.GET.getlist("employee_id")
        data["employee_id"] = employee_list
        form = AttendanceForm(initial=data)
    else:
        form = AttendanceForm()
    form = choosesubordinates(request, form, "attendance.add_attendance")
    if request.method == "POST":
        form = AttendanceForm(request.POST)
        form = choosesubordinates(request, form, "attendance.add_attendance")
        if form.is_valid():
            form.save()
            messages.success(request, _("Attendance added."))
            return HorillaRedirect(request)
    return render(request, "attendance/attendance/form.html", {"form": form})


@login_required
@permission_required("attendance.add_attendance")
def attendance_excel(_request):
    """
    Generate an empty Excel template for attendance data with predefined columns.

    Returns:
        HttpResponse: An HTTP response containing an empty Excel template with predefined columns.
    """
    try:
        columns = [
            "Badge ID",
            "Shift",
            "Work type",
            "Attendance date",
            "Check-in date",
            "Check-in",
            "Check-out date",
            "Check-out",
            "Worked hour",
            "Minimum hour",
        ]
        data_frame = pd.DataFrame(columns=columns)
        response = HttpResponse(content_type="application/ms-excel")
        response["Content-Disposition"] = 'attachment; filename="my_excel_file.xlsx"'
        data_frame.to_excel(response, index=False)
        return response
    except Exception as exception:
        return HttpResponse(exception)


@login_required
@permission_required("attendance.add_attendance")
@require_http_methods(["POST"])
def attendance_import(request):
    """
    Save the import of attendance data from an uploaded Excel file, validate the data,
    and return an Excel file with error details if validation fails for anyone
    of the attendance data.

    Parameters:
        request (HttpRequest): The HTTP request object containing the uploaded Excel file.

    Returns:
        HttpResponse or redirect: An HTTP response with an Excel file containing error details
        if validation fails, or a redirect to the attendance view if successful.
    """
    if request.method == "POST":
        file = request.FILES["attendance_import"]
        file_extension = file.name.split(".")[-1].lower()
        data_frame = (
            pd.read_csv(file) if file_extension == "csv" else pd.read_excel(file)
        )
        attendance_dicts = data_frame.to_dict("records")
        attendance_import = process_attendance_data(attendance_dicts)
        path_info = None
        if attendance_import:
            path_info = handle_attendance_errors(attendance_import)

    created_attendance_count = len(attendance_dicts) - len(attendance_import)
    context = {
        "created_count": created_attendance_count,
        "error_count": len(attendance_import),
        "model": _("Attendance"),
        "path_info": path_info,
    }
    html = render_to_string("import_popup.html", context)
    return HttpResponse(html)


@login_required
def attendance_export(request):
    resolver_match = request.resolver_match
    if (
        resolver_match
        and resolver_match.url_name
        and resolver_match.url_name == "attendance-info-export-form"
    ):
        return render(
            request,
            "attendance/attendance/export_filter.html",
            context={
                "export": AttendanceFilters(queryset=Attendance.objects.all()),
                "export_form": AttendanceExportForm(),
            },
        )
    return export_data(
        request=request,
        model=Attendance,
        filter_class=AttendanceFilters,
        form_class=AttendanceExportForm,
        file_name="Attendance_export",
    )


@login_required
@manager_can_enter("attendance.view_attendance")
def attendance_view(request):
    """
    This method is used to view attendances.
    """
    previous_data = request.GET.urlencode()
    form = AttendanceForm()
    condition = AttendanceValidationCondition.objects.first()
    minot = strtime_seconds("00:00")
    if condition is not None and condition.minimum_overtime_to_approve is not None:
        minot = strtime_seconds(condition.minimum_overtime_to_approve)
    validate_attendances = Attendance.objects.filter(
        attendance_validated=False, employee_id__is_active=True
    )
    attendances = Attendance.objects.filter(
        attendance_validated=True, employee_id__is_active=True
    )
    # ot_attendances = Attendance.objects.filter(
    #     overtime_second__gte=minot,
    #     attendance_validated=True,
    #     employee_id__is_active=True,
    # )
    # for attendance in ot_attendances:
    #     attendance.min_ot_achieved = True
    ot_attendances = Attendance.objects.filter(
        overtime_second__gt=0,
        attendance_validated=True,
        employee_id__is_active=True,
    )
    filter_obj = AttendanceFilters(request.GET, queryset=attendances)
    attendances = filtersubordinates(
        request, filter_obj.qs, "attendance.view_attendance"
    )
    validate_attendances = AttendanceFilters(
        request.GET, queryset=validate_attendances
    ).qs
    validate_attendances = filtersubordinates(
        request, validate_attendances, "attendance.view_attendance"
    )
    ot_attendances = AttendanceFilters(request.GET, queryset=ot_attendances).qs
    ot_attendances = filtersubordinates(
        request, ot_attendances, "attendance.view_attendance"
    )
    check_attendance = Attendance.objects.all()
    if check_attendance.exists():
        template = "attendance/attendance/attendance_view.html"
    else:
        template = "attendance/attendance/attendance_empty.html"
    validate_attendances_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                validate_attendances, request.GET.get("vpage")
            ).object_list
        ]
    )
    ot_attendances_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                ot_attendances, request.GET.get("opage")
            ).object_list
        ]
    )
    attendances_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                attendances, request.GET.get("page")
            ).object_list
        ]
    )
    return render(
        request,
        template,
        {
            "form": form,
            # "validate_attendances": paginator_qry(
            #     validate_attendances, request.GET.get("vpage")
            # ),
            # "attendances": paginator_qry(attendances, request.GET.get("page")),
            # "overtime_attendances": paginator_qry(
            #     ot_attendances, request.GET.get("opage")
            # ),
            "validate_attendances_ids": validate_attendances_ids,
            "ot_attendances_ids": ot_attendances_ids,
            "attendances_ids": attendances_ids,
            "f": filter_obj,
            "pd": previous_data,
            "gp_fields": AttendanceReGroup.fields,
        },
    )


@login_required
@hx_request_required
@manager_can_enter("attendance.change_attendance")
def attendance_update(request, obj_id):
    """
    This method render form to update attendance and save if the form is valid
    args:
        obj_id : attendance id
    """
    attendance = Attendance.objects.get(id=obj_id)
    if request.GET.get("previous_url"):
        form = AttendanceUpdateForm(initial=request.GET.dict())
    else:
        form = AttendanceUpdateForm(
            instance=attendance,
        )
    form = choosesubordinates(request, form, "attendance.change_attendance")
    if request.method == "POST":
        form = AttendanceUpdateForm(request.POST, instance=attendance)
        form = choosesubordinates(request, form, "attendance.change_attendance")
        if form.is_valid():
            form.save()
            messages.success(request, _("Attendance Updated."))
            urlencode = request.GET.urlencode()
            modified_url = f"/attendance/attendance-view/?{urlencode}"
            return HorillaRedirect(request)
    return render(
        request,
        "attendance/attendance/update_form.html",
        {"form": form, "urlencode": request.GET.urlencode(), "obj_id": obj_id},
    )


def attendance_view_redirect(request):
    """
    Full page redirect for normal navigation; for HTMX requests (attendance-view),
    trigger a client-side refresh of the list container without reloading the page.
    """
    if request.META.get("HTTP_HX_REQUEST"):
        response = HttpResponse("", status=200)
        response["HX-Trigger"] = json.dumps(
            {"reloadAttendanceView": True, "showMessages": True}
        )
        return response
    return HorillaRedirect(request)


@login_required
@permission_required("attendance.delete_attendance")
@require_http_methods(["POST"])
def attendance_delete(request, obj_id):
    """
    This method is used to delete attendance.
    args:
        obj_id : attendance id
    """
    try:
        attendance = Attendance.objects.get(id=obj_id)
        month = attendance.attendance_date
        month = month.strftime("%B").lower()
        overtime = attendance.employee_id.employee_overtime.filter(month=month).last()
        if overtime is not None:
            if attendance.attendance_overtime_approve:
                # Subtract overtime of this attendance
                total_overtime = strtime_seconds(overtime.overtime)
                attendance_overtime_seconds = strtime_seconds(
                    attendance.attendance_overtime
                )
                if total_overtime > attendance_overtime_seconds:
                    total_overtime = total_overtime - attendance_overtime_seconds
                else:
                    total_overtime = attendance_overtime_seconds - total_overtime
                overtime.overtime = format_time(total_overtime)
                overtime.save()
        try:
            attendance.delete()
            messages.success(request, _("Attendance deleted."))
        except ProtectedError as e:
            model_verbose_names_set = set()
            for obj in e.protected_objects:
                model_verbose_names_set.add(__(obj._meta.verbose_name.capitalize()))
            model_names_str = ", ".join(model_verbose_names_set)
            messages.error(
                request,
                _(
                    ("An attendance entry for {} already exists.").format(
                        model_names_str
                    )
                ),
            )
    except (Attendance.DoesNotExist, OverflowError):
        messages.error(request, _("Attendance Does not exists.."))
    return attendance_view_redirect(request)


@login_required
@permission_required("attendance.delete_attendance")
@require_http_methods(["POST"])
def attendance_bulk_delete(request):
    """
    This method is used to delete a bulk of attendances
    """
    success_count = 0
    error_messages = []
    ids = request.POST.getlist("ids", "[]")
    attendances = Attendance.objects.filter(id__in=ids)
    employee_ids = attendances.values_list("employee_id", flat=True)
    overtimes = AttendanceOverTime.objects.filter(
        employee_id__in=employee_ids
    ).in_bulk()

    with transaction.atomic():
        for attendance in attendances:
            try:
                month = attendance.attendance_date.strftime("%B").lower()
                overtime = overtimes.get(attendance.employee_id.id)

                if overtime and attendance.attendance_overtime_approve:
                    # Calculate the new overtime
                    total_overtime = strtime_seconds(overtime.overtime)
                    attendance_overtime_seconds = strtime_seconds(
                        attendance.attendance_overtime
                    )
                    total_overtime = abs(total_overtime - attendance_overtime_seconds)
                    overtime.overtime = format_time(total_overtime)
                    overtime.save()

                attendance.delete()
                success_count += 1

            except ProtectedError as e:
                model_verbose_names_set = {
                    __(obj._meta.verbose_name.capitalize())
                    for obj in e.protected_objects
                }
                model_names_str = ", ".join(model_verbose_names_set)
                error_messages.append(
                    f"An attendance entry is protected by: {model_names_str}."
                )

    # Build response messages
    if success_count:
        messages.success(
            request,
            _("%(success_count)s attendances deleted successfully.")
            % {"success_count": success_count},
        )
    for error in error_messages:
        messages.error(request, error)
    return JsonResponse({"message": "Success"})


@login_required
def view_my_attendance(request):
    """
    This method is used to view self attendances of employee
    """
    user = request.user
    try:
        employee = user.employee_get
    except:
        return redirect("/employee/employee-profile")
    employee = user.employee_get
    employee_attendances = employee.employee_attendances.all()
    filter = AttendanceFilters()
    if employee_attendances.exists():
        template = "attendance/own_attendance/view_own_attendances.html"
    else:
        template = "attendance/own_attendance/own_empty.html"
    attendances_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                employee_attendances, request.GET.get("page")
            ).object_list
        ]
    )
    return render(
        request,
        template,
        {
            "attendances": paginator_qry(employee_attendances, request.GET.get("page")),
            "attendances_ids": attendances_ids,
            "f": filter,
            "gp_fields": AttendanceReGroup.fields,
        },
    )


@login_required
@hx_request_required
@manager_can_enter("attendance.add_attendanceovertime")
def attendance_overtime_create(request):
    """
    This method is used to render overtime creating form and save if the form is valid
    """
    form = AttendanceOverTimeForm()
    form = choosesubordinates(request, form, "attendance.add_attendanceovertime")
    if request.method == "POST":
        form = AttendanceOverTimeForm(request.POST)
        form = choosesubordinates(request, form, "attendance.add_attendanceovertime")
        if form.is_valid():
            form.save()
            messages.success(request, _("Attendance account added."))
            return HorillaRedirect(request)
    return render(request, "attendance/attendance_account/form.html", {"form": form})


@login_required
def attendance_overtime_view(request):
    """
    This method is used to view attendance account or overtime account.
    """
    previous_data = request.GET.urlencode()
    filter_obj = AttendanceOverTimeFilter(request.GET)
    if filter_obj.qs.exists():
        template = "attendance/attendance_account/attendance_overtime_view.html"
    else:
        template = "attendance/attendance_account/overtime_empty.html"
    self_account = filter_obj.qs.filter(employee_id__employee_user_id=request.user)
    accounts = filtersubordinates(
        request, filter_obj.qs, "attendance.view_attendanceovertime"
    )
    accounts = accounts | self_account
    accounts = accounts.distinct()
    form = AttendanceOverTimeForm()
    form = choosesubordinates(request, form, "attendance.add_attendanceovertime")
    data_dict = parse_qs(previous_data)
    get_key_instances(AttendanceOverTime, data_dict)
    return render(
        request,
        template,
        {
            "accounts": paginator_qry(accounts, request.GET.get("page")),
            "form": form,
            "pd": previous_data,
            "f": filter_obj,
            "gp_fields": AttendanceOvertimeReGroup.fields,
            "filter_dict": data_dict,
        },
    )


@login_required
def attendance_account_export(request):
    if request.META.get("HTTP_HX_REQUEST") == "true":
        context = {
            "export_obj": AttendanceOverTimeFilter(),
            "export_fields": AttendanceOverTimeExportForm(),
        }

        return render(
            request,
            "attendance/attendance_account/attendance_account_export_filter.html",
            context=context,
        )
    return export_data(
        request=request,
        model=AttendanceOverTime,
        filter_class=AttendanceOverTimeFilter,
        form_class=AttendanceOverTimeExportForm,
        file_name="Attendance_Account",
    )


@login_required
@manager_can_enter("attendance.change_attendanceovertime")
@hx_request_required
def attendance_overtime_update(request, obj_id):
    """
    This method is used to update attendance overtime and save if the forms is valid
    args:
        obj_id : attendance overtime id
    """
    overtime = AttendanceOverTime.objects.get(id=obj_id)
    form = AttendanceOverTimeForm(instance=overtime)
    form = choosesubordinates(request, form, "attendance.change_attendanceovertime")
    if request.method == "POST":
        form = AttendanceOverTimeForm(request.POST, instance=overtime)
        form = choosesubordinates(request, form, "attendance.change_attendanceovertime")
        if form.is_valid():
            form.save()
            messages.success(request, _("Attendance account updated successfully."))
            return HorillaRedirect(request)
    return render(
        request, "attendance/attendance_account/update_form.html", {"form": form}
    )


@login_required
@permission_required("attendance.delete_attendanceovertime")
@require_http_methods(["POST"])
def attendance_overtime_delete(request, obj_id):
    """
    This method is used to delete attendance overtime
    args:
        obj_id : attendance overtime id
    """
    previous_data = request.GET.urlencode()
    hx_target = request.META.get("HTTP_HX_TARGET", None)
    employee_id = None
    try:
        attendance = AttendanceOverTime.objects.get(id=obj_id)
        employee_id = attendance.employee_id.id
        attendance.delete()
        if hx_target == "ot-table":
            messages.success(request, _("Hour account deleted."))
    except (AttendanceOverTime.DoesNotExist, OverflowError, ValueError):
        if hx_target == "ot-table":
            messages.error(request, _("Hour account not found"))
    except ProtectedError:
        if hx_target == "ot-table":
            messages.error(request, _("You cannot delete this hour account"))
    if hx_target and hx_target == "ot-table":
        hour_account = AttendanceOverTime.objects.all()
        if hour_account.exists():
            path = request.META.get("HTTP_HX_CURRENT_URL", None)
            parsed_url = urlparse(path)
            parsed_path = parsed_url.path.lstrip("/")
            if parsed_path == "attendance/attendance-overtime-view/":
                return redirect(
                    f"/attendance/attendance-overtime-search?{previous_data}"
                )
            elif employee_id is not None:
                return redirect(
                    f"/attendance/attendance-overtime-individual-tab/{employee_id}/?deleted=true"
                )
            else:
                return HorillaRedirect(request)
        else:
            return HorillaRedirect(request)
    elif hx_target:
        return HttpResponse()


@login_required
@permission_required("attendance.delete_attendanceovertime")
def attendance_account_bulk_delete(request):
    """
    This method is used to bulk delete for Payslip
    """
    ids = json.loads(request.POST.get("ids", "[]"))
    for id in ids:
        try:
            hour_account = AttendanceOverTime.objects.get(id=id)
            hour_account.delete()
            messages.success(
                request,
                _("{employee} hour account deleted.").format(
                    employee=hour_account.employee_id
                ),
            )
        except AttendanceOverTime.DoesNotExist:
            messages.error(request, _("Hour account not found."))
        except ProtectedError:
            messages.error(
                request,
                _("You cannot delete {hour_account}").format(hour_account=hour_account),
            )
    return JsonResponse({"message": "Success"})


@login_required
@hx_request_required
def form_shift_dynamic_data(request):
    """
    This method is used to update the shift details to the form
    """
    shift_id = request.POST.get("shift_id")
    attendance_date_str = request.POST.get("attendance_date")
    today = datetime.now()
    attendance_date = date(day=today.day, month=today.month, year=today.year)
    if attendance_date_str is not None and attendance_date_str != "":
        attendance_date = datetime.strptime(attendance_date_str, "%Y-%m-%d").date()
    day = attendance_date.strftime("%A").lower()
    schedule_today = EmployeeShiftSchedule.objects.filter(
        shift_id__id=shift_id, day__day=day
    ).first()
    shift_start_time = ""
    shift_end_time = ""
    minimum_hour = "00:00"
    attendance_clock_out_date = attendance_date
    if schedule_today is not None:
        shift_start_time = schedule_today.start_time
        shift_end_time = schedule_today.end_time
        minimum_hour = schedule_today.minimum_working_hour
        if shift_end_time < shift_start_time:
            attendance_clock_out_date = attendance_date + timedelta(days=1)
    worked_hour = minimum_hour
    if attendance_date == date(day=today.day, month=today.month, year=today.year):
        shift_end_time = datetime.now().strftime("%H:%M")
        worked_hour = "00:00"

    minimum_hour = attendance_day_checking(str(attendance_date), minimum_hour)

    return JsonResponse(
        {
            "shift_start_time": shift_start_time,
            "shift_end_time": shift_end_time,
            "checkin_date": attendance_date.strftime("%Y-%m-%d"),
            "minimum_hour": minimum_hour,
            "worked_hour": worked_hour,
            "checkout_date": attendance_clock_out_date.strftime("%Y-%m-%d"),
        }
    )


@login_required
def attendance_activity_view(request):
    """
    This method will render a template to view all attendance activities
    """
    previous_data = request.GET.urlencode()
    filter_obj = AttendanceActivityFilter(request.GET)
    attendance_activities = filter_obj.qs
    self_attendance_activities = attendance_activities.filter(
        employee_id__employee_user_id=request.user
    )
    attendance_activities = filtersubordinates(
        request, filter_obj.qs, "attendance.view_attendanceovertime"
    )
    attendance_activities = attendance_activities | self_attendance_activities
    attendance_activities = attendance_activities.distinct()
    attendance_activities = attendance_activities.order_by("-pk")
    activity_ids = json.dumps(
        [instance.id for instance in paginator_qry(attendance_activities, None)]
    )
    if attendance_activities.exists():
        template = "attendance/attendance_activity/attendance_activity_view.html"
    else:
        template = "attendance/attendance_activity/activity_empty.html"
    return render(
        request,
        template,
        {
            "data": paginator_qry(attendance_activities, request.GET.get("page")),
            "pd": previous_data,
            "f": filter_obj,
            "gp_fields": AttendanceActivityReGroup.fields,
            "activity_ids": activity_ids,
        },
    )


@login_required
def activity_single_view(request, obj_id):
    request_copy = request.GET.copy()
    request_copy.pop("instances_ids", None)
    previous_data = request_copy.urlencode()
    activity = AttendanceActivity.objects.filter(id=obj_id).first()

    instance_ids_json = request.GET["instances_ids"]
    instance_ids = json.loads(instance_ids_json) if instance_ids_json else []
    previous_instance, next_instance = closest_numbers(instance_ids, obj_id)
    context = {
        "pd": previous_data,
        "activity": activity,
        "previous_instance": previous_instance,
        "next_instance": next_instance,
        "instance_ids_json": instance_ids_json,
    }
    if activity:
        attendance = Attendance.objects.filter(
            attendance_date=activity.attendance_date
        ).first()
        context["attendance"] = attendance

    return render(
        request,
        "attendance/attendance_activity/single_attendance_activity.html",
        context=context,
    )


@login_required
@permission_required("attendance.delete_attendanceactivity")
@require_http_methods(["POST", "DELETE"])
def attendance_activity_delete(request, obj_id):
    """
    This method is used to delete attendance activity
    args:attendance-activity-delete
        obj_id : attendance activity id
    """
    request_copy = request.GET.copy()
    request_copy.pop("instances_ids", None)
    previous_data = request_copy.urlencode()
    try:
        AttendanceActivity.objects.get(id=obj_id).delete()
        messages.success(request, _("Attendance activity deleted"))
    except AttendanceActivity.DoesNotExist:
        messages.error(request, _("Attendance activity Does not exists.."))
    except ProtectedError:
        messages.error(request, _("You cannot delete this activity"))

    if not request.GET.get("instances_ids"):
        return redirect(f"/attendance/attendance-activity-search?{previous_data}")
    else:
        instances_ids = request.GET.get("instances_ids")
        instances_list = json.loads(instances_ids)
        if obj_id in instances_list:
            instances_list.remove(obj_id)
        previous_instance, next_instance = closest_numbers(
            json.loads(instances_ids), obj_id
        )
        return redirect(
            f"/attendance/attendance-activity-single-view/{next_instance}/?{previous_data}&instance_ids={instances_list}&deleted=true"
        )


@login_required
@permission_required("attendance.delete_attendanceactivity")
@require_http_methods(["POST"])
def attendance_activity_bulk_delete(request):
    """
    Deletes a bulk of AttendanceActivity records based on a list of IDs.
    """
    try:
        ids_json = request.POST.get("ids", "[]")

        try:
            ids = json.loads(ids_json)
        except json.JSONDecodeError:
            messages.error(request, _("Invalid list of IDs provided."))
            return HttpResponse("<script>$('.filterButton')[0].click()</script>")

        try:
            ids = [int(i) for i in ids]
        except (ValueError, TypeError):
            messages.error(request, _("Invalid list of IDs provided."))
            return HttpResponse("<script>$('.filterButton')[0].click()</script>")

        if not ids:
            messages.warning(
                request, _("No attendance activities selected for deletion.")
            )
            return HttpResponse("<script>$('.filterButton')[0].click()</script>")

        # Perform the delete operation in a transaction
        with transaction.atomic():
            activities = AttendanceActivity.objects.filter(id__in=ids)
            count = activities.count()
            activities.delete()

        if count > 0:
            messages.success(
                request,
                _("{count} attendance activities deleted successfully.").format(
                    count=count
                ),
            )
        else:
            messages.info(
                request,
                _("No matching attendance activities were found to delete."),
            )

    except Exception as e:
        logger.exception("Error during bulk delete of attendance activities")
        messages.error(
            request,
            _("Failed to delete attendance activities: {error}").format(error=str(e)),
        )

    return HttpResponse("<script>$('.filterButton')[0].click()</script>")


def process_activity_dicts(activity_dicts):
    from attendance.views.clock_in_out import clock_in, clock_out

    if not activity_dicts:
        return []

    sorted_activity_dicts = sort_activity_dicts(activity_dicts)
    error_dicts = []  # List to store dictionaries with errors

    for activity in sorted_activity_dicts:
        badge_id = activity.get("Badge ID")
        if not badge_id:
            activity["Error 1"] = "Please add the Badge ID column in the Excel sheet."
            error_dicts.append(activity)
            continue

        employee = Employee.objects.filter(badge_id=badge_id).first()
        if not employee:
            activity["Error 2"] = "Invalid Badge ID"
            error_dicts.append(activity)
            continue

        check_in_date = parse_date(activity["In Date"], "Error 4", activity)
        check_out_date = parse_date(activity["Out Date"], "Error 5", activity)
        check_in_time = (
            parse_time(activity["Check In"])
            if not pd.isna(activity["Check In"])
            else None
        )
        check_out_time = (
            parse_time(activity["Check Out"])
            if not pd.isna(activity["Check Out"])
            else None
        )

        if any(key.startswith("Error") for key in activity.keys()):
            error_dicts.append(activity)
            continue

        if check_in_time:
            try:
                clock_in(
                    Request(
                        user=employee.employee_user_id,
                        date=check_in_date,
                        time=check_in_time,
                        datetime=django_timezone.make_aware(
                            datetime.combine(check_in_date, check_in_time)
                        ),
                    )
                )
            except Exception as e:
                activity["Error 6"] = f"Got an error in import clock in {e}"
                error_dicts.append(activity)

        if check_out_time and check_out_date:
            try:
                clock_out(
                    Request(
                        user=employee.employee_user_id,
                        date=check_out_date,
                        time=check_out_time,
                        datetime=django_timezone.make_aware(
                            datetime.combine(check_out_date, check_out_time)
                        ),
                    )
                )
            except Exception as e:
                activity["Error 7"] = f"Got an error in import clock out {e}"
                error_dicts.append(activity)

    return error_dicts


def handle_activity_import_error(error_data):

    # Directly create the DataFrame from the list of dictionaries
    data_frame = pd.DataFrame(error_data)

    # Create an HTTP response with an Excel attachment
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = 'attachment; filename="ImportError.xlsx"'
    data_frame.to_excel(response, index=False)

    def get_activity_error_sheet(request):
        remove_dynamic_url(path_info)
        return response

    from attendance.urls import path, urlpatterns

    # Create a unique path for the error file download
    path_info = f"activity-error-sheet-{uuid.uuid4()}"
    urlpatterns.append(path(path_info, get_activity_error_sheet, name=path_info))
    settings.DYNAMIC_URL_PATTERNS.append(path_info)

    # Return the path information
    path_info = f"attendance/{path_info}"
    return path_info


@login_required
@permission_required("attendance.add_attendanceactivity")
def attendance_activity_import(request):
    if request.method == "POST":
        file = request.FILES["activity_import"]
        data_frame = pd.read_excel(file)
        activity_dicts = data_frame.to_dict("records")
        if activity_dicts:
            import_error_dicts = process_activity_dicts(activity_dicts)
            path_info = handle_activity_import_error(import_error_dicts)
            created_activity_count = len(activity_dicts) - len(import_error_dicts)
            context = {
                "created_count": created_activity_count,
                "error_count": len(import_error_dicts),
                "model": _("Check-in / Check-out Log"),
                "path_info": path_info,
            }
            html = render_to_string("import_popup.html", context)
            messages.success(request, _("Attendance activity imported successfully"))
            return HttpResponse(html)
    return render(request, "attendance/attendance_activity/import_activity.html")


@login_required
@permission_required("attendance.add_attendanceactivity")
def attendance_activity_import_excel(request):
    if request.method == "GET":
        data_frame = pd.DataFrame(
            columns=[
                "Badge ID",
                "Employee",
                "Attendance Date",
                "In Date",
                "Check In",
                "Check Out",
                "Out Date",
            ]
        )
        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="activity_excel.xlsx"'
        data_frame.to_excel(response, index=False)
        return response


@login_required
@permission_required("attendance.change_attendanceactivity")
def attendance_activity_export(request):
    if request.META.get("HTTP_HX_REQUEST") == "true":
        export_form = AttendanceActivityExportForm()
        context = {
            "export_form": export_form,
            "export": AttendanceActivityFilter(
                queryset=AttendanceActivity.objects.all()
            ),
        }
        return render(
            request,
            "attendance/attendance_activity/export_filter.html",
            context=context,
        )
    return export_data(
        request=request,
        model=AttendanceActivity,
        filter_class=AttendanceActivityFilter,
        form_class=AttendanceActivityExportForm,
        file_name="Attendance_activity",
    )


@login_required
@hx_request_required
def on_time_view(request):
    """
    This method render template to view all on come early out entries
    """
    total_attendances = AttendanceFilters(request.GET).qs
    ids_to_exclude = AttendanceLateComeEarlyOut.objects.filter(
        attendance_id__in=total_attendances.values_list("id", flat=True),
        type="late_come",
    ).values_list("attendance_id", flat=True)
    # Filter out late-come attendances
    total_attendances = total_attendances.exclude(id__in=ids_to_exclude)

    paginator = Paginator(total_attendances, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "attendances": page_obj.object_list,
    }
    return render(
        request, "attendance/attendance/attendance_on_time.html", context=context
    )


@login_required
@install_required
def late_come_early_out_view(request):
    """
    This method render template to view all late come early out entries
    """
    filter_obj = LateComeEarlyOutFilter(request.GET)
    if filter_obj.qs.exists():
        template = "attendance/late_come_early_out/reports.html"
    else:
        template = "attendance/late_come_early_out/reports_empty.html"
    self_reports = filter_obj.qs.filter(employee_id__employee_user_id=request.user)
    reports = filtersubordinates(
        request, filter_obj.qs, "attendance.view_attendancelatecomeearlyout"
    )

    reports = reports | self_reports
    reports = reports.distinct()
    late_in_early_out_ids = json.dumps(
        [instance.id for instance in paginator_qry(reports, None)]
    )
    previous_data = request.GET.urlencode()
    data_dict = parse_qs(previous_data)
    get_key_instances(AttendanceLateComeEarlyOut, data_dict)
    return render(
        request,
        template,
        {
            "data": paginator_qry(reports, request.GET.get("page")),
            "f": filter_obj,
            "gp_fields": LateComeEarlyOutReGroup.fields,
            "filter_dict": data_dict,
            "late_in_early_out_ids": late_in_early_out_ids,
        },
    )


@login_required
@hx_request_required
def late_in_early_out_single_view(request, obj_id):
    request_copy = request.GET.copy()
    request_copy.pop("instances_ids", None)
    previous_data = request_copy.urlencode()
    late_in_early_out = AttendanceLateComeEarlyOut.objects.filter(id=obj_id).first()
    instance_ids_json = request.GET["instances_ids"]
    instance_ids = json.loads(instance_ids_json) if instance_ids_json else []
    previous_instance, next_instance = closest_numbers(instance_ids, obj_id)
    context = {
        "late_in_early_out": late_in_early_out,
        "previous_instance": previous_instance,
        "next_instance": next_instance,
        "instance_ids_json": instance_ids_json,
        "pd": previous_data,
    }
    return render(
        request, "attendance/late_come_early_out/single_report.html", context=context
    )


@login_required
@permission_required("attendance.delete_attendancelatecomeearlyout")
@hx_request_required
@require_http_methods(["POST"])
def late_come_early_out_delete(request, obj_id):
    """
    This method is used to delete the late come early out instance
    args:
        obj_id : late come early out instance id
    """
    request_copy = request.GET.copy()
    request_copy.pop("instances_ids", None)
    previous_data = request_copy.urlencode()
    try:
        AttendanceLateComeEarlyOut.objects.get(id=obj_id).delete()
        messages.success(request, _("Late-in early-out deleted"))
    except AttendanceLateComeEarlyOut.DoesNotExist:
        messages.error(request, _("Late-in early-out does not exists.."))
    except ProtectedError:
        messages.error(request, _("You cannot delete this Late-in early-out"))
    if not request.GET.get("instances_ids"):
        return redirect(f"/attendance/late-come-early-out-search?{previous_data}")
    else:
        instances_ids = request.GET.get("instances_ids")
        instances_list = json.loads(instances_ids)
        if obj_id in instances_list:
            instances_list.remove(obj_id)
        previous_instance, next_instance = closest_numbers(
            json.loads(instances_ids), obj_id
        )
        return redirect(
            f"/attendance/late-in-early-out-single-view/{next_instance}/?{previous_data}&instance_ids={instances_list}&deleted=true"
        )


@login_required
@permission_required("attendance.delete_attendancelatecomeearlyout")
@require_http_methods(["POST"])
def late_come_early_out_bulk_delete(request):
    """
    This method is used to delete bulk of attendances
    """
    ids = request.POST["ids"]
    ids = json.loads(ids)
    del_ids = []
    for attendance_id in ids:
        try:
            late_come = AttendanceLateComeEarlyOut.objects.get(id=attendance_id)
            late_come.delete()
            del_ids.append(late_come)
        except (AttendanceLateComeEarlyOut.DoesNotExist, OverflowError, ValueError):
            messages.error(request, _("Attendance not found."))
    messages.success(request, _("{} Late-in early-out deleted.".format(len(del_ids))))
    return JsonResponse({"message": "Success"})


@login_required
@permission_required("attendance.change_attendancelatecomeearlyout")
def late_come_early_out_export(request):
    """
    Export late come early out data to an Excel file.
    This view function takes a GET request and exports attendance late come early out data into an Excel file.
    The exported Excel file will include the selected fields from the AttendanceLateComeEarlyOut model.
    """
    if request.META.get("HTTP_HX_REQUEST") == "true":
        context = {
            "export": LateComeEarlyOutFilter(
                queryset=AttendanceLateComeEarlyOut.objects.all()
            ),
            "export_form": LateComeEarlyOutExportForm(),
        }

        return render(
            request,
            "attendance/late_come_early_out/export_filter.html",
            context=context,
        )
    return export_data(
        request=request,
        model=AttendanceLateComeEarlyOut,
        filter_class=LateComeEarlyOutFilter,
        form_class=LateComeEarlyOutExportForm,
        file_name="Late_come_",
    )


@login_required
@permission_required("attendance.change_attendancevalidationcondition")
@require_http_methods(["POST"])
def validation_condition_delete(request, obj_id):
    """
    This method is used to delete created validation condition
    args:
        obj_id  : validation condition id
    """
    try:
        AttendanceValidationCondition.objects.get(id=obj_id).delete()
        messages.success(request, _("validation condition deleted."))
    except AttendanceValidationCondition.DoesNotExist:
        messages.error(request, _("validation condition Does not exists.."))
    except ProtectedError:
        messages.error(request, _("You cannot delete this validation condition."))
    return redirect("/attendance/validation-condition-view")


@login_required
@require_http_methods(["POST"])
@manager_can_enter("attendance.change_attendance")
def validate_bulk_attendance(request):
    """
    This method is used to validate a bulk of attendances.
    """
    ids = json.loads(request.POST["ids"])
    validate_req_count = 0
    success_messages = []
    error_messages = []
    filtered_ids = []

    for obj_id in ids:
        try:
            attendance = Attendance.objects.get(id=obj_id)
            if attendance.employee_id.id != request.user.employee_get.id:
                filtered_ids.append(obj_id)
        except Attendance.DoesNotExist:
            error_messages.append(_("Attendance not found"))
        except (OverflowError, ValueError):
            error_messages.append(_("Invalid attendance ID"))

    if request.user.is_superuser:
        filtered_ids = ids

    for obj_id in filtered_ids:
        try:
            attendance = Attendance.objects.get(id=obj_id)

            if attendance.is_validate_request:
                error_messages.append(
                    _(
                        "Pending attendance update request for {}'s attendance on {}!"
                    ).format(attendance.employee_id, attendance.attendance_date)
                )
                continue

            attendance.attendance_validated = True
            # Recalculate worked hours from attendance activities before validation
            # to ensure Hours Account reflects actual worked time.
            # Fixes: https://github.com/horilla/horilla-hr/issues/1055
            if (
                not attendance.attendance_worked_hour
                or attendance.attendance_worked_hour == "00:00"
            ):
                at_work_seconds = attendance.get_at_work_from_activities()
                if at_work_seconds > 0:
                    attendance.attendance_worked_hour = format_time(at_work_seconds)
            attendance.save()
            validate_req_count += 1

            # Send notification
            notify.send(
                request.user.employee_get,
                recipient=attendance.employee_id.employee_user_id,
                verb=f"Your attendance for the date {attendance.attendance_date} is validated",
                verb_ar=f"تم التحقق من حضورك في تاريخ {attendance.attendance_date}",
                verb_de=f"Ihre Anwesenheit für das Datum {attendance.attendance_date} wurde bestätigt",
                verb_es=f"Se ha validado su asistencia para la fecha {attendance.attendance_date}",
                verb_fr=f"Votre présence pour la date {attendance.attendance_date} est validée",
                redirect=reverse("view-my-attendance") + f"?id={attendance.id}",
                icon="checkmark",
            )

        except Attendance.DoesNotExist:
            error_messages.append(_("Attendance not found"))
        except (OverflowError, ValueError):
            error_messages.append(_("Invalid attendance ID"))

    # Handle messages
    if validate_req_count > 0:
        messages.success(
            request, _("{} Attendances validated.").format(validate_req_count)
        )
    for msg in success_messages + error_messages:
        if "Pending" in msg:
            messages.info(request, msg)
        else:
            messages.error(request, msg)

    return JsonResponse({"message": "success"})


@login_required
@manager_can_enter("attendance.change_attendance")
def validate_this_attendance(request, obj_id):
    """
    This method is used to validate attendance
    args:
        id  : attendance id
    """
    try:
        attendance = Attendance.objects.get(id=obj_id)
        if not request.user.is_superuser:
            if attendance.employee_id.id == request.user.employee_get.id:
                messages.error(request, _("You cannot validate your own attendance."))
                return attendance_view_redirect(request)
        attendance.attendance_validated = True
        # Recalculate worked hours from attendance activities before validation
        # to ensure Hours Account reflects actual worked time.
        # Fixes: https://github.com/horilla/horilla-hr/issues/1055
        if (
            not attendance.attendance_worked_hour
            or attendance.attendance_worked_hour == "00:00"
        ):
            at_work_seconds = attendance.get_at_work_from_activities()
            if at_work_seconds > 0:
                attendance.attendance_worked_hour = format_time(at_work_seconds)
        attendance.save()
        urlencode = request.GET.urlencode()
        modified_url = f"/attendance/attendance-view/?{urlencode}"
        messages.success(
            request,
            (
                _("%(employee)s %(date)s Attendance validated.")
                % {
                    "employee": attendance.employee_id,
                    "date": attendance.attendance_date.strftime("%d %b %Y"),
                }
            ),
        )
        notify.send(
            request.user.employee_get,
            recipient=attendance.employee_id.employee_user_id,
            verb=f"Your attendance for the date {attendance.attendance_date} is validated",
            verb_ar=f"تم تحقيق حضورك في تاريخ {attendance.attendance_date}",
            verb_de=f"Deine Anwesenheit für das Datum {attendance.attendance_date} ist bestätigt.",
            verb_es=f"Se valida tu asistencia para la fecha {attendance.attendance_date}.",
            verb_fr=f"Votre présence pour la date {attendance.attendance_date} est validée.",
            redirect=reverse("view-my-attendance") + f"?id={attendance.id}",
            icon="checkmark",
        )
    except (Attendance.DoesNotExist, ValueError):
        messages.error(request, _("Attendance not found"))

    return attendance_view_redirect(request)


@login_required
def revalidate_this_attendance(request, obj_id):
    """
    This method is used to not validate the attendance.
    args:
        id  : attendance id
    """

    attendance = Attendance.find(obj_id)
    if not attendance:
        return HorillaRedirect(
            request, message=_("No Attendance found matching the query.")
        )

    if is_reportingmanger(request, attendance) or request.user.has_perm(
        "attendance.change_attendance"
    ):
        attendance.attendance_validated = False
        attendance.save()
        with contextlib.suppress(Exception):
            notify.send(
                request.user.employee_get,
                recipient=(
                    attendance.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                ),
                verb=f"{attendance.employee_id} requested revalidation for \
                    {attendance.attendance_date} attendance",
                verb_ar=f"{attendance.employee_id} طلب إعادة\
                      التحقق من حضور تاريخ {attendance.attendance_date}",
                verb_de=f"{attendance.employee_id} beantragte eine Neubewertung der \
                    Teilnahme am {attendance.attendance_date}",
                verb_es=f"{attendance.employee_id} solicitó la validación nuevamente \
                    para la asistencia del {attendance.attendance_date}",
                verb_fr=f"{attendance.employee_id} a demandé une revalidation pour la \
                    présence du {attendance.attendance_date}",
                redirect=reverse("view-my-attendance") + f"?id={attendance.id}",
                icon="refresh",
            )
        return HorillaRedirect(request)
    return HttpResponse("You Cannot Request for others attendance")


@login_required
@manager_can_enter("attendance.change_attendance")
@require_http_methods(["GET", "POST"])
def approve_overtime(request, obj_id):
    """
    This method is used to approve attendance overtime
    args:
        obj_id  : attendance id
    """
    try:
        attendance = Attendance.objects.get(id=obj_id)
        if not request.user.is_superuser:
            if attendance.employee_id.id == request.user.employee_get.id:
                messages.error(request, _("You cannot approve your own overtime."))
                return attendance_view_redirect(request)
        attendance.attendance_overtime_approve = True
        attendance.save()
        urlencode = request.GET.urlencode()
        modified_url = f"/attendance/attendance-view/?{urlencode}"
        messages.success(
            request,
            _("%(employee)s's %(date)s overtime approved")
            % {
                "employee": attendance.employee_id,
                "date": attendance.attendance_date.strftime("%d %b %Y"),
            },
        )
        with contextlib.suppress(Exception):
            notify.send(
                request.user.employee_get,
                recipient=attendance.employee_id.employee_user_id,
                verb=f"Your {attendance.attendance_date}'s attendance \
                    overtime approved.",
                verb_ar=f"تمت الموافقة على إضافة ساعات العمل الإضافية لتاريخ \
                    {attendance.attendance_date}.",
                verb_de=f"Die Überstunden für den {attendance.attendance_date}\
                      wurden genehmigt.",
                verb_es=f"Se ha aprobado el tiempo extra de asistencia para el \
                    {attendance.attendance_date}.",
                verb_fr=f"Les heures supplémentaires pour la date\
                      {attendance.attendance_date} ont été approuvées.",
                redirect=reverse("attendance-overtime-view") + f"?id={attendance.id}",
                icon="checkmark",
            )
    except (Attendance.DoesNotExist, OverflowError):
        messages.error(request, _("Attendance not found"))
    return attendance_view_redirect(request)


@login_required
@manager_can_enter("attendance.change_attendance")
def approve_bulk_overtime(request):
    """
    This method is used to approve bulk of attendance
    """
    ids = json.loads(request.POST.get("ids", "[]"))
    otapprove_ids = []
    filtered_ids = []
    for attendance_id in ids:
        try:
            attendance = Attendance.objects.get(id=attendance_id)
            if attendance.employee_id.employee_user_id != request.user:
                filtered_ids.append(attendance_id)
        except (Attendance.DoesNotExist, OverflowError, ValueError):
            messages.error(request, _("Attendance not found"))
    if request.user.is_superuser:
        filtered_ids = ids
    for attendance_id in filtered_ids:
        try:
            attendance = Attendance.objects.get(id=attendance_id)
            attendance.attendance_overtime_approve = True
            attendance.save()
            otapprove_ids.append(attendance)
            notify.send(
                request.user.employee_get,
                recipient=attendance.employee_id.employee_user_id,
                verb=f"Overtime approved for\
                      {attendance.attendance_date}'s attendance",
                verb_ar=f"تمت الموافقة على العمل الإضافي لحضور تاريخ \
                    {attendance.attendance_date}",
                verb_de=f"Überstunden für die Anwesenheit am \
                    {attendance.attendance_date} genehmigt",
                verb_es=f"Horas extra aprobadas para la asistencia del \
                    {attendance.attendance_date}",
                verb_fr=f"Heures supplémentaires approuvées pour la présence du \
                    {attendance.attendance_date}",
                redirect=reverse("attendance-overtime-view") + f"?id={attendance.id}",
                icon="checkmark",
            )
        except (Attendance.DoesNotExist, OverflowError, ValueError):
            messages.error(request, _("Attendance not found"))
    if otapprove_ids:
        messages.success(request, _(" {} Overtime approved".format(len(otapprove_ids))))

    return JsonResponse({"message": "Success"})


@login_required
@hx_request_required
# @manager_can_enter("attendance.change_attendance")
def attendance_add_to_batch(request):
    """
    This method is used to add attendance to a batch
    """
    batches = BatchAttendance.objects.all()
    ids = request.GET.getlist("ids")
    if request.method == "POST":
        ids = request.GET["ids"]
        # Remove brackets and quotes, then split and convert to integers
        int_ids = [int(x.strip().strip("'")) for x in ids.strip("[]").split(",")]
        batch_id = request.POST.get("batch_attendance_id")
        if batch_id:
            batch = BatchAttendance.objects.filter(id=batch_id).first()
            for id in int_ids:
                try:
                    attendance_req = Attendance.objects.filter(id=id).first()
                    attendance_req.batch_attendance_id = batch
                    attendance_req.save()
                except Exception as e:
                    logger.error(e)
                    messages.error(request, _("Something went wrong."))
                    return HorillaRedirect(request)
            messages.success(request, _(f"Attendances added to {batch}."))
            return HorillaRedirect(request)
        else:
            messages.error(request, _("Something went wrong."))
            return HorillaRedirect(request)
    return render(
        request,
        "attendance/attendance/attendance_add_batch.html",
        {"batches": batches, "ids": ids},
    )


@login_required
@hx_request_required
def update_fields_based_shift(request):
    shift_id = request.GET.get("shift_id")
    hx_target = request.META.get("HTTP_HX_TARGET")

    employee_ids = (
        request.GET.get("employee_id")
        if hx_target
        in [
            "attendanceUpdate",
            "attendanceRequest",
            "attendanceUpdateFormFields",
            "attendanceFormFields",
            "attendanceRequestDiv",
        ]
        else request.GET.getlist("employee_id")
    )
    employee_queryset = (
        (
            Employee.objects.get(id=employee_ids)
            if hx_target
            in [
                "attendanceUpdate",
                "attendanceUpdateFormFields",
                "attendanceRequest",
                "attendanceRequestDiv",
                "attendanceFormFields",
            ]
            else Employee.objects.filter(id__in=employee_ids)
        )
        if employee_ids
        else None
    )
    attendance_date_str = request.GET.get("attendance_date")

    attendance_date = (
        datetime.strptime(attendance_date_str, "%Y-%m-%d").date()
        if attendance_date_str
        else datetime.today().date()
    )
    day = attendance_date.strftime("%A").lower()

    schedule_today = (
        EmployeeShiftSchedule.objects.filter(shift_id=shift_id, day__day=day).first()
        if shift_id
        else None
    )

    shift_start_time = schedule_today.start_time if schedule_today else ""
    shift_end_time = schedule_today.end_time if schedule_today else ""
    minimum_hour = schedule_today.minimum_working_hour if schedule_today else "00:00"

    if schedule_today and shift_end_time < shift_start_time:
        attendance_clock_out_date = (attendance_date + timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
    else:
        attendance_clock_out_date = attendance_date.strftime("%Y-%m-%d")

    if attendance_date == datetime.today().date():
        shift_end_time = datetime.now().time()
        worked_hour = "00:00"
    else:
        worked_hour = minimum_hour

    employee = employee_queryset if isinstance(employee_queryset, Employee) else None
    minimum_hour = attendance_day_checking(str(attendance_date), minimum_hour, employee)

    initial_data = {
        "work_type_id": WorkType.find(request.GET.get("work_type_id")),
        "shift_id": shift_id,
        "employee_id": employee_queryset,
        "minimum_hour": minimum_hour,
        "attendance_date": attendance_date.strftime("%Y-%m-%d"),
        "attendance_clock_in": (
            shift_start_time.strftime("%H:%M") if shift_start_time else ""
        ),
        "attendance_clock_out": (
            shift_end_time.strftime("%H:%M") if shift_end_time else ""
        ),
        "attendance_worked_hour": worked_hour,
        "attendance_clock_in_date": attendance_date.strftime("%Y-%m-%d"),
        "attendance_clock_out_date": attendance_clock_out_date,
    }
    form = (
        AttendanceUpdateForm(initial=initial_data)
        if hx_target in ["attendanceUpdate", "attendanceUpdateFormFields"]
        else (
            NewRequestForm(initial=initial_data)
            if hx_target in ["attendanceRequest", "attendanceRequestDiv"]
            else AttendanceForm(initial=initial_data)
        )
    )
    return render(
        request,
        "attendance/attendance/update_hx_form.html",
        {"request": request, "form": form},
    )


@login_required
@hx_request_required
def update_worked_hour_field(request):
    """
    Update the worked hour field based on clock-in and clock-out times.

    This view function calculates the total worked hours for an employee
    by parsing the clock-in and clock-out dates and times from the request
    parameters. It computes the duration between the two times and formats
    the result as a string in the "HH:MM" format. The computed worked hours
    are then initialized in an AttendanceForm, which is rendered in the
    specified HTML template.
    """
    clock_in = parse_datetime(
        (
            now().strftime("%Y-%m-%d")
            if request.GET.get("create_bulk")
            else request.GET.get("attendance_clock_in_date")
        ),
        request.GET.get("attendance_clock_in"),
    )
    clock_out = parse_datetime(
        (
            now().strftime("%Y-%m-%d")
            if request.GET.get("create_bulk")
            else request.GET.get("attendance_clock_out_date")
        ),
        request.GET.get("attendance_clock_out"),
    )

    total_seconds = (
        (clock_out - clock_in).total_seconds() if clock_in and clock_out else -1
    )
    hours, minutes = divmod(max(total_seconds, 0), 3600)
    worked_hours_str = f"{int(hours):02}:{int(minutes // 60):02}"

    form = AttendanceForm(initial={"attendance_worked_hour": worked_hours_str})
    return render(
        request,
        "attendance/attendance/update_hx_form.html",
        {"request": request, "form": form},
    )


@login_required
@hx_request_required
def form_date_checking(request):
    minimum_hour = "00:00"
    attendance_date_str = request.POST.get("attendance_date")
    if not attendance_date_str:
        return JsonResponse(
            {
                "minimum_hour": minimum_hour,
            }
        )
    # Converting to date type.
    attendance_date = datetime.strptime(attendance_date_str, "%Y-%m-%d").date()

    if request.POST.get("shift_id"):
        shift_id = request.POST["shift_id"]
        day = attendance_date.strftime("%A").lower()
        schedule_today = EmployeeShiftSchedule.objects.filter(
            shift_id__id=shift_id, day__day=day
        ).first()

        # Checking the Shift is present in the selected attendance day.
        if schedule_today is not None:
            minimum_hour = schedule_today.minimum_working_hour

    attendance_date = str(attendance_date)
    minimum_hour = attendance_day_checking(attendance_date, minimum_hour)

    return JsonResponse(
        {
            "minimum_hour": minimum_hour,
        }
    )


@login_required
def user_request_one_view(request, id):
    """
    function used to view one user attendance request.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return one user attendance request view template
    """
    attendance_request = Attendance.find(id)
    if not attendance_request:
        return HorillaRedirect(
            request, message=_("No Attendance found matching the query.")
        )

    at_work_seconds = attendance_request.at_work_second
    hours_at_work = at_work_seconds // 3600
    minutes_at_work = (at_work_seconds % 3600) // 60
    at_work = "{:02}:{:02}".format(hours_at_work, minutes_at_work)

    over_time_seconds = attendance_request.overtime_second
    hours_over_time = over_time_seconds // 3600
    minutes_over_time = (over_time_seconds % 3600) // 60
    over_time = "{:02}:{:02}".format(hours_over_time, minutes_over_time)
    instance_ids_json = request.GET["instances_ids"]
    instance_ids = json.loads(instance_ids_json) if instance_ids_json else []
    previous_instance, next_instance = closest_numbers(instance_ids, id)
    return render(
        request,
        "attendance/attendance/attendance_request_one.html",
        {
            "attendance_request": attendance_request,
            "at_work": at_work,
            "over_time": over_time,
            "previous_instance": previous_instance,
            "next_instance": next_instance,
            "instance_ids_json": instance_ids_json,
            "dashboard": request.GET.get("dashboard"),
        },
    )


@login_required
@hx_request_required
def get_attendance_activities(request, obj_id):
    attendance = Attendance.find(obj_id)
    return render(
        request,
        "attendance/attendance/attendance_activites_view.html",
        context={"attendance": attendance},
    )


@login_required
@hx_request_required
def hour_attendance_select(request):
    page_number = request.GET.get("page")
    context = {}

    if page_number == "all":
        if request.user.has_perm("attendance.view_attendanceovertime"):
            employees = AttendanceOverTime.objects.all()
        else:
            employees = AttendanceOverTime.objects.filter(
                employee_id__employee_user_id=request.user
            ) | AttendanceOverTime.objects.filter(
                employee_id__employee_work_info__reporting_manager_id__employee_user_id=request.user
            )

        employee_ids = [str(emp.id) for emp in employees]
        total_count = employees.count()

        context = {"employee_ids": employee_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
@hx_request_required
def hour_attendance_select_filter(request):
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    context = {}

    if page_number == "all":
        if request.user.has_perm("attendance.view_attendanceovertime"):
            attendance_filter = AttendanceOverTimeFilter(
                filters, queryset=AttendanceOverTime.objects.all()
            )
        else:
            attendance_filter = AttendanceOverTimeFilter(
                filters,
                queryset=AttendanceOverTime.objects.filter(
                    employee_id__employee_user_id=request.user
                )
                | AttendanceOverTime.objects.filter(
                    employee_id__employee_work_info__reporting_manager_id__employee_user_id=request.user
                ),
            )

        # Get the filtered queryset
        filtered_attendance = attendance_filter.qs

        attendance_ids = [str(attendance.id) for attendance in filtered_attendance]
        total_count = filtered_attendance.count()

        context = {"employee_ids": attendance_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
@hx_request_required
def activity_attendance_select(request):
    page_number = request.GET.get("page")
    activity = AttendanceActivity.objects.all()

    if page_number == "all":
        if request.user.has_perm("attendance.view_attendanceovertime"):
            activity = AttendanceActivity.objects.all()
        else:
            activity = AttendanceActivity.objects.filter(
                employee_id=request.user.employee_get
            ) | AttendanceActivity.objects.filter(
                employee_id__employee_work_info__reporting_manager_id=request.user.employee_get
            )

    activity_ids = [str(act.id) for act in activity]
    total_count = activity.count()

    context = {"employee_ids": activity_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
@hx_request_required
def activity_attendance_select_filter(request):
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    context = {}

    if page_number == "all":
        if request.user.has_perm("attendance.view_attendanceovertime"):
            activity_filter = AttendanceActivityFilter(
                filters, queryset=AttendanceActivity.objects.all()
            )
        else:
            activity_filter = AttendanceActivityFilter(
                filters,
                queryset=AttendanceActivity.objects.filter(
                    employee_id__employee_user_id=request.user
                )
                | AttendanceActivity.objects.filter(
                    employee_id__employee_work_info__reporting_manager_id__employee_user_id=request.user
                ),
            )

        # Get the filtered queryset
        filtered_activity = activity_filter.qs

        activity_ids = [str(emp.id) for emp in filtered_activity]
        total_count = filtered_activity.count()

        context = {"employee_ids": activity_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
@hx_request_required
def latecome_attendance_select(request):
    page_number = request.GET.get("page")
    late_objs = AttendanceLateComeEarlyOut.objects.none()

    if page_number == "all":
        if request.user.has_perm("attendance.view_attendancelatecomeearlyout"):
            late_objs = AttendanceLateComeEarlyOut.objects.all()
        else:
            late_objs = AttendanceLateComeEarlyOut.objects.filter(
                employee_id__employee_user_id=request.user
            ) | AttendanceLateComeEarlyOut.objects.filter(
                employee_id__employee_work_info__reporting_manager_id__employee_user_id=request.user
            )

    late_ids = [str(emp.id) for emp in late_objs]
    total_count = late_objs.count()

    context = {"employee_ids": late_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
@hx_request_required
def latecome_attendance_select_filter(request):
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    context = {}

    if page_number == "all":
        if request.user.has_perm("attendance.view_attendancelatecomeearlyout"):
            late_filter = LateComeEarlyOutFilter(
                filters, queryset=AttendanceLateComeEarlyOut.objects.all()
            )
        else:
            late_filter = LateComeEarlyOutFilter(
                filters,
                queryset=AttendanceLateComeEarlyOut.objects.filter(
                    employee_id__employee_user_id=request.user
                )
                | AttendanceLateComeEarlyOut.objects.filter(
                    employee_id__employee_work_info__reporting_manager_id__employee_user_id=request.user
                ),
            )

        # Get the filtered queryset
        filtered_obj = late_filter.qs

        late_ids = [str(emp.id) for emp in filtered_obj]
        total_count = filtered_obj.count()

        context = {"employee_ids": late_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
@hx_request_required
@permission_required("attendance.add_gracetime")
def create_grace_time(request):
    """
    function used to create grace time .

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return grace time form template
    """
    is_default = eval_validate(request.GET.get("default"))
    form = GraceTimeForm(initial={"is_default": is_default})
    if request.method == "POST":
        form = GraceTimeForm(request.POST)
        if form.is_valid():
            cleaned_data = form.cleaned_data
            gracetime = form.save()
            shifts = cleaned_data.get("shifts")
            for shift in shifts:
                shift.grace_time_id = gracetime
                shift.save()
            messages.success(request, _("Grace time created successfully."))
            return HorillaRedirect(request)
    return render(
        request,
        "attendance/grace_time/grace_time_form.html",
        {"form": form, "is_default": is_default},
    )


@login_required
@hx_request_required
@permission_required("base.change_employeeshift")
def assign_shift(request, grace_id):
    gracetime = GraceTime.objects.filter(id=grace_id).first() if grace_id else None

    if gracetime:
        form = GraceTimeAssignForm()
        if request.method == "POST":
            form = GraceTimeAssignForm(request.POST)
            if form.is_valid():
                cleaned_data = form.cleaned_data
                shifts = cleaned_data.get("shifts")
                for shift in shifts:
                    shift.grace_time_id = gracetime
                    shift.save()
                messages.success(request, _("Grace time added to shifts successfully."))
                return HorillaRedirect(request)
        return render(
            request,
            "attendance/grace_time/assign_shift.html",
            {"form": form, "grace_time": gracetime},
        )
    messages.error(request, _("Grace time not found."))
    return HorillaRedirect(request)


@login_required
@hx_request_required
@permission_required("attendance.change_gracetime")
def update_grace_time(request, grace_id):
    """
    function used to create grace time .

    Parameters:
    request (HttpRequest): The HTTP request object.
    grace_id: id of grace time object
    Returns:
    GET : return grace time form template
    """
    grace_time = GraceTime.objects.get(id=grace_id)
    form = GraceTimeForm(instance=grace_time)
    if request.method == "POST":
        form = GraceTimeForm(request.POST, instance=grace_time)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.save()
            messages.success(request, _("Grace time updated successfully."))
            return HorillaRedirect(request)
    context = {
        "form": form,
        "grace_id": grace_id,
    }
    return render(
        request, "attendance/grace_time/grace_time_form.html", context=context
    )


@login_required
@permission_required("attendance.delete_gracetime")
def delete_grace_time(request, grace_id):
    """
    function used to delete grace time .

    Parameters:
    request (HttpRequest): The HTTP request object.
    grace_id: id of grace time object
    Returns:
    GET : return grace time form template
    """
    try:
        delete_error = False
        default_grace_time_count = GraceTime.objects.filter(is_default=True).count()
        grace_time_count = GraceTime.objects.filter(is_default=False).count()
        grace_time = GraceTime.objects.get(id=grace_id)
        grace_time_type = grace_time.is_default
        grace_time.delete()
        messages.success(request, _("Grace time deleted successfully."))
    except GraceTime.DoesNotExist:
        delete_error = True
        messages.error(request, _("Grace time does not exist."))
        return HorillaRedirect(request)
    except ProtectedError:
        delete_error = True
        messages.error(request, _("Related datas exists."))
    if delete_error:
        if grace_time_type:
            return HttpResponse(
                "<script>$('#default-containerReload').click();</script>"
            )
        return HttpResponse("<script>$('#gracetime-containerReload').click();</script>")
    elif default_grace_time_count == 1 and grace_time_type:
        return HttpResponse(
            "<script>$('#default-containerReload').click();$('.defaultGraceNav').click();</script>"
        )
    elif grace_time_count == 1 and not grace_time_type:
        return HttpResponse("<script>$('#gracetime-containerReload').click();</script>")
    return HttpResponse("<script>$('#reloadMessagesButton').click();</script>")


@login_required
@hx_request_required
@permission_required("attendance.update_gracetime")
def update_isactive_gracetime(request):
    """
    ajax function to update is active field in GraceTime.
    Args:
    - isChecked: Boolean value representing the state of grace time,
    - gracetimeId: Id of GraceTime object
    """
    isChecked = bool(request.POST.get("isChecked"))
    gracetimeId = request.POST.get("gracetimeId")
    if not gracetimeId:
        messages.error(request, _("GraceTime ID missing"))
        return HttpResponse("")

    gracetime = GraceTime.objects.filter(id=gracetimeId).first()
    if not gracetime:
        messages.error(request, _("GraceTime not found"))
        return HttpResponse("")

    gracetime.is_active = isChecked
    if isChecked:
        messages.success(request, _("Gracetime activated successfully."))
    else:
        messages.success(request, _("Gracetime deactivated successfully."))
    gracetime.save()
    return HttpResponse("")


@login_required
@hx_request_required
@permission_required("attendance.update_gracetime")
def update_gracetime_clock_in_clock_out(request):
    """
    ajax function to update is active field in grace time.
    Args:
    - isChecked: Boolean value representing the state of grace time,
    - gracetimeId: Id of PayslipAutoGenerate object
    """
    gracetimeId = request.POST.get("gracetimeId")
    if not gracetimeId:
        messages.error(request, _("GraceTime ID missing"))
        return HttpResponse("")

    isChecked = bool(request.POST.get("isChecked"))
    update = request.POST.get("update")
    gracetime = GraceTime.objects.filter(id=gracetimeId).first()
    if not gracetime:
        messages.error(request, _("GraceTime not found"))
        return HttpResponse("")

    if update == "clock_in":
        gracetime.allowed_clock_in = isChecked
        if isChecked:
            messages.success(request, _("Gracetime added to clock-in successfully."))
        else:
            messages.success(
                request, _("Gracetime removed from clock-in successfully.")
            )
    elif update == "clock_out":
        gracetime.allowed_clock_out = isChecked
        if isChecked:
            messages.success(request, _("Gracetime added to clock-out successfully."))
        else:
            messages.success(
                request, _("Gracetime removed from clock-out successfully.")
            )
    else:
        messages.error(request, _("Something went wrong ."))
        return HttpResponse("")
    gracetime.save()
    return HttpResponse("")


@login_required
@hx_request_required
def create_attendancerequest_comment(request, attendance_id):
    """
    This method renders form and template to create Attendance request comments
    """
    previous_data = request.GET.urlencode()
    attendance = Attendance.objects.filter(id=attendance_id).first()
    if not attendance:
        return HorillaRedirect(request, message=_("Attendance not found."))

    emp = request.user.employee_get
    form = AttendanceRequestCommentForm(
        initial={"employee_id": emp.id, "request_id": attendance_id}
    )

    if request.method == "POST":
        form = AttendanceRequestCommentForm(request.POST)
        if form.is_valid():
            form.instance.employee_id = emp
            form.instance.request_id = attendance
            form.save()
            comments = AttendanceRequestComment.objects.filter(
                request_id=attendance_id
            ).order_by("-created_at")
            no_comments = False
            if not comments.exists():
                no_comments = True
            form = AttendanceRequestCommentForm(
                initial={"employee_id": emp.id, "request_id": attendance_id}
            )
            messages.success(request, _("Comment added successfully!"))
            work_info = EmployeeWorkInformation.objects.filter(
                employee_id=attendance.employee_id
            )
            if work_info.exists():
                if (
                    attendance.employee_id.employee_work_info.reporting_manager_id
                    is not None
                ):
                    if request.user.employee_get.id == attendance.employee_id.id:
                        rec = (
                            attendance.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                        )
                        notify.send(
                            request.user.employee_get,
                            recipient=rec,
                            verb=f"{attendance.employee_id}'s attendance request has received a comment.",
                            verb_ar=f"تلقت طلب الحضور {attendance.employee_id} تعليقًا.",
                            verb_de=f"{attendance.employee_id}s Anfrage zur Anwesenheit hat einen Kommentar erhalten.",
                            verb_es=f"La solicitud de asistencia de {attendance.employee_id} ha recibido un comentario.",
                            verb_fr=f"La demande de présence de {attendance.employee_id} a reçu un commentaire.",
                            redirect=reverse("request-attendance-view")
                            + f"?id={attendance.id}",
                            icon="chatbox-ellipses",
                        )
                    elif (
                        request.user.employee_get.id
                        == attendance.employee_id.employee_work_info.reporting_manager_id.id
                    ):
                        rec = attendance.employee_id.employee_user_id
                        notify.send(
                            request.user.employee_get,
                            recipient=rec,
                            verb="Your attendance request has received a comment.",
                            verb_ar="تلقى طلب الحضور الخاص بك تعليقًا.",
                            verb_de="Ihr Antrag auf Anwesenheit hat einen Kommentar erhalten.",
                            verb_es="Tu solicitud de asistencia ha recibido un comentario.",
                            verb_fr="Votre demande de présence a reçu un commentaire.",
                            redirect=reverse("request-attendance-view")
                            + f"?id={attendance.id}",
                            icon="chatbox-ellipses",
                        )
                    else:
                        rec = [
                            attendance.employee_id.employee_user_id,
                            attendance.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                        ]
                        notify.send(
                            request.user.employee_get,
                            recipient=rec,
                            verb=f"{attendance.employee_id}'s attendance request has received a comment.",
                            verb_ar=f"تلقت طلب الحضور {attendance.employee_id} تعليقًا.",
                            verb_de=f"{attendance.employee_id}s Anfrage zur Anwesenheit hat einen Kommentar erhalten.",
                            verb_es=f"La solicitud de asistencia de {attendance.employee_id} ha recibido un comentario.",
                            verb_fr=f"La demande de présence de {attendance.employee_id} a reçu un commentaire.",
                            redirect=reverse("request-attendance-view")
                            + f"?id={attendance.id}",
                            icon="chatbox-ellipses",
                        )
                else:
                    rec = attendance.employee_id.employee_user_id
                    notify.send(
                        request.user.employee_get,
                        recipient=rec,
                        verb="Your attendance request has received a comment.",
                        verb_ar="تلقى طلب الحضور الخاص بك تعليقًا.",
                        verb_de="Ihr Antrag auf Anwesenheit hat einen Kommentar erhalten.",
                        verb_es="Tu solicitud de asistencia ha recibido un comentario.",
                        verb_fr="Votre demande de présence a reçu un commentaire.",
                        redirect=reverse("request-attendance-view")
                        + f"?id={attendance.id}",
                        icon="chatbox-ellipses",
                    )
            return render(
                request,
                "requests/attendance/attendance_comment.html",
                {
                    "comments": comments,
                    "no_comments": no_comments,
                    "request_id": attendance_id,
                },
            )
    return render(
        request,
        "requests/attendance/attendance_comment.html",
        {
            "form": form,
            "request_id": attendance_id,
            "pd": previous_data,
        },
    )


@login_required
@hx_request_required
def view_attendancerequest_comment(request, attendance_id):
    """
    This method is used to show Attendance request comments
    """
    comments = AttendanceRequestComment.objects.filter(
        request_id=attendance_id
    ).order_by("-created_at")
    no_comments = False
    if not comments.exists():
        no_comments = True

    if request.FILES:
        files = request.FILES.getlist("files")
        comment_id = request.GET["comment_id"]
        comment = AttendanceRequestComment.objects.get(id=comment_id)
        attachments = []
        for file in files:
            file_instance = AttendanceRequestFile()
            file_instance.file = file
            file_instance.save()
            attachments.append(file_instance)
        comment.files.add(*attachments)

    return render(
        request,
        "requests/attendance/attendance_comment.html",
        {"comments": comments, "no_comments": no_comments, "request_id": attendance_id},
    )


@login_required
@hx_request_required
def delete_attendancerequest_comment(request, comment_id):
    """
    This method is used to delete Attendance request comments
    """
    comment = AttendanceRequestComment.find(comment_id)
    if not comment:
        return HorillaRedirect(
            request, message=_("No Comment found matching the query.")
        )

    # Authorize against the comment's parent attendance request using the
    # same scope request_attendance_view() uses to list requests: the
    # requester's own record, a subordinate's record they're an authorized
    # manager over, or any record if they hold the global view permission.
    # Comment creation isn't restricted to just the owner/manager (see the
    # notify.send() branches above this view), so deletion can't be
    # narrowed to "comment author only" without blocking legitimate
    # moderation by an authorized manager/HR.
    authorized_requests = filtersubordinates(
        request=request,
        perm="attendance.view_attendance",
        queryset=Attendance.objects.filter(pk=comment.request_id_id),
    )
    authorized_requests = authorized_requests | Attendance.objects.filter(
        pk=comment.request_id_id,
        employee_id__employee_user_id=request.user,
    )
    if not authorized_requests.exists():
        return HorillaRedirect(
            request,
            message=_("You don't have permission to delete this comment."),
        )

    script = ""
    comment.delete()
    messages.success(request, _("Comment deleted successfully!"))
    return HttpResponse(script)


@login_required
@hx_request_required
def delete_comment_file(request):
    """
    Used to delete attachment
    """
    script = ""
    ids = request.GET.getlist("ids")
    AttendanceRequestFile.objects.filter(id__in=ids).delete()
    messages.success(request, _("File deleted successfully"))
    return HttpResponse(script)


@login_required
@manager_can_enter("attendance.view_attendance")
def work_records(request):
    today = date.today()
    previous_data = request.GET.urlencode()
    employee_filter_form = EmployeeFilter(request.GET)
    context = {
        "current_date": today,
        "pd": previous_data,
        "f": employee_filter_form,
    }
    return render(
        request, "attendance/work_record/work_record_view.html", context=context
    )


@login_required
@manager_can_enter("attendance.view_attendance")
@hx_request_required
def work_records_change_month(request):
    previous_data = request.GET.urlencode()
    employee_filter_form = EmployeeFilter(request.GET or None)
    # This same instance renders employee_filters.html a SECOND time here
    # (inside work_record_list.html's own Export modal) -- work_record_
    # view.html (the outer page) already renders it once for the browse
    # filter panel, and Django's default auto_id ("id_%s") has no
    # per-request salt, so both ended up emitting the exact same field
    # ids. Company/Department/etc are AJAX-loaded Select2 comboboxes now
    # (EmployeeFilter.ajax_fields), and select2 keys its own generated
    # markup off the underlying element's id -- with two elements sharing
    # one id, the browse panel's copy silently never finished
    # initializing (confirmed live: it stayed plain .oh-select-ajax while
    # the modal's copy became select2-hidden-accessible). auto_id (not
    # `prefix`) only changes the rendered id= attribute, not the field
    # `name`, so request.GET binding here and in the separate
    # work-record-export view (which builds its own fresh, unprefixed
    # EmployeeFilter(request.GET)) are both untouched.
    employee_filter_form.form.auto_id = "id_wrexport_%s"

    employees = filtersubordinatesemployeemodel(
        request, employee_filter_form.qs, "attendance.view_attendance"
    )

    all_employees = employees

    paginator_emp = Paginator(employees, 20)
    page_emp = paginator_emp.get_page(request.GET.get("page"))

    month_str = request.GET.get("month", f"{date.today().year}-{date.today().month}")
    try:
        year, month = map(int, month_str.split("-"))
    except ValueError:
        year, month = date.today().year, date.today().month

    employees = [request.user.employee_get] + list(page_emp.object_list)

    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")

    if start_date_str or end_date_str:
        # Initialize as None
        start_date = None
        end_date = None

        # Try parsing the start date
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            except ValueError:
                start_date = None

        # Try parsing the end date
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            except ValueError:
                end_date = None

        # Default end_date to today if missing or invalid
        if not end_date:
            today = date.today()
            last_day = calendar.monthrange(today.year, today.month)[1]
            end_date = date(today.year, today.month, last_day)

        # Default start_date to first day of end_date's month if missing or invalid
        if not start_date:
            start_date = date(year=end_date.year, month=end_date.month, day=1)

        # Ensure start_date is not after end_date
        if start_date > end_date:
            # Optional: raise error or swap, depending on your use case
            start_date = date(year=end_date.year, month=end_date.month, day=1)

        # Generate list of dates between start_date and end_date (inclusive)
        month_dates = []
        current_date = start_date
        while current_date <= end_date:
            month_dates.append(current_date)
            current_date += timedelta(days=1)
    else:
        month_dates = [
            datetime(year, month, day).date()
            for week in calendar.monthcalendar(year, month)
            for day in week
            if day
        ]

    work_records = WorkRecords.objects.filter(
        date__in=month_dates, employee_id__in=page_emp.object_list
    ).select_related("employee_id", "shift_id", "attendance_id")

    work_records_dict = {(wr.employee_id.id, wr.date): wr for wr in work_records}

    work_record_table = {
        employee: [
            work_records_dict.get((employee.id, current_date))
            for current_date in month_dates
        ]
        for employee in all_employees
    }

    paginated_table = list(work_record_table.items())

    paginator = Paginator(paginated_table, 20)
    page = paginator.get_page(request.GET.get("page"))

    specific_employee_holidays = {}
    specific_dates = set()
    for h in Holidays.objects.filter(
        is_specific=True, start_date__month=month, start_date__year=year
    ).prefetch_related("employees"):
        specific_dates.add(h.start_date)
        for emp in h.employees.all():
            specific_employee_holidays.setdefault(emp.pk, set()).add(h.start_date)

    context = {
        "current_month_dates_list": month_dates,
        "leave_dates": [
            d for d in monthly_leave_days(month, year) if d not in specific_dates
        ],
        "specific_employee_holidays": specific_employee_holidays,
        "data": page,
        "pd": previous_data,
        "current_date": date.today(),
        "f": employee_filter_form,
        "month_str": month_str,
    }

    return render(request, "attendance/work_record/work_record_list.html", context)


#  Matches the labels employee_filters.html already shows next to each of
#  these fields, so the "Applied Filters" summary reads the same way the
#  filter form does instead of a raw, auto-derived field name.
_FILTER_LABELS = {
    "employee_first_name": "First Name",
    "employee_last_name": "Last Name",
    "email": "Email",
    "phone": "Phone",
    "gender": "Gender",
    "country": "Country",
    "department": "Department",
    "employee_work_info__company_id": "Company",
    "employee_work_info__department_id": "Department",
    "employee_work_info__shift_id": "Shift",
    "employee_work_info__tags": "Employee Tag",
    "employee_work_info__reporting_manager_id": "Reporting Manager",
    "employee_work_info__job_position_id": "Job Position",
    "employee_work_info__work_type_id": "Work Type",
    "working_today": "Currently Working",
    "employee_user_id__groups": "Groups",
    "is_active": "Is Active",
    "employee_user_id__user_permissions": "Permissions",
}


def _build_applied_filters_summary(filterset, request_get):
    """
    Build a human readable "Field Equals Value" summary of the filters
    actually applied in request_get, for display in exported reports.
    """
    ignored_keys = {
        "month",
        "start_date",
        "end_date",
        "csrfmiddlewaretoken",
        "field",
        "orderby",
        "sortby",
        "page",
    }
    parts = []
    for key, bound_filter in filterset.filters.items():
        if key in ignored_keys or key not in request_get:
            continue
        values = [value for value in request_get.getlist(key) if value]
        if not values:
            continue
        label = _FILTER_LABELS.get(key, key.replace("_", " ").title())
        queryset = getattr(bound_filter.field, "queryset", None)
        # NullBooleanField (used for tri-state filters like "Working
        # Today") keeps its choices on the widget, not the field itself.
        choices = dict(
            getattr(bound_filter.field, "choices", None)
            or getattr(bound_filter.field.widget, "choices", [])
            or []
        )
        display_values = []
        for value in values:
            if queryset is not None:
                # Drop values that don't resolve to a real object (stale or
                # tampered-with query params) instead of showing a raw,
                # meaningless id.
                obj = queryset.filter(pk=value).first()
                if obj:
                    display_values.append(str(obj))
            elif choices:
                # Same idea for choice fields: skip values outside the
                # known choice set rather than showing them as-is. Also
                # skip NullBooleanSelect-style fields' default "Unknown"
                # option -- <select> elements always submit some value, so
                # an untouched tri-state filter (e.g. "Working Today")
                # still shows up in request.GET as its blank/default
                # choice even though the user never applied it.
                if value in choices:
                    display_text = str(choices[value])
                    if display_text.strip().lower() != "unknown":
                        display_values.append(display_text)
            else:
                display_values.append(value)
        if not display_values:
            continue
        parts.append(f"{label} Equals {', '.join(display_values)}")
    return "; ".join(parts)


@login_required
@permission_required("attendance.view_workrecords")
def work_record_export(request):

    try:
        month_str = request.GET.get("month")
        if month_str:
            year, month = map(int, month_str.split("-"))
        else:
            today = date.today()
            year, month = today.year, today.month
    except ValueError:
        return HttpResponseBadRequest("Invalid month or year parameter.")

    employees = EmployeeFilter(request.GET).qs
    records = WorkRecords.objects.filter(date__month=month, date__year=year)
    # all_date_objects = [date(year, month, day) for day in range(1, num_days + 1)]

    start_date_str = request.GET.get("start_date")
    end_date_str = request.GET.get("end_date")

    # Initialize as None
    start_date = None
    end_date = None

    # Try parsing the start date
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            start_date = None

    # Try parsing the end date
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            end_date = None

    # Default end_date to the last day of the selected month (from the
    # "month" filter) if missing or invalid, instead of always today's date
    # -- otherwise the calendar columns would ignore the selected month.
    if not end_date:
        last_day_of_month = calendar.monthrange(year, month)[1]
        end_date = date(year=year, month=month, day=last_day_of_month)

    # Default start_date to the first day of the selected month if missing
    # or invalid.
    if not start_date:
        start_date = date(year=year, month=month, day=1)

    # Ensure start_date is not after end_date
    if start_date > end_date:
        # Optional: raise error or swap, depending on your use case
        start_date = date(year=end_date.year, month=end_date.month, day=1)

    # Generate list of dates between start_date and end_date (inclusive)
    all_date_objects = []
    current_date = start_date
    while current_date <= end_date:
        all_date_objects.append(current_date)
        current_date += timedelta(days=1)
    _export_specific_dates = set(
        Holidays.objects.filter(
            is_specific=True, start_date__month=month, start_date__year=year
        ).values_list("start_date", flat=True)
    )
    leave_dates = {
        d for d in monthly_leave_days(month, year) if d not in _export_specific_dates
    }

    specific_employee_holidays = {}
    for h in Holidays.objects.filter(
        is_specific=True, start_date__month=month, start_date__year=year
    ).prefetch_related("employees"):
        for emp in h.employees.all():
            specific_employee_holidays.setdefault(emp.pk, set()).add(h.start_date)

    record_lookup = defaultdict(lambda: "ABS")
    for record in records:
        # Previously skipped records dated after today, which silently
        # dropped real, already-known statuses (e.g. an approved future
        # leave) from the lookup entirely. The day <= date.today() check
        # below already decides how each day should render; this loop just
        # needs every record available for it to consult.
        record_key = (record.employee_id, record.date)
        record_lookup[record_key] = record.work_record_type

    date_format = request.user.employee_get.get_date_format()
    format_string = settings.HORILLA_DATE_FORMATS.get(date_format)
    formatted_dates = [day.strftime(format_string) for day in all_date_objects]
    data_rows = []

    for employee in employees:
        row_data = {"Employee": employee}
        emp_specific_holidays = specific_employee_holidays.get(employee.pk, set())
        for day, formatted_day in zip(all_date_objects, formatted_dates):
            is_holiday_day = day in leave_dates or day in emp_specific_holidays
            if not is_holiday_day and day <= date.today():
                row_data[formatted_day] = record_lookup.get((employee, day), "DFT")
            else:
                data = record_lookup.get((employee, day), "")
                row_data[formatted_day] = data if data != "DFT" else ""
        data_rows.append(row_data)

    columns = ["Employee"] + formatted_dates
    df = pd.DataFrame(data_rows, columns=columns)

    export_format = request.GET.get("format", "xlsx")
    file_name = request.GET.get("file_name") or "Daily Work Status"

    if export_format == "csv":
        csv_output = io.StringIO()
        df.to_csv(csv_output, index=False)
        response = HttpResponse(csv_output.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{file_name}.csv"'
        return response

    company = getattr(request, "selected_company_instance", None)
    logo_path = getattr(company, "icon", "") if company else ""
    company_title = getattr(company, "company", "") if company else ""
    company_address = getattr(company, "address", "") if company else ""
    company_location = (
        ", ".join(
            part
            for part in [
                getattr(company, "country", ""),
                getattr(company, "state", ""),
                getattr(company, "city", ""),
            ]
            if part
        )
        if company
        else ""
    )
    company_zip = getattr(company, "zip", "") if company else ""
    date_range = f"{start_date} TO {end_date}"
    applied_filters = _build_applied_filters_summary(
        EmployeeFilter(request.GET), request.GET
    )
    # now() is UTC-internal (USE_TZ=True); localtime() converts it to the
    # active/configured TIME_ZONE before formatting, otherwise the
    # "Generated on" timestamp always shows raw UTC.
    generated_on = django_timezone.localtime(now()).strftime("%d/%m/%Y %I:%M:%S %p")

    # Row layout (0-indexed): 0-3 company block, 4 blank, 5 applied filters,
    # 6 blank, 7 generated-on, 8 blank, 9 date range, 10 data header row.
    DATA_HEADER_ROW = 10

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(
            writer, index=False, sheet_name="Sheet1", startrow=DATA_HEADER_ROW
        )  # leave space for header
        workbook = writer.book
        worksheet = writer.sheets["Sheet1"]

        total_columns = len(df.columns)

        # --- Header Formats ---
        company_format = workbook.add_format({"bold": True, "font_size": 14})
        address_format = workbook.add_format({"font_size": 10})
        filters_format = workbook.add_format(
            {
                "bold": True,
                "font_size": 10,
                "bg_color": "#FFF2CC",
                "valign": "vcenter",
            }
        )
        generated_format = workbook.add_format({"italic": True, "font_size": 9})
        date_format = workbook.add_format({"italic": True, "font_size": 11})
        data_header_format = workbook.add_format(
            {
                "bold": True,
                "font_color": "#ffffff",
                "bg_color": "#404040",
                "border": 1,
                "align": "center",
                "valign": "vcenter",
            }
        )

        # --- Company block: logo top-left, name/address beside it ---
        worksheet.write(0, 1, company_title or "", company_format)
        worksheet.write(1, 1, company_address or "", address_format)
        worksheet.write(2, 1, company_location or "", address_format)
        worksheet.write(
            3, 1, f"ZIP: {company_zip}" if company_zip else "", address_format
        )

        # Merge column A across the company block's rows so a taller logo
        # has enough room to render fully instead of being clipped to a
        # single row's height.
        worksheet.merge_range(0, 0, 2, 0, "")

        logo_full_path = (
            str(os.path.join(settings.MEDIA_ROOT, str(logo_path)))
            if logo_path
            else None
        )

        if logo_full_path and os.path.exists(logo_full_path):
            try:
                # A fixed scale factor sizes the logo relative to its own
                # source resolution, so it renders at a different size for
                # every company depending on what they uploaded. Scale
                # against the actual pixel dimensions instead, so the logo
                # always comes out at roughly the same size in the sheet.
                target_size = 60
                with Image.open(logo_full_path) as img:
                    width, height = img.size
                scale = min(target_size / width, target_size / height)
                worksheet.insert_image(
                    "A1",
                    logo_full_path,
                    {"x_scale": scale, "y_scale": scale},
                )
            except Exception as e:
                print(f"Logo insert failed: {e}")

        # --- Applied Filters banner ---
        if applied_filters:
            worksheet.merge_range(
                xl_range(5, 0, 5, total_columns - 1),
                f"Applied Filters: {applied_filters}",
                filters_format,
            )

        # --- Generated on ---
        worksheet.write(7, 0, f"Generated on: {generated_on}", generated_format)

        # --- Date range ---
        worksheet.merge_range(
            xl_range(9, 0, 9, total_columns - 1), date_range or "", date_format
        )

        # --- Data header row styling ---
        for col_idx, col in enumerate(df.columns):
            worksheet.write(DATA_HEADER_ROW, col_idx, col, data_header_format)

        # --- Cell formats for codes ---
        formats = {
            "ABS": workbook.add_format(
                {"bg_color": "#808080", "font_color": "#ffffff"}
            ),
            "FDP": workbook.add_format(
                {"bg_color": "#38c338", "font_color": "#ffffff"}
            ),
            "HDP": workbook.add_format(
                {"bg_color": "#dfdf52", "font_color": "#000000"}
            ),
            "CONF": workbook.add_format(
                {"bg_color": "#ed4c4c", "font_color": "#ffffff"}
            ),
            "DFT": workbook.add_format(
                {"bg_color": "#a8b1ff", "font_color": "#ffffff"}
            ),
        }

        # --- Apply cell formats ---
        for row_idx, row in enumerate(
            df.itertuples(index=False), start=DATA_HEADER_ROW + 1
        ):  # data starts right after the data header row
            for col_idx, cell_value in enumerate(row):
                if cell_value in formats:
                    worksheet.write(row_idx, col_idx, cell_value, formats[cell_value])

        # --- Auto column width ---
        for col_idx, col in enumerate(df.columns):
            # .max() on an empty column (no rows, e.g. filters matched no
            # employees) returns NaN, which later crashes xlsxwriter when
            # positioning the logo image against that column's width.
            content_len = df[col].astype(str).map(len).max()
            if pd.isna(content_len):
                content_len = 0
            max_len = max(content_len, len(col))
            worksheet.set_column(col_idx, col_idx, min(max_len + 2, 50))

    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{file_name}.xlsx"'
    return response


@login_required
@permission_required("attendance.add_attendancegeneralsetting")
def enable_timerunner(request):
    """
    Enable/disable Time Runner for the currently selected company, then refresh
    the navbar Check-In/Out control so the live timer appears immediately.
    When the company switcher is on "all", apply the change to every
    AttendanceGeneralSetting row (global + per-company).
    """
    company = get_session_company(request)
    enabled = "time_runner" in request.GET.keys()
    if company is None:
        # "All companies" — keep every tenant row in sync so the navbar timer
        # works no matter which company an employee belongs to.
        updated = AttendanceGeneralSetting.objects.entire().update(time_runner=enabled)
        if not updated:
            AttendanceGeneralSetting(company_id=None, time_runner=enabled).save()
    else:
        settings_qs = AttendanceGeneralSetting.objects.filter(company_id=company)
        if settings_qs.exists():
            settings_qs.update(time_runner=enabled)
        else:
            AttendanceGeneralSetting(company_id=company, time_runner=enabled).save()

    message = _("enabled") if enabled else _("disabled")
    messages.success(
        request, _("Time Runner has been {} successfully.").format(message)
    )

    # Retarget so the settings toggle form is left alone, while the navbar
    # attendance button re-renders with/without the live timer.
    response = render(
        request,
        "attendance/components/in_out_component.html",
        {"run": 1},
    )
    response["HX-Retarget"] = "#attendance-activity-container"
    response["HX-Reswap"] = "innerHTML"
    return response


@login_required
@permission_required("base.view_tracklatecomeearlyout")
def track_late_come_early_out(request):
    """
    This standalone page has been merged into the "Attendance Rule" settings
    page; direct access now redirects there.
    """
    return redirect("attendance-rule-view")


@login_required
@permission_required("base.change_tracklatecomeearlyout")
def enable_disable_tracking_late_come_early_out(request):
    """
    Enables or disables the tracking of late arrivals and early departures in attendance.
    """
    if request.method == "POST":
        from base.models import Company

        enable = bool(request.POST.get("is_enable"))
        selected_company = request.session.get("selected_company")
        if selected_company == "all":
            company = None
        else:
            company = Company.objects.filter(id=selected_company).first()

        tracking, created = TrackLateComeEarlyOut.objects.get_or_create(
            company_id=company
        )
        tracking.is_enable = enable
        tracking.save()
        message = _("enabled") if enable else _("disabled")
        messages.success(
            request, _("Tracking late come early out {} successfully").format(message)
        )
    return HorillaRedirect(request)


@login_required
def check_in_check_out_setting(request):
    """
    This standalone page has been merged into the "Attendance Rule" settings
    page; direct access now redirects there.
    """
    return redirect("attendance-rule-view")


@login_required
@hx_request_required
@permission_required("attendance.change_attendancegeneralsetting")
def enable_disable_check_in(request):
    """
    Enables or disables check-in check-out.
    """
    if request.method == "POST":
        is_checked = request.POST.get("isChecked")
        setting_id = request.POST.get("setting_Id")
        enable = bool(is_checked)

        updated = AttendanceGeneralSetting.objects.filter(id=setting_id).update(
            enable_check_in=enable
        )

        if updated:
            message = _("Check In/Check Out has been successfully {}.").format(
                _("enabled") if enable else _("disabled")
            )
            messages.success(request, message)
            if enable:
                return render(request, "attendance/components/in_out_component.html")

    return HttpResponse("")


@login_required
@permission_required("attendance.view_attendancevalidationcondition")
def time_policies_settings_view(request):
    """
    Legacy "Time Policies" settings page. Moved to the Attendance sidebar as
    its own tabbed page; redirect direct visits there.
    """
    return redirect("grace-time-view")


@login_required
@permission_required("attendance.view_attendancevalidationcondition")
def grace_time_view(request):
    """
    Legacy standalone Grace Time settings page. Moved to the Attendance
    sidebar as its own tabbed page; redirect direct visits there.
    """
    return redirect("grace-time-view")


@login_required
@permission_required("attendance.view_attendancevalidationcondition")
def grace_time_page_view(request):
    """
    Time Policies sidebar page with Grace Time and Validation Condition tabs.
    """
    return render(request, "attendance/grace_time/grace_time.html")


@login_required
@permission_required("attendance.view_attendancevalidationcondition")
def grace_time_list_tab(request):
    """
    HTMX tab body for the Grace Time tab.
    """
    return render(request, "attendance/grace_time/grace_time_table.html")


@login_required
@permission_required("attendance.view_attendancevalidationcondition")
def grace_time_validation_condition_tab(request):
    """
    HTMX tab body for the Validation Condition tab.
    """
    condition = AttendanceValidationCondition.objects.first()
    return render(
        request,
        "attendance/grace_time/validation_condition_tab.html",
        {"condition": condition},
    )


@login_required
@permission_required("attendance.view_attendancevalidationcondition")
def validation_condition_view(request):
    """
    Legacy standalone Attendance Break Point settings page. Moved to the
    Attendance sidebar as its own tabbed page; redirect direct visits there.
    """
    return redirect("grace-time-view")


@login_required
@hx_request_required
@permission_required("attendance.add_attendancevalidationcondition")
def validation_condition_create(request):
    """
    This method render a form to create attendance validation conditions,
    and create if the form is valid.
    """
    form = AttendanceValidationConditionForm()
    if request.method == "POST":
        form = AttendanceValidationConditionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Attendance Break-point settings created."))
            form = AttendanceValidationConditionForm()
    return render(
        request,
        "attendance/break_point/condition_form.html",
        {"form": form},
    )


@login_required
@hx_request_required
@permission_required("attendance.change_attendancevalidationcondition")
def validation_condition_update(request, obj_id):
    """
    This method is used to update validation condition
    Args:
        obj_id : validation condition instance id
    """
    condition = AttendanceValidationCondition.objects.get(id=obj_id)
    form = AttendanceValidationConditionForm(instance=condition)
    if request.method == "POST":
        form = AttendanceValidationConditionForm(request.POST, instance=condition)
        if form.is_valid():
            form.save()
            messages.success(request, _("Attendance Break-point settings updated."))
    return render(
        request,
        "attendance/break_point/condition_form.html",
        {"form": form, "condition": condition},
    )


@login_required
@permission_required("attendance.add_attendance")
def allowed_ips(request):
    """
    The standalone IP restriction page has been merged into the "Attendance
    Rule" settings page; direct access now redirects there. (Still used as the
    landing target after create/edit/delete of allowed IPs.)
    """
    return redirect("attendance-rule-view")


@login_required
@permission_required("attendance.add_attendance")
@require_http_methods(["POST"])
def enable_ip_restriction(request):
    """
    This function is used to toggle IP restriction for the active company.
    """
    company = get_session_company(request)
    obj, _created = AttendanceAllowedIP.objects.get_or_create(company_id=company)
    is_enabled = True if request.POST.get("is_enabled") == "on" else False
    obj.is_enabled = is_enabled
    obj.save()
    return HorillaRedirect(request)


@login_required
def attendance_rule_settings_view(request):
    """
    Merged "Attendance Rule" settings page that groups four attendance
    settings under a single header: Track Late Come & Early Out, Check In/Out,
    Biometric Attendance and IP Restriction. Each section reuses its existing
    toggle endpoint; this view only gathers the current state of each.
    """
    from base.models import BiometricAttendance

    company = get_session_company(request)

    tracking = TrackLateComeEarlyOut.objects.filter(company_id=company).first()

    setting, _created = AttendanceGeneralSetting.objects.get_or_create(
        company_id=company
    )
    attendance_general_settings = [setting]
    show_company = len(attendance_general_settings) > 1

    biometric = BiometricAttendance.objects.filter(company_id=company).first()

    allowed_ips = AttendanceAllowedIP.objects.filter(company_id=company).first()

    facedetection = None
    from django.apps import apps

    if apps.is_installed("facedetection"):
        from facedetection.models import FaceDetection

        facedetection = FaceDetection.objects.filter(company_id=company).first()

    return render(
        request,
        "attendance/settings/attendance_rule.html",
        {
            "tracking": tracking,
            "attendance_general_settings": attendance_general_settings,
            "show_company": show_company,
            "biometric": biometric,
            "allowed_ips": allowed_ips,
            "facedetection": facedetection,
        },
    )


def validate_ip_address(self, value):
    """
    This function is used to check if the provided IP is in the ipv4 or ipv6 format.

    Args:
        value: The IP address to validate
    """
    try:
        validate_ipv46_address(value)
    except ValidationError:
        raise ValidationError(_("Enter a valid IPv4 or IPv6 address."))
    return value


@login_required
@hx_request_required
@permission_required("attendance.add_attendance")
def create_allowed_ips(request):
    """
    This function is used to create the allowed IPs for the active company.
    """
    company = get_session_company(request)
    if request.method == "POST":
        form = AttendanceAllowedIPForm(request.POST)
        if form.is_valid():
            ip_addresses = form.cleaned_data.get("ip_addresses")
            obj, _created = AttendanceAllowedIP.objects.get_or_create(
                company_id=company,
                defaults={"additional_data": {"allowed_ips": []}, "is_enabled": True},
            )
            if not obj.additional_data:
                obj.additional_data = {"allowed_ips": []}
            existing_ips = set(obj.additional_data.get("allowed_ips", []))
            new_ips = set(ip_addresses)
            duplicates = new_ips & existing_ips
            if duplicates:
                messages.error(
                    request,
                    _("IP addresses already exist: %(ips)s")
                    % {"ips": ", ".join(duplicates)},
                )
            non_duplicates = new_ips - duplicates
            if non_duplicates:
                obj.additional_data["allowed_ips"] = list(existing_ips | non_duplicates)
                obj.save()
                messages.success(request, _("IP addresses saved successfully"))
            else:
                messages.info(
                    request,
                    _("All provided IP addresses are already in the allowed list."),
                )
            return HorillaRedirect(request)
    else:
        form = AttendanceAllowedIPForm()

    return render(
        request, "attendance/ip_restriction/restrict_form.html", {"form": form}
    )


@login_required
@permission_required("attendance.delete_attendance")
def delete_allowed_ips(request):
    """
    This function is used to delete the allowed ips for the active company.
    """
    company = get_session_company(request)
    try:
        ids = request.GET.getlist("id")
        obj = AttendanceAllowedIP.objects.filter(company_id=company).first()
        if obj:
            ips = (obj.additional_data or {}).get("allowed_ips", [])
            for id in ids:
                ips.pop(eval_validate(id))
            obj.additional_data["allowed_ips"] = ips
            obj.save()
        messages.success(request, _("IP address removed successfully"))
    except Exception:
        messages.error(request, _("Invalid id"))
    return redirect("allowed-ips")


@login_required
@permission_required("attendance.change_attendance")
def edit_allowed_ips(request):
    """
    This function is used to edit the allowed IPs for the active company.
    """
    company = get_session_company(request)
    obj = AttendanceAllowedIP.objects.filter(company_id=company).first()
    if not obj:
        messages.error(request, _("No allowed IPs found."))
        return redirect("allowed-ips")

    ips = (obj.additional_data or {}).get("allowed_ips", [])
    id = request.GET.get("id", request.POST.get("id"))

    try:
        id = int(id)
        if id < 0 or id >= len(ips):
            raise IndexError

        initial_ip = ips[id]
        form = AttendanceAllowedIPForm(initial={"ip_addresses": initial_ip})

        if request.method == "POST":
            form = AttendanceAllowedIPForm(request.POST)
            if form.is_valid():
                new_ip = form.cleaned_data["ip_addresses"][0]
                existing_ips = set(ips)
                if new_ip in existing_ips:
                    messages.error(request, _("IP address already exists."))
                else:
                    existing_ips.discard(initial_ip)
                    existing_ips.add(new_ip)
                    obj.additional_data["allowed_ips"] = list(existing_ips)
                    obj.save()
                    messages.success(request, _("IP address updated successfully"))
                return HorillaRedirect(request)

    except (ValueError, IndexError):
        messages.error(request, _("Invalid ID provided."))

    return render(
        request,
        "attendance/ip_restriction/restrict_form.html",
        {"form": form, "id": id},
    )

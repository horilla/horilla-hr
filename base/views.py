"""
views.py

This module is used to map url pattens with django views or methods
"""

import csv
import hmac
import json
import logging
import mimetypes
import os
import threading
import uuid
from datetime import datetime, timedelta
from email.mime.image import MIMEImage
from os import path
from urllib.parse import parse_qs, unquote, urlencode, urlparse

import pandas as pd
from dateutil import parser
from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.views import PasswordResetConfirmView, PasswordResetView
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.management import call_command
from django.core.validators import validate_ipv46_address
from django.db.models import Count, ProtectedError, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils._os import safe_join
from django.utils.decorators import method_decorator
from django.utils.html import format_html, strip_tags
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views import View
from django.views.decorators.http import require_http_methods
from django.views.generic import RedirectView, TemplateView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

from accessibility.accessibility import ACCESSBILITY_FEATURE
from accessibility.models import DefaultAccessibility
from base.backends import ConfiguredEmailBackend
from base.decorators import (
    shift_request_change_permission,
    work_type_request_change_permission,
)
from base.filters import (
    CompanyLeaveFilter,
    HolidayFilter,
    PenaltyFilter,
    RotatingShiftAssignFilters,
    RotatingShiftRequestReGroup,
    RotatingWorkTypeAssignFilter,
    RotatingWorkTypeRequestReGroup,
    ShiftRequestFilter,
    ShiftRequestReGroup,
    WorkTypeRequestFilter,
    WorkTypeRequestReGroup,
)
from base.forms import (
    AssignPermission,
    AssignUserGroup,
    AuditTagForm,
    ChangePasswordForm,
    ChangeUsernameForm,
    CompanyForm,
    CompanyLeaveForm,
    DepartmentForm,
    DriverForm,
    DynamicMailConfForm,
    DynamicMailTestForm,
    EmployeeShiftForm,
    EmployeeShiftScheduleForm,
    EmployeeShiftScheduleUpdateForm,
    EmployeeTypeForm,
    HolidayForm,
    HolidaysColumnExportForm,
    JobPositionForm,
    JobPositionMultiForm,
    JobRoleForm,
    MailTemplateForm,
    MultipleApproveConditionForm,
    PassWordResetForm,
    ResetPasswordForm,
    RotatingShiftAssign,
    RotatingShiftAssignExportForm,
    RotatingShiftAssignForm,
    RotatingShiftAssignUpdateForm,
    RotatingShiftForm,
    RotatingWorkTypeAssignExportForm,
    RotatingWorkTypeAssignForm,
    RotatingWorkTypeAssignUpdateForm,
    RotatingWorkTypeForm,
    ShiftAllocationForm,
    ShiftRequestColumnForm,
    ShiftRequestCommentForm,
    ShiftRequestForm,
    TagsForm,
    UserGroupForm,
    WorkTypeForm,
    WorkTypeRequestColumnForm,
    WorkTypeRequestCommentForm,
    WorkTypeRequestForm,
)
from base.methods import (
    check_chart_permission,
    choosesubordinates,
    closest_numbers,
    export_data,
    filtersubordinates,
    filtersubordinatesemployeemodel,
    format_date,
    generate_colors,
    generate_otp,
    get_key_instances,
    get_session_company,
    is_reportingmanager,
    paginator_qry,
    sortby,
)
from base.models import (
    WEEK_DAYS,
    WEEKS,
    AnnouncementExpire,
    BaserequestFile,
    BiometricAttendance,
    Company,
    CompanyGroupAssignment,
    CompanyLanguageSetting,
    CompanyLeaves,
    DashboardEmployeeCharts,
    DefaultExportPermission,
    Department,
    DynamicEmailConfiguration,
    DynamicPagination,
    EmployeeShift,
    EmployeeShiftSchedule,
    EmployeeType,
    Holidays,
    HorillaMailTemplate,
    IntegrationApps,
    JobPosition,
    JobRole,
    MultipleApprovalCondition,
    MultipleApprovalManagers,
    NotificationSound,
    PenaltyAccounts,
    RotatingShift,
    RotatingWorkType,
    RotatingWorkTypeAssign,
    ShiftRequest,
    ShiftRequestComment,
    Tags,
    WorkType,
    WorkTypeRequest,
    WorkTypeRequestComment,
)
from employee.filters import EmployeeFilter
from employee.forms import ActiontypeForm, EmployeeGeneralSettingPrefixForm
from employee.models import (
    Actiontype,
    DisciplinaryAction,
    Employee,
    EmployeeGeneralSetting,
    EmployeeWorkInformation,
    ProfileEditFeature,
)
from horilla.decorators import (
    any_permission_required,
    database_init_required,
    delete_permission,
    duplicate_permission,
    hx_request_required,
    login_required,
    manager_can_enter,
    permission_required,
    superuser_required,
)
from horilla.group_by import group_by_queryset
from horilla.http.response import HorillaRedirect
from horilla.menu import get_settings_menu
from horilla.methods import get_horilla_model_class, remove_dynamic_url
from horilla_audit.forms import HistoryTrackingFieldsForm
from horilla_audit.models import AccountBlockUnblock, AuditTag, HistoryTrackingFields
from horilla_auth.models import HorillaUser
from notifications.models import Notification
from notifications.signals import notify

CHARTS = [
    ("employee_work_info", _("Employee Work Info")),
    ("offline_employees", _("Offline Employees")),
    ("online_employees", _("Online Employees")),
    ("overall_leave_chart", _("Overall Leave Chart")),
    ("hired_candidates", _("Hired Candidates")),
    ("onboarding_candidates", _("Onboarding Candidates")),
    ("recruitment_analytics", _("Recruitment Analytics")),
    ("attendance_analytic", _("Attendance analytics")),
    ("hours_chart", _("Hours Chart")),
    ("employees_chart", _("Employees Chart")),
    ("department_chart", _("Department Chart")),
    ("gender_chart", _("Gender Chart")),
    ("shift_request_approve", _("Shift Request to Approve")),
    ("work_type_request_approve", _("Work Type Request to Approve")),
    ("overtime_approve", _("Overtime to Approve")),
    ("attendance_validate", _("Attendance to Validate")),
    ("leave_request_approve", _("Leave Request to Approve")),
    ("leave_allocation_approve", _("Leave Allocation to Approve")),
    ("feedback_answer", _("Feedbacks to Answer")),
    ("asset_request_approve", _("Asset Request to Approve")),
    ("objective_status", _("Objective Status")),
    ("key_result_status", _("Key Result Status")),
    ("feedback_status", _("Feedback Status")),
]

logger = logging.getLogger(__name__)


def custom404(request):
    """
    Custom 404 method
    """
    return render(request, "404.html")


# Create your views here.
def is_reportingmanger(request, instance):
    """
    If the instance have employee id field then you can use this method to know the request
    user employee is the reporting manager of the instance
    """
    manager = request.user.employee_get
    try:
        employee_work_info_manager = (
            instance.employee_id.employee_work_info.reporting_manager_id
        )
    except Exception:
        return HttpResponse("This Employee Dont Have any work information")
    return manager == employee_work_info_manager


def initialize_database_condition():
    """
    Determines if the database initialization process should be triggered.

    This function checks whether there are any users in the database. If there are no users,
    or if there are superusers without associated employees, it indicates that the database
    needs to be initialized.

    Returns:
        bool: True if the database needs to be initialized, False otherwise.
    """
    init_database = not HorillaUser.objects.exists()
    if not init_database:
        init_database = True
        superusers = HorillaUser.objects.filter(is_superuser=True)
        for user in superusers:
            if hasattr(user, "employee_get"):
                init_database = False
                break
    return init_database


def _shift_fixture_dates(file_path):
    """
    Return a date-shifted version of a JSON fixture as a string.

    All dates between 2020-01-01 and 2030-12-31 move so the fixture snapshot
    day (FIXTURE_AS_OF) becomes today. DOBs outside that window are untouched.
    Returns None if no shift is needed (delta == 0).
    """
    from base.demo_data.dates import shift_fixture_dates_text

    with open(file_path, "r", encoding="utf-8") as f:
        return shift_fixture_dates_text(f.read())


# Fixtures whose rows the trailing-6-month backfill (base/demo_data/modules/)
# redates after loading. On a non-flushed re-run, loaddata tries to restore
# each row's *original* fixture date over that already-redated state, which
# can collide with whatever other row the backfill moved onto that exact
# date (e.g. Attendance's per-employee unique_together). Clearing first
# makes the reload safe; on a --flush run the tables are already empty, so
# this is a no-op.
_RELOAD_RESET_MODELS = {
    # Order matters: models that PROTECT their FK to Attendance must be
    # cleared before Attendance itself, or the delete is refused.
    "attendance_data.json": (
        ("attendance", "AttendanceLateComeEarlyOut"),
        ("attendance", "WorkRecords"),
        ("attendance", "AttendanceActivity"),
        ("attendance", "Attendance"),
    ),
}


def reset_backfilled_rows_before_reload(fname: str) -> None:
    """Delete existing rows for models the demo backfill redates, so
    re-loading `fname` without --flush doesn't collide with that state."""
    for app_label, model_name in _RELOAD_RESET_MODELS.get(fname, ()):
        model = apps.get_model(app_label, model_name)
        model._base_manager.all().delete()


DEMO_PAYROLL_GROUP_PREFIX = "Demo Payroll M-"
DEMO_PAYROLL_RENAMED_PREFIX = "Demo Payroll - "


def normalize_demo_payslips():
    """
    Re-anchor demo payslip periods onto real calendar months.

    Demo payslips ship tagged as ``Demo Payroll M-<n>``, where ``n`` counts months
    back from the current one. Fixture date shifting moves every date by a fixed
    number of days, which cannot keep month-long periods aligned to month
    boundaries, so the period, the dates embedded in ``pay_head_data`` and the batch
    label are recomputed from that tag instead. Returns the number of payslips
    updated.

    A row's group_name is renamed to ``Demo Payroll - <Mon Year>`` below for a
    human-readable label -- but that also matches the seeder's own
    "already covered" check in payroll_trend.py, so this must keep
    recognizing renamed rows on every future call too (re-deriving the
    offset from start_date instead of the now-gone "M-<n>" tag), or a
    dynamically-created (non-fixture) backfilled payslip would only ever
    get re-anchored once and then drift stale forever.

    Also runs the app's own ``expire_contract()`` scheduled task inline:
    fixture loaddata bypasses both Contract.save() and the scheduler, so a
    demo Contract shipped "active" with a now-past contract_end_date (after
    the fixture date shift) would otherwise stay contradictorily "active"
    until the real scheduler happens to run.
    """
    if not apps.is_installed("payroll"):
        return 0

    from payroll.models.models import Payslip
    from payroll.scheduler import expire_contract

    expire_contract()

    today = datetime.today().date()
    updated = 0

    # _base_manager skips the company scoping that would hide other companies' rows.
    payslips = Payslip._base_manager.filter(
        Q(group_name__startswith=DEMO_PAYROLL_GROUP_PREFIX)
        | Q(group_name__startswith=DEMO_PAYROLL_RENAMED_PREFIX)
    )
    for payslip in payslips:
        if payslip.group_name.startswith(DEMO_PAYROLL_GROUP_PREFIX):
            try:
                offset = int(payslip.group_name.rsplit("M-", 1)[1])
            except (IndexError, ValueError):
                continue
        else:
            # Already renamed on a prior run -- the "M-<n>" tag is gone, so
            # re-derive the same offset from how far start_date's month
            # already sits from today's.
            offset = (today.year - payslip.start_date.year) * 12 + (
                today.month - payslip.start_date.month
            )

        year, month = today.year, today.month - offset
        while month < 1:
            month += 12
            year -= 1
        # Day 28 exists in every month, so each period stays inside its own month.
        start = datetime(year, month, 1).date()
        end = datetime(year, month, 28).date()

        pay_head_data = payslip.pay_head_data
        if isinstance(pay_head_data, dict):
            pay_head_data["start_date"] = start.strftime("%Y-%m-%d")
            pay_head_data["end_date"] = end.strftime("%Y-%m-%d")
            pay_head_data["range"] = (
                f"{start.strftime('%b %d %Y')} - {end.strftime('%b %d %Y')}"
            )

        status = payslip.status
        # M-0 is the current, still-open month -- a payslip can't already be
        # "paid" or "confirmed" for a period that hasn't closed yet.
        if offset == 0 and status in ("paid", "confirmed"):
            status = "review_ongoing"

        Payslip._base_manager.filter(pk=payslip.pk).update(
            start_date=start,
            end_date=end,
            pay_head_data=pay_head_data,
            group_name=f"{DEMO_PAYROLL_RENAMED_PREFIX}{start.strftime('%b %Y')}",
            status=status,
        )
        updated += 1

    return updated


def load_demo_database(request):
    if initialize_database_condition():
        if request.method == "POST":
            if request.POST.get("load_data_password") == settings.DB_INIT_PASSWORD:
                import tempfile

                from base.demo_data.fixtures import demo_fixture_files

                data_files = demo_fixture_files()

                # Load all data files, shifting dates relative to today
                from pathlib import Path as _Path

                load_dir_path = _Path(settings.BASE_DIR) / "load_data"
                try:
                    from base.demo_data.media import copy_demo_media

                    copy_demo_media(load_dir_path)
                except Exception:
                    pass

                for file in data_files:
                    file_path = path.join(settings.BASE_DIR, "load_data", file)
                    tmp = None
                    try:
                        reset_backfilled_rows_before_reload(file)
                        shifted = _shift_fixture_dates(file_path)
                        if shifted is not None:
                            suffix = path.splitext(file)[1]
                            with tempfile.NamedTemporaryFile(
                                mode="w",
                                suffix=suffix,
                                delete=False,
                                encoding="utf-8",
                            ) as tmp_f:
                                tmp_f.write(shifted)
                                tmp = tmp_f.name
                            call_command("loaddata", tmp)
                        else:
                            call_command("loaddata", file_path)
                    except Exception as e:
                        messages.error(
                            request, _("An error occured : %(e)s") % {"e": e}
                        )
                    finally:
                        if tmp and path.exists(tmp):
                            os.remove(tmp)

                try:
                    from base.demo_data import run_enterprise_demo_seeder

                    run_enterprise_demo_seeder(
                        load_dir=load_dir_path,
                        copy_media=False,
                        scrub_side_files=True,
                    )
                except Exception as e:
                    # The seeder is one long sequence of ~25 steps -- an
                    # exception here could come from any of them, and every
                    # step after the failing one silently never runs. Log
                    # the full traceback so whoever reloads the demo can
                    # actually find which step broke, instead of only ever
                    # seeing this generic toast.
                    logger.exception("Enterprise demo seeder failed partway through")
                    messages.warning(
                        request,
                        _("Enterprise demo seeder could not finish: %(error)s")
                        % {"error": e},
                    )

                normalize_demo_payslips()

                messages.success(request, _("Database loaded successfully."))
                try:
                    from base.demo_roles import assign_demo_user_groups

                    assigned = assign_demo_user_groups()
                    if assigned:
                        messages.info(
                            request,
                            _("Assigned demo roles to %(count)s employee memberships.")
                            % {"count": assigned},
                        )
                except Exception as e:
                    messages.warning(
                        request,
                        _("Demo roles could not be assigned: %(error)s") % {"error": e},
                    )
            else:
                messages.error(request, _("Database Authentication Failed"))
        return redirect(home)
    return redirect("/")


def initialize_database(request):
    """
    Handles the database initialization process via a user interface.

    Parameters:
        request (HttpRequest): The request object.

    Returns:
        HttpResponse: The rendered HTML template or a redirect response.
    """
    if initialize_database_condition():
        if request.method == "POST":
            password = request.POST.get("password")
            if settings.DB_INIT_PASSWORD == password:
                request.session["db_init_verified"] = True
                return redirect(initialize_database_user)
            else:
                messages.warning(
                    request,
                    _("The password you entered is incorrect. Please try again."),
                )
                return HorillaRedirect(request)
        return render(request, "initialize_database/horilla_user.html")
    else:
        return redirect("login")


@database_init_required
@hx_request_required
def initialize_database_user(request):
    """
    Handles the user creation step during database initialization.

    Parameters:
        request (HttpRequest): The request object.

    Returns:
        HttpResponse: The rendered HTML template for company creation or user signup.
    """
    if request.method == "POST":
        form_data = request.POST
        username = form_data.get("username")
        password = form_data.get("password")
        confirm_password = form_data.get("confirm_password")
        if password != confirm_password:
            return render(request, "initialize_database/horilla_user_signup.html")
        first_name = form_data.get("firstname")
        last_name = form_data.get("lastname")
        badge_id = form_data.get("badge_id")
        email = form_data.get("email")
        phone = form_data.get("phone")
        user = HorillaUser.objects.filter(username=username).first()
        if user and not hasattr(user, "employee_get"):
            user.delete()
        user = HorillaUser.objects.create_superuser(
            username=username, email=email, password=password
        )
        employee = Employee()
        employee.employee_user_id = user
        employee.badge_id = badge_id
        employee.employee_first_name = first_name
        employee.employee_last_name = last_name
        employee.email = email
        employee.phone = phone
        employee.save()
        request.session.pop("db_init_verified", None)
        user = authenticate(request, username=username, password=password)
        login(request, user)
        return render(
            request,
            "initialize_database/horilla_company.html",
            {"form": CompanyForm(initial={"hq": True})},
        )
    return render(request, "initialize_database/horilla_user_signup.html")


@superuser_required
@hx_request_required
def initialize_database_company(request):
    """
    Handles the company creation step during database initialization.

    Parameters:
        request (HttpRequest): The request object.

    Returns:
        HttpResponse: The rendered HTML template for department creation or company creation.
    """
    form = CompanyForm()
    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES)
        if form.is_valid():
            company = form.save()
            try:
                employee = request.user.employee_get
                employee.employee_work_info.company_id = company
                employee.employee_work_info.save()
            except Exception:
                logger.exception(
                    "initialize database: could not attach creator to company"
                )
            return render(
                request,
                "initialize_database/horilla_department.html",
                {"form": DepartmentForm(initial={"company_id": company})},
            )
    return render(request, "initialize_database/horilla_company.html", {"form": form})


@superuser_required
@hx_request_required
def initialize_database_department(request):
    """
    Handles the department creation step during database initialization.

    Parameters:
        request (HttpRequest): The request object.

    Returns:
        HttpResponse: The rendered HTML template for department creation.
    """
    departments = Department.objects.all()
    form = DepartmentForm(initial={"company_id": Company.objects.first()})
    if request.method == "POST":
        form = DepartmentForm(request.POST)
        if form.is_valid():
            company = form.cleaned_data.get("company_id")
            form.save()
            form = DepartmentForm(initial={"company_id": company})
    return render(
        request,
        "initialize_database/horilla_department_form.html",
        {"form": form, "departments": departments},
    )


@superuser_required
@hx_request_required
def initialize_department_edit(request, obj_id):
    """
    Handles editing of an existing department during database initialization.

    Parameters:
        request (HttpRequest): The request object.
        obj_id (int): The ID of the department to be edited.

    Returns:
        HttpResponse: The rendered HTML template for department editing.
    """
    department = Department.find(obj_id)
    form = DepartmentForm(instance=department)
    if request.method == "POST":
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            company = form.cleaned_data.get("company_id")
            form.save()
            return render(
                request,
                "initialize_database/horilla_department_form.html",
                {
                    "form": DepartmentForm(initial={"company_id": company}),
                    "departments": Department.objects.all(),
                },
            )
    return render(
        request,
        "initialize_database/horilla_department_form.html",
        {
            "form": form,
            "department": department,
            "departments": Department.objects.all(),
        },
    )


@superuser_required
@hx_request_required
def initialize_department_delete(request, obj_id):
    """
    Handles the deletion of an existing department during database initialization.

    Parameters:
        request (HttpRequest): The request object.
        obj_id (int): The ID of the department to be deleted.

    Returns:
        HttpResponse: A redirect response to the department creation page.
    """
    department = Department.find(obj_id)
    department.delete() if department else None
    return redirect(initialize_database_department)


@superuser_required
@hx_request_required
def initialize_database_job_position(request):
    """
    Handles the job position creation step during database initialization.

    Parameters:
        request (HttpRequest): The request object.

    Returns:
        HttpResponse: The rendered HTML template for job position creation.
    """
    company = Company.objects.first()
    form = JobPositionMultiForm(initial={"company_id": company})
    if request.method == "POST":
        form = JobPositionMultiForm(request.POST)
        if form.is_valid():
            form.save()
            form = JobPositionMultiForm(initial={"company_id": Company.objects.first()})
        return render(
            request,
            "initialize_database/horilla_job_position_form.html",
            {
                "form": form,
                "job_positions": JobPosition.objects.all(),
                "company": company,
            },
        )
    return render(
        request,
        "initialize_database/horilla_job_position.html",
        {"form": form, "job_positions": JobPosition.objects.all(), "company": company},
    )


@superuser_required
@hx_request_required
def initialize_job_position_edit(request, obj_id):
    """
    Handles editing of an existing job position during database initialization.

    Parameters:
        request (HttpRequest): The request object.
        obj_id (int): The ID of the job position to be edited.

    Returns:
        HttpResponse: The rendered HTML template for job position editing.
    """
    company = Company.objects.first()
    job_position = JobPosition.find(obj_id)
    form = JobPositionForm(instance=job_position)
    if request.method == "POST":
        form = JobPositionForm(request.POST, instance=job_position)
        if form.is_valid():
            form.save()
            return render(
                request,
                "initialize_database/horilla_job_position_form.html",
                {
                    "form": JobPositionMultiForm(initial={"company_id": company}),
                    "job_positions": JobPosition.objects.all(),
                    "company": company,
                },
            )
    return render(
        request,
        "initialize_database/horilla_job_position_form.html",
        {
            "form": form,
            "job_position": job_position,
            "job_positions": JobPosition.objects.all(),
            "company": company,
        },
    )


@superuser_required
@hx_request_required
def initialize_job_position_delete(request, obj_id):
    """
    Handles the deletion of an existing job position during database initialization.

    Parameters:
        request (HttpRequest): The request object.
        obj_id (int): The ID of the job position to be deleting.

    Returns:
        HttpResponse: The rendered HTML template for job position creating.
    """
    company = Company.objects.first()
    job_position = JobPosition.find(obj_id)
    job_position.delete() if job_position else None
    return render(
        request,
        "initialize_database/horilla_job_position_form.html",
        {
            "form": JobPositionMultiForm(
                initial={"company_id": Company.objects.first()}
            ),
            "job_positions": JobPosition.objects.all(),
            "company": company,
        },
    )


def login_user(request):
    """
    Handles user login and authentication.
    """
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        next_url = request.GET.get("next", "/")
        query_params = request.GET.dict()
        query_params.pop("next", None)
        params = urlencode(query_params)

        user = authenticate(request, username=username, password=password)

        if not user:
            # One message for every failure mode. Distinguishing "blocked" from
            # "invalid" told an unauthenticated caller which usernames exist,
            # which is what turns a password-guessing attempt into a targeted
            # one. Blocked users are told to contact their administrator via
            # the same text rather than being confirmed as real accounts.
            messages.error(request, _("Invalid username or password."))
            return redirect("login")

        employee = getattr(user, "employee_get", None)
        if employee is None:
            messages.error(
                request,
                _("An employee related to this user's credentials does not exist."),
            )
            return redirect("login")
        if not employee.is_active:
            messages.warning(
                request,
                _(
                    "This user is archived. Please contact the manager for more information."
                ),
            )
            return redirect("login")

        login(request, user)

        messages.success(request, _("Login successful."))

        # Ensure `next_url` is a safe local URL
        if not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}
        ):
            next_url = "/"

        if params:
            next_url += f"?{params}"
        return redirect(next_url)

    return render(
        request, "login.html", {"initialize_database": initialize_database_condition()}
    )


def include_employee_instance(request, form):
    """
    This method is used to include the employee instance to the form
    Args:
        form: django forms instance
    """
    queryset = form.fields["employee_id"].queryset
    employee = Employee.objects.filter(employee_user_id=request.user)
    if employee.first() is not None:
        if queryset.filter(id=employee.first().id).first() is None:
            # queryset = queryset | employee
            queryset = queryset.distinct() | employee.distinct()
            form.fields["employee_id"].queryset = queryset
    return form


def reset_send_success(request):
    return render(request, "reset_send.html")


class HorillaPasswordResetView(PasswordResetView):
    """
    Horilla View for Reset Password
    """

    template_name = "forgot_password.html"
    form_class = PassWordResetForm
    success_url = reverse_lazy("reset-send-success")

    def form_valid(self, form):
        email_backend = ConfiguredEmailBackend()
        default = "base.backends.ConfiguredEmailBackend"
        is_default_backend = True
        EMAIL_BACKEND = getattr(settings, "EMAIL_BACKEND", "")
        if EMAIL_BACKEND and default != EMAIL_BACKEND:
            is_default_backend = False
        if is_default_backend and not email_backend.configuration:
            messages.error(self.request, _("Primary mail server is not configured"))
            return redirect("forgot-password")

        username = form.cleaned_data["email"]
        user = HorillaUser.objects.filter(username=username).first()
        if user:
            opts = {
                "use_https": self.request.is_secure(),
                "token_generator": self.token_generator,
                "from_email": email_backend.dynamic_from_email_with_display_name,
                "email_template_name": self.email_template_name,
                "subject_template_name": self.subject_template_name,
                "request": self.request,
                "html_email_template_name": self.html_email_template_name,
                "extra_email_context": self.extra_email_context,
            }
            form.save(**opts)
            if self.request.user.is_authenticated:
                messages.success(
                    self.request, _("Password reset link sent successfully")
                )
                return HorillaRedirect(self.request)

        return redirect(reverse_lazy("reset-send-success"))


class EmployeePasswordResetView(PasswordResetView):
    """
    Horilla View for Employee Reset Password
    """

    template_name = "forgot_password.html"
    form_class = PassWordResetForm

    def form_valid(self, form):
        try:
            email_backend = ConfiguredEmailBackend()
            default = "base.backends.ConfiguredEmailBackend"
            is_default_backend = True
            EMAIL_BACKEND = getattr(settings, "EMAIL_BACKEND", "")
            if EMAIL_BACKEND and default != EMAIL_BACKEND:
                is_default_backend = False
            if is_default_backend and not email_backend.configuration:
                messages.error(self.request, _("Primary mail server is not configured"))
                return HorillaRedirect(self.request)

            username = form.cleaned_data["email"]
            user = HorillaUser.objects.filter(username=username).first()
            if user:
                opts = {
                    "use_https": self.request.is_secure(),
                    "token_generator": self.token_generator,
                    "from_email": email_backend.dynamic_from_email_with_display_name,
                    "email_template_name": self.email_template_name,
                    "subject_template_name": self.subject_template_name,
                    "request": self.request,
                    "html_email_template_name": self.html_email_template_name,
                    "extra_email_context": self.extra_email_context,
                }
                form.save(**opts)
            messages.success(
                self.request,
                _("If your account exists, a password reset link has been sent"),
            )
            return HorillaRedirect(self.request)

        except Exception as e:
            messages.error(self.request, _("Something went wrong....."))
            return HorillaRedirect(self.request)


setattr(PasswordResetConfirmView, "template_name", "reset_password.html")
setattr(PasswordResetConfirmView, "form_class", ResetPasswordForm)
setattr(PasswordResetConfirmView, "success_url", "/")


@login_required
def change_password(request):
    """
    Handles the password change process for a logged-in user.

    Args:
        request (HttpRequest): The HTTP request object containing metadata about
                               the request and user.

    Returns:
        HttpResponse: Renders the password change form if the request method is GET or
                      the form is invalid. If the form is valid and the password is changed
                      successfully, the page reloads with a success message.
    """
    user = request.user
    form = ChangePasswordForm(user=user)
    if request.method == "POST":
        form = ChangePasswordForm(user, request.POST)
        if form.is_valid():
            new_password = form.cleaned_data["new_password"]
            user.set_password(new_password)
            user.save()
            user = authenticate(request, username=user.username, password=new_password)
            if hasattr(user, "is_new_employee"):
                user.is_new_employee = False
                user.save()
            login(request, user)
            messages.success(request, _("Password changed successfully"))
            return HttpResponse("<script>window.location.href='/';</script>")
        return render(request, "base/auth/password_change_form.html", {"form": form})

    return render(request, "base/auth/password_change.html", {"form": form})


@login_required
def change_username(request):
    """
    Handles the username change process for a logged-in user.

    Args:
        request (HttpRequest): The HTTP request object containing metadata about
                               the request and user.

    Returns:
        HttpResponse: Renders the username change form if the request method is GET or
                      the form is invalid. If the form is valid and the password is changed
                      successfully, the page reloads with a success message.
    """
    user = request.user
    form = ChangeUsernameForm(user=user, initial={"old_username": user.username})
    if request.method == "POST":
        form = ChangeUsernameForm(user, request.POST)
        if form.is_valid():
            new_username = form.cleaned_data["username"]
            user.username = new_username
            user.save()
            if hasattr(user, "is_new_employee"):
                user.is_new_employee = False
                user.save()
            messages.success(request, _("Username changed successfully"))
            return HttpResponse("<script>window.location.href='/';</script>")
        return render(request, "base/auth/username_change_form.html", {"form": form})

    return render(request, "base/auth/username_change.html", {"form": form})


def two_factor_auth(request):
    """
    function to handle two-factor authentication for users.
    """
    # request.session["otp_code"] = None
    try:
        otp = get_otp(request)
    except Exception:
        logger.exception("two_factor_auth: could not read OTP from session")
        otp = None

    if request.method == "POST":
        user_otp = request.POST.get("otp") or ""
        if otp is not None and hmac.compare_digest(str(user_otp), str(otp)):
            request.session["otp_code"] = None
            request.session["otp_code_timestamp"] = None
            request.session["otp_attempts"] = 0
            request.session["otp_code_verified"] = True
            request.session.save()
            messages.success(request, _("OTP verified successfully."))
            return redirect("/")
        elif otp is None:
            messages.error(request, _("OTP expired. Please request a new one."))
            return render(request, "base/auth/two_factor_auth.html")
        else:
            # A six-digit code with a ten-minute life is guessable at network
            # speed; a handful of misses burns the code and forces a resend.
            attempts = request.session.get("otp_attempts", 0) + 1
            request.session["otp_attempts"] = attempts
            if attempts >= 5:
                request.session["otp_code"] = None
                request.session["otp_code_timestamp"] = None
                request.session["otp_attempts"] = 0
                request.session.save()
                messages.error(
                    request, _("Too many incorrect attempts. Request a new OTP.")
                )
            else:
                messages.error(request, _("Invalid OTP."))
            return render(request, "base/auth/two_factor_auth.html")

    if not settings.TWO_FACTORS_AUTHENTICATION:
        return redirect("/")

    if otp is None:
        send_otp(request)
    return render(request, "base/auth/two_factor_auth.html")


def send_otp(request):
    """
    Function to send OTP to the user's email address.
    It generates a new OTP code, stores it in the session, and sends it via email.
    """
    employee = getattr(getattr(request, "user", None), "employee_get", None)
    if not employee:
        return redirect("/login/")

    email = employee.get_mail()
    email_backend = ConfiguredEmailBackend()
    display_email_name = email_backend.dynamic_from_email_with_display_name

    otp_code = set_otp(request)
    email = EmailMessage(
        subject="Your OTP Code",
        body=f"Your OTP code is {otp_code}",
        from_email=display_email_name,
        to=[email],
    )
    thread = threading.Thread(target=email.send)
    thread.start()

    return redirect("two-factor")


def set_otp(request):
    """
    Function to set the OTP code in the session.
    Generates a new OTP code, stores it in the session, and sets a timestamp for expiration.
    """

    otp_code = generate_otp()
    request.session["otp_code"] = otp_code
    request.session["otp_code_timestamp"] = timezone.now().timestamp()
    request.session["otp_code_verified"] = False
    request.session.save()
    return otp_code


def get_otp(request):
    """
    Function to retrieve the OTP code from the session.
    Checks if the OTP code has expired (10 minutes) and clears it if so.
    """
    created_at = request.session.get("otp_code_timestamp", 0)
    current_time = timezone.now().timestamp()

    if current_time - created_at > 600:
        request.session["otp_code"] = None
        request.session["otp_code_timestamp"] = None
        request.session.save()
        return None
    else:
        return request.session.get("otp_code")


def logout_user(request):
    """
    This method used to logout the user
    """
    if request.user:
        logout(request)
    response = HttpResponse()
    response.content = """
        <script>
            localStorage.clear();
        </script>
        <meta http-equiv="refresh" content="0;url=/login/">
    """

    return response


@login_required
def toggle_theme(request):
    if request.method == "POST":
        current = request.session.get("theme")

        request.session["theme"] = "light" if current == "dark" else "dark"

        return HttpResponse(status=204)

    return HttpResponse(status=400)


class Workinfo:
    def __init__(self, employee) -> None:
        self.employee_work_info = employee
        self.employee_id = employee
        self.id = employee.id
        pass


@login_required
def home(request):
    """
    Role-aware home: employees → ESS; managers/HR/leadership → analytics dashboard.
    """
    from base.dashboard_roles import can_see_analytics_home, resolve_home_role

    if can_see_analytics_home(resolve_home_role(request)):
        return redirect("dashboard")
    return redirect("ess-dashboard")


@login_required
@manager_can_enter("employee.view_employeeworkinformation")
def employee_workinfo_complete(request):

    employees_with_pending = []

    # List of field names to focus on
    fields_to_focus = [
        "job_position_id",
        "department_id",
        "work_type_id",
        "employee_type_id",
        "job_role_id",
        "reporting_manager_id",
        "company_id",
        "location",
        "email",
        "mobile",
        "shift_id",
        "date_joining",
        "contract_end_date",
        "basic_salary",
        "salary_hour",
    ]
    search = request.GET.get("search", "")
    employees_workinfos = filtersubordinates(
        request,
        queryset=EmployeeWorkInformation.objects.filter(
            employee_id__employee_first_name__icontains=search,
            employee_id__is_active=True,
        ),
        perm="employee.view_employeeworkinformation",
    )
    for employee in employees_workinfos:
        completed_field_count = sum(
            1
            for field_name in fields_to_focus
            if getattr(employee, field_name) is not None
        )
        if completed_field_count < 15:
            # Create a dictionary with employee information and pending field count
            percent = f"{((completed_field_count / 15) * 100):.1f}"
            employee_info = {
                "employee": employee,
                "completed_field_count": percent,
            }
            employees_with_pending.append(employee_info)
        else:
            pass

    emps = filtersubordinatesemployeemodel(
        request,
        Employee.objects.filter(employee_work_info__isnull=True),
        perm="employee.view_employeeworkinformation",
    )
    for emp in emps:
        employees_with_pending.insert(
            0,
            {
                "employee": Workinfo(employee=emp),
                "completed_field_count": "0",
            },
        )

    employees_with_pending.sort(key=lambda x: float(x["completed_field_count"]))

    employees_with_pending = paginator_qry(
        employees_with_pending, request.GET.get("page")
    )

    return render(
        request,
        "work_info_complete.html",
        {"employees_with_pending": employees_with_pending},
    )


@login_required
def common_settings(request):
    """
    This method is used to render setting page template
    """
    return render(request, "settings.html")


class SettingsView(LoginRequiredMixin, RedirectView):
    """
    Settings page — has no content of its own ({% block settings %} is
    always empty), so redirect to System Preferences by default.
    """

    pattern_name = "system-preferences-view"


def _permission_app_label(app_name):
    """
    Human label for permission UI module nav.
    Uses AppConfig.verbose_name and drops a leading "Horilla" product prefix.
    """
    import re

    from django.apps import apps as django_apps

    try:
        label = str(django_apps.get_app_config(app_name).verbose_name)
    except LookupError:
        label = app_name.replace("_", " ")

    label = re.sub(r"(?i)^horilla[\s_\-]*", "", label).strip()
    label = label.replace("_", " ").strip()
    if not label:
        label = app_name.replace("_", " ")
    # Title-case only fully lowercase labels (keep "Theme Manager", "LDAP", etc.)
    if label == label.lower():
        label = label.title()
    # Sidebar-friendly short label for Django auth
    if app_name == "auth":
        label = "Auth"
    return label


def _custom_permission_label(perm_name, model_verbose):
    """
    Short UI label for a custom Meta permission.
    "Approve Shift Request" + model "Shift Request" -> "Approve".
    """
    label = str(perm_name).strip()
    verbose = str(model_verbose).strip()
    if verbose and label.lower().endswith(verbose.lower()):
        label = label[: -len(verbose)].strip(" -–:")
    return label or str(perm_name)


def _build_permission_matrix():
    """Shared permission matrix context for group/employee permission UIs."""
    permissions = []
    no_permission_models = settings.NO_PERMISSION_MODALS
    for app_name in settings.APPS:
        app_models = []
        for model in get_models_in_app(app_name):
            if model._meta.model_name in no_permission_models:
                continue
            verbose = model._meta.verbose_name.capitalize()
            custom_permissions = [
                {
                    "codename": codename,
                    "name": str(name),
                    "label": _custom_permission_label(name, model._meta.verbose_name),
                }
                for codename, name in (model._meta.permissions or ())
            ]
            app_models.append(
                {
                    "verbose_name": verbose,
                    "model_name": model._meta.model_name,
                    "custom_permissions": custom_permissions,
                }
            )
        permissions.append(
            {
                "app": _permission_app_label(app_name),
                "app_models": app_models,
                "has_custom_permissions": any(
                    m["custom_permissions"] for m in app_models
                ),
            }
        )
    return permissions, no_permission_models


def _user_groups_queryset(search=""):
    """Lightweight group list with annotated counts (no heavy prefetches)."""
    groups = Group.objects.annotate(
        member_count=Count("user", distinct=True),
        perm_count=Count("permissions", distinct=True),
    ).order_by("name")
    if search:
        groups = groups.filter(name__icontains=search)
    return groups


@login_required
@hx_request_required
@superuser_required
def user_group_table(request):
    """
    Group create form (HTMX) — loaded on demand when opening Create modal.
    """
    permissions, no_permission_models = _build_permission_matrix()
    form = UserGroupForm()
    if request.method == "POST":
        form = UserGroupForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Role created."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/auth/group_assign.html",
        {
            "permissions": permissions,
            "form": form,
            "no_permission_models": no_permission_models,
        },
    )


@login_required
@superuser_required
def user_group(request):
    """
    Combined Roles and Permissions settings page.

    Roles are the default tab. The permissions tab keeps the existing direct
    employee-permission workflow on the same settings screen.
    """
    from base.auth_backends import company_scoped_active

    active_tab = "permissions" if request.GET.get("tab") == "permissions" else "roles"
    context = {
        "active_tab": active_tab,
        "no_permission_models": settings.NO_PERMISSION_MODALS,
    }
    if active_tab == "permissions":
        employees = Employee.objects.filter(
            Q(employee_user_id__user_permissions__isnull=False)
            | Q(employee_user_id__groups__isnull=False)
        ).distinct()
        permissions, no_permission_models = _build_permission_matrix()
        context.update(
            {
                "employees": paginator_qry(employees, request.GET.get("page")),
                "permissions": permissions,
                "no_permission_models": no_permission_models,
                "show_assign": True,
                "can_edit_permissions": True,
                "company_scoped": company_scoped_active(),
            }
        )
    else:
        context.update(
            {
                "form": UserGroupForm(),
                "groups": paginator_qry(
                    _user_groups_queryset(), request.GET.get("page")
                ),
                "permissions": [],
            }
        )
    return render(
        request,
        "base/auth/roles_permissions.html",
        context,
    )


@login_required
@hx_request_required
@superuser_required
def user_group_search(request):
    """
    Search / paginate user groups (list rows only).
    """
    search = str(request.GET.get("search") or "")
    groups = _user_groups_queryset(search=search)
    return render(
        request,
        "base/auth/group_lines.html",
        {
            "groups": paginator_qry(groups, request.GET.get("page")),
            "pd": request.GET.urlencode(),
            "permissions": [],
            "no_permission_models": settings.NO_PERMISSION_MODALS,
        },
    )


def _group_detail_context(group):
    """
    Build the context for the members + permissions panel of a single group.
    Shared by the lazy-load view and any action that needs to refresh it
    in place (e.g. removing a member).
    """
    from base.auth_backends import company_scoped_active

    company_scoped = company_scoped_active()
    member_companies = {}
    distinct_member_companies = []
    if company_scoped:
        company_names = set()
        for user_id, company_id, company_name in CompanyGroupAssignment.objects.filter(
            group=group
        ).values_list("user_id", "company_id", "company__company"):
            member_companies.setdefault(user_id, []).append(
                {"id": company_id, "name": company_name}
            )
            company_names.add(company_name)
        distinct_member_companies = sorted(company_names)
    members = [
        {"user": user, "companies": member_companies.get(user.id, [])}
        for user in group.user_set.all()
    ]
    permissions, no_permission_models = _build_permission_matrix()
    return {
        "group": group,
        "member_count": group.user_set.count(),
        "members": members,
        "member_companies": distinct_member_companies,
        "permissions": permissions,
        "no_permission_models": no_permission_models,
        "company_scoped": company_scoped,
    }


@login_required
@hx_request_required
@superuser_required
def user_group_detail(request, obj_id):
    """
    Lazy-loaded members + permissions panel for a single group.
    """
    group = get_object_or_404(
        Group.objects.prefetch_related(
            "permissions", "user_set", "user_set__employee_get"
        ),
        id=obj_id,
    )
    return render(request, "base/auth/group_detail.html", _group_detail_context(group))


@login_required
@require_http_methods(["POST"])
@superuser_required
def update_group_permission(
    request,
):
    """
    This method is used to remove user permission.
    """
    group_id = request.POST.get("id")
    instance = Group.objects.filter(id=group_id).first()
    if not instance:
        messages.error(request, _("Group not found"))
        return JsonResponse({"message": "Group not found", "type": "danger"})
    form = UserGroupForm(request.POST, instance=instance)
    if form.is_valid():
        form.save()
        messages.success(request, _("Updated the permissions"))
        return JsonResponse({})
    if request.POST.get("name_update"):
        name = request.POST["name"]
        if len(name) > 3:
            instance.name = name
            instance.save()
            messages.success(request, _("Name updated"))
            return JsonResponse({"message": "Name updated", "type": "success"})
        messages.info(request, _("At least 4 characters required"))
        return JsonResponse({})
    perms = form.cleaned_data.get("permissions")
    if not perms:
        instance.permissions.clear()
        messages.info(request, _("All permission cleared"))
        return JsonResponse({})
    messages.error(request, _("Something went wrong"))
    return JsonResponse({"message": "Something went wrong", "type": "danger"})


@login_required
@hx_request_required
@superuser_required
def group_assign(request):
    """
    This method is used to assign user group to the users.
    """
    from base.auth_backends import company_scoped_active, get_assigned_company_ids

    group_id = request.GET.get("group") or request.POST.get("group")
    mode = (request.GET.get("mode") or request.POST.get("mode") or "add").lower()
    if mode not in ("add", "edit"):
        mode = "add"
    target_employee_id = request.GET.get("target_employee") or request.POST.get(
        "target_employee"
    )
    if not group_id:
        return HorillaRedirect(request, message=_("Required parameters are missing"))
    group = Group.objects.filter(id=group_id).first()
    if not group:
        return HorillaRedirect(request, message=_("Group not found"))

    grantable_ids = None
    if (
        company_scoped_active()
        and request.user.is_authenticated
        and not request.user.is_superuser
    ):
        grantable_ids = get_assigned_company_ids(request.user)

    if grantable_ids is not None:
        current_employees = Employee.objects.filter(
            is_active=True,
            employee_user_id__company_group_assignments__group=group,
            employee_user_id__company_group_assignments__company_id__in=grantable_ids,
        ).distinct()
        company_qry = {"id__in": grantable_ids}
    else:
        current_employees = Employee.objects.filter(
            employee_user_id__groups__id=group_id, is_active=True
        )
        company_qry = {}

    if mode == "edit" and target_employee_id:
        # Scoped to one employee: only their own companies are pre-filled,
        # so saving never touches any other member's assignments.
        initial_employees = list(current_employees.filter(id=target_employee_id))
        initial_companies = Company.objects.filter(
            group_assignments__group=group,
            group_assignments__user__employee_get__id=target_employee_id,
            **company_qry,
        ).distinct()
    else:
        # Add starts empty; bulk Edit pre-fills current members so their
        # (shared) companies can be updated.
        initial_employees = list(current_employees) if mode == "edit" else []
        initial_companies = Company.objects.filter(
            group_assignments__group=group, **company_qry
        ).distinct()

    form = AssignUserGroup(
        initial={
            "group": group_id,
            "employee": initial_employees,
            "companies": list(initial_companies),
        }
    )
    if request.POST:
        form = AssignUserGroup(request.POST)
        if form.is_valid():
            form.save(mode=mode, target_employee_id=target_employee_id)
            messages.success(
                request,
                (
                    _("Role members updated.")
                    if mode == "edit"
                    else _("Role members added.")
                ),
            )
            return HorillaRedirect(request)
    target_employee = None
    if target_employee_id:
        target_employee = Employee.objects.filter(id=target_employee_id).first()
    return render(
        request,
        "base/auth/group_user_assign.html",
        {
            "form": form,
            "group_id": group_id,
            "group": group,
            "member_count": current_employees.count(),
            "assign_mode": mode,
            "target_employee_id": target_employee_id,
            "target_employee": target_employee,
        },
    )


@login_required
@hx_request_required
@superuser_required
def group_assign_view(request):
    """
    This method is used to search the user groups
    """
    search = ""
    if request.GET.get("search") is not None:
        search = request.GET.get("search")
    groups = Group.objects.filter(name__icontains=search)
    previous_data = request.GET.urlencode()
    return render(
        request,
        "base/auth/group_assign_view.html",
        {"groups": paginator_qry(groups, request.GET.get("page")), "pd": previous_data},
    )


@login_required
@superuser_required
def user_group_view(request):
    """
    This method is used to render template for view all groups
    """
    search = ""
    if request.GET.get("search") is not None:
        search = request.GET["search"]
    user_group = Group.objects.filter()
    return render(request, "base/auth/group_assign.html", {"data": user_group})


@login_required
@superuser_required
@require_http_methods(["POST"])
def user_group_permission_remove(request, pid, gid):
    """
    This method is used to remove permission from group.
    args:
        pid: permission id
        gid: group id
    """
    group = Group.objects.get(id=1)
    permission = Permission.objects.get(id=2)
    group.permissions.remove(permission)
    return HorillaRedirect(request)


@login_required
@superuser_required
@require_http_methods(["POST"])
def group_remove_user(request, uid, gid):
    """
    Remove a user from a group — entirely, or (with a ``company_id``
    parameter) only for one company. When the last company assignment is
    removed the user leaves the group's M2M too (union sync).
    args:
        uid: user instance id
        gid: group instance id
    """
    group = Group.objects.filter(id=gid).first()
    user = HorillaUser.objects.filter(id=uid).first()
    company_id = request.POST.get("company_id") or request.GET.get("company_id")
    fully_removed = True
    if group and user:
        if company_id:
            CompanyGroupAssignment.objects.filter(
                user=user, group=group, company_id=company_id
            ).delete()
            CompanyGroupAssignment.sync_user_group_membership(user, group)
            fully_removed = not user.groups.filter(id=group.id).exists()
            if fully_removed:
                messages.success(request, _("Employee removed from the group."))
            else:
                messages.success(
                    request, _("Company removed from the employee's assignment.")
                )
        else:
            group.user_set.remove(user)
            CompanyGroupAssignment.objects.filter(user=user, group=group).delete()
            messages.success(request, _("Employee removed from the group."))
    else:
        messages.error(request, _("Unable to remove employee from the group."))
    if request.headers.get("HX-Request"):
        if group:
            return render(
                request, "base/auth/group_detail.html", _group_detail_context(group)
            )
        return HttpResponse("")
    return HorillaRedirect(request)


@login_required
@delete_permission()
@require_http_methods(["POST", "DELETE"])
def object_delete(request, obj_id, **kwargs):
    """
    Handles the deletion of an object instance from the database.

    Args:
        request (HttpRequest): The HTTP request object containing metadata about
                               the request and user.
        obj_id (int): The ID of the object to be deleted.
        **kwargs: Additional keyword arguments including:
            - model (Model): The Django model class to which the object belongs.
            - redirect_path (str): The URL path to redirect to after deletion.
            - superuser_only (bool): When True, only Django superusers may delete.
    Returns:
        HttpResponse: Redirects to the specified redirect_path or reloads the
                      previous page. In case of a ProtectedError, it shows an error
                      message indicating that the object is in use.
    """
    if kwargs.get("superuser_only") and not request.user.is_superuser:
        from horilla.methods import handle_no_permission

        return handle_no_permission(request)

    model = kwargs.get("model")
    redirect_path = kwargs.get("redirect_path")
    delete_error = False
    try:
        instance = model.objects.get(id=obj_id)
        instance.delete()
        messages.success(
            request, _("The {} has been deleted successfully.").format(instance)
        )
    except model.DoesNotExist:
        delete_error = True
        messages.error(request, _("{} not found.").format(model._meta.verbose_name))
    except ProtectedError as e:
        model_verbose_names_set = set()
        for obj in e.protected_objects:
            model_verbose_names_set.add(_(obj._meta.verbose_name.capitalize()))

        model_names_str = ", ".join(model_verbose_names_set)
        delete_error = True
        messages.error(
            request,
            _("This {} is already in use for {}.").format(instance, model_names_str),
        ),

    if apps.is_installed("pms") and redirect_path == "/pms/filter-key-result/":
        KeyResult = get_horilla_model_class(app_label="pms", model="keyresult")
        key_results = KeyResult.objects.all()
        if key_results.exists():
            previous_data = request.GET.urlencode()
            redirect_path = redirect_path + "?" + previous_data
            return redirect(redirect_path)
        else:
            return HorillaRedirect(request)

    if (
        redirect_path
        and request.headers.get("HX-Request") == "true"
        and (
            redirect_path.startswith("/employee/document-request-view")
            or redirect_path.startswith("/employee/requests/")
        )
    ):
        referer = request.META.get("HTTP_REFERER", "")
        if (
            "/employee/document-request-view" in referer
            or "/employee/requests/" in referer
        ):
            qs = urlparse(referer).query
            filter_url = reverse("document-request-filter-view")
            if qs:
                filter_url = f"{filter_url}?{qs}"
            inner = format_html(
                '<span hx-get="{}" hx-target="#view-container" hx-swap="innerHTML" '
                'hx-trigger="load"></span>',
                filter_url,
            )
            script = (
                "<script>"
                "document.querySelectorAll('.oh-modal--show').forEach(function (m) {"
                "m.classList.remove('oh-modal--show');"
                "});"
                "document.getElementById('reloadMessagesButton')?.click();"
                "</script>"
            )
            return HttpResponse(str(inner) + script)

    if redirect_path:
        previous_data = request.GET.urlencode()
        redirect_path = redirect_path + "?" + previous_data
        return redirect(redirect_path)
    elif kwargs.get("HttpResponse"):
        if delete_error:
            return_part = "<script>window.location.reload()</script>"
        elif kwargs.get("HttpResponse") is True:
            return_part = ""
        else:
            return_part = kwargs.get("HttpResponse")
        return HttpResponse(f"{return_part}")
    else:
        return HorillaRedirect(request)


@login_required
@hx_request_required
@duplicate_permission()
def object_duplicate(request, obj_id, **kwargs):
    """
    Handles the duplication of an object instance in the database.

    Args:
        request (HttpRequest): The HTTP request object containing metadata about
                               the request and user.
        obj_id (int): The ID of the object to be duplicated.
        **kwargs: Additional keyword arguments including:
            - model (Model): The Django model class to which the object belongs.
            - form (Form): The Django form class used to handle the object data.
            - template (str): The template to render for the duplication process.
            - form_name (str, optional): The name to use for the form in the template context.

    Returns:
        HttpResponse: Renders the duplication form on GET requests and, on successful
                      POST, reloads the page after saving the duplicated object.
    """
    model = kwargs["model"]
    form_class = kwargs["form"]
    template = kwargs["template"]
    try:
        original_object = model.objects.get(id=obj_id)
    except model.DoesNotExist:
        messages.error(
            request,
            _("%(model__meta_verbose_name)s object does not exist.")
            % {"model__meta_verbose_name": model._meta.verbose_name},
        )
        return HorillaRedirect(request)

    form = form_class(instance=original_object)
    search_words = (
        form.get_template_language() if hasattr(form, "get_template_language") else None
    )
    if request.method == "GET":
        for field_name, field in form.fields.items():
            if isinstance(field, forms.CharField):
                if field.initial:
                    initial_value = field.initial
                else:
                    initial_value = f"{form.initial.get(field_name, '')} (copy)"
                form.initial[field_name] = initial_value
                form.fields[field_name].initial = initial_value
        if hasattr(form.instance, "id"):
            form.instance.id = None

    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            new_object = form.save(commit=False)
            new_object.id = None
            new_object.save()
            return HorillaRedirect(request)
    context = {
        kwargs.get("form_name", "form"): form,
        "obj_id": obj_id,
        "duplicate": True,
        "searchWords": search_words,
    }
    return render(request, template, context)


@login_required
@hx_request_required
def add_remove_dynamic_fields(request, **kwargs):
    """
    Handles the dynamic addition and removal of form fields in a Django form.

    Args:
        request (HttpRequest): The HTTP request object containing metadata about
                               the request and user.
        **kwargs: Additional keyword arguments including:
            - model (Model): The Django model class used for `ModelChoiceField`.
            - form_class (Form): The Django form class to which dynamic fields will be added.
            - template (str): The template used to render the newly added field.
            - empty_label (str, optional): The label to show for empty choices in
                a `ModelChoiceField`.
            - field_name_pre (str): The prefix for the dynamically generated field names.
            - field_type (str, optional): The type of field to add, either "character"
                or "model_choice".

    Returns:
        HttpResponse: Returns the HTML for the newly added field, rendered in the context of the
                      specified template. If the request is not POST or if no valid HTMX target
                      is provided, it returns an empty HTTP response.
    """
    if request.method == "POST":
        model = kwargs["model"]
        form_class = kwargs["form_class"]
        template = kwargs["template"]
        empty_label = kwargs.get("empty_label")
        field_name_pre = kwargs["field_name_pre"]
        field_type = kwargs.get("field_type")
        hx_target = request.META.get("HTTP_HX_TARGET")

        if hx_target:
            field_counts = int(hx_target.split("_")[-1]) + 1
            next_hx_target = f"{hx_target.rsplit('_', 1)[0]}_{field_counts}"
            form = form_class()
            field_name = f"{field_name_pre}{field_counts}"
            if field_type and field_type == "character":
                form.fields[field_name] = forms.CharField(
                    widget=forms.TextInput(
                        attrs={
                            "class": "oh-input w-100",
                            "name": field_name,
                            "id": f"id_{field_name}",
                            # .oh-input carries a spacing margin-bottom (theme
                            # v1_styles.css) that skews the flex row's vertical
                            # centering against the delete button beside it.
                            "style": "margin-bottom: 0",
                        }
                    ),
                    required=False,
                )
            else:
                form.fields[field_name] = forms.ModelChoiceField(
                    queryset=model.objects.all(),
                    widget=forms.Select(
                        attrs={
                            "class": "oh-select oh-select-2 mb-3 w-100",
                            "name": field_name,
                            "id": f"id_{field_name}",
                        }
                    ),
                    required=False,
                    empty_label=empty_label,
                )

            context = {
                "field_counts": field_counts,
                "field_html": form[field_name].as_widget(),
                "current_hx_target": hx_target,
                "next_hx_target": next_hx_target,
            }

            field_html = render_to_string(template, context)
            return HttpResponse(field_html)
    return HttpResponse()


@login_required
@permission_required("base.view_dynamicemailconfiguration")
def mail_server_conf(request):
    mail_servers = DynamicEmailConfiguration.objects.all()
    primary_mail_not_exist = True
    if DynamicEmailConfiguration.objects.filter(is_primary=True).exists():
        primary_mail_not_exist = False
    return render(
        request,
        "base/mail_server/mail_server.html",
        {
            "mail_servers": mail_servers,
            "primary_mail_not_exist": primary_mail_not_exist,
        },
    )


@login_required
@hx_request_required
@permission_required("base.view_dynamicemailconfiguration")
def mail_server_test_email(request):
    instance_id = request.GET.get("instance_id")
    white_labelling = getattr(settings, "WHITE_LABELLING", False)
    image_path = path.join(settings.STATIC_ROOT, "images/ui/horilla-logo.png")
    company_name = "Horilla"

    if white_labelling:
        hq = Company.objects.filter(hq=True).last()
        try:
            company = (
                request.user.employee_get.get_company()
                if request.user.employee_get.get_company()
                else hq
            )
        except:
            company = hq

        if company:
            company_name = company.company
            image_path = path.join(settings.MEDIA_ROOT, company.icon.name)

    form = DynamicMailTestForm()
    if request.method == "POST":
        form = DynamicMailTestForm(request.POST)
        if form.is_valid():
            email_to = form.cleaned_data["to_email"]
            subject = _("Test mail from Horilla")

            # HTML content
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; margin: 0; padding: 0;">
                    <table align="center" width="600" cellpadding="0" cellspacing="0" border="0" style="border: 1px solid #e0e0e0; border-radius: 10px; overflow: hidden;">
                        <tr>
                            <td align="center" bgcolor="#4CAF50" style="padding: 20px 0;">
                                <h1 style="color: #ffffff; margin: 0;">{company_name}</h1>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 20px;">
                                <h3 style="color: #4CAF50;">Email tested successfully</h3>
                                <b><p style="font-size: 14px;">Hi,<br>
                                    This email is being sent as part of mail sever testing from {company_name}.</p></b>
                                <img src="cid:unique_image_id" alt="Test Image" style="width: 200px; height: auto; margin: 20px 0;">
                            </td>
                        </tr>
                        <tr>
                            <td bgcolor="#f0f0f0" style="padding: 10px; text-align: center;">
                                <p style="font-size: 12px; color: black;">&copy; {datetime.today().year} {company_name}</p>
                            </td>
                        </tr>
                    </table>
                </body>
            </html>
            """

            # Plain text content (fallback for email clients that do not support HTML)
            text_content = strip_tags(html_content)

            email_backend = ConfiguredEmailBackend()
            emailconfig = DynamicEmailConfiguration.objects.filter(
                id=instance_id
            ).first()
            email_backend.configuration = emailconfig

            try:
                msg = EmailMultiAlternatives(
                    subject,
                    text_content,
                    email_backend.dynamic_from_email_with_display_name,
                    [email_to],
                    connection=email_backend,
                )
                msg.attach_alternative(html_content, "text/html")

                with open(image_path, "rb") as img:
                    msg_img = MIMEImage(img.read())
                    msg_img.add_header("Content-ID", "<unique_image_id>")
                    msg.attach(msg_img)

                msg.send()
            except Exception as e:
                messages.error(request, " ".join([_("Something went wrong :"), str(e)]))
                return HorillaRedirect(request)

            messages.success(request, _("Mail sent successfully"))
            return HorillaRedirect(request)
    return render(
        request,
        "base/mail_server/form_email_test.html",
        {"form": form, "instance_id": instance_id},
    )


@login_required
@permission_required("base.delete_dynamicemailconfiguration")
def mail_server_delete(request):
    """
    This method is used to delete mail server
    """
    id = request.GET.get("ids")

    if not id:
        return HorillaRedirect(request, message=_("Missing required parameter"))

    emailconfig = DynamicEmailConfiguration.objects.filter(id=id).first()
    if not emailconfig:
        return HorillaRedirect(
            request, message=_("Mail server configuration not found")
        )

    # Prevent deleting last remaining config
    total_count = DynamicEmailConfiguration.objects.count()
    if total_count <= 1:
        messages.warning(
            request,
            _("You have only 1 Mail server configuration that can't be deleted"),
        )
        return HorillaRedirect(request)

    # Prevent deleting primary
    if emailconfig.is_primary:
        mails = DynamicEmailConfiguration.objects.all().exclude(is_primary=True)
        return render(
            request,
            "base/mail_server/replace_mail.html",
            {
                "mails": mails,
                "title": _("Can't Delete"),
            },
        )

    emailconfig.delete()
    messages.success(request, _("Mail server configuration deleted"))

    return HorillaRedirect(request)


@login_required
def replace_primary_mail(request):
    """
    This method is used to replace primary mail server
    """
    emailconfig_id = request.POST.get("replace_mail")
    email_config = DynamicEmailConfiguration.find(emailconfig_id)
    if not email_config:
        messages.error(request, _("Mail server configuration not found"))
        return redirect("mail-server-conf")

    email_config.is_primary = True
    email_config.save()
    DynamicEmailConfiguration.objects.filter(is_primary=True).first().delete()
    messages.success(request, _("Primary Mail server configuration replaced"))
    return redirect("mail-server-conf")


@login_required
@hx_request_required
@permission_required("base.add_dynamicemailconfiguration")
def mail_server_create_or_update(request):
    instance_id = request.GET.get("instance_id")
    instance = None
    if instance_id:
        instance = DynamicEmailConfiguration.objects.filter(id=instance_id).first()
    form = DynamicMailConfForm(instance=instance)
    if request.method == "POST":
        form = DynamicMailConfForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            return HorillaRedirect(request)
    return render(
        request, "base/mail_server/form.html", {"form": form, "instance": instance}
    )


@login_required
@permission_required("base.view_horillamailtemplate")
def mail_templates_settings_view(request):
    """
    Mail Template settings page. Migrated from the Configuration menu into
    Settings > Mail.
    """
    templates = HorillaMailTemplate.objects.all()
    form = MailTemplateForm()
    searchWords = form.get_template_language()
    return render(
        request,
        "base/settings/mail_templates.html",
        {"templates": templates, "form": form, "searchWords": searchWords},
    )


@login_required
@permission_required("base.view_horillamailtemplate")
def view_mail_templates(request):
    """
    Legacy standalone Mail Templates page. Migrated into Settings > Mail;
    redirect direct visits to the settings page.
    """
    return redirect("mail-templates-view")


@login_required
@hx_request_required
@permission_required("base.change_horillamailtemplate")
def view_mail_template(request, obj_id):
    """
    This method is used to display the template/form to edit
    """
    template = HorillaMailTemplate.objects.filter(id=obj_id).first()
    if not template:
        messages.error(request, _("Template not found."))
        return HorillaRedirect(request)
    form = MailTemplateForm(instance=template)
    searchWords = form.get_template_language()
    if request.method == "POST":
        form = MailTemplateForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, _("Template updated"))
            return HorillaRedirect(request)

    return render(
        request,
        "mail/htmx/form.html",
        {"form": form, "duplicate": False, "searchWords": searchWords},
    )


@login_required
@hx_request_required
@permission_required("base.add_horillamailtemplate")
def create_mail_templates(request):
    """
    This method is used to create offerletter template
    """
    form = MailTemplateForm()
    searchWords = form.get_template_language()

    if request.method == "POST":
        form = MailTemplateForm(request.POST)
        if form.is_valid():
            instance = form.save()
            instance.save()
            messages.success(request, _("Template created"))
            return HorillaRedirect(request)

    return render(
        request,
        "mail/htmx/form.html",
        {"form": form, "duplicate": False, "searchWords": searchWords},
    )


@login_required
@permission_required("base.delete_horillamailtemplate")
def delete_mail_templates(request):
    ids = request.GET.getlist("ids")
    result = HorillaMailTemplate.objects.filter(id__in=ids).delete()
    messages.success(request, _("Template deleted"))
    return redirect(view_mail_templates)


@login_required
@hx_request_required
@permission_required("base.add_company")
def company_create(request):
    """
    This method render template and form to create company and save if the form is valid
    """

    form = CompanyForm()
    companies = Company.objects.all()
    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES)

        if form.is_valid():
            form.save()

            messages.success(request, _("Company has been created successfully!"))
            return HorillaRedirect(request)

    return render(
        request,
        "base/company/company_form.html",
        {"form": form, "companies": companies},
    )


@login_required
@permission_required("base.view_company")
def company_view(request):
    """
    This method used to view created companies
    """
    companies = Company.objects.all()
    return render(
        request,
        "base/company/company.html",
        {"companies": companies, "model": Company()},
    )


@login_required
@hx_request_required
@permission_required("base.change_company")
def company_update(request, id, **kwargs):
    """
    This method is used to update company
    args:
        id : company instance id

    """
    company = Company.objects.filter(id=id).first()
    if not company:
        messages.error(request, _("Company not found."))
        return HorillaRedirect(request)
    form = CompanyForm(instance=company)
    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, _("Company updated"))
            return HorillaRedirect(request)
    return render(
        request, "base/company/company_form.html", {"form": form, "company": company}
    )


@login_required
@hx_request_required
@permission_required("base.add_department")
def department_create(request):
    """
    This method renders form and template to create department
    """

    form = DepartmentForm()
    if request.method == "POST":
        form = DepartmentForm(request.POST)
        if form.is_valid():
            form.save()
            form = DepartmentForm()
            messages.success(request, _("Department has been created successfully!"))
            return HorillaRedirect(request)
    return render(
        request,
        "base/department/department_form.html",
        {
            "form": form,
        },
    )


@login_required
@permission_required("base.view_department")
def department_view(request):
    """
    This method view department
    """
    departments = Department.objects.all()
    return render(
        request,
        "base/department/department.html",
        {
            "departments": departments,
        },
    )


@login_required
@hx_request_required
@permission_required("base.change_department")
def department_update(request, id, **kwargs):
    """
    This method is used to update department
    args:
        id : department instance id
    """
    department = Department.find(id)
    form = DepartmentForm(instance=department)
    if request.method == "POST":
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            form.save()
            messages.success(request, _("Department updated."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/department/department_form.html",
        {"form": form, "department": department},
    )


@login_required
@permission_required("base.view_jobposition")
def job_position(request):
    """
    This method is used to view job position
    """

    departments = Department.objects.all()
    jobs = False
    if JobPosition.objects.exists():
        jobs = True
    form = JobPositionForm()
    if request.method == "POST":
        form = JobPositionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Job Position has been created successfully!"))
    return render(
        request,
        "base/job_position/job_position.html",
        {"form": form, "departments": departments, "jobs": jobs},
    )


@login_required
@hx_request_required
@permission_required("base.add_jobposition")
def job_position_creation(request):
    """
    This method is used to create job position
    """
    dynamic = request.GET.get("dynamic") if request.GET.get("dynamic") else ""
    form = JobPositionMultiForm()
    if request.method == "POST":
        form = JobPositionMultiForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Job Position has been created successfully!"))
            return HorillaRedirect(request)
    return render(
        request,
        "base/job_position/job_position_form.html",
        {
            "form": form,
            "dynamic": dynamic,
        },
    )


@login_required
@hx_request_required
@permission_required("base.change_jobposition")
def job_position_update(request, id, **kwargs):
    """
    This method is used to update job position
    args:
        id : job position instance id

    """
    job_position = JobPosition.find(id)
    form = JobPositionForm(instance=job_position)
    if request.method == "POST":
        form = JobPositionForm(request.POST, instance=job_position)
        if form.is_valid():
            form.save(commit=True)
            messages.success(request, _("Job position updated."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/job_position/job_position_form.html",
        {"form": form, "job_position": job_position},
    )


@login_required
@hx_request_required
@permission_required("base.add_jobrole")
def job_role_create(request):
    """
    This method is used to create job role.
    """
    dynamic = request.GET.get("dynamic")
    form = JobRoleForm()
    if request.method == "POST":
        form = JobRoleForm(request.POST)
        if form.instance.pk and form.is_valid():
            form.save(commit=True)
            messages.success(request, _("Job role has been created successfully!"))
        elif (
            not form.instance.pk
            and form.data.getlist("job_position_id")
            and form.data.get("job_role")
        ):
            form.save(commit=True)
            messages.success(request, _("Job role has been created successfully!"))
            return HorillaRedirect(request)

    return render(
        request,
        "base/job_role/job_role_form.html",
        {
            "form": form,
            "dynamic": dynamic,
        },
    )


@login_required
@permission_required("base.view_jobrole")
def job_role_view(request):
    """
    This method is used to view job role.
    """

    jobs = JobPosition.objects.all()
    job_role = False
    if JobRole.objects.exists():
        job_role = True

    return render(
        request,
        "base/job_role/job_role.html",
        {"job_positions": jobs, "job_role": job_role},
    )


@login_required
@hx_request_required
@permission_required("base.change_jobrole")
def job_role_update(request, id, **kwargs):
    """
    This method is used to update job role instance
    args:
        id  : job role instance id

    """

    job_role = JobRole.find(id)
    form = JobRoleForm(instance=job_role)
    if request.method == "POST":
        form = JobRoleForm(request.POST, instance=job_role)
        if form.is_valid():
            form.save(commit=True)
            messages.success(request, _("Job role updated."))
            return HorillaRedirect(request)

    return render(
        request,
        "base/job_role/job_role_form.html",
        {
            "form": form,
            "job_role": job_role,
        },
    )


@login_required
@hx_request_required
@permission_required("base.add_worktype")
def work_type_create(request):
    """
    This method is used to create work type
    """
    dynamic = request.GET.get("dynamic")
    from base.auth_backends import resolve_company_id_for_new_record

    company_id = resolve_company_id_for_new_record(request)
    company = Company.objects.filter(id=company_id).first() if company_id else None
    initial = {"company_id": [company] if company else []}
    form = WorkTypeForm(initial=initial)
    work_types = WorkType.objects.all()
    if request.method == "POST":
        form = WorkTypeForm(request.POST)
        if form.is_valid():
            form.save()
            form = WorkTypeForm(initial=initial)
            messages.success(request, _("Work Type has been created successfully!"))
            return HorillaRedirect(request)

    return render(
        request,
        "base/work_type/work_type_form.html",
        {"form": form, "work_types": work_types, "dynamic": dynamic},
    )


@login_required
@permission_required("base.view_worktype")
def work_type_view(request):
    """
    This method is used to view work type
    """
    selected_company = request.session.get("selected_company")
    work_types = WorkType.objects.all()
    if selected_company and selected_company != "all":
        work_types = work_types.filter(company_id__id=selected_company)
    return render(
        request,
        "base/work_type/work_type.html",
        {"work_types": work_types},
    )


@login_required
@hx_request_required
@permission_required("base.change_worktype")
def work_type_update(request, id, **kwargs):
    """
    This method is used to update work type instance
    args:
        id : work type instance id

    """

    work_type = WorkType.find(id)
    form = WorkTypeForm(instance=work_type)
    if request.method == "POST":
        form = WorkTypeForm(request.POST, instance=work_type)
        if form.is_valid():
            form.save()
            messages.success(request, _("Work type updated."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/work_type/work_type_form.html",
        {"form": form, "work_type": work_type},
    )


@login_required
@hx_request_required
@permission_required("base.add_rotatingworktype")
def rotating_work_type_create(request):
    """
    This method is used to create rotating work type   .
    """

    form = RotatingWorkTypeForm()
    if request.method == "POST":
        form = RotatingWorkTypeForm(request.POST)
        if form.is_valid():
            form.save()
            form = RotatingWorkTypeForm()
            messages.success(request, _("Rotating work type created."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/rotating_work_type/htmx/rotating_work_type_form.html",
        {"form": form, "rwork_type": RotatingWorkType.objects.all()},
    )


@login_required
@permission_required("base.view_rotatingworktype")
def rotating_work_type_view(request):
    """
    This method is used to view rotating work type   .
    """

    return render(
        request,
        "base/rotating_work_type/rotating_work_type.html",
        {"rwork_type": RotatingWorkType.objects.all()},
    )


@login_required
@hx_request_required
@permission_required("base.change_rotatingworktype")
def rotating_work_type_update(request, id, **kwargs):
    """
    This method is used to update rotating work type instance.
    args:
        id : rotating work type instance id

    """

    rotating_work_type = RotatingWorkType.find(id)
    form = RotatingWorkTypeForm(instance=rotating_work_type)
    if request.method == "POST":
        form = RotatingWorkTypeForm(request.POST, instance=rotating_work_type)
        if form.is_valid():
            form.save()
            messages.success(request, _("Rotating work type updated."))
            return HorillaRedirect(request)

    return render(
        request,
        "base/rotating_work_type/htmx/rotating_work_type_form.html",
        {"form": form, "r_type": rotating_work_type},
    )


@login_required
@manager_can_enter("base.view_rotatingworktypeassign")
def rotating_work_type_assign(request):
    """
    This method is used to assign rotating work type to employee users
    """

    filter = RotatingWorkTypeAssignFilter(
        queryset=RotatingWorkTypeAssign.objects.filter(is_active=True)
    )
    rwork_all = RotatingWorkTypeAssign.objects.all()
    rwork_type_assign = filter.qs.order_by("-id")
    rwork_type_assign = filtersubordinates(
        request, rwork_type_assign, "base.view_rotatingworktypeassign"
    )
    rwork_type_assign = rwork_type_assign.filter(employee_id__is_active=True)
    assign_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                rwork_type_assign, request.GET.get("page")
            ).object_list
        ]
    )
    return render(
        request,
        "base/rotating_work_type/rotating_work_type_assign.html",
        {
            "f": filter,
            "rwork_type_assign": paginator_qry(
                rwork_type_assign, request.GET.get("page")
            ),
            "assign_ids": assign_ids,
            "rwork_all": rwork_all,
            "gp_fields": RotatingWorkTypeRequestReGroup.fields,
        },
    )


@login_required
@hx_request_required
@manager_can_enter("base.add_rotatingworktypeassign")
def rotating_work_type_assign_add(request):
    """
    This method is used to assign rotating work type
    """
    form = RotatingWorkTypeAssignForm()
    if request.GET.get("emp_id"):
        employee = request.GET.get("emp_id")
        form = RotatingWorkTypeAssignUpdateForm(initial={"employee_id": employee})
    form = choosesubordinates(request, form, "base.add_rotatingworktypeassign")
    if request.method == "POST":
        form = RotatingWorkTypeAssignForm(request.POST)
        form = choosesubordinates(request, form, "base.add_rotatingworktypeassign")
        if form.is_valid():
            form.save()
            employee_ids = request.POST.getlist("employee_id")
            employees = Employee.objects.filter(id__in=employee_ids).select_related(
                "employee_user_id"
            )
            users = [employee.employee_user_id for employee in employees]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb="You are added to rotating work type",
                verb_ar="تمت إضافتك إلى نوع العمل المتناوب",
                verb_de="Sie werden zum rotierenden Arbeitstyp hinzugefügt",
                verb_es="Se le agrega al tipo de trabajo rotativo",
                verb_fr="Vous êtes ajouté au type de travail rotatif",
                icon="infinite",
                redirect=reverse("employee-profile"),
            )

            messages.success(request, _("Rotating work type assigned."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/rotating_work_type/htmx/rotating_work_type_assign_form.html",
        {"form": form},
    )


@login_required
@hx_request_required
@manager_can_enter("base.view_rotatingworktypeassign")
def rotating_work_type_assign_view(request):
    """
    This method renders template to view rotating work type objects
    """

    previous_data = request.GET.urlencode()
    rwork_type_assign = RotatingWorkTypeAssignFilter(request.GET).qs.order_by("-id")
    field = request.GET.get("field")
    if not request.GET.get("is_active") or request.GET.get("is_active") in [
        "true",
        "unknown",
    ]:
        rwork_type_assign = rwork_type_assign.filter(is_active=True)
    if request.GET.get("is_active") == "false":
        rwork_type_assign = rwork_type_assign.filter(is_active=False)
    rwork_type_assign = filtersubordinates(
        request, rwork_type_assign, "base.view_rotatingworktypeassign"
    )
    if request.GET.get("orderby"):
        rwork_type_assign = sortby(request, rwork_type_assign, "orderby")
    template = "base/rotating_work_type/rotating_work_type_assign_view.html"
    data_dict = parse_qs(previous_data)
    get_key_instances(RotatingWorkTypeAssign, data_dict)

    if field != "" and field is not None:
        rwork_type_assign = group_by_queryset(
            rwork_type_assign, field, request.GET.get("page"), "page"
        )
        list_values = [entry["list"] for entry in rwork_type_assign]
        id_list = []
        for value in list_values:
            for instance in value.object_list:
                id_list.append(instance.id)

        assign_ids = json.dumps(list(id_list))
        template = "base/rotating_work_type/htmx/group_by.html"

    else:
        rwork_type_assign = paginator_qry(rwork_type_assign, request.GET.get("page"))
        assign_ids = json.dumps(
            [instance.id for instance in rwork_type_assign.object_list]
        )

    return render(
        request,
        template,
        {
            "rwork_type_assign": rwork_type_assign,
            "pd": previous_data,
            "filter_dict": data_dict,
            "assign_ids": assign_ids,
            "field": field,
        },
    )


@login_required
@hx_request_required
def rotating_work_individual_view(request, instance_id):
    """
    This view is used render detailed view of the rotating work type assign
    """
    request_copy = request.GET.copy()
    request_copy.pop("instances_ids", None)
    previous_data = request_copy.urlencode()
    instance = RotatingWorkTypeAssign.objects.filter(id=instance_id).first()
    context = {"instance": instance, "pd": previous_data}
    assign_ids_json = request.GET.get("instances_ids")
    if assign_ids_json:
        assign_ids = json.loads(assign_ids_json)
        previous_id, next_id = closest_numbers(assign_ids, instance_id)
        context["previous"] = previous_id
        context["next"] = next_id
        context["assign_ids"] = assign_ids_json
    HTTP_REFERER = request.META.get("HTTP_REFERER", None)
    context["close_hx_url"] = ""
    context["close_hx_target"] = ""
    if HTTP_REFERER and (
        HTTP_REFERER.endswith("rotating-work-type-assign/")
        or HTTP_REFERER.endswith("work-schedules/")
    ):
        context["close_hx_url"] = "/rotating-work-type-assign-view"
        context["close_hx_target"] = "#view-container"
    elif HTTP_REFERER:
        HTTP_REFERERS = [part for part in HTTP_REFERER.split("/") if part]
        try:
            employee_id = int(HTTP_REFERERS[-1])
            context["close_hx_url"] = f"/employee/shift-tab/{employee_id}"
            context["close_hx_target"] = "#shift_target"
        except ValueError:
            pass
    return render(request, "base/rotating_work_type/individual_view.html", context)


@login_required
@hx_request_required
@manager_can_enter("base.change_rotatingworktypeassign")
def rotating_work_type_assign_update(request, id):
    """
    This method is used to update rotating work type instance
    """

    rotating_work_type_assign_obj = RotatingWorkTypeAssign.objects.get(id=id)
    form = RotatingWorkTypeAssignUpdateForm(instance=rotating_work_type_assign_obj)
    form = choosesubordinates(request, form, "base.change_rotatingworktypeassign")
    if request.method == "POST":
        form = RotatingWorkTypeAssignUpdateForm(
            request.POST, instance=rotating_work_type_assign_obj
        )
        form = choosesubordinates(request, form, "base.change_rotatingworktypeassign")
        if form.is_valid():
            form.save()
            messages.success(request, _("Rotating work type assign updated."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/rotating_work_type/htmx/rotating_work_type_assign_update_form.html",
        {"update_form": form},
    )


@login_required
@manager_can_enter("base.change_rotatingworktypeassign")
def rotating_work_type_assign_export(request):
    if request.META.get("HTTP_HX_REQUEST") == "true":
        context = {
            "export_filter": RotatingWorkTypeAssignFilter(),
            "export_columns": RotatingWorkTypeAssignExportForm(),
        }
        return render(
            request,
            "base/rotating_work_type/rotating_work_type_assign_export.html",
            context=context,
        )

    return export_data(
        request=request,
        model=RotatingWorkTypeAssign,
        filter_class=RotatingWorkTypeAssignFilter,
        form_class=RotatingWorkTypeAssignExportForm,
        file_name="Rotating_work_type_assign",
    )


def rotating_work_type_assign_redirect(request, obj_id=None, employee_id=None):
    request_copy = request.GET.copy()
    request_copy.pop("instances_ids", None)
    previous_data = request_copy.urlencode()
    hx_target = request.META.get("HTTP_HX_TARGET", None)
    hx_current_url = request.META.get("HTTP_HX_CURRENT_URL", None)
    parsed_url = urlparse(hx_current_url)
    hx_current_path = parsed_url.path.lstrip("/")
    if hx_target and hx_target == "view-container":
        return redirect(f"/rotating-work-type-assign-view?{previous_data}")
    elif hx_target and hx_target == "objectDetailsModalTarget":
        instances_ids = request.GET.get("instances_ids")
        instances_list = json.loads(instances_ids)
        if obj_id in instances_list:
            instances_list.remove(obj_id)
        previous_instance, next_instance = closest_numbers(
            json.loads(instances_ids), obj_id
        )

        url = f"/rwork-individual-view/{next_instance}/"
        params = f"?{previous_data}&instances_ids={instances_list}"
        return redirect(url + params)
    elif hx_target and hx_target == "shift_target" and employee_id:
        return redirect(f"/employee/shift-tab/{employee_id}")

    elif hx_target and hx_target == "genericModalBody":
        instances_ids = request.GET.get("instances_ids")
        instances_list = json.loads(instances_ids)
        if obj_id in instances_list:
            instances_list.remove(obj_id)
        previous_instance, next_instance = closest_numbers(
            json.loads(instances_ids), obj_id
        )

        return redirect(
            f"/work-rotating-detail-view/{next_instance}/?{previous_data}&instances_ids={instances_list}&deleted=True"
        )

    elif hx_target and hx_target == "rotating-work-container":
        if hx_current_path in (
            "employee/rotating-work-type-assign/",
            "employee/work-schedules/",
        ):
            rwork_type_requests = RotatingWorkTypeAssign.objects.all()
            previous_data = request.GET.urlencode()
            if rwork_type_requests.exists():
                return redirect(f"/rotating-list-view?is_active=True&{previous_data}")
            else:
                return HorillaRedirect(request)
        else:
            return redirect(
                f"/employee-rotating-work-tab-list/{employee_id}?deleted=True"
            )

    elif hx_target:
        return HorillaRedirect(request)
    else:
        return HorillaRedirect(request)


@login_required
@hx_request_required
@manager_can_enter("base.change_rotatingworktypeassign")
def rotating_work_type_assign_archive(request, obj_id):
    """
    Archive or un-archive rotating work type assigns
    """
    rwork_type = RotatingWorkTypeAssign.find(obj_id)
    if not rwork_type:
        messages.error(request, _("Rotating work type assign not found."))
        return HorillaRedirect(request)

    employee_id = rwork_type.employee_id.id
    employees_rwork_types = RotatingWorkTypeAssign.objects.filter(
        is_active=True, employee_id=rwork_type.employee_id
    )
    rwork_type.is_active = not rwork_type.is_active
    if rwork_type.is_active and employees_rwork_types:
        messages.error(request, _("Already on record is active"))
    else:
        rwork_type.save()
        message = _("un-archived") if rwork_type.is_active else _("archived")
        messages.success(request, _("Rotating work type assign is {}").format(message))
    return rotating_work_type_assign_redirect(request, obj_id, employee_id)


@login_required
@manager_can_enter("base.change_rotatingworktypeassign")
def rotating_work_type_assign_bulk_archive(request):
    """
    This method is used to archive/un-archive bulk rotating work type assigns.
    """
    ids = request.POST.get("ids")
    if not ids:
        return HorillaRedirect(
            request, message=_("No rotatingworktype found matching the query.")
        )
    ids = json.loads(ids)
    is_active = True
    message = _("un-archived")
    if request.GET.get("is_active") == "False":
        is_active = False
        message = _("archived")
    count = 0

    for id in ids:
        rwork_type_assign = RotatingWorkTypeAssign.objects.get(id=id)
        employees_rwork_type_assign = RotatingWorkTypeAssign.objects.filter(
            is_active=True, employee_id=rwork_type_assign.employee_id
        )

        if is_active and employees_rwork_type_assign.exists():
            messages.error(
                request,
                _("Rotating work type for {employee_id} already exists").format(
                    employee_id=rwork_type_assign.employee_id,
                ),
            )
        else:
            rwork_type_assign.is_active = is_active
            rwork_type_assign.save()
            count += 1

    if count > 0:
        messages.success(
            request,
            _("Rotating work type for {count} employees is {message}").format(
                count=count, message=message
            ),
        )

        return JsonResponse({"message": "Success"})

    return rotating_work_type_assign_redirect(request)


@login_required
@permission_required("base.delete_rotatingworktypeassign")
def rotating_work_type_assign_bulk_delete(request):
    """
    This method is used to archive/un-archive bulk rotating work type assigns
    """
    ids = request.POST.get("ids")
    if not ids:
        return HorillaRedirect(
            request, message=_("No rotatingworktype found matching the query.")
        )
    ids = json.loads(ids)
    for id in ids:
        try:
            rwork_type_assign = RotatingWorkTypeAssign.objects.get(id=id)
            rwork_type_assign.delete()
            messages.success(
                request,
                _("{employee} deleted.").format(employee=rwork_type_assign.employee_id),
            )
        except RotatingWorkTypeAssign.DoesNotExist:
            messages.error(request, _("{rwork_type_assign} not found."))
        except ProtectedError:
            messages.error(
                request,
                _("You cannot delete {rwork_type_assign}").format(
                    rwork_type_assign=rwork_type_assign
                ),
            )
    return JsonResponse({"message": "Success"})


@login_required
@hx_request_required
@permission_required("base.delete_rotatingworktypeassign")
@require_http_methods(["POST"])
def rotating_work_type_assign_delete(request, obj_id):
    """
    This method is used to delete rotating work type
    """
    rotating_work_type_assign_obj = RotatingWorkTypeAssign.find(obj_id)
    if not rotating_work_type_assign_obj:
        messages.error(request, _("Rotating work type assign not found."))
        return HorillaRedirect(request)

    employee_id = rotating_work_type_assign_obj.employee_id.id
    try:
        rotating_work_type_assign_obj.delete()
        messages.success(request, _("Rotating work type assign deleted."))
    except ProtectedError:
        messages.error(request, _("You cannot delete this rotating work type."))

    return rotating_work_type_assign_redirect(request, obj_id, employee_id)


@login_required
@permission_required("base.view_employeetype")
def employee_type_view(request):
    """
    This method is used to view employee type
    """

    types = EmployeeType.objects.all()
    return render(
        request,
        "base/employee_type/employee_type.html",
        {
            "employee_types": types,
        },
    )


@login_required
@hx_request_required
@permission_required("base.add_employeetype")
def employee_type_create(request):
    """
    This method is used to create employee type
    """
    dynamic = request.GET.get("dynamic")
    form = EmployeeTypeForm()
    types = EmployeeType.objects.all()
    if request.method == "POST":
        form = EmployeeTypeForm(request.POST)
        if form.is_valid():
            form.save()
            form = EmployeeTypeForm()
            messages.success(request, _("Employee type created."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/employee_type/employee_type_form.html",
        {"form": form, "employee_types": types, "dynamic": dynamic},
    )


@login_required
@hx_request_required
@permission_required("base.change_employeetype")
def employee_type_update(request, id, **kwargs):
    """
    This method is used to update employee type instance
    args:
        id : employee type instance id

    """

    employee_type = EmployeeType.find(id)
    form = EmployeeTypeForm(instance=employee_type)
    if request.method == "POST":
        form = EmployeeTypeForm(request.POST, instance=employee_type)
        if form.is_valid():
            form.save()
            messages.success(request, _("Employee type updated."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/employee_type/employee_type_form.html",
        {"form": form, "employee_type": employee_type},
    )


@login_required
@permission_required("base.view_employeeshift")
def employee_shift_view(request):
    """
    This method is used to view employee shift
    """

    shifts = EmployeeShift.objects.all()
    if apps.is_installed("attendance"):
        GraceTime = get_horilla_model_class(app_label="attendance", model="gracetime")
        grace_times = GraceTime.objects.all().exclude(is_default=True)
    else:
        grace_times = None
    return render(
        request, "base/shift/shift.html", {"shifts": shifts, "grace_times": grace_times}
    )


@login_required
@hx_request_required
@permission_required("base.add_employeeshift")
def employee_shift_create(request):
    """
    This method is used to create employee shift
    """
    dynamic = request.GET.get("dynamic")
    form = EmployeeShiftForm()
    shifts = EmployeeShift.objects.all()
    if request.method == "POST":
        form = EmployeeShiftForm(request.POST)
        if form.is_valid():
            form.save()
            form = EmployeeShiftForm()
            messages.success(
                request, _("Employee Shift has been created successfully!")
            )
            return HorillaRedirect(request)
    return render(
        request,
        "base/shift/shift_form.html",
        {"form": form, "shifts": shifts, "dynamic": dynamic},
    )


@login_required
@hx_request_required
@permission_required("base.change_employeeshift")
def employee_shift_update(request, id, **kwargs):
    """
    This method is used to update employee shift instance
    args:
        id  : employee shift id

    """
    employee_shift = EmployeeShift.find(id)
    form = EmployeeShiftForm(instance=employee_shift)
    if request.method == "POST":
        form = EmployeeShiftForm(request.POST, instance=employee_shift)
        if form.is_valid():
            form.save()
            messages.success(request, _("Shift updated"))
            return HorillaRedirect(request)
    return render(
        request, "base/shift/shift_form.html", {"form": form, "shift": employee_shift}
    )


@login_required
@permission_required("base.view_employeeshiftschedule")
def employee_shift_schedule_view(request):
    """
    This method is used to view schedule for shift
    """
    shift_schedule = False
    if EmployeeShiftSchedule.objects.exists():
        shift_schedule = True
    shifts = EmployeeShift.objects.all()

    return render(
        request,
        "base/shift/schedule.html",
        {"shifts": shifts, "shift_schedule": shift_schedule},
    )


@login_required
@hx_request_required
@permission_required("base.add_employeeshiftschedule")
def employee_shift_schedule_create(request):
    """
    This method is used to create schedule for shift
    """

    form = EmployeeShiftScheduleForm()
    shifts = EmployeeShift.objects.all()
    if request.method == "POST":
        form = EmployeeShiftScheduleForm(request.POST)
        if form.is_valid():
            form.save()
            form = EmployeeShiftScheduleForm()
            messages.success(
                request, _("Employee Shift Schedule has been created successfully!")
            )
            return HorillaRedirect(request)

    return render(
        request, "base/shift/schedule_form.html", {"form": form, "shifts": shifts}
    )


@login_required
@hx_request_required
@permission_required("base.change_employeeshiftschedule")
def employee_shift_schedule_update(request, id, **kwargs):
    """
    This method is used to update employee shift instance
    args:
        id : employee shift instance id
    """

    employee_shift_schedule = EmployeeShiftSchedule.find(id)
    form = EmployeeShiftScheduleUpdateForm(instance=employee_shift_schedule)
    if request.method == "POST":
        form = EmployeeShiftScheduleUpdateForm(
            request.POST, instance=employee_shift_schedule
        )
        if form.is_valid():
            form.save()
            messages.success(request, _("Shift schedule created."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/shift/schedule_form.html",
        {"form": form, "shift_schedule": employee_shift_schedule},
    )


@login_required
@permission_required("base.view_rotatingshift")
def rotating_shift_view(request):
    """
    This method is used to view rotating shift
    """

    return render(
        request,
        "base/rotating_shift/rotating_shift.html",
        {"rshifts": RotatingShift.objects.all()},
    )


@login_required
@hx_request_required
@permission_required("base.add_rotatingshift")
def rotating_shift_create(request):
    """
    This method is used to create rotating shift
    """

    form = RotatingShiftForm()
    if request.method == "POST":
        form = RotatingShiftForm(request.POST)
        if form.is_valid():
            form.save()
            form = RotatingShiftForm()
            messages.success(request, _("Rotating shift created."))
            return HorillaRedirect(request)
    else:
        form = RotatingShiftForm()
    return render(
        request,
        "base/rotating_shift/htmx/rotating_shift_form.html",
        {"form": form, "rshifts": RotatingShift.objects.all()},
    )


@login_required
@hx_request_required
@permission_required("base.change_rotatingshift")
def rotating_shift_update(request, id, **kwargs):
    """
    This method is used to update rotating shift instance
    args:
        id : rotating shift instance id
    """

    rotating_shift = RotatingShift.find(id)
    form = RotatingShiftForm(instance=rotating_shift)
    if request.method == "POST":
        form = RotatingShiftForm(request.POST, instance=rotating_shift)
        if form.is_valid():
            form.save()
            form = RotatingShiftForm()
            messages.success(request, _("Rotating shift updated."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/rotating_shift/htmx/rotating_shift_form.html",
        {
            "form": form,
            "rshift": rotating_shift,
        },
    )


@login_required
@manager_can_enter("base.view_rotatingshiftassign")
def rotating_shift_assign(request):
    """
    This method is used to assign rotating shift
    """
    form = RotatingShiftAssignForm()
    form = choosesubordinates(request, form, "base.add_rotatingshiftassign")
    filter = RotatingShiftAssignFilters(
        queryset=RotatingShiftAssign.objects.filter(is_active=True)
    )
    rshift_assign = filter.qs
    rshift_all = RotatingShiftAssign.objects.all()

    rshift_assign = filtersubordinates(
        request, rshift_assign, "base.view_rotatingshiftassign"
    )
    rshift_assign = rshift_assign.filter(employee_id__is_active=True)
    assign_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                rshift_assign, request.GET.get("page")
            ).object_list
        ]
    )

    return render(
        request,
        "base/rotating_shift/rotating_shift_assign.html",
        {
            "form": form,
            "f": filter,
            "export_filter": RotatingShiftAssignFilters(),
            "export_columns": RotatingShiftAssignExportForm(),
            "rshift_assign": paginator_qry(rshift_assign, request.GET.get("page")),
            "assign_ids": assign_ids,
            "rshift_all": rshift_all,
            "gp_fields": RotatingShiftRequestReGroup.fields,
        },
    )


@login_required
@hx_request_required
@manager_can_enter("base.add_rotatingshiftassign")
def rotating_shift_assign_add(request):
    """
    This method is used to add rotating shift assign
    """
    form = RotatingShiftAssignForm()
    if request.GET.get("emp_id"):
        employee = request.GET.get("emp_id")
        form = RotatingShiftAssignUpdateForm(initial={"employee_id": employee})
    form = choosesubordinates(request, form, "base.add_rotatingshiftassign")
    if request.method == "POST":
        form = RotatingShiftAssignForm(request.POST)
        form = choosesubordinates(request, form, "base.add_rotatingshiftassign")
        if form.is_valid():
            form.save()
            employee_ids = request.POST.getlist("employee_id")
            employees = Employee.objects.filter(id__in=employee_ids).select_related(
                "employee_user_id"
            )
            users = [employee.employee_user_id for employee in employees]
            notify.send(
                request.user.employee_get,
                recipient=users,
                verb="You are added to rotating shift",
                verb_ar="تمت إضافتك إلى وردية الدورية",
                verb_de="Sie werden der rotierenden Arbeitsschicht hinzugefügt",
                verb_es="Estás agregado a turno rotativo",
                verb_fr="Vous êtes ajouté au quart de travail rotatif",
                icon="infinite",
                redirect=reverse("employee-profile"),
            )

            messages.success(request, _("Rotating shift assigned."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/rotating_shift/htmx/rotating_shift_assign_form.html",
        {"form": form},
    )


@login_required
@hx_request_required
@manager_can_enter("base.view_rotatingshiftassign")
def rotating_shift_assign_view(request):
    """
    This method renders all instance of rotating shift assign to a template
    """
    previous_data = request.GET.urlencode()
    rshift_assign = RotatingShiftAssignFilters(request.GET).qs.order_by("-id")
    field = request.GET.get("field")
    if (
        request.GET.get("is_active") is None
        or request.GET.get("is_active") == "unknown"
    ):
        rshift_assign = rshift_assign.filter(is_active=True)
    rshift_assign = filtersubordinates(
        request, rshift_assign, "base.view_rotatingshiftassign"
    )
    rshift_assign = sortby(request, rshift_assign, "orderby")
    data_dict = parse_qs(previous_data)
    get_key_instances(RotatingShiftAssign, data_dict)
    template = "base/rotating_shift/rotating_shift_assign_view.html"

    if field != "" and field is not None:
        rshift_assign = group_by_queryset(
            rshift_assign, field, request.GET.get("page"), "page"
        )
        list_values = [entry["list"] for entry in rshift_assign]
        id_list = []
        for value in list_values:
            for instance in value.object_list:
                id_list.append(instance.id)

        assign_ids = json.dumps(list(id_list))
        template = "base/rotating_shift/htmx/group_by.html"

    else:
        rshift_assign = paginator_qry(rshift_assign, request.GET.get("page"))
        assign_ids = json.dumps([instance.id for instance in rshift_assign.object_list])
    return render(
        request,
        template,
        {
            "rshift_assign": rshift_assign,
            "pd": previous_data,
            "filter_dict": data_dict,
            "assign_ids": assign_ids,
            "field": field,
        },
    )


@login_required
@hx_request_required
def rotating_shift_individual_view(request, instance_id):
    """
    This view is used render detailed view of the rotating shit assign
    """
    request_copy = request.GET.copy()
    request_copy.pop("instances_ids", None)
    previous_data = request_copy.urlencode()
    instance = RotatingShiftAssign.objects.filter(id=instance_id).first()
    context = {"instance": instance, "pd": previous_data}
    assign_ids_json = request.GET.get("instances_ids")
    HTTP_REFERER = request.META.get("HTTP_REFERER", None)
    context["close_hx_url"] = ""
    context["close_hx_target"] = ""
    if HTTP_REFERER and (
        HTTP_REFERER.endswith("rotating-shift-assign/")
        or HTTP_REFERER.endswith("work-schedules/")
    ):
        context["close_hx_url"] = "/rotating-shift-assign-view"
        context["close_hx_target"] = "#view-container"
    elif HTTP_REFERER:
        HTTP_REFERERS = [part for part in HTTP_REFERER.split("/") if part]
        try:
            employee_id = int(HTTP_REFERERS[-1])
            context["close_hx_url"] = f"/employee/shift-tab/{employee_id}"
            context["close_hx_target"] = "#shift_target"
        except ValueError:
            pass
    if assign_ids_json:
        assign_ids = json.loads(assign_ids_json)
        previous_id, next_id = closest_numbers(assign_ids, instance_id)
        context["previous"] = previous_id
        context["next"] = next_id
        context["assign_ids"] = assign_ids
    return render(request, "base/rotating_shift/individual_view.html", context)


@login_required
@hx_request_required
@manager_can_enter("base.change_rotatingshiftassign")
def rotating_shift_assign_update(request, id):
    """
    This method is used to update rotating shift assign instance
    args:
        id : rotating shift assign instance id

    """
    rotating_shift_assign_obj = RotatingShiftAssign.find(id)
    form = RotatingShiftAssignUpdateForm(instance=rotating_shift_assign_obj)
    form = choosesubordinates(request, form, "base.change_rotatingshiftassign")
    if request.method == "POST":
        form = RotatingShiftAssignUpdateForm(
            request.POST, instance=rotating_shift_assign_obj
        )
        form = choosesubordinates(request, form, "base.change_rotatingshiftassign")
        if form.is_valid():
            form.save()
            messages.success(request, _("Rotating shift assign updated."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/rotating_shift/htmx/rotating_shift_assign_update_form.html",
        {
            "update_form": form,
        },
    )


@login_required
@manager_can_enter("base.change_rotatingshiftassign")
def rotating_shift_assign_export(request):
    if request.META.get("HTTP_HX_REQUEST"):
        context = {
            "export_filter": RotatingShiftAssignFilters(),
            "export_columns": RotatingShiftAssignExportForm(),
        }
        return render(
            request,
            "base/rotating_shift/rotating_shift_assign_export.html",
            context=context,
        )
    return export_data(
        request=request,
        model=RotatingShiftAssign,
        filter_class=RotatingShiftAssignFilters,
        form_class=RotatingShiftAssignExportForm,
        file_name="Rotating_shift_assign_export",
    )


def normalize_list(lst):
    return [None if pd.isna(x) else x for x in lst]


@login_required
@manager_can_enter("base.add_rotatingworktypeassign")
def rotating_shift_assign_import(request):
    if request.method == "POST":
        rotating_shift_obj_list = []
        employee_ids = []
        rotating_shift_assign_list = []
        error_list = []
        new_dicts = {}
        rotating_shifts = RotatingShift.objects.all()
        shifts = EmployeeShift.objects.all()
        file = request.FILES["file"]
        file_extension = file.name.split(".")[-1].lower()
        error = False
        create_rotating_shift = True

        existing_dicts = {
            rot_shift.id: [
                shift.employee_shift if shift else None
                for shift in rot_shift.total_shifts()
            ]
            for rot_shift in rotating_shifts
        }
        data_frame = (
            pd.read_csv(file) if file_extension == "csv" else pd.read_excel(file)
        )
        work_info_dicts = data_frame.to_dict("records")
        try:
            keys_list = list(work_info_dicts[0].keys())
            error_dict = {key: [] for key in keys_list}
        except:
            messages.error(request, _("something went wrong...."))
            data_frame = pd.DataFrame(
                ["Please provide valid data"],
                columns=["Title Error"],
            )

            error_count = 1
            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="ImportError.csv"'

            data_frame.to_csv(response, index=False)
            response["X-Error-Count"] = error_count
            return response

        error_dict["Title Error"] = []
        error_dict["Employee Error"] = []
        error_dict["Date Error"] = []
        if len(keys_list) > 4:
            start_date = keys_list[3]
            start_date = parser.parse(str(start_date), dayfirst=True).date()

        for total_rows, row in enumerate(work_info_dicts, start=1):
            employee_ids.append(row["Badge Id"])
            current_list = list(row.values())[3:]
            current_list = normalize_list(current_list)
            if start_date < datetime.today().date():
                error_dict["Date Error"] = "Start Date must be greater than today"

            if current_list not in list(
                existing_dicts.values()
            ) and current_list not in list(new_dicts.values()):
                if rotating_shifts.filter(name=row["Title"]).exists():
                    row["Title Error"] = "Rotating Shift with this Title already exists"
                    error = True
                    error_list.append(row)
                    continue

                rotating_shift_obj = RotatingShift(
                    name=row["Title"],
                    shift1=shifts.filter(employee_shift=current_list[0]).first(),
                    shift2=shifts.filter(employee_shift=current_list[1]).first(),
                )
                if current_list[2:]:
                    additional_data = []
                    for item in current_list[2:]:
                        try:
                            additional_data.append(
                                shifts.filter(employee_shift=item).first().id
                            )
                        except:
                            additional_data.append(None)

                    rotating_shift_obj.additional_data = {
                        "additional_shifts": additional_data
                    }
                    rotating_shift_obj.save()
                new_dicts[rotating_shift_obj.id] = current_list

                rotating_shift_obj_list.append(rotating_shift_obj)
            else:
                flag = True
                for rot_shift_id, shift_list in existing_dicts.items():
                    if shift_list == current_list:
                        rotating_shift_obj = RotatingShift.objects.get(id=rot_shift_id)
                        rotating_shift_obj_list.append(rotating_shift_obj)
                        flag = False
                        break
                if flag:
                    for rot_shift_id, shift_list in new_dicts.items():
                        if shift_list == current_list:
                            rotating_shift_obj = RotatingShift.objects.get(
                                id=rot_shift_id
                            )
                            rotating_shift_obj_list.append(rotating_shift_obj)
                            break

        employee_list = Employee.objects.filter(badge_id__in=employee_ids)
        r_shifts = RotatingShiftAssign.objects.all()
        if start_date and employee_ids:
            for employee, rshift in zip(employee_list, rotating_shift_obj_list):
                if not r_shifts.filter(
                    employee_id=employee, rotating_shift_id=rshift
                ).exists():
                    rot_shift_assign = RotatingShiftAssign()
                    rot_shift_assign.employee_id = employee
                    rot_shift_assign.rotating_shift_id = rshift
                    rot_shift_assign.start_date = start_date
                    rot_shift_assign.based_on = "after"
                    rot_shift_assign.rotate_after_day = 1
                    rot_shift_assign.next_change_date = start_date
                    rot_shift_assign.next_shift = rshift.shift1
                    rot_shift_assign.additional_data["next_shift_index"] = 1
                    rotating_shift_assign_list.append(rot_shift_assign)
                else:
                    error_message = f"Rotating Shift with ID {rshift.name} is already assigned to employee {employee}"
                    for row in work_info_dicts:
                        if row["Badge Id"] == employee.badge_id:
                            row["Employee Error"] = error_message
                            error_list.append(row)
                            break

        create_rotating_shift = (
            not error_list or request.POST.get("create_rotating_shift") == "true"
        )

        if create_rotating_shift:
            if rotating_shift_assign_list:
                RotatingShiftAssign.objects.bulk_create(rotating_shift_assign_list)

        flg = set()
        unique_error_list = []

        for row in error_list:
            badge_id = row["Badge Id"]
            if badge_id not in flg:
                unique_error_list.append(row)
                flg.add(badge_id)

        if unique_error_list:
            for item in unique_error_list:
                for key, value in error_dict.items():
                    if key in item:
                        value.append(item[key])
                    else:
                        try:
                            value.append(None)
                        except:
                            pass

            keys_to_remove = [
                key
                for key, value in error_dict.items()
                if all(v is None for v in value)
            ]

            for key in keys_to_remove:
                del error_dict[key]
            data_frame = pd.DataFrame(error_dict, columns=error_dict.keys())
            error_count = len(unique_error_list)

            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="ImportError.csv"'

            data_frame.to_csv(response, index=False)
            response["X-Error-Count"] = error_count
            return response

        return JsonResponse(
            {
                "Success": "Employees Imported Succefully",
                "success_count": len(employee_list),
            }
        )
    return HttpResponse("")


def rotating_shift_assign_redirect(request, obj_id, employee_id):
    request_copy = request.GET.copy()
    request_copy.pop("instances_ids", None)
    previous_data = request_copy.urlencode()
    hx_target = request.META.get("HTTP_HX_TARGET", None)
    if hx_target and hx_target == "view-container":
        return redirect(f"/rotating-shift-assign-view?{previous_data}")
    elif hx_target and hx_target == "objectDetailsModalTarget":
        instances_ids = request.GET.get("instances_ids")
        instances_list = json.loads(instances_ids)
        if obj_id in instances_list:
            instances_list.remove(obj_id)
        previous_instance, next_instance = closest_numbers(
            json.loads(instances_ids), obj_id
        )
        return redirect(
            f"/rshit-individual-view/{next_instance}/?{previous_data}\
            &instances_ids={instances_list}"
        )
    elif hx_target and hx_target == "genericModalBody":
        instances_ids = request.GET.get("instances_ids")
        instances_list = json.loads(instances_ids)
        if obj_id in instances_list:
            instances_list.remove(obj_id)
        previous_instance, next_instance = closest_numbers(
            json.loads(instances_ids), obj_id
        )
        return redirect(
            f"/rotating-shift-individual-detail-view/{next_instance}/?{previous_data}&instance_ids={instances_list}&detail=true"
        )
    elif hx_target and hx_target == "shift_target" and employee_id:
        return redirect(f"/employee/shift-tab/{employee_id}")
    elif hx_target and hx_target == "rotating-shift-container":
        path = request.META.get("HTTP_HX_CURRENT_URL", None)
        parsed_url = urlparse(path)
        parsed_path = parsed_url.path.lstrip("/")
        if parsed_path in (
            "employee/rotating-shift-assign/",
            "employee/work-schedules/",
        ):
            return redirect(f"/rotating-shift-request-list/?is_active=true")
        return redirect(
            f"/rotating-shift-individual-tab-view/{employee_id}?deleted=true"
        )

    return HorillaRedirect(request)


@login_required
@hx_request_required
@manager_can_enter("base.change_rotatingshiftassign")
def rotating_shift_assign_archive(request, obj_id):
    """
    This method is used to archive and unarchive rotating shift assign records
    """
    rshift = RotatingShiftAssign.find(obj_id)
    if not rshift:
        messages.error(request, _("Rotating shift assign not found."))
        return HorillaRedirect(request)

    employee_id = rshift.employee_id.id
    employees_rshift_assigns = RotatingShiftAssign.objects.filter(
        is_active=True, employee_id=rshift.employee_id
    )
    rshift.is_active = not rshift.is_active
    if rshift.is_active and employees_rshift_assigns:
        messages.error(request, _("Already on record is active"))
    else:
        rshift.save()
        message = _("un-archived") if rshift.is_active else _("archived")
        messages.success(request, _("Rotating shift assign is {}").format(message))

    return rotating_shift_assign_redirect(request, obj_id, employee_id)


@login_required
@manager_can_enter("base.change_rotatingshiftassign")
def rotating_shift_assign_bulk_archive(request):
    """
    This method is used to archive/un-archive bulk rotating shift assigns
    """
    ids = request.POST.get("ids")
    if not ids:
        return HorillaRedirect(
            request, message=_("No rotatingshift found matching the query.")
        )
    ids = json.loads(ids)
    is_active = True
    message = _("un-archived")
    if request.GET.get("is_active") == "False":
        is_active = False
        message = _("archived")
    for id in ids:
        # check permission right here...
        rshift_assign = RotatingShiftAssign.objects.get(id=id)
        employees_rshift_assign = RotatingShiftAssign.objects.filter(
            is_active=True, employee_id=rshift_assign.employee_id
        )
        flag = True
        if is_active:
            if len(employees_rshift_assign) < 1:
                flag = False
                rshift_assign.is_active = is_active
        else:
            flag = False
            rshift_assign.is_active = is_active
        rshift_assign.save()
        if not flag:
            messages.success(
                request,
                _("Rotating shift for {employee} is {message}").format(
                    employee=rshift_assign.employee_id, message=message
                ),
            )
        else:
            messages.error(
                request,
                _("Rotating shift for {employee} is already exists").format(
                    employee=rshift_assign.employee_id
                ),
            )
    return JsonResponse({"message": "Success"})


@login_required
@manager_can_enter("base.delete_rotatingshiftassign")
def rotating_shift_assign_bulk_delete(request):
    """
    This method is used to bulk delete for rotating shift assign
    """
    ids = request.POST.get("ids")
    if not ids:
        return HorillaRedirect(
            request, message=_("No rotatingshift found matching the query.")
        )
    ids = json.loads(ids)
    for id in ids:
        try:
            rshift_assign = RotatingShiftAssign.objects.get(id=id)
            rshift_assign.delete()
            messages.success(
                request,
                _("{employee} assign deleted.").format(
                    employee=rshift_assign.employee_id
                ),
            )
        except RotatingShiftAssign.DoesNotExist:
            messages.error(request, _("{rshift_assign} not found."))
        except ProtectedError:
            messages.error(
                request,
                _("You cannot delete {rshift_assign}").format(
                    rshift_assign=rshift_assign
                ),
            )
    return JsonResponse({"message": "Success"})


@login_required
@hx_request_required
@manager_can_enter("base.delete_rotatingshiftassign")
@require_http_methods(["POST"])
def rotating_shift_assign_delete(request, obj_id):
    """
    This method is used to delete rotating shift assign instance
    args:
        id : rotating shift assign instance id
    """
    try:
        rotating_shift_assign_obj = RotatingShiftAssign.objects.get(id=obj_id)
        employee_id = rotating_shift_assign_obj.employee_id.id
        rotating_shift_assign_obj.delete()
        messages.success(request, _("Rotating shift assign deleted."))
    except RotatingShiftAssign.DoesNotExist:
        employee_id = None
        messages.error(request, _("Rotating shift assign not found."))
    except ProtectedError:
        messages.error(request, _("You cannot delete this rotating shift assign."))
    return rotating_shift_assign_redirect(request, obj_id, employee_id)


def get_models_in_app(app_name):
    """
    get app models
    """
    try:
        app_config = apps.get_app_config(app_name)
        models = app_config.get_models()
        return [model for model in models if model.__name__ != "CompanyTheme"]
    except LookupError:
        return []


@login_required
def employee_permission_assign(request, pk=None):
    """
    Assign / view permissions for an employee user.

    - Settings "Employee Permission" page (no employee in path): superadmin only.
    - Employee profile tab: employee self, reporting manager, or superadmin.
    """
    from employee.cbv.accessibility import can_edit_employee_permissions
    from horilla.methods import handle_no_permission

    context = {}
    template = "base/auth/permission.html"
    path = request.path
    parts = path.strip("/").split("/")
    id_part = parts[-1]
    emp_id = None
    if id_part != "employee-permission-assign":
        emp_id = id_part
    else:
        id_part = None

    # Settings page (no employee context) is superadmin-only.
    if not emp_id and not request.user.is_superuser:
        return handle_no_permission(request)
    if not emp_id:
        # Direct employee permissions now live beside Roles on one settings
        # screen. Keep this legacy URL as a backwards-compatible entry point.
        return redirect(f"{reverse('user-group-view')}?tab=permissions")

    if emp_id:
        template = "tabs/group_permissions.html"
        employees = Employee.objects.filter(id=emp_id)
        employee = employees.first()
        if not employee:
            return handle_no_permission(request)
        import json

        from base.auth_backends import (
            get_effective_permission_codenames,
            get_permission_company_label,
            get_user_groups_for_company,
        )
        from employee.cbv.accessibility import can_view_employee_permissions

        if not can_view_employee_permissions(request, employee):
            return handle_no_permission(request)
        target_user = employee.employee_user_id
        context["employee"] = employee
        context["can_edit_permissions"] = can_edit_employee_permissions(
            request, employee
        )
        context["can_view_permissions"] = True
        context["employee_company_groups"] = list(
            get_user_groups_for_company(target_user)
        )
        context["employee_perm_codenames"] = json.dumps(
            get_effective_permission_codenames(target_user)
        )
        context["permission_company_label"] = get_permission_company_label()
    else:
        employees = Employee.objects.filter(
            Q(employee_user_id__user_permissions__isnull=False)
            | Q(employee_user_id__groups__isnull=False)
        ).distinct()
        context["show_assign"] = True
        context["can_edit_permissions"] = True
    from base.auth_backends import company_scoped_active

    permissions, no_permission_models = _build_permission_matrix()
    context["permissions"] = permissions
    context["no_permission_models"] = no_permission_models
    context["company_scoped"] = company_scoped_active()
    context["employees"] = paginator_qry(employees, request.GET.get("page"))
    return render(
        request,
        template,
        context,
    )


@login_required
@hx_request_required
def employee_permission_search(request, codename=None, uid=None):
    """
    This method renders template to view all instances of user permissions
    """
    from employee.cbv.accessibility import (
        can_edit_employee_permissions,
        can_view_employee_permissions,
    )
    from horilla.methods import handle_no_permission

    context = {}
    template = "base/auth/permission_lines.html"
    employees = EmployeeFilter(request.GET).qs
    if request.GET.get("profile_tab"):
        employees = Employee.objects.filter(id=request.GET["employee_id"])
        employee = employees.first()
        if not employee or not can_view_employee_permissions(request, employee):
            return handle_no_permission(request)
        context["employee"] = employee
        context["can_edit_permissions"] = can_edit_employee_permissions(
            request, employee
        )
    else:
        if not (
            request.user.is_superuser or request.user.has_perm("auth.view_permission")
        ):
            return handle_no_permission(request)
        employees = employees.filter(
            Q(employee_user_id__user_permissions__isnull=False)
            | Q(employee_user_id__groups__isnull=False)
        ).distinct()
        context["show_assign"] = True
        context["can_edit_permissions"] = True
    permissions, no_permission_models = _build_permission_matrix()
    context["permissions"] = permissions
    context["no_permission_models"] = no_permission_models
    context["employees"] = paginator_qry(employees, request.GET.get("page"))
    return render(
        request,
        template,
        context,
    )


@login_required
@require_http_methods(["POST"])
def update_permission(
    request,
):
    """
    This method is used to remove user permission.
    """
    from employee.cbv.accessibility import can_edit_employee_permissions
    from horilla.methods import handle_no_permission

    try:
        data = json.loads(request.body)

        employee_id = data.get("employee")
        permissions_data = data.get("permissions", [])

        if not employee_id:
            messages.error(request, _("Employee not provided"))
            return JsonResponse(
                {"message": "Employee not provided", "type": "danger"}, status=400
            )

        employee = Employee.objects.select_related("employee_user_id").get(
            id=employee_id
        )
        if not can_edit_employee_permissions(request, employee):
            return handle_no_permission(request)

        user = employee.employee_user_id

        all_codenames = [p["codename"] for p in permissions_data]
        checked_codenames = [p["codename"] for p in permissions_data if p["checked"]]

        existing_managed = user.user_permissions.filter(codename__in=all_codenames)
        managed_permissions = Permission.objects.filter(codename__in=all_codenames)
        checked_permissions = managed_permissions.filter(codename__in=checked_codenames)

        user.user_permissions.remove(*existing_managed)
        user.user_permissions.add(*checked_permissions)

        messages.success(request, _("Permissions updated successfully"))

        return JsonResponse(
            {"message": "Permissions updated successfully", "type": "success"}
        )

    except Employee.DoesNotExist:
        messages.error(request, _("Employee not found"))
        return JsonResponse(
            {"message": "Employee not found", "type": "danger"}, status=404
        )

    except Exception as e:
        messages.error(request, _("Something went wrong"))
        return JsonResponse(
            {"message": "Something went wrong", "type": "danger"}, status=500
        )


@login_required
@hx_request_required
@superuser_required
def permission_table(request):
    """
    This method is used to render the permission table
    """
    form = AssignPermission()
    permissions, no_permission_models = _build_permission_matrix()
    if request.method == "POST":
        form = AssignPermission(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Employee permission assigned."))
            return HorillaRedirect(request)
    return render(
        request,
        "base/auth/permission_assign.html",
        {
            "permissions": permissions,
            "form": form,
            "no_permission_models": no_permission_models,
        },
    )


@login_required
@permission_required("auth.add_permission")
def employee_permission_codenames(request, emp_id):
    """
    JSON list of effective permission codenames for one employee.
    Used by the Assign Permissions modal when a single employee is selected.
    """
    employee = get_object_or_404(
        Employee.objects.select_related("employee_user_id"), id=emp_id
    )
    user = employee.employee_user_id
    if not user:
        return JsonResponse({"codenames": []})
    codenames = sorted(
        {perm.split(".", 1)[-1] for perm in user.get_all_permissions() if perm}
    )
    return JsonResponse({"codenames": codenames})


@login_required
def work_type_request_view(request):
    """
    This method renders template to  view all work type requests
    """
    previous_data = request.GET.urlencode()
    employee = Employee.objects.filter(employee_user_id=request.user).first()
    if request.user.has_perm("base.view_worktyperequest"):
        work_type_requests = WorkTypeRequest.objects.all()
    else:
        work_type_requests = filtersubordinates(
            request, WorkTypeRequest.objects.all(), "base.add_worktyperequest"
        )
        work_type_requests = work_type_requests | WorkTypeRequest.objects.filter(
            employee_id=employee
        )
        work_type_requests = work_type_requests.filter(employee_id__is_active=True)
    requests_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                work_type_requests, request.GET.get("page")
            ).object_list
        ]
    )
    f = WorkTypeRequestFilter(request.GET, queryset=work_type_requests)
    data_dict = parse_qs(previous_data)
    get_key_instances(WorkTypeRequest, data_dict)
    form = WorkTypeRequestForm()
    form = choosesubordinates(
        request,
        form,
        "base.add_worktypereqeust",
    )
    form = include_employee_instance(request, form)
    return render(
        request,
        "work_type_request/work_type_request_view.html",
        {
            "data": paginator_qry(f.qs, request.GET.get("page")),
            "f": f,
            "form": form,
            "filter_dict": data_dict,
            "requests_ids": requests_ids,
            "gp_fields": WorkTypeRequestReGroup.fields,
        },
    )


@login_required
@manager_can_enter("base.view_worktyperequest")
def work_type_request_export(request):
    if request.META.get("HTTP_HX_REQUEST") == "true":
        export_filter = WorkTypeRequestFilter()
        export_fields = WorkTypeRequestColumnForm()
        context = {
            "export_fields": export_fields,
            "export_filter": export_filter,
        }
        return render(
            request, "work_type_request/work_type_request_export.html", context=context
        )
    return export_data(
        request,
        WorkTypeRequest,
        WorkTypeRequestColumnForm,
        WorkTypeRequestFilter,
        "Work_type_request",
    )


@login_required
@hx_request_required
def work_type_request_search(request):
    """
    This method is used to search work type request.
    """
    employee = Employee.objects.filter(employee_user_id=request.user).first()
    previous_data = request.GET.urlencode()
    field = request.GET.get("field")
    f = WorkTypeRequestFilter(request.GET)
    work_typ_requests = (
        filtersubordinates(request, f.qs, "base.add_worktyperequest")
        if not request.user.has_perm("base.view_worktyperequest")
        else f.qs
    )
    employee_work_requests = list(WorkTypeRequest.objects.filter(employee_id=employee))
    subordinates_work_requests = list(work_typ_requests)
    combined_requests = list(set(subordinates_work_requests + employee_work_requests))
    combined_requests_qs = WorkTypeRequest.objects.filter(
        id__in=[req.id for req in combined_requests]
    )
    work_typ_requests = sortby(request, combined_requests_qs, "orderby")
    template = "work_type_request/htmx/requests.html"

    if field != "" and field is not None:
        work_typ_requests = group_by_queryset(
            work_typ_requests, field, request.GET.get("page"), "page"
        )
        list_values = [entry["list"] for entry in work_typ_requests]
        id_list = []
        for value in list_values:
            for instance in value.object_list:
                id_list.append(instance.id)

        requests_ids = json.dumps(list(id_list))
        template = "work_type_request/htmx/group_by.html"

    else:
        work_typ_requests = paginator_qry(work_typ_requests, request.GET.get("page"))
        requests_ids = json.dumps(
            [instance.id for instance in work_typ_requests.object_list]
        )

    data_dict = parse_qs(previous_data)
    get_key_instances(WorkTypeRequest, data_dict)
    return render(
        request,
        template,
        {
            "data": work_typ_requests,
            "pd": previous_data,
            "filter_dict": data_dict,
            "requests_ids": requests_ids,
            "field": field,
        },
    )


def handle_wtr_close_hx_url(request):
    employee = request.user.employee_get.id
    HTTP_REFERER = request.META.get("HTTP_REFERER", "")
    previous_data = unquote(request.GET.urlencode().replace("pd=", ""))
    close_hx_url = ""
    close_hx_target = ""

    if HTTP_REFERER and "/" + "/".join(HTTP_REFERER.split("/")[3:]) == "/":
        close_hx_url = reverse("dashboard-work-type-request")
        close_hx_target = "#WorkTypeRequestApproveBody"
    elif HTTP_REFERER and HTTP_REFERER.endswith("requests/"):
        close_hx_url = f"/work-list-view?{previous_data}"
        close_hx_target = "#listContainer"
    elif HTTP_REFERER and HTTP_REFERER.endswith("work-type-request-view/"):
        close_hx_url = f"/work-type-request-search?{previous_data}"
        close_hx_target = "#view-container"
    elif HTTP_REFERER and HTTP_REFERER.endswith("employee-profile/"):
        close_hx_url = f"/employee/shift-tab/{employee}?profile=true"
        close_hx_target = "#shift_target"
    elif HTTP_REFERER:
        HTTP_REFERERS = [part for part in HTTP_REFERER.split("/") if part]
        try:
            employee_id = int(HTTP_REFERERS[-1])
            close_hx_url = f"/employee/shift-tab/{employee_id}"
            close_hx_target = "#shift_target"
        except ValueError:
            pass
    return close_hx_url, close_hx_target


@login_required
@hx_request_required
def work_type_request(request):
    """
    This method is used to create request for work type  .
    """
    encoded_data = request.GET.urlencode()
    previous_data = unquote(encoded_data.replace("pd=", ""))
    form = WorkTypeRequestForm()
    employee = request.user.employee_get.id
    if request.GET.get("emp_id"):
        employee = request.GET.get("emp_id")
    form = WorkTypeRequestForm(initial={"employee_id": employee})
    form = choosesubordinates(
        request,
        form,
        "base.add_worktyperequest",
    )
    form = include_employee_instance(request, form)

    f = WorkTypeRequestFilter()
    context = {"f": f, "pd": previous_data}
    context["close_hx_url"], context["close_hx_target"] = handle_wtr_close_hx_url(
        request
    )
    if request.method == "POST":
        form = WorkTypeRequestForm(request.POST)
        form = choosesubordinates(
            request,
            form,
            "base.add_worktyperequest",
        )
        form = include_employee_instance(request, form)
        if form.is_valid():
            instance = form.save()
            try:
                notify.send(
                    instance.employee_id,
                    recipient=(
                        instance.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                    ),
                    verb=f"You have new work type request to \
                            validate for {instance.employee_id}",
                    verb_ar=f"لديك طلب نوع وظيفة جديد للتحقق من \
                            {instance.employee_id}",
                    verb_de=f"Sie haben eine neue Arbeitstypanfrage zur \
                            Validierung für {instance.employee_id}",
                    verb_es=f"Tiene una nueva solicitud de tipo de trabajo para \
                            validar para {instance.employee_id}",
                    verb_fr=f"Vous avez une nouvelle demande de type de travail\
                            à valider pour {instance.employee_id}",
                    icon="information",
                    redirect=reverse("work-type-request-view") + f"?id={instance.id}",
                )
            except Exception as error:
                pass
            messages.success(request, _("Work type request added."))
            work_type_requests = WorkTypeRequest.objects.all()
            if len(work_type_requests) == 1:
                return HorillaRedirect(request)
            form = WorkTypeRequestForm()
    context["form"] = form
    return render(request, "work_type_request/request_form.html", context=context)


def handle_wtr_redirect(request, work_type_request):
    hx_request = request.META.get("HTTP_HX_REQUEST") == "true"
    if not hx_request:
        return HorillaRedirect(request)

    current_url = "/" + "/".join(
        request.META.get("HTTP_HX_CURRENT_URL", "").split("/")[3:]
    )
    hx_target = request.META.get("HTTP_HX_TARGET")

    if not current_url:
        return HorillaRedirect(request)

    if hx_target == "objectDetailsModalTarget":
        instances_ids = request.GET.get("instances_ids")
        dashboard = request.GET.get("dashboard")
        url = reverse(
            "work-type-request-single-view",
            kwargs={"obj_id": work_type_request.id},
        )
        return redirect(f"{url}?instances_ids={instances_ids}&dashboard={dashboard}")

    if current_url == "/":
        return redirect(reverse("dashboard-work-type-request"))

    if (
        "/work-type-request-view/" in current_url
        or "/employee/requests/" in current_url
    ):
        return redirect(f"/work-type-request-search?{request.GET.urlencode()}")

    if "/employee-view/" in current_url:
        return redirect(f"/employee/shift-tab/{work_type_request.employee_id.id}")

    return HorillaRedirect(request)


@login_required
def work_type_request_cancel(request, id):
    """
    This method is used to cancel work type request
    args:
        id  : work type request id

    """
    is_ajax = request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"
    work_type_request = WorkTypeRequest.find(id)
    if not work_type_request:
        messages.error(request, _("Work type request not found."))
        return JsonResponse({"result": False}) if is_ajax else HorillaRedirect(request)

    if not (
        is_reportingmanger(request, work_type_request)
        or request.user.has_perm("base.cancel_worktyperequest")
        or work_type_request.employee_id == request.user.employee_get
        and work_type_request.approved == False
    ):
        messages.error(request, _("You don't have permission"))
        return JsonResponse({"result": False}) if is_ajax else HorillaRedirect(request)
    work_type_request.canceled = True
    work_type_request.approved = False
    work_info = EmployeeWorkInformation.objects.filter(
        employee_id=work_type_request.employee_id
    )
    if work_info.exists():
        work_type_request.employee_id.employee_work_info.work_type_id = (
            work_type_request.previous_work_type_id
        )
        work_type_request.employee_id.employee_work_info.save()
    work_type_request.save()
    messages.success(request, _("Work type request has been rejected."))
    notify.send(
        request.user.employee_get,
        recipient=work_type_request.employee_id.employee_user_id,
        verb="Your work type request has been rejected.",
        verb_ar="تم إلغاء طلب نوع وظيفتك",
        verb_de="Ihre Arbeitstypanfrage wurde storniert",
        verb_es="Su solicitud de tipo de trabajo ha sido cancelada",
        verb_fr="Votre demande de type de travail a été annulée",
        redirect=reverse("work-type-request-view") + f"?id={work_type_request.id}",
        icon="close",
    )
    if is_ajax:
        return JsonResponse({"result": True})
    return handle_wtr_redirect(request, work_type_request)


@login_required
@manager_can_enter("base.change_worktyperequest")
def work_type_request_bulk_cancel(request):
    """
    This method is used to cancel a bunch work type request
    """
    ids = request.POST.get("ids")
    if not ids:
        return HorillaRedirect(
            request, message=_("No worktype request found matching the query.")
        )
    ids = json.loads(ids)
    result = False
    for id in ids:
        work_type_request = WorkTypeRequest.objects.get(id=id)
        if (
            is_reportingmanger(request, work_type_request)
            or request.user.has_perm("base.cancel_worktyperequest")
            or work_type_request.employee_id == request.user.employee_get
            and work_type_request.approved == False
        ):
            work_type_request.canceled = True
            work_type_request.approved = False
            work_type_request.employee_id.employee_work_info.work_type_id = (
                work_type_request.previous_work_type_id
            )
            work_type_request.employee_id.employee_work_info.save()
            work_type_request.save()
            messages.success(request, _("Work type request has been canceled."))
            notify.send(
                request.user.employee_get,
                recipient=work_type_request.employee_id.employee_user_id,
                verb="Your work type request has been canceled.",
                verb_ar="تم إلغاء طلب نوع وظيفتك.",
                verb_de="Ihre Arbeitstypanfrage wurde storniert.",
                verb_es="Su solicitud de tipo de trabajo ha sido cancelada.",
                verb_fr="Votre demande de type de travail a été annulée.",
                redirect=reverse("work-type-request-view")
                + f"?id={work_type_request.id}",
                icon="close",
            )
            result = True
    return JsonResponse({"result": result})


@login_required
def work_type_request_approve(request, id):
    """
    This method is used to approve requested work type
    """

    is_ajax = request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"
    work_type_request = WorkTypeRequest.find(id)
    if not work_type_request:
        messages.error(request, _("Work type request not found."))
        return JsonResponse({"result": False}) if is_ajax else HorillaRedirect(request)
    if not (
        (
            is_reportingmanger(request, work_type_request)
            or request.user.has_perm("base.approve_worktyperequest")
            or request.user.has_perm("base.change_worktyperequest")
        )
        and not work_type_request.approved
    ):
        messages.error(request, _("You don't have permission"))
        return JsonResponse({"result": False}) if is_ajax else HorillaRedirect(request)
    """
    Here the request will be approved, can send mail right here
    """
    if not work_type_request.is_any_work_type_request_exists():
        work_type_request.approved = True
        work_type_request.canceled = False
        work_type_request.save()
        messages.success(request, _("Work type request has been approved."))
        notify.send(
            request.user.employee_get,
            recipient=work_type_request.employee_id.employee_user_id,
            verb="Your work type request has been approved.",
            verb_ar="تمت الموافقة على طلب نوع وظيفتك.",
            verb_de="Ihre Arbeitstypanfrage wurde genehmigt.",
            verb_es="Su solicitud de tipo de trabajo ha sido aprobada.",
            verb_fr="Votre demande de type de travail a été approuvée.",
            redirect=reverse("work-type-request-view") + f"?id={work_type_request.id}",
            icon="checkmark",
        )
        if is_ajax:
            return JsonResponse({"result": True})
    else:
        messages.error(
            request,
            _("An approved work type request already exists during this time period."),
        )
        if is_ajax:
            return JsonResponse({"result": False})
    return handle_wtr_redirect(request, work_type_request)


@login_required
def work_type_request_bulk_approve(request):
    """
    This method is used to approve bulk of requested work type
    """
    ids = request.POST.get("ids")
    if not ids:
        return HorillaRedirect(
            request, message=_("No worktype request found matching the query.")
        )
    ids = json.loads(ids)
    result = False
    for id in ids:
        work_type_request = WorkTypeRequest.objects.get(id=id)
        if (
            is_reportingmanger(request, work_type_request)
            or request.user.has_perm("base.approve_worktyperequest")
            or request.user.has_perm("base.change_worktyperequest")
        ) and not work_type_request.approved:
            # """
            # Here the request will be approved, can send mail right here
            # """
            work_type_request.approved = True
            work_type_request.canceled = False
            employee_work_info = work_type_request.employee_id.employee_work_info
            employee_work_info.work_type_id = work_type_request.work_type_id
            employee_work_info.save()
            work_type_request.save()
            messages.success(request, _("Work type request has been approved."))
            notify.send(
                request.user.employee_get,
                recipient=work_type_request.employee_id.employee_user_id,
                verb="Your work type request has been approved.",
                verb_ar="تمت الموافقة على طلب نوع وظيفتك.",
                verb_de="Ihre Arbeitstypanfrage wurde genehmigt.",
                verb_es="Su solicitud de tipo de trabajo ha sido aprobada.",
                verb_fr="Votre demande de type de travail a été approuvée.",
                redirect=reverse("work-type-request-view")
                + f"?id={work_type_request.id}",
                icon="checkmark",
            )
            result = True
    return JsonResponse({"result": result})


@login_required
@hx_request_required
@work_type_request_change_permission()
def work_type_request_update(request, work_type_request_id):
    """
    This method is used to update work type request instance
    args:
        id : work type request instance id

    """
    work_type_request = WorkTypeRequest.objects.get(id=work_type_request_id)
    form = WorkTypeRequestForm(instance=work_type_request)
    form = choosesubordinates(request, form, "base.change_worktyperequest")
    form = include_employee_instance(request, form)
    if request.method == "POST":
        form = WorkTypeRequestForm(request.POST, instance=work_type_request)
        form = choosesubordinates(request, form, "base.change_worktyperequest")
        form = include_employee_instance(request, form)
        if form.is_valid():
            form.save()
            messages.success(request, _("Request Updated Successfully"))
            return HorillaRedirect(request)

    return render(request, "work_type_request/request_form.html", {"form": form})


@login_required
@hx_request_required
@require_http_methods(["POST"])
def work_type_request_delete(request, obj_id):
    """
    This method is used to delete work type request
    args:
        id : work type request instance id

    """

    try:
        work_type_request = WorkTypeRequest.objects.get(id=obj_id)
        employee = work_type_request.employee_id
        messages.success(request, _("Work type request deleted."))
        work_type_request.delete()
        notify.send(
            request.user.employee_get,
            recipient=employee.employee_user_id,
            verb="Your work type request has been deleted.",
            verb_ar="تم حذف طلب نوع وظيفتك.",
            verb_de="Ihre Arbeitstypanfrage wurde gelöscht.",
            verb_es="Su solicitud de tipo de trabajo ha sido eliminada.",
            verb_fr="Votre demande de type de travail a été supprimée.",
            redirect="#",
            icon="trash",
        )
    except WorkTypeRequest.DoesNotExist:
        employee = None
        messages.error(request, _("Work type request not found."))
    except ProtectedError:
        messages.error(request, _("You cannot delete this work type request."))

    hx_target = request.META.get("HTTP_HX_TARGET", None)
    hx_current_url = request.META.get("HTTP_HX_CURRENT_URL", None)
    parsed_url = urlparse(hx_current_url)
    hx_current_path = parsed_url.path.lstrip("/")
    if hx_target and hx_target == "genericModalBody":
        instances_ids = request.GET.get("instances_ids")
        instances_list = json.loads(instances_ids)
        if obj_id in instances_list:
            instances_list.remove(obj_id)
        previous_instance, next_instance = closest_numbers(
            json.loads(instances_ids), obj_id
        )
        previous_data = request.GET.urlencode()
        return redirect(
            f"/work-detail-view/{next_instance}/?{previous_data}&instance_ids={instances_list}&deleted=true"
        )
    # elif hx_target and hx_target == "listContainer":
    #     previous_data = request.GET.urlencode()
    #     work_type_requests = WorkTypeRequest.objects.all()
    #     if work_type_requests.exists():
    #         return redirect(f"/work-list-view?{previous_data}")
    #     else:
    #         return HttpResponse("<script>window.location.reload()</script>")

    elif hx_target and hx_target == "work-shift":
        if hx_current_path in (
            "employee/work-type-request-view/",
            "employee/requests/",
        ):
            work_type_requests = WorkTypeRequest.objects.all()
            previous_data = request.GET.urlencode()
            if work_type_requests.exists():
                return redirect(f"/work-list-view?{previous_data}")
            else:
                return HorillaRedirect(request)
        else:
            return redirect(f"/employeeprofileview-Work Type & Shift/{employee.id}")

    elif hx_target and hx_target == "shift_target" and employee:
        return redirect(f"/employee/shift-tab/{employee.id}")

    else:
        return HorillaRedirect(request)


@login_required
@hx_request_required
def work_type_request_single_view(request, obj_id):
    """
    This method is used to view details of an work type request
    """
    work_type_request = WorkTypeRequest.objects.filter(id=obj_id).first()
    context = {
        "work_type_request": work_type_request,
        "dashboard": request.GET.get("dashboard"),
    }
    requests_ids_json = request.GET.get("instances_ids")
    if requests_ids_json:
        requests_ids = json.loads(requests_ids_json)
        previous_id, next_id = closest_numbers(requests_ids, obj_id)
        context["requests_ids"] = requests_ids_json
        context["previous"] = previous_id
        context["next"] = next_id
    context["close_hx_url"], context["close_hx_target"] = handle_wtr_close_hx_url(
        request
    )
    return render(
        request,
        "work_type_request/htmx/work_type_request_single_view.html",
        context,
    )


@login_required
@permission_required("base.delete_worktyperequest")
@require_http_methods(["POST"])
def work_type_request_bulk_delete(request):
    """
    This method is used to delete work type request
    args:
        id : work type request instance id

    """
    ids = request.POST["ids"]
    ids = json.loads(ids)
    del_ids = []
    for id in ids:
        try:
            work_type_request = WorkTypeRequest.objects.get(id=id)
            user = work_type_request.employee_id.employee_user_id
            work_type_request.delete()
            del_ids.append(work_type_request)
            notify.send(
                request.user.employee_get,
                recipient=user,
                verb="Your work type request has been deleted.",
                verb_ar="تم حذف طلب نوع وظيفتك.",
                verb_de="Ihre Arbeitstypanfrage wurde gelöscht.",
                verb_es="Su solicitud de tipo de trabajo ha sido eliminada.",
                verb_fr="Votre demande de type de travail a été supprimée.",
                redirect="#",
                icon="trash",
            )
        except WorkTypeRequest.DoesNotExist:
            messages.error(request, _("Work type request not found."))
        except ProtectedError:
            messages.error(
                request,
                _(
                    "You cannot delete {employee} work type request for the date {date}."
                ).format(
                    employee=work_type_request.employee_id,
                    date=work_type_request.requested_date,
                ),
            )
        result = True
    messages.success(request, _("{} work type requests deleted.".format(len(del_ids))))
    return JsonResponse({"result": result})


@login_required
@hx_request_required
def shift_request(request):
    """
    This method is used to create shift request
    """
    form = ShiftRequestForm()
    employee = request.user.employee_get.id
    if request.GET.get("emp_id"):
        employee = request.GET.get("emp_id")

    form = ShiftRequestForm(initial={"employee_id": employee})
    form = choosesubordinates(
        request,
        form,
        "base.add_shiftrequest",
    )
    form = include_employee_instance(request, form)
    f = ShiftRequestFilter()
    if request.method == "POST":
        form = ShiftRequestForm(request.POST)
        form = choosesubordinates(request, form, "base.add_shiftrequest")
        form = include_employee_instance(request, form)

        if form.is_valid():
            instance = form.save()
            try:
                notify.send(
                    instance.employee_id,
                    recipient=(
                        instance.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                    ),
                    verb=f"You have new shift request to approve \
                        for {instance.employee_id}",
                    verb_ar=f"لديك طلب وردية جديد للموافقة عليه لـ {instance.employee_id}",
                    verb_de=f"Sie müssen eine neue Schichtanfrage \
                        für {instance.employee_id} genehmigen",
                    verb_es=f"Tiene una nueva solicitud de turno para \
                        aprobar para {instance.employee_id}",
                    verb_fr=f"Vous avez une nouvelle demande de quart de\
                        travail à approuver pour {instance.employee_id}",
                    icon="information",
                    redirect=reverse("shift-request-view") + f"?id={instance.id}",
                )
            except Exception as e:
                pass
            messages.success(request, _("Shift request added"))
            return HorillaRedirect(request)
    return render(
        request,
        "shift_request/htmx/shift_request_create_form.html",
        {"form": form, "f": f},
    )


@login_required
def update_employee_allocation(request):

    shift = request.GET.get("shift_id")
    if not shift:
        return HorillaRedirect(request, message=_("No shift found matching the query."))
    form = ShiftAllocationForm()
    shift = EmployeeShift.objects.filter(id=shift).first()
    employee_ids = shift.employeeworkinformation_set.values_list(
        "employee_id", flat=True
    )
    employees = Employee.objects.filter(id__in=employee_ids)
    form.fields["reallocate_to"].queryset = employees
    context = {"form": form}
    html_template = render_to_string(
        "shift_request/htmx/shift_reallocate_employees.html", context
    )
    return HttpResponse(html_template)


@login_required
@hx_request_required
def shift_request_allocation(request):
    """
    This method is used to create shift request reallocation
    """
    form = ShiftAllocationForm()
    if request.GET.get("emp_id"):
        employee = request.GET.get("emp_id")
        form = ShiftAllocationForm(initial={"employee_id": employee})
    form = choosesubordinates(
        request,
        form,
        "base.add_shiftrequest",
    )
    form = include_employee_instance(request, form)
    f = ShiftRequestFilter()
    if request.method == "POST":
        form = ShiftAllocationForm(request.POST)
        form = choosesubordinates(request, form, "base.add_shiftrequest")
        form = include_employee_instance(request, form)

        if form.is_valid():
            instance = form.save()
            reallocate_emp = form.cleaned_data["reallocate_to"]
            try:
                notify.send(
                    instance.employee_id,
                    recipient=(
                        instance.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                    ),
                    verb=f"You have a new shift reallocation request to approve for {instance.employee_id}.",
                    verb_ar=f"لديك طلب تخصيص جديد للورديات يتعين عليك الموافقة عليه لـ {instance.employee_id}.",
                    verb_de=f"Sie haben eine neue Anfrage zur Verschiebung der Schichtzuteilung zur Genehmigung für {instance.employee_id}.",
                    verb_es=f"Tienes una nueva solicitud de reasignación de turnos para aprobar para {instance.employee_id}.",
                    verb_fr=f"Vous avez une nouvelle demande de réaffectation de shift à approuver pour {instance.employee_id}.",
                    icon="information",
                    redirect=reverse("shift-request-view") + f"?id={instance.id}",
                )
            except Exception as e:
                pass

            try:
                notify.send(
                    instance.employee_id,
                    recipient=reallocate_emp,
                    verb=f"You have a new shift reallocation request from {instance.employee_id}.",
                    verb_ar=f"لديك طلب تخصيص جديد للورديات من {instance.employee_id}.",
                    verb_de=f"Sie haben eine neue Anfrage zur Verschiebung der Schichtzuteilung von {instance.employee_id}.",
                    verb_es=f"Tienes una nueva solicitud de reasignación de turnos de {instance.employee_id}.",
                    verb_fr=f"Vous avez une nouvelle demande de réaffectation de shift de {instance.employee_id}.",
                    icon="information",
                    redirect=reverse("shift-request-view") + f"?id={instance.id}",
                )
            except Exception as e:
                pass

            messages.success(request, _("Request Added"))
            return HorillaRedirect(request)
    return render(
        request,
        "shift_request/htmx/shift_allocation_form.html",
        {"form": form, "f": f},
    )


@login_required
def shift_request_view(request):
    """
    This method renders all shift request instances to a template
    """
    previous_data = request.GET.urlencode()
    employee = Employee.objects.filter(employee_user_id=request.user).first()
    shift_requests = filtersubordinates(
        request,
        ShiftRequest.objects.filter(reallocate_to__isnull=True),
        "base.view_shiftrequest",
    )
    shift_requests = shift_requests | ShiftRequest.objects.filter(employee_id=employee)
    shift_requests = shift_requests.filter(employee_id__is_active=True)

    allocated_shift_requests = filtersubordinates(
        request,
        ShiftRequest.objects.filter(reallocate_to__isnull=False),
        "base.view_shiftrequest",
    )
    allocated_requests = ShiftRequest.objects.filter(reallocate_to__isnull=False)
    if not request.user.has_perm("base.view_shiftrequest"):
        allocated_requests = allocated_requests.filter(
            Q(reallocate_to=employee) | Q(employee_id=employee)
        )
    allocated_shift_requests = allocated_shift_requests | allocated_requests

    requests_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                shift_requests, request.GET.get("page")
            ).object_list
        ]
    )
    allocated_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                allocated_shift_requests, request.GET.get("page")
            ).object_list
        ]
    )
    f = ShiftRequestFilter(request.GET, queryset=shift_requests)
    data_dict = parse_qs(previous_data)
    get_key_instances(ShiftRequest, data_dict)
    form = ShiftRequestForm()

    form = choosesubordinates(
        request,
        form,
        "base.add_shiftrequest",
    )
    form = include_employee_instance(request, form)
    return render(
        request,
        "shift_request/shift_request_view.html",
        {
            "allocated_data": paginator_qry(
                allocated_shift_requests, request.GET.get("page")
            ),
            "data": paginator_qry(f.qs, request.GET.get("page")),
            "f": f,
            "form": form,
            "filter_dict": data_dict,
            "requests_ids": requests_ids,
            "allocated_ids": allocated_ids,
            "gp_fields": ShiftRequestReGroup.fields,
        },
    )


@login_required
@manager_can_enter("base.view_shiftrequest")
def shift_request_export(request):
    if request.META.get("HTTP_HX_REQUEST") == "true":
        export_fields = ShiftRequestColumnForm()
        export_filter = ShiftRequestFilter()

        context = {
            "export_fields": export_fields,
            "export_filter": export_filter,
        }
        return render(
            request, "shift_request/shift_request_export.html", context=context
        )
    return export_data(
        request,
        ShiftRequest,
        ShiftRequestColumnForm,
        ShiftRequestFilter,
        "Shift_requests",
    )


@login_required
@hx_request_required
def shift_request_search(request):
    """
    This method is used search shift request by employee and also used to filter shift request.
    """

    employee = Employee.objects.filter(employee_user_id=request.user).first()
    previous_data = request.GET.urlencode()
    field = request.GET.get("field")
    f = ShiftRequestFilter(request.GET)
    f = sortby(request, f.qs, "sortby")
    shift_requests = filtersubordinates(
        request, f.filter(reallocate_to__isnull=True), "base.add_shiftrequest"
    )
    shift_requests = shift_requests | f.filter(
        employee_id__employee_user_id=request.user
    )

    allocated_shift_requests = filtersubordinates(
        request, f.filter(reallocate_to__isnull=False), "base.add_shiftrequest"
    )
    if not request.user.has_perm("base.view_shiftrequest"):
        allocated_shift_requests = allocated_shift_requests | f.filter(
            Q(reallocate_to=employee) | Q(employee_id=employee)
        )

    requests_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                shift_requests, request.GET.get("page")
            ).object_list
        ]
    )

    allocated_ids = json.dumps(
        [
            instance.id
            for instance in paginator_qry(
                allocated_shift_requests, request.GET.get("page")
            ).object_list
        ]
    )

    data_dict = parse_qs(previous_data)
    template = "shift_request/htmx/requests.html"
    if field != "" and field is not None:
        shift_requests = group_by_queryset(
            shift_requests, field, request.GET.get("page"), "page"
        )
        allocated_shift_requests = group_by_queryset(
            allocated_shift_requests, field, request.GET.get("page"), "page"
        )
        shift_list_values = [entry["list"] for entry in shift_requests]
        allocated_list_values = [entry["list"] for entry in allocated_shift_requests]
        shift_id_list = []
        allocated_id_list = []

        for value in shift_list_values:
            for instance in value.object_list:
                shift_id_list.append(instance.id)

        for value in allocated_list_values:
            for instance in value.object_list:
                allocated_id_list.append(instance.id)

        requests_ids = json.dumps(list(shift_id_list))
        allocated_ids = json.dumps(list(allocated_id_list))
        template = "shift_request/htmx/group_by.html"

    else:
        shift_requests = paginator_qry(shift_requests, request.GET.get("page"))
        allocated_shift_requests = paginator_qry(
            allocated_shift_requests, request.GET.get("page")
        )
        requests_ids = json.dumps(
            [
                instance.id
                for instance in paginator_qry(
                    shift_requests, request.GET.get("page")
                ).object_list
            ]
        )

        allocated_ids = json.dumps(
            [
                instance.id
                for instance in paginator_qry(
                    allocated_shift_requests, request.GET.get("page")
                ).object_list
            ]
        )

    get_key_instances(ShiftRequest, data_dict)
    return render(
        request,
        template,
        {
            "allocated_data": allocated_shift_requests,
            "data": paginator_qry(shift_requests, request.GET.get("page")),
            "pd": previous_data,
            "filter_dict": data_dict,
            "requests_ids": requests_ids,
            "allocated_ids": allocated_ids,
            "field": field,
        },
    )


@login_required
@hx_request_required
def shift_request_details(request, id):
    """
    This method is used to show shift request details in a modal
    args:
        id : shift request instance id
    """
    shift_request = ShiftRequest.find(id)
    if not shift_request:
        messages.error(request, _("Shift request not found."))
        return HorillaRedirect(request)
    requests_ids_json = request.GET.get("instances_ids")
    context = {
        "shift_request": shift_request,
        "dashboard": request.GET.get("dashboard"),
    }
    if requests_ids_json:
        requests_ids = json.loads(requests_ids_json)
        previous_id, next_id = closest_numbers(requests_ids, id)
        context["previous"] = previous_id
        context["next"] = next_id
        context["requests_ids"] = requests_ids_json
    return render(
        request,
        "shift_request/htmx/shift_request_detail.html",
        context,
    )


@login_required
@hx_request_required
def shift_allocation_request_details(request, id):
    """
    This method is used to show shift request details in a modal
    args:
        id : shift request instance id
    """
    shift_request = ShiftRequest.find(id)
    if not shift_request:
        messages.error(request, _("Shift request not found."))
        return HorillaRedirect(request)
    requests_ids_json = request.GET.get("instances_ids")
    context = {
        "shift_request": shift_request,
        "dashboard": request.GET.get("dashboard"),
    }
    if requests_ids_json:
        requests_ids = json.loads(requests_ids_json)
        previous_id, next_id = closest_numbers(requests_ids, id)
        context["previous"] = previous_id
        context["next"] = next_id
        context["allocation_ids"] = requests_ids_json
    return render(
        request,
        "shift_request/htmx/allocation_details.html",
        context,
    )


@login_required
@hx_request_required
@shift_request_change_permission()
def shift_request_update(request, shift_request_id):
    """
    This method is used to update shift request instance
    args:
        id : shift request instance id
    """
    shift_request = ShiftRequest.objects.get(id=shift_request_id)
    form = ShiftRequestForm(instance=shift_request)
    form = choosesubordinates(request, form, "base.change_shiftrequest")
    form = include_employee_instance(request, form)
    if request.method == "POST":
        if not shift_request.approved:

            form = ShiftRequestForm(request.POST, instance=shift_request)
            form = choosesubordinates(request, form, "base.change_shiftrequest")
            form = include_employee_instance(request, form)
            if form.is_valid():
                form.save()
                messages.success(request, _("Request Updated Successfully"))
                return HorillaRedirect(request)
        else:
            messages.info(request, _("Can't edit approved shift request"))
            return HorillaRedirect(request)

    return render(request, "shift_request/request_update_form.html", {"form": form})


@login_required
def shift_allocation_request_update(request, shift_request_id):
    """
    This method is used to update shift request instance
    args:
        id : shift request instance id
    """
    shift_request = ShiftRequest.objects.get(id=shift_request_id)
    form = ShiftAllocationForm(instance=shift_request)
    form = choosesubordinates(request, form, "base.change_shiftrequest")
    form = include_employee_instance(request, form)
    if request.method == "POST":
        response = render(
            request,
            "shift_request/request_update_form.html",
            {
                "form": form,
            },
        )
        form = ShiftAllocationForm(request.POST, instance=shift_request)
        form = choosesubordinates(request, form, "base.change_shiftrequest")
        form = include_employee_instance(request, form)
        if form.is_valid():
            form.save()
            instance = form.save()
            reallocate_emp = form.cleaned_data["reallocate_to"]
            try:
                notify.send(
                    instance.employee_id,
                    recipient=(
                        instance.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                    ),
                    verb=f"You have a new shift reallocation request to approve for {instance.employee_id}.",
                    verb_ar=f"لديك طلب تخصيص جديد للورديات يتعين عليك الموافقة عليه لـ {instance.employee_id}.",
                    verb_de=f"Sie haben eine neue Anfrage zur Verschiebung der Schichtzuteilung zur Genehmigung für {instance.employee_id}.",
                    verb_es=f"Tienes una nueva solicitud de reasignación de turnos para aprobar para {instance.employee_id}.",
                    verb_fr=f"Vous avez une nouvelle demande de réaffectation de shift à approuver pour {instance.employee_id}.",
                    icon="information",
                    redirect=reverse("shift-request-view") + f"?id={instance.id}",
                )
            except Exception as e:
                pass

            try:
                notify.send(
                    instance.employee_id,
                    recipient=reallocate_emp,
                    verb=f"You have a new shift reallocation request from {instance.employee_id}.",
                    verb_ar=f"لديك طلب تخصيص جديد للورديات من {instance.employee_id}.",
                    verb_de=f"Sie haben eine neue Anfrage zur Verschiebung der Schichtzuteilung von {instance.employee_id}.",
                    verb_es=f"Tienes una nueva solicitud de reasignación de turnos de {instance.employee_id}.",
                    verb_fr=f"Vous avez une nouvelle demande de réaffectation de shift de {instance.employee_id}.",
                    icon="information",
                    redirect=reverse("shift-request-view") + f"?id={instance.id}",
                )
            except Exception as e:
                pass
            messages.success(request, _("Request Updated Successfully"))
            return HttpResponse(
                response.content.decode("utf-8") + "<script>location.reload();</script>"
            )

    return render(
        request, "shift_request/allocation_request_update_form.html", {"form": form}
    )


@login_required
def shift_request_cancel(request, id):
    """
    This method is used to update or cancel shift request
    args:
        id : shift request id

    """

    is_ajax = request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"
    shift_request = ShiftRequest.find(id)
    if not shift_request:
        messages.error(request, _("Shift request not found."))
        return JsonResponse({"result": False}) if is_ajax else HorillaRedirect(request)
    if not (
        is_reportingmanger(request, shift_request)
        or request.user.has_perm("base.cancel_shiftrequest")
        or shift_request.employee_id == request.user.employee_get
        and shift_request.approved == False
    ):
        messages.error(request, _("You don't have permission"))
        return JsonResponse({"result": False}) if is_ajax else HorillaRedirect(request)
    today_date = datetime.today().date()
    if (
        shift_request.approved
        and shift_request.requested_date <= today_date <= shift_request.requested_till
        and not shift_request.is_permanent_shift
    ):
        shift_request.employee_id.employee_work_info.shift_id = (
            shift_request.previous_shift_id
        )
        shift_request.employee_id.employee_work_info.save()
    shift_request.canceled = True
    shift_request.approved = False
    work_info = EmployeeWorkInformation.objects.filter(
        employee_id=shift_request.employee_id
    )
    if work_info.exists():
        shift_request.employee_id.employee_work_info.shift_id = (
            shift_request.previous_shift_id
        )
    if shift_request.reallocate_to and work_info.exists():
        shift_request.reallocate_to.employee_work_info.shift_id = shift_request.shift_id
        shift_request.reallocate_to.employee_work_info.save()
    if work_info.exists():
        shift_request.employee_id.employee_work_info.save()
    shift_request.save()
    messages.success(request, _("Shift request rejected"))
    notify.send(
        request.user.employee_get,
        recipient=shift_request.employee_id.employee_user_id,
        verb="Your shift request has been canceled.",
        verb_ar="تم إلغاء طلبك للوردية.",
        verb_de="Ihr Schichtantrag wurde storniert.",
        verb_es="Se ha cancelado su solicitud de turno.",
        verb_fr="Votre demande de quart a été annulée.",
        redirect=reverse("shift-request-view") + f"?id={shift_request.id}",
        icon="close",
    )
    if shift_request.reallocate_to:
        notify.send(
            request.user.employee_get,
            recipient=shift_request.reallocate_to.employee_user_id,
            verb="Your shift request has been rejected.",
            verb_ar="تم إلغاء طلبك للوردية.",
            verb_de="Ihr Schichtantrag wurde storniert.",
            verb_es="Se ha cancelado su solicitud de turno.",
            verb_fr="Votre demande de quart a été annulée.",
            redirect=reverse("shift-request-view") + f"?id={shift_request.id}",
            icon="close",
        )
    return JsonResponse({"result": True}) if is_ajax else HorillaRedirect(request)


@login_required
def shift_allocation_request_cancel(request, id):
    """
    This method is used to update or cancel shift request
    args:
        id : shift request id

    """

    shift_request = ShiftRequest.find(id)
    if not shift_request:
        return HorillaRedirect(
            request, message=_("No shift request found matching the query.")
        )

    shift_request.reallocate_canceled = True
    shift_request.reallocate_approved = False
    work_info = EmployeeWorkInformation.objects.filter(
        employee_id=shift_request.employee_id
    )
    if work_info.exists():
        shift_request.employee_id.employee_work_info.shift_id = (
            shift_request.previous_shift_id
        )
        shift_request.employee_id.employee_work_info.save()
    shift_request.save()
    messages.success(request, _("Shift request canceled"))
    notify.send(
        request.user.employee_get,
        recipient=shift_request.employee_id.employee_user_id,
        verb="Your shift request has been canceled.",
        verb_ar="تم إلغاء طلبك للوردية.",
        verb_de="Ihr Schichtantrag wurde storniert.",
        verb_es="Se ha cancelado su solicitud de turno.",
        verb_fr="Votre demande de quart a été annulée.",
        redirect=reverse("shift-request-view") + f"?id={shift_request.id}",
        icon="close",
    )

    return HorillaRedirect(request)


@login_required
@manager_can_enter("base.change_shiftrequest")
@require_http_methods(["POST"])
def shift_request_bulk_cancel(request):
    """
    This method is used to cancel a bunch of shift request.
    """
    ids = request.POST["ids"]
    ids = json.loads(ids)
    result = False
    for id in ids:
        shift_request = ShiftRequest.objects.get(id=id)
        if (
            is_reportingmanger(request, shift_request)
            or request.user.has_perm("base.cancel_shiftrequest")
            or shift_request.employee_id == request.user.employee_get
            and shift_request.approved == False
        ):
            shift_request.canceled = True
            shift_request.approved = False
            shift_request.employee_id.employee_work_info.shift_id = (
                shift_request.previous_shift_id
            )

            if shift_request.reallocate_to:
                shift_request.reallocate_to.employee_work_info.shift_id = (
                    shift_request.shift_id
                )
                shift_request.reallocate_to.employee_work_info.save()

            shift_request.employee_id.employee_work_info.save()
            shift_request.save()
            messages.success(request, _("Shift request canceled"))
            notify.send(
                request.user.employee_get,
                recipient=shift_request.employee_id.employee_user_id,
                verb="Your shift request has been canceled.",
                verb_ar="تم إلغاء طلبك للوردية.",
                verb_de="Ihr Schichtantrag wurde storniert.",
                verb_es="Se ha cancelado su solicitud de turno.",
                verb_fr="Votre demande de quart a été annulée.",
                redirect=reverse("shift-request-view") + f"?id={shift_request.id}",
                icon="close",
            )
            if shift_request.reallocate_to:
                notify.send(
                    request.user.employee_get,
                    recipient=shift_request.employee_id.employee_user_id,
                    verb="Your shift request has been canceled.",
                    verb_ar="تم إلغاء طلبك للوردية.",
                    verb_de="Ihr Schichtantrag wurde storniert.",
                    verb_es="Se ha cancelado su solicitud de turno.",
                    verb_fr="Votre demande de quart a été annulée.",
                    redirect=reverse("shift-request-view") + f"?id={shift_request.id}",
                    icon="close",
                )
            result = True
    return JsonResponse({"result": result})


@login_required
@manager_can_enter("base.change_shiftrequest")
def shift_request_approve(request, id):
    """
    Approve shift request
    args:
        id : shift request instance id
    """

    is_ajax = request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"
    shift_request = ShiftRequest.find(id)
    if not shift_request:
        messages.error(request, _("Shift request not found."))
        return JsonResponse({"result": False}) if is_ajax else HorillaRedirect(request)

    user = request.user
    if not (
        (
            is_reportingmanger(request, shift_request)
            or user.has_perm("base.approve_shiftrequest")
            or user.has_perm("base.change_shiftrequest")
        )
        and not shift_request.approved
    ):
        messages.error(request, _("You don't have permission"))
        return JsonResponse({"result": False}) if is_ajax else HorillaRedirect(request)

    if shift_request.is_any_request_exists():
        messages.error(
            request,
            _("An approved shift request already exists during this time period."),
        )
        return JsonResponse({"result": False}) if is_ajax else HorillaRedirect(request)

    today_date = datetime.today().date()
    if not shift_request.is_permanent_shift:
        if shift_request.requested_date <= today_date <= shift_request.requested_till:
            shift_request.employee_id.employee_work_info.shift_id = (
                shift_request.shift_id
            )
            shift_request.employee_id.employee_work_info.save()
    shift_request.approved = True
    shift_request.canceled = False

    if shift_request.reallocate_to:
        shift_request.reallocate_to.employee_work_info.shift_id = (
            shift_request.previous_shift_id
        )
        shift_request.reallocate_to.employee_work_info.save()

    shift_request.save()
    messages.success(request, _("Shift has been approved."))

    recipients = [shift_request.employee_id.employee_user_id]
    if shift_request.reallocate_to:
        recipients.append(shift_request.reallocate_to.employee_user_id)

    for recipient in recipients:
        notify.send(
            user.employee_get,
            recipient=recipient,
            verb="Your shift request has been approved.",
            verb_ar="تمت الموافقة على طلبك للوردية.",
            verb_de="Ihr Schichtantrag wurde genehmigt.",
            verb_es="Se ha aprobado su solicitud de turno.",
            verb_fr="Votre demande de quart a été approuvée.",
            redirect=reverse("shift-request-view") + f"?id={shift_request.id}",
            icon="checkmark",
        )

    return JsonResponse({"result": True}) if is_ajax else HorillaRedirect(request)


@login_required
def shift_allocation_request_approve(request, id):
    """
    This method is used to approve shift request
    args:
        id : shift request instance id
    """

    shift_request = ShiftRequest.find(id)
    if not shift_request:
        return HorillaRedirect(
            request, message=_("No shift request found matching the query.")
        )

    if not shift_request.is_any_request_exists():
        shift_request.reallocate_approved = True
        shift_request.reallocate_canceled = False
        shift_request.save()
        messages.success(request, _("You are available for shift reallocation."))
        notify.send(
            request.user.employee_get,
            recipient=shift_request.employee_id.employee_user_id,
            verb=f"{request.user.employee_get} is available for shift reallocation.",
            verb_ar=f"{request.user.employee_get} متاح لإعادة توزيع الورديات.",
            verb_de=f"{request.user.employee_get} steht für die Verschiebung der Schichtzuteilung zur Verfügung.",
            verb_es=f"{request.user.employee_get} está disponible para la reasignación de turnos.",
            verb_fr=f"{request.user.employee_get} est disponible pour la réaffectation de shift.",
            redirect=reverse("shift-request-view") + f"?id={shift_request.id}",
            icon="checkmark",
        )
        return HorillaRedirect(request)
    else:
        messages.error(
            request,
            _("An approved shift request already exists during this time period."),
        )
        return HorillaRedirect(request)


@login_required
@require_http_methods(["POST"])
@manager_can_enter("base.change_shiftrequest")
def shift_request_bulk_approve(request):
    """
    This method is used to approve a bunch of shift request
    """
    ids = request.POST["ids"]
    ids = json.loads(ids)
    result = False
    for id in ids:
        shift_request = ShiftRequest.objects.get(id=id)
        if (
            is_reportingmanger(request, shift_request)
            or request.user.has_perm("base.approve_shiftrequest")
            or request.user.has_perm("base.change_shiftrequest")
        ) and not shift_request.approved:
            """
            here the request will be approved, can send mail right here
            """
            shift_request.approved = True
            shift_request.canceled = False

            if shift_request.reallocate_to:
                shift_request.reallocate_to.employee_work_info.shift_id = (
                    shift_request.previous_shift_id
                )
                shift_request.reallocate_to.employee_work_info.save()

            employee_work_info = shift_request.employee_id.employee_work_info
            employee_work_info.shift_id = shift_request.shift_id
            employee_work_info.save()
            shift_request.save()
            messages.success(request, _("Shifts have been approved."))
            notify.send(
                request.user.employee_get,
                recipient=shift_request.employee_id.employee_user_id,
                verb="Your shift request has been approved.",
                verb_ar="تمت الموافقة على طلبك للوردية.",
                verb_de="Ihr Schichtantrag wurde genehmigt.",
                verb_es="Se ha aprobado su solicitud de turno.",
                verb_fr="Votre demande de quart a été approuvée.",
                redirect=reverse("shift-request-view") + f"?id={shift_request.id}",
                icon="checkmark",
            )
        result = True
    return JsonResponse({"result": result})


@login_required
@require_http_methods(["POST"])
def shift_request_delete(request, id):
    """
    This method is used to delete shift request instance
    args:
        id : shift request instance id

    """

    shift_request = ShiftRequest.find(id)
    if not shift_request:
        messages.error(request, _("Shift request not found."))
        return HorillaRedirect(request)

    try:
        user = shift_request.employee_id.employee_user_id
        messages.success(request, _("Shift request deleted"))
        shift_request.delete()
        notify.send(
            request.user.employee_get,
            recipient=user,
            verb="Your shift request has been deleted.",
            verb_ar="تم حذف طلب الوردية الخاص بك.",
            verb_de="Ihr Schichtantrag wurde gelöscht.",
            verb_es="Se ha eliminado su solicitud de turno.",
            verb_fr="Votre demande de quart a été supprimée.",
            redirect="#",
            icon="trash",
        )

    except ProtectedError:
        messages.error(request, _("You cannot delete this shift request."))

    hx_target = request.META.get("HTTP_HX_TARGET", None)
    path = request.META.get("HTTP_HX_CURRENT_URL", None)
    parsed_url = urlparse(path)
    parsed_path = parsed_url.path.lstrip("/")
    if hx_target and hx_target == "shift-container":
        previous_data = request.GET.urlencode()
        if parsed_path in (
            "employee/shift-request-view/",
            "employee/requests/",
        ):
            return redirect(f"/list-shift-request/?deleted=true")
        else:
            return redirect(
                f"/shift-request-individual-tab-view/{shift_request.employee_id.id}?deleted=true"
            )
    if hx_target and hx_target == "genericModalBody":
        previous_data = request.GET.urlencode()
        instances_ids = request.GET.get("instances_ids", None)
        instances_list = json.loads(instances_ids) if instances_ids else []
        if id in instances_list:
            instances_list.remove(id)
            previous_instance, next_instance = closest_numbers(
                json.loads(instances_ids), id
            )
            return redirect(
                f"/shift-detail-view/{next_instance}/?{previous_data}&instance_ids={instances_list}&deleted=true"
            )

    return HorillaRedirect(request)


@login_required
@permission_required("base.delete_shiftrequest")
@require_http_methods(["POST"])
def shift_request_bulk_delete(request):
    """
    This method is used to delete shift request instance
    args:
        id : shift request instance id

    """
    ids = request.POST["ids"]
    ids = json.loads(ids)
    del_ids = []
    result = False
    for id in ids:
        try:
            shift_request = ShiftRequest.objects.get(id=id)
            user = shift_request.employee_id.employee_user_id
            shift_request.delete()
            del_ids.append(shift_request)
            notify.send(
                request.user.employee_get,
                recipient=user,
                verb="Your shift request has been deleted.",
                verb_ar="تم حذف طلب الوردية الخاص بك.",
                verb_de="Ihr Schichtantrag wurde gelöscht.",
                verb_es="Se ha eliminado su solicitud de turno.",
                verb_fr="Votre demande de quart a été supprimée.",
                redirect="#",
                icon="trash",
            )
        except ShiftRequest.DoesNotExist:
            messages.error(request, _("Shift request not found."))
        except ProtectedError:
            messages.error(
                request,
                _(
                    "You cannot delete {employee} shift request for the date {date}."
                ).format(
                    employee=shift_request.employee_id,
                    date=shift_request.requested_date,
                ),
            )
        result = True

    messages.success(request, _("{} shift requests deleted.".format(len(del_ids))))
    return JsonResponse({"result": result})


@login_required
def notifications(request):
    """
    This method will render notification items
    """
    all_notifications = request.user.notifications.unread()
    return render(
        request,
        "notification/notification_items.html",
        {"notifications": all_notifications},
    )


@login_required
def clear_notification(request):
    """
    This method is used to clear notification
    """
    try:
        request.user.notifications.unread().delete()
        messages.success(request, _("Unread notifications removed."))
    except Exception as e:
        messages.error(request, e)
    notifications = request.user.notifications.unread()
    return render(
        request,
        "notification/notification_items.html",
        {"notifications": notifications},
    )


@login_required
def delete_all_notifications(request):
    try:
        request.user.notifications.read().delete()
        request.user.notifications.unread().delete()
        messages.success(request, _("All notifications removed."))
    except Exception as e:
        messages.error(request, e)
    notifications = request.user.notifications.all()
    return render(
        request, "notification/all_notifications.html", {"notifications": notifications}
    )


@login_required
def delete_notification(request, id):
    """
    This method is used to delete notification
    """
    try:
        request.user.notifications.get(id=id).delete()
        messages.success(request, _("Notification deleted."))
    except request.user.notifications.model.DoesNotExist:
        messages.error(request, _("Notification not found."))
        return HorillaRedirect(request)
    except Exception as e:
        messages.error(request, e)
    return HttpResponse(
        "<script>"
        "setTimeout(function(){"
        "$('#reloadMessagesButton').click();"
        "htmx.ajax('GET','/all-notifications/',{target:'#sidebarModalBody',swap:'innerHTML'});"
        "},100);"
        "</script>"
    )


@login_required
def mark_as_read_notification(request, notification_id):
    script = ""
    notification_id = request.GET.get("notification_id")
    if not notification_id:
        return HorillaRedirect(
            request, message=_("No notification found matching the query.")
        )
    notification = get_object_or_404(
        Notification, id=notification_id, recipient=request.user
    )
    notification.mark_as_read()
    if not request.user.notifications.unread():
        script = """<span hx-get='/notifications' hx-target='#notificationContainer' hx-trigger='load'></span>"""
    return HttpResponse(script)


@login_required
def mark_as_read_notification_json(request):
    try:
        notification_id = request.POST["notification_id"]
        notification_id = int(notification_id)
        notification = Notification.objects.get(
            id=notification_id, recipient=request.user
        )
        notification.mark_as_read()
        return JsonResponse({"success": True})
    except (KeyError, ValueError, TypeError, Notification.DoesNotExist):
        # Missing or non-numeric notification_id, or no such notification.
        # Narrowed from a bare except so a genuine failure in mark_as_read
        # is no longer reported to the client as "Invalid request".
        logger.warning(
            "mark_as_read failed for notification_id=%r",
            request.POST.get("notification_id"),
        )
        return JsonResponse({"success": False, "error": "Invalid request"})


@login_required
def read_notifications(request):
    """
    This method is to mark as read the notification
    """
    try:
        request.user.notifications.all().mark_all_as_read()
        messages.info(request, _("Notifications marked as read"))
    except Exception as e:
        messages.error(request, e)
    notifications = request.user.notifications.unread()

    return render(
        request,
        "notification/notification_items.html",
        {"notifications": notifications},
    )


@login_required
def all_notifications(request):
    """
    This method to render all notifications to template
    """
    return render(
        request,
        "notification/all_notifications.html",
        {"notifications": request.user.notifications.all()},
    )


@login_required
def notification_sound(request):
    employee = request.user.employee_get
    sound, created = NotificationSound.objects.get_or_create(employee=employee)
    if not created:
        sound.sound_enabled = not sound.sound_enabled
        sound.save()

    return HttpResponse("")


@login_required
def _system_preferences_context(request):
    """
    Build template context shared by the System Preferences settings page.
    """
    tracking_company = get_session_company(request)

    if apps.is_installed("payroll"):
        PayrollSettings = get_horilla_model_class(
            app_label="payroll", model="payrollsettings"
        )
        from payroll.forms.component_forms import PayrollSettingsForm

        currency_instance, _created = PayrollSettings.objects.get_or_create(
            company_id=tracking_company
        )
        currency_form = PayrollSettingsForm(instance=currency_instance)
    else:
        currency_form = None

    selected_company_id = request.session.get("selected_company")

    if selected_company_id == "all" or not selected_company_id:
        companies = Company.objects.all()
    else:
        companies = Company.objects.filter(id=selected_company_id)

    prefix_instance, _created = EmployeeGeneralSetting.objects.get_or_create(
        company_id=tracking_company
    )
    prefix_form = EmployeeGeneralSettingPrefixForm(instance=prefix_instance)

    expire_instance, _created = AnnouncementExpire.objects.get_or_create(
        company_id=tracking_company
    )
    announcement_expire_settings = [expire_instance]
    show_expire_company = len(announcement_expire_settings) > 1

    enabled_block_unblock = (
        AccountBlockUnblock.objects.exists()
        and AccountBlockUnblock.objects.first().is_enabled
    )
    enabled_profile_edit = (
        ProfileEditFeature.objects.exists()
        and ProfileEditFeature.objects.first().is_enabled
    )
    history_tracking_instance = HistoryTrackingFields.for_settings_ui(tracking_company)
    history_fields_form_initial = {
        "tracking_fields": history_tracking_instance.tracked_field_names()
    }
    export_access_company = get_session_company(request)
    export_access_instance = DefaultExportPermission.objects.filter(
        company_id=export_access_company
    ).first()
    enabled_export_access = (
        export_access_instance is None or export_access_instance.is_enabled
    )
    history_fields_form = HistoryTrackingFieldsForm(initial=history_fields_form_initial)

    from base.auth_backends import company_scoped_active, get_allowed_company_ids

    tracking_scoped = (
        company_scoped_active()
        and request.user.is_authenticated
        and not request.user.is_superuser
    )
    if tracking_scoped:
        tracking_assign_company_qs = Company.objects.filter(
            id__in=get_allowed_company_ids(request.user) or []
        )
    else:
        tracking_assign_company_qs = Company.objects.all()
    tracking_assign_companies = list(tracking_assign_company_qs.order_by("company"))
    # Default: all companies selected for assignment.
    tracking_assigned_company_ids = [c.id for c in tracking_assign_companies]

    pagination_instance, _created = DynamicPagination.objects.get_or_create(
        user_id=request.user, company_id=tracking_company
    )
    pagination_settings = [pagination_instance]
    show_pagination_company = len(pagination_settings) > 1

    language_company = tracking_company
    language_setting = CompanyLanguageSetting.objects.filter(
        company_id=language_company
    ).first()
    enabled_languages = (
        language_setting.enabled_languages if language_setting else ["en"]
    )
    if language_company:
        language_employee_count = EmployeeWorkInformation.objects.filter(
            company_id=language_company, employee_id__is_active=True
        ).count()
    else:
        language_employee_count = Employee.objects.filter(is_active=True).count()
    language_configured_on = language_setting.created_at if language_setting else None

    language_scoped = tracking_scoped
    if language_scoped:
        all_language_companies = tracking_assign_company_qs
    else:
        all_language_companies = Company.objects.all()
    language_employee_counts_by_company = {
        row["company_id"]: row["count"]
        for row in (
            EmployeeWorkInformation.objects.filter(employee_id__is_active=True)
            .values("company_id")
            .annotate(count=Count("id"))
        )
    }
    language_enabled_counts_by_company = {
        setting.company_id_id: len(setting.enabled_languages or [])
        for setting in CompanyLanguageSetting.objects.exclude(company_id=None)
    }
    language_company_options = [
        {
            "id": company.id,
            "name": company.company,
            "icon": company.icon.url,
            "selected": language_company is not None
            and company.id == language_company.id,
            "employee_count": language_employee_counts_by_company.get(company.id, 0),
            "enabled_count": language_enabled_counts_by_company.get(company.id, 0),
        }
        for company in all_language_companies
    ]

    return {
        "announcement_expire_settings": announcement_expire_settings,
        "show_expire_company": show_expire_company,
        "currency_form": currency_form,
        "pagination_settings": pagination_settings,
        "show_pagination_company": show_pagination_company,
        "history_fields_form": history_fields_form,
        "history_tracking_instance": history_tracking_instance,
        "tracking_company": tracking_company,
        "tracking_is_all_companies": tracking_company is None,
        "tracking_assign_companies": tracking_assign_companies,
        "tracking_assigned_company_ids": tracking_assigned_company_ids,
        "enabled_block_unblock": enabled_block_unblock,
        "enabled_profile_edit": enabled_profile_edit,
        "enabled_export_access": enabled_export_access,
        "prefix_form": prefix_form,
        "companies": companies,
        "selected_company_id": selected_company_id,
        "current_company": companies.first(),
        "languages": settings.LANGUAGES,
        "enabled_languages": enabled_languages,
        "language_employee_count": language_employee_count,
        "language_configured_on": language_configured_on,
        "language_company": language_company,
        "language_company_count": all_language_companies.count(),
        "language_company_options": language_company_options,
        "language_total_available": len(settings.LANGUAGES),
    }


@login_required
def system_preferences_settings_view(request):
    """
    Merged "System Preferences" settings page that groups general defaults,
    formatting/localization, and data access controls under a single header.
    """
    context = _system_preferences_context(request)
    return render(request, "base/settings/system_preferences.html", context)


@login_required
@hx_request_required
@permission_required("base.change_announcementexpire")
def update_announcement_expire_days(request):
    """
    Updates the "Default Expire Days" setting for one company row (or the
    "All Companies" row) on the System Preferences page.
    """
    if request.method == "POST":
        setting_id = request.POST.get("setting_id")
        days = request.POST.get("days")
        updated = AnnouncementExpire.objects.filter(id=setting_id).update(days=days)
        if updated:
            messages.success(request, _("Default expire days updated."))
    return HttpResponse("")


@login_required
def general_settings(request):
    """
    Legacy URL — redirects to System Preferences.
    """
    return redirect("system-preferences-view")


@login_required
def encashment_general_settings_view(request):
    """
    Encashment redeem condition settings (moved out of General Settings).
    """
    if not apps.is_installed("payroll"):
        return redirect("system-preferences-view")

    EncashmentGeneralSettings = get_horilla_model_class(
        app_label="payroll", model="encashmentgeneralsettings"
    )
    from payroll.forms.forms import EncashmentGeneralSettingsForm

    encashment_instance = EncashmentGeneralSettings.objects.first()
    encashment_form = EncashmentGeneralSettingsForm(instance=encashment_instance)

    return render(
        request,
        "base/encashment_general_settings.html",
        {
            "encashment_form": encashment_form,
        },
    )


@login_required
@permission_required("base.view_company")
def date_settings(request):
    """
    This method is used to render Date format selector in settings
    """
    return redirect("system-preferences-view")


@login_required
@permission_required("base.change_company")
def save_date_format(request):
    if request.method == "POST":
        # Taking the selected Date Format
        selected_format = request.POST.get("selected_format")

        if selected_format not in settings.HORILLA_DATE_FORMATS:
            messages.error(request, _("Invalid date format."))
            return JsonResponse(
                {"success": False, "error": "Invalid date format."}, status=400
            )
        if not len(selected_format):
            messages.error(request, _("Please select a valid date format."))
        else:
            user = request.user
            employee = user.employee_get
            if request.user.is_superuser:
                selected_company = request.session.get("selected_company")
                if selected_company == "all":
                    all_companies = Company.objects.all()
                    for cmp in all_companies:
                        cmp.date_format = selected_format
                        cmp.save()
                    messages.success(request, _("Date format saved successfully."))
                else:
                    company = Company.objects.get(id=selected_company)
                    company.date_format = selected_format
                    company.save()
                    messages.success(request, _("Date format saved successfully."))

                # Return a JSON response indicating success
                return JsonResponse({"success": True})
            else:
                # Taking the company_name of the user
                info = EmployeeWorkInformation.objects.filter(employee_id=employee)
                # Employee workinformation will not exists if he/she chnged the company, So can't save the date format.
                if info.exists():
                    for data in info:
                        employee_company = data.company_id

                    company_name = Company.objects.filter(company=employee_company)
                    emp_company = company_name.first()

                    if emp_company is None:
                        messages.warning(
                            request, _("Please update the company field for the user.")
                        )
                    else:
                        # Save the selected format to the backend
                        emp_company.date_format = selected_format
                        emp_company.save()
                        messages.success(request, _("Date format saved successfully."))
                else:
                    messages.warning(
                        request,
                        _("Date format cannot saved. You are not in the company."),
                    )
                # Return a JSON response indicating success
                return JsonResponse({"success": True})

    # Return a JSON response for unsupported methods
    return JsonResponse({"error": "Unsupported method"}, status=405)


@login_required
def get_date_format(request):
    user = request.user
    employee = user.employee_get

    selected_company = request.session.get("selected_company")
    if selected_company != "all" and request.user.is_superuser:
        company = Company.objects.get(id=selected_company)
        date_format = company.date_format
        if date_format:
            date_format = date_format
        else:
            date_format = "MMM. D, YYYY"
        return JsonResponse({"selected_format": date_format})

    # Taking the company_name of the user
    info = EmployeeWorkInformation.objects.filter(employee_id=employee)
    if info.exists():
        for data in info:
            employee_company = data.company_id
        company_name = Company.objects.filter(company=employee_company)
        emp_company = company_name.first()
        if emp_company:
            # Access the date_format attribute directly
            date_format = emp_company.date_format if emp_company else "MMM. D, YYYY"
        else:
            date_format = "MMM. D, YYYY"
    else:
        date_format = "MMM. D, YYYY"
    # Return the date format as JSON response
    return JsonResponse({"selected_format": date_format})


@login_required
@permission_required("base.change_company")
def save_time_format(request):
    if request.method == "POST":
        # Taking the selected Time Format
        selected_format = request.POST.get("selected_format")

        if not len(selected_format):
            messages.error(request, _("Please select a valid time format."))
        else:
            user = request.user
            employee = user.employee_get
            if request.user.is_superuser:
                selected_company = request.session.get("selected_company")
                if selected_company == "all":
                    all_companies = Company.objects.all()
                    for cmp in all_companies:
                        cmp.time_format = selected_format
                        cmp.save()
                    messages.success(request, _("Date format saved successfully."))
                else:
                    company = Company.objects.get(id=selected_company)
                    company.time_format = selected_format
                    company.save()
                    messages.success(request, _("Date format saved successfully."))

                # Return a JSON response indicating success
                return JsonResponse({"success": True})
            else:
                # Taking the company_name of the user
                info = EmployeeWorkInformation.objects.filter(employee_id=employee)
                # Employee workinformation will not exists if he/she chnged the company, So can't save the time format.
                if info.exists():
                    for data in info:
                        employee_company = data.company_id

                    company_name = Company.objects.filter(company=employee_company)
                    emp_company = company_name.first()

                    if emp_company is None:
                        messages.warning(
                            request, _("Please update the company field for the user.")
                        )
                    else:
                        # Save the selected format to the backend
                        emp_company.time_format = selected_format
                        emp_company.save()
                        messages.success(request, _("Time format saved successfully."))
                else:
                    messages.warning(
                        request,
                        _("Time format cannot saved. You are not in the company."),
                    )

                # Return a JSON response indicating success
                return JsonResponse({"success": True})

    # Return a JSON response for unsupported methods
    return JsonResponse({"error": "Unsupported method"}, status=405)


@login_required
def get_time_format(request):
    user = request.user
    employee = user.employee_get

    selected_company = request.session.get("selected_company")
    if selected_company != "all" and request.user.is_superuser:
        company = Company.objects.get(id=selected_company)
        time_format = company.time_format
        if time_format:
            time_format = time_format
        else:
            time_format = "hh:mm A"
        return JsonResponse({"selected_format": time_format})

    # Taking the company_name of the user
    info = EmployeeWorkInformation.objects.filter(employee_id=employee)
    if info.exists():
        for data in info:
            employee_company = data.company_id
        company_name = Company.objects.filter(company=employee_company)
        emp_company = company_name.first()
        if emp_company:
            # Access the date_format attribute directly
            time_format = emp_company.time_format
        else:
            time_format = "hh:mm A"
    else:
        time_format = "hh:mm A"
    # Return the date format as JSON response
    return JsonResponse({"selected_format": time_format})


def _history_tracking_settings_context(request, company):
    """Shared template context for the work-info tracking settings partial."""
    from base.auth_backends import company_scoped_active, get_allowed_company_ids

    history_tracking_instance = HistoryTrackingFields.for_settings_ui(company)
    history_fields_form = HistoryTrackingFieldsForm(
        initial={"tracking_fields": history_tracking_instance.tracked_field_names()}
    )
    tracking_scoped = (
        company_scoped_active()
        and request.user.is_authenticated
        and not request.user.is_superuser
    )
    if tracking_scoped:
        tracking_assign_company_qs = Company.objects.filter(
            id__in=get_allowed_company_ids(request.user) or []
        )
    else:
        tracking_assign_company_qs = Company.objects.all()
    tracking_assign_companies = list(tracking_assign_company_qs.order_by("company"))
    # Default: all companies selected for assignment.
    tracking_assigned_company_ids = [c.id for c in tracking_assign_companies]
    return {
        "history_tracking_instance": history_tracking_instance,
        "history_fields_form": history_fields_form,
        "tracking_company": company,
        "tracking_is_all_companies": company is None,
        "tracking_assign_companies": tracking_assign_companies,
        "tracking_assigned_company_ids": tracking_assigned_company_ids,
    }


@login_required
def history_field_settings(request):
    """
    Save Work Information Tracking settings for the currently selected company.

    When All Companies is selected, the fields form can also post
    ``assign_companies`` so the same settings are applied to those companies.
    """
    company = get_session_company(request)

    if request.method == "POST":
        updating_fields = request.POST.get("update_tracking_fields") == "1"
        fields = request.POST.getlist("tracking_fields")
        track_enabled = request.POST.get("work_info_track") == "on"
        assign_company_ids = None
        if company is None:
            from base.auth_backends import (
                company_scoped_active,
                get_allowed_company_ids,
            )

            if updating_fields:
                raw_ids = request.POST.getlist("assign_companies")
                assign_company_ids = []
                for raw in raw_ids:
                    try:
                        assign_company_ids.append(int(raw))
                    except (TypeError, ValueError):
                        continue
            else:
                # Toggle-only: keep existing company assignments in sync.
                assign_company_ids = HistoryTrackingFields.assigned_company_ids()

            if (
                company_scoped_active()
                and request.user.is_authenticated
                and not request.user.is_superuser
            ):
                allowed = set(get_allowed_company_ids(request.user) or [])
                assign_company_ids = [
                    cid for cid in (assign_company_ids or []) if cid in allowed
                ]

        HistoryTrackingFields.apply_settings(
            work_info_track=track_enabled,
            field_names=fields,
            company=company,
            assign_company_ids=assign_company_ids,
            update_fields=updating_fields,
        )
        if company is None and updating_fields and assign_company_ids:
            messages.success(
                request,
                _("Settings updated and assigned to %(count)s company(ies).")
                % {"count": len(assign_company_ids)},
            )
        else:
            messages.success(request, _("Settings updated."))

    if request.headers.get("HX-Request"):
        return render(
            request,
            "base/audit_tag/history_tracking_fields_content.html",
            _history_tracking_settings_context(request, company),
        )
    return redirect(general_settings)


@login_required
@permission_required("horilla_audit.change_accountblockunblock")
def enable_account_block_unblock(request):
    if request.method == "POST":
        enabled = request.POST.get("enable_block_account") == "on"
        instance = AccountBlockUnblock.objects.first()
        if instance:
            instance.is_enabled = enabled
            instance.save()
        else:
            AccountBlockUnblock.objects.create(is_enabled=enabled)
        messages.success(
            request,
            _(
                f"Account block/unblock setting has been {'enabled' if enabled else 'disabled'}."
            ),
        )
        if request.META.get("HTTP_HX_REQUEST"):
            return HttpResponse()
        return redirect(general_settings)
    return HttpResponse(status=405)


@login_required
@permission_required("employee.change_employee")
def enable_profile_edit_feature(request):

    if request.method == "POST":
        enabled = request.POST.get("enable_profile_edit") == "on"
        instance = ProfileEditFeature.objects.first()
        feature = DefaultAccessibility.objects.filter(feature="profile_edit").first()
        if instance:
            instance.is_enabled = enabled
            instance.save()
        else:
            ProfileEditFeature.objects.create(is_enabled=enabled)

        if enabled and not feature:
            DefaultAccessibility.objects.create(
                feature="profile_edit", filter={"feature": ["profile_edit"]}
            )
        else:
            if feature is not None:
                feature.delete()
                messages.info(
                    request, _("Profile edit accessibility feature has been removed.")
                )

        if enabled:
            if not any(item[0] == "profile_edit" for item in ACCESSBILITY_FEATURE):
                ACCESSBILITY_FEATURE.append(("profile_edit", _("Profile Edit Access")))
        else:
            ACCESSBILITY_FEATURE.pop()

        messages.success(
            request,
            _(f"Profile edit feature has been {'enabled' if enabled else 'disabled'}."),
        )
        if request.META.get("HTTP_HX_REQUEST"):
            return HttpResponse()
        return redirect(general_settings)
    return HttpResponse(status=405)


@login_required
@permission_required("base.view_defaultexportpermission")
def default_export_access_settings_view(request):
    """
    "Default Export Access" settings page. Controls, per company, whether
    all users of that company can export data, or export access is
    restricted to users holding the per-module export permission.
    """
    company = get_session_company(request)
    instance = DefaultExportPermission.objects.filter(company_id=company).first()
    enabled_export_access = instance is None or instance.is_enabled
    return render(
        request,
        "base/settings/default_export_access.html",
        {"enabled_export_access": enabled_export_access},
    )


@login_required
@permission_required("base.change_defaultexportpermission")
def enable_default_export_access(request):
    if request.method == "POST":
        enabled = request.POST.get("enable_export_access") == "on"
        company = get_session_company(request)
        instance, _created = DefaultExportPermission.objects.get_or_create(
            company_id=company
        )
        instance.is_enabled = enabled
        instance.save()
        messages.success(
            request,
            _(
                f"Default export access has been {'enabled' if enabled else 'disabled'}."
            ),
        )
        if request.META.get("HTTP_HX_REQUEST"):
            return HttpResponse()
        return redirect(default_export_access_settings_view)
    return HttpResponse(status=405)


@login_required
@permission_required("base.change_companylanguagesetting")
def update_language_settings(request):
    """
    Handles the "Enable Languages" form on the System Preferences page.
    Restricts, per company, which languages appear in the navbar language
    switcher for that company's users. When no languages are selected,
    every language defined in settings.LANGUAGES stays available.
    """
    if request.method == "POST":
        selected_languages = request.POST.getlist("enabled_languages")
        language_labels = dict(settings.LANGUAGES)
        selected_languages = [
            code for code in selected_languages if code in language_labels
        ]
        company = get_session_company(request)
        instance, _created = CompanyLanguageSetting.objects.get_or_create(
            company_id=company
        )
        previous_languages = set(instance.enabled_languages or [])
        current_languages = set(selected_languages)
        newly_enabled = [
            language_labels[code]
            for code in selected_languages
            if code not in previous_languages
        ]
        newly_disabled = [
            language_labels[code]
            for code in instance.enabled_languages or []
            if code not in current_languages
        ]
        instance.enabled_languages = selected_languages
        instance.save()
        if newly_enabled or newly_disabled:
            parts = []
            if newly_enabled:
                parts.append(_("Enabled: %s") % ", ".join(newly_enabled))
            if newly_disabled:
                parts.append(_("Disabled: %s") % ", ".join(newly_disabled))
            messages.success(request, ". ".join(parts) + ".")
        else:
            messages.success(request, _("Language settings have been updated."))
    if request.META.get("HTTP_HX_REQUEST"):
        return HttpResponse()
    return HorillaRedirect(request)


@login_required
def shift_select(request):
    page_number = request.GET.get("page")
    shifts = ShiftRequest.objects.none()

    if page_number == "all":
        if request.user.has_perm("base.view_shiftrequest"):
            shifts = ShiftRequest.objects.all()
        else:
            shifts = ShiftRequest.objects.filter(
                employee_id__employee_user_id=request.user
            ) | ShiftRequest.objects.filter(
                employee_id__employee_work_info__reporting_manager_id__employee_user_id=request.user
            )

    shift_ids = [str(shift.id) for shift in shifts]
    total_count = shifts.count()

    context = {"employee_ids": shift_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
def shift_select_filter(request):
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    context = {}

    if page_number == "all":
        employee_filter = ShiftRequestFilter(
            filters, queryset=ShiftRequest.objects.all()
        )

        # Get the filtered queryset
        filtered_employees = employee_filter.qs

        employee_ids = [str(emp.id) for emp in filtered_employees]
        total_count = filtered_employees.count()

        context = {"employee_ids": employee_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
def work_type_select(request):
    page_number = request.GET.get("page")
    work_types = WorkTypeRequest.objects.none()

    if page_number == "all":
        if request.user.has_perm("base.view_worktyperequest"):
            work_types = WorkTypeRequest.objects.all()
        else:
            work_types = WorkTypeRequest.objects.filter(
                employee_id__employee_user_id=request.user
            ) | WorkTypeRequest.objects.filter(
                employee_id__employee_work_info__reporting_manager_id__employee_user_id=request.user
            )

    work_ids = [str(work.id) for work in work_types]
    total_count = work_types.count()

    context = {"employee_ids": work_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
def work_type_select_filter(request):
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    context = {}

    if page_number == "all":
        employee_filter = WorkTypeRequestFilter(
            filters, queryset=WorkTypeRequest.objects.all()
        )

        # Get the filtered queryset
        filtered_employees = employee_filter.qs

        employee_ids = [str(emp.id) for emp in filtered_employees]
        total_count = filtered_employees.count()

        context = {"employee_ids": employee_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
def rotating_shift_select(request):
    page_number = request.GET.get("page")

    if page_number == "all":
        if request.user.has_perm("base.view_rotatingshiftassign"):
            r_shifts = RotatingShiftAssign.objects.filter(is_active=True)
        else:
            r_shifts = RotatingShiftAssign.objects.filter(
                employee_id__employee_work_info__reporting_manager_id__employee_user_id=request.user
            )
    else:
        r_shifts = RotatingShiftAssign.objects.all()

    r_shift_ids = [str(r_shift.id) for r_shift in r_shifts]
    total_count = r_shifts.count()

    context = {"employee_ids": r_shift_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
def rotating_shift_select_filter(request):
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    context = {}

    if page_number == "all":
        employee_filter = RotatingShiftAssignFilters(
            filters, queryset=RotatingShiftAssign.objects.all()
        )

        # Get the filtered queryset
        filtered_employees = employee_filter.qs

        employee_ids = [str(emp.id) for emp in filtered_employees]
        total_count = filtered_employees.count()

        context = {"employee_ids": employee_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
def rotating_work_type_select(request):
    page_number = request.GET.get("page")

    if page_number == "all":
        if request.user.has_perm("base.view_rotatingworktypeassign"):
            r_shifts = RotatingWorkTypeAssign.objects.filter(is_active=True)
        else:
            r_shifts = RotatingWorkTypeAssign.objects.filter(
                employee_id__employee_work_info__reporting_manager_id__employee_user_id=request.user
            )
    else:
        r_shifts = RotatingWorkTypeAssign.objects.all()

    r_shift_ids = [str(r_shift.id) for r_shift in r_shifts]
    total_count = r_shifts.count()

    context = {"employee_ids": r_shift_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
def rotating_work_type_select_filter(request):
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    context = {}

    if page_number == "all":
        employee_filter = RotatingWorkTypeAssignFilter(
            filters, queryset=RotatingWorkTypeAssign.objects.all()
        )

        # Get the filtered queryset
        filtered_employees = employee_filter.qs

        employee_ids = [str(emp.id) for emp in filtered_employees]
        total_count = filtered_employees.count()

        context = {"employee_ids": employee_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
@permission_required("horilla_audit.view_audittag")
def tag_view(request):
    """
    Legacy standalone History Tags settings page. Merged into Audit & History;
    redirect direct visits to the merged page.
    """
    return redirect("audit-history-view")


@login_required
@permission_required("base.view_tags")
def helpdesk_tag_view(request):
    """
    This method is used to show Help desk tags
    """
    tags = Tags.objects.all()
    return render(
        request,
        "base/tags/helpdesk_tags.html",
        {"tags": tags},
    )


@login_required
@hx_request_required
@permission_required("base.add_tags")
def tag_create(request):
    """
    This method renders form and template to create Ticket type
    """
    form = TagsForm()
    if request.method == "POST":
        form = TagsForm(request.POST)
        if form.is_valid():
            form.save()
            form = TagsForm()
            messages.success(request, _("Tag has been created successfully!"))
            return HorillaRedirect(request)
    return render(
        request,
        "base/tags/tags_form.html",
        {
            "form": form,
        },
    )


@login_required
@hx_request_required
@permission_required("base.change_tags")
def tag_update(request, tag_id):
    """
    This method renders form and template to create Ticket type
    """
    tag = Tags.objects.filter(id=tag_id).first()
    if not tag:
        messages.error(request, _("Tag not found."))
        return HorillaRedirect(request)
    form = TagsForm(instance=tag)
    if request.method == "POST":
        form = TagsForm(request.POST, instance=tag)
        if form.is_valid():
            form.save()
            form = TagsForm()
            messages.success(request, _("Tag has been updated successfully!"))
            return HorillaRedirect(request)
    return render(
        request,
        "base/tags/tags_form.html",
        {"form": form, "tag_id": tag_id},
    )


@login_required
@hx_request_required
@permission_required("horilla_audit.add_audittag")
def audit_tag_create(request):
    """
    This method renders form and template to create Ticket type
    """
    form = AuditTagForm()
    if request.method == "POST":
        form = AuditTagForm(request.POST)
        if form.is_valid():
            form.save()
            form = AuditTagForm()
            messages.success(request, _("Tag has been created successfully!"))
            return HorillaRedirect(request)
    return render(
        request,
        "base/audit_tag/audit_tag_form.html",
        {
            "form": form,
        },
    )


@login_required
@hx_request_required
@permission_required("horilla_audit.change_audittag")
def audit_tag_update(request, tag_id):
    """
    This method renders form and template to create Ticket type
    """
    tag = AuditTag.objects.filter(id=tag_id).first()
    if not tag:
        messages.error(request, _("Tag not found."))
        return HorillaRedirect(request)
    form = AuditTagForm(instance=tag)
    if request.method == "POST":
        form = AuditTagForm(request.POST, instance=tag)
        if form.is_valid():
            form.save()
            form = AuditTagForm()
            messages.success(request, _("Tag has been updated successfully!"))
            return HorillaRedirect(request)
    return render(
        request,
        "base/audit_tag/audit_tag_form.html",
        {"form": form, "tag_id": tag_id},
    )


@login_required
@permission_required("base.view_multipleapprovalcondition")
def multiple_approval_condition(request):
    form = MultipleApproveConditionForm()
    selected_company = request.session.get("selected_company")
    if selected_company != "all":
        conditions = MultipleApprovalCondition.objects.filter(
            company_id=selected_company
        ).order_by("department")[::-1]
    else:
        conditions = MultipleApprovalCondition.objects.all().order_by("department")[
            ::-1
        ]
    create = True
    return render(
        request,
        "multi_approval_condition/condition.html",
        {"form": form, "conditions": conditions, "create": create},
    )


@login_required
@hx_request_required
@permission_required("base.view_multipleapprovalcondition")
def hx_multiple_approval_condition(request):
    selected_company = request.session.get("selected_company")
    if selected_company != "all":
        conditions = MultipleApprovalCondition.objects.filter(
            company_id=selected_company
        ).order_by("department")[::-1]
    else:
        conditions = MultipleApprovalCondition.objects.all().order_by("department")[
            ::-1
        ]
    return render(
        request,
        "multi_approval_condition/condition_table.html",
        {"conditions": conditions},
    )


@login_required
@hx_request_required
@permission_required("base.add_multipleapprovalcondition")
def get_condition_value_fields(request):
    operator = request.GET.get("condition_operator")
    form = MultipleApproveConditionForm()
    is_range = True if operator and operator == "range" else False
    context = {"form": form, "range": is_range}
    field_html = render_to_string(
        "multi_approval_condition/condition_value_fields.html", context
    )
    return HttpResponse(field_html)


@login_required
@hx_request_required
@permission_required("base.add_multipleapprovalcondition")
def add_more_approval_managers(request):
    current_hx_target = request.META.get("HTTP_HX_TARGET")
    if not current_hx_target:
        return HttpResponse()
    hx_target_split = current_hx_target.split("_")
    try:
        next_hx_target = "_".join(
            [hx_target_split[0], str(int(hx_target_split[-1]) + 1)]
        )
    except (IndexError, ValueError):
        return HttpResponse()

    form = MultipleApproveConditionForm()
    managers_count = request.GET.get("managers_count")
    context = {
        "next_hx_target": next_hx_target,
        "current_hx_target": current_hx_target,
    }
    if managers_count:
        managers_count = int(managers_count) + 1
        field_name = f"multi_approval_manager_{managers_count}"
        choices = [("reporting_manager_id", _("Reporting Manager"))] + [
            (employee.pk, str(employee)) for employee in Employee.objects.all()
        ]
        form.fields[field_name] = forms.ChoiceField(
            choices=choices,
            widget=forms.Select(
                attrs={
                    "class": "oh-select oh-select-2 mb-3",
                    "name": field_name,
                    "id": f"id_{field_name}",
                }
            ),
            required=False,
        )
        context["managers_count"] = managers_count
        context["field_html"] = form[field_name].as_widget()
    else:
        form.fields["multi_approval_manager"].widget.attrs.update(
            {
                "name": f"multi_approval_manager_{str(int(hx_target_split[-1]) + 1)}",
                "id": f"id_multi_approval_manager_{str(int(hx_target_split[-1]) + 1)}",
            }
        )
        context["form"] = form

    field_html = render_to_string(
        "multi_approval_condition/add_more_approval_manager.html", context
    )
    return HttpResponse(field_html)


@login_required
@hx_request_required
@permission_required("base.add_multipleapprovalcondition")
def remove_approval_manager(request):
    return HttpResponse()


@login_required
@hx_request_required
@permission_required("base.add_multipleapprovalcondition")
def multiple_level_approval_create(request):
    form = MultipleApproveConditionForm()
    create = True
    if request.method == "POST":
        form = MultipleApproveConditionForm(request.POST)
        dept_id = request.POST.get("department")
        condition_field = request.POST.get("condition_field")
        condition_operator = request.POST.get("condition_operator")
        condition_value = request.POST.get("condition_value")
        condition_start_value = request.POST.get("condition_start_value")
        condition_end_value = request.POST.get("condition_end_value")
        company_id = request.POST.get("company_id")
        condition_approval_managers = request.POST.getlist("multi_approval_manager")
        company = Company.objects.get(id=company_id)
        department = Department.objects.get(id=dept_id)
        instance = MultipleApprovalCondition()
        if form.is_valid():
            instance.department = department
            instance.condition_field = condition_field
            instance.condition_operator = condition_operator
            instance.company_id = company
            if condition_operator != "range":
                instance.condition_value = condition_value
            else:
                instance.condition_start_value = condition_start_value
                instance.condition_end_value = condition_end_value

            instance.save()
            sequence = 0
            for emp_id in condition_approval_managers:
                sequence += 1
                reporting_manager = None
                try:
                    employee_id = int(emp_id)
                except:
                    employee_id = None
                    reporting_manager = emp_id
                MultipleApprovalManagers.objects.create(
                    condition_id=instance,
                    sequence=sequence,
                    employee_id=employee_id,
                    reporting_manager=reporting_manager,
                )
            form = MultipleApproveConditionForm()
            messages.success(
                request, _("Multiple approval condition created successfully")
            )
    return render(
        request,
        "multi_approval_condition/condition_create_form.html",
        {"form": form, "create": create},
    )


def edit_approval_managers(form, managers):
    for i, manager in enumerate(managers):
        if i == 0:
            form.initial["multi_approval_manager"] = manager.employee_id
        else:
            field_name = f"multi_approval_manager_{i}"
            choices = [("reporting_manager_id", _("Reporting Manager"))] + [
                (employee.pk, str(employee)) for employee in Employee.objects.all()
            ]
            form.fields[field_name] = forms.ChoiceField(
                choices=choices,
                label=_("Approval Manager {}").format(i),
                widget=forms.Select(attrs={"class": "oh-select oh-select-2 mb-3"}),
                required=False,
            )

            form.initial[field_name] = manager.employee_id
    return form


def approval_managers_edit(form, managers):
    for i, manager in enumerate(managers):
        if i == 0:
            form.initial["multi_approval_manager"] = manager.employee_id
        else:
            field_name = f"multi_approval_manager_{i}"
            form.fields[field_name] = forms.ModelChoiceField(
                queryset=Employee.objects.all(),
                label=_("Approval Manager {}").format(i),
                widget=forms.Select(attrs={"class": "oh-select oh-select-2 mb-3"}),
                required=False,
            )
            form.initial[field_name] = manager.employee_id
    return form


@login_required
@hx_request_required
@permission_required("base.change_multipleapprovalcondition")
def multiple_level_approval_edit(request, condition_id):
    create = False
    condition = MultipleApprovalCondition.objects.get(id=condition_id)
    managers = MultipleApprovalManagers.objects.filter(condition_id=condition).order_by(
        "sequence"
    )
    form = MultipleApproveConditionForm(instance=condition)
    edit_approval_managers(form, managers)
    if request.method == "POST":
        form = MultipleApproveConditionForm(request.POST, instance=condition)
        if form.is_valid():
            instance = form.save()
            messages.success(
                request, _("Multiple approval condition updated successfully")
            )
            sequence = 0
            MultipleApprovalManagers.objects.filter(condition_id=condition).delete()
            for key, value in request.POST.items():
                if key.startswith("multi_approval_manager"):
                    sequence += 1
                    reporting_manager = None
                    try:
                        employee_id = int(value)
                    except:
                        employee_id = None
                        reporting_manager = value
                    MultipleApprovalManagers.objects.create(
                        condition_id=instance,
                        sequence=sequence,
                        employee_id=employee_id,
                        reporting_manager=reporting_manager,
                    )
    selected_company = request.session.get("selected_company")
    if selected_company != "all":
        conditions = MultipleApprovalCondition.objects.filter(
            company_id=selected_company
        ).order_by("department")[::-1]
    else:
        conditions = MultipleApprovalCondition.objects.all().order_by("department")[
            ::-1
        ]

    return render(
        request,
        "multi_approval_condition/condition_edit_form.html",
        {
            "form": form,
            "conditions": conditions,
            "create": create,
            "condition": condition,
            "managers_count": len(managers),
        },
    )


@login_required
@permission_required("base.delete_multipleapprovalcondition")
def multiple_level_approval_delete(request, condition_id):

    request_copy = request.GET.copy()
    request_copy.pop("instances_ids", None)
    previous_data = request_copy.urlencode()

    if not MultipleApprovalCondition.objects.filter(id=condition_id).exists():
        return HorillaRedirect(
            request,
            message=_("No MultipleApprovalCondition matching query does not exist."),
        )

    condition = MultipleApprovalCondition.objects.get(id=condition_id)
    condition.delete()
    messages.success(request, _("Multiple approval condition deleted successfully"))
    hx_target = request.META.get("HTTP_HX_TARGET")
    if hx_target and hx_target == "genericModalBody":
        instances_ids = request.GET.get("instances_ids")
        instances_list = json.loads(instances_ids)
        if condition_id in instances_list:
            instances_list.remove(condition_id)
            previous_instance, next_instance = closest_numbers(
                json.loads(instances_ids), condition_id
            )
        return redirect(
            f"/detail-view-multiple-approval-condition/{next_instance}/?{previous_data}&instance_ids={instances_list}&deleted=true"
        )

    return redirect(reverse("hx-multiple-approval-condition"))


@login_required
@hx_request_required
def create_shiftrequest_comment(request, shift_id):
    """
    This method renders form and template to create shift request comments
    """
    shift = ShiftRequest.find(shift_id)
    emp = request.user.employee_get
    form = ShiftRequestCommentForm(
        initial={"employee_id": emp.id, "request_id": shift_id}
    )

    if request.method == "POST":
        form = ShiftRequestCommentForm(request.POST)
        if form.is_valid():
            form.instance.employee_id = emp
            form.instance.request_id = shift
            form.save()
            comments = ShiftRequestComment.objects.filter(request_id=shift_id).order_by(
                "-created_at"
            )
            no_comments = False
            if not comments.exists():
                no_comments = True
            form = ShiftRequestCommentForm(
                initial={"employee_id": emp.id, "request_id": shift_id}
            )
            messages.success(request, _("Comment added successfully!"))
            work_info = EmployeeWorkInformation.objects.filter(
                employee_id=shift.employee_id
            )
            if work_info.exists():
                if (
                    shift.employee_id.employee_work_info.reporting_manager_id
                    is not None
                ):
                    if request.user.employee_get.id == shift.employee_id.id:
                        rec = (
                            shift.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                        )
                        notify.send(
                            request.user.employee_get,
                            recipient=rec,
                            verb=f"{shift.employee_id}'s shift request has received a comment.",
                            verb_ar=f"تلقت طلب تحويل {shift.employee_id} تعليقًا.",
                            verb_de=f"{shift.employee_id}s Schichtantrag hat einen Kommentar erhalten.",
                            verb_es=f"La solicitud de turno de {shift.employee_id} ha recibido un comentario.",
                            verb_fr=f"La demande de changement de poste de {shift.employee_id} a reçu un commentaire.",
                            redirect=reverse("shift-request-view") + f"?id={shift.id}",
                            icon="chatbox-ellipses",
                        )
                    elif (
                        request.user.employee_get.id
                        == shift.employee_id.employee_work_info.reporting_manager_id.id
                    ):
                        rec = shift.employee_id.employee_user_id
                        notify.send(
                            request.user.employee_get,
                            recipient=rec,
                            verb="Your shift request has received a comment.",
                            verb_ar="تلقت طلبك للتحول تعليقًا.",
                            verb_de="Ihr Schichtantrag hat einen Kommentar erhalten.",
                            verb_es="Tu solicitud de turno ha recibido un comentario.",
                            verb_fr="Votre demande de changement de poste a reçu un commentaire.",
                            redirect=reverse("shift-request-view") + f"?id={shift.id}",
                            icon="chatbox-ellipses",
                        )
                    else:
                        rec = [
                            shift.employee_id.employee_user_id,
                            shift.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                        ]
                        notify.send(
                            request.user.employee_get,
                            recipient=rec,
                            verb=f"{shift.employee_id}'s shift request has received a comment.",
                            verb_ar=f"تلقت طلب تحويل {shift.employee_id} تعليقًا.",
                            verb_de=f"{shift.employee_id}s Schichtantrag hat einen Kommentar erhalten.",
                            verb_es=f"La solicitud de turno de {shift.employee_id} ha recibido un comentario.",
                            verb_fr=f"La demande de changement de poste de {shift.employee_id} a reçu un commentaire.",
                            redirect=reverse("shift-request-view") + f"?id={shift.id}",
                            icon="chatbox-ellipses",
                        )
                else:
                    rec = shift.employee_id.employee_user_id
                    notify.send(
                        request.user.employee_get,
                        recipient=rec,
                        verb="Your shift request has received a comment.",
                        verb_ar="تلقت طلبك للتحول تعليقًا.",
                        verb_de="Ihr Schichtantrag hat einen Kommentar erhalten.",
                        verb_es="Tu solicitud de turno ha recibido un comentario.",
                        verb_fr="Votre demande de changement de poste a reçu un commentaire.",
                        redirect=reverse("shift-request-view") + f"?id={shift.id}",
                        icon="chatbox-ellipses",
                    )
            return render(
                request,
                "shift_request/htmx/shift_comment.html",
                {
                    "comments": comments,
                    "no_comments": no_comments,
                    "request_id": shift_id,
                    "shift_request": shift,
                },
            )
    return render(
        request,
        "shift_request/htmx/shift_comment.html",
        {"form": form, "request_id": shift_id, "shift_request": shift},
    )


@login_required
@hx_request_required
def view_shift_comment(request, shift_id):
    """
    This method is used to render all the notes of the employee
    """
    shift_request = ShiftRequest.find(shift_id)
    comments = ShiftRequestComment.objects.filter(request_id=shift_id).order_by(
        "-created_at"
    )
    no_comments = False
    if not comments.exists():
        no_comments = True
    if request.FILES:
        files = request.FILES.getlist("files")
        comment_id = request.GET["comment_id"]
        comment = ShiftRequestComment.objects.get(id=comment_id)
        attachments = []
        for file in files:
            file_instance = BaserequestFile()
            file_instance.file = file
            file_instance.save()
            attachments.append(file_instance)
        comment.files.add(*attachments)
    return render(
        request,
        "shift_request/htmx/shift_comment.html",
        {
            "comments": comments,
            "no_comments": no_comments,
            "request_id": shift_id,
            "shift_request": shift_request,
        },
    )


@login_required
@hx_request_required
def delete_shift_comment_file(request):
    """
    Used to delete attachment
    """

    try:
        ids = [int(i) for i in request.GET.getlist("ids") if i.isdigit()]
        shift_id = int(request.GET["shift_id"])
        comment_id = int(request.GET["comment_id"])
    except (KeyError, ValueError):
        return HorillaRedirect(
            request,
            message=_("Invalid Request"),
        )

    comment = ShiftRequestComment.find(comment_id)
    if not comment:
        return HorillaRedirect(request, message=_("Comment not found."))

    script = ""

    if (
        request.user.employee_get == comment.employee_id
        or request.user.has_perm("base.delete_baserequestfile")
        or is_reportingmanager(request)
    ):
        BaserequestFile.objects.filter(id__in=ids).delete()
        messages.success(request, _("File deleted successfully"))
    else:
        messages.warning(request, _("You don't have permission"))
        script = f"""
        <span hx-get="/view-shift-comment/{shift_id}/"
            hx-trigger="load"
            hx-target="#commentContainer"
            data-target="#activitySidebar">
        </span>
        """

    return HttpResponse(script)


@login_required
@hx_request_required
def view_work_type_comment(request, work_type_id):
    """
    This method is used to render all the notes of the employee
    """
    work_type_request = WorkTypeRequest.find(work_type_id)
    comments = WorkTypeRequestComment.objects.filter(request_id=work_type_id).order_by(
        "-created_at"
    )
    no_comments = False
    if not comments.exists():
        no_comments = True
    if request.FILES:
        files = request.FILES.getlist("files")
        comment_id = request.GET["comment_id"]
        comment = WorkTypeRequestComment.objects.get(id=comment_id)
        attachments = []
        for file in files:
            file_instance = BaserequestFile()
            file_instance.file = file
            file_instance.save()
            attachments.append(file_instance)
        comment.files.add(*attachments)
    return render(
        request,
        "work_type_request/htmx/work_type_comment.html",
        {
            "comments": comments,
            "no_comments": no_comments,
            "request_id": work_type_id,
            "work_type_request": work_type_request,
        },
    )


@login_required
@hx_request_required
def delete_work_type_comment_file(request):
    """
    Used to delete attachment
    """

    try:
        ids = [int(i) for i in request.GET.getlist("ids") if i.isdigit()]
        request_id = int(request.GET["request_id"])
        comment_id = int(request.GET["comment_id"])
    except (KeyError, ValueError):
        return HorillaRedirect(
            request, message=_("Invalid Request"), redirect_to="work-type-request-view"
        )

    comment = WorkTypeRequestComment.find(comment_id)
    if not comment:
        return HorillaRedirect(
            request,
            message=_("Comment not found."),
            redirect_to="work-type-request-view",
        )

    script = ""

    if (
        request.user.employee_get == comment.employee_id
        or request.user.has_perm("base.delete_baserequestfile")
        or is_reportingmanager(request)
    ):
        BaserequestFile.objects.filter(id__in=ids).delete()
        messages.success(request, _("File deleted successfully"))
    else:
        messages.warning(request, _("You don't have permission"))
        script = f"""
        <span hx-get="/view-work-type-comment/{request_id}/"
            hx-trigger="load"
            hx-target="#commentContainer"
            data-target="#activitySidebar">
        </span>
        """

    return HttpResponse(script)


@login_required
@hx_request_required
def delete_shiftrequest_comment(request, comment_id):
    """
    This method is used to delete shift request comments
    """
    comment = ShiftRequestComment.find(comment_id)
    if not comment:
        return HorillaRedirect(request, message=_("Comment not found."))

    request_id = comment.request_id.id
    script = ""
    if (
        request.user.employee_get == comment.employee_id
        or request.user.has_perm("base.delete_baserequestfile")
        or is_reportingmanager(request)
    ):
        comment.delete()
        messages.success(request, _("Comment deleted successfully!"))
    else:
        messages.warning(request, _("You don't have permission"))
        script = f"""<span hx-get="/view-shift-comment/{request_id}/" hx-trigger="load" hx-target="#commentContainer" data-target="#activitySidebar"></span>"""
    return HttpResponse(script)


@login_required
@hx_request_required
def create_worktyperequest_comment(request, worktype_id):
    """
    This method renders form and template to create Work type request comments
    """
    work_type = WorkTypeRequest.objects.filter(id=worktype_id).first()
    emp = request.user.employee_get
    form = WorkTypeRequestCommentForm(
        initial={"employee_id": emp.id, "request_id": worktype_id}
    )

    if request.method == "POST":
        form = WorkTypeRequestCommentForm(request.POST)
        if form.is_valid():
            form.instance.employee_id = emp
            form.instance.request_id = work_type
            form.save()
            comments = WorkTypeRequestComment.objects.filter(
                request_id=worktype_id
            ).order_by("-created_at")
            no_comments = False
            if not comments.exists():
                no_comments = True
            form = WorkTypeRequestCommentForm(
                initial={"employee_id": emp.id, "request_id": worktype_id}
            )
            messages.success(request, _("Comment added successfully!"))

            work_info = EmployeeWorkInformation.objects.filter(
                employee_id=work_type.employee_id
            )
            if work_info.exists():
                if (
                    work_type.employee_id.employee_work_info.reporting_manager_id
                    is not None
                ):
                    if request.user.employee_get.id == work_type.employee_id.id:
                        rec = (
                            work_type.employee_id.employee_work_info.reporting_manager_id.employee_user_id
                        )
                        notify.send(
                            request.user.employee_get,
                            recipient=rec,
                            verb=f"{work_type.employee_id}'s work type request has received a comment.",
                            verb_ar=f"تلقت طلب نوع العمل {work_type.employee_id} تعليقًا.",
                            verb_de=f"{work_type.employee_id}s Arbeitsart-Antrag hat einen Kommentar erhalten.",
                            verb_es=f"La solicitud de tipo de trabajo de {work_type.employee_id} ha recibido un comentario.",
                            verb_fr=f"La demande de type de travail de {work_type.employee_id} a reçu un commentaire.",
                            redirect=reverse("work-type-request-view")
                            + f"?id={work_type.id}",
                            icon="chatbox-ellipses",
                        )
                    elif (
                        request.user.employee_get.id
                        == work_type.employee_id.employee_work_info.reporting_manager_id.id
                    ):
                        rec = work_type.employee_id.employee_user_id
                        notify.send(
                            request.user.employee_get,
                            recipient=rec,
                            verb="Your work type request has received a comment.",
                            verb_ar="تلقى طلب نوع العمل الخاص بك تعليقًا.",
                            verb_de="Ihr Arbeitsart-Antrag hat einen Kommentar erhalten.",
                            verb_es="Tu solicitud de tipo de trabajo ha recibido un comentario.",
                            verb_fr="Votre demande de type de travail a reçu un commentaire.",
                            redirect=reverse("work-type-request-view")
                            + f"?id={work_type.id}",
                            icon="chatbox-ellipses",
                        )
                    else:
                        rec = [
                            work_type.employee_id.employee_user_id,
                            work_type.employee_id.employee_work_info.reporting_manager_id.employee_user_id,
                        ]
                        notify.send(
                            request.user.employee_get,
                            recipient=rec,
                            verb=f"{work_type.employee_id}'s work type request has received a comment.",
                            verb_ar=f"تلقت طلب نوع العمل {work_type.employee_id} تعليقًا.",
                            verb_de=f"{work_type.employee_id}s Arbeitsart-Antrag hat einen Kommentar erhalten.",
                            verb_es=f"La solicitud de tipo de trabajo de {work_type.employee_id} ha recibido un comentario.",
                            verb_fr=f"La demande de type de travail de {work_type.employee_id} a reçu un commentaire.",
                            redirect=reverse("work-type-request-view")
                            + f"?id={work_type.id}",
                            icon="chatbox-ellipses",
                        )
                else:
                    rec = work_type.employee_id.employee_user_id
                    notify.send(
                        request.user.employee_get,
                        recipient=rec,
                        verb="Your work type request has received a comment.",
                        verb_ar="تلقى طلب نوع العمل الخاص بك تعليقًا.",
                        verb_de="Ihr Arbeitsart-Antrag hat einen Kommentar erhalten.",
                        verb_es="Tu solicitud de tipo de trabajo ha recibido un comentario.",
                        verb_fr="Votre demande de type de travail a reçu un commentaire.",
                        redirect=reverse("work-type-request-view")
                        + f"?id={work_type.id}",
                        icon="chatbox-ellipses",
                    )
            return render(
                request,
                "work_type_request/htmx/work_type_comment.html",
                {
                    "comments": comments,
                    "no_comments": no_comments,
                    "request_id": worktype_id,
                    "work_type_request": work_type,
                },
            )
    return render(
        request,
        "work_type_request/htmx/work_type_comment.html",
        {"form": form, "request_id": worktype_id, "work_type_request": work_type},
    )


@login_required
@hx_request_required
def delete_worktyperequest_comment(request, comment_id):
    """
    This method is used to delete Work type request comments
    """
    comment = WorkTypeRequestComment.find(comment_id)
    if not comment:
        return HorillaRedirect(request, message=_("Comment not found."))

    script = ""
    request_id = comment.request_id.id
    if (
        request.user.employee_get == comment.employee_id
        or request.user.has_perm("base.delete_baserequestfile")
        or is_reportingmanager(request)
    ):
        comment.delete()
        messages.success(request, _("Comment deleted successfully!"))
    else:
        messages.warning(request, _("You don't have permission"))
        script = f"""<span hx-get="/view-work-type-comment/{request_id}/" hx-trigger="load" hx-target="#commentContainer" data-target="#activitySidebar"></span>"""
    return HttpResponse(script)


@login_required
def pagination_settings_view(request):
    """
    Updates one of the current user's Default Records Per Page rows (one
    row per company, plus the "All Companies" row) on the System
    Preferences page.
    """
    if request.method == "POST":
        setting_id = request.POST.get("setting_id")
        pagination = request.POST.get("pagination")
        updated = DynamicPagination.objects.filter(
            id=setting_id, user_id=request.user
        ).update(pagination=pagination)
        if updated:
            messages.success(request, _("Default pagination updated."))
    if request.META.get("HTTP_HX_REQUEST"):
        return HttpResponse()
    return HorillaRedirect(request)


@login_required
@permission_required("employee.view_actiontype")
def action_type_view(request):
    """
    This method is used to show Action Type
    """
    action_types = Actiontype.objects.all()
    return render(
        request, "base/action_type/action_type.html", {"action_types": action_types}
    )


@login_required
@hx_request_required
@permission_required("employee.add_actiontype")
def action_type_create(request):
    """
    This method renders form and template to create Action Type
    """
    form = ActiontypeForm()
    previous_data = request.GET.urlencode()
    dynamic = request.GET.get("dynamic")
    if request.method == "POST":
        form = ActiontypeForm(request.POST)
        if form.is_valid():
            form.save()
            form = ActiontypeForm()
            messages.success(request, _("Action has been created successfully!"))
            if dynamic != None:
                url = reverse("create-actions")
                instance = Actiontype.objects.all().order_by("-id").first()
                mutable_get = request.GET.copy()
                mutable_get["action"] = str(instance.id)
                return redirect(f"{url}?{mutable_get.urlencode()}")

    return render(
        request,
        "base/action_type/action_type_form.html",
        {
            "form": form,
            "pd": previous_data,
        },
    )


@login_required
@hx_request_required
@permission_required("employee.change_actiontype")
def action_type_update(request, act_id):
    """
    This method renders form and template to update Action type
    """
    action = Actiontype.objects.filter(id=act_id).first()
    if not action:
        messages.error(request, _("Action type not found."))
        return HorillaRedirect(request)
    form = ActiontypeForm(instance=action)

    if action.action_type == "warning":
        if (
            AccountBlockUnblock.objects.first()
            and AccountBlockUnblock.objects.first().is_enabled
        ):
            form.fields["block_option"].widget = forms.HiddenInput()

    if request.method == "POST":
        form = ActiontypeForm(request.POST, instance=action)
        if form.is_valid():
            act_type = form.cleaned_data["action_type"]
            if act_type == "warning":
                form.instance.block_option = False
            form.save()
            form = ActiontypeForm()
            messages.success(request, _("Action has been updated successfully!"))
    return render(
        request,
        "base/action_type/action_type_form.html",
        {"form": form, "act_id": act_id},
    )


@login_required
@hx_request_required
@permission_required("employee.delete_actiontype")
def action_type_delete(request, act_id):
    """
    This method is used to delete the action type.
    """
    if DisciplinaryAction.objects.filter(action=act_id).exists():

        messages.error(
            request,
            _(
                "This action type is in use in disciplinary actions and cannot be deleted."
            ),
        )
        return HorillaRedirect(request)

    else:
        Actiontype.objects.filter(id=act_id).delete()
        messages.success(request, _("Action has been deleted successfully!"))
        return HttpResponse()


@login_required
def driver_viewed_status(request):
    """
    This method is used to update driver viewed status
    """
    form = DriverForm(request.GET)
    if form.is_valid():
        form.save()
    return HttpResponse("")


def _charts_use_modern_prefs(charts) -> bool:
    """True when DashboardEmployeeCharts.charts is modern ``[{id, visible}, ...]``."""
    return bool(
        charts
        and isinstance(charts, list)
        and isinstance(charts[0], dict)
        and charts[0].get("id")
    )


@login_required
@hx_request_required
def dashboard_components_toggle(request):
    """
    This function is used to create personalized dashboard charts for employees
    """
    employee_charts, created = DashboardEmployeeCharts.objects.get_or_create(
        employee=request.user.employee_get
    )
    charts = employee_charts.charts or []
    # Modern home prefs must not be mutated by legacy tile toggles.
    if _charts_use_modern_prefs(charts):
        return HttpResponse("")
    chart_id = request.GET.get("chart_id")
    if chart_id and chart_id in charts:
        charts.remove(chart_id)
        employee_charts.charts = charts
        employee_charts.save()
    return HttpResponse("")


@login_required
@hx_request_required
def employee_chart_show(request):
    """
    This function is used to choose which chart to show in the dashboard
    """
    employee_charts, created = DashboardEmployeeCharts.objects.get_or_create(
        employee=request.user.employee_get
    )

    charts = check_chart_permission(request, CHARTS)

    if request.method == "POST":
        # Refuse to overwrite modern dashboard Customize prefs with legacy string ids.
        if _charts_use_modern_prefs(employee_charts.charts):
            messages.warning(
                request,
                _(
                    "Chart preferences are managed via Customize on the modern "
                    "dashboard. Legacy Dashboard Charts was not applied."
                ),
            )
            return HttpResponse("<script>window.location.reload();</script>")

        data = set(request.POST.keys())
        current_order = employee_charts.charts or []

        new_order = [c for c in current_order if c in data]

        for char in data:
            if char not in new_order:
                new_order.append(char)

        employee_charts.charts = new_order
        employee_charts.save()
        messages.success(request, _("Dashboard charts updated successfully"))

        return HttpResponse("<script>window.location.reload();</script>")

    context = {"dashboard_charts": charts, "employee_chart": employee_charts.charts}
    return render(request, "dashboard_chart_form.html", context)


@login_required
@hx_request_required
def reorder_dashboard_charts(request):
    """
    This function is used to reorder the dashboard charts
    """
    employee_charts, created = DashboardEmployeeCharts.objects.get_or_create(
        employee=request.user.employee_get
    )
    if _charts_use_modern_prefs(employee_charts.charts):
        messages.warning(
            request,
            _("Use Customize on the modern dashboard to reorder charts."),
        )
        return HttpResponse(headers={"HX-Refresh": "true"})

    charts = [
        (chart, chart.replace("_", " ")) for chart in (employee_charts.charts or [])
    ]

    if request.method == "POST":
        chart_keys = list(request.POST.keys())
        filtered_chart_keys = [
            item for item in chart_keys if item in employee_charts.charts
        ]
        employee_charts.charts = filtered_chart_keys
        employee_charts.save()
        return HttpResponse(headers={"HX-Refresh": "true"})

    return render(
        request,
        "horilla_theme/components/reorder_dashboard_charts.html",
        {"charts": charts},
    )


@login_required
@permission_required("base.add_biometricattendance")
def activate_biometric_attendance(request):
    if request.method == "GET":
        is_installed = request.GET.get("is_installed")
        selected_company = request.session.get("selected_company")
        if selected_company == "all":
            company = None
        else:
            company = Company.objects.filter(id=selected_company).first()
        instance, created = BiometricAttendance.objects.get_or_create(
            company_id=company
        )
        if is_installed == "true":
            instance.is_installed = True
            messages.success(
                request,
                _("The biometric attendance feature has been activated successfully."),
            )
        else:
            instance.is_installed = False
            messages.info(
                request,
                _(
                    "The biometric attendance feature has been deactivated successfully."
                ),
            )
        instance.save()
    return JsonResponse({"message": "Success"})


@login_required
def get_horilla_installed_apps(request):
    return JsonResponse({"installed_apps": settings.APPS})


def generate_error_report(error_list, error_data, file_name):
    for item in error_list:
        for key, value in error_data.items():
            if key in item:
                value.append(item[key])
            else:
                value.append(None)

    keys_to_remove = [
        key for key, value in error_data.items() if all(v is None for v in value)
    ]
    for key in keys_to_remove:
        del error_data[key]

    data_frame = pd.DataFrame(error_data, columns=error_data.keys())
    response = HttpResponse(content_type="application/ms-excel")
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
    writer = pd.ExcelWriter(response, engine="xlsxwriter")
    try:
        styled_data_frame = data_frame.style.map(
            lambda x: "text-align: center", subset=pd.IndexSlice[:, :]
        )
        styled_data_frame.to_excel(writer, index=False, sheet_name="Sheet1")
    except Exception:
        data_frame.to_excel(writer, index=False, sheet_name="Sheet1")

    worksheet = writer.sheets["Sheet1"]
    worksheet.set_column("A:Z", 30)
    writer.close()

    def get_error_sheet(request):
        remove_dynamic_url(path_info)
        return response

    from base.urls import path, urlpatterns

    # Create a unique path for the error file download
    path_info = f"error-sheet-{uuid.uuid4()}"
    urlpatterns.append(path(path_info, get_error_sheet, name=path_info))
    settings.DYNAMIC_URL_PATTERNS.append(path_info)
    for key in error_data:
        error_data[key] = []
    return path_info


@login_required
@hx_request_required
def get_upcoming_holidays(request):
    """
    Retrieve and display a list of upcoming holidays for the current month and year.
    """
    today = timezone.localdate()
    current_year = today.year
    holidays = Holidays.objects.filter(
        start_date__year=current_year, start_date__gte=today
    )
    colors = generate_colors(len(holidays))
    for i, holiday in enumerate(holidays):
        holiday.background_color = colors[i]
    return render(request, "holiday/upcoming_holidays.html", {"holidays": holidays})


@login_required
@hx_request_required
@permission_required("base.add_holidays")
def holiday_creation(request):
    """
    function used to create holidays.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return holiday creation form template
    POST : return holiday view template
    """

    previous_data = request.GET.urlencode()
    form = HolidayForm()
    if request.method == "POST":
        form = HolidayForm(request.POST)
        if form.is_valid():
            form.save()
            form = HolidayForm()
            messages.success(request, _("New holiday created successfully.."))
            if Holidays.objects.filter().count() == 1:
                return HorillaRedirect(request)
    return render(
        request, "holiday/holiday_form.html", {"form": form, "pd": previous_data}
    )


@login_required
def holidays_excel_template(request):
    try:
        columns = [
            "Holiday Name",
            "Start Date",
            "End Date",
            "Recurring",
        ]
        data_frame = pd.DataFrame(columns=columns)
        response = HttpResponse(content_type="application/ms-excel")
        response["Content-Disposition"] = (
            'attachment; filename="assign_leave_type_excel.xlsx"'
        )
        data_frame.to_excel(response, index=False)
        return response
    except Exception as exception:
        return HttpResponse(exception)


def csv_holiday_import(file):
    """
    Imports holiday data from a CSV file.

    This function reads a CSV file containing holiday information, validates the data,
    and saves valid holiday records to the database using bulk creation for efficiency.

    The expected format for the CSV file is:
    - "Holiday Name": Name of the holiday (string)
    - "Start Date": Start date of the holiday (date string in a recognized format)
    - "End Date": End date of the holiday (date string in a recognized format)
    - "Recurring": Indicates whether the holiday recurs ("yes" or "no")
    """
    holiday_list, error_list = [], []
    file_name = settings.FILE_STORAGE.save(
        "holiday_import.csv", ContentFile(file.read())
    )
    holiday_file = settings.FILE_STORAGE.path(file_name)

    with open(holiday_file, errors="ignore") as csv_file:
        save = True
        reader = csv.reader(csv_file)
        next(reader)

        for total_rows, row in enumerate(reader, start=1):
            try:
                name, start_date, end_date, recurring = row
                holiday_dict = {
                    "Holiday Name": name,
                    "Start Date": start_date,
                    "End Date": end_date,
                    "Recurring": recurring,
                }

                try:
                    start_date = format_date(start_date)
                except:
                    save = False
                    holiday_dict["Start Date Error"] = _("Invalid start date format.")
                    error_list.append(holiday_dict)

                try:
                    end_date = format_date(end_date)
                except:
                    save = False
                    holiday_dict["End Date Error"] = _("Invalid end date format.")
                    error_list.append(holiday_dict)

                if recurring.lower() not in ["yes", "no"]:
                    save = False
                    holiday_dict["Recurring Field Error"] = _(
                        "Recurring must be yes or no."
                    )
                    error_list.append(holiday_dict)

                if save:
                    holiday_list.append(
                        Holidays(
                            name=name,
                            start_date=start_date,
                            end_date=end_date,
                            recurring=recurring.lower() == "yes",
                        )
                    )

            except Exception as e:
                holiday_dict["Other Errors"] = str(e)
                error_list.append(holiday_dict)

    if holiday_list:
        Holidays.objects.bulk_create(holiday_list)

    if os.path.exists(holiday_file):
        os.remove(holiday_file)

    return (error_list, total_rows)


def excel_holiday_import(file):
    """
    Imports holiday data from an Excel file.

    This function reads an Excel file containing holiday information, validates the data,
    and saves valid holiday records to the database using bulk creation for efficiency

    The expected format for the Excel file is:
    - "Holiday Name": Name of the holiday (string)
    - "Start Date": Start date of the holiday (date string in a recognized format)
    - "End Date": End date of the holiday (date string in a recognized format)
    - "Recurring": Indicates whether the holiday recurs ("yes" or "no")

    """
    error_list = []
    valid_holidays = []
    data_frame = pd.read_excel(file)
    holiday_dicts = data_frame.to_dict("records")

    for holiday in holiday_dicts:
        save = True
        try:
            name = holiday["Holiday Name"]

            try:
                start_date = pd.to_datetime(holiday["Start Date"]).date()
            except Exception:
                save = False
                holiday["Start Date Error"] = _("Invalid start date format {}").format(
                    holiday["Start Date"]
                )

            try:
                end_date = pd.to_datetime(holiday["End Date"]).date()
            except Exception:
                save = False
                holiday["End Date Error"] = _("Invalid end date format {}").format(
                    holiday["End Date"]
                )

            recurring_str = holiday.get("Recurring", "").lower()
            if recurring_str in ["yes", "no"]:
                recurring = recurring_str == "yes"
            else:
                save = False
                holiday["Recurring Field Error"] = _(
                    "Recurring must be {} or {}"
                ).format("yes", "no")

            if save:
                holiday_instance = Holidays(
                    name=name,
                    start_date=start_date,
                    end_date=end_date,
                    recurring=recurring,
                )
                valid_holidays.append(holiday_instance)
            else:
                error_list.append(holiday)

        except Exception as e:
            holiday["Other errors"] = str(e)
            error_list.append(holiday)

    if valid_holidays:
        Holidays.objects.bulk_create(valid_holidays)

    return error_list, len(holiday_dicts)


@login_required
@hx_request_required
@permission_required("base.add_holidays")
def holidays_info_import(request):
    result = None
    file_name = "HolidaysImportError.xlsx"
    path_info = None
    error_data = {
        "Holiday Name": [],
        "Start Date": [],
        "End Date": [],
        "Recurring": [],
        "Start Date Error": [],
        "End Date Error": [],
        "Recurring Field Error": [],
        "Other Errors": [],
    }

    # is_hx_request = request.headers.get('HX-Request') == 'true'

    if request.method == "POST":
        file = request.FILES.get("holidays_import")
        if file:
            content_type = file.content_type
            if content_type == "text/csv":
                error_list, total_count = csv_holiday_import(file)
                if error_list:
                    path_info = generate_error_report(error_list, error_data, file_name)
            elif (
                content_type
                == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ):
                error_list, total_count = excel_holiday_import(file)
                if error_list:
                    path_info = generate_error_report(error_list, error_data, file_name)
            else:
                messages.error(
                    request, _("The file you attempted to import is unsupported")
                )
                return HorillaRedirect(request)

            created_holidays_count = total_count - len(error_list)
            context = {
                "created_count": created_holidays_count,
                "error_count": len(error_list),
                "model": _("Holidays"),
                "path_info": path_info,
            }
            result = render_to_string("import_popup.html", context)

    return HttpResponse(result)


@login_required
def holiday_info_export(request):
    if request.META.get("HTTP_HX_REQUEST"):
        export_filter = HolidayFilter()
        export_column = HolidaysColumnExportForm()
        content = {
            "export_filter": export_filter,
            "export_column": export_column,
        }
        return render(
            request, "holiday/holiday_export_filter_form.html", context=content
        )
    return export_data(
        request=request,
        model=Holidays,
        filter_class=HolidayFilter,
        form_class=HolidaysColumnExportForm,
        file_name="Holidays_export",
    )


@login_required
@permission_required("base.view_holidays")
def holidays_settings_view(request):
    """
    Holidays ("Public Holidays") settings page. Migrated from the Configuration
    menu into Settings > Organization; reuses the existing nav/list HTMX
    endpoints.
    """
    return render(request, "base/settings/holidays.html")


@login_required
def holiday_view(request):
    """
    function used to view holidays.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return holiday view  template
    """
    queryset = Holidays.objects.all()[::-1]
    previous_data = request.GET.urlencode()
    page_number = request.GET.get("page")
    page_obj = paginator_qry(queryset, page_number)
    holiday_filter = HolidayFilter()

    return render(
        request,
        "holiday/holiday_view.html",
        {
            "holidays": page_obj,
            "form": holiday_filter.form,
            "pd": previous_data,
        },
    )


@login_required
@hx_request_required
def holiday_filter(request):
    """
    function used to filter holidays.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return holiday view template
    """
    queryset = Holidays.objects.all()
    previous_data = request.GET.urlencode()
    holiday_filter = HolidayFilter(request.GET, queryset).qs
    if request.GET.get("sortby"):
        holiday_filter = sortby(request, holiday_filter, "sortby")
    page_number = request.GET.get("page")
    page_obj = paginator_qry(holiday_filter[::-1], page_number)
    data_dict = parse_qs(previous_data)
    get_key_instances(Holidays, data_dict)
    return render(
        request,
        "holiday/holiday.html",
        {"holidays": page_obj, "pd": previous_data, "filter_dict": data_dict},
    )


@login_required
@hx_request_required
@permission_required("base.change_holidays")
def holiday_update(request, obj_id):
    """
    function used to update holiday.

    Parameters:
    request (HttpRequest): The HTTP request object.
    id : holiday id

    Returns:
    GET : return holiday update form template
    POST : return holiday view template
    """
    query_string = request.GET.urlencode()
    if query_string.startswith("pd="):
        previous_data = unquote(query_string[len("pd=") :])
    else:
        previous_data = unquote(query_string)
    holiday = Holidays.objects.get(id=obj_id)
    form = HolidayForm(instance=holiday)
    if request.method == "POST":
        form = HolidayForm(request.POST, instance=holiday)
        if form.is_valid():
            form.save()
            messages.success(request, _("Holidays updated successfully.."))
    return render(
        request,
        "holiday/holiday_update_form.html",
        {"form": form, "id": obj_id, "pd": previous_data},
    )


@login_required
@hx_request_required
@permission_required("base.delete_holidays")
def holiday_delete(request, obj_id):
    """
    function used to delete holiday.

    Parameters:
    request (HttpRequest): The HTTP request object.
    id : holiday id

    Returns:
    GET : return holiday view template
    """
    query_string = request.GET.urlencode()
    try:
        Holidays.objects.get(id=obj_id).delete()
        messages.success(request, _("Holidays deleted successfully.."))
    except Holidays.DoesNotExist:
        messages.error(request, _("Holidays not found."))
    except ProtectedError:
        messages.error(request, _("Related entries exists"))
    if not Holidays.objects.filter():
        return HorillaRedirect(request)
    return redirect(f"/holiday-filter?{query_string}")


@login_required
@require_http_methods(["POST"])
@permission_required("base.delete_holidays")
def bulk_holiday_delete(request):
    """
    Deletes multiple holidays based on IDs passed in the POST request.
    """
    ids = request.POST.getlist("ids")
    deleted_count = Holidays.objects.filter(id__in=ids).delete()[0]
    messages.success(
        request, _("{} Holidays have been successfully deleted.".format(deleted_count))
    )
    return redirect("holiday-filter")


@login_required
def holiday_select(request):
    page_number = request.GET.get("page")
    holidays = Holidays.objects.none()

    if page_number == "all":
        holidays = Holidays.objects.all()

    holiday_ids = [str(hol.id) for hol in holidays]
    total_count = holidays.count()

    context = {"employee_ids": holiday_ids, "total_count": total_count}

    return JsonResponse(context, safe=False)


@login_required
def holiday_select_filter(request):
    page_number = request.GET.get("page")
    filtered = request.GET.get("filter")
    filters = json.loads(filtered) if filtered else {}
    context = {}

    if page_number == "all":
        employee_filter = HolidayFilter(filters, queryset=Holidays.objects.all())

        # Get the filtered queryset
        filtered_employees = employee_filter.qs

        employee_ids = [str(emp.id) for emp in filtered_employees]
        total_count = filtered_employees.count()

        context = {"employee_ids": employee_ids, "total_count": total_count}

    return JsonResponse(context)


@login_required
@hx_request_required
@permission_required("base.add_companyleaves")
def company_leave_creation(request):
    """
    function used to create company leave.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return company leave creation form template
    POST : return company leave view template
    """
    form = CompanyLeaveForm()
    if request.method == "POST":
        form = CompanyLeaveForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("New company leave created successfully.."))
            if CompanyLeaves.objects.filter().count() == 1:
                return HorillaRedirect(request)
    return render(
        request, "company_leave/company_leave_creation_form.html", {"form": form}
    )


@login_required
@permission_required("base.view_companyleaves")
def company_leaves_settings_view(request):
    """
    Weekly Off Days ("Weekly Off Days") settings page. Migrated from the
    Configuration menu into Settings > Organization; reuses the existing
    nav/list HTMX endpoints.
    """
    return render(request, "base/settings/company_leaves.html")


@login_required
def company_leave_view(request):
    """
    function used to view company leave.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return company leave view template
    """
    queryset = CompanyLeaves.objects.all()
    previous_data = request.GET.urlencode()
    page_number = request.GET.get("page")
    page_obj = paginator_qry(queryset, page_number)
    company_leave_filter = CompanyLeaveFilter()
    return render(
        request,
        "company_leave/company_leave_view.html",
        {
            "company_leaves": page_obj,
            "weeks": WEEKS,
            "week_days": WEEK_DAYS,
            "form": company_leave_filter.form,
            "pd": previous_data,
        },
    )


@login_required
@hx_request_required
def company_leave_filter(request):
    """
    function used to filter company leave.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return company leave view template
    """
    queryset = CompanyLeaves.objects.all()
    previous_data = request.GET.urlencode()
    page_number = request.GET.get("page")
    company_leave_filter = CompanyLeaveFilter(request.GET, queryset).qs
    page_obj = paginator_qry(company_leave_filter, page_number)
    data_dict = parse_qs(previous_data)
    get_key_instances(CompanyLeaves, data_dict)

    return render(
        request,
        "company_leave/company_leave.html",
        {
            "company_leaves": page_obj,
            "weeks": WEEKS,
            "week_days": WEEK_DAYS,
            "pd": previous_data,
            "filter_dict": data_dict,
        },
    )


@login_required
@hx_request_required
@permission_required("base.change_companyleaves")
def company_leave_update(request, id):
    """
    function used to update company leave.

    Parameters:
    request (HttpRequest): The HTTP request object.
    id : company leave id

    Returns:
    GET : return company leave update form template
    POST : return company leave view template
    """
    company_leave = CompanyLeaves.objects.get(id=id)
    form = CompanyLeaveForm(instance=company_leave)
    if request.method == "POST":
        form = CompanyLeaveForm(request.POST, instance=company_leave)
        if form.is_valid():
            form.save()
            messages.success(request, _("Company leave updated successfully.."))
    return render(
        request,
        "company_leave/company_leave_update_form.html",
        {"form": form, "id": id},
    )


@login_required
@hx_request_required
@permission_required("base.delete_companyleaves")
def company_leave_delete(request, id):
    """
    function used to create company leave.

    Parameters:
    request (HttpRequest): The HTTP request object.

    Returns:
    GET : return company leave creation form template
    POST : return company leave view template
    """
    query_string = request.GET.urlencode()
    try:
        CompanyLeaves.objects.get(id=id).delete()
        messages.success(request, _("Company leave deleted successfully.."))
    except CompanyLeaves.DoesNotExist:
        messages.error(request, _("Company leave not found."))
    except ProtectedError:
        messages.error(request, _("Related entries exists"))
    if not CompanyLeaves.objects.filter():
        return HorillaRedirect(request)
    return redirect(f"/company-leave-filter?{query_string}")


@login_required
@hx_request_required
def view_penalties(request):
    """
    This method is used to filter or view the penalties
    """
    records = PenaltyFilter(request.GET).qs
    return render(request, "penalty/penalty_view.html", {"records": records})


@login_required
@permission_required("base.delete_penaltyaccounts")
def delete_penalities(request, penalty_id):
    penalty = PenaltyAccounts.objects.filter(id=penalty_id).first()
    if not penalty:
        return HorillaRedirect(
            request, message=_("No penalty account found matching the query.")
        )
    penalty.delete()
    messages.success(request, _("Penalty deleted suucessfully"))
    return HttpResponse(
        "<script>$('.reload-record').click();$('#reloadMessagesButton').click();</script>"
    )


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required("horilla_meet.view_googlecloudcredential"), name="dispatch"
)
class EnableIntegrationsView(View):
    """Handles enabling/disabling Google Meet integration dynamically."""

    def post(self, request, *args, **kwargs):
        """Handles POST request to enable/disable an integration app."""
        app_label = request.GET.get("app_label")

        if not app_label:
            messages.error(request, _("Missing app_label"))
            return HttpResponse("<script>window.location.reload()</script>")

        selected_company = request.session.get("selected_company")
        if selected_company and selected_company != "all":
            company = Company.objects.filter(id=selected_company).first()
        else:
            company = None

        enabled = request.POST.get("is_enabled") is not None
        integration_app, created = IntegrationApps.objects.update_or_create(
            app_label=app_label,
            company=company,
            defaults={"is_enabled": enabled},
        )
        try:
            app_config = apps.get_app_config(app_label)
            app_verbose_name = app_config.verbose_name
        except LookupError:
            app_verbose_name = app_label

        if enabled:
            messages.success(
                request,
                _("%(app_verbose_name)s enabled")
                % {"app_verbose_name": app_verbose_name},
            )
        else:
            messages.error(
                request,
                _("%(app_verbose_name)s disabled")
                % {"app_verbose_name": app_verbose_name},
            )

        return HttpResponse("<script>window.location.reload()</script>")


def is_jwt_token_valid(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        return None  # No token

    token = auth_header.split("Bearer ")[1].strip()
    try:
        UntypedToken(token)  # Will raise if invalid
        validated_token = JWTAuthentication().get_validated_token(token)
        user = JWTAuthentication().get_user(validated_token)
        return user
    except (InvalidToken, TokenError):
        return None


def protected_media(request, path):
    # Media-path prefixes that are safe to serve without authentication.
    # These are assets rendered on genuinely-public pages (login screen,
    # open recruitments, candidate self-tracking) and contain no sensitive
    # employee data. Do NOT add prefixes here without security review.
    public_media_prefixes = (
        "base/icon/",
        "base/company/icon/",
        "recruitment/candidate/profile/",
    )

    # Prevent path traversal
    try:
        media_path = safe_join(settings.MEDIA_ROOT, path)
    except Exception:
        # safe_join raises ValueError if traversal detected
        raise Http404("Invalid file path")

    if not os.path.exists(media_path) or not os.path.isfile(media_path):
        raise Http404("File not found")

    # Uploads never produce dot-files or dot-directories, but the Docker
    # entrypoint persists the generated SECRET_KEY at media/.generated_secret_key
    # so it survives restarts. Serving it would let any logged-in user forge
    # sessions and JWTs, so refuse every hidden path outright.
    if any(part.startswith(".") for part in path.split("/")):
        raise Http404("File not found")

    is_public_asset = any(path.startswith(prefix) for prefix in public_media_prefixes)

    if not is_public_asset:
        jwt_user = is_jwt_token_valid(request.META.get("HTTP_AUTHORIZATION", ""))
        if not request.user.is_authenticated and not jwt_user:
            messages.error(
                request,
                "You must be logged in or provide a valid token to access this file.",
            )
            return redirect("login")

    # Determine the content type from the extension and decide whether the
    # browser may render it inline. User-uploaded content that browsers treat
    # as active markup (HTML/SVG/XML/etc.) must never render in this origin --
    # doing so would turn any file upload into stored XSS (CWE-79). Such files
    # are forced to download instead. See GHSA-p68r-g665-5cm9.
    content_type, _encoding = mimetypes.guess_type(media_path)
    renderable_active_types = {
        "text/html",
        "application/xhtml+xml",
        "image/svg+xml",
        "application/xml",
        "text/xml",
        "application/xslt+xml",
        "text/javascript",
        "application/javascript",
        "application/x-javascript",
    }
    force_download = content_type is None or content_type in renderable_active_types

    response = FileResponse(open(media_path, "rb"))
    # Always send a content type so the browser does not sniff one of its own.
    response["Content-Type"] = content_type or "application/octet-stream"
    # Block MIME sniffing -- a browser must honour the declared type and not
    # re-interpret e.g. an octet-stream as HTML.
    response["X-Content-Type-Options"] = "nosniff"
    if force_download:
        filename = os.path.basename(media_path)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

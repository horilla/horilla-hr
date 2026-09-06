import logging
import os
import time
from datetime import datetime

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.signals import user_login_failed
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Max, Q
from django.db.models.signals import m2m_changed, post_delete, post_migrate, post_save
from django.dispatch import receiver
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from base.models import (
    Announcement,
    AnnouncementExpire,
    Company,
    DefaultExportPermission,
    PenaltyAccounts,
)
from horilla.methods import get_horilla_model_class


@receiver(post_save, sender=Company)
def create_announcement_expire_setting(sender, instance, created, raw, **kwargs):
    """
    Signal receiver that automatically creates an AnnouncementExpire object
    whenever a new Company is created. This does NOT skip creation during
    loaddata, so the object will also be created when fixture data is loaded.
    """
    AnnouncementExpire.objects.get_or_create(company_id=None)
    if created:
        AnnouncementExpire.objects.get_or_create(company_id=instance)


@receiver(post_save, sender=Company)
def create_default_export_permission(sender, instance, created, raw, **kwargs):
    """
    Give every new company an explicit "Default Export Access" row.

    Readers treat a missing row as enabled, so without this a company added
    after migration base.0003 would again have the permissive behaviour
    implied by absence rather than recorded as a decision. Mirrors the
    announcement-expire receiver above, including the NULL-company row that
    the "All companies" session scope reads.
    """
    DefaultExportPermission.objects.get_or_create(
        company_id=None, defaults={"is_enabled": True}
    )
    if created:
        DefaultExportPermission.objects.get_or_create(
            company_id=instance, defaults={"is_enabled": True}
        )


@receiver(post_save, sender=PenaltyAccounts)
def create_deduction_cutleave_from_penalty(sender, instance, created, **kwargs):
    """
    This is post save method, used to create deduction and cut available leave days
    """
    # only work when creating
    if created:
        penalty_amount = instance.penalty_amount
        if apps.is_installed("payroll") and penalty_amount:
            Deduction = get_horilla_model_class(app_label="payroll", model="deduction")
            penalty = Deduction()
            if instance.late_early_id:
                penalty.title = f"{instance.late_early_id.get_type_display()} penalty"
                penalty.one_time_date = (
                    instance.late_early_id.attendance_id.attendance_date
                )
            elif instance.leave_request_id:
                penalty.title = f"Leave penalty {instance.leave_request_id.end_date}"
                penalty.one_time_date = instance.leave_request_id.end_date
            else:
                penalty.title = f"Penalty on {datetime.today()}"
                penalty.one_time_date = datetime.today()
            penalty.include_active_employees = False
            penalty.is_fixed = True
            penalty.amount = instance.penalty_amount
            penalty.only_show_under_employee = True
            penalty.save()
            penalty.include_active_employees = False
            penalty.specific_employees.add(instance.employee_id)
            penalty.save()

        if (
            apps.is_installed("leave")
            and instance.leave_type_id
            and instance.minus_leaves
        ):
            available = instance.employee_id.available_leave.filter(
                leave_type_id=instance.leave_type_id
            ).first()
            unit = round(instance.minus_leaves * 2) / 2
            if not instance.deduct_from_carry_forward:
                available.available_days = max(0, (available.available_days - unit))
            else:
                available.carryforward_days = max(
                    0, (available.carryforward_days - unit)
                )

            available.save()


@receiver(post_delete, sender=PenaltyAccounts)
def delete_deduction_cutleave_from_penalty(sender, instance, **kwargs):
    """
    This is a post delete method, used to delete the deduction and update available leave days.
    """
    # Check if the deduction model is installed
    if apps.is_installed("payroll"):
        Deduction = get_horilla_model_class(app_label="payroll", model="deduction")

        # A CASCADE delete of the related AttendanceLateComeEarlyOut (e.g.
        # reset_backfilled_rows_before_reload) deletes this PenaltyAccounts
        # row as part of the same operation, before this signal fires --
        # the FK id column is still set, but fetching the related row
        # raises DoesNotExist instead of returning None like a plain
        # missing FK would. Resolve it once, tolerating that case, instead
        # of querying it fresh (and risking the same crash) at each of the
        # two call sites below.
        late_early = None
        if instance.late_early_id_id:
            try:
                late_early = instance.late_early_id
            except ObjectDoesNotExist:
                late_early = None

        if late_early:
            title = f"{late_early.get_type_display()} penalty"
        elif instance.leave_request_id:
            title = f"Leave penalty {instance.leave_request_id.end_date}"
        else:
            title = f"Penalty on {datetime.today()}"

        # Attempt to retrieve the deduction specifically associated with the penalty account
        deductions = Deduction.objects.filter(
            specific_employees=instance.employee_id,
            amount=instance.penalty_amount,
            title=title,
        )

        # If you have a date or other unique field, add it to the filter
        if late_early:
            deductions = deductions.filter(
                one_time_date=late_early.attendance_id.attendance_date
            )
        elif instance.leave_request_id:
            deductions = deductions.filter(
                one_time_date=instance.leave_request_id.end_date
            )
        else:
            deductions = deductions.filter(one_time_date=datetime.today())

        for deduction in deductions:
            deduction.delete()

    if apps.is_installed("leave") and instance.leave_type_id and instance.minus_leaves:
        available = instance.employee_id.available_leave.filter(
            leave_type_id=instance.leave_type_id
        ).first()
        if available:
            unit = round(instance.minus_leaves * 2) / 2
            if not instance.deduct_from_carry_forward:
                available.available_days += unit  # Restore the deducted days
            else:
                available.carryforward_days += (
                    unit  # Restore the deducted carryforward days
                )

            available.save()


# @receiver(post_migrate)
def clean_work_records(sender, **kwargs):
    if sender.label not in ["attendance"]:
        return
    from attendance.models import WorkRecords

    latest_records = (
        WorkRecords.objects.exclude(work_record_type="DFT")
        .values("employee_id", "date")
        .annotate(latest_id=Max("id"))
    )

    # Delete all but the latest WorkRecord
    deleted_count = 0
    for record in latest_records:
        deleted_count += (
            WorkRecords.objects.filter(
                employee_id=record["employee_id"], date=record["date"]
            )
            .exclude(id=record["latest_id"])
            .delete()[0]
        )


@receiver(post_migrate)
def create_shift_days(sender, **kwargs):
    from base.models import EmployeeShiftDay

    if not EmployeeShiftDay.objects.exists():
        days = [
            ("monday", "Monday"),
            ("tuesday", "Tuesday"),
            ("wednesday", "Wednesday"),
            ("thursday", "Thursday"),
            ("friday", "Friday"),
            ("saturday", "Saturday"),
            ("sunday", "Sunday"),
        ]

        EmployeeShiftDay.objects.bulk_create(
            [EmployeeShiftDay(day=day[0]) for day in days]
        )


# ---------------------------------------------------------------------------
# Default HRMS auth groups (created on migrate; no users are assigned)
# ---------------------------------------------------------------------------

# Apps whose migrations should trigger group create / permission fill-in.
_HRMS_GROUP_MIGRATE_APPS = {
    "base",
    "auth",
    "employee",
    "leave",
    "attendance",
    "payroll",
    "recruitment",
    "onboarding",
    "offboarding",
    "asset",
    "helpdesk",
    "project",
    "pms",
    "biometric",
    "horilla_documents",
}

# name -> permission rules
# apps: list of app_labels, or "__all__" for every installed HRMS app below
# actions: add / view / change / delete / export, or "__all__" for every permission
# (CRUD + custom Meta permissions such as approve_ / cancel_)
_DEFAULT_HRMS_GROUPS = {
    "Admin": {
        "apps": "__all__",
        "actions": "__all__",
    },
    "HR Manager": {
        "apps": (
            "base",
            "employee",
            "leave",
            "attendance",
            "recruitment",
            "onboarding",
            "offboarding",
            "asset",
            "horilla_documents",
            "helpdesk",
            "pms",
        ),
        "actions": ("add", "view", "change", "delete"),
    },
    "Payroll Manager": {
        "apps": ("payroll", "employee", "attendance", "leave"),
        "actions": ("add", "view", "change", "delete"),
        # Payroll leads need full payroll; employee/attendance/leave mainly for context
        "app_actions": {
            "employee": ("view", "change"),
            "attendance": ("view",),
            "leave": ("view",),
        },
    },
    "Attendance Manager": {
        "apps": ("attendance", "employee", "base"),
        "actions": ("add", "view", "change", "delete"),
        "app_actions": {
            "employee": ("view",),
            "base": ("view",),
        },
    },
    "Leave Manager": {
        "apps": ("leave", "employee"),
        "actions": ("add", "view", "change", "delete"),
        "app_actions": {
            "employee": ("view",),
        },
    },
    "Recruiter": {
        "apps": ("recruitment", "onboarding", "employee"),
        "actions": ("add", "view", "change", "delete"),
        "app_actions": {
            "employee": ("view", "add", "change"),
        },
    },
    "Asset Manager": {
        "apps": ("asset", "employee"),
        "actions": ("add", "view", "change", "delete"),
        "app_actions": {
            "employee": ("view",),
        },
    },
    "Helpdesk Agent": {
        "apps": ("helpdesk", "employee"),
        "actions": ("add", "view", "change", "delete"),
        "app_actions": {
            "employee": ("view",),
        },
    },
    "Project Manager": {
        "apps": ("project", "employee", "pms"),
        "actions": ("add", "view", "change", "delete"),
        "app_actions": {
            "employee": ("view",),
            "pms": ("view", "change", "add"),
        },
    },
    "Performance Manager": {
        "apps": ("pms", "employee"),
        "actions": ("add", "view", "change", "delete"),
        "app_actions": {
            "employee": ("view",),
        },
    },
}

_ALL_HRMS_APP_LABELS = (
    "auth",
    "base",
    "employee",
    "leave",
    "attendance",
    "payroll",
    "recruitment",
    "onboarding",
    "offboarding",
    "asset",
    "helpdesk",
    "project",
    "pms",
    "biometric",
    "horilla_documents",
    "horilla_automations",
    "horilla_audit",
    "accessibility",
)


def _is_app_available(label):
    """Return True if an app config exists for this label (e.g. 'auth', 'leave')."""
    try:
        apps.get_app_config(label)
        return True
    except LookupError:
        return False


def _resolve_group_permissions(config):
    """
    Build a Permission queryset for a default group config from currently
    installed apps / content types (skips apps that are not installed yet).
    """
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    app_labels = config.get("apps", ())
    if app_labels == "__all__":
        app_labels = [
            label for label in _ALL_HRMS_APP_LABELS if _is_app_available(label)
        ]
    else:
        app_labels = [label for label in app_labels if _is_app_available(label)]

    default_actions = config.get("actions", ("view",))
    app_actions = config.get("app_actions") or {}

    permission_ids = []
    for app_label in app_labels:
        actions = app_actions.get(app_label, default_actions)
        content_types = ContentType.objects.filter(app_label=app_label)
        if not content_types.exists():
            continue
        if actions == "__all__":
            permission_ids.extend(
                Permission.objects.filter(
                    content_type__in=content_types,
                ).values_list("id", flat=True)
            )
            continue
        for action in tuple(actions):
            permission_ids.extend(
                Permission.objects.filter(
                    content_type__in=content_types,
                    codename__startswith=f"{action}_",
                ).values_list("id", flat=True)
            )

    # Admin also needs Django auth group/permission management
    if config.get("apps") == "__all__" and _is_app_available("auth"):
        permission_ids.extend(
            Permission.objects.filter(
                content_type__app_label="auth",
                codename__in=[
                    "add_group",
                    "auth.change_group",
                    "auth.delete_group",
                    "view_group",
                    "add_permission",
                    "change_permission",
                    "delete_permission",
                    "view_permission",
                    "add_user",
                    "change_user",
                    "delete_user",
                    "view_user",
                ],
            ).values_list("id", flat=True)
        )

    return Permission.objects.filter(id__in=set(permission_ids))


def _sync_export_permissions():
    """
    Create an `export_<model>` Permission for every model that appears in
    the group/employee permission matrix (mirrors Django's own auto-created
    add/change/delete/view permissions, which don't include "export").
    """
    from django.conf import settings
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    no_permission_models = settings.NO_PERMISSION_MODALS
    for app_label in _ALL_HRMS_APP_LABELS:
        if not _is_app_available(app_label):
            continue
        for content_type in ContentType.objects.filter(app_label=app_label):
            if content_type.model in no_permission_models:
                continue
            model_class = content_type.model_class()
            if model_class is None:
                continue
            Permission.objects.get_or_create(
                content_type=content_type,
                codename=f"export_{content_type.model}",
                defaults={"name": f"Can export {model_class._meta.verbose_name}"},
            )


def _sync_default_hrms_groups():
    """
    Create default HRMS groups if missing and attach default permissions.
    Does not assign any users. Uses additive permission sync so later app
    migrations can fill permissions that were not available yet.
    """
    from django.contrib.auth.models import Group

    for name, config in _DEFAULT_HRMS_GROUPS.items():
        group, _created = Group.objects.get_or_create(name=name)
        permissions = _resolve_group_permissions(config)
        if permissions.exists():
            # Additive only — never strip permissions an admin may have customized
            group.permissions.add(*permissions)


@receiver(post_migrate)
def create_default_hrms_groups(sender, **kwargs):
    """
    Ensure standard HRMS auth groups exist after migrate.
    Groups are created without assigning employees; admins can assign later.
    """
    if getattr(sender, "label", None) not in _HRMS_GROUP_MIGRATE_APPS:
        return
    try:
        _sync_export_permissions()
        _sync_default_hrms_groups()
    except Exception:
        # Auth / contenttypes tables may not be ready for some migrate senders
        logging.getLogger(__name__).debug(
            "Skipping default HRMS group sync for %s",
            getattr(sender, "label", sender),
            exc_info=True,
        )


@receiver(m2m_changed, sender=Announcement.employees.through)
def filtered_employees(sender, instance, action, **kwargs):
    """
    filtered employees
    """
    if action not in ["post_add", "post_remove", "post_clear"]:
        return  # Only run after M2M changes
    employee_ids = list(instance.employees.values_list("id", flat=True))
    department_ids = list(instance.department.values_list("id", flat=True))
    job_position_ids = list(instance.job_position.values_list("id", flat=True))

    employees = instance.model_employee.objects.filter(
        Q(id__in=employee_ids)
        | Q(employee_work_info__department_id__in=department_ids)
        | Q(employee_work_info__job_position_id__in=job_position_ids)
    )

    instance.filtered_employees.set(employees)


# Logger setup
logger = logging.getLogger("django.security")

# Create a global dictionary to track login attempts and ban time per session
failed_attempts = {}
ban_time = {}

FAIL2BAN_LOG_ENABLED = os.path.exists(
    "security.log"
)  # Checking that any file is created for the details of the wrong logins.
# The file will be created only if you set the LOGGING in your settings.py


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request, **kwargs):
    """
    To ban the IP of user that enter wrong credentials for multiple times
    you should add this section in your settings.py file. And also it creates the security file for deatils of wrong logins.


    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'security_file': {
                'level': 'WARNING',
                'class': 'logging.FileHandler',
                'filename': '/var/log/django/security.log', # File Path for view the log details.
                                                            # Give the same path to the section FAIL2BAN_LOG_ENABLED = os.path.exists('security.log') in signals.py in Base.
            },
        },
        'loggers': {
            'django.security': {
                'handlers': ['security_file'],
                'level': 'WARNING',
                'propagate': False,
            },
        },
    }

    # This section is for giving the maxtry and bantime

    FAIL2BAN_MAX_RETRY = 3        # Same as maxretry in jail.local
    FAIL2BAN_BAN_TIME = 300       # Same as bantime in jail.local (in seconds)

    """

    # Checking that the file is created or not to initiate the ban functions.
    if not FAIL2BAN_LOG_ENABLED:
        return

    max_attempts = getattr(settings, "FAIL2BAN_MAX_RETRY", 3)
    ban_duration = getattr(settings, "FAIL2BAN_BAN_TIME", 300)

    username = credentials.get("username", "unknown")
    ip = request.META.get("REMOTE_ADDR", "unknown")
    session_key = (
        request.session.session_key or request.session._get_or_create_session_key()
    )

    # Check if currently banned
    if session_key in ban_time and ban_time[session_key] > time.time():
        banned_until = time.strftime("%H:%M", time.localtime(ban_time[session_key]))
        messages.info(
            request,
            _("You are banned until %(banned_until)s. Please try again later.")
            % {"banned_until": banned_until},
        )
        return redirect("/")

    # If ban expired, reset counters
    if session_key in ban_time and ban_time[session_key] <= time.time():
        del ban_time[session_key]
        if session_key in failed_attempts:
            del failed_attempts[session_key]

    # Initialize tracking if needed
    if session_key not in failed_attempts:
        failed_attempts[session_key] = 0

    failed_attempts[session_key] += 1
    attempts_left = max_attempts - failed_attempts[session_key]

    logger.warning(f"Invalid login attempt for user '{username}' from {ip}")

    if failed_attempts[session_key] >= max_attempts:
        ban_time[session_key] = time.time() + ban_duration
        messages.info(
            request,
            _(
                "You have been banned for %(minutes)s minutes due to multiple failed login attempts."
            )
            % {"minutes": ban_duration // 60},
        )
        return redirect("/")

    messages.info(
        request,
        _("You have %(attempts)s login attempt(s) left before a temporary ban.")
        % {"attempts": attempts_left},
    )
    return redirect("login")


class Fail2BanMiddleware:
    """
    Middleware to force password change for new employees.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session_key = request.session.session_key
        if not session_key:
            request.session.create()

        # Check ban and enforce it
        if session_key in ban_time and ban_time[session_key] > time.time():
            banned_until = time.strftime("%H:%M", time.localtime(ban_time[session_key]))
            messages.info(
                request,
                _("You are banned until %(banned_until)s. Please try again later.")
                % {"banned_until": banned_until},
            )
            return render(request, "403.html")

        # If ban expired, clear counters
        if session_key in ban_time and ban_time[session_key] <= time.time():
            del ban_time[session_key]
            if session_key in failed_attempts:
                del failed_attempts[session_key]

        return self.get_response(request)


settings.MIDDLEWARE.append("base.signals.Fail2BanMiddleware")

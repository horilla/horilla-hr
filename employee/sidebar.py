"""
employee/sidebar.py

To set Horilla sidebar for employee
"""

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from accessibility.methods import check_is_accessible
from base.templatetags.basefilters import is_reportingmanager
from horilla.horilla_middlewares import _thread_locals

request = getattr(_thread_locals, "request", None)
MENU = _("Employee")
IMG_SRC = "images/ui/employees.svg"


SUBMENUS = [
    {
        "menu": _("Dashboard"),
        "redirect": reverse_lazy("employee-dashboard"),
        "accessibility": "employee.sidebar.dashboard_accessibility",
    },
    {
        "menu": _("Employees"),
        "redirect": reverse_lazy("employee-view"),
        "accessibility": "employee.sidebar.employee_accessibility",
        "match_prefixes": [
            "/employee/employee-view-new/",
            "/employee/employee-view-update/",
        ],
    },
    {
        "menu": _("Organization Chart"),
        "redirect": reverse_lazy("organisation-chart"),
    },
    {
        "menu": _("Requests"),
        "redirect": reverse_lazy("requests-view"),
        "accessibility": "employee.sidebar.requests_accessibility",
    },
    {
        "menu": _("Work Schedules"),
        "redirect": reverse_lazy("work-schedules-view"),
        "accessibility": "employee.sidebar.work_schedules_accessibility",
    },
    {
        "menu": _("Policies & Discipline"),
        "redirect": reverse_lazy("policies-discipline-view"),
        # disciplinary-actions-detail-view/<pk>/ is a sibling URL (not a
        # sub-path of policies-discipline-view/), so it needs an explicit
        # prefix for the sidebar's path-based active-link highlighting to
        # match it.
        "match_prefixes": ["/employee/disciplinary-actions-detail-view/"],
    },
    {
        "menu": _("Configuration"),
        "redirect": reverse_lazy("employee-settings-view"),
        "accessibility": "employee.sidebar.employee_settings_accessibility",
    },
]


def document_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm(
        "horilla_documents.view_documentrequest"
    ) or is_reportingmanager(request.user)


def requests_accessibility(request, submenu, user_perms, *args, **kwargs):
    return True


def rotating_shift_assign_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm(
        "base.view_rotatingshiftassign"
    ) or is_reportingmanager(request.user)


def rotating_work_type_assign_accessibility(
    request, submenu, user_perms, *args, **kwargs
):
    return request.user.has_perm(
        "base.view_rotatingworktypeassign"
    ) or is_reportingmanager(request.user)


def shift_roster_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_roster") or is_reportingmanager(
        request.user
    )


def work_schedules_accessibility(request, submenu, user_perms, *args, **kwargs):
    return (
        rotating_shift_assign_accessibility(
            request, submenu, user_perms, *args, **kwargs
        )
        or rotating_work_type_assign_accessibility(
            request, submenu, user_perms, *args, **kwargs
        )
        or shift_roster_accessibility(request, submenu, user_perms, *args, **kwargs)
    )


def employee_settings_accessibility(request, submenu, user_perms, *args, **kwargs):
    return (
        employee_shift_accessibility(request, submenu, user_perms, *args, **kwargs)
        or shift_schedule_accessibility(request, submenu, user_perms, *args, **kwargs)
        or rotating_shift_accessibility(request, submenu, user_perms, *args, **kwargs)
        or work_type_accessibility(request, submenu, user_perms, *args, **kwargs)
        or rotating_work_type_accessibility(
            request, submenu, user_perms, *args, **kwargs
        )
        or employee_type_accessibility(request, submenu, user_perms, *args, **kwargs)
        or employee_tag_accessibility(request, submenu, user_perms, *args, **kwargs)
    )


def dashboard_accessibility(request, submenu, user_perms, *args, **kwargs):
    """
    Employee dashboard is limited to what the dashboard views allow:
    employee view permission holders and reporting managers.
    """
    return request.user.has_perm("employee.view_employee") or is_reportingmanager(
        request.user
    )


def employee_accessibility(request, submenu, user_perms, *args, **kwargs):
    """
    Employee accessibility method
    """
    cache_key = request.session.session_key + "accessibility_filter"
    employee = getattr(request.user, "employee_get", None)
    return (
        is_reportingmanager(request.user)
        or request.user.has_perm("employee.view_employee")
        or check_is_accessible("employee_view", cache_key, employee)
    )


# ---------------------------------------------------------------------------
# Settings menu registrations
# ---------------------------------------------------------------------------


def work_type_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_worktype")


def rotating_work_type_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_rotatingworktype")


def employee_shift_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_employeeshift")


def rotating_shift_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_rotatingshift")


def shift_schedule_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_employeeshiftschedule")


def employee_type_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("base.view_employeetype")


def employee_tag_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("employee.view_employeetag")

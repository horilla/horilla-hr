"""
leave/sidebar.py
"""

from django.apps import apps
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from base.templatetags.basefilters import is_leave_approval_manager, is_reportingmanager
from horilla.menu import settings_menu
from leave.templatetags.leavefilters import is_compensatory

MENU = _("Leave")
IMG_SRC = "images/ui/leave.svg"

SUBMENUS = [
    {
        "menu": _("Dashboard"),
        "redirect": reverse_lazy("leave-dashboard"),
        "accessibility": "leave.sidebar.dashboard_accessibility",
    },
    {
        "menu": _("My Leave Requests"),
        "redirect": reverse_lazy("user-request-view"),
        # my-leave-request-detail-view/<pk>/ is a sibling URL (not a sub-path
        # of user-request-view/), so it needs an explicit prefix for the
        # sidebar's path-based active-link highlighting to match it.
        "match_prefixes": ["/leave/my-leave-request-detail-view/"],
    },
    {
        "menu": _("Compensatory Leave Requests"),
        "redirect": reverse_lazy("view-compensatory-leave"),
        "accessibility": "leave.sidebar.componstory_accessibility",
        # compensatory-leave-individual-view/<id>/ is a sibling URL (not a
        # sub-path of view-compensatory-leave/), so it needs an explicit
        # prefix for the sidebar's path-based active-link highlighting to
        # match it.
        "match_prefixes": ["/leave/compensatory-leave-individual-view/"],
    },
    {
        "menu": _("Leave Requests"),
        "redirect": reverse_lazy("request-view"),
        "accessibility": "leave.sidebar.leave_request_accessibility",
        # one-request-view/<id>/ and leave-requests-detail-view/<pk>/ are
        # sibling URLs (not sub-paths of request-view/), so they need
        # explicit prefixes for the sidebar's path-based active-link
        # highlighting to match them.
        "match_prefixes": [
            "/leave/one-request-view/",
            "/leave/leave-requests-detail-view/",
        ],
    },
    {
        "menu": _("Leave Allocation Request"),
        "redirect": reverse_lazy("leave-allocation-request-view"),
        # These are sibling URLs (not sub-paths of
        # leave-allocation-request-view/), so they need explicit prefixes for
        # the sidebar's path-based active-link highlighting to match them.
        "match_prefixes": [
            "/leave/leave-allocation-request-single-view/",
            "/leave/detail-leave-allocation-request/",
            "/leave/leave-allocation-request-detail-view/",
        ],
    },
    {
        "menu": _("Leave Balances"),
        "redirect": reverse_lazy("assign-view"),
        "accessibility": "leave.sidebar.assign_accessibility",
        # available-leave-single-view/<pk>/ is a sibling URL (not a sub-path
        # of assign-view/), so it needs an explicit prefix for the sidebar's
        # path-based active-link highlighting to match it.
        "match_prefixes": ["/leave/available-leave-single-view/"],
    },
    {
        "menu": _("Restricted Leave Periods"),
        "redirect": reverse_lazy("restrict-view"),
        "accessibility": "leave.sidebar.restrict_leave_accessibility",
        # restricted-days-detail-view/<pk>/ is a sibling URL (not a sub-path
        # of restrict-view/), so it needs an explicit prefix for the
        # sidebar's path-based active-link highlighting to match it.
        "match_prefixes": ["/leave/restricted-days-detail-view/"],
    },
    {
        "menu": _("Public Holidays"),
        "redirect": reverse_lazy("holiday-view"),
        # "accessibility": "leave.sidebar.holiday_accessibility",
    },
    {
        "menu": _("Weekly Off Days"),
        "redirect": reverse_lazy("company-leave-view"),
        "accessibility": "leave.sidebar.company_leave_accessibility",
    },
    {
        "menu": _("Configuration"),
        "redirect": reverse_lazy("leave-settings-view"),
        "accessibility": "leave.sidebar.leave_settings_accessibility",
    },
]


def dashboard_accessibility(request, submenu, user_perms, *args, **kwargs):
    """The leave dashboard is the admin-level one; it needs view_leaverequest."""
    return request.user.has_perm("leave.view_leaverequest")


def leave_request_accessibility(request, submenu, user_perms, *args, **kwargs):
    return (
        request.user.has_perm("leave.view_leaverequest")
        or is_leave_approval_manager(request.user)
        or is_reportingmanager(request.user)
    )


def assign_accessibility(request, submenu, user_perm, *args, **kwargs):
    submenu["redirect"] = submenu["redirect"] + "?field=leave_type_id"
    return request.user.has_perm("leave.view_availableleave") or is_reportingmanager(
        request.user
    )


def holiday_accessibility(request, submenu, user_perms, *args, **kwargs):
    return not request.user.is_superuser and not request.user.has_perm(
        "base.view_holidays"
    )


def company_leave_accessibility(request, submenu, user_perms, *args, **kwargs):
    return not request.user.is_superuser and not request.user.has_perm(
        "base.view_companyleaves"
    )


def restrict_leave_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("leave.view_restrictleave")


def componstory_accessibility(request, submenu, user_perms, *args, **kwargs):
    return apps.is_installed("attendance") and is_compensatory(request.user)


# ---------------------------------------------------------------------------
# Settings menu registrations
# ---------------------------------------------------------------------------


def leave_rules_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("leave.add_restrictleave") or (
        apps.is_installed("attendance")
        and request.user.has_perm("attendance.view_attendancevalidationcondition")
    )


def leave_settings_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("leave.view_restrictleave")


@settings_menu.register
class LeaveSettings:
    title = _("Leave")
    order = 6
    condition = lambda self, request: apps.is_installed("leave")
    items = [
        {
            "label": _("Leave Rules"),
            "url": reverse_lazy("leave-rules-view"),
            "accessibility": leave_rules_accessibility,
            "search_entries": [
                {
                    "text": _("Compensatory Leave"),
                    "description": _("Enable compensatory leave requests"),
                },
                {
                    "text": _("Restrict Past Date Leave"),
                    "description": _(
                        "Only admins can create leave requests for past dates"
                    ),
                },
            ],
        },
    ]

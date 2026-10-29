"""
attendance/sidebar.py
"""

from django.apps import apps
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from base.context_processors import enable_late_come_early_out_tracking
from base.templatetags.basefilters import is_reportingmanager
from horilla.menu import settings_menu

MENU = _("Attendance")
IMG_SRC = "images/ui/attendances.svg"


SUBMENUS = [
    {
        "menu": _("Dashboard"),
        "redirect": reverse_lazy("attendance-dashboard"),
        "accessibility": "attendance.sidebar.dashboard_accessibility",
    },
    {
        "menu": _("My Attendances"),
        "redirect": reverse_lazy("view-my-attendance"),
        # my-attendance-detail/<pk>/ is a sibling URL (not a sub-path of
        # view-my-attendance/), so it needs an explicit prefix for the
        # sidebar's path-based active-link highlighting to match it.
        "match_prefixes": ["/attendance/my-attendance-detail/"],
    },
    {
        "menu": _("Attendances"),
        "redirect": reverse_lazy("attendance-view"),
        "accessibility": "attendance.sidebar.attendances_accessibility",
        # These tabs' detail views are sibling URLs (not sub-paths of
        # attendance-view/), so they need explicit prefixes for the
        # sidebar's path-based active-link highlighting to match them.
        "match_prefixes": [
            "/attendance/validate-detail-view/",
            "/attendance/ot-detail-view/",
            "/attendance/validated-detail-view/",
        ],
    },
    {
        "menu": _("Attendance Requests"),
        "redirect": reverse_lazy("request-attendance-view"),
        # attendances-tab-detail-view/<pk>/ is a sibling URL (not a sub-path
        # of request-attendance-view/), so it needs an explicit prefix for
        # the sidebar's path-based active-link highlighting to match it.
        "match_prefixes": ["/attendance/attendances-tab-detail-view/"],
    },
    {
        "menu": _("Check-in / Check-out Log"),
        "redirect": reverse_lazy("attendance-activity-view"),
        # attendance-activity-single-view/<pk>/ is a sibling URL (not a
        # sub-path of attendance-activity-view/), so it needs an explicit
        # prefix for the sidebar's path-based active-link highlighting to
        # match it.
        "match_prefixes": ["/attendance/attendance-activity-single-view/"],
    },
    {
        "menu": _("Late Arrival & Early Departure"),
        "redirect": reverse_lazy("late-come-early-out-view"),
        "accessibility": "attendance.sidebar.tracking_accessibility",
        # late-in-early-out-single-view/<pk>/ is a sibling URL (not a
        # sub-path of late-come-early-out-view/), so it needs an explicit
        # prefix for the sidebar's path-based active-link highlighting to
        # match it.
        "match_prefixes": ["/attendance/late-in-early-out-single-view/"],
    },
    {
        "menu": _("Monthly Summary"),
        "redirect": reverse_lazy("attendance-monthly-summary"),
        "accessibility": "attendance.sidebar.monthly_summary_accessibility",
    },
    {
        "menu": _("Time Policies"),
        "redirect": reverse_lazy("grace-time-view"),
        "accessibility": "attendance.sidebar.validation_condition_accessibility",
    },
]


def attendances_accessibility(request, submenu, user_perms, *args, **kwargs):
    """
    Check if the user has permission to view attendance or is a reporting manager.
    """
    return request.user.has_perm("attendance.view_attendance") or is_reportingmanager(
        request.user
    )


def dashboard_accessibility(request, submenu, user_perms, *args, **kwargs):
    """
    Check if the user has permission to view attendance or is a reporting manager.
    """
    return (
        request.user.is_superuser
        or request.user.has_perm("attendance.view_attendance")
        or is_reportingmanager(request.user)
    )


def tracking_accessibility(request, submenu, user_perms, *args, **kwargs):
    """
    Determine if late come/early out tracking is enabled and user has access.
    """
    tracking_enabled = enable_late_come_early_out_tracking(None).get("tracking")
    has_access = (
        request.user.is_superuser
        or request.user.has_perm("attendance.view_attendancelatecomeearlyout")
        or is_reportingmanager(request.user)
    )
    return tracking_enabled and has_access


def monthly_summary_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("attendance.view_attendance") or is_reportingmanager(
        request.user
    )


# ---------------------------------------------------------------------------
# Settings menu registrations
# ---------------------------------------------------------------------------


def validation_condition_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("attendance.view_attendancevalidationcondition")


def biometric_accessibility(request, submenu, user_perms, *args, **kwargs):
    return apps.is_installed("biometric") and request.user.has_perm(
        "base.view_biometricattendance"
    )


def ip_restriction_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("attendance.add_attendance")


def attendance_rule_accessibility(request, submenu, user_perms, *args, **kwargs):
    user = request.user
    return (
        user.has_perm("base.view_tracklatecomeearlyout")
        or user.has_perm("attendance.change_attendancegeneralsetting")
        or user.has_perm("attendance.view_attendancegeneralsetting")
        or (
            apps.is_installed("biometric")
            and user.has_perm("base.view_biometricattendance")
        )
        or user.has_perm("attendance.add_attendance")
        or (
            apps.is_installed("geofencing")
            and user.has_perm("geofencing.add_geofencing")
        )
        or (
            apps.is_installed("facedetection")
            and user.has_perm("facedetection.add_facedetection")
        )
    )


def geo_face_accessibility(request, submenu, user_perms, *args, **kwargs):
    has_geo = apps.is_installed("geofencing") and request.user.has_perm(
        "geofencing.add_geofencing"
    )
    has_face = apps.is_installed("facedetection") and request.user.has_perm(
        "facedetection.add_facedetection"
    )
    return has_geo or has_face


@settings_menu.register
class AttendanceSettings:
    title = _("Attendance")
    order = 5
    condition = lambda self, request: apps.is_installed("attendance")
    items = [
        {
            "label": _("Attendance Rules"),
            "url": reverse_lazy("attendance-rule-view"),
            "accessibility": attendance_rule_accessibility,
            "search_entries": [
                {
                    "text": _("Enable Check In / Check Out"),
                    "description": _(
                        "Employees record attendance using the Check-In/Out button"
                    ),
                },
                {
                    "text": _("At-Work Tracker"),
                    "description": _(
                        "Show live at-work hours in the navbar inside the check-in button"
                    ),
                },
                {
                    "text": _("Track Late Arrival & Early Departure"),
                    "description": _(
                        "Track late arrivals and early departures of employees"
                    ),
                },
                {
                    "text": _("IP Login Restriction"),
                    "description": _(
                        "Restrict attendance marking to specific IP addresses only"
                    ),
                },
                {
                    "text": _("Biometric Attendance"),
                    "description": _("Enable biometric devices for attendance marking"),
                },
                {
                    "text": _("Face Detection"),
                    "description": _(
                        "Allow employees to mark attendance using face detection"
                    ),
                },
                {
                    "text": _("Geofencing"),
                    "description": _(
                        "Restrict attendance marking to a geographic area"
                    ),
                },
            ],
        },
    ]

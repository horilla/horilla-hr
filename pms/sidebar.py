"""
pms/sidebar.py
"""

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from base.templatetags.basefilters import is_reportingmanager

MENU = _("Performance")
IMG_SRC = "images/ui/pms.svg"


SUBMENUS = [
    {
        "menu": _("Dashboard"),
        "redirect": reverse_lazy("dashboard-view"),
        "accessibility": "pms.sidebar.dashboard_accessibility",
    },
    {
        "menu": _("Employee objective"),
        "redirect": reverse_lazy("objective-list-view"),
        # objective-detailed-view/<id>/ is a sibling URL (not a sub-path of
        # objective-list-view/), so it needs an explicit prefix for the sidebar's
        # path-based active-link highlighting to match it.
        "match_prefixes": ["/pms/objective-detailed-view/"],
    },
    {
        "menu": _("Key Results"),
        "redirect": reverse_lazy("view-key-result"),
        "accessibility": "pms.sidebar.key_result_accessibility",
        # key-result-detail-view/<pk>/ is a sibling URL (not a sub-path of
        # view-key-result/), so it needs an explicit prefix for the sidebar's
        # path-based active-link highlighting to match it.
        "match_prefixes": ["/pms/key-result-detail-view/"],
    },
    {
        "menu": _("360 Feedback"),
        "redirect": reverse_lazy("feedback-view"),
        # feedback-creation/ and feedback-detailed-view/<id>/ are sibling URLs
        # (not sub-paths of feedback-view/), so they need explicit prefixes
        # for the sidebar's path-based active-link highlighting to match them.
        "match_prefixes": [
            "/pms/feedback-creation/",
            "/pms/feedback-detailed-view/",
        ],
    },
    {
        "menu": _("Meetings"),
        "redirect": reverse_lazy("view-meetings"),
        # meetings-detail-view/<pk>/ is a sibling URL (not a sub-path of
        # view-meetings/), so it needs an explicit prefix for the sidebar's
        # path-based active-link highlighting to match it.
        "match_prefixes": ["/pms/meetings-detail-view/"],
    },
    {
        "menu": _("Bonus Points"),
        "redirect": reverse_lazy("employee-bonus-point"),
        # update-employee-bonus-point/<pk>/ is a sibling URL (not a sub-path of
        # employee-bonus-point/), so it needs an explicit prefix for the sidebar's
        # path-based active-link highlighting to match it.
        "match_prefixes": ["/pms/update-employee-bonus-point/"],
    },
    {
        "menu": _("Configuration"),
        "redirect": reverse_lazy("performance-settings-view"),
        "accessibility": "pms.sidebar.performance_settings_accessibility",
        # question-template-detailed-view/<id>/ is a sibling URL (not a
        # sub-path of performance-settings-view/), so it needs an explicit
        # prefix for the sidebar's path-based active-link highlighting to
        # match it.
        "match_prefixes": ["/pms/question-template-detailed-view/"],
    },
]


def dashboard_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("pms.view_employeeobjective")


def objective_template_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.is_superuser or request.user.has_perm("pms.add_objective")


def key_result_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("pms.view_keyresult")


def period_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("pms.view_period") or is_reportingmanager(request.user)


def question_template_accessibility(request, submenu, user_perms, *args, **kwargs):
    return request.user.has_perm("pms.view_questiontemplate") or is_reportingmanager(
        request.user
    )


def performance_settings_accessibility(request, submenu, user_perms, *args, **kwargs):
    return (
        request.user.is_superuser
        or request.user.has_perm("pms.add_bonuspointsetting")
        or request.user.has_perm("pms.view_objective")
        or request.user.has_perm("pms.view_questiontemplate")
        or request.user.has_perm("pms.view_period")
        or is_reportingmanager(request.user)
    )

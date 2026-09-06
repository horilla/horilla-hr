"""
offboarding/sidebar.py
"""

from django.apps import apps
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _

from base.context_processors import resignation_request_enabled
from horilla.menu import settings_menu
from offboarding.templatetags.offboarding_filter import (
    any_manager,
    is_offboarding_employee,
)

MENU = _("Offboarding")
IMG_SRC = "images/ui/exit-outline.svg"
ACCESSIBILITY = "offboarding.sidebar.offboarding_accessibility"


SUBMENUS = [
    {
        "menu": _("Dashboard"),
        "redirect": reverse("offboarding-dashboard"),
        "accessibility": "offboarding.sidebar.dashboard_accessibility",
    },
    {
        "menu": _("Resignation Letters"),
        "redirect": reverse("resignation-request-view"),
        "accessibility": "offboarding.sidebar.resignation_letter_accessibility",
    },
    {
        "menu": _("Exit Process"),
        "redirect": reverse("offboarding-pipeline"),
    },
]


def offboarding_accessibility(request, menu, user_perms, *args, **kwargs):
    accessible = False
    try:
        accessible = (
            request.user.has_module_perms("offboarding")
            or any_manager(request.user.employee_get)
            or is_offboarding_employee(request.user.employee_get)
        )
    except Exception:
        # employee_get raises for a user with no Employee row; the menu
        # should then simply not be shown. `except Exception` instead of a
        # bare `finally` so KeyboardInterrupt and SystemExit still propagate.
        pass
    return accessible


def resignation_letter_accessibility(request, menu, user_perms, *args, **kwargs):
    return resignation_request_enabled(request)[
        "enabled_resignation_request"
    ] and request.user.has_perm("offboarding.view_resignationletter")


def dashboard_accessibility(request, *args):
    """
    Check if the user has permission to view the dashboard.
    """

    return request.user.has_module_perms("offboarding") or any_manager(
        request.user.employee_get
    )


# ---------------------------------------------------------------------------
# Settings menu registration
# ---------------------------------------------------------------------------


def offboarding_rules_accessibility(request, submenu, user_perms, *args, **kwargs):
    user = request.user
    return user.has_perm("offboarding.change_offboardinggeneralsetting") or (
        apps.is_installed("payroll")
        and user.has_perm("payroll.change_payrollgeneralsetting")
    )


@settings_menu.register
class OffboardingSettings:
    title = _("Offboarding")
    order = 8
    condition = lambda self, request: apps.is_installed("offboarding")
    items = [
        {
            "label": _("Offboarding Rules"),
            "url": reverse_lazy("offboarding-rules-view"),
            "accessibility": offboarding_rules_accessibility,
            "search_entries": [
                {
                    "text": _("Allow Resignation Request"),
                    "description": _("Allow employees to submit resignation requests"),
                },
                {
                    "text": _("Default Notice Period"),
                    "description": _(
                        "Default days between resignation and last working day"
                    ),
                },
            ],
        },
    ]

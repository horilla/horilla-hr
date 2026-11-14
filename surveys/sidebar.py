"""surveys/sidebar.py"""

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

MENU = _("Surveys")
IMG_SRC = "images/ui/survey.svg"
ACCESSIBILITY = "surveys.sidebar.surveys_accessibility"

SUBMENUS = [
    {"menu": _("Dashboard"), "redirect": reverse("surveys-dashboard")},
    {
        "menu": _("Surveys"),
        "redirect": reverse("surveys-view"),
        # a survey's own page
        "match_prefixes": ["/surveys/survey-detail/"],
    },
    {"menu": _("Library"), "redirect": reverse("surveys-library")},
]


def surveys_accessibility(request, menu, user_perms, *args, **kwargs):
    """HR with the module's permissions, or a manager of any survey."""
    if request.user.has_module_perms("surveys"):
        return True
    try:
        employee = request.user.employee_get
    except Exception:
        return False
    return employee.surveys_managed.exists()

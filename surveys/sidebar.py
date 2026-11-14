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
    """The menu is for HR. A manager of one survey reaches it from the link in
    their notification, and has no use for the lists and the library."""
    return request.user.has_module_perms("surveys")

"""
company_onboarding/sidebar.py

To set Horilla sidebar for company_onboarding.
"""

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

MENU = _("Company Setup")
ACCESSIBILITY = "company_onboarding.sidebar.menu_accessibility"
IMG_SRC = "images/ui/rocket.svg"

SUBMENUS = [
    {
        "menu": _("Client Companies"),
        "redirect": reverse("company-onboarding-list"),
    },
]


def menu_accessibility(
    request, _menu: str = "", user_perms=None, *args, **kwargs
) -> bool:
    return request.user.has_perm("base.view_company")

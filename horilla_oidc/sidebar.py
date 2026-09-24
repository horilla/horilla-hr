"""
Adds the SSO entry to the Settings sidebar's Integrations section (the
``horilla.menu.settings_menu`` registry the themed settings page renders).
Imported from ``apps.py`` ready().
"""

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from base.sidebar import IntegrationsSettings

IntegrationsSettings.items.append(
    {
        "label": _("Single Sign-On (OIDC)"),
        "url": reverse_lazy("oidc-settings"),
        "accessibility": lambda request, *args, **kwargs: request.user.is_superuser,
        "search_entries": [
            {"text": _("Single Sign-On"), "description": _("Let employees sign in through your identity provider")},
            {"text": _("OIDC"), "description": _("OpenID Connect: Okta, Microsoft Entra ID, Google Workspace, Keycloak")},
            {"text": _("SSO"), "description": _("Single Sign-On configuration")},
        ],
    }
)

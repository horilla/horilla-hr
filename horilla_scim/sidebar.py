"""
Adds the SCIM entry to the Settings sidebar's Integrations section.
Imported from apps.py ready().
"""

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from base.sidebar import IntegrationsSettings

IntegrationsSettings.items.append(
    {
        "label": _("SCIM Provisioning"),
        "url": reverse_lazy("scim-settings"),
        "accessibility": lambda request, *args, **kwargs: request.user.is_superuser,
        "search_entries": [
            {
                "text": _("SCIM Provisioning"),
                "description": _(
                    "Let your identity provider create, update and deactivate employees"
                ),
            },
            {
                "text": _("SCIM Token"),
                "description": _(
                    "Bearer token for Okta, Microsoft Entra ID, OneLogin, JumpCloud"
                ),
            },
        ],
    }
)

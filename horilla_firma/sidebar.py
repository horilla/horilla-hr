"""
Settings-menu entry for the Firma e-signature integration.

Imported from apps.py ready() so the registration runs at startup.
"""

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from horilla.menu import settings_menu
from horilla_firma.accessibility import settings_accessibility


@settings_menu.register
class FirmaSettingsMenu:
    title = _("E-Signature")
    order = 12
    items = [
        {
            "label": _("Firma E-Signature"),
            "url": reverse_lazy("firma-settings"),
            "accessibility": settings_accessibility,
            "search_entries": [
                {
                    "text": _("Firma E-Signature"),
                    "description": _(
                        "Send offer letters to candidates for electronic signature"
                    ),
                },
                {
                    "text": _("Firma API Key"),
                    "description": _("API key of the Firma workspace to send from"),
                },
                {
                    "text": _("Firma Webhook"),
                    "description": _(
                        "Receive signing updates and signed documents from Firma"
                    ),
                },
            ],
        },
    ]

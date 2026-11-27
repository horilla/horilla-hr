"""
assets/sidebar.py
"""

from django.apps import apps
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _

from horilla.menu import settings_menu

MENU = _("Assets")
IMG_SRC = "images/ui/assets.svg"

SUBMENUS = [
    {
        "menu": _("Dashboard"),
        "redirect": reverse("asset-dashboard"),
        "accessibility": "asset.sidebar.dashboard_accessibility",
        # The dashboard's "Expiring Soon" widget links straight to an asset's
        # detail page (a plain <a href>, not a modal), which is a sibling URL
        # rather than a sub-path of asset-dashboard/, so it needs an explicit
        # prefix for the sidebar's path-based active-link highlighting to match it.
        "match_prefixes": ["/asset/asset-information/"],
    },
    {
        "menu": _("Assets"),
        "redirect": reverse("asset-category-view"),
        "accessibility": "asset.sidebar.dashboard_accessibility",
        # asset-detail-view/<pk>/ and asset-list/<cat_id>/ are sibling URLs
        # (not sub-paths of asset-category-view/), so they need explicit
        # prefixes for the sidebar's path-based active-link highlighting to
        # match them.
        "match_prefixes": ["/asset/asset-detail-view/", "/asset/asset-list/"],
    },
    {
        "menu": _("Asset Batches"),
        "redirect": reverse("asset-batch-view"),
        "accessibility": "asset.sidebar.lot_accessibility",
        # asset-batch-detail-view/<pk>/ is a sibling URL (not a sub-path of
        # asset-batch-view/), so it needs an explicit prefix for the sidebar's
        # path-based active-link highlighting to match it.
        "match_prefixes": ["/asset/asset-batch-detail-view/"],
    },
    {
        "menu": _("Requests & Allocation"),
        "redirect": reverse("asset-request-allocation-view"),
        # The "Asset Renewal" action on this page is a plain <a href> full-page
        # link (not a modal), and asset-renewal/ is a sibling URL rather than a
        # sub-path of asset-request-allocation-view/, so it needs an explicit
        # prefix for the sidebar's path-based active-link highlighting to match it.
        "match_prefixes": ["/asset/asset-renewal/"],
    },
    {
        "menu": _("Asset History"),
        "redirect": reverse("asset-history"),
        "accessibility": "asset.sidebar.history_accessibility",
        # asset-history-detail-view/<pk>/ and asset-history-single-view/<id>/
        # are sibling URLs (not sub-paths of asset-history/), so they need
        # explicit prefixes for the sidebar's path-based active-link
        # highlighting to match them.
        "match_prefixes": [
            "/asset/asset-history-detail-view/",
            "/asset/asset-history-single-view/",
        ],
    },
]


def dashboard_accessibility(request, submenu, user_perms, *args, **kwargs):
    """
    Determine if the user has the necessary permissions to access the
    dashboard and asset category view.
    """
    return request.user.has_perm("asset.view_assetcategory")


def history_accessibility(request, submenu, user_perms, *args, **kwargs):
    """
    Determine if the user has the necessary permissions to access the
    dashboard and asset category view.
    """
    return request.user.has_perm("asset.view_assetassignment")


def lot_accessibility(request, subment, user_perms, *args, **kwargs):
    """
    Asset batch sidebar accessibility method
    """
    return request.user.has_perm("asset.view_assetlot")


def asset_rule_accessibility(request, submenu, user_perms, *args, **kwargs):
    """
    Determine if the user has the necessary permissions to access the
    Asset Rule settings page.
    """
    return request.user.has_perm(
        "asset.change_assetgeneralsetting"
    ) or request.user.has_perm("asset.view_assetgeneralsetting")


@settings_menu.register
class AssetSettings:
    """
    Registers the Assets section and its items in the Settings sidebar.
    """

    title = _("Assets")
    order = 9
    condition = lambda self, request: apps.is_installed("asset")
    items = [
        {
            "label": _("Asset Rule"),
            "url": reverse_lazy("asset-rule-view"),
            "accessibility": asset_rule_accessibility,
            "search_entries": [
                {
                    "text": _("Enable Asset Fine"),
                    "description": _(
                        "Allow adding a fine for an employee when an asset is returned"
                    ),
                },
            ],
        },
    ]

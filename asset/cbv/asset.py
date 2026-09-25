from typing import Any

from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from asset.filters import AssetFilter
from asset.models import Asset
from horilla_views.cbv_methods import login_required, permission_required
from horilla_views.generic.cbv.views import HorillaDetailedView, HorillaListView


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("asset.view_asset"), name="dispatch")
class AssetListView(HorillaListView):
    """
    list view for batch number
    """

    model = Asset
    filter_class = AssetFilter
    template_name = "cbv/asset/asset_list_with_count.html"
    columns = [
        (_("Serial No."), "asset_tracking_id"),
        (_("Asset Name"), "asset_name_display"),
        (_("Status"), "asset_status_col"),
        "asset_lot_number_id",
    ]
    show_filter_tags = True
    bulk_select_option = True
    quick_export = True
    action_method = "action_column"
    header_attrs = {
        "asset_tracking_id": "style='width:160px !important;'",
        "action": "style='width:130px !important;'",
    }

    row_status_indications = [
        (
            "yellow--dot",
            _("Available"),
        ),
        (
            "blue--dot",
            _("In Use"),
        ),
        (
            "gray--dot",
            _("Not Available"),
        ),
        (
            "red--dot",
            _("Expired"),
        ),
    ]
    row_status_class = "{row_status_class}"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        cat_id = kwargs.get("cat_id", "")
        self.view_id = f"assetCategoryAssetList{cat_id}"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        # Nested under asset-category accordion — keep the toolbar tight.
        context["margin_class"] = "ml-0 mr-0"
        context["asset_category_id"] = self.kwargs.get("cat_id")
        return context

    def get_queryset(self, queryset=None, filtered=False, *args, **kwargs):
        qs = (
            super()
            .get_queryset(queryset, filtered, *args, **kwargs)
            .filter(asset_category_id=self.kwargs["cat_id"])
        )

        # Fallback for a deep link into this category's asset list (see
        # asset_category_view) - only applies when the current request
        # didn't already specify its own date filter. Read (not popped)
        # since HorillaListView calls get_queryset() more than once per
        # request; asset_category_view clears it on the next plain visit
        # instead, so it doesn't linger indefinitely.
        if not self.request.GET.get(
            "asset_purchase_date_from"
        ) and not self.request.GET.get("asset_purchase_date_till"):
            deep_link = self.request.session.get("asset_purchase_date_deep_link")
            if deep_link:
                if deep_link.get("from"):
                    qs = qs.filter(asset_purchase_date__gte=deep_link["from"])
                if deep_link.get("till"):
                    qs = qs.filter(asset_purchase_date__lte=deep_link["till"])
        return qs

    row_attrs = """
        hx-get='{asset_detail}?instance_ids={ordered_ids}'
        hx-target="#genericModalBody"
        data-target="#genericModal"
        data-toggle="oh-modal-toggle"
    """


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("asset.view_asset"), name="dispatch")
class AssetInformationView(HorillaDetailedView):
    """
    Detail view of the page
    """

    model = Asset
    header = False
    action_method = "detail_view_action"
    body = [
        "asset_name_display",
        "asset_purchase_date",
        "asset_purchase_cost",
        (_("Status"), "asset_status_col"),
        "asset_lot_number_id",
        "asset_category_id",
    ]

    def get_context_data(self, **kwargs: Any):
        """
        Return context data with the title set to the asset's tracking id --
        the tracking id is the unique identifier for the physical asset;
        asset_name is often shared across many units and is shown in the
        body instead.
        """

        context = super().get_context_data(**kwargs)
        if not self.instance:
            return context
        context["title"] = context["asset"].asset_tracking_id

        body = list(self.body)
        if self.instance.asset_status == "In use":
            body.append((_("Assigned To"), "current_assignees"))
        context["body"] = body
        return context

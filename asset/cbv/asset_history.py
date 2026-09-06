"""
this page is handling the cbv methods of asset history page
"""

from typing import Any

from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _

from asset.filters import AssetHistoryFilter
from asset.forms import AssetHistoryExportForm
from asset.models import AssetAssignment
from base.methods import export_data, has_export_access
from horilla_views.cbv_methods import (
    hx_request_required,
    login_required,
    permission_required,
)
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaListView,
    HorillaNavView,
    TemplateView,
)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("asset.view_assetassignment"), name="dispatch")
class AssetHistoryView(TemplateView):
    """
    for page view
    """

    template_name = "cbv/asset_history/asset_history_home.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("asset.view_assetassignment"), name="dispatch")
class AssetHistorylistView(HorillaListView):
    """
    list view
    """

    filter_class = AssetHistoryFilter
    model = AssetAssignment
    # Actions dropdown Export covers selected/filtered export (employee list pattern).
    quick_export = False

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("asset-history-list")

    columns = [
        (_("Asset"), "asset_id__asset_name", "get_avatar"),
        (_("Asset Item"), "asset_item_id"),
        (_("Employee"), "assigned_to_employee_id"),
        (_("Assigned Date"), "assigned_date"),
        (_("Returned Date"), "return_date"),
        (_("Return Status"), "return_status"),
    ]

    sortby_mapping = [
        ("Asset", "asset_id__asset_name", "get_avatar"),
        ("Employee", "assigned_to_employee_id__get_full_name"),
        ("Assigned Date", "assigned_date"),
        ("Returned Date", "return_date"),
    ]

    row_attrs = """
        hx-get='{asset_detail_view}?instance_ids={ordered_ids}'
        hx-target="#genericModalBody"
        data-target="#genericModal"
        data-toggle="oh-modal-toggle"
    """

    # Mirrors AssetHistoryNavView.nested_group_by_fields below -- List
    # and Nav are separate classes/templates (see employee/cbv/employees.py's
    # EmployeesList/EmployeeNav for the same split).
    nested_group_by_fields = [
        ("asset_id__asset_name", _("Asset")),
        ("assigned_to_employee_id", _("Employee")),
        ("assigned_date", _("Assigned Date")),
        ("return_date", _("Returned Date")),
        ("return_status", _("Return Status")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("asset.view_assetassignment"), name="dispatch")
class AssetHistoryNavView(HorillaNavView):
    """
    navbar
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("asset-history-list")
        if has_export_access(self.request, AssetAssignment):
            self.actions = [
                {
                    "action": _("Export"),
                    "attrs": f"""
                    data-toggle="oh-modal-toggle"
                    data-target="#assetHistoryExport"
                    hx-get="{reverse('asset-history-export-form')}"
                    hx-target="#assetHistoryExportForm"
                    hx-vals='js:{{"has_selection": (JSON.parse(document.getElementById("selectedInstances")?.getAttribute("data-ids")||"[]").length>0)}}'
                    style="cursor: pointer;"
                    """,
                },
            ]

    nav_title = _("Asset History")
    filter_body_template = "cbv/asset_history/asset_history_filter.html"
    filter_form_context_name = "form"
    filter_instance = AssetHistoryFilter()
    search_swap_target = "#listContainer"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. AssetHistoryFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    group_by_fields = [
        ("asset_id__asset_name", _("Asset")),
        ("assigned_to_employee_id", _("Employee")),
        ("assigned_date", _("Assigned Date")),
        ("return_date", _("Returned Date")),
    ]

    # Mirrors AssetHistorylistView.nested_group_by_fields
    nested_group_by_fields = [
        ("asset_id__asset_name", _("Asset")),
        ("assigned_to_employee_id", _("Employee")),
        ("assigned_date", _("Assigned Date")),
        ("return_date", _("Returned Date")),
        ("return_status", _("Return Status")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(hx_request_required, name="dispatch")
@method_decorator(permission_required("asset.view_assetassignment"), name="dispatch")
class AssetHistoryExportFormView(TemplateView):
    """
    Load export column/filter form into the Actions > Export modal.
    """

    template_name = "cbv/asset_history/asset_history_export.html"

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data(**kwargs)
        context["export_form"] = AssetHistoryExportForm()
        context["export_filter"] = AssetHistoryFilter(
            queryset=AssetAssignment.objects.all()
        )
        context["hide_export_filters"] = self.request.GET.get("has_selection") == "true"
        return context


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("asset.view_assetassignment"), name="dispatch")
class AssetHistoryExportView(TemplateView):
    """
    Download Asset History Excel — selected rows when instance_ids present,
    otherwise filtered queryset (same convention as employee export).
    """

    def get(self, request, *args, **kwargs):
        return export_data(
            request=request,
            model=AssetAssignment,
            filter_class=AssetHistoryFilter,
            form_class=AssetHistoryExportForm,
            file_name="Asset_History",
            perm="asset.view_assetassignment",
        )


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required("asset.view_assetassignment"), name="dispatch")
class AssetHistoryDetailView(HorillaDetailedView):
    """
    detail view of the page
    """

    model = AssetAssignment
    title = _("Asset Details")
    header = {
        "title": "asset_id",
        "subtitle": "asset_id__asset_category_id",
        "avatar": "assigned_to_employee_id__get_avatar",
    }
    body = [
        (_("Allocated User"), "assigned_to_employee_id"),
        (_("Asset Item"), "asset_item_id"),
        (_("Returned Status"), "return_status"),
        (_("Allocated Date"), "assigned_date"),
        (_("Returned Date"), "return_date"),
        (_("Return Description"), "return_condition"),
    ]
    cols = {
        "return_condition": 12,
    }

    def get_context_data(self, **kwargs: Any) -> dict:
        context = super().get_context_data(**kwargs)
        instance = self.get_object()
        if instance.assign_images.all():
            self.body.append(
                (
                    _("Assign Condition Images"),
                    "assign_condition_img",
                    True,
                )
            )
        if instance.return_images.all():
            self.body.append(
                (
                    _("Return Condition Images"),
                    "return_condition_img",
                    True,
                )
            )
        return context

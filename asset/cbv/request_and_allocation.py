"""
Request and allocation page
"""

from datetime import timedelta
from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from django.views.generic.edit import DeleteView

from asset.filters import (
    AssetAllocationFilter,
    AssetRenewalFilter,
    AssetRequestFilter,
    CustomAssetFilter,
)
from asset.forms import AssetAllocationForm, AssetReassignForm, AssetRequestForm
from asset.models import Asset, AssetAssignment, AssetRequest, ReturnImages
from attendance.cbv.tab_shell import AttendanceTabContentShell
from base.methods import filtersubordinates
from employee.models import Employee
from horilla.horilla_middlewares import _thread_locals
from horilla.http.response import HorillaRedirect
from horilla_views.cbv_methods import (
    login_required,
    owner_can_enter,
    permission_required,
)
from horilla_views.generic.cbv.views import (
    HorillaDetailedView,
    HorillaFormView,
    HorillaListView,
    HorillaNavView,
    HorillaTabView,
    TemplateView,
)
from notifications.signals import notify


@method_decorator(login_required, name="dispatch")
class RequestAndAllocationView(TemplateView):
    """
    for request and allocation page
    """

    template_name = "cbv/request_and_allocation/request_and_allocation.html"

    def get(self, request, *args, **kwargs):
        # Deep-link support for e.g. the dashboard's "pending approvals"
        # card: ?asset_request_status=Requested. The query string can't be
        # relied on to survive down to the Asset Request tab's own list
        # fetch - this page auto-submits an unrelated (Asset Allocation)
        # filter form on load, which htmx rebuilds the request URL from,
        # dropping any param that isn't one of that form's own fields.
        # Stash it in the session instead, which AssetRequestList.get_queryset
        # picks up as a fallback, immune to that. A plain (non-deep-link)
        # visit to this page clears any stale value instead of letting it
        # linger indefinitely.
        status = request.GET.get("asset_request_status")
        if status:
            request.session["asset_request_deep_link_status"] = status
        else:
            request.session.pop("asset_request_deep_link_status", None)
        return super().get(request, *args, **kwargs)


@method_decorator(login_required, name="dispatch")
class AllocationList(HorillaListView):
    """
    For both  asset allocation and asset tab
    """

    # view_id = "view-container"

    bulk_update_fields = ["asset_id__expiry_date"]

    model = AssetAssignment
    filter_class = AssetAllocationFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-asset")

    columns = [
        (_("Asset"), "asset_id", "get_avatar"),
        (_("Category"), "asset_id__asset_category_id"),
        (_("Expiry Date"), "asset_id__expiry_date"),
    ]

    header_attrs = {
        "action": """ style = "width:140px !important" """,
        "asset_id": """ style = "width:250px !important" """,
        "asset_id__asset_category_id": """ style = "width:250px !important" """,
        "asset_id__expiry_date": """ style = "width:250px !important" """,
    }

    sortby_mapping = [
        (_("Category"), "asset_id__asset_category_id__asset_category_name"),
        (_("Expiry Date"), "asset_id__expiry_date"),
    ]

    action_method = "asset_action"

    row_attrs = """
        hx-get='{detail_view_asset}?instance_ids={ordered_ids}'
        hx-target="#genericModalBody"
        data-target="#genericModal"
        data-toggle="oh-modal-toggle"
    """

    # Mirrors AllocationList.nested_group_by_fields below -- same mixed
    # list already used by the classic group_by_fields above, which
    # tolerates a field not existing on the currently active tab's model
    # by falling back silently (see the try/except around both the
    # classic and nested grouping branches in HorillaListView).
    nested_group_by_fields = [
        ("requested_employee_id", _("Asset Request / Employee")),
        ("asset_category_id", _("Asset Request / Asset Category")),
        ("asset_request_date", _("Asset Request / Request Date")),
        ("asset_request_status", _("Asset Request / Status")),
        ("assigned_to_employee_id", _("Asset Allocation / Employee")),
        ("assigned_date", _("Asset Allocation / Assigned Date")),
        ("return_date", _("Asset Allocation / Return Date")),
    ]


@method_decorator(login_required, name="dispatch")
class AssetList(AllocationList):
    """
    Asset tab
    """

    # view_id = "assetlist"
    def get_queryset(self):
        """
        Returns a queryset of AssetRequest objects filtered by
        the current user's employee ID.
        """
        queryset = super().get_queryset()
        employee = self.request.user.employee_get
        queryset = queryset.filter(assigned_to_employee_id=employee).exclude(
            return_status__isnull=False
        )
        return queryset

    selected_instances_key_id = "assetlistInstances"


@method_decorator(login_required, name="dispatch")
class AssetAllocationList(AllocationList):
    """
    Asset allocation tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-asset-allocation")

        if any(
            self.request.user.has_perm(p)
            for p in [
                "asset.delete_assetassignment",
                "asset.change_assetassignment",
                "asset.add_assetassignment",
            ]
        ):
            self.action_method = "allocation_action"
            self.option_method = "allocation_option"

    header_attrs = {
        "option": """ style = "width:110px !important" """,
        "action": """ style = "width:140px !important" """,
    }

    columns = [
        (
            _("Allocated User"),
            "assigned_to_employee_id",
            "assigned_to_employee_id__get_avatar",
        ),
        (_("Asset"), "asset_id"),
        (_("Assigned Date"), "assigned_date"),
        (_("Return Date"), "return_status_col"),
    ]

    sortby_mapping = [
        (_("Allocated User"), "assigned_to_employee_id__get_full_name"),
        (_("Asset"), "asset_id__asset_name"),
        (_("Assigned Date"), "assigned_date"),
        (_("Return Date"), "return_status_col"),
    ]

    row_attrs = """
        hx-get='{detail_view_asset_allocation}'
        hx-target="#genericModalBody"
        data-target="#genericModal"
        data-toggle="oh-modal-toggle"
    """


@method_decorator(login_required, name="dispatch")
class AssetRequestList(HorillaListView):
    """
    Asset Request Tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.search_url = reverse("list-asset-request")
        # self.view_id = "view-container"
        self.action_method = "action_col"

    model = AssetRequest
    filter_class = AssetRequestFilter

    def get_queryset(self):
        """
        Returns a filtered queryset of AssetRequest objects
        based on user permissions and employee ID.
        """

        queryset = super().get_queryset()
        queryset = filtersubordinates(
            request=self.request,
            perm="asset.view_assetrequest",
            queryset=queryset,
            field="requested_employee_id",
        ) | queryset.filter(requested_employee_id=self.request.user.employee_get)

        # Fallback for a deep link into this tab (see
        # RequestAndAllocationView.get) - only applies when the current
        # request didn't already specify its own status filter. Checked by
        # key presence, not truthiness: clicking the "x" on the "Asset
        # request status" chip (clearFilterFromTag in clearFilter.js) sets
        # the form field to "" and resubmits, so the key IS present (just
        # empty) - `not self.request.GET.get(...)` would still be True for
        # that, silently re-applying the just-cleared filter forever. Read
        # (not popped) since HorillaListView calls get_queryset() more than
        # once per request; RequestAndAllocationView.get clears it on the
        # next plain visit instead, so it doesn't linger indefinitely -- an
        # explicit clear here also drops it immediately instead of waiting
        # for that.
        if "asset_request_status" not in self.request.GET:
            deep_link_status = self.request.session.get(
                "asset_request_deep_link_status"
            )
            if deep_link_status:
                queryset = queryset.filter(asset_request_status=deep_link_status)
                # Also reflect it in the "Filters:" chip row - otherwise the
                # list is correctly filtered but looks unfiltered, since
                # that display reads self._saved_filters, not this queryset.
                saved_filters = self._saved_filters.copy()
                saved_filters["asset_request_status"] = deep_link_status
                self._saved_filters = saved_filters
        else:
            self.request.session.pop("asset_request_deep_link_status", None)
        return queryset

    columns = [
        (
            _("Request User"),
            "requested_employee_id",
            "requested_employee_id__get_avatar",
        ),
        (_("Asset Category"), "asset_category_id"),
        (_("Requested Date"), "asset_request_date"),
        (_("Status"), "status_col"),
    ]

    header_attrs = {"action": """ style = "width:180px !important" """}

    sortby_mapping = [
        ("Request User", "requested_employee_id__get_full_name"),
        ("Asset Category", "asset_category_id__asset_category_name"),
        ("Requested Date", "asset_request_date"),
        ("Status", "status_col"),
    ]

    row_attrs = """
        hx-get='{detail_view_asset_request}?instance_ids={ordered_ids}'
        hx-target="#genericModalBody"
        data-target="#genericModal"
        data-toggle="oh-modal-toggle"
    """

    # Mirrors AllocationList.nested_group_by_fields
    nested_group_by_fields = [
        ("requested_employee_id", _("Asset Request / Employee")),
        ("asset_category_id", _("Asset Request / Asset Category")),
        ("asset_request_date", _("Asset Request / Request Date")),
        ("asset_request_status", _("Asset Request / Status")),
        ("assigned_to_employee_id", _("Asset Allocation / Employee")),
        ("assigned_date", _("Asset Allocation / Assigned Date")),
        ("return_date", _("Asset Allocation / Return Date")),
    ]


@method_decorator(login_required, name="dispatch")
@method_decorator(require_http_methods(["POST"]), name="dispatch")
@method_decorator(
    permission_required(perm="asset.delete_assetassignment"), name="dispatch"
)
class AssetAllocationDelete(DeleteView):
    """
    This the Asset Allocation Delete View
    """

    model = AssetAssignment

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        messages.success(request, _("Allocation deleted successfully"))

        return HorillaFormView.HttpResponse()


@method_decorator(login_required, name="dispatch")
@method_decorator(require_http_methods(["POST"]), name="dispatch")
@method_decorator(
    permission_required(perm="asset.delete_assetrequest"), name="dispatch"
)
class AssetRequestDelete(DeleteView):
    """
    This the Asset Request Delete View
    """

    model = AssetRequest

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        messages.success(request, _("Asset request deleted successfully"))

        return HorillaFormView.HttpResponse()


@method_decorator(login_required, name="dispatch")
class RequestAndAllocationTab(HorillaTabView):
    """
    Tab View
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.view_id = "assetReqAllocContainer"
        if not self.request or not self.request.user.is_authenticated:
            return
        employee = self.request.user.employee_get
        asset_qs = AssetAssignment.objects.filter(
            assigned_to_employee_id=employee
        ).exclude(return_status__isnull=False)
        asset_count = AssetAllocationFilter(
            self.request.GET, queryset=asset_qs
        ).qs.count()

        request_qs = (
            filtersubordinates(
                request=self.request,
                perm="asset.view_assetrequest",
                queryset=AssetRequest.objects.all(),
                field="requested_employee_id",
            )
            | AssetRequest.objects.filter(requested_employee_id=employee)
        ).distinct()
        request_count = AssetRequestFilter(
            self.request.GET, queryset=request_qs
        ).qs.count()

        allocation_count = AssetAllocationFilter(
            self.request.GET, queryset=AssetAssignment.objects.all()
        ).qs.count()

        self.tabs = [
            {
                "title": _("Asset"),
                "url": f"{reverse('req-alloc-asset-tab-shell')}",
                "badge": asset_count,
            },
            {
                "title": _("Asset Request"),
                "url": f"{reverse('req-alloc-asset-request-tab-shell')}",
                "badge": request_count,
            },
        ]
        if self.request.user.has_perm("asset.view_assetassignment"):
            self.tabs.append(
                {
                    "title": _("Asset Allocation"),
                    "url": f"{reverse('req-alloc-asset-allocation-tab-shell')}",
                    "badge": allocation_count,
                },
            )


class _RequestAndAllocationNavBase(HorillaNavView):
    """
    Shared base for each Request & Allocation tab's own, independent Nav -
    everything (nav_title/search_url/search_swap_target/filter_instance/
    filter_body_template/group_by_fields/create_attrs/actions) differs per
    tab, since each tab is backed by its own model with its own create flow.
    """


@method_decorator(login_required, name="dispatch")
class AssetNav(_RequestAndAllocationNavBase):
    """
    Independent Nav for the Asset tab. No create flow of its own (this tab
    just lists the logged-in employee's own allocations).
    """

    nav_title = _("Asset")
    filter_instance = CustomAssetFilter()
    filter_form_context_name = "form"
    filter_body_template = "cbv/request_and_allocation/asset_filter.html"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session.
    modern_filter = True

    group_by_fields = [
        ("assigned_to_employee_id", _("Employee")),
        ("assigned_date", _("Assigned Date")),
        ("return_date", _("Return Date")),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-asset")
        self.search_swap_target = "#assetListContainer"


@method_decorator(login_required, name="dispatch")
class AssetRequestNav(_RequestAndAllocationNavBase):
    """
    Independent Nav for the Asset Request tab.
    """

    nav_title = _("Asset Request")
    filter_instance = AssetRequestFilter()
    filter_form_context_name = "form"
    filter_body_template = "cbv/request_and_allocation/asset_request_filter.html"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. AssetRequestFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs. Since this tab now has its own
    # independent Nav (this class's own filter_instance IS
    # AssetRequestFilter), the generic custom_filter_fields/
    # custom_filter_rows context (HorillaNavView.get_context_data)
    # covers its "+ Add filter" builder directly -- no more manual
    # asset_request_custom_filter_fields/rows wiring needed now that
    # the combined 3-in-1 Nav is gone.
    modern_filter = True

    group_by_fields = [
        ("requested_employee_id", _("Employee")),
        ("asset_category_id", _("Asset Category")),
        ("asset_request_date", _("Request Date")),
        ("asset_request_status", _("Status")),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-asset-request")
        self.search_swap_target = "#assetRequestListContainer"
        self.create_attrs = f"""
                            data-toggle="oh-modal-toggle"
                            data-target="#genericModal"
                            hx-get="{reverse('asset-request-creation')}"
                            hx-target="#genericModalBody"
                            """


@method_decorator(login_required, name="dispatch")
class AssetAllocationNav(_RequestAndAllocationNavBase):
    """
    Independent Nav for the Asset Allocation tab.
    """

    nav_title = _("Asset Allocation")
    filter_instance = AssetAllocationFilter()
    filter_form_context_name = "form"
    filter_body_template = "cbv/request_and_allocation/asset_allocation_filter.html"
    # Modern slide-over filter panel (generic/horilla_nav.html's own
    # {% if modern_filter %} branch) -- same treatment as every other
    # panel this session. AssetAllocationFilter.ajax_fields carries the
    # AJAX-loaded comboboxes this needs.
    modern_filter = True

    group_by_fields = [
        ("assigned_to_employee_id", _("Employee")),
        ("assigned_date", _("Assigned Date")),
        ("return_date", _("Return Date")),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("list-asset-allocation")
        self.search_swap_target = "#assetAllocationListContainer"
        if self.request.user.has_perm("asset.view_assetassignment"):
            self.create_attrs = f"""
                                data-toggle="oh-modal-toggle"
                                data-target="#genericModal"
                                hx-get="{reverse('asset-allocate-creation')}"
                                hx-target="#genericModalBody"
                                """
            self.actions = [
                {
                    "action": _("Asset Renewal"),
                    "attrs": f"""
                        href="{reverse('asset-renewal')}"
                    """,
                }
            ]


class AssetTabShell(AttendanceTabContentShell):
    nav_url_name = "req-alloc-asset-nav"
    container_id = "assetListContainer"
    tabs_root_id = "assetReqAllocContainer"


class AssetRequestTabShell(AttendanceTabContentShell):
    nav_url_name = "req-alloc-asset-request-nav"
    container_id = "assetRequestListContainer"
    tabs_root_id = "assetReqAllocContainer"


class AssetAllocationTabShell(AttendanceTabContentShell):
    nav_url_name = "req-alloc-asset-allocation-nav"
    container_id = "assetAllocationListContainer"
    tabs_root_id = "assetReqAllocContainer"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    owner_can_enter(
        "asset.view_assetassignment",
        AssetAssignment,
        employee_field="assigned_to_employee_id",
    ),
    name="dispatch",
)
class AssetDetailView(HorillaDetailedView):
    """
    detail view of asset tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.body = [
            (_("Tracking Id"), "asset_id__asset_tracking_id"),
            (_("Batch No"), "asset_id__asset_lot_number_id"),
            (_("Assigned Date"), "assigned_date"),
            (_("Status"), "asset_detail_status"),
            (_("Assigned by"), "assigned_by_employee_id"),
            (_("Description"), "asset_id__asset_description"),
            # ("Category","asset_id__asset_category_id")
        ]
        self.cols = {
            "asset_id__asset_description": 12,
        }

    action_method = "asset_detail_action"

    model = AssetAssignment
    title = _("Asset Information")
    header = {
        "title": "asset_id__asset_name",
        "subtitle": "asset_id__asset_category_id",
        "avatar": "get_avatar",
    }


@method_decorator(login_required, name="dispatch")
@method_decorator(
    owner_can_enter(
        "asset.view_assetrequest", AssetRequest, employee_field="requested_employee_id"
    ),
    name="dispatch",
)
class AssetRequestDetailView(HorillaDetailedView):
    """
    detail view of asset request tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.body = [
            (_("Asset Category"), "asset_category_id"),
            (_("Requested Date"), "asset_request_date"),
            (_("Status"), "status_col"),
            (_("Request Description"), "description"),
        ]

        self.cols = {
            "description": 12,
        }

    model = AssetRequest
    title = _("Details")
    header = {
        "title": "requested_employee_id",
        "subtitle": "asset_request_detail_subtitle",
        "avatar": "requested_employee_id__get_avatar",
    }
    action_method = "detail_action_col"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    owner_can_enter(
        "asset.view_assetassignment",
        AssetAssignment,
        employee_field="assigned_to_employee_id",
    ),
    name="dispatch",
)
class AssetAllocationDetailView(HorillaDetailedView):
    """
    detail view of asset allocation tab
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.body = [
            (_("Returned Status"), "return_status"),
            (_("Allocated User"), "assigned_by_employee_id"),
            (_("Allocated Date"), "assigned_date"),
            (_("Return Date"), "return_date"),
            (_("Asset"), "asset_id"),
            (_("Status"), "detail_status"),
            (_("Return Description"), "return_condition"),
        ]

        self.cols = {
            "return_condition": 12,
        }

    model = AssetAssignment
    title = _("Details")
    header = {
        "title": "assigned_to_employee_id",
        "subtitle": "asset_allocation_detail_subtitle",
        "avatar": "assigned_to_employee_id__get_avatar",
    }
    action_method = "asset_allocation_detail_action"


@method_decorator(login_required, name="dispatch")
class AssetRequestCreateForm(HorillaFormView):
    """
    Create Asset request
    """

    model = AssetRequest
    form_class = AssetRequestForm
    template_name = "cbv/request_and_allocation/forms/req_form.html"
    new_display_title = _("Asset Request")

    def dispatch(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        if pk:
            asset_request = AssetRequest.objects.filter(id=pk).first()
            if asset_request:
                employee = asset_request.requested_employee_id
                is_owner = request.user.employee_get == employee
                has_perm = request.user.has_perm("asset.change_assetrequest")
                if not (is_owner or has_perm):
                    messages.error(request, _("You don't have permission."))
                    return HorillaRedirect(request)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.GET.get("pk"):
            pk = self.request.GET.get("pk")
            self.form.fields["requested_employee_id"].queryset = (
                Employee.objects.filter(id=pk)
            )
            self.form.fields["requested_employee_id"].initial = pk

        if self.form.instance.pk:
            self.form_class.verbose_name = _("Asset Request")
        return context

    def form_valid(self, form: AssetRequestForm) -> HttpResponse:
        """
        Handles validation and saving of an AssetRequestForm.
        """
        if form.is_valid():
            message = _("Asset Request Created Successfully")
            form.save()
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(permission_required(perm="asset.add_asset"), name="dispatch")
class AssetAllocationFormView(HorillaFormView):
    """
    Create Asset Allocation
    """

    model = AssetAssignment
    form_class = AssetAllocationForm
    template_name = "cbv/request_and_allocation/forms/allo_form.html"
    new_display_title = _("Asset Allocation")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.form.instance.pk:
            self.form_class.verbose_name = _("Asset Allocation")
        return context

    def form_valid(self, form: AssetAllocationForm) -> HttpResponse:
        """
        form valid function
        """
        if form.is_valid():
            message = _("Asset allocated Successfully")
            instance = form.save()
            asset = instance.asset_id
            if instance.asset_item_id_id:
                asset_item = instance.asset_item_id
                asset_item.status = "In use"
                asset_item.save()
            active_count = AssetAssignment.objects.filter(
                asset_id=asset, return_date__isnull=True
            ).count()
            if active_count >= asset.quantity:
                asset.asset_status = "In use"
                asset.save()
            request = getattr(_thread_locals, "request", None)
            files = request.FILES.getlist("assign_images")
            attachments = []
            if request.FILES:
                for file in files:
                    attachment = ReturnImages()
                    attachment.image = file
                    attachment.save()
                    attachments.append(attachment)
                form.instance.assign_images.add(*attachments)
            messages.success(self.request, message)
            return self.HttpResponse()
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="asset.add_assetassignment"), name="dispatch"
)
class AssetApproveFormView(HorillaFormView):
    """
    Create Asset Allocation
    """

    model = AssetAssignment
    form_class = AssetAllocationForm
    template_name = "cbv/request_and_allocation/forms/asset_approve_form.html"
    new_display_title = _("Asset Allocation")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        req_id = self.kwargs.get("req_id")
        asset_request = AssetRequest.objects.filter(id=req_id).first()
        if not asset_request:
            messages.error(self.request, _("Asset request not found."))
            return context
        asset_category = asset_request.asset_category_id
        assets = Asset.available_assets().filter(asset_category_id=asset_category)
        self.form.fields["asset_id"].queryset = assets
        self.form.fields["assigned_to_employee_id"].initial = (
            asset_request.requested_employee_id
        )
        self.form.fields["assigned_by_employee_id"].initial = (
            self.request.user.employee_get
        )
        return context

    def form_invalid(self, form: Any) -> HttpResponse:
        if not form.is_valid():
            errors = form.errors.as_data()
            return render(
                self.request, self.template_name, {"form": form, "errors": errors}
            )
        return super().form_invalid(form)

    def form_valid(self, form: AssetAllocationForm) -> HttpResponse:
        """
        form valid function
        """
        req_id = self.kwargs.get("req_id")
        asset_request = AssetRequest.objects.filter(id=req_id).first()
        if not asset_request:
            messages.error(self.request, _("Asset request not found."))
            return self.HttpResponse()
        if form.is_valid():
            instance = form.save()
            asset = instance.asset_id
            if instance.asset_item_id_id:
                asset_item = instance.asset_item_id
                asset_item.status = "In use"
                asset_item.save()
            active_count = AssetAssignment.objects.filter(
                asset_id=asset, return_date__isnull=True
            ).count()
            if active_count >= asset.quantity:
                asset.asset_status = "In use"
                asset.save()
            asset_request.asset_request_status = "Approved"
            asset_request.save()
            request = getattr(_thread_locals, "request", None)
            files = request.FILES.getlist("assign_images")
            attachments = []
            if request.FILES:
                for file in files:
                    attachment = ReturnImages()
                    attachment.image = file
                    attachment.save()
                    attachments.append(attachment)
                form.instance.assign_images.add(*attachments)
            messages.success(self.request, _("Asset request approved successfully!."))
            notify.send(
                self.request.user.employee_get,
                recipient=asset_request.requested_employee_id.employee_user_id,
                verb="Your asset request approved!.",
                verb_ar="تم الموافقة على طلب الأصول الخاص بك!",
                verb_de="Ihr Antragsantrag wurde genehmigt!",
                verb_es="¡Su solicitud de activo ha sido aprobada!",
                verb_fr="Votre demande d'actif a été approuvée !",
                redirect=reverse("asset-request-allocation-view")
                + f"?asset_request_date={asset_request.asset_request_date}\
                &asset_request_status={asset_request.asset_request_status}",
                icon="bag-check",
            )
            return self.HttpResponse(targets_to_reload=["#applyFilter"])
        return super().form_valid(form)


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="asset.change_assetassignment"), name="dispatch"
)
class AssetRenewalView(TemplateView):
    """
    Page wrapper for the asset renewal / expiring assignments view.
    """

    template_name = "cbv/request_and_allocation/asset_renewal.html"


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="asset.change_assetassignment"), name="dispatch"
)
class AssetRenewalNav(HorillaNavView):
    """
    Nav bar for the asset renewal page.
    """

    nav_title = _("Asset Renewal")
    search_swap_target = "#listContainer"
    filter_body_template = "cbv/request_and_allocation/asset_renewal_filter.html"
    filter_form_context_name = "form"
    filter_instance = AssetRenewalFilter()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("asset-renewal-list")


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="asset.change_assetassignment"), name="dispatch"
)
class ExpiringAssignmentList(HorillaListView):
    """
    Lists active assignments whose asset expires within 30 days (or is already expired).
    """

    model = AssetAssignment
    filter_class = AssetRenewalFilter
    action_method = "reassign_action"
    row_attrs = ""

    columns = [
        (
            _("Employee"),
            "assigned_to_employee_id",
            "assigned_to_employee_id__get_avatar",
        ),
        (_("Asset"), "asset_id__asset_name_display"),
        (_("Category"), "asset_id__asset_category_id"),
        (_("Expiry Date"), "asset_id__expiry_date"),
        (_("Days Left"), "days_left_display"),
    ]

    bulk_update_fields = ["asset_id"]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.search_url = reverse("asset-renewal-list")

    def get_queryset(self):
        queryset = super().get_queryset()
        today = timezone.now().date()
        threshold = today + timedelta(days=30)
        queryset = queryset.filter(
            return_date__isnull=True,
            asset_id__expiry_date__isnull=False,
            asset_id__expiry_date__lte=threshold,
        ).order_by("asset_id__expiry_date")
        return queryset


@method_decorator(login_required, name="dispatch")
@method_decorator(
    permission_required(perm="asset.change_assetassignment"), name="dispatch"
)
class AssetReassignFormView(HorillaFormView):
    """
    Modal form to swap the asset on an existing assignment to a replacement.
    """

    model = AssetAssignment
    form_class = AssetReassignForm
    template_name = "cbv/request_and_allocation/forms/reassign_form.html"
    new_display_title = _("Reassign Asset")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["assignment"] = AssetAssignment.objects.get(pk=self.kwargs["pk"])
        return context

    def form_valid(self, form):
        old_asset = AssetAssignment.objects.get(pk=self.kwargs["pk"]).asset_id
        instance = form.save()
        new_asset = instance.asset_id

        old_active = AssetAssignment.objects.filter(
            asset_id=old_asset, return_date__isnull=True
        ).count()
        if old_active < old_asset.quantity and not old_asset.is_expired:
            old_asset.asset_status = "Available"
            old_asset.save()

        new_active = AssetAssignment.objects.filter(
            asset_id=new_asset, return_date__isnull=True
        ).count()
        if new_active >= new_asset.quantity:
            new_asset.asset_status = "In use"
            new_asset.save()

        messages.success(self.request, _("Asset reassigned successfully."))
        return self.HttpResponse(targets_to_reload=["#listContainer"])

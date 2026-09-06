"""
Module containing custom filter classes for various models.
"""

import uuid

import django_filters
from django import forms
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_filters import FilterSet

from base.methods import reload_queryset
from employee.models import Employee
from horilla.filters import HorillaFilterSet, filter_name_or_badge_terms

from .models import Asset, AssetAssignment, AssetCategory, AssetLot, AssetRequest


class CustomFilterSet(HorillaFilterSet):
    """
    Custom FilterSet class that applies specific CSS classes to filter
    widgets.

    The class applies CSS classes to different types of filter widgets,
    such as NumberInput, EmailInput, TextInput, Select, Textarea,
    CheckboxInput, CheckboxSelectMultiple, and ModelChoiceField. The
    CSS classes are applied to enhance the styling and behavior of the
    filter widgets.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Exclude ajax_fields: reload_queryset's fallback branch resets
        # any ModelChoiceField's queryset to model.objects.all(), which
        # would undo _apply_ajax_fields' trim to just the selected
        # value(s) (or none) -- re-inflating the very "don't pre-render
        # the whole queryset as <option> tags" cost ajax_fields exists
        # to avoid.
        reload_queryset(
            {
                name: field
                for name, field in self.form.fields.items()
                if name not in self.ajax_fields
            }
        )
        for field_name, field in self.form.fields.items():
            # Skip fields already handed a HorillaAjaxSelectWidget by
            # HorillaFilterSet._apply_ajax_fields (called from
            # super().__init__() above) -- it's a forms.SelectMultiple
            # subclass, so it would otherwise match the plain "Select"
            # branch below and pick up a bare "oh-select" class
            # alongside its own "oh-select-ajax" one. htmxSelect2.js
            # treats those as two different widgets and initializes
            # whichever classic-vs-ajax handler runs first; if the
            # classic one wins, the field ends up marked
            # "select2-hidden-accessible" with no ajax config, and the
            # ajax initializer then skips it as already-initialized --
            # silently breaking the AJAX search for that field.
            if field_name in self.ajax_fields:
                continue
            filter_widget = self.filters[field_name]
            widget = filter_widget.field.widget
            if isinstance(
                widget, (forms.NumberInput, forms.EmailInput, forms.TextInput)
            ):
                field.widget.attrs.update({"class": "oh-input w-100"})
            elif isinstance(widget, (forms.Select,)):
                field.widget.attrs.update(
                    {
                        "class": "oh-select oh-select-2",
                    }
                )
            elif isinstance(widget, (forms.Textarea)):
                field.widget.attrs.update({"class": "oh-input w-100"})
            elif isinstance(
                widget,
                (
                    forms.CheckboxInput,
                    forms.CheckboxSelectMultiple,
                ),
            ):
                filter_widget.field.widget.attrs.update(
                    {"class": "oh-switch__checkbox"}
                )
            elif isinstance(widget, (forms.ModelChoiceField)):
                field.widget.attrs.update(
                    {
                        "class": "oh-select oh-select-2 ",
                    }
                )
            elif isinstance(widget, (forms.DateField)):
                field.widget.attrs.update({"type": "date", "class": "oh-input  w-100"})
            if isinstance(field, django_filters.CharFilter):
                field.lookup_expr = "icontains"


class AssetExportFilter(CustomFilterSet):
    """
    Custom filter class for exporting filtered Asset data.
    """

    class Meta:
        """
        A nested class that specifies the configuration for the filter.
            model(class): The Asset model is used to filter.
            fields (str): A special value "__all__" to include all fields
                          of the model in the filter.
        """

        model = Asset
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form.fields["asset_purchase_date"].widget.attrs.update({"type": "date"})


class AssetFilter(CustomFilterSet):
    """
    Custom filter set for Asset instances.
    """

    search = django_filters.CharFilter(method="search_method")
    category = django_filters.CharFilter(field_name="asset_category_id")
    expired = django_filters.BooleanFilter(method="filter_expired")

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Asset Batch Number and Category opt into AJAX-searched comboboxes
    # instead of pre-rendering their whole queryset as <option> tags.
    ajax_fields = {
        "asset_lot_number_id": {
            "key": "asset-batch-number",
            "queryset_fn": lambda request: AssetLot.objects.all(),
            "display_fn": lambda obj: obj.lot_number,
            "search_fields": ["lot_number"],
            "placeholder": _("Select batch number..."),
        },
        "asset_category_id": {
            "key": "asset-category",
            "queryset_fn": lambda request: AssetCategory.objects.all(),
            "display_fn": lambda obj: obj.asset_category_name,
            "search_fields": ["asset_category_name"],
            "placeholder": _("Select category..."),
        },
    }

    class Meta:
        """
        A nested class that specifies the configuration for the filter.
            model(class): The Asset model is used to filter.
            fields (str): A special value "__all__" to include all fields
                          of the model in the filter.
        """

        model = Asset
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.form.visible_fields():
            visible.field.widget.attrs["id"] = str(uuid.uuid4())

    def search_method(self, queryset, _, value):
        """
        Search method
        """
        return (
            queryset.filter(asset_tracking_id__icontains=value)
            | queryset.filter(asset_name__icontains=value)
            | queryset.filter(asset_category_id__asset_category_name__icontains=value)
        ).distinct()

    def filter_expired(self, queryset, _, value):
        """
        Filters by Asset.is_expired, which is a derived property (an expiry
        date in the past) rather than a stored field the ORM can filter on.
        """
        today = timezone.now().date()
        if value:
            return queryset.filter(expiry_date__lt=today)
        return queryset.filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=today))

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/PMS FeedbackFilter. Purchase Date is a plain
        DateField column, so the plain field+lookup shape applies
        directly (a raw queryset.filter(**{field__lookup: value}) call),
        offering the full gte/lte/gt/lt/exact set instead of the fixed
        gte/lte pair asset_purchase_date_from/asset_purchase_date_till
        were limited to. Created At is included too, same as every
        other modernized panel's builder this session.
        """
        fields = [
            {
                "key": "asset_purchase_date",
                "field": "asset_purchase_date",
                "label": str(_("Purchase Date")),
                "type": "date_range",
            },
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(_("Created At")),
                "type": "date_range",
            },
        ]
        for entry in fields:
            entry["lookups"] = [
                [lk, str(label)]
                for lk, label in self.CUSTOM_FILTER_LOOKUPS[entry["type"]]
            ]
        return fields

    def filter_queryset(self, queryset):
        """
        HorillaFilterSet._apply_custom_filters isn't wired into the base
        filter_queryset automatically -- this is the minimal "call it at
        the end" hookup, same as AttendanceFilters/FeedbackFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)


class CustomAssetFilter(CustomFilterSet):
    """
    Custom filter set for asset assigned to employees instances.
    """

    asset_id__asset_name = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        """
        Specifies the model and fields to be used for filtering AssetAssignment instances.

        Attributes:
        model (class): The model class AssetAssignment to be filtered.
        fields (list): The fields to include in the filter, referring to
                       related AssetAssignment fields.
        """

        model = AssetAssignment
        fields = [
            "asset_id__asset_name",
            "asset_id__asset_status",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.form.visible_fields():
            visible.field.widget.attrs["id"] = str(uuid.uuid4())

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter/AssetAllocationFilter (which shares
        this same AssetAssignment model, on the Asset Allocation tab).
        Asset Expiry Date traverses to the related Asset row.
        """
        fields = [
            {
                "key": "assigned_date",
                "field": "assigned_date",
                "label": str(_("Assigned Date")),
                "type": "date_range",
            },
            {
                "key": "return_date",
                "field": "return_date",
                "label": str(_("Return Date")),
                "type": "date_range",
            },
            {
                "key": "asset_expiry_date",
                "field": "asset_id__expiry_date",
                "label": str(_("Asset Expiry Date")),
                "type": "date_range",
            },
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(_("Created At")),
                "type": "date_range",
            },
        ]
        for entry in fields:
            entry["lookups"] = [
                [lk, str(label)]
                for lk, label in self.CUSTOM_FILTER_LOOKUPS[entry["type"]]
            ]
        return fields

    def filter_queryset(self, queryset):
        """
        HorillaFilterSet._apply_custom_filters isn't wired into the base
        filter_queryset automatically -- this is the minimal "call it at
        the end" hookup, same as AttendanceFilters/FeedbackFilter/
        AssetFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)


class AssetRequestFilter(CustomFilterSet):
    """
    Custom filter set for AssetRequest instances.
    """

    search = django_filters.CharFilter(method="search_method")
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX requested_employee_id picker below rather than instead of it --
    # same field/behavior as every other modernized panel this session;
    # see horilla.filters.filter_name_or_badge_terms for the shared
    # matching logic. requested_employee_id is the only employee-role
    # field on this filter, so it has a clear single owner to search
    # against.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Requesting User and Asset Category opt into AJAX-searched
    # comboboxes instead of pre-rendering their whole queryset as
    # <option> tags.
    ajax_fields = {
        "requested_employee_id": {
            "key": "asset-request-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "asset_category_id": {
            "key": "asset-request-category",
            "queryset_fn": lambda request: AssetCategory.objects.all(),
            "display_fn": lambda obj: obj.asset_category_name,
            "search_fields": ["asset_category_name"],
            "placeholder": _("Select category..."),
        },
    }

    def search_method(self, queryset, _, value: str):
        """
        This method is used to search employees
        """
        values = value.split(" ")
        empty = queryset.model.objects.none()
        for split in values:
            empty = empty | (
                queryset.filter(
                    requested_employee_id__employee_first_name__icontains=split
                )
                | queryset.filter(
                    requested_employee_id__employee_last_name__icontains=split
                )
            )
        return empty.distinct()

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic.
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "requested_employee_id__employee_first_name",
            "requested_employee_id__employee_last_name",
            "requested_employee_id__badge_id",
        )

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/PMS FeedbackFilter/AssetFilter. Asset Request
        Date and Created At are plain DateField/DateTimeField columns,
        so the plain field+lookup shape applies directly (a raw
        queryset.filter(**{field__lookup: value}) call), offering the
        full gte/lte/gt/lt/exact set instead of the fixed exact-only
        match the old permanent asset_request_date input was limited
        to.
        """
        fields = [
            {
                "key": "asset_request_date",
                "field": "asset_request_date",
                "label": str(_("Asset Request Date")),
                "type": "date_range",
            },
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(_("Created At")),
                "type": "date_range",
            },
        ]
        for entry in fields:
            entry["lookups"] = [
                [lk, str(label)]
                for lk, label in self.CUSTOM_FILTER_LOOKUPS[entry["type"]]
            ]
        return fields

    def filter_queryset(self, queryset):
        """
        HorillaFilterSet._apply_custom_filters isn't wired into the base
        filter_queryset automatically -- this is the minimal "call it at
        the end" hookup, same as AttendanceFilters/FeedbackFilter/
        AssetFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)

    class Meta:
        """
        Specifies the model and fields to be used for filtering AssetRequest instances.

        Attributes:
        model (class): The model class AssetRequest to be filtered.
        fields (str): A special value "__all__" to include all fields of the model in the filter.
        """

        model = AssetRequest
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.form.visible_fields():
            visible.field.widget.attrs["id"] = str(uuid.uuid4())
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )


class AssetAllocationFilter(CustomFilterSet):
    """
    Custom filter set for AssetAllocation instances.
    """

    search = django_filters.CharFilter(method="search_method")

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Allocated User, Asset, and Allocated By opt into AJAX-searched
    # comboboxes instead of pre-rendering their whole queryset as
    # <option> tags. No dedicated "Name or Badge ID" field is added:
    # assigned_to_employee_id and assigned_by_employee_id are two
    # separate employee-role fields with no single clear owner, same
    # reasoning as the Recruitment Pipeline panel.
    ajax_fields = {
        "assigned_to_employee_id": {
            "key": "asset-allocation-assigned-to",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "asset_id": {
            "key": "asset-allocation-asset",
            "queryset_fn": lambda request: Asset.objects.all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["asset_name", "asset_tracking_id"],
            "placeholder": _("Search asset..."),
        },
        "assigned_by_employee_id": {
            "key": "asset-allocation-assigned-by",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    def search_method(self, queryset, _, value: str):
        """
        This method is used to search employees and assets
        """
        values = value.split(" ")
        empty = queryset.model.objects.none()
        for split in values:
            empty = empty | (
                queryset.filter(
                    assigned_to_employee_id__employee_first_name__icontains=split
                )
                | queryset.filter(
                    assigned_to_employee_id__employee_last_name__icontains=split
                )
                | queryset.filter(asset_id__asset_name__icontains=split)
                | queryset.filter(
                    asset_id__asset_category_id__asset_category_name__icontains=split
                )
            )
        return empty.distinct()

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/PMS FeedbackFilter/AssetFilter. Assigned Date,
        Return Date, and Created At are plain DateField/DateTimeField
        columns, so the plain field+lookup shape applies directly (a
        raw queryset.filter(**{field__lookup: value}) call), offering
        the full gte/lte/gt/lt/exact set instead of the fixed exact-only
        match the old permanent assigned_date/return_date inputs were
        limited to.
        """
        fields = [
            {
                "key": "assigned_date",
                "field": "assigned_date",
                "label": str(_("Asset Allocated Date")),
                "type": "date_range",
            },
            {
                "key": "return_date",
                "field": "return_date",
                "label": str(_("Return Date")),
                "type": "date_range",
            },
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(_("Created At")),
                "type": "date_range",
            },
        ]
        for entry in fields:
            entry["lookups"] = [
                [lk, str(label)]
                for lk, label in self.CUSTOM_FILTER_LOOKUPS[entry["type"]]
            ]
        return fields

    def filter_queryset(self, queryset):
        """
        HorillaFilterSet._apply_custom_filters isn't wired into the base
        filter_queryset automatically -- this is the minimal "call it at
        the end" hookup, same as AttendanceFilters/FeedbackFilter/
        AssetFilter/AssetRequestFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)

    class Meta:
        """
        Specifies the model and fields to be used for filtering AssetAllocation instances.

        Attributes:
            model (class): The model class AssetAssignment to be filtered.
            fields (str): A special value "__all__" to include all fields
                          of the model in the filter.
        """

        model = AssetAssignment
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.form.visible_fields():
            visible.field.widget.attrs["id"] = str(uuid.uuid4())


class AssetCategoryFilter(CustomFilterSet):
    """
    Custom filter set for AssetCategory instances.
    """

    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = AssetCategory
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for visible in self.form.visible_fields():
            visible.field.widget.attrs["id"] = str(uuid.uuid4())

    def search_method(self, queryset, name, value):
        """
        Search method to filter by asset category name or related asset name.
        """
        if not value:
            return queryset  # Return unfiltered queryset if no search term is provided

        return queryset.filter(
            Q(asset_category_name__icontains=value)
            | Q(asset__asset_name__icontains=value)
        ).distinct()

    def filter_queryset(self, queryset):
        """
        Filters queryset and applies AssetFilter if necessary.
        """
        # Get the base filtered queryset
        queryset = super().filter_queryset(queryset)

        # Filter by assets if asset data is present in the GET request
        if self.data and "asset__pk" in self.data:
            assets = AssetFilter(data=self.data).qs
            queryset = queryset.filter(
                asset__pk__in=assets.values_list("pk", flat=True)
            )

        return queryset.distinct()


class AssetRequestReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("requested_employee_id", "Employee"),
        ("asset_category_id", "Asset Category"),
        ("asset_request_date", "Request Date"),
        ("asset_request_status", "Status"),
    ]


class AssetAllocationReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("assigned_to_employee_id", "Employee"),
        ("assigned_date", "Assigned Date"),
        ("return_date", "Return Date"),
    ]


class AssetHistoryFilter(CustomFilterSet):
    """
    Custom filter set for AssetAssignment instances for filtering in asset history view.
    """

    search = django_filters.CharFilter(
        field_name="asset_id__asset_name", lookup_expr="icontains"
    )
    returned_assets = django_filters.CharFilter(
        field_name="return_status", method="exclude_none"
    )
    return_date_gte = django_filters.DateFilter(
        field_name="return_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    return_date_lte = django_filters.DateFilter(
        field_name="return_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    assigned_date_gte = django_filters.DateFilter(
        field_name="assigned_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    assigned_date_lte = django_filters.DateFilter(
        field_name="assigned_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Allocated User, Asset, and Allocated By opt into AJAX-searched
    # comboboxes instead of pre-rendering their whole queryset as
    # <option> tags. No dedicated "Name or Badge ID" field is added:
    # assigned_to_employee_id and assigned_by_employee_id are two
    # separate employee-role fields with no single clear owner, same
    # reasoning as AssetAllocationFilter/the Recruitment Pipeline panel.
    ajax_fields = {
        "assigned_to_employee_id": {
            "key": "asset-history-assigned-to",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "asset_id": {
            "key": "asset-history-asset",
            "queryset_fn": lambda request: Asset.objects.all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["asset_name", "asset_tracking_id"],
            "placeholder": _("Search asset..."),
        },
        "assigned_by_employee_id": {
            "key": "asset-history-assigned-by",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    def exclude_none(self, queryset, name, value):
        """
        Exclude objects with a null return_status from the queryset if value is "True"
        """
        if value == "True":
            queryset = queryset.filter(return_status__isnull=False)
        return queryset

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/PMS FeedbackFilter/AssetFilter/
        AssetAllocationFilter. Assigned Date, Return Date, and Created
        At are plain DateField/DateTimeField columns, so the plain
        field+lookup shape applies directly (a raw queryset.filter(**
        {field__lookup: value}) call), offering the full gte/lte/gt/
        lt/exact set instead of the fixed gte/lte pair the old
        permanent assigned_date_gte/lte and return_date_gte/lte inputs
        were limited to.
        """
        fields = [
            {
                "key": "assigned_date",
                "field": "assigned_date",
                "label": str(_("Asset Allocated Date")),
                "type": "date_range",
            },
            {
                "key": "return_date",
                "field": "return_date",
                "label": str(_("Return Date")),
                "type": "date_range",
            },
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(_("Created At")),
                "type": "date_range",
            },
        ]
        for entry in fields:
            entry["lookups"] = [
                [lk, str(label)]
                for lk, label in self.CUSTOM_FILTER_LOOKUPS[entry["type"]]
            ]
        return fields

    def filter_queryset(self, queryset):
        """
        HorillaFilterSet._apply_custom_filters isn't wired into the base
        filter_queryset automatically -- this is the minimal "call it at
        the end" hookup, same as AttendanceFilters/FeedbackFilter/
        AssetFilter/AssetRequestFilter/AssetAllocationFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)

    class Meta:
        """
        Specifies the model and fields to be used for filtering AssetAllocation instances.

        Attributes:
            model (class): The model class AssetAssignment to be filtered.
            fields (str): A special value "__all__" to include all fields
                          of the model in the filter.
        """

        model = AssetAssignment
        fields = "__all__"


class AssetHistoryReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("asset_id", "Asset"),
        ("assigned_to_employee_id", "Employee"),
        ("assigned_date", "Assigned Date"),
        ("return_date", "Return Date"),
    ]


class AssetRenewalFilter(HorillaFilterSet):
    """
    Filter set for the Asset Renewal page — expiring/expired active assignments.
    Filters operate on AssetAssignment with traversal into the related Asset.
    """

    search = django_filters.CharFilter(
        field_name="asset_id__asset_name",
        lookup_expr="icontains",
        label=_("Asset Name"),
    )
    asset_category_id = django_filters.ModelChoiceFilter(
        field_name="asset_id__asset_category_id",
        queryset=AssetCategory.objects.all(),
        label=_("Category"),
    )
    expiry_date_gte = django_filters.DateFilter(
        field_name="asset_id__expiry_date",
        lookup_expr="gte",
        label=_("Expiry Date From"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    expiry_date_lte = django_filters.DateFilter(
        field_name="asset_id__expiry_date",
        lookup_expr="lte",
        label=_("Expiry Date To"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    assigned_date_gte = django_filters.DateFilter(
        field_name="assigned_date",
        lookup_expr="gte",
        label=_("Assigned Date From"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    assigned_date_lte = django_filters.DateFilter(
        field_name="assigned_date",
        lookup_expr="lte",
        label=_("Assigned Date To"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    asset_status = django_filters.ChoiceFilter(
        field_name="asset_id__asset_status",
        choices=[
            ("Available", "Available"),
            ("In use", "In use"),
            ("Not-Available", "Not-Available"),
        ],
        label=_("Asset Status"),
        empty_label=_("All"),
    )

    class Meta:
        model = AssetAssignment
        fields = "__all__"


class AssetBatchNoFilter(FilterSet):

    search = django_filters.CharFilter(field_name="lot_number", lookup_expr="icontains")

    class Meta:
        model = AssetLot
        fields = [
            "lot_number",
        ]

# pylint: disable=too-few-public-methods
"""
Module for defining filters related to biometric devices.

This module contains the definition of the BiometricDeviceFilter class,
which is used to filter instances of BiometricDevices
"""

import django_filters
from django.utils.translation import gettext_lazy as _

from base.filters import FilterSet
from biometric.models import BiometricDevices
from horilla.filters import HorillaFilterSet


class BiometricDeviceFilter(HorillaFilterSet):
    """
    Filter class for querying biometric devices.

    This class defines filters for querying instances of BiometricDevices
    based on various criteria such as name, machine type, and activity status.
    """

    search = django_filters.CharFilter(field_name="name", lookup_expr="icontains")

    class Meta:
        """
        Meta class to add additional options
        """

        model = BiometricDevices
        fields = [
            "name",
            "machine_type",
            "is_active",
            "is_scheduler",
            "is_live",
        ]

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields), same pattern
        as HolidayFilter/AssetFilter.
        """
        fields = [
            {"key": "name", "field": "name", "label": str(_("Name")), "type": "text"},
            {
                "key": "machine_ip",
                "field": "machine_ip",
                "label": str(_("Machine IP")),
                "type": "text",
            },
            {
                "key": "port",
                "field": "port",
                "label": str(_("Port No")),
                "type": "number",
            },
            {
                "key": "last_fetch_date",
                "field": "last_fetch_date",
                "label": str(_("Last Fetch Date")),
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
        Apply the "+ Add filter" rows after the declared filters.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)

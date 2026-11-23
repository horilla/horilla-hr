import django_filters

from additional_info.models import AdditionalInfoField


class AdditionalInfoFieldFilter(django_filters.FilterSet):
    """Search the field list by label."""

    search = django_filters.CharFilter(field_name="label", lookup_expr="icontains")

    class Meta:
        model = AdditionalInfoField
        fields = ["label"]

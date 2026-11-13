import django_filters
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from horilla.filters import FilterSet
from report.models import ReportRunLog, ReportSubscription


class ReportSubscriptionFilter(FilterSet):
    search = django_filters.CharFilter(method="filter_search")
    status = django_filters.ChoiceFilter(
        method="filter_status",
        label=_("Status"),
        choices=[("active", _("Active")), ("paused", _("Paused"))],
    )

    class Meta:
        model = ReportSubscription
        fields = []

    def filter_search(self, queryset, name, value):
        """
        Match a subscription by its name, report name or slug, or a recipient's name.

        Parameters:
            queryset: ReportSubscription queryset to narrow.
            name: Filter field name (unused).
            value: Search text.

        Returns:
            The queryset limited to subscriptions matching the text.
        """
        from report.registry import list_reports

        value = value.strip()
        if not value:
            return queryset
        needle = value.lower()
        report_slugs = [
            definition.slug
            for definition in list_reports()
            if needle in str(definition.name).lower()
        ]
        recipient_links = (
            ReportSubscription.recipients_employees.through.objects.filter(
                Q(employee__employee_first_name__icontains=value)
                | Q(employee__employee_last_name__icontains=value)
            ).values("reportsubscription_id")
        )
        return queryset.filter(
            Q(name__icontains=value)
            | Q(report_slug__icontains=value)
            | Q(report_slug__in=report_slugs)
            | Q(pk__in=recipient_links)
        )

    def filter_status(self, queryset, name, value):
        """
        Limit subscriptions to the active or paused ones.

        Parameters:
            queryset: ReportSubscription queryset to narrow.
            name: Filter field name (unused).
            value: "active" or "paused".

        Returns:
            The queryset limited to the chosen status.
        """
        if value == "active":
            return queryset.filter(is_active=True)
        if value == "paused":
            return queryset.filter(is_active=False)
        return queryset


class ReportAuditFilter(FilterSet):
    report_slug = django_filters.CharFilter(
        field_name="report_slug", lookup_expr="icontains", label=_("Report slug")
    )
    q = django_filters.CharFilter(method="filter_by_user", label=_("Username or email"))
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = ReportRunLog
        fields = ["action", "report_slug", "q"]

    def filter_search(self, queryset, name, value):
        """
        Match an audit entry by report, user or action.

        Parameters:
            queryset: ReportRunLog queryset to narrow.
            name: Filter field name (unused).
            value: Search text.

        Returns:
            The queryset limited to entries matching the text.
        """
        from report.registry import list_reports

        value = value.strip()
        if not value:
            return queryset
        needle = value.lower()
        report_slugs = [
            definition.slug
            for definition in list_reports()
            if needle in str(definition.name).lower()
        ]
        actions = [
            key
            for key, label in ReportRunLog.ACTION_CHOICES
            if needle in str(label).lower()
        ]
        return queryset.filter(
            Q(report_slug__icontains=value)
            | Q(report_slug__in=report_slugs)
            | Q(action__in=actions)
            | Q(user__username__icontains=value)
            | Q(user__email__icontains=value)
            | Q(user__employee_get__employee_first_name__icontains=value)
            | Q(user__employee_get__employee_last_name__icontains=value)
        )

    def filter_by_user(self, queryset, name, value):
        from django.db.models import Q

        return queryset.filter(
            Q(user__username__icontains=value) | Q(user__email__icontains=value)
        )

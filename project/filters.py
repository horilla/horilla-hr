from datetime import date as _date

import django_filters
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from horilla.filters import (
    FilterSet,
    HorillaFilterSet,
    filter_by_name,
    filter_name_or_badge_terms,
)

from .models import Employee, Project, ProjectStage, Task, TimeSheet


class ProjectFilter(HorillaFilterSet):
    search = django_filters.CharFilter(method="filter_by_project")
    search_field = django_filters.CharFilter(method="search_in")
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX managers picker below rather than instead of it -- same field/
    # behavior as every other modernized panel this session; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic. `managers` is the only employee-role field on this filter,
    # so it has a clear single owner to search against.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- managers is a ManyToManyField to Employee, so it opts in here
    # instead of pre-rendering the whole employee queryset as <option> tags.
    ajax_fields = {
        "managers": {
            "key": "project-managers",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    class Meta:
        model = Project
        fields = [
            "title",
            "managers",
            "status",
            "is_active",
        ]

    start_from = django_filters.DateFilter(
        field_name="start_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("Start From"),
    )
    end_till = django_filters.DateFilter(
        field_name="end_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("End Till"),
    )
    overdue = django_filters.CharFilter(method="filter_overdue", label=_("Overdue"))

    def filter_by_project(self, queryset, _, value):
        if self.data.get("search_field"):
            return queryset
        queryset = queryset.filter(title__icontains=value)
        return queryset

    def filter_overdue(self, queryset, name, value):
        if value == "True":
            return queryset.filter(end_date__lt=_date.today()).exclude(
                status__in=["completed", "cancelled", "expired"]
            )
        return queryset

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
            "managers__employee_first_name",
            "managers__employee_last_name",
            "managers__badge_id",
        )

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )


class TaskFilter(FilterSet):
    search = django_filters.CharFilter(method="filter_by_task")
    task_managers = django_filters.ModelChoiceFilter(
        field_name="task_managers", queryset=Employee.objects.all()
    )
    end_till = django_filters.DateFilter(
        field_name="end_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "stage",
            "task_managers",
            "end_date",
            "status",
            "project",
        ]

    def filter_by_task(self, queryset, _, value):
        queryset = queryset.filter(title__icontains=value)
        return queryset


class TaskAllFilter(HorillaFilterSet):
    search = django_filters.CharFilter(method="filter_by_task")
    end_till = django_filters.DateFilter(
        field_name="end_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("End Date Till"),
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- every model/queryset-backed field in the modern filter panel opts
    # in here instead of pre-rendering its whole queryset as <option> tags.
    # No dedicated "Name or Badge ID" field is added: task_managers and
    # task_members are two separate employee-role fields with no single
    # clear owner, same reasoning as the Recruitment Pipeline panel.
    ajax_fields = {
        "project": {
            "key": "task-project",
            "queryset_fn": lambda request: Project.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.title,
            "search_fields": ["title"],
            "placeholder": _("Select project..."),
        },
        "stage": {
            "key": "task-stage",
            "queryset_fn": lambda request: ProjectStage.objects.select_related(
                "project"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["title", "project__title"],
            "placeholder": _("Select stage..."),
        },
        "task_managers": {
            "key": "task-managers",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "task_members": {
            "key": "task-members",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    class Meta:
        model = Task
        fields = [
            "title",
            "project",
            "stage",
            "task_managers",
            "task_members",
            "end_date",
            "status",
            "is_active",
        ]

    def filter_by_task(self, queryset, _, value):
        queryset = queryset.filter(title__icontains=value)
        return queryset


class TimeSheetFilter(HorillaFilterSet):
    """
    Filter set class for Timesheet model
    """

    date = django_filters.DateFilter(
        field_name="date", widget=forms.DateInput(attrs={"type": "date"})
    )
    start_from = django_filters.DateFilter(
        field_name="date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("Start Date From"),
    )
    end_till = django_filters.DateFilter(
        field_name="date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
        label=_("End Date Till"),
    )

    task = django_filters.ModelChoiceFilter(
        field_name="task_id", queryset=Task.objects.all()
    )
    search = django_filters.CharFilter(method="filter_by_employee")

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- every model/queryset-backed field in the modern filter panel opts
    # in here instead of pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "project_id": {
            "key": "timesheet-project",
            "queryset_fn": lambda request: Project.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.title,
            "search_fields": ["title"],
            "placeholder": _("Select project..."),
        },
        "task": {
            "key": "timesheet-task",
            "queryset_fn": lambda request: Task.objects.select_related(
                "project"
            ).filter(is_active=True),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["title", "project__title"],
            "placeholder": _("Select task..."),
        },
        "employee_id": {
            "key": "timesheet-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    class Meta:
        """
        Meta class to add additional options
        """

        model = TimeSheet
        fields = [
            "employee_id",
            "project_id",
            "task_id",
            "date",
            "status",
        ]

    def filter_by_employee(self, queryset, _, value):
        """
        Filter queryset by first name or last name.
        """

        # Split the search value into first name and last name

        parts = value.split()
        first_name = parts[0]
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        # Filter the queryset by first name and last name
        if first_name and last_name != "":
            queryset = queryset.filter(
                Q(employee_id__employee_first_name__icontains=first_name)
                | Q(employee_id__employee_last_name__icontains=last_name)
            )
        elif first_name:
            queryset = queryset.filter(
                Q(employee_id__employee_first_name__icontains=first_name)
                | Q(employee_id__employee_last_name__icontains=first_name)
            )
        elif last_name:
            queryset = queryset.filter(
                employee_id__employee_last_name__icontains=last_name
            )
        return queryset

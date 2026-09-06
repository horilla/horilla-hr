"""
filters.py

This page is used to register filter for attendance models

"""

import datetime
import uuid

import django_filters
from django import forms
from django.db.models import Value
from django.db.models.functions import Coalesce, Concat
from django.forms import DateTimeInput
from django.utils.translation import gettext_lazy as _

from attendance.models import (
    Attendance,
    AttendanceActivity,
    AttendanceGeneralSetting,
    AttendanceLateComeEarlyOut,
    AttendanceOverTime,
    AttendanceValidationCondition,
    GraceTime,
    strtime_seconds,
)
from base.filters import FilterSet
from base.models import Company, Department, EmployeeShift, JobPosition, WorkType
from employee.filters import EmployeeFilter
from employee.models import Employee
from horilla.filters import HorillaFilterSet, filter_by_name, filter_name_or_badge_terms


class DurationInSecondsFilter(django_filters.CharFilter):
    """
    Custom CharFilter class that applies specific filter process.
    """

    def filter(self, qs, value):
        """
        FilterSet filter method

        Args:
            qs (self): FilterSet instance
            value (str): duration formatted string

        Returns:
            qs: queryset object
        """
        if value:
            ftr = [3600, 60, 1]
            duration_sec = sum(a * b for a, b in zip(ftr, map(int, value.split(":"))))
            lookup = self.lookup_expr or "exact"
            return qs.filter(**{f"{self.field_name}__{lookup}": duration_sec})
        return qs


class AttendanceOverTimeFilter(HorillaFilterSet):
    """
    Filter set class for AttendanceOverTime model

    Args:
        FilterSet (class): custom filter set class to apply styling
    """

    MONTH_CHOICES = [
        ("January", _("January")),
        ("February", _("February")),
        ("March", _("March")),
        ("April", _("April")),
        ("May", _("May")),
        ("June", _("June")),
        ("July", _("July")),
        ("August", _("August")),
        ("September", _("September")),
        ("October", _("October")),
        ("November", _("November")),
        ("December", _("December")),
    ]
    search = django_filters.CharFilter(method=filter_by_name)

    worked_hours__gte = DurationInSecondsFilter(
        field_name="hour_account_second", lookup_expr="gte"
    )
    worked_hours__lte = DurationInSecondsFilter(
        field_name="hour_account_second", lookup_expr="lte"
    )
    pending_hours__lte = DurationInSecondsFilter(
        field_name="hour_pending_second", lookup_expr="lte"
    )
    pending_hours__gte = DurationInSecondsFilter(
        field_name="hour_pending_second", lookup_expr="gte"
    )
    overtime__gte = DurationInSecondsFilter(
        field_name="overtime_second", lookup_expr="gte"
    )
    overtime__lte = DurationInSecondsFilter(
        field_name="overtime_second", lookup_expr="lte"
    )
    month = django_filters.ChoiceFilter(choices=MONTH_CHOICES, lookup_expr="icontains")
    department_name = django_filters.CharFilter(
        field_name="employee_id__employee_work_info__department_id__department",
        lookup_expr="icontains",
    )

    class Meta:
        """
        Meta class to add additional options
        """

        model = AttendanceOverTime
        fields = [
            "employee_id",
            "month",
            "overtime",
            "worked_hours",
            "year",
            "department_name",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__company_id",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__location",
            "employee_id__employee_work_info__reporting_manager_id",
            "employee_id__employee_work_info__shift_id",
            "employee_id__employee_work_info__work_type_id",
        ]

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"

        self.form.fields["employee_id__employee_work_info__location"].widget.attrs[
            "placeholder"
        ] = _("Work Location")


class LateComeEarlyOutFilter(HorillaFilterSet):
    """
    LateComeEarlyOutFilter class
    """

    search = django_filters.CharFilter(method=filter_by_name)
    employee_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Employee.objects.all(),
        widget=forms.SelectMultiple(),
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as AttendanceFilters.name_or_badge and
    # AttendanceActivityFilter.name_or_badge; see horilla.filters.
    # filter_name_or_badge_terms for the shared matching logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )
    # Any/Yes/No segmented toggle, matching AttendanceFilters.
    # attendance_validated/attendance_overtime_approve -- overrides the
    # auto-generated BooleanFilter/NullBooleanSelect Meta.fields would
    # otherwise produce for these two (can't express "Any" as a clean
    # empty state the same way).
    attendance_id__attendance_validated = django_filters.ChoiceFilter(
        field_name="attendance_id__attendance_validated",
        label=_("Validated?"),
        choices=[("", _("Any")), (True, _("Yes")), (False, _("No"))],
        empty_label=None,
        widget=forms.RadioSelect,
    )
    attendance_id__attendance_overtime_approve = django_filters.ChoiceFilter(
        field_name="attendance_id__attendance_overtime_approve",
        label=_("OT Approved?"),
        choices=[("", _("Any")), (True, _("Yes")), (False, _("No"))],
        empty_label=None,
        widget=forms.RadioSelect,
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation) -- mirrors
    # AttendanceFilters.ajax_fields, keys prefixed "late-" so they don't
    # collide with the other Attendance FilterSets' ajax-choices keys.
    ajax_fields = {
        "employee_id": {
            "key": "late-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "late-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "employee_id__employee_work_info__company_id": {
            "key": "late-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": _("Select company..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "late-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "late-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "attendance_id__shift_id": {
            "key": "late-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": _("Select shift..."),
        },
        "attendance_id__work_type_id": {
            "key": "late-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": _("Select work type..."),
        },
    }

    attendance_date__gte = django_filters.DateFilter(
        field_name="attendance_id__attendance_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    attendance_date__lte = django_filters.DateFilter(
        field_name="attendance_id__attendance_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    attendance_clock_in__lte = django_filters.TimeFilter(
        field_name="attendance_id__attendance_clock_in",
        widget=forms.TimeInput(attrs={"type": "time"}),
        lookup_expr="lte",
    )
    attendance_clock_in__gte = django_filters.TimeFilter(
        field_name="attendance_id__attendance_clock_in",
        widget=forms.TimeInput(attrs={"type": "time"}),
        lookup_expr="gte",
    )
    attendance_clock_out__gte = django_filters.TimeFilter(
        field_name="attendance_id__attendance_clock_out",
        widget=forms.TimeInput(attrs={"type": "time"}),
        lookup_expr="gte",
    )
    attendance_clock_out__lte = django_filters.TimeFilter(
        field_name="attendance_id__attendance_clock_out",
        widget=forms.TimeInput(attrs={"type": "time"}),
        lookup_expr="lte",
    )
    attendance_date = django_filters.DateFilter(
        field_name="attendance_id__attendance_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    overtime_second__lte = DurationInSecondsFilter(
        field_name="attendance_id__overtime_second", lookup_expr="lte"
    )
    overtime_second__gte = DurationInSecondsFilter(
        field_name="attendance_id__overtime_second", lookup_expr="gte"
    )
    at_work_second__lte = DurationInSecondsFilter(
        field_name="attendance_id__at_work_second", lookup_expr="lte"
    )
    at_work_second__gte = DurationInSecondsFilter(
        field_name="attendance_id__at_work_second", lookup_expr="gte"
    )
    department = django_filters.CharFilter(
        field_name="employee_id__employee_work_info__department_id__department",
        lookup_expr="icontains",
    )
    year = django_filters.CharFilter(
        field_name="attendance_id__attendance_date", lookup_expr="year"
    )
    month = django_filters.CharFilter(
        field_name="attendance_id__attendance_date", lookup_expr="month"
    )
    week = django_filters.CharFilter(
        field_name="attendance_id__attendance_date", lookup_expr="week"
    )

    class Meta:
        """
        Meta class for additional options"""

        model = AttendanceLateComeEarlyOut
        fields = [
            "employee_id",
            "type",
            "attendance_id__minimum_hour",
            "attendance_id__attendance_worked_hour",
            "attendance_id__attendance_overtime_approve",
            "attendance_id__attendance_validated",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__company_id",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__location",
            "employee_id__employee_work_info__reporting_manager_id",
            "attendance_id__shift_id",
            "attendance_id__work_type_id",
            "attendance_date__gte",
            "attendance_date__lte",
            "attendance_clock_in__lte",
            "attendance_clock_in__gte",
            "attendance_clock_out__gte",
            "attendance_clock_out__lte",
            "attendance_date",
            "department",
            "year",
            "month",
            "week",
        ]

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder --
        In/Out clock time and At Work/OT ranges used to each have their
        own permanent From/Till inputs in the Advanced section, but were
        moved out here (kept dedicated: Attendance Date, the one used
        often enough to stay permanent), same consolidation as
        AttendanceFilters._build_custom_filter_fields.

        Clock In/Out use the plain field+lookup shape (attendance_id__
        attendance_clock_in/out are plain TimeField columns via the FK,
        so any of gte/lte/gt/lt/exact is just a normal ORM lookup). At
        Work/OT use the "declared-filter" shape instead (DurationInSeconds
        Filter.filter does its own "HH:MM:SS" <-> seconds conversion, same
        as AttendanceFilters' Pending Hour/OT).
        """
        fields = [
            {
                "key": "clock_in",
                "field": "attendance_id__attendance_clock_in",
                "label": str(_("Clock In")),
                "type": "time_range",
            },
            {
                "key": "clock_out",
                "field": "attendance_id__attendance_clock_out",
                "label": str(_("Clock Out")),
                "type": "time_range",
            },
            {
                "key": "at_work_from",
                "filter_name": "at_work_second__gte",
                "label": str(_("At Work Greater or Equal")),
                "type": "duration_from",
            },
            {
                "key": "at_work_till",
                "filter_name": "at_work_second__lte",
                "label": str(_("At Work Lesser or Equal")),
                "type": "duration_till",
            },
            {
                "key": "overtime_from",
                "filter_name": "overtime_second__gte",
                "label": str(_("OT Greater or Equal")),
                "type": "duration_from",
            },
            {
                "key": "overtime_till",
                "filter_name": "overtime_second__lte",
                "label": str(_("OT Lesser or Equal")),
                "type": "duration_till",
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
        the end" hookup, same as AttendanceFilters.filter_queryset.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter and
        AttendanceFilters).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )


class AttendanceActivityFilter(HorillaFilterSet):
    """
    Filter set class for AttendanceActivity model

    Args:
        FilterSet (class): custom filter set class to apply styling
    """

    search = django_filters.CharFilter(method=filter_by_name)

    attendance_date = django_filters.DateFilter(
        field_name="attendance_date", widget=forms.DateInput(attrs={"type": "date"})
    )
    attendance_date_from = django_filters.DateFilter(
        field_name="attendance_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    attendance_date_till = django_filters.DateFilter(
        field_name="attendance_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    in_from = django_filters.DateFilter(
        field_name="clock_in",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "time"}),
    )
    out_from = django_filters.DateFilter(
        field_name="clock_out",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "time"}),
    )
    in_till = django_filters.DateFilter(
        field_name="clock_in",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "time"}),
    )
    out_till = django_filters.DateFilter(
        field_name="clock_out",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "time"}),
    )
    clock_in_date = django_filters.DateFilter(
        field_name="clock_in_date", widget=forms.DateInput(attrs={"type": "date"})
    )
    clock_out_date = django_filters.DateFilter(
        field_name="clock_out_date", widget=forms.DateInput(attrs={"type": "date"})
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as AttendanceFilters.name_or_badge and
    # EmployeeFilter.name_or_badge; see horilla.filters.
    # filter_name_or_badge_terms for the shared matching logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation) -- mirrors
    # AttendanceFilters.ajax_fields field-for-field (same employee_id__
    # employee_work_info__* paths, since AttendanceActivity also has an
    # employee_id FK), keys prefixed "activity-" so they don't collide
    # with AttendanceFilters' own ajax-choices endpoint keys.
    ajax_fields = {
        "employee_id": {
            "key": "activity-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "activity-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "employee_id__employee_work_info__company_id": {
            "key": "activity-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": _("Select company..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "activity-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "activity-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__shift_id": {
            "key": "activity-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": _("Select shift..."),
        },
        "employee_id__employee_work_info__work_type_id": {
            "key": "activity-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": _("Select work type..."),
        },
    }

    class Meta:
        """
        Meta class to add additional options
        """

        fields = [
            "employee_id",
            "attendance_date",
            "attendance_date_from",
            "attendance_date_till",
            "in_from",
            "in_till",
            "out_from",
            "shift_day",
            "out_till",
            "clock_in_date",
            "clock_out_date",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__company_id",
            "employee_id__employee_work_info__shift_id",
            "employee_id__employee_work_info__work_type_id",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__location",
            "employee_id__employee_work_info__reporting_manager_id",
        ]
        model = AttendanceActivity

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder --
        In/Out clock time used to have fixed From/Till inputs
        (in_from/in_till/out_from/out_till) permanently in the Advanced
        section; consolidated here into one flexible entry per side
        (offering every comparison: From/Till/After/Before/Is) instead,
        same consolidation as AttendanceFilters._build_custom_filter_fields
        did for attendance_clock_in/attendance_clock_out. clock_in/
        clock_out are plain TimeField columns, so any of gte/lte/gt/lt/
        exact is just a normal ORM lookup -- no declared-filter dispatch
        needed.

        in_datetime/out_datetime are the full DateTimeField columns
        (date + time together, vs. clock_in/clock_out's time-only and
        clock_in_date/clock_out_date's date-only columns) -- offered here
        too via the "datetime_range" category so the exact moment can be
        filtered directly instead of separately narrowing date and time.
        """
        fields = [
            {
                "key": "clock_in",
                "field": "clock_in",
                "label": str(_("Clock In")),
                "type": "time_range",
            },
            {
                "key": "clock_out",
                "field": "clock_out",
                "label": str(_("Clock Out")),
                "type": "time_range",
            },
            {
                "key": "in_datetime",
                "field": "in_datetime",
                "label": str(_("In Datetime")),
                "type": "datetime_range",
            },
            {
                "key": "out_datetime",
                "field": "out_datetime",
                "label": str(_("Out Datetime")),
                "type": "datetime_range",
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
        the end" hookup, same as AttendanceFilters.filter_queryset.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter and
        AttendanceFilters).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"

        self.form.fields["employee_id__employee_work_info__location"].widget.attrs[
            "placeholder"
        ] = _("Work Location")
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )


class AttendanceFilters(HorillaFilterSet):
    """
    Filter set class for Attendance model

    Args:
        FilterSet (class): custom filter set class to apply styling
    """

    id = django_filters.NumberFilter(field_name="id")
    search = django_filters.CharFilter(method="filter_by_name")
    search_field = django_filters.CharFilter(method="search_in")

    employee = django_filters.CharFilter(field_name="employee_id__id")
    date_attendance = django_filters.DateFilter(field_name="attendance_date")
    employee_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Employee.objects.all(),
        widget=forms.SelectMultiple(),
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker above rather than instead of it -- e.g.
    # "PEP01, PEP02, jane" matches any attendance whose employee's name
    # or badge matches ANY one of those terms. Same field/behavior as
    # EmployeeFilter.name_or_badge; see horilla.filters.
    # filter_name_or_badge_terms for the shared matching logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # Any/Yes/No segmented toggle, matching EmployeeFilter.is_active --
    # the leading empty choice is what lets the field clear back to
    # unfiltered (a plain Yes/No ChoiceField, or the auto-generated
    # BooleanFilter/NullBooleanSelect Meta.fields would otherwise produce
    # for these two, can't express that -- see HorillaNavView.
    # _get_applied_filter_count's own comment on why "unknown" being non-
    # empty matters for the filter-count badge).
    attendance_validated = django_filters.ChoiceFilter(
        field_name="attendance_validated",
        label=_("Validated?"),
        choices=[("", _("Any")), (True, _("Yes")), (False, _("No"))],
        # empty_label=None: ChoiceFilter prepends its OWN blank
        # "---------" choice by default (FILTERS_EMPTY_CHOICE_LABEL),
        # redundant alongside the "Any" choice declared above. widget=
        # RadioSelect: without it this falls back to a plain <select>,
        # which the segmented-toggle template markup below (iterating
        # `form.field` as individual radio subwidgets) isn't built to
        # render -- both exactly matching EmployeeFilter.is_active.
        empty_label=None,
        widget=forms.RadioSelect,
    )
    attendance_overtime_approve = django_filters.ChoiceFilter(
        field_name="attendance_overtime_approve",
        label=_("OT Approved?"),
        choices=[("", _("Any")), (True, _("Yes")), (False, _("No"))],
        empty_label=None,
        widget=forms.RadioSelect,
    )
    # Same Any/Yes/No segmented pattern, for the "My Attendances" panel
    # (my_attendance_filter.html) -- these two aren't shown on the main
    # Attendance list's own panel, only "My Attendances"'s.
    is_validate_request = django_filters.ChoiceFilter(
        field_name="is_validate_request",
        label=_("Requested?"),
        choices=[("", _("Any")), (True, _("Yes")), (False, _("No"))],
        empty_label=None,
        widget=forms.RadioSelect,
    )
    is_validate_request_approved = django_filters.ChoiceFilter(
        field_name="is_validate_request_approved",
        label=_("Approved Request?"),
        choices=[("", _("Any")), (True, _("Yes")), (False, _("No"))],
        empty_label=None,
        widget=forms.RadioSelect,
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation) -- every
    # model/queryset-backed field in the modern filter panel opts in here
    # instead of pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "employee_id": {
            "key": "attendance-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "attendance-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "employee_id__employee_work_info__company_id": {
            "key": "attendance-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": _("Select company..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "attendance-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "attendance-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "shift_id": {
            "key": "attendance-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": _("Select shift..."),
        },
        "work_type_id": {
            "key": "attendance-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": _("Select work type..."),
        },
    }

    attendance_date__gte = django_filters.DateFilter(
        field_name="attendance_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    attendance_date__lte = django_filters.DateFilter(
        field_name="attendance_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    attendance_clock_in__lte = django_filters.TimeFilter(
        field_name="attendance_clock_in",
        widget=forms.TimeInput(attrs={"type": "time"}),
        lookup_expr="lte",
    )
    attendance_clock_in__gte = django_filters.TimeFilter(
        field_name="attendance_clock_in",
        widget=forms.TimeInput(attrs={"type": "time"}),
        lookup_expr="gte",
    )
    attendance_clock_out__gte = django_filters.TimeFilter(
        field_name="attendance_clock_out",
        widget=forms.TimeInput(attrs={"type": "time"}),
        lookup_expr="gte",
    )
    attendance_clock_out__lte = django_filters.TimeFilter(
        field_name="attendance_clock_out",
        widget=forms.TimeInput(attrs={"type": "time"}),
        lookup_expr="lte",
    )
    attendance_date = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    pending_hour_lte = DurationInSecondsFilter(
        method="filter_pending_hour",
    )
    pending_hour_gte = DurationInSecondsFilter(
        method="filter_pending_hour",
    )
    at_work_second__lte = DurationInSecondsFilter(
        field_name="at_work_second",
        lookup_expr="lte",
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    at_work_second__gte = DurationInSecondsFilter(
        field_name="at_work_second",
        lookup_expr="gte",
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    overtime_second__lte = DurationInSecondsFilter(
        field_name="overtime_second",
        lookup_expr="lte",
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    overtime_second__gte = DurationInSecondsFilter(
        field_name="overtime_second",
        lookup_expr="gte",
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    year = django_filters.CharFilter(field_name="attendance_date", lookup_expr="year")
    month = django_filters.CharFilter(field_name="attendance_date", lookup_expr="month")
    week = django_filters.CharFilter(field_name="attendance_date", lookup_expr="week")
    department = django_filters.CharFilter(
        field_name="employee_id__employee_work_info__department_id__department",
        lookup_expr="icontains",
    )

    @property
    def form(self):
        form = super().form
        form.fields["pending_hour_lte"].widget = forms.TimeInput(
            attrs={"type": "time", "class": "oh-input w-100 form-control"}
        )
        form.fields["pending_hour_gte"].widget = forms.TimeInput(
            attrs={"type": "time", "class": "oh-input w-100 form-control"}
        )
        return form

    def filter_pending_hour(self, queryset, name, value):
        """
        This method calculates the pending hours for each attendance record in the
        queryset and filters the records based on whether the pending hours are less
        than or equal to (`pending_hour__lte`) or greater than the specified value.
        """
        if value is not None:
            value = strtime_seconds(value)
            filtered_attendance = []
            for attendance in queryset:
                minimum_hour_second = strtime_seconds(attendance.minimum_hour)
                worked_hour_second = attendance.at_work_second
                pending_hour_second = minimum_hour_second - worked_hour_second
                if name == "pending_hour__lte":
                    if value >= pending_hour_second:
                        filtered_attendance.append(attendance)
                else:
                    if value <= pending_hour_second:
                        filtered_attendance.append(attendance)
        return queryset.filter(
            id__in=[attendance.id for attendance in filtered_attendance]
        )

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder --
        In/Out clock time and Pending Hour/OT ranges used to each have
        their own permanent From/Till inputs in the Advanced section, but
        were moved out here (kept dedicated: Attendance Date and At Work,
        the two used often enough to stay permanent).

        Clock In/Out use the plain field+lookup shape, ONE entry each
        offering every comparison ("time_range": From/Till/After/Before/
        Is) rather than a separate fixed-direction entry per side --
        attendance_clock_in/attendance_clock_out are plain TimeField
        columns, so any of gte/lte/gt/lt/exact is just a normal ORM
        lookup (see HorillaFilterSet._build_custom_filter_fields's
        docstring), no per-direction Filter object needed.

        Pending Hour and OT use the "declared-filter" shape instead
        (still one entry per direction): pending_hour_gte/lte and
        overtime_second__gte/lte each do their own "HH:MM:SS" <-> seconds
        conversion (filter_pending_hour / DurationInSecondsFilter.filter)
        rather than a plain ORM lookup, and each direction is its own
        separate Filter object -- a raw queryset.filter(**{...}) call in
        the generic path wouldn't reproduce that conversion, and there's
        no single Filter here that supports more than the one lookup it
        was declared with, so these can't be collapsed into one flexible
        entry the way Clock In/Out could.
        """
        fields = [
            {
                "key": "clock_in",
                "field": "attendance_clock_in",
                "label": str(_("Clock In")),
                "type": "time_range",
            },
            {
                "key": "clock_out",
                "field": "attendance_clock_out",
                "label": str(_("Clock Out")),
                "type": "time_range",
            },
            {
                "key": "pending_hour_from",
                "filter_name": "pending_hour_gte",
                "label": str(_("Pending Hour Greater or Equal")),
                "type": "duration_from",
            },
            {
                "key": "pending_hour_till",
                "filter_name": "pending_hour_lte",
                "label": str(_("Pending Hour Lesser or Equal")),
                "type": "duration_till",
            },
            {
                "key": "overtime_from",
                "filter_name": "overtime_second__gte",
                "label": str(_("OT Greater or Equal")),
                "type": "duration_from",
            },
            {
                "key": "overtime_till",
                "filter_name": "overtime_second__lte",
                "label": str(_("OT Lesser or Equal")),
                "type": "duration_till",
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
        filter_queryset automatically (see its own docstring) -- this is
        the minimal "call it at the end" hookup, same as EmployeeFilter's
        own filter_queryset does alongside its own extra logic.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)

    class Meta:
        """
        Meta class to add additional options
        """

        model = Attendance
        fields = [
            "id",
            "employee_id",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__company_id",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__location",
            "employee_id__employee_work_info__reporting_manager_id",
            "attendance_day",
            "attendance_date",
            "work_type_id",
            "shift_id",
            "minimum_hour",
            "attendance_validated",
            "at_work_second",
            "overtime_second",
            "late_come_early_out__type",
            "attendance_overtime_approve",
            "attendance_validated",
            "is_validate_request",
            "is_validate_request_approved",
            "is_bulk_request",
            "at_work_second__lte",
            "at_work_second__gte",
            "overtime_second__lte",
            "overtime_second__gte",
            "overtime_second",
            "department",
            "month",
            "year",
            "batch_attendance_id",
        ]

        widgets = {
            "attendance_date": DateTimeInput(attrs={"type": "date"}),
        }

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"

        self.form.fields["employee_id__employee_work_info__location"].widget.attrs[
            "placeholder"
        ] = _("Work Location")
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )

    def filter_by_name(self, queryset, name, value):

        if self.data.get("search_field"):
            return queryset
        # Call the imported function
        """
        This method allows filtering by the employee's first and/or last name or by other
        fields such as day, shift, work type, department, job position, or company, depending
        on the value of `search_field` provided in the request data.
        """
        filter_method = {
            "day": "attendance_day__day__icontains",
            "shift": "shift_id__employee_shift__icontains",
            "work_type": "work_type_id__work_type__icontains",
            "department": "employee_id__employee_work_info__department_id__department__icontains",
            "job_position": "employee_id__employee_work_info__\
                job_position_id__job_position__icontains",
            "company": "employee_id__employee_work_info__company_id__company__icontains",
        }
        search_field = self.data.get("search_field")
        qs = queryset
        if not search_field:
            value = " ".join(value.split())

            queryset = queryset.annotate(
                full_name=Concat(
                    Coalesce("employee_id__employee_first_name", Value("")),
                    Value(" "),
                    Coalesce("employee_id__employee_last_name", Value("")),
                )
            )

            queryset = queryset.filter(full_name__icontains=value)

            queryset = (
                queryset | qs.filter(employee_id__badge_id__icontains=value)
            ).distinct()
        else:
            filter = filter_method.get(search_field)
            queryset = queryset.filter(**{filter: value})

        queryset = (
            queryset | qs.filter(employee_id__badge_id__icontains=value).distinct()
        )

        return queryset


class LateComeEarlyOutReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("employee_id", "Employee"),
        ("type", "Type"),
        ("attendance_id__attendance_date", "Attendance Date"),
        ("attendance_id__shift_id", "Shift"),
        ("attendance_id__work_type_id", "Work Type"),
        ("attendance_id__minimum_hour", "Minimum Hour"),
        ("attendance_id__employee_id__country", "Country"),
        (
            "attendance_id__employee_id__employee_work_info__reporting_manager_id",
            "Reporting Manager",
        ),
        ("attendance_id__employee_id__employee_work_info__department_id", "Department"),
        (
            "attendance_id__employee_id__employee_work_info__job_position_id",
            "Job Position",
        ),
        (
            "attendance_id__employee_id__employee_work_info__employee_type_id",
            "Employment Type",
        ),
        ("attendance_id__employee_id__employee_work_info__company_id", "Company"),
    ]


class AttendanceReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("employee_id", "Employee"),
        ("batch_attendance_id", "Batch"),
        ("attendance_date", "Attendance Date"),
        ("shift_id", "Shift"),
        ("work_type_id", "Work Type"),
        ("minimum_hour", "Minimum Hour"),
        ("employee_id__country", "Country"),
        ("employee_id__employee_work_info__reporting_manager_id", "Reporting Manager"),
        ("employee_id__employee_work_info__department_id", "Department"),
        ("employee_id__employee_work_info__job_position_id", "Job Position"),
        ("employee_id__employee_work_info__employee_type_id", "Employment Type"),
        ("employee_id__employee_work_info__company_id", "Company"),
    ]


class AttendanceOvertimeReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("employee_id", "Employee"),
        ("month", "Month"),
        ("year", "Year"),
        ("employee_id__country", "Country"),
        ("employee_id__employee_work_info__reporting_manager_id", "Reporting Manager"),
        ("employee_id__employee_work_info__shift_id", "Shift"),
        ("employee_id__employee_work_info__work_type_id", "Work Type"),
        ("employee_id__employee_work_info__department_id", "Department"),
        ("employee_id__employee_work_info__job_position_id", "Job Position"),
        ("employee_id__employee_work_info__employee_type_id", "Employment Type"),
        ("employee_id__employee_work_info__company_id", "Company"),
    ]


class AttendanceActivityReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("employee_id", "Employee"),
        ("attendance_date", "Attendance Date"),
        ("clock_in_date", "In Date"),
        ("clock_out_date", "Out Date"),
        ("shift_day", "Shift Day"),
        ("employee_id__country", "Country"),
        ("employee_id__employee_work_info__reporting_manager_id", "Reporting Manager"),
        ("employee_id__employee_work_info__shift_id", "Shift"),
        ("employee_id__employee_work_info__work_type_id", "Work Type"),
        ("employee_id__employee_work_info__department_id", "Department"),
        ("employee_id__employee_work_info__job_position_id", "Job Position"),
        ("employee_id__employee_work_info__employee_type_id", "Employment Type"),
        ("employee_id__employee_work_info__company_id", "Company"),
    ]


class AttendanceRequestReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("employee_id", "Employee"),
        ("batch_attendance_id", "Batch"),
        ("attendance_day", "Attendance Date"),
        ("attendance_clock_in_date", "In Date"),
        ("attendance_clock_out_date", "Out Date"),
        ("employee_id__country", "Country"),
        ("employee_id__employee_work_info__reporting_manager_id", "Reporting Manager"),
        ("employee_id__employee_work_info__shift_id", "Shift"),
        ("employee_id__employee_work_info__work_type_id", "Work Type"),
        ("employee_id__employee_work_info__department_id", "Department"),
        ("employee_id__employee_work_info__job_position_id", "Job Position"),
        ("employee_id__employee_work_info__employee_type_id", "Employment Type"),
        ("employee_id__employee_work_info__company_id", "Company"),
    ]


class AttendanceBreakpointFilter(FilterSet):
    """
    filter class for attendance breakpoint condition model
    """

    search = django_filters.CharFilter(field_name="company_id", lookup_expr="icontains")

    class Meta:
        model = AttendanceValidationCondition
        fields = [
            "validation_at_work",
            "minimum_overtime_to_approve",
            "overtime_cutoff",
            "company_id",
        ]


class GraceTimeFilter(HorillaFilterSet):

    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = GraceTime
        fields = ["company_id"]

    def search_method(self, queryset, _, value):
        """
        This method is used to mail server
        """

        return ((queryset.filter(company_id__company__icontains=value))).distinct()


class AttendanceGeneralSettingFilter(HorillaFilterSet):

    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = AttendanceGeneralSetting
        fields = ["company_id"]

    def search_method(self, queryset, _, value):
        """
        This method is used to mail server
        """
        return ((queryset.filter(company_id__company__icontains=value))).distinct()


def get_working_today(queryset, _name, value):
    today = datetime.datetime.now().date()
    yesterday = today - datetime.timedelta(days=1)

    working_employees = Attendance.objects.filter(
        attendance_date__gte=yesterday,
        attendance_date__lte=today,
        attendance_clock_out_date__isnull=True,
    ).values_list("employee_id", flat=True)

    if value:
        queryset = queryset.filter(id__in=working_employees)
    else:
        queryset = queryset.exclude(id__in=working_employees)
    return queryset


og_init = EmployeeFilter.__init__


def online_init(self, *args, **kwargs):
    og_init(self, *args, **kwargs)
    custom_field = django_filters.BooleanFilter(
        label="Working", method=get_working_today
    )
    self.filters["working_today"] = custom_field
    self.form.fields["working_today"] = custom_field.field
    self.form.fields["working_today"].widget.attrs.update(
        {
            "class": "oh-select oh-select-2 w-100",
        }
    )


EmployeeFilter.__init__ = online_init

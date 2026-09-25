"""
offboarding/filters.py

This module is used to register django_filters
"""

import uuid

import django_filters
from django import forms
from django.utils.translation import gettext_lazy as _

from base.filters import FilterSet
from base.models import (
    Department,
    EmployeeShift,
    EmployeeType,
    JobPosition,
    JobRole,
    WorkType,
)
from employee.models import Employee
from horilla.filters import HorillaFilterSet, filter_name_or_badge_terms
from offboarding.models import (
    Offboarding,
    OffboardingEmployee,
    OffboardingStage,
    ResignationLetter,
)


class LetterFilter(HorillaFilterSet):
    """
    LetterFilter class
    """

    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")
    planned_to_leave_on = django_filters.DateFilter(
        field_name="planned_to_leave_on",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as every other modernized panel this session; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )
    # Multi-status deep link (e.g. the dashboard's Joining vs Exiting
    # "Exiting" series, status__in=["approved", "requested"]) -- status
    # itself is single-value exact, so this can't be expressed there.
    # Comma-separated, same convention as filter_name_or_badge_terms's
    # multi-term input.
    status_in = django_filters.CharFilter(method="filter_status_in")

    # Dedicated Created At range (dashboard deep links: Resignation Status,
    # Department Attrition, Exit Reasons). The Advanced "+ Add filter"
    # builder already offers a generic date_range entry for each of these
    # (see _build_custom_filter_fields below), but that mechanism submits
    # gte/lte as two rows sharing the same custom_field/custom_lookup/
    # custom_value <select> names -- fine for the builder's own UI, but the
    # generic filter-tag chip bar (horilla_views/templates/generic/
    # filter_tags.html) has no way to tell those rows apart and renders
    # garbled tags ("Custom field: Created at" / "Custom lookup: GteLte").
    # A uniquely-named field per direction (same "_from"/"_till" convention
    # as EmployeeFilter.probation_from/_till, AttendanceFilters.
    # attendance_date_from/_till, ...) sidesteps that entirely: each shows
    # up as its own clean, correctly-labelled tag.
    created_at_from = django_filters.DateFilter(
        field_name="created_at",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    created_at_till = django_filters.DateFilter(
        field_name="created_at",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    # Same reasoning, for Department Attrition's OffboardingEmployee.
    # created_at (see has_offboarding above for why that's a different
    # column than this letter's own created_at).
    offboarding_created_at_from = django_filters.DateFilter(
        field_name="offboarding_employee_id__created_at",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    offboarding_created_at_till = django_filters.DateFilter(
        field_name="offboarding_employee_id__created_at",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    # Same reasoning, for Exit Reasons' ExitReason.created_at.
    exit_reason_logged_at_from = django_filters.DateFilter(
        field_name="offboarding_employee_id__exitreason__created_at",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    exit_reason_logged_at_till = django_filters.DateFilter(
        field_name="offboarding_employee_id__exitreason__created_at",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    # Department Attrition chart deep link -- that chart counts
    # OffboardingEmployee rows grouped by department, not raw
    # ResignationLetter rows: a letter that was only ever "requested" or
    # "rejected" without ever becoming an offboarding employee (
    # offboarding_employee_id stays null) was never counted there, so the
    # plain department field alone over-counts the redirect's list versus
    # what the chart showed. This narrows it back down to the same
    # population.
    has_offboarding = django_filters.BooleanFilter(method="filter_has_offboarding")

    # Exit Reasons chart deep link (dashboard -> Resignation Letter view) --
    # ResignationLetter has no exit_reason field of its own; the reason is
    # logged against the linked OffboardingEmployee (see
    # PipelineEmployeeFilter.filter_exit_reason's identical reverse-accessor
    # note in this same module).
    exit_reason = django_filters.CharFilter(method="filter_exit_reason")

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- every model/queryset-backed field in the modern filter panel opts
    # in here instead of pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "employee_id": {
            "key": "resignation-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "resignation-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "resignation-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "resignation-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    class Meta:
        model = ResignationLetter
        fields = [
            "status",
            "employee_id",
            "planned_to_leave_on",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__reporting_manager_id",
        ]

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
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )

    def filter_status_in(self, queryset, name, value):
        statuses = [s.strip() for s in value.split(",") if s.strip()]
        return queryset.filter(status__in=statuses) if statuses else queryset

    def filter_has_offboarding(self, queryset, name, value):
        return queryset.filter(offboarding_employee_id__isnull=not value)

    def filter_exit_reason(self, queryset, name, value):
        return queryset.filter(offboarding_employee_id__exitreason__title=value)

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Planned To Leave On stays available
        as its own exact-match quick field above too; this adds the
        full gte/lte/gt/lt/exact set for it, plus Created At.
        """
        fields = [
            {
                "key": "planned_to_leave_on",
                "field": "planned_to_leave_on",
                "label": str(_("Planned To Leave On")),
                "type": "date_range",
            },
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(_("Created At")),
                "type": "date_range",
            },
            # Department Attrition chart deep link -- the dashboard counts
            # OffboardingEmployee.created_at for that period, not the
            # letter's own created_at, so the redirect needs this separate
            # path to reproduce the exact same slice.
            {
                "key": "offboarding_created_at",
                "field": "offboarding_employee_id__created_at",
                "label": str(_("Offboarding Created At")),
                "type": "date_range",
            },
            # Exit Reasons chart deep link -- same field path as
            # PipelineEmployeeFilter's identical "exit_reason_logged_at"
            # entry above, one hop further through offboarding_employee_id.
            {
                "key": "exit_reason_logged_at",
                "field": "offboarding_employee_id__exitreason__created_at",
                "label": str(_("Exit Reason Logged On")),
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

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )


class PipelineFilter(HorillaFilterSet):
    """
    PipelineFilter
    """

    search = django_filters.CharFilter(method="search_method", lookup_expr="icontains")
    offboarding_manager = django_filters.ModelChoiceFilter(
        field_name="managers", queryset=Employee.objects.all()
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Managers opts into an AJAX-searched combobox instead of
    # pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "offboarding_manager": {
            "key": "exit-process-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    class Meta:
        model = Offboarding
        fields = "__all__"

    def search_method(self, queryset, _, value):
        """
        This method is used to add custom search condition
        """
        return (
            queryset.filter(title__icontains=value)
            | queryset.filter(offboardingstage__title__icontains=value)
            | queryset.filter(
                offboardingstage__offboardingemployee__employee_id__employee_first_name__icontains=value
            )
        ).distinct()

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Created At is the only real date
        column on this model, so it's the sole entry.
        """
        fields = [
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


class PipelineStageFilter(HorillaFilterSet):
    """
    PipelineStageFilter
    """

    search = django_filters.CharFilter(method="search_method", lookup_expr="icontains")

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Offboarding opts into an AJAX-searched combobox instead of
    # pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "offboarding_id": {
            "key": "exit-process-stage-offboarding",
            "queryset_fn": lambda request: Offboarding.objects.all(),
            "display_fn": lambda obj: obj.title,
            "search_fields": ["title"],
            "placeholder": _("Select offboarding..."),
        },
    }

    class Meta:
        model = OffboardingStage
        fields = "__all__"
        exclude = [
            "sequence",
        ]

    def search_method(self, queryset, _, value):
        """
        This method is used to add custom search condition
        """

        return (
            queryset.filter(title__icontains=value)
            | queryset.filter(
                offboardingemployee__employee_id__employee_first_name__icontains=value
            )
            | queryset.filter(offboarding_id__title__icontains=value)
        ).distinct()

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Created At is the only real date
        column on this model, so it's the sole entry.
        """
        fields = [
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


class PipelineEmployeeFilter(HorillaFilterSet):
    """
    PipelineEmployeeFilter
    """

    search = django_filters.CharFilter(method="search_method", lookup_expr="icontains")

    notice_period_starts = django_filters.DateFilter(
        field_name="notice_period_starts",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    notice_period_ends = django_filters.DateFilter(
        field_name="notice_period_ends",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    offboarding_stage_id = django_filters.CharFilter(
        field_name="stage_id",
    )
    stage_type = django_filters.CharFilter(
        field_name="stage_id__type",
    )
    # Exact-employee deep link (e.g. the dashboard's Notice Period Tracker
    # rows) -- plain FK-by-pk match, same shape as offboarding_stage_id/
    # stage_type above.
    employee_id = django_filters.CharFilter(
        field_name="employee_id",
    )
    # "Active Offboarding" (dashboard KPI) is every non-archived employee --
    # stage_type above is exact-match only, so it can't express that; a
    # dedicated exclude method is the only way to reuse the same stage
    # "type" values without adding a fixed stage_type=!archived convention.
    stage_type_exclude = django_filters.CharFilter(method="filter_stage_type_exclude")
    # Exit Reasons chart deep link -- ExitReason.offboarding_employee_id's
    # default reverse accessor is "exitreason" (no related_name set).
    exit_reason = django_filters.CharFilter(method="filter_exit_reason")

    def filter_stage_type_exclude(self, queryset, name, value):
        return queryset.exclude(stage_id__type=value)

    def filter_exit_reason(self, queryset, name, value):
        return queryset.filter(exitreason__title=value)

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Department/Job Position/Job Role/Employee Type/Shift/Work Type
    # opt into AJAX-searched comboboxes instead of pre-rendering their
    # whole queryset as <option> tags.
    ajax_fields = {
        "employee_id__employee_work_info__department_id": {
            "key": "exit-process-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "exit-process-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "employee_id__employee_work_info__job_role_id": {
            "key": "exit-process-job-role",
            "queryset_fn": lambda request: JobRole.objects.select_related(
                "job_position_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_role", "job_position_id__job_position"],
            "placeholder": _("Select job role..."),
        },
        "employee_id__employee_work_info__employee_type_id": {
            "key": "exit-process-employee-type",
            "queryset_fn": lambda request: EmployeeType.objects.all(),
            "display_fn": lambda obj: obj.employee_type,
            "search_fields": ["employee_type"],
            "placeholder": _("Select employee type..."),
        },
        "employee_id__employee_work_info__shift_id": {
            "key": "exit-process-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": _("Select shift..."),
        },
        "employee_id__employee_work_info__work_type_id": {
            "key": "exit-process-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": _("Select work type..."),
        },
    }

    class Meta:
        model = OffboardingEmployee
        fields = [
            "stage_id",
            "employee_id__gender",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__job_role_id",
            "employee_id__employee_work_info__employee_type_id",
            "employee_id__employee_work_info__shift_id",
            "employee_id__employee_work_info__work_type_id",
        ]

    def search_method(self, queryset, _, value):
        """
        This method is used to add custom search condition
        """
        return (
            queryset.filter(employee_id__employee_first_name__icontains=value)
            | queryset.filter(stage_id__title__icontains=value)
            | queryset.filter(stage_id__offboarding_id__title__icontains=value)
        ).distinct()

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Notice Period Starts/Ends used to
        each have their own single-direction fixed input (gte/lte on a
        different column each) -- replaced with the full
        gte/lte/gt/lt/exact set per field, plus Created At.
        """
        fields = [
            {
                "key": "notice_period_starts",
                "field": "notice_period_starts",
                "label": str(_("Notice Period Starts")),
                "type": "date_range",
            },
            {
                "key": "notice_period_ends",
                "field": "notice_period_ends",
                "label": str(_("Notice Period Ends")),
                "type": "date_range",
            },
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(_("Created At")),
                "type": "date_range",
            },
            {
                "key": "exit_reason_logged_at",
                "field": "exitreason__created_at",
                "label": str(_("Exit Reason Logged On")),
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


class LetterReGroup(FilterSet):
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("employee_id", "Employee"),
        ("planned_to_leave_on", "Planned to leave date"),
        ("status", "Status"),
        ("employee_id__employee_work_info__department_id", "Department"),
        ("employee_id__employee_work_info__job_position_id", "Job Position"),
        ("employee_id__employee_work_info__reporting_manager_id", "Reporting Manager"),
    ]

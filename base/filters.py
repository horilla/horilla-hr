"""
This module contains custom Django filters for filtering querysets related to Shift Requests,
Work Type Requests, Rotating Shift and Rotating Work Type Assign.
"""

import uuid

import django_filters
from django import forms
from django.db.models import Q, Value
from django.db.models.functions import Coalesce, Concat
from django.utils.translation import gettext as __
from django_filters import CharFilter, DateFilter, filters

from base.models import (
    Announcement,
    AnnouncementView,
    Company,
    CompanyLeaves,
    Department,
    DynamicEmailConfiguration,
    EmailLog,
    EmployeeShift,
    EmployeeShiftSchedule,
    EmployeeType,
    Holidays,
    JobPosition,
    JobRole,
    MultipleApprovalCondition,
    PenaltyAccounts,
    Roster,
    RotatingShift,
    RotatingShiftAssign,
    RotatingWorkType,
    RotatingWorkTypeAssign,
    ShiftRequest,
    WorkType,
    WorkTypeRequest,
)
from employee.models import Employee
from horilla.filters import (
    FilterSet,
    HorillaFilterSet,
    filter_by_name,
    filter_name_or_badge_terms,
)


class ShiftRequestFilter(HorillaFilterSet):
    """
    Custom filter for Shift Requests.
    """

    requested_date = django_filters.DateFilter(
        field_name="requested_date", widget=forms.DateInput(attrs={"type": "date"})
    )
    requested_date__gte = django_filters.DateFilter(
        field_name="requested_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    requested_date__lte = django_filters.DateFilter(
        field_name="requested_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    search = CharFilter(method=filter_by_name)

    status = django_filters.ChoiceFilter(
        method="filter_status",
        label=__("Status"),
        choices=[
            ("requested", __("Requested")),
            ("approved", __("Approved")),
            ("canceled", __("Canceled")),
        ],
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as EmployeeFilter.name_or_badge/AttendanceFilters.
    # name_or_badge; see horilla.filters.filter_name_or_badge_terms for
    # the shared matching logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=__("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation) -- every
    # model/queryset-backed field in the modern filter panel opts in here
    # instead of pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "employee_id": {
            "key": "shift-request-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": __("Search employee..."),
        },
        "shift_id": {
            "key": "shift-request-requested-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": __("Select shift..."),
        },
        "previous_shift_id": {
            "key": "shift-request-previous-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": __("Select shift..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "shift-request-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": __("Select job position..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "shift-request-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": __("Select department..."),
        },
        "employee_id__employee_work_info__work_type_id": {
            "key": "shift-request-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": __("Select work type..."),
        },
        "employee_id__employee_work_info__job_role_id": {
            "key": "shift-request-job-role",
            "queryset_fn": lambda request: JobRole.objects.select_related(
                "job_position_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_role", "job_position_id__job_position"],
            "placeholder": __("Select job role..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "shift-request-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": __("Search employee..."),
        },
        "employee_id__employee_work_info__company_id": {
            "key": "shift-request-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": __("Select company..."),
        },
        "employee_id__employee_work_info__shift_id": {
            "key": "shift-request-work-info-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": __("Select shift..."),
        },
    }

    class Meta:
        """
        A nested class that specifies the model and fields for the filter.
        """

        fields = "__all__"
        model = ShiftRequest
        fields = [
            "id",
            "employee_id",
            "requested_date",
            "previous_shift_id",
            "shift_id",
            "requested_till",
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__is_active",
            "employee_id__gender",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__work_type_id",
            "employee_id__employee_work_info__employee_type_id",
            "employee_id__employee_work_info__job_role_id",
            "employee_id__employee_work_info__reporting_manager_id",
            "employee_id__employee_work_info__company_id",
            "employee_id__employee_work_info__shift_id",
        ]

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = __(
            "e.g. John, PEP01, PEP02"
        )

    def filter_status(self, queryset, name, value):
        """
        Filters the queryset by combined status: requested, approved or canceled.
        """
        if value == "requested":
            return queryset.filter(approved=False, canceled=False)
        if value == "approved":
            return queryset.filter(approved=True, canceled=False)
        if value == "canceled":
            return queryset.filter(canceled=True)
        return queryset

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter/AttendanceFilters).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )


class WorkTypeRequestFilter(HorillaFilterSet):
    """
    Custom filter for Work Type Requests.
    """

    requested_date = django_filters.DateFilter(
        field_name="requested_date", widget=forms.DateInput(attrs={"type": "date"})
    )
    requested_date__gte = django_filters.DateFilter(
        field_name="requested_till",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    requested_date__lte = django_filters.DateFilter(
        field_name="requested_till",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    status = django_filters.ChoiceFilter(
        method="filter_status",
        label=__("Status"),
        choices=[
            ("requested", __("Requested")),
            ("approved", __("Approved")),
            ("canceled", __("Canceled")),
        ],
    )
    search = CharFilter(method=filter_by_name)
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as ShiftRequestFilter.name_or_badge; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=__("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation) -- every
    # model/queryset-backed field in the modern filter panel opts in here
    # instead of pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "employee_id": {
            "key": "work-type-request-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": __("Search employee..."),
        },
        "work_type_id": {
            "key": "work-type-request-requested-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": __("Select work type..."),
        },
        "previous_work_type_id": {
            "key": "work-type-request-previous-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": __("Select work type..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "work-type-request-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": __("Select job position..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "work-type-request-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": __("Select department..."),
        },
        "employee_id__employee_work_info__work_type_id": {
            "key": "work-type-request-work-info-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": __("Select work type..."),
        },
        "employee_id__employee_work_info__job_role_id": {
            "key": "work-type-request-job-role",
            "queryset_fn": lambda request: JobRole.objects.select_related(
                "job_position_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_role", "job_position_id__job_position"],
            "placeholder": __("Select job role..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "work-type-request-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": __("Search employee..."),
        },
        "employee_id__employee_work_info__company_id": {
            "key": "work-type-request-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": __("Select company..."),
        },
        "employee_id__employee_work_info__shift_id": {
            "key": "work-type-request-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": __("Select shift..."),
        },
    }

    class Meta:
        """
        A nested class that specifies the model and fields for the filter.
        """

        fields = "__all__"
        model = WorkTypeRequest
        fields = [
            "id",
            "employee_id",
            "requested_date",
            "previous_work_type_id",
            "work_type_id",
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__is_active",
            "employee_id__gender",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__work_type_id",
            "employee_id__employee_work_info__employee_type_id",
            "employee_id__employee_work_info__job_role_id",
            "employee_id__employee_work_info__reporting_manager_id",
            "employee_id__employee_work_info__company_id",
            "employee_id__employee_work_info__shift_id",
        ]

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = __(
            "e.g. John, PEP01, PEP02"
        )

    def filter_status(self, queryset, name, value):
        """
        Filters the queryset by combined status: requested, approved or canceled.
        """
        if value == "requested":
            return queryset.filter(approved=False, canceled=False)
        if value == "approved":
            return queryset.filter(approved=True, canceled=False)
        if value == "canceled":
            return queryset.filter(canceled=True)
        return queryset

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter/AttendanceFilters/
        ShiftRequestFilter).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )


class RotatingShiftAssignFilters(HorillaFilterSet):
    """
    Custom filter for Rotating Shift Assign.
    """

    search = CharFilter(method=filter_by_name)

    next_change_date = django_filters.DateFilter(
        field_name="next_change_date", widget=forms.DateInput(attrs={"type": "date"})
    )
    start_date = django_filters.DateFilter(
        field_name="start_date", widget=forms.DateInput(attrs={"type": "date"})
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as ShiftRequestFilter.name_or_badge; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=__("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation) -- every
    # model/queryset-backed field in the modern filter panel opts in here
    # instead of pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "employee_id": {
            "key": "rotating-shift-assign-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": __("Search employee..."),
        },
        "rotating_shift_id": {
            "key": "rotating-shift-assign-rotating-shift",
            "queryset_fn": lambda request: RotatingShift.objects.all(),
            "display_fn": lambda obj: obj.name,
            "search_fields": ["name"],
            "placeholder": __("Select rotating shift..."),
        },
        "current_shift": {
            "key": "rotating-shift-assign-current-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": __("Select shift..."),
        },
        "next_shift": {
            "key": "rotating-shift-assign-next-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": __("Select shift..."),
        },
        "employee_id__employee_work_info__company_id": {
            "key": "rotating-shift-assign-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": __("Select company..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "rotating-shift-assign-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": __("Select department..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "rotating-shift-assign-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": __("Select job position..."),
        },
        "employee_id__employee_work_info__job_role_id": {
            "key": "rotating-shift-assign-job-role",
            "queryset_fn": lambda request: JobRole.objects.select_related(
                "job_position_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_role", "job_position_id__job_position"],
            "placeholder": __("Select job role..."),
        },
        "employee_id__employee_work_info__work_type_id": {
            "key": "rotating-shift-assign-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": __("Select work type..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "rotating-shift-assign-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": __("Search employee..."),
        },
        "employee_id__employee_work_info__shift_id": {
            "key": "rotating-shift-assign-work-info-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": __("Select shift..."),
        },
    }

    class Meta:
        """
        A nested class that specifies the model and fields for the filter.
        """

        fields = "__all__"
        model = RotatingShiftAssign
        fields = [
            "employee_id",
            "rotating_shift_id",
            "next_change_date",
            "start_date",
            "based_on",
            "rotate_after_day",
            "rotate_every_weekend",
            "rotate_every",
            "current_shift",
            "next_shift",
            "is_active",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__work_type_id",
            "employee_id__employee_work_info__employee_type_id",
            "employee_id__employee_work_info__job_role_id",
            "employee_id__employee_work_info__reporting_manager_id",
            "employee_id__employee_work_info__company_id",
            "employee_id__employee_work_info__shift_id",
        ]

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = __(
            "e.g. John, PEP01, PEP02"
        )

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter/AttendanceFilters/
        ShiftRequestFilter).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )


class RotatingWorkTypeAssignFilter(HorillaFilterSet):
    """
    Custom filter for Rotating Work Type Assign.
    """

    search = CharFilter(method=filter_by_name)

    next_change_date = django_filters.DateFilter(
        field_name="next_change_date", widget=forms.DateInput(attrs={"type": "date"})
    )
    start_date = django_filters.DateFilter(
        field_name="start_date", widget=forms.DateInput(attrs={"type": "date"})
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as RotatingShiftAssignFilters.name_or_badge; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=__("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation) -- every
    # model/queryset-backed field in the modern filter panel opts in here
    # instead of pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "employee_id": {
            "key": "rotating-work-type-assign-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": __("Search employee..."),
        },
        "rotating_work_type_id": {
            "key": "rotating-work-type-assign-rotating-work-type",
            "queryset_fn": lambda request: RotatingWorkType.objects.all(),
            "display_fn": lambda obj: obj.name,
            "search_fields": ["name"],
            "placeholder": __("Select rotating work type..."),
        },
        "current_work_type": {
            "key": "rotating-work-type-assign-current-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": __("Select work type..."),
        },
        "next_work_type": {
            "key": "rotating-work-type-assign-next-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": __("Select work type..."),
        },
        "employee_id__employee_work_info__company_id": {
            "key": "rotating-work-type-assign-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": __("Select company..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "rotating-work-type-assign-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": __("Select department..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "rotating-work-type-assign-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": __("Select job position..."),
        },
        "employee_id__employee_work_info__job_role_id": {
            "key": "rotating-work-type-assign-job-role",
            "queryset_fn": lambda request: JobRole.objects.select_related(
                "job_position_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_role", "job_position_id__job_position"],
            "placeholder": __("Select job role..."),
        },
        "employee_id__employee_work_info__work_type_id": {
            "key": "rotating-work-type-assign-work-info-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": __("Select work type..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "rotating-work-type-assign-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": __("Search employee..."),
        },
        "employee_id__employee_work_info__shift_id": {
            "key": "rotating-work-type-assign-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": __("Select shift..."),
        },
    }

    class Meta:
        """
        A nested class that specifies the model and fields for the filter.
        """

        fields = "__all__"
        model = RotatingWorkTypeAssign
        fields = [
            "employee_id",
            "rotating_work_type_id",
            "next_change_date",
            "start_date",
            "based_on",
            "rotate_after_day",
            "rotate_every_weekend",
            "rotate_every",
            "current_work_type",
            "next_work_type",
            "is_active",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__work_type_id",
            "employee_id__employee_work_info__employee_type_id",
            "employee_id__employee_work_info__job_role_id",
            "employee_id__employee_work_info__reporting_manager_id",
            "employee_id__employee_work_info__company_id",
            "employee_id__employee_work_info__shift_id",
        ]

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = __(
            "e.g. John, PEP01, PEP02"
        )

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter/AttendanceFilters/
        ShiftRequestFilter/RotatingShiftAssignFilters).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )


class ShiftRequestReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("employee_id", "Employee"),
        ("shift_id", "Requested Shift"),
        ("previous_shift_id", "Current Shift"),
        ("requested_date", "Requested Date"),
    ]


class WorkTypeRequestReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("employee_id", "Employee"),
        ("work_type_id", "Requested Work Type"),
        ("previous_work_type_id", "Current Work Type"),
        ("requested_date", "Requested Date"),
        ("employee_id__employee_work_info__department_id", "Department"),
        ("employee_id__employee_work_info__job_position_id", "Job Position"),
        ("employee_id__employee_work_info__reporting_manager_id", "Reporting Manager"),
    ]


class RotatingWorkTypeRequestReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("employee_id", "Employee"),
        ("rotating_work_type_id", "Rotating Work Type"),
        ("current_work_type", "Current Work Type"),
        ("based_on", "Based On"),
        ("employee_id__employee_work_info__department_id", "Department"),
        ("employee_id__employee_work_info__job_role_id", "Job Role"),
        ("employee_id__employee_work_info__reporting_manager_id", "Reporting Manager"),
    ]


class RotatingShiftRequestReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", "Select"),
        ("employee_id", "Employee"),
        ("rotating_shift_id", "Rotating Shift"),
        ("based_on", "Based On"),
        ("employee_id__employee_work_info__department_id", "Department"),
        ("employee_id__employee_work_info__job_role_id", "Job Role"),
        ("employee_id__employee_work_info__reporting_manager_id", "Reporting Manager"),
    ]


class MultipleApprovalConditionFilter(HorillaFilterSet):

    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = MultipleApprovalCondition
        fields = [
            "department",
        ]

    def search_method(self, queryset, _, value):
        """
        This method is used to search department
        """

        return (queryset.filter(department__department__icontains=value)).distinct()


class EmployeeShiftFilter(FilterSet):

    search = django_filters.CharFilter(
        field_name="employee_shift", lookup_expr="icontains"
    )

    class Meta:
        model = EmployeeShift
        fields = [
            "employee_shift",
        ]


class EmployeeShiftScheduleFilter(FilterSet):

    search = django_filters.CharFilter(field_name="day__day", lookup_expr="icontains")

    class Meta:
        model = EmployeeShiftSchedule
        fields = []


class RotatingShiftFilter(HorillaFilterSet):

    # search = django_filters.CharFilter(
    #     field_name="name", lookup_expr="icontains"
    # )
    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = RotatingShift
        fields = ["name", "shift1", "shift2"]

    def search_method(self, queryset, _, value):
        """
        This method is used to search employees and objective
        """

        return (
            queryset.filter(name__icontains=value)
            | queryset.filter(shift1__employee_shift__icontains=value)
            | queryset.filter(shift2__employee_shift__icontains=value)
        ).distinct()


class DepartmentViewFilter(HorillaFilterSet):
    search = django_filters.CharFilter(method="filter_by_all_fields")

    class Meta:
        model = Department
        fields = [
            "department",
        ]

    def filter_by_all_fields(self, queryset, name, value):
        return queryset.filter(
            Q(department__icontains=value)
            | Q(job_position__job_position__icontains=value)
        ).distinct()


class WorkTypeFilter(HorillaFilterSet):

    search = django_filters.CharFilter(field_name="work_type", lookup_expr="icontains")

    class Meta:
        model = WorkType
        fields = [
            "work_type",
        ]


class RotatingWorkTypeFilter(HorillaFilterSet):

    search = django_filters.CharFilter(method="search_method")

    def search_method(self, queryset, _, value):
        """
        This method is used to search employees and objective
        """

        return (
            queryset.filter(name__icontains=value)
            | queryset.filter(work_type1__work_type__icontains=value)
            | queryset.filter(work_type2__work_type__icontains=value)
        ).distinct()

    class Meta:
        model = RotatingWorkType
        fields = ["name", "work_type1", "work_type2"]


class EmployeeTypeFilter(FilterSet):

    search = django_filters.CharFilter(
        field_name="employee_type", lookup_expr="icontains"
    )

    class Meta:
        model = EmployeeType
        fields = [
            "employee_type",
        ]


class JobRoleFilter(HorillaFilterSet):
    search = django_filters.CharFilter(method="filter_by_all_fields")

    class Meta:
        model = JobPosition
        fields = [
            "job_position",
        ]

    def filter_by_all_fields(self, queryset, name, value):
        return queryset.filter(
            Q(job_position__icontains=value) | Q(jobrole__job_role__icontains=value)
        ).distinct()


class CompanyFilter(FilterSet):

    search = CharFilter(method="search_method")

    def search_method(self, queryset, _, value):
        """
        This method is used to search company and objective
        """

        return (
            queryset.filter(company__icontains=value)
            | queryset.filter(hq__icontains=value)
            | queryset.filter(address__icontains=value)
            | queryset.filter(country__icontains=value)
            | queryset.filter(state__icontains=value)
            | queryset.filter(city__icontains=value)
            | queryset.filter(zip__icontains=value)
        ).distinct()

    class Meta:
        model = Company
        fields = ["company", "hq", "address", "country", "state", "city", "zip"]


class MailServerFilter(HorillaFilterSet):

    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = DynamicEmailConfiguration
        fields = ["username"]

    def search_method(self, queryset, _, value):
        """
        This method is used to mail server
        """

        return ((queryset.filter(username__icontains=value))).distinct()


class HolidayFilter(HorillaFilterSet):
    """
    Filter class for Holidays model.

    This filter allows searching Holidays objects based on name and date range.
    """

    search = filters.CharFilter(field_name="name", lookup_expr="icontains")
    from_date = DateFilter(
        field_name="start_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    to_date = DateFilter(
        field_name="end_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        """
        Meta class defines the model and fields to filter
        """

        model = Holidays
        fields = {
            "recurring": ["exact"],
        }

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"
        self.form.fields["from_date"].label = (
            f"{self.Meta.model()._meta.get_field('start_date').verbose_name} From"
        )
        self.form.fields["to_date"].label = (
            f"{self.Meta.model()._meta.get_field('end_date').verbose_name} Till"
        )

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Start Date/End Date used to each
        have their own single-direction fixed input (from_date's gte on
        start_date, to_date's lte on end_date) -- replaced with the
        full gte/lte/gt/lt/exact set per field, plus Created At.
        """
        fields = [
            {
                "key": "start_date",
                "field": "start_date",
                "label": str(__("Start Date")),
                "type": "date_range",
            },
            {
                "key": "end_date",
                "field": "end_date",
                "label": str(__("End Date")),
                "type": "date_range",
            },
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(__("Created At")),
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


class CompanyLeaveFilter(HorillaFilterSet):
    """
    Filter class for CompanyLeaves model.

    This filter allows searching CompanyLeaves objects based on
    name, week day and based_on_week choices.
    """

    name = filters.CharFilter(field_name="based_on_week_day", lookup_expr="icontains")
    search = filters.CharFilter(method="filter_week_day")

    class Meta:
        """ "
        Meta class defines the model and fields to filter
        """

        model = CompanyLeaves
        fields = {
            "based_on_week": ["exact"],
            "based_on_week_day": ["exact"],
        }

    def filter_week_day(self, queryset, _, value):
        week_qry = CompanyLeaves.objects.none()
        weekday_values = []
        week_values = []
        WEEK_DAYS = [
            ("0", __("Monday")),
            ("1", __("Tuesday")),
            ("2", __("Wednesday")),
            ("3", __("Thursday")),
            ("4", __("Friday")),
            ("5", __("Saturday")),
            ("6", __("Sunday")),
        ]
        WEEKS = [
            (None, __("All")),
            ("0", __("First Week")),
            ("1", __("Second Week")),
            ("2", __("Third Week")),
            ("3", __("Fourth Week")),
            ("4", __("Fifth Week")),
        ]

        for day_value, day_name in WEEK_DAYS:
            if value.lower() in day_name.lower():
                weekday_values.append(day_value)
        for day_value, day_name in WEEKS:
            if value.lower() in day_name.lower() and value.lower() != __("All").lower():
                week_values.append(day_value)
                week_qry = queryset.filter(based_on_week__in=week_values)
            elif value.lower() in __("All").lower():
                week_qry = queryset.filter(based_on_week__isnull=True)
        return queryset.filter(based_on_week_day__in=weekday_values) | week_qry


class PenaltyFilter(FilterSet):
    """
    PenaltyFilter
    """

    class Meta:
        model = PenaltyAccounts
        fields = "__all__"


class MailLogFilter(HorillaFilterSet):

    search = django_filters.CharFilter(field_name="subject", lookup_expr="icontains")

    class Meta:
        model = EmailLog
        fields = "__all__"


class AnnouncementFilter(HorillaFilterSet):

    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")

    class Meta:
        model = Announcement
        fields = "__all__"


class AnnouncementViewFilter(HorillaFilterSet):

    search = django_filters.CharFilter(
        field_name="announcement", lookup_expr="icontains"
    )

    class Meta:
        model = AnnouncementView
        fields = "__all__"


# ---------------------------------------------------------------------------
# Roster Filter
# ---------------------------------------------------------------------------


class RosterFilter(HorillaFilterSet):
    """
    Filters the Roster queryset by employee, department, and date range.
    """

    employee = django_filters.ModelMultipleChoiceFilter(
        queryset=Employee.objects.filter(is_active=True),
        label=__("Employee"),
    )
    # queryset=Department.objects.all() directly (not deferred to
    # queryset=None + a real assignment in __init__ like the pre-modern
    # version of this field did) -- HorillaFilterSet.__init__ calls
    # reload_queryset() on every ModelChoiceField before __init__'s own
    # body gets a chance to run, and that reads field.queryset.model
    # unconditionally, crashing on a still-None queryset. A plain
    # .all() here is lazy (no query runs at class-definition/import
    # time), same as every other ajax_fields queryset_fn in this file.
    department = django_filters.ModelChoiceFilter(
        queryset=Department.objects.all(),
        label=__("Department"),
        widget=forms.Select(attrs={"class": "oh-select oh-select-2 w-100"}),
    )
    from_date = django_filters.DateFilter(
        field_name="date",
        lookup_expr="gte",
        label=__("From Date"),
        widget=forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
    )
    to_date = django_filters.DateFilter(
        field_name="date",
        lookup_expr="lte",
        label=__("To Date"),
        widget=forms.DateInput(attrs={"type": "date", "class": "oh-input w-100"}),
    )
    # NOT the shared horilla.filters.filter_by_name -- that helper assumes
    # an "employee_id"-named FK (Coalesce("employee_id__employee_first_
    # name", ...)), but Roster's own FK field is named "employee" (see
    # base/models.py), so that lookup path doesn't resolve on this model
    # at all -- using it here raised a FieldError the moment this field
    # actually had a value (the "search" box every inline_nav.html-based
    # page already has). filter_search below is the same name-only
    # matching logic, just pointed at the correct field path.
    search = django_filters.CharFilter(method="filter_search")
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee picker above rather than instead of it -- same
    # field/behavior as EmployeeFilter.name_or_badge/AttendanceFilters.
    # name_or_badge; see horilla.filters.filter_name_or_badge_terms for
    # the shared matching logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=__("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation).
    ajax_fields = {
        "employee": {
            "key": "roster-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": __("Search employee..."),
        },
        "department": {
            "key": "roster-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": __("Select department..."),
        },
    }

    class Meta:
        model = Roster
        fields = ["employee", "department", "from_date", "to_date"]

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = __(
            "e.g. John, PEP01, PEP02"
        )

    def filter_search(self, queryset, name, value):
        """
        Name-only search box (inline_nav.html's own "search" field) --
        see this field's own comment above for why it can't reuse the
        shared horilla.filters.filter_by_name.
        """
        value = " ".join(value.split())
        queryset = queryset.annotate(
            full_name=Concat(
                Coalesce("employee__employee_first_name", Value("")),
                Value(" "),
                Coalesce("employee__employee_last_name", Value("")),
            )
        )
        return queryset.filter(full_name__icontains=value)

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter/AttendanceFilters).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee__employee_first_name",
            "employee__employee_last_name",
            "employee__badge_id",
        )

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Date's existing from_date/to_date
        gte/lte pair (labeled "Date Range" above) stays in place for the
        common case; this adds the full gte/lte/gt/lt/exact set for it,
        plus Created At.
        """
        fields = [
            {
                "key": "date",
                "field": "date",
                "label": str(__("Date")),
                "type": "date_range",
            },
            {
                "key": "created_at",
                "field": "created_at",
                "label": str(__("Created At")),
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

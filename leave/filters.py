"""
This module contains custom filter classes used for filtering
various models in the Leave Management System app.
The filters are designed to provide flexible search and filtering
capabilities for LeaveType, LeaveRequest and AvailableLeave models.
"""

import uuid
from datetime import datetime, timedelta

import django_filters
from django import forms
from django.apps import apps
from django.db.models import Q, Value
from django.db.models.functions import Coalesce, Concat, TruncYear
from django.utils.timezone import now
from django.utils.translation import gettext as __
from django.utils.translation import gettext_lazy as _
from django_filters import DateFilter, NumberFilter, filters

from base.models import (
    Company,
    Department,
    EmployeeShift,
    EmployeeType,
    JobPosition,
    JobRole,
    WorkType,
)
from employee.models import Employee
from horilla.filters import (
    FilterSet,
    HorillaFilterSet,
    filter_by_name,
    filter_name_or_badge_terms,
)
from horilla_views.templatetags.generic_template_filters import getattribute

from .models import (
    AvailableLeave,
    LeaveAllocationRequest,
    LeaveRequest,
    LeaveType,
    RestrictLeave,
)


class LeaveTypeFilter(HorillaFilterSet):
    """
    Filter class for LeaveType model.

    This filter allows searching LeaveType objects based on their name and payment attributes.
    """

    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    search = filters.CharFilter(field_name="name", lookup_expr="icontains")
    carry_forward_gte = filters.CharFilter(
        field_name="carryforward_max", lookup_expr="gte"
    )
    carry_forward_lte = filters.CharFilter(
        field_name="carryforward_max", lookup_expr="lte"
    )
    total_days_gte = filters.CharFilter(field_name="total_days", lookup_expr="gte")
    total_days_lte = filters.CharFilter(field_name="total_days", lookup_expr="lte")

    class Meta:
        """ "
        Meta class defines the model and fields to filter
        """

        model = LeaveType
        fields = "__all__"
        exclude = ["icon"]


class AssignedLeaveFilter(HorillaFilterSet):
    """
    Filter class for AvailableLeave model.

    This filter allows searching AvailableLeave objects based on leave type,
    employee, assigned date and payment attributes.
    """

    # leave_type = filters.CharFilter(
    #     field_name="leave_type_id__name", lookup_expr="icontains"
    # )
    search = filters.CharFilter(method=filter_by_name)
    employee_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Employee.objects.all(),
        widget=forms.SelectMultiple(),
    )
    assigned_date = DateFilter(
        field_name="assigned_date",
        lookup_expr="exact",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as LeaveRequestFilter.name_or_badge; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see LeaveRequestFilter.ajax_fields for the full explanation).
    ajax_fields = {
        "employee_id": {
            "key": "assigned-leave-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "leave_type_id": {
            "key": "assigned-leave-leave-type",
            "queryset_fn": lambda request: LeaveType.objects.all(),
            "display_fn": lambda obj: obj.name,
            "search_fields": ["name"],
            "placeholder": _("Select leave type..."),
        },
    }
    available_days__gte = NumberFilter(field_name="available_days", lookup_expr="gte")
    available_days__lte = NumberFilter(field_name="available_days", lookup_expr="lte")
    carryforward_days__gte = NumberFilter(
        field_name="carryforward_days", lookup_expr="gte"
    )
    carryforward_days__lte = NumberFilter(
        field_name="carryforward_days", lookup_expr="lte"
    )
    total_leave_days__gte = NumberFilter(
        field_name="total_leave_days", lookup_expr="gte"
    )
    total_leave_days__lte = NumberFilter(
        field_name="total_leave_days", lookup_expr="lte"
    )

    class Meta:
        """ "
        Meta class defines the model and fields to filter
        """

        model = AvailableLeave
        fields = [
            "employee_id",
            "leave_type_id",
            "available_days",
            "available_days__gte",
            "available_days__lte",
            "carryforward_days",
            "carryforward_days__gte",
            "carryforward_days__lte",
            "total_leave_days",
            "total_leave_days__gte",
            "total_leave_days__lte",
            "assigned_date",
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

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )


class LeaveRequestFilter(HorillaFilterSet):
    """
    Filter class for LeaveRequest model.
    This filter allows searching LeaveRequest objects
    based on employee,date range, leave type, and status.
    """

    search = django_filters.CharFilter(method="filter_by_name")
    search_field = django_filters.CharFilter(method="search_in")
    today_leave = django_filters.BooleanFilter(method="filter_today_leave")
    overall_leave = django_filters.CharFilter(method="overall_leave_filter")
    from_date = DateFilter(
        method="filter_from_date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    to_date = DateFilter(
        field_name="start_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    # start_date = DateFilter(
    #     field_name="start_date",
    #     lookup_expr="exact",
    #     widget=forms.DateInput(attrs={"type": "date"}),
    # )

    # end_date = DateFilter(
    #     field_name="end_date",
    #     lookup_expr="exact",
    #     widget=forms.DateInput(attrs={"type": "date"}),
    # )
    start_date_gte = DateFilter(
        field_name="start_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    department_name = django_filters.CharFilter(
        field_name="employee_id__employee_work_info__department_id__department",
        lookup_expr="icontains",
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as EmployeeFilter.name_or_badge/AttendanceFilters.
    # name_or_badge; see horilla.filters.filter_name_or_badge_terms for the
    # shared matching logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation) -- every
    # model/queryset-backed field in the modern filter panel opts in here
    # instead of pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "employee_id": {
            "key": "leave-request-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__company_id": {
            "key": "leave-request-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": _("Select company..."),
        },
        "employee_id__employee_work_info__employee_type_id": {
            "key": "leave-request-employee-type",
            "queryset_fn": lambda request: EmployeeType.objects.all(),
            "display_fn": lambda obj: obj.employee_type,
            "search_fields": ["employee_type"],
            "placeholder": _("Select employee type..."),
        },
        "employee_id__employee_work_info__job_role_id": {
            "key": "leave-request-job-role",
            "queryset_fn": lambda request: JobRole.objects.select_related(
                "job_position_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_role", "job_position_id__job_position"],
            "placeholder": _("Select job role..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "leave-request-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "leave-request-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "leave-request-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "employee_id__employee_work_info__shift_id": {
            "key": "leave-request-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": _("Select shift..."),
        },
        "employee_id__employee_work_info__work_type_id": {
            "key": "leave-request-work-type",
            "queryset_fn": lambda request: WorkType.objects.all(),
            "display_fn": lambda obj: obj.work_type,
            "search_fields": ["work_type"],
            "placeholder": _("Select work type..."),
        },
    }

    class Meta:
        """ "
        Meta class defines the model and fields to filter
        """

        model = LeaveRequest
        fields = [
            "id",
            "employee_id",
            "leave_type_id",
            "status",
            "department_name",
            "overall_leave",
            "employee_id__employee_work_info__company_id",
            "employee_id__employee_work_info__employee_type_id",
            "employee_id__employee_work_info__job_role_id",
            "employee_id__employee_work_info__reporting_manager_id",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__shift_id",
            "employee_id__employee_work_info__work_type_id",
        ]

    def overall_leave_filter(self, queryset, _, value):
        """
        Overall leave custom filter method
        """
        today = datetime.today()

        today_leave_requests = queryset.filter(
            Q(start_date__lte=today) & Q(end_date__gte=today) & Q(status="approved")
        )
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        weekly_leave_requests = queryset.filter(
            status="approved", start_date__lte=end_of_week, end_date__gte=start_of_week
        )
        start_of_month = today.replace(day=1)
        end_of_month = start_of_month.replace(day=28) + timedelta(days=4)
        if end_of_month.month != today.month:
            end_of_month = end_of_month - timedelta(days=end_of_month.day)
        monthly_leave_requests = queryset.filter(
            status="approved",
            start_date__lte=end_of_month,
            end_date__gte=start_of_month,
        )
        start_of_year = today.replace(month=1, day=1)
        end_of_year = today.replace(month=12, day=31)
        yearly_leave_requests = (
            queryset.filter(
                status="approved",
                start_date__lte=end_of_year,
                end_date__gte=start_of_year,
            )
            .annotate(year=TruncYear("start_date"))
            .filter(year=start_of_year)
        )
        if value == "month":
            queryset = monthly_leave_requests
        elif value == "week":
            queryset = weekly_leave_requests
        elif value == "year":
            queryset = yearly_leave_requests
        else:
            queryset = today_leave_requests
        return queryset

    def filter_today_leave(self, queryset, name, value):
        if value:
            today = now().date()
            return queryset.filter(start_date__lte=today).filter(
                Q(end_date__gte=today) | Q(end_date__isnull=True, start_date=today)
            )
        return queryset

    def filter_from_date(self, queryset, name, value):
        # end_date >= value, or for single-day leaves (end_date null) start_date >= value
        return queryset.filter(
            Q(end_date__gte=value) | Q(end_date__isnull=True, start_date__gte=value)
        )

    def filter_by_name(self, queryset, name, value):

        if self.data.get("search_field"):
            return queryset
        # Call the imported function
        filter_method = {
            "leave_type_id": "leave_type_id__name__icontains",
            "status": "status__icontains",
            "employee_id__employee_work_info__department_id": "employee_id__employee_work_info__department_id__department__icontains",
            "employee_id__employee_work_info__job_position_id__": "employee_id__employee_work_info__job_position_id__job_position__icontains",
            "employee_id__employee_work_info__company_id": "employee_id__employee_work_info__company_id__company__icontains",
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
        return queryset

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter and AttendanceFilters).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Start Date/End Date are deliberately
        NOT duplicated here: from_date/to_date above already cover them
        with bespoke overlap-aware logic (filter_from_date treats a
        null end_date as an open-ended single-day leave), which a plain
        field__lookup builder entry can't reproduce. Created At is a
        plain DateTimeField column with no such nuance, so it's safe as
        a straightforward addition.
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

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )


class UserLeaveRequestFilter(FilterSet):
    """
    Filter class for LeaveRequest model specific to user leave requests.
    This filter allows searching user-specific LeaveRequest objects
    based on leave type, date range, and status.
    """

    search = filters.CharFilter(
        field_name="leave_type_id__name", lookup_expr="icontains"
    )
    leave_type = filters.CharFilter(
        field_name="leave_type_id__name", lookup_expr="icontains"
    )
    from_date = DateFilter(
        field_name="end_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    to_date = DateFilter(
        field_name="start_date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    start_date_gte = DateFilter(
        field_name="start_date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        """
        Meta class defines the model and fields to filter
        """

        model = LeaveRequest
        fields = {
            "leave_type_id": ["exact"],
            "status": ["exact"],
        }

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        from horilla.horilla_middlewares import _thread_locals

        request = getattr(_thread_locals, "request", None)
        leave_requests = request.user.employee_get.leaverequest_set.all()
        assigned_leave_types = LeaveType.objects.filter(
            id__in=leave_requests.values_list("leave_type_id", flat=True)
        )
        self.form.fields["leave_type_id"].queryset = assigned_leave_types


class LeaveAllocationRequestFilter(HorillaFilterSet):
    """
    Filter class for LeaveAllocationRequest model specific to user leave requests.
    This filter allows searching user-specific LeaveRequest objects
    based on leave type, date range, and status.
    """

    id = django_filters.NumberFilter(field_name="id")

    leave_type = filters.CharFilter(
        field_name="leave_type_id__name", lookup_expr="icontains"
    )
    search = filters.CharFilter(method=filter_by_name)
    number_of_days_up_to = filters.NumberFilter(
        field_name="requested_days", lookup_expr="lte"
    )
    number_of_days_more_than = filters.NumberFilter(
        field_name="requested_days", lookup_expr="gte"
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as LeaveRequestFilter.name_or_badge; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )
    # created_by is a FK to HorillaUser, not Employee -- rendering/
    # filtering on it directly (Meta.fields's own auto-generated
    # ModelChoiceFilter) surfaced raw usernames/emails ("admin",
    # "michael.brown@horilla.com", ...) in the picker instead of the
    # employee's name, since a HorillaUser has no display-friendly
    # __str__ of its own. Overrides that auto field with one that goes
    # through the User -> Employee reverse OneToOne instead
    # (Employee.employee_user_id's related_name="employee_get", see
    # employee/models.py) -- picks an Employee, filters via
    # created_by__employee_get, same UX as employee_id above.
    created_by = django_filters.ModelMultipleChoiceFilter(
        field_name="created_by__employee_get",
        queryset=Employee.objects.filter(employee_user_id__isnull=False),
        label=_("Created By"),
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see EmployeeFilter.ajax_fields for the full explanation).
    ajax_fields = {
        "employee_id": {
            "key": "leave-allocation-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "created_by": {
            "key": "leave-allocation-created-by",
            "queryset_fn": lambda request: Employee.objects.filter(
                employee_user_id__isnull=False
            ),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    class Meta:
        """
        Meta class defines the model and fields to filter
        """

        model = LeaveAllocationRequest
        fields = {
            "id": ["exact"],
            "created_by": ["exact"],
            "status": ["exact"],
            "leave_type_id": ["exact"],
            "employee_id": ["exact"],
        }

    def filter_name_or_badge(self, queryset, name, value):
        """
        Filter panel's dedicated "Name or Badge ID" field (see
        name_or_badge above) -- see horilla.filters.
        filter_name_or_badge_terms for the shared comma-separated
        matching logic (also used by EmployeeFilter/AttendanceFilters/
        LeaveRequestFilter).
        """
        return filter_name_or_badge_terms(
            queryset,
            value,
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__badge_id",
        )

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Requested Date and Created At are
        plain DateField/DateTimeField columns, so the plain
        field+lookup shape applies directly.
        """
        fields = [
            {
                "key": "requested_date",
                "field": "requested_date",
                "label": str(_("Requested Date")),
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

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )


class LeaveRequestReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", _("Select")),
        ("employee_id", _("Employee")),
        ("leave_type_id", _("Leave Type")),
        ("start_date", _("Start Date")),
        ("status", _("Status")),
        ("requested_days", _("Requested Days")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employment Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


class MyLeaveRequestReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", _("Select")),
        ("leave_type_id", _("Leave Type")),
        ("status", _("Status")),
        ("requested_days", _("Requested Days")),
    ]


class LeaveAssignReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", _("Select")),
        ("employee_id", _("Employee")),
        ("leave_type_id", _("Leave Type")),
        ("available_days", _("Available Days")),
        ("carryforward_days", _("Carry Forward Days")),
        ("total_leave_days", _("Total Leave Days Days")),
        ("assigned_date", _("Assigned Date")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employment Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


class LeaveAllocationRequestReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", _("Select")),
        ("employee_id", _("Employee")),
        ("leave_type_id", _("Leave Type")),
        ("status", _("Status")),
        ("requested_days", _("Requested Days")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__employee_type_id", _("Employment Type")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


class RestrictLeaveFilter(HorillaFilterSet):
    """
    Filter class for Restrict model.

    This filter allows searching Restrictleave objects based on name and date range.
    """

    search = filters.CharFilter(field_name="title", lookup_expr="icontains")
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

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism,
    # see LeaveRequestFilter.ajax_fields for the full explanation). No
    # employee field exists on this model, so there's no "Name or Badge
    # ID" search here -- unlike the other modernized panels this session.
    ajax_fields = {
        "department": {
            "key": "restrict-leave-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "job_position": {
            "key": "restrict-leave-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
    }

    class Meta:
        """
        Meta class defines the model and fields to filter
        """

        model = RestrictLeave
        fields = "__all__"

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
                "label": str(_("Start Date")),
                "type": "date_range",
            },
            {
                "key": "end_date",
                "field": "end_date",
                "label": str(_("End Date")),
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

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"


if apps.is_installed("attendance"):
    from .models import CompensatoryLeaveRequest

    class CompensatoryLeaveRequestFilter(FilterSet):
        """
        Filter class for CompensatoryLeaveRequest model specific to user leave requests.
        This filter allows searching user-specific LeaveRequest objects
        based on leave type, date range, and status.
        """

        id = django_filters.NumberFilter(field_name="id")

        leave_type = filters.CharFilter(
            field_name="leave_type_id__name", lookup_expr="icontains"
        )
        search = filters.CharFilter(method="filter_by_name")
        created_by__employee_get = django_filters.ModelMultipleChoiceFilter(
            field_name="created_by__employee_get",
            queryset=Employee.objects.all(),
            widget=forms.SelectMultiple(),
        )
        number_of_days_up_to = filters.NumberFilter(
            field_name="requested_days", lookup_expr="lte"
        )
        number_of_days_more_than = filters.NumberFilter(
            field_name="requested_days", lookup_expr="gte"
        )

        class Meta:
            """
            Meta class defines the model and fields to filter
            """

            model = CompensatoryLeaveRequest
            fields = {
                "id": ["exact"],
                "created_by__employee_get": ["exact"],
                "status": ["exact"],
                "leave_type_id": ["exact"],
                "employee_id": ["exact"],
            }

        def filter_by_name(self, queryset, name, value):
            # Call the imported function
            filter_method = {
                "leave_type": "leave_type_id__name__icontains",
                "status": "status__icontains",
                "department": "employee_id__employee_work_info__department_id__department__icontains",
                "job_position": "employee_id__employee_work_info__job_position_id__job_position__icontains",
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

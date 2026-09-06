"""
Module containing filter set classes for payroll models.

This module defines the filter set classes used for filtering data in the payroll app.
Each filter set class corresponds to a specific model and contains filter fields and methods
to customize the filtering behavior.

"""

import uuid

import django_filters
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from base.filters import FilterSet
from base.models import (
    Company,
    Department,
    EmployeeShift,
    JobPosition,
    JobRole,
    WorkType,
)
from employee.models import Employee
from horilla.filters import HorillaFilterSet, filter_by_name, filter_name_or_badge_terms
from payroll.models.models import (
    Allowance,
    Contract,
    Deduction,
    FilingStatus,
    LoanAccount,
    Payslip,
    PayslipAutoGenerate,
    Reimbursement,
    SalaryStructure,
)
from payroll.models.tax_models import TaxBracket


class ContractFilter(HorillaFilterSet):
    """
    Filter set class for Contract model

    Args:
        FilterSet (class): custom filter set class to apply styling
    """

    search = django_filters.CharFilter(method="filter_by_contract")
    contract_start_date_from = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
        field_name="contract_start_date",
        lookup_expr="gte",
    )
    contract_start_date_till = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
        field_name="contract_start_date",
        lookup_expr="lte",
    )
    contract_end_date_from = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
        field_name="contract_end_date",
        lookup_expr="gte",
    )
    contract_end_date_till = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
        field_name="contract_end_date",
        lookup_expr="lte",
    )
    basic_pay__lte = django_filters.NumberFilter(field_name="wage", lookup_expr="lte")
    basic_pay__gte = django_filters.NumberFilter(field_name="wage", lookup_expr="gte")
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as every other modernized panel this session; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- every model/queryset-backed field in the modern filter panel opts
    # in here instead of pre-rendering its whole queryset as <option> tags.
    # Note: department/job_position/job_role/shift/work_type are FK fields
    # declared directly on the Contract model itself (not traversed via
    # employee_id__employee_work_info__...), unlike most other filters in
    # this rollout.
    ajax_fields = {
        "employee_id": {
            "key": "contract-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__company_id": {
            "key": "contract-company",
            "queryset_fn": lambda request: Company.objects.all(),
            "display_fn": lambda obj: obj.company,
            "search_fields": ["company"],
            "placeholder": _("Select company..."),
        },
        "department": {
            "key": "contract-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "job_position": {
            "key": "contract-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "job_role": {
            "key": "contract-job-role",
            "queryset_fn": lambda request: JobRole.objects.select_related(
                "job_position_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_role", "job_position_id__job_position"],
            "placeholder": _("Select job role..."),
        },
        "shift": {
            "key": "contract-shift",
            "queryset_fn": lambda request: EmployeeShift.objects.all(),
            "display_fn": lambda obj: obj.employee_shift,
            "search_fields": ["employee_shift"],
            "placeholder": _("Select shift..."),
        },
        "work_type": {
            "key": "contract-work-type",
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

        model = Contract
        fields = [
            "employee_id",
            "contract_name",
            "wage_type",
            "filing_status",
            "employee_id__employee_work_info__company_id",
            "department",
            "job_position",
            "job_role",
            "shift",
            "work_type",
            "pay_frequency",
            "contract_status",
            "wage",
        ]

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        for field in self.form.fields.keys():
            self.form.fields[field].widget.attrs["id"] = f"{uuid.uuid4()}"
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )

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

    def filter_by_contract(self, queryset, _, value):
        """
        Filter queryset by first name or last name.
        """
        # Split the search value into first name and last name
        parts = value.split()
        first_name = parts[0]
        og_queryset = queryset
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        # Filter the queryset by first name and last name
        if first_name and last_name:
            queryset = queryset.filter(
                employee_id__employee_first_name__icontains=first_name,
                employee_id__employee_last_name__icontains=last_name,
            )
        elif first_name:
            queryset = queryset.filter(
                employee_id__employee_first_name__icontains=first_name
            )
        elif last_name:
            queryset = queryset.filter(
                employee_id__employee_last_name__icontains=last_name
            )
        queryset = queryset | og_queryset.filter(contract_name__icontains=value)
        return queryset


class AllowanceFilter(HorillaFilterSet):
    """
    Filter set class for Allowance model.
    """

    search = django_filters.CharFilter(method="filter_by_employee")

    class Meta:
        """
        Meta class to add additional options
        """

        model = Allowance
        fields = [
            "title",
            "is_taxable",
            "is_condition_based",
            "is_fixed",
            "based_on",
            "amount",
        ]

    def filter_by_employee(self, queryset, _, value):
        """
        Filter queryset by first name or last name.
        """
        # Split the search value into first name and last name
        parts = value.split()
        first_name = parts[0]
        og_queryset = queryset
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        # Filter the queryset by first name and last name
        if first_name and last_name:
            queryset = queryset.filter(
                specific_employees__employee_first_name__icontains=first_name,
                specific_employees__employee_last_name__icontains=last_name,
            )
        elif first_name:
            queryset = queryset.filter(
                specific_employees__employee_first_name__icontains=first_name
            )
        elif last_name:
            queryset = queryset.filter(
                specific_employees__employee_last_name__icontains=last_name
            )
        queryset = queryset | og_queryset.filter(title__icontains=value)
        return queryset.distinct()

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


class DeductionFilter(HorillaFilterSet):
    """
    Filter set class for Deduction model.
    """

    search = django_filters.CharFilter(method="filter_by_employee")

    class Meta:
        """
        Meta class to add additional options
        """

        model = Deduction
        fields = [
            "title",
            "is_pretax",
            "is_condition_based",
            "is_fixed",
            "based_on",
            "amount",
        ]

    def filter_by_employee(self, queryset, _, value):
        """
        Filter queryset by first name or last name.
        """
        # Split the search value into first name and last name
        parts = value.split()
        first_name = parts[0]
        og_queryset = queryset
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        # Filter the queryset by first name and last name
        if first_name and last_name:
            queryset = queryset.filter(
                specific_employees__employee_first_name__icontains=first_name,
                specific_employees__employee_last_name__icontains=last_name,
            )
        elif first_name:
            queryset = queryset.filter(
                specific_employees__employee_first_name__icontains=first_name
            )
        elif last_name:
            queryset = queryset.filter(
                specific_employees__employee_last_name__icontains=last_name
            )
        queryset = queryset | og_queryset.filter(title__icontains=value)
        return queryset.distinct()

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


class SalaryStructureFilter(HorillaFilterSet):
    """
    Filter set class for SalaryStructure model.
    """

    search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")

    class Meta:
        """
        Meta class to add additional options
        """

        model = SalaryStructure
        fields = ["title"]


class PayslipFilter(HorillaFilterSet):
    """
    Filter set class for payslip model.
    """

    search = django_filters.CharFilter(method=filter_by_name)
    employee_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Employee.objects.all(),
        widget=forms.SelectMultiple(),
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as every other modernized panel this session; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- Employee is opted into an AJAX-searched combobox instead of a
    # pre-rendered <option> list.
    ajax_fields = {
        "employee_id": {
            "key": "payslip-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    start_date_from = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
        field_name="start_date",
        lookup_expr="gte",
    )
    start_date_till = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
        field_name="start_date",
        lookup_expr="lte",
    )
    end_date_from = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
        field_name="end_date",
        lookup_expr="gte",
    )
    end_date_till = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
        field_name="end_date",
        lookup_expr="lte",
    )
    gross_pay__lte = django_filters.NumberFilter(
        field_name="gross_pay", lookup_expr="lte"
    )
    gross_pay__gte = django_filters.NumberFilter(
        field_name="gross_pay", lookup_expr="gte"
    )
    deduction__lte = django_filters.NumberFilter(
        field_name="deduction", lookup_expr="lte"
    )
    deduction__gte = django_filters.NumberFilter(
        field_name="deduction", lookup_expr="gte"
    )
    net_pay__lte = django_filters.NumberFilter(field_name="net_pay", lookup_expr="lte")
    net_pay__gte = django_filters.NumberFilter(field_name="net_pay", lookup_expr="gte")

    department_id = django_filters.CharFilter(
        field_name="employee_id__employee_work_info__department_id",
        lookup_expr="icontains",
    )
    department = django_filters.CharFilter(
        field_name="employee_id__employee_work_info__department_id__department",
        lookup_expr="icontains",
    )
    month = django_filters.CharFilter(field_name="start_date", lookup_expr="month")
    year = django_filters.CharFilter(field_name="start_date", lookup_expr="year")

    allowance_title = django_filters.CharFilter(
        method="filter_by_allowance_title", label="Allowance Title"
    )
    allowance_amount_gte = django_filters.NumberFilter(
        method="filter_by_allowance_amount_gte"
    )
    allowance_amount_lte = django_filters.NumberFilter(
        method="filter_by_allowance_amount_lte"
    )
    deduction_amount_gte = django_filters.NumberFilter(
        method="filter_by_deduction_amount_gte"
    )
    deduction_amount_lte = django_filters.NumberFilter(
        method="filter_by_deduction_amount_lte"
    )

    class Meta:
        """
        Meta class to add additional options
        """

        model = Payslip
        fields = [
            "employee_id",
            "group_name",
            "status",
            "gross_pay__lte",
            "gross_pay__gte",
            "deduction__lte",
            "deduction__gte",
            "net_pay__lte",
            "net_pay__gte",
            "sent_to_employee",
            "allowance_amount_gte",
            "allowance_amount_lte",
            "deduction_amount_gte",
            "deduction_amount_lte",
        ]

    def filter_by_allowance_amount_gte(self, queryset, name, value):
        return queryset.filter(
            id__in=[
                p.id
                for p in queryset
                if any(
                    float(allowance.get("amount", 0)) >= float(value)
                    for allowance in (p.pay_head_data or {}).get("allowances", [])
                )
            ]
        )

    def filter_by_allowance_amount_lte(self, queryset, name, value):
        return queryset.filter(
            id__in=[
                p.id
                for p in queryset
                if all(
                    float(allowance.get("amount", 0)) <= float(value)
                    for allowance in (p.pay_head_data or {}).get("allowances", [])
                )
            ]
        )

    def filter_by_deduction_amount_lte(self, queryset, name, value):
        value = float(value)
        deduction_keys = [
            "pretax_deductions",
            "gross_pay_deductions",
            "basic_pay_deductions",
            "post_tax_deductions",
            "tax_deductions",
            "net_deductions",
        ]

        return queryset.filter(
            id__in=[
                p.id
                for p in queryset
                if all(
                    float(d.get("amount", 0)) <= value
                    for key in deduction_keys
                    for d in (p.pay_head_data or {}).get(key, [])
                )
            ]
        )

    def filter_by_deduction_amount_gte(self, queryset, name, value):
        value = float(value)
        deduction_keys = [
            "pretax_deductions",
            "gross_pay_deductions",
            "basic_pay_deductions",
            "post_tax_deductions",
            "tax_deductions",
            "net_deductions",
        ]

        return queryset.filter(
            id__in=[
                p.id
                for p in queryset
                if any(
                    float(d.get("amount", 0)) >= value
                    for key in deduction_keys
                    for d in (p.pay_head_data or {}).get(key, [])
                )
            ]
        )

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


class LoanAccountFilter(HorillaFilterSet):
    """
    LoanAccountFilter
    """

    # search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")
    search = django_filters.CharFilter(method="filter_by_search")
    search_employee = django_filters.CharFilter(method=filter_by_name)
    provided_date = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
        field_name="provided_date",
    )
    from_date = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
        field_name="provided_date",
        lookup_expr="gte",
    )
    to_date = django_filters.DateFilter(
        widget=forms.DateInput(attrs={"type": "date"}),
        field_name="provided_date",
        lookup_expr="lte",
    )
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as every other modernized panel this session; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- every model/queryset-backed field in the modern filter panel opts
    # in here instead of pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "employee_id": {
            "key": "loan-account-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "loan-account-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "loan-account-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "loan-account-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    def filter_by_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value)
            | Q(employee_id__employee_first_name__icontains=value)
            | Q(employee_id__employee_last_name__icontains=value)
        )

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

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter. Provided Date is a plain DateField
        column, so the plain field+lookup shape applies directly (a raw
        queryset.filter(**{field__lookup: value}) call), offering the
        full gte/lte/gt/lt/exact set instead of the fixed gte/lte
        from_date/to_date pair (plus a separate exact-only
        provided_date input) the template used to render as three
        separate fields for the same underlying column. Installment
        Start Date and Created At are included too.
        """
        fields = [
            {
                "key": "provided_date",
                "field": "provided_date",
                "label": str(_("Provided Date")),
                "type": "date_range",
            },
            {
                "key": "installment_start_date",
                "field": "installment_start_date",
                "label": str(_("Installment Start Date")),
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
        model = LoanAccount
        fields = [
            "search",
            "search_employee",
            "provided_date",
            "settled",
            "type",
            "employee_id",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__reporting_manager_id",
        ]

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )


class ReimbursementFilter(HorillaFilterSet):
    """
    ReimbursementFilter
    """

    # search = django_filters.CharFilter(field_name="title", lookup_expr="icontains")
    search = django_filters.CharFilter(method="search_method")
    # Dedicated comma-separated "Name or Badge ID" search, alongside the
    # AJAX employee_id picker below rather than instead of it -- same
    # field/behavior as every other modernized panel this session; see
    # horilla.filters.filter_name_or_badge_terms for the shared matching
    # logic.
    name_or_badge = django_filters.CharFilter(
        method="filter_name_or_badge", label=_("Name or Badge ID")
    )

    # HorillaFilterSet.ajax_fields (generic AJAX-loaded combobox mechanism)
    # -- every model/queryset-backed field in the modern filter panel opts
    # in here instead of pre-rendering its whole queryset as <option> tags.
    ajax_fields = {
        "employee_id": {
            "key": "reimbursement-employee",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
        "employee_id__employee_work_info__department_id": {
            "key": "reimbursement-department",
            "queryset_fn": lambda request: Department.objects.all(),
            "display_fn": lambda obj: obj.department,
            "search_fields": ["department"],
            "placeholder": _("Select department..."),
        },
        "employee_id__employee_work_info__job_position_id": {
            "key": "reimbursement-job-position",
            "queryset_fn": lambda request: JobPosition.objects.select_related(
                "department_id"
            ).all(),
            "display_fn": lambda obj: str(obj),
            "search_fields": ["job_position", "department_id__department"],
            "placeholder": _("Select job position..."),
        },
        "employee_id__employee_work_info__reporting_manager_id": {
            "key": "reimbursement-reporting-manager",
            "queryset_fn": lambda request: Employee.objects.filter(is_active=True),
            "display_fn": lambda obj: obj.get_full_name(),
            "search_fields": ["employee_first_name", "employee_last_name", "badge_id"],
            "placeholder": _("Search employee..."),
        },
    }

    class Meta:
        model = Reimbursement
        fields = [
            "id",
            "status",
            "type",
            "employee_id",
            "approved_by",
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__job_position_id",
            "employee_id__employee_work_info__reporting_manager_id",
        ]

    def search_method(self, queryset, _, value):
        """
        This method is used to search employees and objective
        """

        return (
            (queryset.filter(employee_id__employee_first_name__icontains=value))
            | queryset.filter(title__icontains=value)
        ).distinct()

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

    def _build_custom_filter_fields(self):
        """
        Registry backing the Advanced section's "+ Add filter" builder
        (see HorillaFilterSet._build_custom_filter_fields's docstring
        for the two supported entry shapes) -- same "choose field, then
        lookup, then value" pattern used by AttendanceFilters/
        EmployeeFilter/AssetFilter/LoanAccountFilter. Allowance On and
        Created At are plain DateField/DateTimeField columns, so the
        plain field+lookup shape applies directly.
        """
        fields = [
            {
                "key": "allowance_on",
                "field": "allowance_on",
                "label": str(_("Allowance On")),
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
        AssetFilter/LoanAccountFilter.
        """
        queryset = super().filter_queryset(queryset)
        return self._apply_custom_filters(queryset)

    def __init__(self, data=None, queryset=None, *, request=None, prefix=None):
        super().__init__(data=data, queryset=queryset, request=request, prefix=prefix)
        self.form.fields["name_or_badge"].widget.attrs["placeholder"] = _(
            "e.g. John, PEP01, PEP02"
        )


class TaxBracketFilter(HorillaFilterSet):
    """
    Filter set class for TaxBracket model.
    """

    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = TaxBracket
        fields = "__all__"

    def search_method(self, queryset, _, value):
        """
        This method is used to search employees and objective
        """

        return (
            queryset.filter(filing_status_id__filing_status__icontains=value)
        ).distinct()


class FilingStatusFilter(HorillaFilterSet):
    """
    Filter set class for TaxBracket model.
    """

    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = FilingStatus
        fields = "__all__"

    def search_method(self, queryset, _, value):
        """
        This method is used to search employees and objective
        """

        return (queryset.filter(filing_status__icontains=value)).distinct()


class ContractReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", _("Select")),
        ("employee_id", _("Employee")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("contract_status", _("Status")),
        ("employee_id__employee_work_info__shift_id", _("Shift")),
        ("employee_id__employee_work_info__work_type_id", _("Work Type")),
        ("employee_id__employee_work_info__job_role_id", _("Job Role")),
        (
            "employee_id__employee_work_info__reporting_manager_id",
            _("Reporting Manager"),
        ),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


class PayslipReGroup:
    """
    Class to keep the field name for group by option
    """

    fields = [
        ("", _("Select")),
        ("employee_id", _("Employee")),
        ("group_name", _("Payslip Batch")),
        ("start_date", _("Start Date")),
        ("end_date", _("End Date")),
        ("basic_pay", _("Basic Pay")),
        ("gross_pay", _("Gross Pay")),
        ("net_pay", _("Net Pay")),
        ("status", _("Status")),
        ("employee_id__employee_work_info__department_id", _("Department")),
        ("employee_id__employee_work_info__job_position_id", _("Job Position")),
        ("employee_id__employee_work_info__job_role_id", _("Job Role")),
        ("employee_id__employee_work_info__company_id", _("Company")),
    ]


class PayslipAutoGenerateFilter(HorillaFilterSet):

    search = django_filters.CharFilter(method="search_method")

    class Meta:
        model = PayslipAutoGenerate
        fields = ["company_id"]

    def search_method(self, queryset, _, value):
        """
        This method is used to search employees and objective
        """

        return ((queryset.filter(company_id__company__icontains=value))).distinct()

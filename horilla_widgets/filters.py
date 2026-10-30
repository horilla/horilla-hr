"""
filters.py

Standalone filter and field registry for the employee multi-select picker widget.
"""

import django_filters
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from base.methods import filtersubordinatesemployeemodel
from base.models import (
    Company,
    Department,
    EmployeeShift,
    EmployeeType,
    JobPosition,
    JobRole,
    WorkType,
)
from employee.models import Employee, EmployeeTag
from horilla.filters import filter_name_or_badge_terms
from horilla_widgets.generic_ajax import register_ajax_field

WORK_INFO = "employee_work_info__"


def _ajax_field(name, label, queryset_fn, display_fn, search_fields):
    """Describe one AJAX-searched picker filter field."""
    return {
        "name": name,
        "label": label,
        "kind": "ajax",
        "key": f"picker-{name}",
        "queryset_fn": queryset_fn,
        "display_fn": display_fn,
        "search_fields": search_fields,
    }


def _choice_field(name, label):
    """Describe one picker filter field whose options are a small fixed list."""
    return {"name": name, "label": label, "kind": "choice"}


def _employee_queryset(request):
    return filtersubordinatesemployeemodel(
        request, Employee.objects.filter(is_active=True), "employee.view_employee"
    )


PICKER_GROUPS = [
    {
        "label": _("Work info"),
        "open": True,
        "fields": [
            _ajax_field(
                "department",
                _("Department"),
                lambda request: Department.objects.all(),
                lambda obj: obj.department,
                ["department"],
            ),
            _ajax_field(
                "job_position",
                _("Job position"),
                lambda request: JobPosition.objects.select_related("department_id"),
                str,
                ["job_position", "department_id__department"],
            ),
            _ajax_field(
                "company",
                _("Company"),
                lambda request: Company.objects.all(),
                lambda obj: obj.company,
                ["company"],
            ),
            _ajax_field(
                "work_type",
                _("Work type"),
                lambda request: WorkType.objects.all(),
                lambda obj: obj.work_type,
                ["work_type"],
            ),
            _ajax_field(
                "shift",
                _("Shift"),
                lambda request: EmployeeShift.objects.all(),
                lambda obj: obj.employee_shift,
                ["employee_shift"],
            ),
            _ajax_field(
                "employee_type",
                _("Employee type"),
                lambda request: EmployeeType.objects.all(),
                lambda obj: obj.employee_type,
                ["employee_type"],
            ),
            _ajax_field(
                "job_role",
                _("Job role"),
                lambda request: JobRole.objects.select_related("job_position_id"),
                str,
                ["job_role", "job_position_id__job_position"],
            ),
        ],
    },
    {
        "label": _("People"),
        "open": False,
        "fields": [
            _ajax_field(
                "reporting_manager",
                _("Reporting manager"),
                _employee_queryset,
                lambda obj: obj.get_full_name(),
                ["employee_first_name", "employee_last_name", "badge_id"],
            ),
            _ajax_field(
                "tag",
                _("Employee tag"),
                lambda request: EmployeeTag.objects.all(),
                lambda obj: obj.title,
                ["title"],
            ),
            _choice_field("gender", _("Gender")),
            _choice_field("country", _("Country")),
        ],
    },
]

for _group in PICKER_GROUPS:
    for _field in _group["fields"]:
        if _field["kind"] == "ajax":
            register_ajax_field(
                _field["key"],
                _field["queryset_fn"],
                _field["display_fn"],
                _field["search_fields"],
            )


def _country_choices():
    countries = (
        Employee.objects.exclude(country__isnull=True)
        .exclude(country="")
        .order_by("country")
        .values_list("country", flat=True)
        .distinct()
    )
    return [(country, country) for country in countries]


CHOICE_SOURCES = {
    "gender": lambda: list(Employee.choice_gender),
    "country": _country_choices,
}


def get_picker_groups():
    """Return the rail's groups and fields, with AJAX urls and choice lists resolved."""
    groups = []
    for group in PICKER_GROUPS:
        fields = []
        for field in group["fields"]:
            item = {
                "name": field["name"],
                "label": field["label"],
                "kind": field["kind"],
            }
            if field["kind"] == "ajax":
                item["url"] = reverse("horilla-ajax-choices", args=[field["key"]])
            else:
                item["choices"] = CHOICE_SOURCES[field["name"]]()
            fields.append(item)
        groups.append(
            {"label": group["label"], "open": group["open"], "fields": fields}
        )
    return groups


class EmployeePickerFilter(django_filters.FilterSet):
    """Filters the employees listed in the multi-select picker modal."""

    name_or_badge = django_filters.CharFilter(method="filter_name_or_badge")
    department = django_filters.ModelMultipleChoiceFilter(
        field_name=f"{WORK_INFO}department_id",
        queryset=lambda request: Department.objects.all(),
    )
    job_position = django_filters.ModelMultipleChoiceFilter(
        field_name=f"{WORK_INFO}job_position_id",
        queryset=lambda request: JobPosition.objects.all(),
    )
    company = django_filters.ModelMultipleChoiceFilter(
        field_name=f"{WORK_INFO}company_id",
        queryset=lambda request: Company.objects.all(),
    )
    work_type = django_filters.ModelMultipleChoiceFilter(
        field_name=f"{WORK_INFO}work_type_id",
        queryset=lambda request: WorkType.objects.all(),
    )
    shift = django_filters.ModelMultipleChoiceFilter(
        field_name=f"{WORK_INFO}shift_id",
        queryset=lambda request: EmployeeShift.objects.all(),
    )
    employee_type = django_filters.ModelMultipleChoiceFilter(
        field_name=f"{WORK_INFO}employee_type_id",
        queryset=lambda request: EmployeeType.objects.all(),
    )
    job_role = django_filters.ModelMultipleChoiceFilter(
        field_name=f"{WORK_INFO}job_role_id",
        queryset=lambda request: JobRole.objects.all(),
    )
    reporting_manager = django_filters.ModelMultipleChoiceFilter(
        field_name=f"{WORK_INFO}reporting_manager_id",
        queryset=lambda request: Employee.objects.all(),
    )
    tag = django_filters.ModelMultipleChoiceFilter(
        field_name=f"{WORK_INFO}tags",
        queryset=lambda request: EmployeeTag.objects.all(),
    )
    gender = django_filters.MultipleChoiceFilter(choices=Employee.choice_gender)
    country = django_filters.MultipleChoiceFilter(choices=_country_choices)
    joined_from = django_filters.DateFilter(
        field_name=f"{WORK_INFO}date_joining", lookup_expr="gte"
    )
    joined_till = django_filters.DateFilter(
        field_name=f"{WORK_INFO}date_joining", lookup_expr="lte"
    )

    class Meta:
        model = Employee
        fields = []

    def filter_name_or_badge(self, queryset, name, value):
        """Match a comma-separated list of names or badge ids."""
        return filter_name_or_badge_terms(
            queryset, value, "employee_first_name", "employee_last_name", "badge_id"
        )

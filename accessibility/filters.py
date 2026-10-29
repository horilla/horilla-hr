"""
accessibility/filters.py
"""

from functools import reduce

import django_filters
from django.contrib.auth.models import Permission
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from employee.models import Employee
from horilla.filters import HorillaFilterSet
from horilla.horilla_middlewares import _thread_locals
from horilla_auth.models import HorillaUser

PERMISSION_FIELD = "employee_user_id__user_permissions"
PERMISSION_BACKEND = "base.auth_backends.CompanyScopedBackend"


def _filter_form_structured(self):
    """
    Render the form fields as HTML table rows with Bootstrap styling.
    """
    request = getattr(_thread_locals, "request", None)
    context = {
        "form": self,
        "request": request,
    }
    table_html = render_to_string("accessibility/filter_form_body.html", context)
    return table_html


class AccessibilityFilter(HorillaFilterSet):
    """
    Accessibility Filter with dynamic OR logic between fields
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.form.structured = _filter_form_structured(self.form)

    pk = django_filters.ModelMultipleChoiceFilter(
        queryset=Employee.objects.all(),
        field_name="pk",
        lookup_expr="in",
        label=_("Employee"),
    )
    excluded_employees = django_filters.ModelMultipleChoiceFilter(
        queryset=Employee.objects.all(),
        label=_("Exclude Employees"),
    )
    employee_user_id__user_permissions = django_filters.ModelMultipleChoiceFilter(
        queryset=Permission.objects.select_related("content_type").all(),
        label=_("Permissions"),
    )

    verbose_name = {
        "employee_work_info__job_position_id": _("Job Position"),
        "employee_work_info__department_id": _("Department"),
        "employee_work_info__work_type_id": _("Work Type"),
        "employee_work_info__employee_type_id": _("Employee Type"),
        "employee_work_info__job_role_id": _("Job Role"),
        "employee_work_info__company_id": _("Company"),
        "employee_work_info__shift_id": _("Shift"),
        "employee_work_info__tags": _("Tags"),
        "employee_user_id__groups": _("Groups"),
        "employee_user_id__user_permissions": _("Permissions"),
    }

    class Meta:
        """
        Meta class for additional options
        """

        model = Employee
        fields = [
            "pk",
            "employee_work_info__job_position_id",
            "employee_work_info__department_id",
            "employee_work_info__work_type_id",
            "employee_work_info__employee_type_id",
            "employee_work_info__job_role_id",
            "employee_work_info__company_id",
            "employee_work_info__shift_id",
            "employee_work_info__tags",
            "employee_user_id__groups",
            "employee_user_id__user_permissions",
        ]

    def filter_queryset(self, queryset):
        """
        Dynamically apply OR condition between all specified fields
        """
        or_conditions = []

        for field in self.Meta.fields:
            field_value = self.data.get(field)
            if field_value:
                # Ensure field_value is always a list of strings (IDs)
                if not isinstance(field_value, (list, tuple)):
                    field_value = [field_value]

                # Convert all to ints
                try:
                    field_value = [int(v) for v in field_value if v]
                except ValueError:
                    continue  # skip invalid values

                if field == PERMISSION_FIELD:
                    continue
                if "__" in field:
                    or_conditions.append(Q(**{f"{field}__id__in": field_value}))
                else:
                    or_conditions.append(Q(**{f"{field}__in": field_value}))

        if or_conditions:
            queryset = queryset.filter(
                reduce(lambda x, y: x | y, or_conditions)
            ).distinct()

        permission_ids = self.data.get(PERMISSION_FIELD)
        if permission_ids:
            if not isinstance(permission_ids, (list, tuple)):
                permission_ids = [permission_ids]
            permissions = Permission.objects.filter(
                pk__in=[pk for pk in permission_ids if str(pk).isdigit()]
            )
            if permissions:
                permission_q = Q(pk__in=queryset.values("pk")) if or_conditions else Q()
                for permission in permissions:
                    permission_q |= Q(
                        employee_user_id__in=HorillaUser.objects.with_perm(
                            permission, backend=PERMISSION_BACKEND
                        )
                    )
                queryset = self.queryset.filter(permission_q)

        excluded_employees = self.data.get("excluded_employees")
        if excluded_employees:
            if not isinstance(excluded_employees, (list, tuple)):
                excluded_employees = [excluded_employees]
            queryset = queryset.exclude(pk__in=excluded_employees)

        return queryset

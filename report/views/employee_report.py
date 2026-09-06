import json

from django.db.models import CharField, Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import render

from base.methods import has_export_access
from base.models import Company
from employee.filters import EmployeeFilter
from employee.models import Employee
from horilla.decorators import login_required, permission_required
from report.dynamic_filter_utils import (
    RELATIVE_DATE_OPERATORS,
    parse_multi_value,
    resolve_relative_date_range,
)
from report.pivot_limits import pivot_json_with_meta

# Maps the field ids used by the dynamic Filters modal to the ORM path
# `employee_pivot` filters on. "name" and "reporting_manager" are handled
# separately since each is really two underlying columns (first/last name).
DYNAMIC_FILTER_FIELD_PATHS = {
    "badge_id": "badge_id",
    "email": "email",
    "phone": "phone",
    "gender": "gender",
    "department": "employee_work_info__department_id__department",
    "job_position": "employee_work_info__job_position_id__job_position",
    "job_role": "employee_work_info__job_role_id__job_role",
    "work_type": "employee_work_info__work_type_id__work_type",
    "shift": "employee_work_info__shift_id__employee_shift",
    "employee_type": "employee_work_info__employee_type_id__employee_type",
    "date_joining": "employee_work_info__date_joining",
    "experience": "employee_work_info__experience",
    "company": "employee_work_info__company_id__company",
}

NAME_FIELD_PATHS = {
    "name": ("employee_first_name", "employee_last_name"),
    "reporting_manager": (
        "employee_work_info__reporting_manager_id__employee_first_name",
        "employee_work_info__reporting_manager_id__employee_last_name",
    ),
}


def _field_accepts_empty_string(model, path):
    """
    Whether `path` (a possibly relation-crossing `__`-joined ORM path)
    resolves to a text-like field. Date/number fields reject "" as an
    invalid value at query-evaluation time, so `is_empty` must not compare
    them against "" -- only `__isnull` makes sense there.
    """
    meta = model._meta
    parts = path.split("__")
    for i, part in enumerate(parts):
        try:
            field = meta.get_field(part)
        except Exception:
            return True
        if field.is_relation and i < len(parts) - 1:
            meta = field.related_model._meta
            continue
        return field.get_internal_type() in (
            "CharField",
            "TextField",
            "EmailField",
            "SlugField",
        )
    return True


def _apply_dynamic_filter_row(qs, field, operator, value):
    """
    Apply one (field, operator, value) row from the Filters modal to the
    queryset. Unknown fields/operators or rows missing a required value are
    ignored rather than raising, since a still-being-filled-in row shouldn't
    break the whole request.
    """
    if field in NAME_FIELD_PATHS:
        first_path, last_path = NAME_FIELD_PATHS[field]
        if operator == "is_empty":
            return qs.filter(
                Q(**{f"{first_path}__isnull": True}) | Q(**{first_path: ""})
            )
        if not value:
            return qs

        # Options are offered (and picked) as the combined "First Last"
        # string, so match against first+last concatenated together rather
        # than against each half separately -- a two-word name can never
        # equal/contain just the first or just the last name column alone.
        full_name = f"_{field}_full_name"
        qs = qs.annotate(
            **{
                full_name: Concat(
                    first_path, Value(" "), last_path, output_field=CharField()
                )
            }
        )
        if operator == "equals":
            values = parse_multi_value(value)
            if len(values) > 1:
                return qs.filter(**{f"{full_name}__in": values})
            return qs.filter(**{f"{full_name}__iexact": values[0]})
        if operator == "not_equals":
            values = parse_multi_value(value)
            if len(values) > 1:
                return qs.exclude(**{f"{full_name}__in": values})
            return qs.exclude(**{f"{full_name}__iexact": values[0]})
        if operator == "contains":
            return qs.filter(**{f"{full_name}__icontains": value})
        return qs

    path = DYNAMIC_FILTER_FIELD_PATHS.get(field)
    if not path:
        return qs

    if operator == "is_empty":
        q = Q(**{f"{path}__isnull": True})
        if _field_accepts_empty_string(qs.model, path):
            q |= Q(**{path: ""})
        return qs.filter(q)
    if operator in RELATIVE_DATE_OPERATORS:
        return qs.filter(**{f"{path}__range": resolve_relative_date_range(operator)})
    if not value:
        return qs
    if operator == "equals":
        values = parse_multi_value(value)
        if len(values) > 1:
            return qs.filter(**{f"{path}__in": values})
        return qs.filter(**{f"{path}__iexact": values[0]})
    if operator == "not_equals":
        values = parse_multi_value(value)
        if len(values) > 1:
            return qs.exclude(**{f"{path}__in": values})
        return qs.exclude(**{f"{path}__iexact": values[0]})
    if operator == "contains":
        return qs.filter(**{f"{path}__icontains": value})
    if operator == "greater_than":
        return qs.filter(**{f"{path}__gt": value})
    if operator == "less_than":
        return qs.filter(**{f"{path}__lt": value})
    if operator == "between":
        bounds = [part.strip() for part in value.split(",") if part.strip()]
        if len(bounds) == 2:
            return qs.filter(**{f"{path}__range": (bounds[0], bounds[1])})
    return qs


def apply_dynamic_filters(qs, request):
    """
    Apply the Filters modal's field/operator/value rows, sent as a JSON
    array in the `dynamic_filters` query param, e.g.
    '[{"field": "department", "operator": "contains", "value": "hr"},
      {"field": "department", "operator": "contains", "value": "sales",
       "connector": "or"}]'.

    Each row (after the first) carries a `connector` ("and"/"or", default
    "and") saying how it combines with everything before it. Rows are
    evaluated left to right with no precedence/grouping -- the same way a
    plain English "A and B or C" reads. Each row is applied fresh against
    the original (pre-filter) queryset rather than chaining `.filter()`
    calls, since chaining always ANDs at the SQL level regardless of what
    the user picked; the per-row results are then combined with Django's
    QuerySet `&`/`|` operators, which correctly combine their underlying
    WHERE clauses (and any `.annotate()` a row added, e.g. for name
    matching) as AND/OR instead.
    """
    raw = request.GET.get("dynamic_filters")
    if not raw:
        return qs
    try:
        rows = json.loads(raw)
    except (ValueError, TypeError):
        return qs
    if not isinstance(rows, list):
        return qs

    base_qs = qs
    combined = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        field = row.get("field")
        operator = row.get("operator")
        value = (row.get("value") or "").strip()
        connector = row.get("connector") or "and"
        if not field or not operator:
            continue
        row_qs = _apply_dynamic_filter_row(base_qs, field, operator, value)
        if row_qs is base_qs:
            # Row didn't actually filter anything (unknown field, or an
            # operator missing its required value) -- skip it rather than
            # let an untouched full queryset dominate an OR combination.
            continue
        if combined is None:
            combined = row_qs
        elif connector == "or":
            combined = combined | row_qs
        else:
            combined = combined & row_qs
    return combined if combined is not None else qs


@login_required
@permission_required(perm="employee.view_employee")
def employee_filter_field_options(request):
    """
    Distinct values available for a given dynamic-filter field, so the
    Filters panel can offer a searchable pick-list (like the rest of the
    app already does for relationship fields) instead of a freehand text
    box for fields where a fixed value is actually being matched.
    """
    field = request.GET.get("field")
    qs = Employee.objects.all()

    if field in NAME_FIELD_PATHS:
        first_path, last_path = NAME_FIELD_PATHS[field]
        pairs = (
            qs.exclude(**{f"{first_path}__isnull": True})
            .exclude(**{first_path: ""})
            .values_list(first_path, last_path)
            .distinct()
        )
        options = sorted({f"{first} {last or ''}".strip() for first, last in pairs})
        return JsonResponse({"options": options})

    path = DYNAMIC_FILTER_FIELD_PATHS.get(field)
    if not path:
        return JsonResponse({"options": []})

    values = qs.exclude(**{f"{path}__isnull": True})
    if _field_accepts_empty_string(qs.model, path):
        values = values.exclude(**{path: ""})
    values = values.values_list(path, flat=True).distinct()
    # Some fields have leaked the literal string "None" as sentinel junk
    options = sorted({str(v) for v in values if str(v).strip().lower() != "none"})
    return JsonResponse({"options": options})


@login_required
@permission_required(perm="employee.view_employee")
def employee_report(request):
    company = "all"
    selected_company = request.session.get("selected_company")
    if selected_company != "all":
        company = Company.objects.filter(id=selected_company).first()

    return render(
        request,
        "report/employee_report.html",
        {
            "company": company,
            "f": EmployeeFilter(),
            "export_access": has_export_access(request, Employee),
        },
    )


@login_required
@permission_required(perm="employee.view_employee")
def employee_pivot(request):
    qs = Employee.objects.all()
    # EmployeeFilter.is_active carries initial=True, but django-filter's
    # `initial` only preselects the form widget -- it never reaches the
    # queryset. Without this the pivot counted terminated employees, so its
    # headcount disagreed with every standard report (which defaults to
    # active). An explicit is_active in the query string still wins.
    if not request.GET.get("is_active"):
        qs = qs.filter(is_active=True)
    filtered_qs = EmployeeFilter(request.GET, queryset=qs)
    qs = filtered_qs.qs
    qs = apply_dynamic_filters(qs, request)

    data = list(
        qs.values(
            "employee_first_name",
            "employee_last_name",
            "badge_id",
            "gender",
            "email",
            "phone",
            "employee_work_info__department_id__department",
            "employee_work_info__job_position_id__job_position",
            "employee_work_info__job_role_id__job_role",
            "employee_work_info__work_type_id__work_type",
            "employee_work_info__shift_id__employee_shift",
            "employee_work_info__employee_type_id__employee_type",
            "employee_work_info__reporting_manager_id__employee_first_name",
            "employee_work_info__reporting_manager_id__employee_last_name",
            "employee_work_info__company_id__company",
            "employee_work_info__date_joining",
            "employee_work_info__experience",
        )
    )
    choice_gender = {
        "male": "Male",
        "female": "Female",
        "other": "Other",
    }

    # Transform data to match format
    data_list = [
        {
            "Name": f"{item['employee_first_name']} {item['employee_last_name']}",
            "Badge Id": item["badge_id"] or "-",
            "Gender": choice_gender.get(item["gender"]),
            "Email": item["email"],
            "Phone": item["phone"],
            "Department": (
                item["employee_work_info__department_id__department"]
                if item["employee_work_info__department_id__department"]
                else "-"
            ),
            "Job Position": (
                item["employee_work_info__job_position_id__job_position"]
                if item["employee_work_info__job_position_id__job_position"]
                else "-"
            ),
            "Job Role": (
                item["employee_work_info__job_role_id__job_role"]
                if item["employee_work_info__job_role_id__job_role"]
                else "-"
            ),
            "Work Type": (
                item["employee_work_info__work_type_id__work_type"]
                if item["employee_work_info__work_type_id__work_type"]
                else "-"
            ),
            "Shift": (
                item["employee_work_info__shift_id__employee_shift"]
                if item["employee_work_info__shift_id__employee_shift"]
                else "-"
            ),
            "Employee Type": (
                item["employee_work_info__employee_type_id__employee_type"]
                if item["employee_work_info__employee_type_id__employee_type"]
                else "-"
            ),
            "Reporting Manager": (
                f"{item['employee_work_info__reporting_manager_id__employee_first_name']} {item['employee_work_info__reporting_manager_id__employee_last_name']}"
                if item["employee_work_info__reporting_manager_id__employee_first_name"]
                else "-"
            ),
            "Date of Joining": (
                item["employee_work_info__date_joining"]
                if item["employee_work_info__date_joining"]
                else "-"
            ),
            "Experience": round(float(item["employee_work_info__experience"] or 0), 2),
            "Company": item["employee_work_info__company_id__company"],
        }
        for item in data
    ]
    return pivot_json_with_meta(data_list)

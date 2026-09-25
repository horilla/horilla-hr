import json

from django.apps import apps
from django.db.models import CharField, Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import render

if apps.is_installed("asset"):
    from asset.models import Asset
    from base.methods import has_export_access
    from base.models import Company
    from horilla.decorators import login_required, permission_required
    from report.dynamic_filter_utils import (
        RELATIVE_DATE_OPERATORS,
        parse_multi_value,
        resolve_relative_date_range,
    )
    from report.pivot_limits import pivot_json_with_meta

    # Maps the field ids used by the dynamic Filters modal to the ORM path
    # `asset_pivot` filters on. "asset_user" is handled separately since it
    # is really two underlying columns (first/last name).
    DYNAMIC_FILTER_FIELD_PATHS = {
        "asset_name": "asset_name",
        "asset_tracking_id": "asset_tracking_id",
        "asset_purchase_date": "asset_purchase_date",
        "asset_purchase_cost": "asset_purchase_cost",
        "asset_lot_number_id": "asset_lot_number_id__lot_number",
        "asset_category_id": "asset_category_id__asset_category_name",
        "asset_status": "asset_status",
        "expiry_date": "expiry_date",
        "badge_id": "assetassignment__assigned_by_employee_id__badge_id",
        "email": "assetassignment__assigned_by_employee_id__email",
        "phone": "assetassignment__assigned_by_employee_id__phone",
        "gender": "assetassignment__assigned_by_employee_id__gender",
        "department": "assetassignment__assigned_by_employee_id__employee_work_info__department_id__department",
        "job_position": "assetassignment__assigned_by_employee_id__employee_work_info__job_position_id__job_position",
        "job_role": "assetassignment__assigned_by_employee_id__employee_work_info__job_role_id__job_role",
        "assigned_date": "assetassignment__assigned_date",
        "return_date": "assetassignment__return_date",
        "return_status": "assetassignment__return_status",
    }

    NAME_FIELD_PATHS = {
        "asset_user": (
            "assetassignment__assigned_by_employee_id__employee_first_name",
            "assetassignment__assigned_by_employee_id__employee_last_name",
        ),
    }

    def _field_accepts_empty_string(model, path):
        """
        Whether `path` (a possibly relation-crossing `__`-joined ORM path)
        resolves to a text-like field. Date/number fields reject "" as an
        invalid value at query-evaluation time, so `is_empty` must not
        compare them against "" -- only `__isnull` makes sense there.
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
        queryset. Unknown fields/operators or rows missing a required value
        are ignored rather than raising, since a still-being-filled-in row
        shouldn't break the whole request.
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
            # string, so match against first+last concatenated together
            # rather than against each half separately -- a two-word name
            # can never equal/contain just the first or just the last name
            # column alone.
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
            return qs.filter(
                **{f"{path}__range": resolve_relative_date_range(operator)}
            )
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
        '[{"field": "asset_status", "operator": "contains", "value": "use"},
          {"field": "asset_status", "operator": "contains", "value": "avail",
           "connector": "or"}]'.

        Each row (after the first) carries a `connector` ("and"/"or",
        default "and") saying how it combines with everything before it,
        evaluated left to right with no precedence/grouping. Each row is
        applied fresh against the original queryset rather than chaining
        `.filter()` calls (which always ANDs at the SQL level regardless of
        intent); the per-row results are combined with QuerySet `&`/`|`,
        which correctly combine their WHERE clauses (and any `.annotate()`
        a row added) as AND/OR.
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
                continue
            if combined is None:
                combined = row_qs
            elif connector == "or":
                combined = combined | row_qs
            else:
                combined = combined & row_qs
        return combined if combined is not None else qs

    @login_required
    @permission_required(perm="asset.view_asset")
    def asset_filter_field_options(request):
        """
        Distinct values available for a given dynamic-filter field, so the
        Filters panel can offer a searchable pick-list (like the rest of the
        app already does for relationship fields) instead of a freehand text
        box for fields where a fixed value is actually being matched.
        """
        field = request.GET.get("field")
        qs = Asset.objects.all()

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
    @permission_required(perm="asset.view_asset")
    def asset_report(request):
        company = "all"
        selected_company = request.session.get("selected_company")
        if selected_company != "all":
            company = Company.objects.filter(id=selected_company).first()

        return render(
            request,
            "report/asset_report.html",
            {
                "company": company,
                "export_access": has_export_access(request, Asset),
            },
        )

    @login_required
    @permission_required(perm="asset.view_asset")
    def asset_pivot(request):
        qs = Asset.objects.all()
        qs = apply_dynamic_filters(qs, request)

        data = list(
            qs.values(
                "asset_name",
                "asset_purchase_date",
                "asset_tracking_id",
                "asset_purchase_cost",
                "asset_status",
                "asset_category_id__asset_category_name",
                "asset_lot_number_id__lot_number",
                "expiry_date",
                "assetassignment__assigned_by_employee_id__employee_work_info__department_id__department",
                "assetassignment__assigned_by_employee_id__employee_work_info__job_position_id__job_position",
                "assetassignment__assigned_by_employee_id__employee_work_info__job_role_id__job_role",
                "assetassignment__assigned_by_employee_id__email",
                "assetassignment__assigned_by_employee_id__phone",
                "assetassignment__assigned_by_employee_id__gender",
                "assetassignment__assigned_by_employee_id__employee_first_name",
                "assetassignment__assigned_by_employee_id__employee_last_name",
                "assetassignment__assigned_by_employee_id__badge_id",
                "assetassignment__assigned_date",
                "assetassignment__return_date",
                "assetassignment__return_status",
            )
        )
        data_list = [
            {
                "Asset Name": item["asset_name"],
                "Asset User": (
                    f"{item['assetassignment__assigned_by_employee_id__employee_first_name']} {item['assetassignment__assigned_by_employee_id__employee_last_name']}"
                    if item[
                        "assetassignment__assigned_by_employee_id__employee_first_name"
                    ]
                    or item[
                        "assetassignment__assigned_by_employee_id__employee_last_name"
                    ]
                    else "-"
                ),
                "Asset User Badge Id": (
                    item["assetassignment__assigned_by_employee_id__badge_id"] or "-"
                ),
                "Email": (
                    item["assetassignment__assigned_by_employee_id__email"]
                    if item["assetassignment__assigned_by_employee_id__email"]
                    else "-"
                ),
                "Phone": (
                    item["assetassignment__assigned_by_employee_id__phone"]
                    if item["assetassignment__assigned_by_employee_id__phone"]
                    else "-"
                ),
                "Gender": (
                    item["assetassignment__assigned_by_employee_id__gender"]
                    if item["assetassignment__assigned_by_employee_id__gender"]
                    else "-"
                ),
                "Department": (
                    item[
                        "assetassignment__assigned_by_employee_id__employee_work_info__department_id__department"
                    ]
                    if item[
                        "assetassignment__assigned_by_employee_id__employee_work_info__department_id__department"
                    ]
                    else "-"
                ),
                "Job Position": (
                    item[
                        "assetassignment__assigned_by_employee_id__employee_work_info__job_position_id__job_position"
                    ]
                    if item[
                        "assetassignment__assigned_by_employee_id__employee_work_info__job_position_id__job_position"
                    ]
                    else "-"
                ),
                "Job Role": (
                    item[
                        "assetassignment__assigned_by_employee_id__employee_work_info__job_role_id__job_role"
                    ]
                    if item[
                        "assetassignment__assigned_by_employee_id__employee_work_info__job_role_id__job_role"
                    ]
                    else "-"
                ),
                "Asset Purchce Date": item["asset_purchase_date"],
                "Asset Cost": item["asset_purchase_cost"],
                "Status": item["asset_status"],
                "Assigned Date": (
                    item["assetassignment__assigned_date"]
                    if item["assetassignment__assigned_date"]
                    else "-"
                ),
                "Return Date": (
                    item["assetassignment__return_date"]
                    if item["assetassignment__return_date"]
                    else "-"
                ),
                "Return Condition": (
                    item["assetassignment__return_status"]
                    if item["assetassignment__return_status"]
                    else "-"
                ),
                "Category": item["asset_category_id__asset_category_name"],
                "Batch Number": item["asset_lot_number_id__lot_number"],
                "Serial No.": item["asset_tracking_id"],
                "Warranty Expiry Date": (
                    item["expiry_date"] if item["expiry_date"] else "-"
                ),
            }
            for item in data
        ]
        return pivot_json_with_meta(data_list)

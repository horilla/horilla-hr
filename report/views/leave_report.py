import json

from django.apps import apps
from django.db.models import CharField, Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import render

if apps.is_installed("leave"):

    from base.methods import has_export_access
    from base.models import Company
    from horilla.decorators import login_required, permission_required
    from leave.filters import AssignedLeaveFilter, LeaveRequestFilter
    from leave.models import AvailableLeave, LeaveRequest
    from report.dynamic_filter_utils import (
        RELATIVE_DATE_OPERATORS,
        parse_multi_value,
        resolve_relative_date_range,
    )
    from report.pivot_limits import pivot_json_with_meta

    # Maps the field ids used by the dynamic Filters panel to the ORM path
    # `leave_pivot` filters on. This is a *multi-model* report -- the field
    # catalog (and therefore the valid ORM paths) differs depending on which
    # model type ("leave_request" or "available_leave") is currently
    # selected, so both this and NAME_FIELD_PATHS are keyed by model type.
    # "employee" and "reporting_manager" are handled separately (via
    # NAME_FIELD_PATHS) since each is really two underlying columns
    # (first/last name).
    DYNAMIC_FILTER_FIELD_PATHS = {
        "leave_request": {
            "leave_type": "leave_type_id__name",
            "status": "status",
            "company": "employee_id__employee_work_info__company_id__company",
            "department": "employee_id__employee_work_info__department_id__department",
            "job_position": "employee_id__employee_work_info__job_position_id__job_position",
            "job_role": "employee_id__employee_work_info__job_role_id__job_role",
            "shift": "employee_id__employee_work_info__shift_id__employee_shift",
            "work_type": "employee_id__employee_work_info__work_type_id__work_type",
            "start_date": "start_date",
            "end_date": "end_date",
            "badge_id": "employee_id__badge_id",
            "gender": "employee_id__gender",
            "email": "employee_id__email",
            "phone": "employee_id__phone",
            "experience": "employee_id__employee_work_info__experience",
            "start_date_breakdown": "start_date_breakdown",
            "end_date_breakdown": "end_date_breakdown",
            "requested_days": "requested_days",
        },
        "available_leave": {
            "leave_type": "leave_type_id__name",
            "available_days": "available_days",
            "carryforward_days": "carryforward_days",
            "total_leave_days": "total_leave_days",
            "assigned_date": "assigned_date",
            "reset_date": "reset_date",
            "expired_date": "expired_date",
            "company": "employee_id__employee_work_info__company_id__company",
            "department": "employee_id__employee_work_info__department_id__department",
            "job_position": "employee_id__employee_work_info__job_position_id__job_position",
            "job_role": "employee_id__employee_work_info__job_role_id__job_role",
            "shift": "employee_id__employee_work_info__shift_id__employee_shift",
            "work_type": "employee_id__employee_work_info__work_type_id__work_type",
            "badge_id": "employee_id__badge_id",
            "gender": "employee_id__gender",
            "email": "employee_id__email",
            "phone": "employee_id__phone",
            "experience": "employee_id__employee_work_info__experience",
        },
    }

    NAME_FIELD_PATHS = {
        "leave_request": {
            "employee": (
                "employee_id__employee_first_name",
                "employee_id__employee_last_name",
            ),
            "reporting_manager": (
                "employee_id__employee_work_info__reporting_manager_id__employee_first_name",
                "employee_id__employee_work_info__reporting_manager_id__employee_last_name",
            ),
        },
        "available_leave": {
            "employee": (
                "employee_id__employee_first_name",
                "employee_id__employee_last_name",
            ),
        },
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

    def _apply_dynamic_filter_row(qs, model_type, field, operator, value):
        """
        Apply one (field, operator, value) row from the Filters panel to the
        queryset, using the field catalog for `model_type`. Unknown
        fields/operators or rows missing a required value are ignored rather
        than raising, since a still-being-filled-in row shouldn't break the
        whole request.
        """
        name_field_paths = NAME_FIELD_PATHS.get(model_type, {})
        if field in name_field_paths:
            first_path, last_path = name_field_paths[field]
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

        path = DYNAMIC_FILTER_FIELD_PATHS.get(model_type, {}).get(field)
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
            # Breakdown is stored as a lowercase, underscore-joined code
            # (e.g. "full_day") but offered to the user as a friendly label
            # ("Full Day") -- normalize back to the stored form instead of
            # forcing the option list to leak raw codes.
            if field in ("start_date_breakdown", "end_date_breakdown"):
                values = [v.strip().lower().replace(" ", "_") for v in values]
            if len(values) > 1:
                return qs.filter(**{f"{path}__in": values})
            return qs.filter(**{f"{path}__iexact": values[0]})
        if operator == "not_equals":
            values = parse_multi_value(value)
            if field in ("start_date_breakdown", "end_date_breakdown"):
                values = [v.strip().lower().replace(" ", "_") for v in values]
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

    def apply_dynamic_filters(qs, request, model_type):
        """
        Apply the Filters panel's field/operator/value rows, sent as a JSON
        array in the `dynamic_filters` query param, e.g.
        '[{"field": "leave_type", "operator": "contains", "value": "sick"},
          {"field": "leave_type", "operator": "contains", "value": "casual",
           "connector": "or"}]', interpreted against the field catalog for
        `model_type`.

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
            row_qs = _apply_dynamic_filter_row(
                base_qs, model_type, field, operator, value
            )
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
    @permission_required(perm="leave.view_leaverequest")
    def leave_filter_field_options(request):
        """
        Distinct values available for a given dynamic-filter field on the
        currently selected model type, so the Filters panel can offer a
        searchable pick-list (like the rest of the app already does for
        relationship fields) instead of a freehand text box for fields
        where a fixed value is actually being matched.
        """
        model_type = request.GET.get("model", "leave_request")
        field = request.GET.get("field")

        if model_type == "available_leave":
            qs = AvailableLeave.objects.all()
        else:
            qs = LeaveRequest.objects.all()

        name_field_paths = NAME_FIELD_PATHS.get(model_type, {})
        if field in name_field_paths:
            first_path, last_path = name_field_paths[field]
            pairs = (
                qs.exclude(**{f"{first_path}__isnull": True})
                .exclude(**{first_path: ""})
                .values_list(first_path, last_path)
                .distinct()
            )
            options = sorted({f"{first} {last or ''}".strip() for first, last in pairs})
            return JsonResponse({"options": options})

        path = DYNAMIC_FILTER_FIELD_PATHS.get(model_type, {}).get(field)
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
    @permission_required(perm="leave.view_leaverequest")
    def leave_report(request):
        company = "all"
        selected_company = request.session.get("selected_company")
        if selected_company != "all":
            company = Company.objects.filter(id=selected_company).first()

        leave_request_filter = LeaveRequestFilter()

        export_access_map = {
            "leave_request": has_export_access(request, LeaveRequest),
            "available_leave": has_export_access(request, AvailableLeave),
        }

        return render(
            request,
            "report/leave_report.html",
            {
                "company": company,
                "form": leave_request_filter.form,
                "f": AssignedLeaveFilter(),
                "export_access_map": export_access_map,
            },
        )

    @login_required
    @permission_required(perm="leave.view_leaverequest")
    def leave_pivot(request):
        model_type = request.GET.get(
            "model", "leave_request"
        )  # Default to LeaveRequest

        if model_type == "leave_request":

            qs = LeaveRequest.objects.all()
            leave_filter = LeaveRequestFilter(request.GET, queryset=qs)
            qs = leave_filter.qs
            qs = apply_dynamic_filters(qs, request, model_type)

            data = list(
                qs.values(
                    "employee_id__employee_first_name",
                    "employee_id__employee_last_name",
                    "employee_id__badge_id",
                    "leave_type_id__name",
                    "start_date",
                    "start_date_breakdown",
                    "end_date",
                    "end_date_breakdown",
                    "requested_days",
                    "status",
                    "employee_id__gender",
                    "employee_id__email",
                    "employee_id__phone",
                    "employee_id__employee_work_info__department_id__department",
                    "employee_id__employee_work_info__job_role_id__job_role",
                    "employee_id__employee_work_info__job_position_id__job_position",
                    "employee_id__employee_work_info__employee_type_id__employee_type",
                    "employee_id__employee_work_info__experience",
                    "employee_id__employee_work_info__work_type_id__work_type",
                    "employee_id__employee_work_info__shift_id__employee_shift",
                    "employee_id__employee_work_info__company_id__company",
                )
            )
            BREAKDOWN_MAP = {
                "full_day": "Full Day",
                "first_half": "First Half",
                "second_half": "Second Half",
            }

            choice_gender = {
                "male": "Male",
                "female": "Female",
                "other": "Other",
            }

            LEAVE_STATUS = {
                "requested": "Requested",
                "approved": "Approved",
                "cancel_requested": "Cancel Requested",
                "cancelled": "Cancelled",
                "rejected": "Rejected",
            }
            data_list = [
                {
                    "Name": f"{item['employee_id__employee_first_name']} {item['employee_id__employee_last_name']}",
                    "Badge ID": item["employee_id__badge_id"] or "-",
                    "Gender": choice_gender.get(item["employee_id__gender"]),
                    "Email": item["employee_id__email"],
                    "Phone": item["employee_id__phone"],
                    "Department": (
                        item[
                            "employee_id__employee_work_info__department_id__department"
                        ]
                        if item[
                            "employee_id__employee_work_info__department_id__department"
                        ]
                        else "-"
                    ),
                    "Job Position": (
                        item[
                            "employee_id__employee_work_info__job_position_id__job_position"
                        ]
                        if item[
                            "employee_id__employee_work_info__job_position_id__job_position"
                        ]
                        else "-"
                    ),
                    "Job Role": (
                        item["employee_id__employee_work_info__job_role_id__job_role"]
                        if item[
                            "employee_id__employee_work_info__job_role_id__job_role"
                        ]
                        else "-"
                    ),
                    "Work Type": (
                        item["employee_id__employee_work_info__work_type_id__work_type"]
                        if item[
                            "employee_id__employee_work_info__work_type_id__work_type"
                        ]
                        else "-"
                    ),
                    "Shift": (
                        item[
                            "employee_id__employee_work_info__shift_id__employee_shift"
                        ]
                        if item[
                            "employee_id__employee_work_info__shift_id__employee_shift"
                        ]
                        else "-"
                    ),
                    "Experience": item["employee_id__employee_work_info__experience"],
                    "Leave Type": item["leave_type_id__name"],
                    "Start Date": item["start_date"],
                    "Start Date Breakdown": BREAKDOWN_MAP.get(
                        item["start_date_breakdown"], "-"
                    ),
                    "End Date Breakdown": BREAKDOWN_MAP.get(
                        item["end_date_breakdown"], "-"
                    ),
                    "End Date": item["end_date"],
                    "Requested Days": item["requested_days"],
                    "Status": LEAVE_STATUS.get(item["status"]),
                    "Company": item[
                        "employee_id__employee_work_info__company_id__company"
                    ],
                }
                for item in data
            ]
        elif model_type == "available_leave":

            qs = AvailableLeave.objects.all()
            available_leave_filter = AssignedLeaveFilter(request.GET, queryset=qs)
            qs = available_leave_filter.qs
            qs = apply_dynamic_filters(qs, request, model_type)

            data = list(
                qs.values(
                    "employee_id__employee_first_name",
                    "employee_id__employee_last_name",
                    "employee_id__badge_id",
                    "leave_type_id__name",
                    "available_days",
                    "carryforward_days",
                    "total_leave_days",
                    "assigned_date",
                    "reset_date",
                    "expired_date",
                    "employee_id__gender",
                    "employee_id__email",
                    "employee_id__phone",
                    "employee_id__employee_work_info__department_id__department",
                    "employee_id__employee_work_info__job_role_id__job_role",
                    "employee_id__employee_work_info__job_position_id__job_position",
                    "employee_id__employee_work_info__employee_type_id__employee_type",
                    "employee_id__employee_work_info__experience",
                    "employee_id__employee_work_info__work_type_id__work_type",
                    "employee_id__employee_work_info__shift_id__employee_shift",
                    "employee_id__employee_work_info__company_id__company",
                )
            )
            choice_gender = {
                "male": "Male",
                "female": "Female",
                "other": "Other",
            }
            data_list = [
                {
                    "Name": f"{item['employee_id__employee_first_name']} {item['employee_id__employee_last_name']}",
                    "Badge ID": item["employee_id__badge_id"] or "-",
                    "Gender": choice_gender.get(item["employee_id__gender"]),
                    "Email": item["employee_id__email"],
                    "Phone": item["employee_id__phone"],
                    "Department": (
                        item[
                            "employee_id__employee_work_info__department_id__department"
                        ]
                        if item[
                            "employee_id__employee_work_info__department_id__department"
                        ]
                        else "-"
                    ),
                    "Job Position": (
                        item[
                            "employee_id__employee_work_info__job_position_id__job_position"
                        ]
                        if item[
                            "employee_id__employee_work_info__job_position_id__job_position"
                        ]
                        else "-"
                    ),
                    "Job Role": (
                        item["employee_id__employee_work_info__job_role_id__job_role"]
                        if item[
                            "employee_id__employee_work_info__job_role_id__job_role"
                        ]
                        else "-"
                    ),
                    "Work Type": (
                        item["employee_id__employee_work_info__work_type_id__work_type"]
                        if item[
                            "employee_id__employee_work_info__work_type_id__work_type"
                        ]
                        else "-"
                    ),
                    "Shift": (
                        item[
                            "employee_id__employee_work_info__shift_id__employee_shift"
                        ]
                        if item[
                            "employee_id__employee_work_info__shift_id__employee_shift"
                        ]
                        else "-"
                    ),
                    "Experience": item["employee_id__employee_work_info__experience"],
                    "Leave Type": item["leave_type_id__name"],
                    "Available Days": item["available_days"],
                    "Carryforward Days": item["carryforward_days"],
                    "Total Leave Days": item["total_leave_days"],
                    "Assigned Date": item["assigned_date"],
                    "Reset Date": item.get("reset_date", "-") or "-",
                    "Expired Date": item.get("expired_date", "-") or "-",
                    "Company": item[
                        "employee_id__employee_work_info__company_id__company"
                    ],
                }
                for item in data
            ]
        else:
            data_list = []  # Empty if invalid model selected

        return pivot_json_with_meta(data_list)

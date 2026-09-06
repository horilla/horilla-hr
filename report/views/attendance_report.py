import json
from datetime import datetime, time

from django.apps import apps
from django.db.models import CharField, Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import render

if apps.is_installed("attendance"):

    from attendance.filters import AttendanceFilters
    from attendance.models import Attendance
    from base.methods import has_export_access
    from base.models import Company
    from horilla.decorators import login_required, permission_required
    from report.dynamic_filter_utils import (
        RELATIVE_DATE_OPERATORS,
        parse_multi_value,
        resolve_relative_date_range,
    )
    from report.pivot_limits import pivot_json_with_meta

    # The pivot sums these columns client-side, so they have to be real
    # decimal hours. Formatting them as "HH.MM" put the minutes in the
    # fractional slot of a base-10 number -- 1:45 became 1.45, so two such
    # rows totalled 2.90 hours instead of 3.50. Returning a float keeps the
    # widget's aggregation arithmetic correct.
    def convert_time_to_decimal_w(time_str):
        """Duration ("H:MM" or time) -> decimal hours."""
        try:
            if isinstance(time_str, str):
                hours, minutes = map(int, time_str.split(":")[:2])
            elif isinstance(time_str, time):
                hours, minutes = time_str.hour, time_str.minute
            else:
                return 0.0

            return round(hours + minutes / 60, 2)
        except (ValueError, TypeError):
            return 0.0

    def convert_time_to_decimal(time_str):
        """Clock time ("H:MM:SS" or time) -> decimal hours."""
        try:
            if isinstance(time_str, str):  # When time comes as string
                t = datetime.strptime(time_str, "%H:%M:%S").time()
            elif isinstance(time_str, time):
                t = time_str
            else:
                return 0.0

            return round(t.hour + t.minute / 60, 2)
        except Exception:
            return 0.0

    # Maps the field ids used by the dynamic Filters modal to the ORM path
    # `attendance_pivot` filters on. "employee" is handled separately since it
    # is really two underlying columns (first/last name).
    DYNAMIC_FILTER_FIELD_PATHS = {
        "department": "employee_id__employee_work_info__department_id__department",
        "shift": "shift_id__employee_shift",
        "company": "employee_id__employee_work_info__company_id__company",
        "job_position": "employee_id__employee_work_info__job_position_id__job_position",
        "job_role": "employee_id__employee_work_info__job_role_id__job_role",
        "work_type": "work_type_id__work_type",
        "attendance_date": "attendance_date",
        "batch": "batch_attendance_id__title",
        "clock_in": "attendance_clock_in",
        "clock_out": "attendance_clock_out",
        "minimum_hour": "minimum_hour",
        "at_work_second": "at_work_second",
        "overtime_second": "overtime_second",
        "badge_id": "employee_id__badge_id",
        "gender": "employee_id__gender",
        "email": "employee_id__email",
        "experience": "employee_id__employee_work_info__experience",
    }

    NAME_FIELD_PATHS = {
        "employee": (
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
        ),
    }

    # In Time/Out Time (TimeField) and Min Hour (CharField storing "HH:MM")
    # are real times-of-day. The generic __iexact/__icontains lookups used
    # below for every other field are pure string comparisons and silently
    # match nothing against a TimeField unless the value happens to match
    # its stored "HH:MM:SS" format exactly (e.g. __iexact "09:19" against
    # "09:19:00" fails) -- these need a plain exact/gt/lt lookup instead,
    # which goes through Django's own field coercion and matches "09:19"
    # correctly regardless of stored seconds.
    TIME_FIELDS = {"clock_in", "clock_out", "minimum_hour"}

    # At Work/Overtime are stored as raw seconds (IntegerField), but the
    # Filters panel offers them as an HH:MM duration picker to match how the
    # report itself displays them (see format_seconds_to_time) -- convert
    # the submitted HH:MM[:SS] value to seconds before filtering.
    DURATION_FIELDS = {"at_work_second", "overtime_second"}

    def _duration_to_seconds(value):
        parts = value.split(":")
        try:
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            seconds = int(parts[2]) if len(parts) > 2 else 0
        except (ValueError, IndexError):
            return None
        return hours * 3600 + minutes * 60 + seconds

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

        if field in TIME_FIELDS:
            if operator == "is_empty":
                q = Q(**{f"{path}__isnull": True})
                if _field_accepts_empty_string(qs.model, path):
                    q |= Q(**{path: ""})
                return qs.filter(q)
            if not value:
                return qs
            if operator == "equals":
                return qs.filter(**{path: value})
            if operator == "not_equals":
                return qs.exclude(**{path: value})
            if operator == "greater_than":
                return qs.filter(**{f"{path}__gt": value})
            if operator == "less_than":
                return qs.filter(**{f"{path}__lt": value})
            if operator == "between":
                bounds = [part.strip() for part in value.split(",") if part.strip()]
                if len(bounds) == 2:
                    return qs.filter(**{f"{path}__range": (bounds[0], bounds[1])})
                return qs
            return qs

        if field in DURATION_FIELDS:
            if operator == "is_empty":
                return qs.filter(**{f"{path}__isnull": True})
            if operator == "between":
                bounds = [part.strip() for part in value.split(",") if part.strip()]
                if len(bounds) == 2:
                    seconds = [_duration_to_seconds(b) for b in bounds]
                    if all(s is not None for s in seconds):
                        return qs.filter(**{f"{path}__range": tuple(seconds)})
                return qs
            if not value:
                return qs
            seconds = _duration_to_seconds(value)
            if seconds is None:
                return qs
            if operator == "equals":
                return qs.filter(**{path: seconds})
            if operator == "not_equals":
                return qs.exclude(**{path: seconds})
            if operator == "greater_than":
                return qs.filter(**{f"{path}__gt": seconds})
            if operator == "less_than":
                return qs.filter(**{f"{path}__lt": seconds})
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
        '[{"field": "department", "operator": "contains", "value": "hr"},
          {"field": "department", "operator": "contains", "value": "sales",
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
    @permission_required(perm="attendance.view_attendance")
    def attendance_filter_field_options(request):
        """
        Distinct values available for a given dynamic-filter field, so the
        Filters panel can offer a searchable pick-list (like the rest of the
        app already does for relationship fields) instead of a freehand text
        box for fields where a fixed value is actually being matched.
        """
        field = request.GET.get("field")
        qs = Attendance.objects.all()

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
    @permission_required(perm="attendance.view_attendance")
    def attendance_report(request):
        company = "all"
        selected_company = request.session.get("selected_company")
        if selected_company != "all":
            company = Company.objects.filter(id=selected_company).first()

        return render(
            request,
            "report/attendance_report.html",
            {
                "company": company,
                "f": AttendanceFilters(),
                "export_access": has_export_access(request, Attendance),
            },
        )

    @login_required
    @permission_required(perm="attendance.view_attendance")
    def attendance_pivot(request):
        qs = Attendance.objects.all()
        filter_obj = AttendanceFilters(request.GET, queryset=qs)
        qs = filter_obj.qs
        qs = apply_dynamic_filters(qs, request)

        data = list(
            qs.values(
                "employee_id__employee_first_name",
                "employee_id__employee_last_name",
                "employee_id__badge_id",
                "attendance_date",
                "attendance_clock_in",
                "attendance_clock_out",
                "minimum_hour",
                "attendance_overtime",
                "at_work_second",
                "work_type_id__work_type",
                "shift_id__employee_shift",
                "attendance_day__day",
                "employee_id__gender",
                "employee_id__email",
                "employee_id__phone",
                "employee_id__employee_work_info__department_id__department",
                "employee_id__employee_work_info__job_role_id__job_role",
                "employee_id__employee_work_info__job_position_id__job_position",
                "employee_id__employee_work_info__employee_type_id__employee_type",
                "employee_id__employee_work_info__experience",
                "batch_attendance_id__title",
                "employee_id__employee_work_info__company_id__company",
            )
        )
        DAY = {
            "monday": "Monday",
            "tuesday": "Tuesday",
            "wednesday": "Wednesday",
            "thursday": "Thursday",
            "friday": "Friday",
            "saturday": "Saturday",
            "sunday": "Sunday",
        }
        choice_gender = {
            "male": "Male",
            "female": "Female",
            "other": "Other",
        }
        data_list = [
            {
                "Name": f"{item['employee_id__employee_first_name']} {item['employee_id__employee_last_name']}",
                "Badge Id": item["employee_id__badge_id"] or "-",
                "Gender": choice_gender.get(item["employee_id__gender"]),
                "Email": item["employee_id__email"],
                "Phone": item["employee_id__phone"],
                "Department": (
                    item["employee_id__employee_work_info__department_id__department"]
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
                    if item["employee_id__employee_work_info__job_role_id__job_role"]
                    else "-"
                ),
                "Work Type": (
                    item["work_type_id__work_type"]
                    if item["work_type_id__work_type"]
                    else "-"
                ),
                "Shift": (
                    item["shift_id__employee_shift"]
                    if item["shift_id__employee_shift"]
                    else "-"
                ),
                "Experience": item["employee_id__employee_work_info__experience"],
                "Attendance Date": item["attendance_date"],
                "Attendance Day": DAY.get(item["attendance_day__day"]),
                "Clock-in": format_time(item["attendance_clock_in"]),
                "Clock-out": format_time(item["attendance_clock_out"]),
                "At Work": format_seconds_to_time(item["at_work_second"]),
                "Minimum Hour": item["minimum_hour"],
                "Overtime": item["attendance_overtime"],
                "Batch": (
                    item["batch_attendance_id__title"]
                    if item["batch_attendance_id__title"]
                    else "-"
                ),
                "Company": item["employee_id__employee_work_info__company_id__company"],
                # For correct total
                "Clock-in Decimal": convert_time_to_decimal(
                    item["attendance_clock_in"]
                ),
                "Clock-out Decimal": convert_time_to_decimal(
                    item["attendance_clock_out"]
                ),
                "At Work Decimal": convert_time_to_decimal_w(
                    format_seconds_to_time(item["at_work_second"])
                ),
                "Minimum Hour Decimal": convert_time_to_decimal_w(item["minimum_hour"]),
                "Overtime Decimal": convert_time_to_decimal_w(
                    item["attendance_overtime"]
                ),
            }
            for item in data
        ]
        return pivot_json_with_meta(data_list)

    # Helper function to format time
    def format_time(time_value):
        if isinstance(time_value, str):  # In case time is string
            time_value = datetime.strptime(time_value, "%H:%M:%S").time()
        return time_value.strftime("%H:%M") if time_value else ""

    def format_seconds_to_time(seconds):
        """Convert seconds to HH:MM format."""
        try:
            seconds = int(seconds)
            hours, remainder = divmod(seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{hours:02}:{minutes:02}"
        except (ValueError, TypeError):
            return "00:00"

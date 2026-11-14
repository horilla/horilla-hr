import json

from django.apps import apps
from django.db.models import CharField, Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import render

if apps.is_installed("recruitment"):

    from base.methods import has_export_access
    from base.models import Company
    from horilla.decorators import login_required, permission_required
    from recruitment.filters import CandidateFilter, RecruitmentFilter
    from recruitment.models import Candidate, Recruitment
    from report.dynamic_filter_utils import (
        RELATIVE_DATE_OPERATORS,
        parse_multi_value,
        resolve_relative_date_range,
    )
    from report.pivot_limits import pivot_json_with_meta

    # Maps the field ids used by the dynamic Filters panel to the ORM path
    # `recruitment_pivot` filters on, keyed by the report's `model` type
    # ("candidate" / "recruitment" / "onboarding") since each type filters a
    # different base queryset with a different set of fields. Fields that are
    # really two underlying columns (first/last name) are handled separately
    # via NAME_FIELD_PATHS, same as employee_report.py.
    DYNAMIC_FILTER_FIELD_PATHS = {
        "candidate": {
            "name": "name",
            "mobile": "mobile",
            "email": "email",
            "country": "country",
            "state": "state",
            "city": "city",
            "address": "address",
            "dob": "dob",
            "source": "source",
            "recruitment": "recruitment_id__title",
            "job_position": "job_position_id__job_position",
            "department": "job_position_id__department_id__department",
            "hired": "hired",
            "offer_letter_status": "offer_letter_status",
            "gender": "gender",
            "stage_type": "stage_id__stage_type",
            "current_stage": "stage_id__stage",
            "canceled": "canceled",
            "recruitment_status": "recruitment_id__closed",
            "vacancy": "recruitment_id__vacancy",
            "company": "recruitment_id__company_id__company",
        },
        "recruitment": {
            "title": "title",
            "start_date": "start_date",
            "end_date": "end_date",
            "is_closed": "closed",
            "is_published": "is_published",
            "is_active": "is_active",
            "job_position": "open_positions__job_position",
            "company": "company_id__company",
            "vacancy": "vacancy",
            "manager_badge_id": "recruitment_managers__badge_id",
        },
        "onboarding": {
            "recruitment": "recruitment_id__title",
            "company": "recruitment_id__company_id__company",
            "stage_title": "stage_title",
            "task_title": "onboarding_task__task_title",
            "stage_manager_badge_id": "employee_id__badge_id",
            "task_manager_badge_id": "onboarding_task__employee_id__badge_id",
            "candidates": "onboarding_task__candidates__name",
        },
    }

    NAME_FIELD_PATHS = {
        "recruitment": {
            "managers": (
                "recruitment_managers__employee_first_name",
                "recruitment_managers__employee_last_name",
            ),
        },
        "onboarding": {
            "stage_manager": (
                "employee_id__employee_first_name",
                "employee_id__employee_last_name",
            ),
            "task_manager": (
                "onboarding_task__employee_id__employee_first_name",
                "onboarding_task__employee_id__employee_last_name",
            ),
        },
    }

    # "Application Form"/"Inside Software"/"Other" as shown to the user don't
    # normalize back to their stored codes ("application"/"software"/"other")
    # via the usual lowercase+underscore trick (payroll's `status`, leave's
    # breakdown fields) since the display labels don't map 1:1 by just
    # removing spaces -- an explicit reverse lookup is needed instead.
    SOURCE_DISPLAY_TO_CODE = {
        "application form": "application",
        "inside software": "software",
        "other": "other",
    }

    # Fields backed by a BooleanField -- these can't use __iexact/__icontains
    # (Django doesn't support those lookups on booleans), so the value coming
    # from the Filters panel ("True"/"False") has to be coerced to an actual
    # bool before filtering instead.
    BOOLEAN_FIELDS = {
        "candidate": {"hired", "canceled", "recruitment_status"},
        "recruitment": {"is_closed", "is_published", "is_active"},
        "onboarding": set(),
    }

    # Fields whose ORM path crosses a many-valued relation (M2M, or a reverse
    # FK such as OnboardingStage -> OnboardingTask) -- filtering on these can
    # multiply the base rows, so a `.distinct()` after filtering is required
    # to avoid duplicate rows leaking into the pivot data.
    MULTI_VALUED_FIELDS = {
        "candidate": set(),
        "recruitment": {"managers", "job_position", "manager_badge_id"},
        "onboarding": {
            "task_title",
            "stage_manager",
            "task_manager",
            "stage_manager_badge_id",
            "task_manager_badge_id",
            "candidates",
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

    def _to_bool(value):
        return str(value).strip().lower() in ("true", "1", "yes")

    def _apply_dynamic_filter_row(qs, model_type, field, operator, value):
        """
        Apply one (field, operator, value) row from the Filters panel to the
        queryset for the given model type. Unknown fields/operators or rows
        missing a required value are ignored rather than raising, since a
        still-being-filled-in row shouldn't break the whole request.
        """
        name_paths = NAME_FIELD_PATHS.get(model_type, {})
        multi_valued = MULTI_VALUED_FIELDS.get(model_type, set())

        if field in name_paths:
            first_path, last_path = name_paths[field]
            if operator == "is_empty":
                qs = qs.filter(
                    Q(**{f"{first_path}__isnull": True}) | Q(**{first_path: ""})
                )
                return qs.distinct() if field in multi_valued else qs
            if not value:
                return qs

            # Options are offered (and picked) as the combined "First Last"
            # string, so match against first+last concatenated together
            # rather than against each half separately -- a two-word name
            # can never equal/contain just the first or just the last name
            # column alone.
            full_name = f"_{model_type}_{field}_full_name"
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
                    qs = qs.filter(**{f"{full_name}__in": values})
                else:
                    qs = qs.filter(**{f"{full_name}__iexact": values[0]})
            elif operator == "not_equals":
                values = parse_multi_value(value)
                if len(values) > 1:
                    qs = qs.exclude(**{f"{full_name}__in": values})
                else:
                    qs = qs.exclude(**{f"{full_name}__iexact": values[0]})
            elif operator == "contains":
                qs = qs.filter(**{f"{full_name}__icontains": value})
            else:
                return qs
            return qs.distinct() if field in multi_valued else qs

        path = DYNAMIC_FILTER_FIELD_PATHS.get(model_type, {}).get(field)
        if not path:
            return qs

        if field in BOOLEAN_FIELDS.get(model_type, set()):
            if operator == "is_empty":
                return qs.filter(**{f"{path}__isnull": True})
            if not value:
                return qs
            bool_values = [_to_bool(v) for v in parse_multi_value(value)]
            if operator == "equals":
                qs = qs.filter(**{f"{path}__in": bool_values})
            elif operator == "not_equals":
                qs = qs.exclude(**{f"{path}__in": bool_values})
            else:
                return qs
            return qs.distinct() if field in multi_valued else qs

        if operator == "is_empty":
            q = Q(**{f"{path}__isnull": True})
            if _field_accepts_empty_string(qs.model, path):
                q |= Q(**{path: ""})
            qs = qs.filter(q)
        elif operator in RELATIVE_DATE_OPERATORS:
            qs = qs.filter(**{f"{path}__range": resolve_relative_date_range(operator)})
        elif not value:
            return qs
        elif operator == "equals":
            values = parse_multi_value(value)
            if field == "source":
                values = [
                    SOURCE_DISPLAY_TO_CODE.get(v.strip().lower(), v) for v in values
                ]
            if len(values) > 1:
                qs = qs.filter(**{f"{path}__in": values})
            else:
                qs = qs.filter(**{f"{path}__iexact": values[0]})
        elif operator == "not_equals":
            values = parse_multi_value(value)
            if field == "source":
                values = [
                    SOURCE_DISPLAY_TO_CODE.get(v.strip().lower(), v) for v in values
                ]
            if len(values) > 1:
                qs = qs.exclude(**{f"{path}__in": values})
            else:
                qs = qs.exclude(**{f"{path}__iexact": values[0]})
        elif operator == "contains":
            qs = qs.filter(**{f"{path}__icontains": value})
        elif operator == "greater_than":
            qs = qs.filter(**{f"{path}__gt": value})
        elif operator == "less_than":
            qs = qs.filter(**{f"{path}__lt": value})
        elif operator == "between":
            bounds = [part.strip() for part in value.split(",") if part.strip()]
            if len(bounds) == 2:
                qs = qs.filter(**{f"{path}__range": (bounds[0], bounds[1])})
            else:
                return qs
        else:
            return qs

        return qs.distinct() if field in multi_valued else qs

    def apply_dynamic_filters(qs, request, model_type):
        """
        Apply the Filters panel's field/operator/value rows, sent as a JSON
        array in the `dynamic_filters` query param, e.g.
        '[{"field": "company", "operator": "contains", "value": "abc"},
          {"field": "company", "operator": "contains", "value": "xyz",
           "connector": "or"}]', scoped to the given `model_type`
        ("candidate" / "recruitment" / "onboarding").

        Each row (after the first) carries a `connector` ("and"/"or",
        default "and") saying how it combines with everything before it,
        evaluated left to right with no precedence/grouping. Each row is
        applied fresh against the original queryset rather than chaining
        `.filter()` calls (which always ANDs at the SQL level regardless of
        intent); the per-row results are combined with QuerySet `&`/`|`,
        which correctly combine their WHERE clauses (and any
        `.annotate()`/`.distinct()` a row added) as AND/OR.
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
    @permission_required(perm="recruitment.view_recruitment")
    def recruitment_filter_field_options(request):
        """
        Distinct values available for a given dynamic-filter field on a given
        model type, so the Filters panel can offer a searchable pick-list
        (like the rest of the app already does for relationship fields)
        instead of a freehand text box for fields where a fixed value is
        actually being matched.
        """
        model_type = request.GET.get("model", "candidate")
        field = request.GET.get("field")

        if model_type == "candidate":
            qs = Candidate.objects.all()
        elif model_type == "recruitment":
            qs = Recruitment.objects.all()
        elif model_type == "onboarding" and apps.is_installed("onboarding"):
            OnboardingStage = apps.get_model("onboarding", "OnboardingStage")
            qs = OnboardingStage.objects.all()
        else:
            return JsonResponse({"options": []})

        name_paths = NAME_FIELD_PATHS.get(model_type, {})
        if field in name_paths:
            first_path, last_path = name_paths[field]
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

        if field in BOOLEAN_FIELDS.get(model_type, set()):
            return JsonResponse({"options": ["True", "False"]})

        values = qs.exclude(**{f"{path}__isnull": True})
        if _field_accepts_empty_string(qs.model, path):
            values = values.exclude(**{path: ""})
        values = values.values_list(path, flat=True).distinct()
        # Some fields have leaked the literal string "None" as sentinel junk
        options = sorted({str(v) for v in values if str(v).strip().lower() != "none"})
        return JsonResponse({"options": options})

    @login_required
    @permission_required(perm="recruitment.view_recruitment")
    def recruitment_report(request):
        company = "all"
        selected_company = request.session.get("selected_company")
        if selected_company != "all":
            company = Company.objects.filter(id=selected_company).first()
        if apps.is_installed("onboarding"):
            OnboardingStage = apps.get_model("onboarding", "OnboardingStage")
            onboarding_export_access = has_export_access(request, OnboardingStage)
        else:
            onboarding_export_access = False
        return render(
            request,
            "report/recruitment_report.html",
            {
                "company": company,
                "f": CandidateFilter(),
                "fr": RecruitmentFilter(),
                "export_access_map": {
                    "candidate": has_export_access(request, Candidate),
                    "recruitment": has_export_access(request, Recruitment),
                    "onboarding": onboarding_export_access,
                },
            },
        )

    @login_required
    @permission_required(perm="recruitment.view_recruitment")
    def recruitment_pivot(request):
        model_type = request.GET.get("model", "candidate")  # Default to Candidate

        if model_type == "candidate":
            qs = Candidate.objects.all()
            filter_obj = CandidateFilter(request.GET, queryset=qs)
            qs = filter_obj.qs
            qs = apply_dynamic_filters(qs, request, model_type)

            data = list(
                qs.values(
                    "name",
                    "recruitment_id__title",
                    "job_position_id__job_position",
                    "stage_id__stage",
                    "email",
                    "mobile",
                    "gender",
                    "offer_letter_status",
                    "recruitment_id__closed",
                    "recruitment_id__vacancy",
                    "country",
                    "recruitment_id__company_id__company",
                    "address",
                    "dob",
                    "state",
                    "city",
                    "source",
                    "job_position_id__department_id__department",
                )
            )
            choice_gender = {
                "male": "Male",
                "female": "Female",
                "other": "Other",
            }
            OFFER_LETTER_STATUS = {
                "not_sent": "Not Sent",
                "sent": "Sent",
                "accepted": "Accepted",
                "rejected": "Rejected",
                "joined": "Joined",
            }
            SOURCE_CHOICE = {
                "application": "Application Form",
                "software": "Inside Software",
                "other": "Other",
            }

            data_list = [
                {
                    "Candidate": item["name"],
                    "Email": item["email"],
                    "Phone": item["mobile"],
                    "Gender": choice_gender.get(item["gender"]),
                    "Address": item["address"],
                    "Date Of Birth": item["dob"],
                    "Country": item["country"] if item["country"] else "-",
                    "State": item["state"] if item["state"] else "-",
                    "City": item["city"] if item["city"] else "-",
                    "Source": (
                        SOURCE_CHOICE.get(item["source"]) if item["source"] else "-"
                    ),
                    "Job Position": item["job_position_id__job_position"],
                    "Department": item["job_position_id__department_id__department"],
                    "Offer Letter": OFFER_LETTER_STATUS.get(
                        item["offer_letter_status"]
                    ),
                    "Recruitment": item["recruitment_id__title"],
                    "Current Stage": item["stage_id__stage"],
                    "Recruitment Status": (
                        "Closed" if item["recruitment_id__closed"] else "Open"
                    ),
                    "Vacancy": item["recruitment_id__vacancy"],
                    "Company": item["recruitment_id__company_id__company"],
                }
                for item in data
            ]
        elif model_type == "recruitment":
            qs = Recruitment.objects.all()
            filter_obj = RecruitmentFilter(request.GET, queryset=qs)
            qs = filter_obj.qs
            qs = apply_dynamic_filters(qs, request, model_type)
            data = list(
                qs.values(
                    "title",
                    "vacancy",
                    "closed",
                    "open_positions__job_position",
                    "start_date",
                    "end_date",
                    "is_published",
                    "recruitment_managers__employee_first_name",
                    "recruitment_managers__employee_last_name",
                    "recruitment_managers__badge_id",
                    "company_id__company",
                )
            )
            data_list = [
                {
                    "Recruitment": item["title"],
                    "Manager": f"{item['recruitment_managers__employee_first_name']} {item['recruitment_managers__employee_last_name']}",
                    "Manager Badge ID": item["recruitment_managers__badge_id"] or "-",
                    "Closed": "Closed" if item["closed"] else "Open",
                    "Status": "Published" if item["is_published"] else "Not Published",
                    "Start Date": item["start_date"],
                    "End Date": item["end_date"],
                    "Job Position": item["open_positions__job_position"],
                    "Vacancy": item["vacancy"],
                    "Company": item["company_id__company"],
                }
                for item in data
            ]
        elif model_type == "onboarding" and apps.is_installed("onboarding"):
            from onboarding.filters import OnboardingStageFilter

            OnboardingStage = apps.get_model("onboarding", "OnboardingStage")
            qs = OnboardingStage.objects.all()
            filter_obj = OnboardingStageFilter(request.GET, queryset=qs)
            qs = filter_obj.qs
            qs = apply_dynamic_filters(qs, request, model_type)

            data = list(
                qs.values(
                    "stage_title",
                    "recruitment_id__title",
                    "employee_id__employee_first_name",
                    "employee_id__employee_last_name",
                    "employee_id__badge_id",
                    "onboarding_task__task_title",
                    "onboarding_task__employee_id__employee_first_name",
                    "onboarding_task__employee_id__employee_last_name",
                    "onboarding_task__employee_id__badge_id",
                    "onboarding_task__candidates__name",
                    "recruitment_id__company_id__company",
                )
            )

            data_list = [
                {
                    "Recruitment": item["recruitment_id__title"],
                    "Stage": item["stage_title"],
                    "Stage Manager": (
                        f"{item['employee_id__employee_first_name']} {item['employee_id__employee_last_name']}"
                        if item["employee_id__employee_first_name"]
                        else "-"
                    ),
                    "Stage Manager Badge ID": item["employee_id__badge_id"] or "-",
                    "Task": (
                        item["onboarding_task__task_title"]
                        if item["onboarding_task__task_title"]
                        else "-"
                    ),
                    "Task Manager": (
                        f"{item['onboarding_task__employee_id__employee_first_name']} {item['onboarding_task__employee_id__employee_last_name']}"
                        if item["onboarding_task__employee_id__employee_first_name"]
                        else "-"
                    ),
                    "Task Manager Badge ID": (
                        item["onboarding_task__employee_id__badge_id"] or "-"
                    ),
                    "Candidates": (
                        item["onboarding_task__candidates__name"]
                        if item["onboarding_task__candidates__name"]
                        else "-"
                    ),
                    "Company": (
                        item["recruitment_id__company_id__company"]
                        if item["recruitment_id__company_id__company"]
                        else "-"
                    ),
                }
                for item in data
            ]
        else:
            data_list = []
        return pivot_json_with_meta(data_list)

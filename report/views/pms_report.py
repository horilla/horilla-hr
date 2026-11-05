import json

from django.apps import apps
from django.db.models import CharField, Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import render

if apps.is_installed("pms"):

    from base.methods import has_export_access
    from base.models import Company
    from horilla.decorators import login_required, permission_required
    from pms.filters import EmployeeObjectiveFilter, FeedbackFilter
    from pms.models import EmployeeKeyResult, EmployeeObjective, Feedback, Objective
    from pms.views import objective_filter_pagination
    from report.dynamic_filter_utils import (
        RELATIVE_DATE_OPERATORS,
        parse_multi_value,
        resolve_relative_date_range,
    )
    from report.pivot_limits import pivot_json_with_meta

    # Maps the field ids used by the dynamic Filters panel to the ORM path
    # `pms_pivot` filters on, scoped per `model` type ("objective",
    # "feedback", "employeeobjective") since each report type is a
    # different base queryset with its own set of filterable fields.
    DYNAMIC_FILTER_FIELD_PATHS = {
        "objective": {
            "duration": "duration",
            "key_result": "key_result_id__title",
            "company": "company_id__company",
            "manager_badge_id": "managers__badge_id",
            "assignee_badge_id": "assignees__badge_id",
            "assignee_department": "assignees__employee_work_info__department_id__department",
            "assignee_job_position": "assignees__employee_work_info__job_position_id__job_position",
            "assignee_job_role": "assignees__employee_work_info__job_role_id__job_role",
        },
        "feedback": {
            "review_cycle": "review_cycle",
            "status": "status",
            "start_date": "start_date",
            "end_date": "end_date",
            "manager_badge_id": "manager_id__badge_id",
            "employee_badge_id": "employee_id__badge_id",
        },
        "employeeobjective": {
            "key_result": "key_result_id__title",
            "status": "status",
            "start_date": "start_date",
            "end_date": "end_date",
            "employee_badge_id": "employee_objective_id__employee_id__badge_id",
            "department": "employee_objective_id__employee_id__employee_work_info__department_id__department",
            "job_position": "employee_objective_id__employee_id__employee_work_info__job_position_id__job_position",
            "job_role": "employee_objective_id__employee_id__employee_work_info__job_role_id__job_role",
            "start_value": "start_value",
            "current_value": "current_value",
            "target_value": "target_value",
        },
    }

    # Fields that are really two underlying columns (first/last name),
    # scoped per model type the same way as DYNAMIC_FILTER_FIELD_PATHS.
    # "managers"/"assignees"/"colleague"/"subordinate" reach Employee
    # through a ManyToMany relation -- Concat/annotate works the same way
    # through an M2M join as it does through a single FK.
    # NAME_FIELD_PATHS entries that reach Employee through a M2M relation
    # AND whose branch of pms_pivot iterates model instances directly
    # (rather than a fanned-out `.values()` queryset, like "objective"'s
    # own M2M fields already are) -- for these, two employees sharing the
    # exact same full name could otherwise make a single Feedback match
    # more than one joined row and get its rows duplicated in the report.
    M2M_DISTINCT_FIELDS = {
        "feedback": {"colleague", "subordinate"},
    }

    NAME_FIELD_PATHS = {
        "objective": {
            "managers": (
                "managers__employee_first_name",
                "managers__employee_last_name",
            ),
            "assignees": (
                "assignees__employee_first_name",
                "assignees__employee_last_name",
            ),
        },
        "feedback": {
            "employee": (
                "employee_id__employee_first_name",
                "employee_id__employee_last_name",
            ),
            "manager": (
                "manager_id__employee_first_name",
                "manager_id__employee_last_name",
            ),
            "colleague": (
                "colleague_id__employee_first_name",
                "colleague_id__employee_last_name",
            ),
            "subordinate": (
                "subordinate_id__employee_first_name",
                "subordinate_id__employee_last_name",
            ),
        },
        "employeeobjective": {
            "employee": (
                "employee_objective_id__employee_id__employee_first_name",
                "employee_objective_id__employee_id__employee_last_name",
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
        queryset, scoped to `model_type`. Unknown fields/operators or rows
        missing a required value are ignored rather than raising, since a
        still-being-filled-in row shouldn't break the whole request.
        """
        name_paths = NAME_FIELD_PATHS.get(model_type, {})
        if field in name_paths:
            first_path, last_path = name_paths[field]
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
            full_name = f"_{model_type}_{field}_full_name"
            qs = qs.annotate(
                **{
                    full_name: Concat(
                        first_path, Value(" "), last_path, output_field=CharField()
                    )
                }
            )
            needs_distinct = field in M2M_DISTINCT_FIELDS.get(model_type, set())
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
                needs_distinct = False
            return qs.distinct() if needs_distinct else qs

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

    def apply_dynamic_filters(qs, request, model_type):
        """
        Apply the Filters panel's field/operator/value rows, sent as a JSON
        array in the `dynamic_filters` query param, e.g.
        '[{"field": "status", "operator": "equals", "value": "Closed"},
          {"field": "status", "operator": "equals", "value": "Open",
           "connector": "or"}]', scoped to the given `model_type`.

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
    @permission_required(perm="pms.view_objective")
    def pms_filter_field_options(request):
        """
        Distinct values available for a given dynamic-filter field (scoped
        to the selected `model` report type), so the Filters panel can
        offer a searchable pick-list instead of a freehand text box for
        fields where a fixed value is actually being matched.
        """
        field = request.GET.get("field")
        model_type = request.GET.get("model", "objective")

        if model_type == "feedback":
            qs = Feedback.objects.all()
        elif model_type == "employeeobjective":
            qs = EmployeeKeyResult.objects.all()
        else:
            qs = Objective.objects.all()

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

        values = qs.exclude(**{f"{path}__isnull": True})
        if _field_accepts_empty_string(qs.model, path):
            values = values.exclude(**{path: ""})
        values = values.values_list(path, flat=True).distinct()
        # Some fields have leaked the literal string "None" as sentinel junk
        options = sorted({str(v) for v in values if str(v).strip().lower() != "none"})
        return JsonResponse({"options": options})

    @login_required
    @permission_required(perm="pms.view_objective")
    def pms_report(request):

        company = "all"
        selected_company = request.session.get("selected_company")
        if selected_company != "all":
            company = Company.objects.filter(id=selected_company).first()
        employee = request.user.employee_get
        objective_own = EmployeeObjective.objects.filter(
            employee_id=employee, archive=False
        )
        objective_own = objective_own.distinct()

        feedback = request.GET.get(
            "search"
        )  # if the search is none the filter will works
        if feedback is None:
            feedback = ""
        self_feedback = Feedback.objects.filter(employee_id=employee).filter(
            review_cycle__icontains=feedback
        )
        initial_data = {"archive": False}
        feedback_filter_own = FeedbackFilter(
            request.GET or initial_data, queryset=self_feedback
        )

        context = objective_filter_pagination(request, objective_own)
        cm = {
            "company": company,
            "feedback_filter_form": feedback_filter_own.form,
            "emp_obj_form": EmployeeObjectiveFilter(),
            "export_access_map": {
                "objective": has_export_access(request, Objective),
                "feedback": has_export_access(request, Feedback),
                "employeeobjective": has_export_access(request, EmployeeKeyResult),
            },
        }
        context.update(cm)

        return render(request, "report/pms_report.html", context)

    @login_required
    @permission_required(perm="pms.view_objective")
    def pms_pivot(request):

        model_type = request.GET.get("model", "objective")
        if model_type == "objective":
            qs = Objective.objects.all()
            qs = apply_dynamic_filters(qs, request, "objective")

            data = list(
                qs.values(
                    "title",
                    "managers__employee_first_name",
                    "managers__employee_last_name",
                    "managers__badge_id",
                    "assignees__employee_first_name",
                    "assignees__employee_last_name",
                    "assignees__badge_id",
                    "key_result_id__title",
                    "key_result_id__target_value",
                    "duration_unit",
                    "duration",
                    "company_id__company",
                    "key_result_id__progress_type",
                    "key_result_id__duration",
                    "assignees__employee_work_info__department_id__department",
                    "assignees__employee_work_info__job_role_id__job_role",
                    "assignees__employee_work_info__job_position_id__job_position",
                )
            )
            DURATION_UNIT = {
                "days": "Days",
                "months": "Months",
                "years": "Years",
            }
            KEY_RESULT_TARGET = {
                "%": "%",
                "#": "Number",
                "Currency": "Currency",
            }
            data_list = [
                {
                    "Objective": item["title"],
                    "Objective Duration": f'{item["duration"]} {DURATION_UNIT.get(item["duration_unit"])}',
                    "Manager": (
                        f"{item['managers__employee_first_name']} {item['managers__employee_last_name']}"
                        if item["managers__employee_first_name"]
                        else "-"
                    ),
                    "Manager Badge ID": item["managers__badge_id"] or "-",
                    "Assignees": f"{item['assignees__employee_first_name']} {item['assignees__employee_last_name']}",
                    "Assignee Badge ID": item["assignees__badge_id"] or "-",
                    "Assignee Department": (
                        item["assignees__employee_work_info__department_id__department"]
                        if item[
                            "assignees__employee_work_info__department_id__department"
                        ]
                        else "-"
                    ),
                    "Assignee Job Position": (
                        item[
                            "assignees__employee_work_info__job_position_id__job_position"
                        ]
                        if item[
                            "assignees__employee_work_info__job_position_id__job_position"
                        ]
                        else "-"
                    ),
                    "Assignee Job Role": (
                        item["assignees__employee_work_info__job_role_id__job_role"]
                        if item["assignees__employee_work_info__job_role_id__job_role"]
                        else "-"
                    ),
                    "Key Results": item["key_result_id__title"],
                    "Key Result Duration": f'{item["key_result_id__duration"]} {"Days"}',
                    "Key Result Target": f'{item["key_result_id__target_value"]} {KEY_RESULT_TARGET.get(item["key_result_id__progress_type"])}',
                    "Company": item["company_id__company"],
                }
                for item in data
            ]
        elif model_type == "feedback":

            data_list = []

            PERIOD = {
                "days": "Days",
                "months": "Months",
                "years": "Years",
            }

            feedbacks = Feedback.objects.select_related(
                "manager_id", "employee_id", "question_template_id"
            ).prefetch_related(
                "colleague_id",
                "subordinate_id",
                "question_template_id__question",
                "feedback_answer__question_id",  # related_name
                "feedback_answer__employee_id",
            )

            # Dynamic Filters panel rows (field/operator/value), scoped to
            # this model type. `start_date`/`end_date` filter the Feedback's
            # own start_date/end_date fields (previously this filtered
            # created_at instead, which didn't match what "Start Date"/
            # "End Date" mean for a Feedback record -- fixed here).
            feedbacks = apply_dynamic_filters(feedbacks, request, "feedback")

            for feedback in feedbacks:
                manager = (
                    f"{feedback.manager_id.employee_first_name} {feedback.manager_id.employee_last_name}"
                    if feedback.manager_id
                    else ""
                )
                manager_badge_id = (
                    feedback.manager_id.badge_id if feedback.manager_id else "-"
                ) or "-"
                employee = (
                    f"{feedback.employee_id.employee_first_name} {feedback.employee_id.employee_last_name}"
                    if feedback.employee_id
                    else ""
                )
                employee_badge_id = (
                    feedback.employee_id.badge_id if feedback.employee_id else "-"
                ) or "-"

                answerable_employees = list(feedback.colleague_id.all()) + list(
                    feedback.subordinate_id.all()
                )
                answerable_names = (
                    ", ".join(
                        f"{e.employee_first_name} {e.employee_last_name}"
                        for e in answerable_employees
                    )
                    or "-"
                )

                questions = feedback.question_template_id.question.all()

                # Fetch ALL answers for this feedback and map them grouped by question
                answers = feedback.feedback_answer.select_related(
                    "employee_id", "question_id"
                )

                for question in questions:
                    question_answers = [
                        ans for ans in answers if ans.question_id_id == question.id
                    ]

                    # If no one answered this question, still show the question
                    if not question_answers:
                        data_list.append(
                            {
                                "Title": feedback.review_cycle,
                                "Manager": manager,
                                "Manager Badge ID": manager_badge_id,
                                "Employee": employee,
                                "Employee Badge ID": employee_badge_id,
                                "Answerable Employees": answerable_names,
                                "Questions": question.question,
                                "Answer": "",
                                "Answered Employees": "-",
                                "Status": feedback.status,
                                "Start Date": feedback.start_date,
                                "End Date": feedback.end_date,
                                "Cyclic": ("Yes" if feedback.cyclic_feedback else "No"),
                                "Cycle Period": (
                                    f"{feedback.cyclic_feedback_days_count} {PERIOD.get(feedback.cyclic_feedback_period)}"
                                    if feedback.cyclic_feedback_days_count
                                    else "-"
                                ),
                            }
                        )
                    else:
                        for answer in question_answers:
                            answer_value = (
                                answer.answer.get("answer") if answer.answer else ""
                            )
                            answered_by = (
                                f"{answer.employee_id.employee_first_name} {answer.employee_id.employee_last_name}"
                                if answer.employee_id
                                else "-"
                            )
                            data_list.append(
                                {
                                    "Title": feedback.review_cycle,
                                    "Manager": manager,
                                    "Manager Badge ID": manager_badge_id,
                                    "Employee": employee,
                                    "Employee Badge ID": employee_badge_id,
                                    "Answerable Employees": answerable_names,
                                    "Questions": question.question,
                                    "Answer": answer_value,
                                    "Answered Employees": answered_by,
                                    "Status": feedback.status,
                                    "Start Date": feedback.start_date,
                                    "End Date": feedback.end_date,
                                    "Cyclic": (
                                        "Yes" if feedback.cyclic_feedback else "No"
                                    ),
                                    "Cycle Period": (
                                        f"{feedback.cyclic_feedback_days_count} {PERIOD.get(feedback.cyclic_feedback_period)}"
                                        if feedback.cyclic_feedback_days_count
                                        else "-"
                                    ),
                                }
                            )
        elif model_type == "employeeobjective":

            qs = EmployeeKeyResult.objects.all()
            qs = apply_dynamic_filters(qs, request, "employeeobjective")

            data = list(
                qs.values(
                    "key_result",
                    "employee_objective_id__employee_id__employee_first_name",
                    "employee_objective_id__employee_id__employee_last_name",
                    "employee_objective_id__employee_id__badge_id",
                    "employee_objective_id__objective_id__title",
                    "employee_objective_id__objective_id__duration_unit",
                    "employee_objective_id__objective_id__duration",
                    "start_value",
                    "current_value",
                    "target_value",
                    "start_date",
                    "end_date",
                    "status",
                    "progress_type",
                    "employee_objective_id__employee_id__employee_work_info__department_id__department",
                    "employee_objective_id__employee_id__employee_work_info__job_role_id__job_role",
                    "employee_objective_id__employee_id__employee_work_info__job_position_id__job_position",
                )
            )
            DURATION_UNIT = {
                "days": "Days",
                "months": "Months",
                "years": "Years",
            }
            KEY_RESULT_TARGET = {
                "%": "%",
                "#": "Number",
                "Currency": "Currency",
            }

            data_list = [
                {
                    "Employee": f"{item['employee_objective_id__employee_id__employee_first_name']} {item['employee_objective_id__employee_id__employee_last_name']}",
                    "Employee Badge ID": (
                        item["employee_objective_id__employee_id__badge_id"] or "-"
                    ),
                    "Department": (
                        item[
                            "employee_objective_id__employee_id__employee_work_info__department_id__department"
                        ]
                        if item[
                            "employee_objective_id__employee_id__employee_work_info__department_id__department"
                        ]
                        else "-"
                    ),
                    "Job Position": (
                        item[
                            "employee_objective_id__employee_id__employee_work_info__job_position_id__job_position"
                        ]
                        if item[
                            "employee_objective_id__employee_id__employee_work_info__job_position_id__job_position"
                        ]
                        else "-"
                    ),
                    "Job Role": (
                        item[
                            "employee_objective_id__employee_id__employee_work_info__job_role_id__job_role"
                        ]
                        if item[
                            "employee_objective_id__employee_id__employee_work_info__job_role_id__job_role"
                        ]
                        else "-"
                    ),
                    "Employee Keyresult": item["key_result"],
                    "Objective": item["employee_objective_id__objective_id__title"],
                    "Objective Duration": f'{item["employee_objective_id__objective_id__duration"]} {DURATION_UNIT.get(item["employee_objective_id__objective_id__duration_unit"])}',
                    "Keyresult Start Value": f'{item["start_value"]} {KEY_RESULT_TARGET.get(item["progress_type"])}',
                    "Keyresult Target Value": f'{item["target_value"]} {KEY_RESULT_TARGET.get(item["progress_type"])}',
                    "Keyresult Current Value": (
                        f'{item["current_value"]} {KEY_RESULT_TARGET.get(item["progress_type"])}'
                        if item["current_value"]
                        else "-"
                    ),
                    "Keyresult Start Date": (
                        item["start_date"] if item["start_date"] else "-"
                    ),
                    "Keyresult End Date": item["end_date"] if item["end_date"] else "-",
                    "status": item["status"],
                }
                for item in data
            ]

        else:
            data_list = []

        return pivot_json_with_meta(data_list)

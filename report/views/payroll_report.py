import json

from django.apps import apps
from django.db.models import CharField, Q, Value
from django.db.models.functions import Concat
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_date

if apps.is_installed("payroll"):

    from base.methods import has_export_access
    from base.models import Company
    from horilla.decorators import login_required, permission_required
    from payroll.filters import PayslipFilter
    from payroll.models.models import Payslip
    from report.dynamic_filter_utils import (
        RELATIVE_DATE_OPERATORS,
        parse_multi_value,
        resolve_relative_date_range,
    )
    from report.pivot_limits import pivot_json_with_meta

    # Maps the field ids used by the dynamic Filters modal to the ORM path
    # `payroll_pivot` filters on, scoped per `model` type ("payslip" /
    # "allowance") since each report type exposes a different (though
    # overlapping) set of fields -- both ultimately query the same Payslip
    # model, just with different filterable columns.
    DYNAMIC_FILTER_FIELD_PATHS = {
        "payslip": {
            "status": "status",
            "group_name": "group_name",
            "start_date": "start_date",
            "end_date": "end_date",
            "gross_pay": "gross_pay",
            "deduction": "deduction",
            "net_pay": "net_pay",
            "contract_wage": "contract_wage",
            "basic_pay": "basic_pay",
            "badge_id": "employee_id__badge_id",
            "gender": "employee_id__gender",
            "email": "employee_id__email",
            "phone": "employee_id__phone",
            "department": "employee_id__employee_work_info__department_id__department",
            "job_position": "employee_id__employee_work_info__job_position_id__job_position",
            "job_role": "employee_id__employee_work_info__job_role_id__job_role",
            "work_type": "employee_id__employee_work_info__work_type_id__work_type",
            "shift": "employee_id__employee_work_info__shift_id__employee_shift",
            "employee_type": "employee_id__employee_work_info__employee_type_id__employee_type",
            "experience": "employee_id__employee_work_info__experience",
        },
        "allowance": {
            "status": "status",
            "group_name": "group_name",
            "start_date": "start_date",
            "end_date": "end_date",
            "badge_id": "employee_id__badge_id",
            "gender": "employee_id__gender",
            "email": "employee_id__email",
            "phone": "employee_id__phone",
            "department": "employee_id__employee_work_info__department_id__department",
            "job_position": "employee_id__employee_work_info__job_position_id__job_position",
            "job_role": "employee_id__employee_work_info__job_role_id__job_role",
            "work_type": "employee_id__employee_work_info__work_type_id__work_type",
            "shift": "employee_id__employee_work_info__shift_id__employee_shift",
        },
    }

    # "employee" is really two underlying columns (first/last name), handled
    # separately -- same as NAME_FIELD_PATHS in report/views/employee_report.py.
    NAME_FIELD_PATHS = {
        "payslip": {
            "employee": (
                "employee_id__employee_first_name",
                "employee_id__employee_last_name",
            ),
        },
        "allowance": {
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
        Apply one (field, operator, value) row from the Filters modal to the
        queryset, scoped to the given `model_type`. Unknown fields/operators
        or rows missing a required value are ignored rather than raising,
        since a still-being-filled-in row shouldn't break the whole request.
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
            # Status is stored as a lowercase, underscore-joined code
            # (e.g. "review_ongoing") but offered to the user as a friendly
            # label ("Review Ongoing") -- normalize back to the stored form
            # instead of forcing the option list to leak the raw codes.
            if field == "status":
                values = [v.strip().lower().replace(" ", "_") for v in values]
            if len(values) > 1:
                return qs.filter(**{f"{path}__in": values})
            return qs.filter(**{f"{path}__iexact": values[0]})
        if operator == "not_equals":
            values = parse_multi_value(value)
            if field == "status":
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
        Apply the Filters modal's field/operator/value rows, sent as a JSON
        array in the `dynamic_filters` query param, e.g.
        '[{"field": "status", "operator": "equals", "value": "Paid"},
          {"field": "status", "operator": "equals", "value": "Confirmed",
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
    @permission_required(perm="payroll.view_payslip")
    def payroll_filter_field_options(request):
        """
        Distinct values available for a given dynamic-filter field, so the
        Filters panel can offer a searchable pick-list instead of a freehand
        text box for fields where a fixed value is actually being matched.
        Both "payslip" and "allowance" report types filter on the same
        underlying Payslip queryset, just exposing a different field subset.
        """
        model_type = request.GET.get("model", "payslip")
        field = request.GET.get("field")

        if request.user.has_perm("payroll.view_payslip"):
            qs = Payslip.objects.all()
        else:
            qs = Payslip.objects.filter(employee_id__employee_user_id=request.user)

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
    @permission_required(perm="payroll.view_payslip")
    def payroll_report(request):
        company = "all"
        selected_company = request.session.get("selected_company")
        if selected_company != "all":
            company = Company.objects.filter(id=selected_company).first()

        if request.user.has_perm("payroll.view_payslip"):
            payslips = Payslip.objects.all()
        else:
            payslips = Payslip.objects.filter(
                employee_id__employee_user_id=request.user
            )

        filter_form = PayslipFilter(request.GET, payslips)

        payslip_export_access = has_export_access(request, Payslip)
        export_access_map = {
            "payslip": payslip_export_access,
            "allowance": payslip_export_access,
        }

        return render(
            request,
            "report/payroll_report.html",
            {
                "company": company,
                "f": filter_form,
                "export_access_map": export_access_map,
            },
        )

    @login_required
    @permission_required(perm="payroll.view_payslip")
    def payroll_pivot(request):
        model_type = request.GET.get("model", "payslip")

        if model_type == "payslip":
            qs = Payslip.objects.all()
            # The sidebar filter form has to be applied here too, not just on
            # the allowance/deduction branches below -- without it the payslip
            # pivot silently ignored every filter the user set.
            qs = PayslipFilter(request.GET, queryset=qs).qs
            qs = apply_dynamic_filters(qs, request, "payslip")

            data = list(
                qs.values(
                    "id",  # Include payslip ID to fetch pay_head_data later
                    "employee_id__employee_first_name",
                    "employee_id__employee_last_name",
                    "employee_id__badge_id",
                    "employee_id__gender",
                    "employee_id__email",
                    "employee_id__phone",
                    "start_date",
                    "end_date",
                    "contract_wage",
                    "basic_pay",
                    "gross_pay",
                    "deduction",
                    "net_pay",
                    "group_name",
                    "status",
                    "employee_id__employee_work_info__department_id__department",
                    "employee_id__employee_work_info__job_role_id__job_role",
                    "employee_id__employee_work_info__job_position_id__job_position",
                    "employee_id__employee_work_info__work_type_id__work_type",
                    "employee_id__employee_work_info__shift_id__employee_shift",
                    "employee_id__employee_work_info__employee_type_id__employee_type",
                    "employee_id__employee_work_info__experience",
                )
            )

            choice_gender = {
                "male": "Male",
                "female": "Female",
                "other": "Other",
            }

            STATUS = {
                "draft": "Draft",
                "review_ongoing": "Review Ongoing",
                "confirmed": "Confirmed",
                "paid": "Paid",
            }

            # Fetch pay_head_data separately and map by payslip ID
            payslip_ids = [item["id"] for item in data]
            pay_head_data_dict = dict(
                Payslip.objects.filter(id__in=payslip_ids).values_list(
                    "id", "pay_head_data"
                )
            )

            data_list = []
            for item in data:
                # Load pay_head_data for current payslip
                pay_head_data = pay_head_data_dict.get(item["id"], {})

                # Extract allowances and deductions
                allowances = pay_head_data.get("allowances", [])
                deductions = pay_head_data.get(
                    "pretax_deductions", []
                ) + pay_head_data.get("post_tax_deductions", [])

                # Prepare allowance and deduction lists with properly rounded amounts
                allowance_titles = (
                    ", ".join([allowance["title"] for allowance in allowances]) or "-"
                )
                allowance_amounts = (
                    ", ".join(
                        [
                            str(round(float(allowance["amount"] or 0), 2))
                            for allowance in allowances
                        ]
                    )
                    or "-"
                )

                deduction_titles = (
                    ", ".join([deduction["title"] for deduction in deductions]) or "-"
                )
                deduction_amounts = (
                    ", ".join(
                        [
                            str(round(float(deduction["amount"] or 0), 2))
                            for deduction in deductions
                        ]
                    )
                    or "-"
                )

                # Calculate total allowance amount
                total_allowance_amount = sum(
                    [
                        round(float(allowance["amount"] or 0), 2)
                        for allowance in allowances
                    ]
                )

                # Calculate total deduction amount
                total_deduction_amount = sum(
                    [
                        round(float(deduction["amount"] or 0), 2)
                        for deduction in deductions
                    ]
                )

                # Main data structure
                data_list.append(
                    {
                        "Employee": f"{item['employee_id__employee_first_name']} {item['employee_id__employee_last_name']}",
                        "Badge Id": item["employee_id__badge_id"] or "-",
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
                            item[
                                "employee_id__employee_work_info__job_role_id__job_role"
                            ]
                            if item[
                                "employee_id__employee_work_info__job_role_id__job_role"
                            ]
                            else "-"
                        ),
                        "Work Type": (
                            item[
                                "employee_id__employee_work_info__work_type_id__work_type"
                            ]
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
                        "Employee Type": (
                            item[
                                "employee_id__employee_work_info__employee_type_id__employee_type"
                            ]
                            if item[
                                "employee_id__employee_work_info__employee_type_id__employee_type"
                            ]
                            else "-"
                        ),
                        "Payslip Start Date": item["start_date"],
                        "Payslip End Date": item["end_date"],
                        "Batch Name": item["group_name"] if item["group_name"] else "-",
                        "Contract Wage": round(float(item["contract_wage"] or 0), 2),
                        "Basic Salary": round(float(item["basic_pay"] or 0), 2),
                        "Gross Pay": round(float(item["gross_pay"] or 0), 2),
                        "Net Pay": round(float(item["net_pay"] or 0), 2),
                        "Allowance Title": allowance_titles,
                        "Allowance Amount": allowance_amounts,
                        "Total Allowance Amount": round(total_allowance_amount, 2),
                        "Deduction Title": deduction_titles,
                        "Deduction Amount": deduction_amounts,
                        "Total Deduction Amount": round(total_deduction_amount, 2),
                        "Status": STATUS.get(item["status"]),
                        "Experience": round(
                            float(
                                item["employee_id__employee_work_info__experience"] or 0
                            ),
                            2,
                        ),
                    }
                )

        elif model_type == "allowance":

            payslips = Payslip.objects.all()

            payslip_filter = PayslipFilter(request.GET, queryset=payslips)
            filtered_qs = payslip_filter.qs  # This uses all custom filters you defined
            filtered_qs = apply_dynamic_filters(filtered_qs, request, "allowance")

            data = list(
                filtered_qs.values(
                    "id",  # Include payslip ID to fetch pay_head_data later
                    "employee_id__employee_first_name",
                    "employee_id__employee_last_name",
                    "employee_id__badge_id",
                    "employee_id__gender",
                    "employee_id__email",
                    "employee_id__phone",
                    "start_date",
                    "end_date",
                    "status",
                    "employee_id__employee_work_info__department_id__department",
                    "employee_id__employee_work_info__job_role_id__job_role",
                    "employee_id__employee_work_info__job_position_id__job_position",
                    "employee_id__employee_work_info__work_type_id__work_type",
                    "employee_id__employee_work_info__shift_id__employee_shift",
                )
            )

            choice_gender = {
                "male": "Male",
                "female": "Female",
                "other": "Other",
            }

            STATUS = {
                "draft": "Draft",
                "review_ongoing": "Review Ongoing",
                "confirmed": "Confirmed",
                "paid": "Paid",
            }

            # Fetch pay_head_data separately and map by payslip ID
            payslip_ids = [item["id"] for item in data]
            pay_head_data_dict = dict(
                Payslip.objects.filter(id__in=payslip_ids).values_list(
                    "id", "pay_head_data"
                )
            )

            data_list = []
            for item in data:
                # Load pay_head_data for current payslip
                pay_head_data = pay_head_data_dict.get(item["id"], {})

                # Combine Allowances and Deductions in a single section
                all_pay_data = []

                # Add Allowances to combined data
                for allowance in pay_head_data.get("allowances", []):
                    all_pay_data.append(
                        {
                            "Pay Type": "Allowance",
                            "Title": allowance["title"],
                            "Amount": round(float(allowance["amount"] or 0), 2),
                        }
                    )

                # Add Deductions to combined data
                for deduction in pay_head_data.get(
                    "pretax_deductions", []
                ) + pay_head_data.get("post_tax_deductions", []):
                    all_pay_data.append(
                        {
                            "Pay Type": "Deduction",
                            "Title": deduction["title"],
                            "Amount": round(float(deduction["amount"] or 0), 2),
                        }
                    )

                # Add combined data to main data list
                for pay_item in all_pay_data:
                    data_list.append(
                        {
                            "Employee": f"{item['employee_id__employee_first_name']} {item['employee_id__employee_last_name']}",
                            "Badge Id": item["employee_id__badge_id"] or "-",
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
                                item[
                                    "employee_id__employee_work_info__job_role_id__job_role"
                                ]
                                if item[
                                    "employee_id__employee_work_info__job_role_id__job_role"
                                ]
                                else "-"
                            ),
                            "Work Type": (
                                item[
                                    "employee_id__employee_work_info__work_type_id__work_type"
                                ]
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
                            "Payslip Start Date": item["start_date"],
                            "Payslip End Date": item["end_date"],
                            "Allowance & Deduction": pay_item["Pay Type"],
                            "Allowance & Deduction Title": pay_item["Title"],
                            "Allowance & Deduction Amount": pay_item["Amount"],
                            "Status": STATUS.get(item["status"]),
                        }
                    )
        else:
            data_list = []

        return pivot_json_with_meta(data_list)

"""Payroll and labor cost metrics."""

from __future__ import annotations

from django.db.models import Avg, Count, Q, Sum
from django.utils.translation import gettext as _

from report.engine import ReportFilters, apply_org_filters, empty_report, iter_months


def _payslips(filters: ReportFilters):
    from payroll.models.models import Payslip

    qs = Payslip.objects.filter(
        start_date__lte=filters.to_date,
        end_date__gte=filters.from_date,
    )
    if filters.payslip_status:
        qs = qs.filter(status=filters.payslip_status)
    return apply_org_filters(
        qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )


def labor_cost_summary(filters: ReportFilters) -> dict:
    qs = _payslips(filters)
    agg = qs.aggregate(
        gross=Sum("gross_pay"),
        net=Sum("net_pay"),
        deduction=Sum("deduction"),
        count=Count("id"),
        employees=Count("employee_id", distinct=True),
    )
    gross = round(agg["gross"] or 0, 2)
    net = round(agg["net"] or 0, 2)
    deduction = round(agg["deduction"] or 0, 2)
    # Employer cost proxy ≈ gross (employer contributions not always modeled)
    employer_proxy = gross

    by_dept = list(
        qs.filter(employee_id__employee_work_info__department_id__isnull=False)
        .values("employee_id__employee_work_info__department_id__department")
        .annotate(
            gross=Sum("gross_pay"),
            net=Sum("net_pay"),
            deduction=Sum("deduction"),
            count=Count("id"),
        )
        .order_by("-gross")
    )

    trend = []
    from payroll.models.models import Payslip

    for month_start, month_end, label in iter_months(filters.to_date, 6):
        month_qs = apply_org_filters(
            Payslip.objects.filter(
                start_date__lte=month_end,
                end_date__gte=month_start,
            ),
            filters,
            prefix="employee_id__employee_work_info",
            employee_prefix="employee_id",
        )
        if filters.payslip_status:
            month_qs = month_qs.filter(status=filters.payslip_status)
        m = month_qs.aggregate(gross=Sum("gross_pay"), net=Sum("net_pay"))
        trend.append(
            {
                "month": label,
                "gross": round(m["gross"] or 0, 2),
                "net": round(m["net"] or 0, 2),
            }
        )

    return {
        "title": _("Labor Cost Summary"),
        "kpis": [
            {"label": _("Gross pay"), "value": gross, "hint": _("Period payslips")},
            {"label": _("Net pay"), "value": net, "hint": _("Period payslips")},
            {"label": _("Deductions"), "value": deduction, "hint": _("Period")},
            {
                "label": _("Gross (employer cost proxy)"),
                "value": employer_proxy,
                "hint": _("≈ gross until employer contribs modeled"),
            },
        ],
        "charts": [
            {
                "id": "cost_trend",
                "type": "line",
                "title": _("Labor Cost Trend"),
                "categories": [t["month"] for t in trend],
                "series": [
                    {"name": _("Gross"), "data": [t["gross"] for t in trend]},
                    {"name": _("Net"), "data": [t["net"] for t in trend]},
                ],
            },
            {
                "id": "cost_dept",
                "type": "bar",
                "title": _("Gross by Department"),
                "categories": [
                    r["employee_id__employee_work_info__department_id__department"]
                    for r in by_dept[:12]
                ],
                "series": [
                    {
                        "name": _("Gross"),
                        "data": [round(r["gross"] or 0, 2) for r in by_dept[:12]],
                    }
                ],
            },
        ],
        "table": {
            "columns": [
                {"key": "department", "label": _("Department")},
                {"key": "gross", "label": _("Gross")},
                {"key": "deduction", "label": _("Deductions")},
                {"key": "net", "label": _("Net")},
                {"key": "count", "label": _("Payslips")},
            ],
            "rows": [
                {
                    "department": r[
                        "employee_id__employee_work_info__department_id__department"
                    ],
                    "gross": round(r["gross"] or 0, 2),
                    "deduction": round(r["deduction"] or 0, 2),
                    "net": round(r["net"] or 0, 2),
                    "count": r["count"],
                }
                for r in by_dept
            ],
        },
        "meta": {"employees": agg["employees"] or 0, "payslips": agg["count"] or 0},
        "explorer_url_name": "payroll-report",
    }


def cost_composition(filters: ReportFilters) -> dict:
    qs = _payslips(filters)
    allowance_total = 0.0
    deduction_total = 0.0
    allowance_map: dict[str, float] = {}
    deduction_map: dict[str, float] = {}

    for slip in qs.only("pay_head_data", "gross_pay", "deduction").iterator():
        data = slip.pay_head_data or {}
        if not isinstance(data, dict):
            continue
        for key in ("allowances", "allowance"):
            items = data.get(key) or []
            if isinstance(items, dict):
                items = list(items.values()) if items else []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = (
                    item.get("title")
                    or item.get("allowance")
                    or item.get("name")
                    or _("Allowance")
                )
                amount = float(item.get("amount") or item.get("amt") or 0)
                allowance_map[title] = allowance_map.get(title, 0) + amount
                allowance_total += amount
        # Payslip.pay_head_data splits deductions across several keys by the
        # stage they apply at -- there is no flat "deductions" list, so the
        # original ("deductions", "deduction_list") pair never matched anything
        # and this chart rendered empty for every install. The allowance loop
        # above happens to use a correct key, which is why "Top Allowances"
        # worked while "Top Deductions" silently did not.
        for key in (
            "basic_pay_deductions",
            "gross_pay_deductions",
            "pretax_deductions",
            "post_tax_deductions",
            "tax_deductions",
            "net_deductions",
            # Legacy/simple payload shapes, kept so older payslips still parse.
            "deductions",
            "deduction_list",
        ):
            items = data.get(key) or []
            if isinstance(items, dict):
                items = list(items.values()) if items else []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = (
                    item.get("title")
                    or item.get("deduction")
                    or item.get("name")
                    or _("Deduction")
                )
                amount = float(item.get("amount") or item.get("amt") or 0)
                deduction_map[title] = deduction_map.get(title, 0) + amount
                deduction_total += amount

    # Fallback if pay_head_data lacks structured lists. Guarded per side: a
    # payload that itemises allowances but not deductions (or vice versa) must
    # still get a total for the side it is missing -- an "and" here let one
    # populated side suppress the other's fallback, leaving that chart empty.
    unsplit_fallback = False
    if not allowance_total or not deduction_total:
        agg = qs.aggregate(gross=Sum("gross_pay"), deduction=Sum("deduction"))
        if not allowance_total:
            allowance_total = float(agg["gross"] or 0)
            allowance_map[_("Gross (unsplit)")] = allowance_total
            unsplit_fallback = True
        if not deduction_total:
            deduction_total = float(agg["deduction"] or 0)
            deduction_map[_("Deductions (unsplit)")] = deduction_total
            unsplit_fallback = True

    allow_rows = sorted(
        [
            {"component": k, "amount": round(v, 2), "kind": _("Allowance")}
            for k, v in allowance_map.items()
        ],
        key=lambda x: -x["amount"],
    )[:30]
    ded_rows = sorted(
        [
            {"component": k, "amount": round(v, 2), "kind": _("Deduction")}
            for k, v in deduction_map.items()
        ],
        key=lambda x: -x["amount"],
    )[:30]

    return {
        "title": _("Cost Composition"),
        "kpis": [
            {
                "label": _("Allowances total"),
                "value": round(allowance_total, 2),
                "hint": (
                    _("Unsplit gross — pay_head_data missing structured lists")
                    if unsplit_fallback
                    else _("From payslip heads")
                ),
            },
            {
                "label": _("Deductions total"),
                "value": round(deduction_total, 2),
                "hint": (
                    _("Unsplit deduction field — not componentized")
                    if unsplit_fallback
                    else _("From payslip heads")
                ),
            },
            {
                "label": _("Allowance components"),
                "value": len(allowance_map),
                "hint": _("Unsplit fallback") if unsplit_fallback else "",
            },
            {
                "label": _("Deduction components"),
                "value": len(deduction_map),
                "hint": "",
            },
        ],
        "charts": [
            {
                "id": "allowances",
                "type": "donut",
                "title": _("Top Allowances"),
                "categories": [r["component"] for r in allow_rows[:8]],
                "series": [
                    {
                        "name": _("Amount"),
                        "data": [r["amount"] for r in allow_rows[:8]],
                    }
                ],
            },
            {
                "id": "deductions",
                "type": "donut",
                "title": _("Top Deductions"),
                "categories": [r["component"] for r in ded_rows[:8]],
                "series": [
                    {
                        "name": _("Amount"),
                        "data": [r["amount"] for r in ded_rows[:8]],
                    }
                ],
            },
        ],
        "table": {
            "columns": [
                {"key": "kind", "label": _("Type")},
                {"key": "component", "label": _("Component")},
                {"key": "amount", "label": _("Amount")},
            ],
            "rows": allow_rows + ded_rows,
        },
        "explorer_url_name": "payroll-report",
    }


def payroll_headcount_cost(filters: ReportFilters) -> dict:
    from employee.models import Employee

    qs = _payslips(filters)
    by_dept = list(
        qs.filter(employee_id__employee_work_info__department_id__isnull=False)
        .values(
            "employee_id__employee_work_info__department_id",
            "employee_id__employee_work_info__department_id__department",
        )
        .annotate(
            gross=Sum("gross_pay"),
            net=Sum("net_pay"),
            payslips=Count("id"),
            employees=Count("employee_id", distinct=True),
            avg_net=Avg("net_pay"),
        )
        .order_by("-gross")
    )

    active = apply_org_filters(
        Employee.objects.all(),
        filters,
        prefix="employee_work_info",
        employee_prefix="",
    ).count()
    total_gross = qs.aggregate(g=Sum("gross_pay"))["g"] or 0
    cost_per_fte = round(total_gross / active, 2) if active else 0
    avg_net = qs.aggregate(a=Avg("net_pay"))["a"] or 0

    rows = []
    for r in by_dept:
        emp_count = r["employees"] or 1
        rows.append(
            {
                "department": r[
                    "employee_id__employee_work_info__department_id__department"
                ],
                "employees": r["employees"],
                "gross": round(r["gross"] or 0, 2),
                "avg_net": round(r["avg_net"] or 0, 2),
                "cost_per_head": round((r["gross"] or 0) / emp_count, 2),
            }
        )

    return {
        "title": _("Payroll Headcount Cost"),
        "kpis": [
            {
                "label": _("Cost per head (proxy)"),
                "value": cost_per_fte,
                "hint": _("Gross / active headcount — not hours-based FTE"),
            },
            {
                "label": _("Avg net pay"),
                "value": round(avg_net, 2),
                "hint": _("Per payslip"),
            },
            {"label": _("Active headcount"), "value": active, "hint": ""},
            {
                "label": _("Total gross"),
                "value": round(total_gross, 2),
                "hint": _("Period"),
            },
        ],
        "charts": [
            {
                "id": "cost_per_head",
                "type": "bar",
                "title": _("Cost per Head by Department"),
                "categories": [r["department"] for r in rows[:12]],
                "series": [
                    {
                        "name": _("Cost / head"),
                        "data": [r["cost_per_head"] for r in rows[:12]],
                    }
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "department", "label": _("Department")},
                {"key": "employees", "label": _("Employees")},
                {"key": "gross", "label": _("Gross")},
                {"key": "avg_net", "label": _("Avg Net")},
                {"key": "cost_per_head", "label": _("Cost / Head")},
            ],
            "rows": rows,
        },
        "explorer_url_name": "payroll-report",
    }


def payslip_register(filters: ReportFilters) -> dict:
    qs = (
        _payslips(filters)
        .select_related(
            "employee_id",
            "employee_id__employee_work_info",
            "employee_id__employee_work_info__department_id",
        )
        .order_by("-end_date", "employee_id__employee_first_name")
    )
    total = qs.count()
    # Cap rows for UI; export uses same query with higher limit via engine caller
    limit = int(filters.extra.get("row_limit", 500))
    rows = []
    for slip in qs[:limit]:
        emp = slip.employee_id
        dept = ""
        try:
            dept = emp.employee_work_info.department_id.department
        except Exception:
            dept = ""
        rows.append(
            {
                "employee": (
                    emp.get_full_name() if hasattr(emp, "get_full_name") else str(emp)
                ),
                "badge": getattr(emp, "badge_id", "") or "",
                "department": dept,
                "start_date": slip.start_date.isoformat() if slip.start_date else "",
                "end_date": slip.end_date.isoformat() if slip.end_date else "",
                "gross": round(slip.gross_pay or 0, 2),
                "deduction": round(slip.deduction or 0, 2),
                "net": round(slip.net_pay or 0, 2),
                "status": (
                    slip.get_status() if hasattr(slip, "get_status") else slip.status
                ),
            }
        )

    agg = qs.aggregate(
        gross=Sum("gross_pay"), net=Sum("net_pay"), deduction=Sum("deduction")
    )

    return {
        "title": _("Payslip Register"),
        "kpis": [
            {"label": _("Payslips"), "value": total, "hint": _("In period")},
            {
                "label": _("Gross total"),
                "value": round(agg["gross"] or 0, 2),
                "hint": "",
            },
            {
                "label": _("Net total"),
                "value": round(agg["net"] or 0, 2),
                "hint": "",
            },
            {
                "label": _("Shown rows"),
                "value": len(rows),
                "hint": _("Capped for display"),
            },
        ],
        "charts": [],
        "table": {
            "columns": [
                {"key": "employee", "label": _("Employee")},
                {"key": "badge", "label": _("Badge ID")},
                {"key": "department", "label": _("Department")},
                {"key": "start_date", "label": _("Start")},
                {"key": "end_date", "label": _("End")},
                {"key": "gross", "label": _("Gross")},
                {"key": "deduction", "label": _("Deduction")},
                {"key": "net", "label": _("Net")},
                {"key": "status", "label": _("Status")},
            ],
            "rows": rows,
        },
        "explorer_url_name": "payroll-report",
    }


def payslip_register_drilldown(
    filters: ReportFilters, params: dict, request=None
) -> dict:
    """Drill payslip register by department label or employee badge/name."""
    from report.drilldown import (
        apply_subordinate_scope,
        drilldown_payload,
        employee_link,
        empty_drilldown,
        payslip_link,
    )

    dimension = (params.get("dimension") or "department").strip().lower()
    value = (params.get("value") or "").strip()
    if not value:
        return empty_drilldown(
            _("Payslip Register"), dimension, value, _("Missing dimension value.")
        )

    qs = _payslips(filters)
    qs = apply_subordinate_scope(
        request, qs, perm="payroll.view_payslip", field="employee_id"
    )

    title = _("Payslip Register")
    if dimension in ("department", "dept"):
        qs = qs.filter(employee_id__employee_work_info__department_id__department=value)
        title = _("Payslips · %(dept)s") % {"dept": value}
        dimension = "department"
    elif dimension in ("employee", "badge"):
        qs = qs.filter(
            Q(employee_id__badge_id__iexact=value)
            | Q(employee_id__employee_first_name__icontains=value)
            | Q(employee_id__employee_last_name__icontains=value)
        )
        title = _("Payslips · %(emp)s") % {"emp": value}
        dimension = "employee"
    elif dimension in ("status",):
        qs = qs.filter(status__iexact=value)
        title = _("Payslips · status %(s)s") % {"s": value}
    else:
        return empty_drilldown(title, dimension, value, _("Unsupported dimension."))

    limit = int((params.get("limit") or filters.extra.get("row_limit") or 200))
    total = qs.count()
    rows = []
    for slip in qs.select_related(
        "employee_id",
        "employee_id__employee_work_info__department_id",
    ).order_by("-end_date")[:limit]:
        emp = slip.employee_id
        dept = ""
        try:
            dept = emp.employee_work_info.department_id.department
        except Exception:
            dept = ""
        rows.append(
            {
                "employee": (
                    emp.get_full_name() if hasattr(emp, "get_full_name") else str(emp)
                ),
                "badge": getattr(emp, "badge_id", "") or "",
                "department": dept,
                "end_date": slip.end_date.isoformat() if slip.end_date else "",
                "net": round(slip.net_pay or 0, 2),
                "status": (
                    slip.get_status() if hasattr(slip, "get_status") else slip.status
                ),
                "link": payslip_link(slip.id),
                "employee_link": employee_link(emp.id if emp else None),
            }
        )
    return drilldown_payload(
        title=title,
        dimension=dimension,
        value=value,
        columns=[
            {"key": "employee", "label": _("Employee")},
            {"key": "badge", "label": _("Badge ID")},
            {"key": "department", "label": _("Department")},
            {"key": "end_date", "label": _("End")},
            {"key": "net", "label": _("Net")},
            {"key": "status", "label": _("Status")},
            {"key": "link", "label": _("Payslip"), "type": "link"},
        ],
        rows=rows,
        truncated=total > len(rows),
    )


def payroll_readiness(filters: ReportFilters) -> dict:
    """Active employees who cannot be paid: missing bank details or contract.

    An exception report, so it is most valuable when it returns rows --
    unlike every other report here, an empty result is the good outcome.
    Run as a pre-payroll gate: each row is a person the payroll run will
    either skip or fail on.
    """
    from django.apps import apps as django_apps

    from employee.models import Employee

    if not django_apps.is_installed("payroll"):
        return empty_report(
            _("Payroll Readiness"), filters, _("Payroll app is not installed.")
        )

    from payroll.models.models import Contract

    employees = apply_org_filters(
        Employee.objects.filter(is_active=True),
        filters,
        prefix="employee_work_info",
        employee_prefix="",
    )
    total = employees.count()
    if not total:
        return empty_report(
            _("Payroll Readiness"), filters, _("No active employees in scope.")
        )

    # OneToOne from EmployeeBankDetails, so absence is a plain isnull check.
    missing_bank_ids = set(
        employees.filter(employee_bank_details__isnull=True).values_list(
            "id", flat=True
        )
    )
    with_active_contract = set(
        Contract.objects.filter(
            employee_id__in=employees, contract_status="active"
        ).values_list("employee_id", flat=True)
    )
    missing_contract_ids = {
        e_id
        for e_id in employees.values_list("id", flat=True)
        if e_id not in with_active_contract
    }

    blocked_ids = missing_bank_ids | missing_contract_ids
    ready = total - len(blocked_ids)

    rows = []
    for emp in (
        employees.filter(id__in=blocked_ids)
        .select_related("employee_work_info__department_id")
        .order_by("employee_first_name", "employee_last_name")[:300]
    ):
        reasons = []
        if emp.id in missing_bank_ids:
            reasons.append(str(_("No bank details")))
        if emp.id in missing_contract_ids:
            reasons.append(str(_("No active contract")))
        work_info = getattr(emp, "employee_work_info", None)
        department = getattr(
            getattr(work_info, "department_id", None), "department", ""
        )
        rows.append(
            {
                "employee": emp.get_full_name(),
                "department": department or "",
                "blocker": ", ".join(reasons),
            }
        )

    ready_pct = round(ready / total * 100, 1) if total else 0
    return {
        "title": _("Payroll Readiness"),
        "kpis": [
            {
                "label": _("Cannot be paid"),
                "value": len(blocked_ids),
                "hint": _("Missing bank details or an active contract"),
            },
            {
                "label": _("Missing bank details"),
                "value": len(missing_bank_ids),
                "hint": _("No EmployeeBankDetails record"),
            },
            {
                "label": _("No active contract"),
                "value": len(missing_contract_ids),
                "hint": _("No contract in 'active' status"),
            },
            {
                "label": _("Ready to pay"),
                "value": f"{ready_pct}%",
                "hint": _("%(ready)s of %(total)s active employees")
                % {"ready": ready, "total": total},
            },
        ],
        "charts": [
            {
                "id": "readiness",
                "type": "donut",
                "title": _("Payroll Readiness"),
                "categories": [str(_("Ready")), str(_("Blocked"))],
                "series": [
                    {"name": str(_("Employees")), "data": [ready, len(blocked_ids)]}
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "employee", "label": _("Employee")},
                {"key": "department", "label": _("Department")},
                {"key": "blocker", "label": _("Blocker")},
            ],
            "rows": rows,
        },
        "explorer_url_name": "payroll-report",
    }


def loan_advance_ledger(filters: ReportFilters) -> dict:
    """Outstanding employee loans and advances.

    Unrecovered advances are a real balance-sheet liability, and the only
    existing view is per-employee. This is a register: it is correct at any
    row count, unlike the rate metrics elsewhere in this module.
    """
    from django.apps import apps as django_apps

    if not django_apps.is_installed("payroll"):
        return empty_report(
            _("Loan & Advance Ledger"), filters, _("Payroll app is not installed.")
        )

    from payroll.models.models import LoanAccount

    qs = LoanAccount.objects.filter(provided_date__lte=filters.to_date)
    qs = apply_org_filters(
        qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )

    rows = []
    outstanding_total = 0.0
    issued_total = 0.0
    by_type: dict[str, float] = {}
    for loan in qs.select_related("employee_id").order_by("-provided_date")[:300]:
        principal = float(loan.loan_amount or 0)
        issued_total += principal
        # Installments actually recovered are not stored as a count, so derive
        # from the schedule: everything due on or before to_date, capped at the
        # agreed number of installments.
        paid = 0
        if loan.installment_start_date and loan.installment_amount:
            months = (
                (filters.to_date.year - loan.installment_start_date.year) * 12
                + filters.to_date.month
                - loan.installment_start_date.month
                + 1
            )
            paid = max(0, min(months, loan.installments or 0))
        recovered = min(principal, paid * float(loan.installment_amount or 0))
        balance = 0.0 if loan.settled else max(0.0, principal - recovered)
        outstanding_total += balance
        label = str(
            loan.get_type_display() if hasattr(loan, "get_type_display") else loan.type
        )
        by_type[label] = by_type.get(label, 0) + balance
        emp = getattr(loan, "employee_id", None)
        rows.append(
            {
                "employee": emp.get_full_name() if emp else "",
                "title": loan.title or "",
                "type": label,
                "amount": round(principal, 2),
                "recovered": round(recovered, 2),
                "balance": round(balance, 2),
                "status": str(_("Settled")) if loan.settled else str(_("Running")),
            }
        )

    running = sum(1 for r in rows if r["status"] == str(_("Running")))
    type_labels = [k for k, v in by_type.items() if v > 0]
    return {
        "title": _("Loan & Advance Ledger"),
        "kpis": [
            {
                "label": _("Outstanding balance"),
                "value": round(outstanding_total, 2),
                "hint": _("Unrecovered principal at period end"),
            },
            {
                "label": _("Total issued"),
                "value": round(issued_total, 2),
                "hint": _("Principal advanced to date"),
            },
            {
                "label": _("Running accounts"),
                "value": running,
                "hint": _("Not yet settled"),
            },
            {
                "label": _("Accounts"),
                "value": len(rows),
                "hint": _("In period"),
            },
        ],
        "charts": (
            [
                {
                    "id": "loan_type",
                    "type": "donut",
                    "title": _("Outstanding by Type"),
                    "categories": type_labels,
                    "series": [
                        {
                            "name": str(_("Balance")),
                            "data": [round(by_type[k], 2) for k in type_labels],
                        }
                    ],
                }
            ]
            if type_labels
            else []
        ),
        "table": {
            "columns": [
                {"key": "employee", "label": _("Employee")},
                {"key": "title", "label": _("Title")},
                {"key": "type", "label": _("Type")},
                {"key": "amount", "label": _("Amount")},
                {"key": "recovered", "label": _("Recovered")},
                {"key": "balance", "label": _("Balance")},
                {"key": "status", "label": _("Status")},
            ],
            "rows": rows,
        },
        "explorer_url_name": "payroll-report",
    }


def reimbursement_register(filters: ReportFilters) -> dict:
    """Reimbursement and encashment claims by type and status.

    Pending-claim exposure before a payroll run closes. Note the model has no
    approval timestamp, so ageing is measured from created_at rather than a
    real decision date -- stated in the KPI hint rather than left implied.
    """
    from django.apps import apps as django_apps

    if not django_apps.is_installed("payroll"):
        return empty_report(
            _("Reimbursement Register"), filters, _("Payroll app is not installed.")
        )

    # created_at is nullable and auto_now_add, so rows created via
    # bulk_create() carry no date. A plain range filter drops them from every
    # window rather than just this one -- here that would hide 8 of 14 demo
    # claims -- so undated rows are kept, matching the same fix in talent.py.
    from django.db.models import Q

    from payroll.models.models import Reimbursement

    qs = Reimbursement.objects.filter(
        Q(created_at__isnull=True)
        | Q(created_at__gte=filters.from_date, created_at__lte=filters.to_date)
    )
    qs = apply_org_filters(
        qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )

    by_status: dict[str, float] = {}
    by_type: dict[str, float] = {}
    rows = []
    pending_amount = 0.0
    for claim in qs.select_related("employee_id").order_by("-created_at")[:300]:
        amount = float(claim.amount or 0)
        status_label = str(
            claim.get_status_display()
            if hasattr(claim, "get_status_display")
            else claim.status
        )
        type_label = str(
            claim.get_type_display()
            if hasattr(claim, "get_type_display")
            else claim.type
        )
        by_status[status_label] = by_status.get(status_label, 0) + amount
        by_type[type_label] = by_type.get(type_label, 0) + amount
        if claim.status == "requested":
            pending_amount += amount
        emp = getattr(claim, "employee_id", None)
        rows.append(
            {
                "employee": emp.get_full_name() if emp else "",
                "title": claim.title or "",
                "type": type_label,
                "amount": round(amount, 2),
                "status": status_label,
                "raised": claim.created_at.isoformat() if claim.created_at else "",
            }
        )

    status_labels = list(by_status.keys())
    return {
        "title": _("Reimbursement Register"),
        "kpis": [
            {
                "label": _("Pending amount"),
                "value": round(pending_amount, 2),
                "hint": _("Claims still in 'requested'"),
            },
            {
                "label": _("Claims"),
                "value": len(rows),
                "hint": _("Raised in period (by created date)"),
            },
            {
                "label": _("Total claimed"),
                "value": round(sum(by_status.values()), 2),
                "hint": _("All statuses"),
            },
            {
                "label": _("Approved"),
                "value": round(by_status.get(str(_("Approved")), 0), 2),
                "hint": _("Approval date not stored; ageing uses created date"),
            },
        ],
        "charts": (
            [
                {
                    "id": "claims_status",
                    "type": "donut",
                    "title": _("Claim Amount by Status"),
                    "categories": status_labels,
                    "series": [
                        {
                            "name": str(_("Amount")),
                            "data": [round(by_status[k], 2) for k in status_labels],
                        }
                    ],
                }
            ]
            if status_labels
            else []
        ),
        "table": {
            "columns": [
                {"key": "employee", "label": _("Employee")},
                {"key": "title", "label": _("Title")},
                {"key": "type", "label": _("Type")},
                {"key": "amount", "label": _("Amount")},
                {"key": "status", "label": _("Status")},
                {"key": "raised", "label": _("Raised")},
            ],
            "rows": rows,
        },
        "explorer_url_name": "payroll-report",
    }

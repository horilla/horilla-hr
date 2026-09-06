"""Workforce / employee analytics metrics."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date

from django.db.models import Count, Q
from django.utils.translation import gettext as _

from report.engine import (
    ReportFilters,
    apply_org_filters,
    empty_report,
    iter_months,
    month_offset,
)

logger = logging.getLogger(__name__)


def _work_info(filters: ReportFilters):
    from employee.models import EmployeeWorkInformation

    return apply_org_filters(
        EmployeeWorkInformation.objects.all(),
        filters,
        prefix="",
        employee_prefix="employee_id",
    )


def _employees(filters: ReportFilters, *, apply_status: bool = True):
    from employee.models import Employee

    return apply_org_filters(
        Employee.objects.all(),
        filters,
        prefix="employee_work_info",
        employee_prefix="",
        apply_employment_status=apply_status,
    )


def workforce_composition(filters: ReportFilters) -> dict:
    from employee.models import Employee

    work_info = _work_info(filters)
    active = _employees(filters)
    headcount = active.count()

    by_dept = list(
        work_info.filter(department_id__isnull=False)
        .values("department_id__department")
        .annotate(count=Count("employee_id", distinct=True))
        .order_by("-count")
    )
    by_type = list(
        work_info.filter(employee_type_id__isnull=False)
        .values("employee_type_id__employee_type")
        .annotate(count=Count("employee_id", distinct=True))
        .order_by("-count")
    )
    by_job = list(
        work_info.filter(job_position_id__isnull=False)
        .values("job_position_id__job_position")
        .annotate(count=Count("employee_id", distinct=True))
        .order_by("-count")[:15]
    )
    by_location = list(
        work_info.filter(location__isnull=False)
        .exclude(location="")
        .values("location")
        .annotate(count=Count("employee_id", distinct=True))
        .order_by("-count")[:15]
    )

    # FTE proxy: count full-time-ish types containing "full" else treat as 0.5
    fte = 0.0
    for row in by_type:
        label = (row["employee_type_id__employee_type"] or "").lower()
        weight = 1.0 if "full" in label or "permanent" in label else 0.5
        if "part" in label or "intern" in label or "contract" in label:
            weight = 0.5
        fte += row["count"] * weight
    if not by_type:
        fte = float(headcount)

    return {
        "title": _("Workforce Composition"),
        "kpis": [
            {
                "label": _("Headcount"),
                "value": headcount,
                "hint": _("Active employees"),
            },
            {
                "label": _("FTE (proxy)"),
                "value": round(fte, 1),
                "hint": _("From employee type"),
            },
            {
                "label": _("Departments"),
                "value": len(by_dept),
                "hint": _("With active staff"),
            },
            {
                "label": _("Job positions"),
                "value": len(by_job),
                "hint": _("Top roles shown in table"),
            },
        ],
        "charts": [
            {
                "id": "by_dept",
                "type": "bar",
                "title": _("Headcount by Department"),
                "categories": [r["department_id__department"] for r in by_dept[:12]],
                "series": [
                    {
                        "name": _("Employees"),
                        "data": [r["count"] for r in by_dept[:12]],
                    }
                ],
            },
            {
                "id": "by_type",
                "type": "donut",
                "title": _("By Employee Type"),
                "categories": [r["employee_type_id__employee_type"] for r in by_type],
                "series": [
                    {
                        "name": _("Employees"),
                        "data": [r["count"] for r in by_type],
                    }
                ],
            },
        ],
        "table": {
            "columns": [
                {"key": "dimension", "label": _("Dimension")},
                {"key": "value", "label": _("Value")},
                {"key": "count", "label": _("Count")},
            ],
            "rows": (
                [
                    {
                        "dimension": _("Department"),
                        "value": r["department_id__department"],
                        "count": r["count"],
                    }
                    for r in by_dept
                ]
                + [
                    {
                        "dimension": _("Job Position"),
                        "value": r["job_position_id__job_position"],
                        "count": r["count"],
                    }
                    for r in by_job
                ]
                + [
                    {
                        "dimension": _("Location"),
                        "value": r["location"],
                        "count": r["count"],
                    }
                    for r in by_location
                ]
            ),
        },
        "explorer_url_name": "employee-report",
    }


def diversity_snapshot(filters: ReportFilters) -> dict:
    from employee.models import Employee

    employees = _employees(filters)
    total = employees.count()
    if not total:
        return empty_report(_("Diversity Snapshot"), filters, _("No active employees."))

    gender_counts = Counter(employees.values_list("gender", flat=True))
    gender_labels = {"male": _("Male"), "female": _("Female"), "other": _("Other")}
    genders = [
        {
            "key": g or "unknown",
            "label": gender_labels.get(g, g or _("Unknown")),
            "count": c,
            "pct": round(c / total * 100, 1),
        }
        for g, c in gender_counts.items()
        if c > 0
    ]
    genders.sort(key=lambda x: -x["count"])

    today = filters.to_date
    age_bands = {
        _("Under 25"): 0,
        _("25–34"): 0,
        _("35–44"): 0,
        _("45–54"): 0,
        _("55+"): 0,
        _("Unknown"): 0,
    }
    for dob in employees.values_list("dob", flat=True):
        if not dob:
            age_bands[_("Unknown")] += 1
            continue
        age = (today - dob).days // 365
        if age < 25:
            age_bands[_("Under 25")] += 1
        elif age < 35:
            age_bands[_("25–34")] += 1
        elif age < 45:
            age_bands[_("35–44")] += 1
        elif age < 55:
            age_bands[_("45–54")] += 1
        else:
            age_bands[_("55+")] += 1

    # Leadership gender: employees who are reporting managers
    managers = employees.filter(
        id__in=employees.exclude(
            employee_work_info__reporting_manager_id__isnull=True
        ).values_list("employee_work_info__reporting_manager_id", flat=True)
    )
    mgr_gender = Counter(managers.values_list("gender", flat=True))
    mgr_total = managers.count() or 1
    leadership_rows = [
        {
            "category": _("Leadership gender"),
            "value": gender_labels.get(g, g or _("Unknown")),
            "count": c,
            "pct": round(c / mgr_total * 100, 1),
        }
        for g, c in mgr_gender.items()
        if c
    ]

    # Equal-weight representation KPIs (avoid single "Female %" hero)
    male_pct = next((g["pct"] for g in genders if g["key"] == "male"), 0)
    female_pct = next((g["pct"] for g in genders if g["key"] == "female"), 0)
    other_pct = round(
        sum(g["pct"] for g in genders if g["key"] not in ("male", "female")), 1
    )

    return {
        "title": _("Diversity Snapshot"),
        "kpis": [
            {"label": _("Headcount"), "value": total, "hint": _("Active")},
            {
                "label": _("Male %"),
                "value": f"{male_pct}%",
                "hint": _("Representation"),
            },
            {
                "label": _("Female %"),
                "value": f"{female_pct}%",
                "hint": _("Representation"),
            },
            {
                "label": _("Other / unspecified %"),
                "value": f"{other_pct}%",
                "hint": _("Representation"),
            },
        ],
        "charts": [
            {
                "id": "gender",
                "type": "donut",
                "title": _("Gender Distribution"),
                "categories": [g["label"] for g in genders],
                "series": [
                    {"name": _("Employees"), "data": [g["count"] for g in genders]}
                ],
            },
            {
                "id": "age",
                "type": "bar",
                "title": _("Age Bands"),
                "categories": list(age_bands.keys()),
                "series": [{"name": _("Employees"), "data": list(age_bands.values())}],
            },
        ],
        "table": {
            "columns": [
                {"key": "category", "label": _("Category")},
                {"key": "value", "label": _("Value")},
                {"key": "count", "label": _("Count")},
                {"key": "pct", "label": _("%")},
            ],
            "rows": (
                [
                    {
                        "category": _("Gender"),
                        "value": g["label"],
                        "count": g["count"],
                        "pct": g["pct"],
                    }
                    for g in genders
                ]
                + [
                    {
                        "category": _("Age"),
                        "value": band,
                        "count": count,
                        "pct": round(count / total * 100, 1) if total else 0,
                    }
                    for band, count in age_bands.items()
                    if count
                ]
                + leadership_rows
            ),
        },
        "explorer_url_name": "employee-report",
    }


def tenure_longevity(filters: ReportFilters) -> dict:
    from employee.models import EmployeeWorkInformation

    work_info = _work_info(filters).exclude(date_joining__isnull=True)
    today = filters.to_date
    bands = {
        _("0–1 years"): 0,
        _("1–3 years"): 0,
        _("3–5 years"): 0,
        _("5–10 years"): 0,
        _("10+ years"): 0,
    }
    tenures = []
    by_dept: dict[str, list[float]] = {}

    for row in work_info.select_related("department_id").values(
        "date_joining", "department_id__department"
    ):
        joining = row["date_joining"]
        years = (today - joining).days / 365.25
        tenures.append(years)
        dept = row["department_id__department"] or _("Unassigned")
        by_dept.setdefault(dept, []).append(years)
        if years < 1:
            bands[_("0–1 years")] += 1
        elif years < 3:
            bands[_("1–3 years")] += 1
        elif years < 5:
            bands[_("3–5 years")] += 1
        elif years < 10:
            bands[_("5–10 years")] += 1
        else:
            bands[_("10+ years")] += 1

    avg_tenure = round(sum(tenures) / len(tenures), 1) if tenures else 0
    dept_rows = [
        {
            "department": dept,
            "count": len(vals),
            "avg_tenure": round(sum(vals) / len(vals), 1),
        }
        for dept, vals in sorted(by_dept.items(), key=lambda x: -len(x[1]))
    ]

    return {
        "title": _("Tenure & Longevity"),
        "kpis": [
            {
                "label": _("Avg tenure (yrs)"),
                "value": avg_tenure,
                "hint": _("Active employees with joining date"),
            },
            {
                "label": _("With joining date"),
                "value": len(tenures),
                "hint": _("Included in calculation"),
            },
            {
                "label": _("Under 1 year"),
                "value": bands[_("0–1 years")],
                "hint": _("New joiners band"),
            },
            {
                "label": _("10+ years"),
                "value": bands[_("10+ years")],
                "hint": _("Long-tenure cohort"),
            },
        ],
        "charts": [
            {
                "id": "tenure_bands",
                "type": "bar",
                "title": _("Tenure Bands"),
                "categories": list(bands.keys()),
                "series": [{"name": _("Employees"), "data": list(bands.values())}],
            }
        ],
        "table": {
            "columns": [
                {"key": "department", "label": _("Department")},
                {"key": "count", "label": _("Headcount")},
                {"key": "avg_tenure", "label": _("Avg Tenure (yrs)")},
            ],
            "rows": dept_rows,
        },
        "explorer_url_name": "employee-report",
    }


def turnover_attrition(filters: ReportFilters) -> dict:
    """Turnover (all exits) using shared exit sources — not voluntary attrition."""
    from employee.models import EmployeeWorkInformation
    from report.formulas import turnover_rate as formula_turnover
    from report.metrics._exits import exits_in_period, iter_exits

    months = []
    for month_start, month_end, label in iter_months(filters.to_date, 6):
        end = min(month_end, filters.to_date)
        hires_qs = EmployeeWorkInformation.objects.filter(
            date_joining__gte=month_start,
            date_joining__lte=end,
        )
        hires_qs = apply_org_filters(
            hires_qs, filters, prefix="", employee_prefix="employee_id"
        )
        hires = hires_qs.count()
        exits = exits_in_period(filters, from_date=month_start, to_date=end)
        months.append(
            {"month": label, "hires": hires, "exits": exits, "net": hires - exits}
        )

    window_start = month_offset(filters.to_date, 5)
    period_exits = iter_exits(filters, from_date=window_start, to_date=filters.to_date)
    total_exits = len(period_exits)
    total_hires = sum(m["hires"] for m in months)

    # Average of month-end active HC over the 6 month windows
    month_end_counts = []
    for month_start, month_end, _label in iter_months(filters.to_date, 6):
        end = min(month_end, filters.to_date)
        # Active employees joined by month end (proxy closing HC)
        hc = (
            apply_org_filters(
                EmployeeWorkInformation.objects.filter(date_joining__lte=end).filter(
                    Q(employee_id__is_active=True)
                    | Q(
                        employee_id__is_active=False,
                        contract_end_date__gt=end,
                    )
                ),
                filters,
                prefix="",
                employee_prefix="employee_id",
                apply_employment_status=False,
            )
            .values("employee_id")
            .distinct()
            .count()
        )
        month_end_counts.append(hc)
    avg_headcount = (
        sum(month_end_counts) / len(month_end_counts) if month_end_counts else 0
    )
    rate = formula_turnover(total_hires, total_exits, avg_headcount)

    # One pass for both the first-year count and the department breakdown.
    # These were two loops over the same list running identical work-info
    # lookups. Measured: this does not change the query count (iter_exits
    # already select_relates work_info, so the per-row fallback almost never
    # fired) -- it is a readability change, plus a bulk fetch instead of a
    # per-row one on the rare path where the relation really is missing.
    missing = [
        row["employee_id"]
        for row in period_exits
        if getattr(row.get("employee"), "employee_work_info", None) is None
    ]
    fallback_wi = {}
    if missing:
        try:
            fallback_wi = {
                wi.employee_id_id: wi
                for wi in EmployeeWorkInformation.objects.filter(
                    employee_id__in=missing
                ).select_related("department_id")
            }
        except Exception:
            logger.exception("Could not backfill work info for exit rows")

    first_year = 0
    dept_counter = Counter()
    for row in period_exits:
        emp = row.get("employee")
        wi = getattr(emp, "employee_work_info", None) if emp else None
        if wi is None:
            wi = fallback_wi.get(row["employee_id"])

        joining = getattr(wi, "date_joining", None) if wi else None
        if joining and row["exit_date"] and (row["exit_date"] - joining).days <= 365:
            first_year += 1

        dept = (
            getattr(getattr(wi, "department_id", None), "department", None)
            if wi
            else None
        )
        dept_counter[dept or str(_("Unassigned"))] += 1

    by_dept = [{"department": k, "count": v} for k, v in dept_counter.most_common()]

    return {
        "title": _("Turnover (All Exits)"),
        # This report deliberately analyses a fixed rolling 6-month window
        # anchored on to_date (see window_start above) so the rate stays a
        # stable trend metric -- it does not read filters.from_date. Declaring
        # the real window here stops run_report defaulting the header to the
        # user's picked period, which made a 1-month and a 20-month selection
        # display different headers over identical numbers.
        "period": {
            "from_date": window_start.isoformat(),
            "to_date": filters.to_date.isoformat(),
            "preset": "rolling_6m",
            "label": _("Rolling 6 months"),
        },
        "period_note": _(
            "Fixed rolling 6-month window — this report ignores the selected "
            "start date so the turnover rate stays comparable between runs."
        ),
        "kpis": [
            {
                "label": _("Turnover rate (6m)"),
                "value": f"{rate}%",
                "hint": _("Exits ÷ average month-end headcount"),
            },
            {
                "label": _("Exits (6m)"),
                "value": total_exits,
                "hint": _("Offboarding / resignation / inactive fallback"),
            },
            {
                "label": _("Hires (6m)"),
                "value": total_hires,
                "hint": _("Joined in window"),
            },
            {
                "label": _("First-year exits"),
                "value": first_year,
                "hint": _("Tenure ≤ 1 year at exit_date"),
            },
        ],
        "charts": [
            {
                "id": "hires_exits",
                "type": "line",
                "title": _("Hires vs Exits"),
                "categories": [m["month"] for m in months],
                "series": [
                    {"name": _("Hires"), "data": [m["hires"] for m in months]},
                    {"name": _("Exits"), "data": [m["exits"] for m in months]},
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "month", "label": _("Month")},
                {"key": "hires", "label": _("Hires")},
                {"key": "exits", "label": _("Exits")},
                {"key": "net", "label": _("Net")},
            ],
            "rows": months
            + [
                {
                    "month": _("Dept exit: %(dept)s") % {"dept": r["department"]},
                    "hires": "",
                    "exits": r["count"],
                    "net": "",
                }
                for r in by_dept
            ],
        },
        "explorer_url_name": "employee-report",
    }


def joiners_leavers(filters: ReportFilters) -> dict:
    from employee.models import EmployeeWorkInformation
    from report.metrics._exits import iter_exits

    hires_qs = EmployeeWorkInformation.objects.filter(
        date_joining__gte=filters.from_date,
        date_joining__lte=filters.to_date,
    )
    hires_qs = apply_org_filters(
        hires_qs, filters, prefix="", employee_prefix="employee_id"
    )
    hires = hires_qs.count()

    exit_rows = iter_exits(
        filters, from_date=filters.from_date, to_date=filters.to_date
    )
    exits = len(exit_rows)

    trend = []
    for month_start, month_end, label in iter_months(filters.to_date, 6):
        end = min(month_end, filters.to_date)
        count = apply_org_filters(
            EmployeeWorkInformation.objects.filter(date_joining__lte=end),
            filters,
            prefix="",
            employee_prefix="employee_id",
        ).count()
        trend.append({"month": label, "count": count})

    hire_rows = list(
        hires_qs.select_related("employee_id", "department_id")
        .order_by("-date_joining")[:50]
        .values(
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "department_id__department",
            "date_joining",
            "job_position_id__job_position",
        )
    )

    table_rows = [
        {
            "type": _("Joiner"),
            "name": f"{r['employee_id__employee_first_name']} {r['employee_id__employee_last_name'] or ''}".strip(),
            "department": r["department_id__department"] or "",
            "position": r["job_position_id__job_position"] or "",
            "date": r["date_joining"].isoformat() if r["date_joining"] else "",
            "source": "joining",
        }
        for r in hire_rows
    ]
    for row in exit_rows[:50]:
        emp = row.get("employee")
        wi = getattr(emp, "employee_work_info", None) if emp else None
        if wi is None and emp is not None:
            try:
                wi = EmployeeWorkInformation.objects.filter(employee_id=emp).first()
            except Exception:
                wi = None
        first = getattr(emp, "employee_first_name", "") if emp else ""
        last = getattr(emp, "employee_last_name", "") if emp else ""
        dept = (
            getattr(getattr(wi, "department_id", None), "department", "") if wi else ""
        )
        pos = (
            getattr(getattr(wi, "job_position_id", None), "job_position", "")
            if wi
            else ""
        )
        table_rows.append(
            {
                "type": _("Leaver"),
                "name": f"{first} {last or ''}".strip(),
                "department": dept or "",
                "position": pos or "",
                "date": row["exit_date"].isoformat(),
                "source": row["source"],
            }
        )

    closing_hc = trend[-1]["count"] if trend else 0

    return {
        "title": _("Joiners & Leavers"),
        "kpis": [
            {"label": _("Joiners"), "value": hires, "hint": _("In selected period")},
            {"label": _("Leavers"), "value": exits, "hint": _("In selected period")},
            {
                "label": _("Net change"),
                "value": hires - exits,
                "hint": _("Joiners − leavers"),
            },
            {
                "label": _("Closing HC (proxy)"),
                "value": closing_hc,
                "hint": _("Joined on/before period end (active filter)"),
            },
        ],
        "charts": [
            {
                "id": "headcount_trend",
                "type": "line",
                "title": _("Headcount Trend"),
                "categories": [t["month"] for t in trend],
                "series": [
                    {"name": _("Headcount"), "data": [t["count"] for t in trend]}
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "type", "label": _("Type")},
                {"key": "name", "label": _("Employee")},
                {"key": "department", "label": _("Department")},
                {"key": "position", "label": _("Position")},
                {"key": "date", "label": _("Date")},
                {"key": "source", "label": _("Source")},
            ],
            "rows": table_rows,
        },
        "explorer_url_name": "employee-report",
    }


def headcount_bridge(filters: ReportFilters) -> dict:
    """Opening → hires → exits → closing headcount bridge for the selected period."""
    from employee.models import EmployeeWorkInformation
    from report.metrics._exits import iter_exits

    opening = (
        apply_org_filters(
            EmployeeWorkInformation.objects.filter(
                date_joining__lt=filters.from_date
            ).filter(
                Q(employee_id__is_active=True)
                | Q(
                    employee_id__is_active=False,
                    contract_end_date__gte=filters.from_date,
                )
            ),
            filters,
            prefix="",
            employee_prefix="employee_id",
            apply_employment_status=False,
        )
        .values("employee_id")
        .distinct()
        .count()
    )

    hires_qs = EmployeeWorkInformation.objects.filter(
        date_joining__gte=filters.from_date,
        date_joining__lte=filters.to_date,
    )
    hires_qs = apply_org_filters(
        hires_qs, filters, prefix="", employee_prefix="employee_id"
    )
    hires = hires_qs.count()
    exit_rows = iter_exits(
        filters, from_date=filters.from_date, to_date=filters.to_date
    )
    exits = len(exit_rows)
    closing = max(0, opening + hires - exits)
    # Cross-check with closing HC proxy (joined by period end, active filter)
    closing_proxy = apply_org_filters(
        EmployeeWorkInformation.objects.filter(date_joining__lte=filters.to_date),
        filters,
        prefix="",
        employee_prefix="employee_id",
    ).count()

    by_source = Counter(r["source"] for r in exit_rows)
    rows = [
        {
            "step": _("Opening headcount"),
            "count": opening,
            "note": _("Joined before period start"),
        },
        {"step": _("(+) Joiners"), "count": hires, "note": _("date_joining in period")},
        {"step": _("(−) Leavers"), "count": exits, "note": _("Shared exit sources")},
        {
            "step": _("Closing (bridge)"),
            "count": closing,
            "note": _("Opening + joiners − leavers"),
        },
        {
            "step": _("Closing (active proxy)"),
            "count": closing_proxy,
            "note": _("Joined on/before period end · active filter"),
        },
    ]
    for source, count in by_source.most_common():
        rows.append(
            {
                "step": _("Leaver source: %(s)s") % {"s": source},
                "count": count,
                "note": "",
            }
        )

    return {
        "title": _("Headcount Bridge"),
        "kpis": [
            {"label": _("Opening"), "value": opening, "hint": _("Before period")},
            {"label": _("Joiners"), "value": hires, "hint": _("In period")},
            {"label": _("Leavers"), "value": exits, "hint": _("In period")},
            {
                "label": _("Closing (bridge)"),
                "value": closing,
                "hint": _("Opening + joiners − leavers"),
            },
        ],
        "charts": [
            {
                "id": "hc_bridge",
                "type": "bar",
                "title": _("Bridge steps"),
                "categories": [r["step"] for r in rows[:4]],
                "series": [
                    {"name": _("Count"), "data": [r["count"] for r in rows[:4]]}
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "step", "label": _("Step")},
                {"key": "count", "label": _("Count")},
                {"key": "note", "label": _("Notes")},
            ],
            "rows": rows,
        },
        "explorer_url_name": "employee-report",
    }


def exit_analysis(filters: ReportFilters) -> dict:
    """Exit mix by source / dept / tenure — no voluntary split without reason fields."""
    from employee.models import EmployeeWorkInformation
    from report.metrics._exits import iter_exits

    exit_rows = iter_exits(
        filters, from_date=filters.from_date, to_date=filters.to_date
    )
    if not exit_rows:
        return empty_report(
            _("Exit Analysis"),
            filters,
            _("No exits found in the selected period."),
        )

    by_source = Counter(r["source"] for r in exit_rows)
    tenure_bands = Counter()
    dept_counter = Counter()
    table_rows = []

    for row in exit_rows:
        emp = row.get("employee")
        wi = getattr(emp, "employee_work_info", None) if emp else None
        if wi is None and emp is not None:
            try:
                wi = EmployeeWorkInformation.objects.filter(employee_id=emp).first()
            except Exception:
                wi = None
        joining = getattr(wi, "date_joining", None) if wi else None
        tenure_days = None
        if joining and row.get("exit_date"):
            tenure_days = (row["exit_date"] - joining).days
            if tenure_days < 90:
                tenure_bands[_("< 90 days")] += 1
            elif tenure_days < 365:
                tenure_bands[_("90 days – 1 year")] += 1
            elif tenure_days < 365 * 3:
                tenure_bands[_("1–3 years")] += 1
            else:
                tenure_bands[_("3+ years")] += 1
        else:
            tenure_bands[_("Unknown tenure")] += 1

        dept = (
            getattr(getattr(wi, "department_id", None), "department", None)
            if wi
            else None
        )
        dept_counter[dept or str(_("Unassigned"))] += 1
        first = getattr(emp, "employee_first_name", "") if emp else ""
        last = getattr(emp, "employee_last_name", "") if emp else ""
        table_rows.append(
            {
                "name": f"{first} {last or ''}".strip(),
                "exit_date": (
                    row["exit_date"].isoformat() if row.get("exit_date") else ""
                ),
                "source": row["source"],
                "department": dept or "",
                "tenure_days": tenure_days if tenure_days is not None else "",
            }
        )

    source_rows = [{"bucket": k, "count": v} for k, v in by_source.most_common()]
    tenure_rows = [{"bucket": k, "count": v} for k, v in tenure_bands.most_common()]

    return {
        "title": _("Exit Analysis"),
        "kpis": [
            {"label": _("Exits"), "value": len(exit_rows), "hint": _("In period")},
            {
                "label": _("Exit sources"),
                "value": len(by_source),
                "hint": _("Offboarding / resignation / inactive fallback"),
            },
            {
                "label": _("Top source"),
                "value": source_rows[0]["bucket"] if source_rows else "—",
                "hint": "",
            },
            {
                "label": _("Departments"),
                "value": len(dept_counter),
                "hint": _("With exits"),
            },
        ],
        "charts": [
            {
                "id": "exit_source",
                "type": "donut",
                "title": _("Exits by source"),
                "categories": [r["bucket"] for r in source_rows],
                "series": [
                    {"name": _("Exits"), "data": [r["count"] for r in source_rows]}
                ],
            },
            {
                "id": "exit_tenure",
                "type": "bar",
                "title": _("Tenure at exit"),
                "categories": [r["bucket"] for r in tenure_rows],
                "series": [
                    {"name": _("Exits"), "data": [r["count"] for r in tenure_rows]}
                ],
            },
        ],
        "table": {
            "columns": [
                {"key": "name", "label": _("Employee")},
                {"key": "exit_date", "label": _("Exit date")},
                {"key": "source", "label": _("Source")},
                {"key": "department", "label": _("Department")},
                {"key": "tenure_days", "label": _("Tenure (days)")},
            ],
            "rows": table_rows[:100],
        },
        "explorer_url_name": "employee-report",
    }


def new_hire_90_day_attrition(filters: ReportFilters) -> dict:
    """Early attrition among period joiners (exit within 90 days of joining)."""
    from employee.models import EmployeeWorkInformation
    from report.formulas import early_attrition_rate
    from report.metrics._exits import iter_exits

    hires_qs = EmployeeWorkInformation.objects.filter(
        date_joining__gte=filters.from_date,
        date_joining__lte=filters.to_date,
    )
    # This report is *about* people who left, so the cohort must include
    # inactive employees. apply_org_filters defaults to active-only, which
    # dropped every leaver from the joiner cohort and made the numerator
    # structurally zero -- the rate could never be anything but 0%.
    hires_qs = apply_org_filters(
        hires_qs,
        filters,
        prefix="",
        employee_prefix="employee_id",
        apply_employment_status=False,
    )
    hire_rows = list(
        hires_qs.select_related("employee_id", "department_id").values(
            "employee_id",
            "date_joining",
            "department_id__department",
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
        )
    )
    cohort = len(hire_rows)
    if not cohort:
        return empty_report(
            _("New-Hire 90-Day Attrition"),
            filters,
            _("No joiners in the selected period."),
        )

    # Look ahead so exits shortly after period end still count for late joiners
    from datetime import timedelta

    exit_horizon = filters.to_date + timedelta(days=90)
    exits = iter_exits(filters, from_date=filters.from_date, to_date=exit_horizon)
    exit_by_emp = {r["employee_id"]: r for r in exits}

    early = []
    for h in hire_rows:
        emp_id = h["employee_id"]
        joining = h["date_joining"]
        if not joining or emp_id not in exit_by_emp:
            continue
        exit_row = exit_by_emp[emp_id]
        if (exit_row["exit_date"] - joining).days <= 90:
            early.append(
                {
                    "name": f"{h['employee_id__employee_first_name']} {h['employee_id__employee_last_name'] or ''}".strip(),
                    "joined": joining.isoformat(),
                    "exit_date": exit_row["exit_date"].isoformat(),
                    "days": (exit_row["exit_date"] - joining).days,
                    "source": exit_row["source"],
                    "department": h["department_id__department"] or "",
                }
            )

    rate = early_attrition_rate(len(early), cohort)
    return {
        "title": _("New-Hire 90-Day Attrition"),
        "kpis": [
            {
                "label": _("90-day attrition"),
                "value": f"{rate}%",
                "hint": _("Early exits ÷ period joiners"),
            },
            {"label": _("Cohort joiners"), "value": cohort, "hint": _("In period")},
            {
                "label": _("Early exits"),
                "value": len(early),
                "hint": _("Exit ≤ 90 days after joining"),
            },
            {
                "label": _("Retained past 90d (proxy)"),
                "value": cohort - len(early),
                "hint": _("No recorded early exit"),
            },
        ],
        "charts": [
            {
                "id": "early_attrition",
                "type": "donut",
                "title": _("Cohort outcomes"),
                "categories": [_("Early exit"), _("No early exit")],
                "series": [
                    {
                        "name": _("Joiners"),
                        "data": [len(early), cohort - len(early)],
                    }
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "name", "label": _("Employee")},
                {"key": "joined", "label": _("Joined")},
                {"key": "exit_date", "label": _("Exit date")},
                {"key": "days", "label": _("Days to exit")},
                {"key": "source", "label": _("Source")},
                {"key": "department", "label": _("Department")},
            ],
            "rows": early[:100],
        },
        "explorer_url_name": "employee-report",
    }


def workforce_composition_drilldown(
    filters: ReportFilters, params: dict, request=None
) -> dict:
    """Drill into workforce composition by department / type / location label."""
    from report.drilldown import (
        apply_subordinate_scope,
        drilldown_payload,
        employee_link,
        empty_drilldown,
    )

    dimension = (params.get("dimension") or "department").strip().lower()
    value = (params.get("value") or "").strip()
    if not value:
        return empty_drilldown(
            _("Workforce Composition"), dimension, value, _("Missing dimension value.")
        )

    qs = _employees(filters)
    qs = apply_subordinate_scope(request, qs, perm="employee.view_employee", field="id")

    title = _("Workforce Composition")
    if dimension in ("department", "dept", "by_dept"):
        qs = qs.filter(employee_work_info__department_id__department=value)
        dimension = "department"
        title = _("Employees in %(dept)s") % {"dept": value}
    elif dimension in ("employee_type", "type", "by_type"):
        qs = qs.filter(employee_work_info__employee_type_id__employee_type=value)
        dimension = "employee_type"
        title = _("Employees · %(type)s") % {"type": value}
    elif dimension in ("location",):
        qs = qs.filter(employee_work_info__location=value)
        title = _("Employees in %(loc)s") % {"loc": value}
    elif dimension in ("job_position", "job"):
        qs = qs.filter(employee_work_info__job_position_id__job_position=value)
        dimension = "job_position"
        title = _("Employees · %(job)s") % {"job": value}
    else:
        return empty_drilldown(title, dimension, value, _("Unsupported dimension."))

    limit = int((params.get("limit") or filters.extra.get("row_limit") or 200))
    total = qs.count()
    rows = []
    for emp in qs.select_related(
        "employee_work_info",
        "employee_work_info__department_id",
        "employee_work_info__job_position_id",
    ).order_by("employee_first_name", "employee_last_name")[:limit]:
        wi = getattr(emp, "employee_work_info", None)
        dept = ""
        job = ""
        try:
            dept = wi.department_id.department if wi and wi.department_id_id else ""
        except Exception:
            dept = ""
        try:
            job = (
                wi.job_position_id.job_position if wi and wi.job_position_id_id else ""
            )
        except Exception:
            job = ""
        rows.append(
            {
                "employee": (
                    emp.get_full_name() if hasattr(emp, "get_full_name") else str(emp)
                ),
                "badge": getattr(emp, "badge_id", "") or "",
                "department": dept,
                "job_position": job,
                "link": employee_link(emp.id),
            }
        )
    return drilldown_payload(
        title=title,
        dimension=dimension,
        value=value,
        columns=[
            {"key": "employee", "label": _("Employee")},
            {"key": "badge", "label": _("Badge")},
            {"key": "department", "label": _("Department")},
            {"key": "job_position", "label": _("Job position")},
            {"key": "link", "label": _("Open"), "type": "link"},
        ],
        rows=rows,
        truncated=total > len(rows),
    )


def turnover_attrition_drilldown(
    filters: ReportFilters, params: dict, request=None
) -> dict:
    """Who exited, over the same rolling 6-month window the KPIs use.

    The report deliberately ignores filters.from_date (see
    turnover_attrition), so the drill-down has to use that same window or the
    list would not add up to the rate above it.
    """
    from report.metrics._exits import exit_drilldown

    return exit_drilldown(
        filters,
        params,
        request,
        title=_("Exits · Rolling 6 months"),
        from_date=month_offset(filters.to_date, 5),
        to_date=filters.to_date,
    )


def exit_analysis_drilldown(filters: ReportFilters, params: dict, request=None) -> dict:
    from report.metrics._exits import exit_drilldown

    return exit_drilldown(filters, params, request, title=_("Exits in period"))


def joiners_leavers_drilldown(
    filters: ReportFilters, params: dict, request=None
) -> dict:
    """Joiners or leavers, depending on the clicked series."""
    from employee.models import EmployeeWorkInformation
    from report.drilldown import (
        apply_subordinate_scope,
        drilldown_payload,
        employee_link,
        empty_drilldown,
    )
    from report.metrics._exits import exit_drilldown

    dimension = (params.get("dimension") or "").strip().lower()
    value = (params.get("value") or "").strip()

    # The chart plots hires and exits side by side, so the series decides
    # which population to list.
    if dimension in ("exits", "leavers", "exit"):
        return exit_drilldown(filters, params, request, title=_("Leavers in period"))

    qs = EmployeeWorkInformation.objects.filter(
        date_joining__gte=filters.from_date,
        date_joining__lte=filters.to_date,
    )
    qs = apply_org_filters(qs, filters, prefix="", employee_prefix="employee_id")
    qs = apply_subordinate_scope(
        request, qs, perm="employee.view_employee", field="employee_id"
    )
    if value and dimension in ("department", "dept", "by_dept"):
        qs = qs.filter(department_id__department=value)
        dimension = "department"
    elif value and dimension in ("month",):
        qs = [
            r
            for r in qs.select_related("employee_id", "department_id")
            if r.date_joining and r.date_joining.strftime("%b %Y") == value
        ]

    if not isinstance(qs, list):
        qs = list(qs.select_related("employee_id", "department_id"))
    if not qs:
        return empty_drilldown(_("Joiners in period"), dimension or "joiners", value)

    limit = int((params.get("limit") or filters.extra.get("row_limit") or 200))
    total = len(qs)
    rows = []
    for wi in qs[:limit]:
        emp = wi.employee_id
        rows.append(
            {
                "employee": str(emp) if emp else "",
                "department": getattr(wi.department_id, "department", "") or "",
                "date_joining": wi.date_joining.isoformat() if wi.date_joining else "",
                "url": employee_link(getattr(emp, "id", None)),
            }
        )
    return drilldown_payload(
        title=_("Joiners in period"),
        dimension=dimension or "joiners",
        value=value,
        columns=[
            {"key": "employee", "label": _("Employee")},
            {"key": "department", "label": _("Department")},
            {"key": "date_joining", "label": _("Joined")},
        ],
        rows=rows,
        truncated=total > len(rows),
    )


def new_hire_90_day_attrition_drilldown(
    filters: ReportFilters, params: dict, request=None
) -> dict:
    """Only the cohort members who left within 90 days of joining.

    Mirrors the report: the exit window looks 90 days past period end so a
    late joiner's early exit still counts, and the row is kept only when the
    gap between joining and exit is within 90 days.
    """
    from datetime import timedelta

    from employee.models import EmployeeWorkInformation
    from report.metrics._exits import exit_drilldown

    joining_by_emp = dict(
        apply_org_filters(
            EmployeeWorkInformation.objects.filter(
                date_joining__gte=filters.from_date,
                date_joining__lte=filters.to_date,
            ),
            filters,
            prefix="",
            employee_prefix="employee_id",
            # Leavers are the whole point of this cohort, so active-only
            # filtering would exclude exactly the rows we are looking for.
            apply_employment_status=False,
        ).values_list("employee_id", "date_joining")
    )

    def _within_90_days(row) -> bool:
        joined = joining_by_emp.get(row["employee_id"])
        if not joined or not row.get("exit_date"):
            return False
        return 0 <= (row["exit_date"] - joined).days <= 90

    return exit_drilldown(
        filters,
        params,
        request,
        title=_("New hires who left within 90 days"),
        from_date=filters.from_date,
        to_date=filters.to_date + timedelta(days=90),
        extra_filter=_within_90_days,
    )

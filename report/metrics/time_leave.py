"""Time, attendance, and leave metrics."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils.translation import gettext as _

from report.engine import ReportFilters, apply_org_filters, iter_months


def attendance_summary(filters: ReportFilters) -> dict:
    from attendance.models import Attendance, AttendanceLateComeEarlyOut
    from employee.models import Employee

    active = apply_org_filters(
        Employee.objects.all(), filters, prefix="employee_work_info", employee_prefix=""
    )
    headcount = active.count()

    att_qs = Attendance.objects.filter(
        attendance_date__gte=filters.from_date,
        attendance_date__lte=filters.to_date,
    )
    att_qs = apply_org_filters(
        att_qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )

    present_days = att_qs.values("employee_id", "attendance_date").distinct().count()
    unique_present = att_qs.values("employee_id").distinct().count()

    late = AttendanceLateComeEarlyOut.objects.filter(
        type="late_come",
        attendance_id__attendance_date__gte=filters.from_date,
        attendance_id__attendance_date__lte=filters.to_date,
    )
    late = apply_org_filters(
        late,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )
    late_count = late.count()

    early = AttendanceLateComeEarlyOut.objects.filter(
        type="early_out",
        attendance_id__attendance_date__gte=filters.from_date,
        attendance_id__attendance_date__lte=filters.to_date,
    )
    early = apply_org_filters(
        early,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )

    ot_seconds = att_qs.aggregate(total=Sum("overtime_second"))["total"] or 0
    worked_seconds = att_qs.aggregate(total=Sum("at_work_second"))["total"] or 0
    ot_hours = round(ot_seconds / 3600, 1)
    avg_hours = round(worked_seconds / 3600 / present_days, 2) if present_days else 0

    by_dept = list(
        att_qs.filter(employee_id__employee_work_info__department_id__isnull=False)
        .values("employee_id__employee_work_info__department_id__department")
        .annotate(
            records=Count("id"),
            employees=Count("employee_id", distinct=True),
            ot=Sum("overtime_second"),
        )
        .order_by("-records")[:15]
    )

    return {
        "title": _("Attendance Summary"),
        "kpis": [
            {"label": _("Active headcount"), "value": headcount, "hint": ""},
            {
                "label": _("Present employee-days"),
                "value": present_days,
                "hint": _("Unique employee × day"),
            },
            {"label": _("Late comes"), "value": late_count, "hint": _("In period")},
            {
                "label": _("OT hours"),
                "value": ot_hours,
                "hint": _("Sum of overtime"),
            },
        ],
        "charts": [
            {
                "id": "dept_attendance",
                "type": "bar",
                "title": _("Attendance Records by Department"),
                "categories": [
                    r["employee_id__employee_work_info__department_id__department"]
                    for r in by_dept
                ],
                "series": [
                    {"name": _("Records"), "data": [r["records"] for r in by_dept]}
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "department", "label": _("Department")},
                {"key": "employees", "label": _("Employees")},
                {"key": "records", "label": _("Records")},
                {"key": "ot_hours", "label": _("OT Hours")},
            ],
            "rows": [
                {
                    "department": r[
                        "employee_id__employee_work_info__department_id__department"
                    ],
                    "employees": r["employees"],
                    "records": r["records"],
                    "ot_hours": round((r["ot"] or 0) / 3600, 1),
                }
                for r in by_dept
            ],
        },
        "meta": {
            "unique_present": unique_present,
            "early_out": early.count(),
            "avg_hours_per_present_day": avg_hours,
        },
        "explorer_url_name": "attendance-report",
    }


def absenteeism_rate(filters: ReportFilters) -> dict:
    """Calendar-aware punch-gap absenteeism (leave-adjusted when possible)."""
    from attendance.models import Attendance
    from employee.models import Employee
    from report.formulas import absenteeism_rate as formula_absenteeism
    from report.metrics._calendar import count_expected_working_days

    total_employees = apply_org_filters(
        Employee.objects.all(), filters, prefix="employee_work_info", employee_prefix=""
    ).count()

    months = []
    for month_start, month_end, label in iter_months(filters.to_date, 6):
        end = min(month_end, filters.to_date)
        working_days = count_expected_working_days(month_start, end)
        if working_days == 0 or total_employees == 0:
            months.append(
                {
                    "month": label,
                    "rate": 0,
                    "absent_days": 0,
                    "expected_days": 0,
                    "leave_days": 0,
                }
            )
            continue

        present_qs = Attendance.objects.filter(
            attendance_date__gte=month_start,
            attendance_date__lte=end,
        )
        present_qs = apply_org_filters(
            present_qs,
            filters,
            prefix="employee_id__employee_work_info",
            employee_prefix="employee_id",
        )
        present_days = (
            present_qs.values("employee_id", "attendance_date").distinct().count()
        )

        leave_days = 0
        try:
            from leave.models import LeaveRequest

            leave_qs = LeaveRequest.objects.filter(
                status="approved",
                start_date__lte=end,
            ).filter(Q(end_date__gte=month_start) | Q(end_date__isnull=True))
            leave_qs = apply_org_filters(
                leave_qs,
                filters,
                prefix="employee_id__employee_work_info",
                employee_prefix="employee_id",
            )
            # Approximate leave-employee-days in month via requested_days (capped
            # by month length); not perfect overlap math but avoids counting leave
            # as unscheduled absence.
            for lr in leave_qs.only(
                "start_date", "end_date", "requested_days"
            ).iterator():
                lr_start = max(lr.start_date, month_start)
                lr_end = min(lr.end_date or lr.start_date, end)
                if lr_end < lr_start:
                    continue
                span = (lr_end - lr_start).days + 1
                leave_days += min(float(lr.requested_days or span), span)
        except Exception:
            leave_days = 0

        expected = total_employees * working_days
        absent = max(0, expected - present_days - leave_days)
        months.append(
            {
                "month": label,
                "rate": formula_absenteeism(absent, expected),
                "absent_days": round(absent, 1),
                "expected_days": expected,
                "leave_days": round(leave_days, 1),
            }
        )

    latest = months[-1]["rate"] if months else 0
    avg_rate = round(sum(m["rate"] for m in months) / len(months), 1) if months else 0

    return {
        "title": _("Absenteeism Rate"),
        "kpis": [
            {
                "label": _("Latest month rate"),
                "value": f"{latest}%",
                "hint": _("Unscheduled absence / calendar expected days"),
            },
            {
                "label": _("6-month avg"),
                "value": f"{avg_rate}%",
                "hint": _("Average rate"),
            },
            {
                "label": _("Active headcount"),
                "value": total_employees,
                "hint": _("Denominator base"),
            },
            {
                "label": _("Absent days (latest)"),
                "value": months[-1]["absent_days"] if months else 0,
                "hint": _("After subtracting approved leave"),
            },
        ],
        "charts": [
            {
                "id": "absenteeism",
                "type": "line",
                "title": _("Absenteeism Trend"),
                "categories": [m["month"] for m in months],
                "series": [{"name": _("Rate %"), "data": [m["rate"] for m in months]}],
            }
        ],
        "table": {
            "columns": [
                {"key": "month", "label": _("Month")},
                {"key": "rate", "label": _("Rate %")},
                {"key": "absent_days", "label": _("Unscheduled Absent Days")},
                {"key": "leave_days", "label": _("Approved Leave Days")},
                {"key": "expected_days", "label": _("Expected Days")},
            ],
            "rows": months,
        },
        "explorer_url_name": "attendance-report",
    }


def overtime_analysis(filters: ReportFilters) -> dict:
    from attendance.models import Attendance
    from report.metrics._privacy import allow_named_ot_rows

    att_qs = Attendance.objects.filter(
        attendance_date__gte=filters.from_date,
        attendance_date__lte=filters.to_date,
        overtime_second__gt=0,
    )
    att_qs = apply_org_filters(
        att_qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )

    total_ot = att_qs.aggregate(total=Sum("overtime_second"))["total"] or 0
    approved = (
        att_qs.filter(attendance_overtime_approve=True).aggregate(
            total=Sum("approved_overtime_second")
        )["total"]
        or 0
    )

    # Concentration view, absorbed from the former ot-concentration report:
    # same base queryset, same department chart, same privacy gate -- the only
    # things it added were the top-5/top-10 share KPIs and a per-department
    # share column, so it is a view of this report rather than its own report.
    from report.formulas import ot_concentration_share

    by_emp_totals = list(
        att_qs.values("employee_id")
        .annotate(total_seconds=Sum("overtime_second"))
        .order_by("-total_seconds")
        .values_list("total_seconds", flat=True)
    )
    top5_share = ot_concentration_share(
        sum(v or 0 for v in by_emp_totals[:5]), total_ot
    )
    top10_share = ot_concentration_share(
        sum(v or 0 for v in by_emp_totals[:10]), total_ot
    )

    by_dept = list(
        att_qs.filter(employee_id__employee_work_info__department_id__isnull=False)
        .values("employee_id__employee_work_info__department_id__department")
        .annotate(
            total_seconds=Sum("overtime_second"),
            approved_seconds=Sum("approved_overtime_second"),
            employees=Count("employee_id", distinct=True),
        )
        .order_by("-total_seconds")[:20]
    )

    include_names = allow_named_ot_rows(filters)
    table_columns = [
        {"key": "department", "label": _("Department")},
        {"key": "ot_hours", "label": _("OT Hours")},
        {"key": "employees", "label": _("Employees")},
        {"key": "share", "label": _("Share")},
    ]
    table_rows = [
        {
            "department": r[
                "employee_id__employee_work_info__department_id__department"
            ]
            or "",
            "ot_hours": round((r["total_seconds"] or 0) / 3600, 1),
            "employees": r["employees"],
            "share": f"{ot_concentration_share(r['total_seconds'] or 0, total_ot)}%",
        }
        for r in by_dept
    ]

    if include_names:
        by_emp = list(
            att_qs.values(
                "employee_id__employee_first_name",
                "employee_id__employee_last_name",
                "employee_id__employee_work_info__department_id__department",
            )
            .annotate(total_seconds=Sum("overtime_second"))
            .order_by("-total_seconds")[:25]
        )
        table_columns = [
            {"key": "employee", "label": _("Employee")},
            {"key": "department", "label": _("Department")},
            {"key": "ot_hours", "label": _("OT Hours")},
        ]
        table_rows = [
            {
                "employee": f"{r['employee_id__employee_first_name']} {r['employee_id__employee_last_name'] or ''}".strip(),
                "department": r[
                    "employee_id__employee_work_info__department_id__department"
                ]
                or "",
                "ot_hours": round((r["total_seconds"] or 0) / 3600, 1),
            }
            for r in by_emp
        ]

    return {
        "title": _("Overtime Analysis"),
        "kpis": [
            {
                "label": _("Total OT hours"),
                "value": round(total_ot / 3600, 1),
                "hint": _("In period"),
            },
            {
                "label": _("Approved OT hours"),
                "value": round(approved / 3600, 1),
                "hint": _("Approved overtime"),
            },
            {
                "label": _("Employees with OT"),
                "value": att_qs.values("employee_id").distinct().count(),
                "hint": _("Names hidden unless include_names + change_attendance"),
            },
            {
                "label": _("Departments"),
                "value": len(by_dept),
                "hint": _("With OT"),
            },
            {
                "label": _("Top 5 share"),
                "value": f"{top5_share}%",
                "hint": _("OT concentrated in the top 5 employees"),
            },
            {
                "label": _("Top 10 share"),
                "value": f"{top10_share}%",
                "hint": _("OT concentrated in the top 10 employees"),
            },
        ],
        "charts": [
            {
                "id": "ot_dept",
                "type": "bar",
                "title": _("OT Hours by Department"),
                "categories": [
                    r["employee_id__employee_work_info__department_id__department"]
                    for r in by_dept[:12]
                ],
                "series": [
                    {
                        "name": _("OT Hours"),
                        "data": [
                            round((r["total_seconds"] or 0) / 3600, 1)
                            for r in by_dept[:12]
                        ],
                    }
                ],
            }
        ],
        "table": {
            "columns": table_columns,
            "rows": table_rows,
        },
        "explorer_url_name": "attendance-report",
    }


def leave_utilization(filters: ReportFilters) -> dict:
    """Period leave used vs current entitlement snapshot (planner metric)."""
    from leave.models import AvailableLeave, LeaveRequest
    from report.formulas import leave_utilization_rate

    allocations = AvailableLeave.objects.filter(employee_id__is_active=True)
    allocations = apply_org_filters(
        allocations,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )
    if filters.leave_type_id:
        allocations = allocations.filter(leave_type_id=filters.leave_type_id)
    allocation_rows = list(
        allocations.values("leave_type_id", "leave_type_id__name")
        .annotate(
            total_available=Sum("available_days"),
            total_carryforward=Sum("carryforward_days"),
            total_allocated=Sum("total_leave_days"),
        )
        .order_by("-total_allocated")
    )

    leave_qs = LeaveRequest.objects.filter(
        start_date__lte=filters.to_date,
        end_date__gte=filters.from_date,
    )
    leave_qs = apply_org_filters(
        leave_qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )
    if filters.leave_type_id:
        leave_qs = leave_qs.filter(leave_type_id=filters.leave_type_id)
    if filters.leave_status:
        leave_qs = leave_qs.filter(status=filters.leave_status)
    else:
        leave_qs = leave_qs.filter(status="approved")
    used_by_type = {
        row["leave_type_id"]: float(row["total"] or 0)
        for row in leave_qs.values("leave_type_id").annotate(
            total=Sum("requested_days")
        )
    }

    utilization = []
    for item in allocation_rows:
        lt_id = item["leave_type_id"]
        allocated = float(item["total_allocated"] or 0)
        available = float(item["total_available"] or 0) + float(
            item["total_carryforward"] or 0
        )
        used = used_by_type.get(lt_id, 0.0)
        rate = leave_utilization_rate(used, allocated)
        utilization.append(
            {
                "type": item["leave_type_id__name"] or _("Unknown"),
                "allocated": round(allocated, 1),
                "used": round(used, 1),
                "remaining": round(available, 1),
                "rate": rate,
            }
        )

    total_used = sum(u["used"] for u in utilization)
    total_alloc = sum(u["allocated"] for u in utilization)
    overall = leave_utilization_rate(total_used, total_alloc)

    return {
        "title": _("Leave Planning (Used vs Entitlement)"),
        "kpis": [
            {
                "label": _("Period used / entitlement"),
                "value": f"{overall}%",
                "hint": _(
                    "Planner ratio — period approved days ÷ current entitlement snapshot"
                ),
            },
            {
                "label": _("Days used (period)"),
                "value": round(total_used, 1),
                "hint": _("Approved leave in period"),
            },
            {
                "label": _("Entitlement snapshot"),
                "value": round(total_alloc, 1),
                "hint": _("Current total_leave_days (not period accrual)"),
            },
            {"label": _("Leave types"), "value": len(utilization), "hint": ""},
        ],
        "charts": [
            {
                "id": "leave_util",
                "type": "bar",
                "title": _("Used vs entitlement by type"),
                "categories": [u["type"] for u in utilization],
                "series": [
                    {
                        "name": _("Used (period)"),
                        "data": [u["used"] for u in utilization],
                    },
                    {
                        "name": _("Entitlement snapshot"),
                        "data": [u["allocated"] for u in utilization],
                    },
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "type", "label": _("Leave Type")},
                {"key": "allocated", "label": _("Entitlement snapshot")},
                {"key": "used", "label": _("Used (period)")},
                {"key": "remaining", "label": _("Open balance")},
                {"key": "rate", "label": _("Ratio %")},
            ],
            "rows": utilization,
        },
        "explorer_url_name": "leave-report",
    }


def leave_liability(filters: ReportFilters) -> dict:
    from leave.models import AvailableLeave

    qs = AvailableLeave.objects.filter(employee_id__is_active=True)
    qs = apply_org_filters(
        qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )
    if filters.leave_type_id:
        qs = qs.filter(leave_type_id=filters.leave_type_id)

    by_type = []
    aggregated = (
        qs.values("leave_type_id", "leave_type_id__name")
        .annotate(
            avail=Sum("available_days"),
            carry=Sum("carryforward_days"),
            employees=Count("employee_id", distinct=True),
        )
        .order_by("-avail")
    )
    for row in aggregated:
        remaining = float(row["avail"] or 0) + float(row["carry"] or 0)
        by_type.append(
            {
                "type": row["leave_type_id__name"] or _("Unknown"),
                "remaining": round(remaining, 1),
                "employees": row["employees"],
            }
        )
    by_type.sort(key=lambda x: -x["remaining"])

    by_dept = list(
        qs.filter(employee_id__employee_work_info__department_id__isnull=False)
        .values("employee_id__employee_work_info__department_id__department")
        .annotate(
            avail=Sum("available_days"),
            carry=Sum("carryforward_days"),
        )
        .order_by("-avail")
    )
    dept_rows = [
        {
            "department": r[
                "employee_id__employee_work_info__department_id__department"
            ],
            "remaining": round(float(r["avail"] or 0) + float(r["carry"] or 0), 1),
        }
        for r in by_dept
    ]

    total_liability = sum(r["remaining"] for r in by_type)

    return {
        "title": _("Open Leave Balance (Days)"),
        "kpis": [
            {
                "label": _("Open balance (days)"),
                "value": round(total_liability, 1),
                "hint": _("Available + carry forward — not currency liability"),
            },
            {"label": _("Leave types"), "value": len(by_type), "hint": ""},
            {
                "label": _("Departments"),
                "value": len(dept_rows),
                "hint": _("With balances"),
            },
            {
                "label": _("Employees with leave"),
                "value": qs.values("employee_id").distinct().count(),
                "hint": "",
            },
        ],
        "charts": [
            {
                "id": "liability_type",
                "type": "donut",
                "title": _("Liability by Leave Type"),
                "categories": [r["type"] for r in by_type],
                "series": [
                    {"name": _("Days"), "data": [r["remaining"] for r in by_type]}
                ],
            }
        ],
        "table": {
            "columns": [
                {"key": "type", "label": _("Leave Type")},
                {"key": "remaining", "label": _("Open Days")},
                {"key": "employees", "label": _("Employees")},
            ],
            "rows": by_type
            + [
                {
                    "type": _("Dept: %(d)s") % {"d": r["department"]},
                    "remaining": r["remaining"],
                    "employees": "",
                }
                for r in dept_rows
            ],
        },
        "explorer_url_name": "leave-report",
    }


def unscheduled_absence(filters: ReportFilters) -> dict:
    """
    Period unscheduled absence using calendar expected days.

    Absent ≈ expected − present punch days − approved leave days (same method as
    absenteeism-rate, scoped to the selected period rather than a fixed 6m chart).
    """
    from attendance.models import Attendance
    from employee.models import Employee
    from report.formulas import absenteeism_rate as formula_absenteeism
    from report.metrics._calendar import count_expected_working_days

    employees = apply_org_filters(
        Employee.objects.all(), filters, prefix="employee_work_info", employee_prefix=""
    )
    total_employees = employees.count()
    working_days = count_expected_working_days(filters.from_date, filters.to_date)
    expected = total_employees * working_days

    present_qs = Attendance.objects.filter(
        attendance_date__gte=filters.from_date,
        attendance_date__lte=filters.to_date,
    )
    present_qs = apply_org_filters(
        present_qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )
    present_days = (
        present_qs.values("employee_id", "attendance_date").distinct().count()
    )

    leave_days = 0.0
    try:
        from leave.models import LeaveRequest

        leave_qs = LeaveRequest.objects.filter(
            status="approved",
            start_date__lte=filters.to_date,
            end_date__gte=filters.from_date,
        )
        leave_qs = apply_org_filters(
            leave_qs,
            filters,
            prefix="employee_id__employee_work_info",
            employee_prefix="employee_id",
        )
        for lr in leave_qs.only("start_date", "end_date", "requested_days").iterator():
            lr_start = max(lr.start_date, filters.from_date)
            lr_end = min(lr.end_date or lr.start_date, filters.to_date)
            if lr_end < lr_start:
                continue
            span = (lr_end - lr_start).days + 1
            leave_days += min(float(lr.requested_days or span), span)
    except Exception:
        leave_days = 0.0

    absent = max(0.0, expected - present_days - leave_days)
    rate = formula_absenteeism(absent, expected)

    months = []
    for month_start, month_end, label in iter_months(filters.to_date, 6):
        start = max(month_start, filters.from_date)
        end = min(month_end, filters.to_date)
        if end < start:
            continue
        wd = count_expected_working_days(start, end)
        exp = total_employees * wd
        if exp == 0:
            months.append(
                {"month": label, "rate": 0, "absent_days": 0, "expected_days": 0}
            )
            continue
        pqs = Attendance.objects.filter(
            attendance_date__gte=start, attendance_date__lte=end
        )
        pqs = apply_org_filters(
            pqs,
            filters,
            prefix="employee_id__employee_work_info",
            employee_prefix="employee_id",
        )
        present = pqs.values("employee_id", "attendance_date").distinct().count()
        month_absent = max(0, exp - present)
        months.append(
            {
                "month": label,
                "rate": formula_absenteeism(month_absent, exp),
                "absent_days": round(month_absent, 1),
                "expected_days": exp,
            }
        )

    return {
        "title": _("Unscheduled Absence"),
        "kpis": [
            {
                "label": _("Unscheduled absence rate"),
                "value": f"{rate}%",
                "hint": _("After subtracting approved leave"),
            },
            {
                "label": _("Absent days"),
                "value": round(absent, 1),
                "hint": _("Expected − present − approved leave"),
            },
            {
                "label": _("Expected days"),
                "value": expected,
                "hint": _("Calendar working days × headcount"),
            },
            {
                "label": _("Approved leave days"),
                "value": round(leave_days, 1),
                "hint": _("Excluded from unscheduled"),
            },
        ],
        "charts": [
            {
                "id": "unscheduled_trend",
                "type": "line",
                "title": _("Monthly rate (present-gap proxy)"),
                "categories": [m["month"] for m in months],
                "series": [{"name": _("Rate %"), "data": [m["rate"] for m in months]}],
            }
        ],
        "table": {
            "columns": [
                {"key": "month", "label": _("Month")},
                {"key": "rate", "label": _("Rate %")},
                {"key": "absent_days", "label": _("Absent days")},
                {"key": "expected_days", "label": _("Expected days")},
            ],
            "rows": months,
        },
        "explorer_url_name": "attendance-report",
    }


def leave_liability_drilldown(
    filters: ReportFilters, params: dict, request=None
) -> dict:
    """Per-employee open leave balance behind a leave-type total."""
    from leave.models import AvailableLeave
    from report.drilldown import (
        apply_subordinate_scope,
        drilldown_payload,
        employee_link,
        empty_drilldown,
    )

    dimension = (params.get("dimension") or "leave_type").strip().lower()
    value = (params.get("value") or "").strip()

    qs = AvailableLeave.objects.filter(employee_id__is_active=True)
    qs = apply_org_filters(
        qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )
    qs = apply_subordinate_scope(
        request, qs, perm="leave.view_leaverequest", field="employee_id"
    )
    if filters.leave_type_id:
        qs = qs.filter(leave_type_id=filters.leave_type_id)
    if value and dimension in ("leave_type", "type"):
        qs = qs.filter(leave_type_id__name=value)
        dimension = "leave_type"
    elif value and dimension in ("department", "dept"):
        qs = qs.filter(employee_id__employee_work_info__department_id__department=value)
        dimension = "department"

    title = (
        _("Open balance · %(type)s") % {"type": value}
        if value
        else _("Open leave balance")
    )
    limit = int((params.get("limit") or filters.extra.get("row_limit") or 200))
    qs = qs.select_related(
        "employee_id",
        "leave_type_id",
        "employee_id__employee_work_info",
        "employee_id__employee_work_info__department_id",
    ).order_by("-available_days")
    total = qs.count()
    if not total:
        return empty_drilldown(title, dimension, value)

    rows = []
    for al in qs[:limit]:
        emp = al.employee_id
        wi = getattr(emp, "employee_work_info", None)
        dept = getattr(wi, "department_id", None) if wi else None
        available = float(al.available_days or 0)
        carry = float(al.carryforward_days or 0)
        rows.append(
            {
                "employee": str(emp) if emp else "",
                "department": getattr(dept, "department", "") or "",
                "leave_type": getattr(al.leave_type_id, "name", "") or "",
                "available": round(available, 1),
                "carryforward": round(carry, 1),
                # The report's liability figure is available + carryforward,
                # so show the same total here.
                "total_days": round(available + carry, 1),
                "url": employee_link(getattr(emp, "id", None)),
            }
        )
    return drilldown_payload(
        title=title,
        dimension=dimension,
        value=value,
        columns=[
            {"key": "employee", "label": _("Employee")},
            {"key": "department", "label": _("Department")},
            {"key": "leave_type", "label": _("Leave type")},
            {"key": "available", "label": _("Available")},
            {"key": "carryforward", "label": _("Carried forward")},
            {"key": "total_days", "label": _("Open days")},
        ],
        rows=rows,
        truncated=total > len(rows),
    )


def overtime_analysis_drilldown(
    filters: ReportFilters, params: dict, request=None
) -> dict:
    """Overtime behind a department total.

    Named per-employee rows stay behind the same gate the report uses
    (report/metrics/_privacy.py): without it, drilling in would be a way to
    rebuild the named breakdown the report deliberately withholds.
    """
    from django.db.models import Sum as _Sum

    from attendance.models import Attendance
    from report.drilldown import (
        apply_subordinate_scope,
        drilldown_payload,
        employee_link,
        empty_drilldown,
    )
    from report.metrics._privacy import allow_named_ot_rows

    dimension = (params.get("dimension") or "department").strip().lower()
    value = (params.get("value") or "").strip()

    qs = Attendance.objects.filter(
        attendance_date__gte=filters.from_date,
        attendance_date__lte=filters.to_date,
        overtime_second__gt=0,
    )
    qs = apply_org_filters(
        qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
    )
    qs = apply_subordinate_scope(
        request, qs, perm="attendance.view_attendance", field="employee_id"
    )
    if value and dimension in ("department", "dept", "by_dept"):
        qs = qs.filter(employee_id__employee_work_info__department_id__department=value)
        dimension = "department"

    named = allow_named_ot_rows(filters)
    title = _("Overtime · %(dept)s") % {"dept": value} if value else _("Overtime")

    if not named:
        # Aggregate-only view: same shape, no identities.
        grouped = (
            qs.values("employee_id__employee_work_info__department_id__department")
            .annotate(seconds=_Sum("overtime_second"))
            .order_by("-seconds")
        )
        rows = [
            {
                "department": g[
                    "employee_id__employee_work_info__department_id__department"
                ]
                or str(_("Unassigned")),
                "ot_hours": round((g["seconds"] or 0) / 3600, 2),
            }
            for g in grouped
        ]
        if not rows:
            return empty_drilldown(title, dimension, value)
        return drilldown_payload(
            title=title,
            dimension=dimension,
            value=value,
            columns=[
                {"key": "department", "label": _("Department")},
                {"key": "ot_hours", "label": _("OT hours")},
            ],
            rows=rows,
            truncated=False,
        ) | {
            "message": _(
                "Department totals only. Named rows require the overtime "
                "permission and ?include_names=1."
            )
        }

    grouped = (
        qs.values(
            "employee_id",
            "employee_id__employee_first_name",
            "employee_id__employee_last_name",
            "employee_id__employee_work_info__department_id__department",
        )
        .annotate(seconds=_Sum("overtime_second"))
        .order_by("-seconds")
    )
    limit = int((params.get("limit") or filters.extra.get("row_limit") or 200))
    grouped = list(grouped)
    if not grouped:
        return empty_drilldown(title, dimension, value)
    rows = [
        {
            "employee": f"{g['employee_id__employee_first_name']} "
            f"{g['employee_id__employee_last_name'] or ''}".strip(),
            "department": g[
                "employee_id__employee_work_info__department_id__department"
            ]
            or "",
            "ot_hours": round((g["seconds"] or 0) / 3600, 2),
            "url": employee_link(g["employee_id"]),
        }
        for g in grouped[:limit]
    ]
    return drilldown_payload(
        title=title,
        dimension=dimension,
        value=value,
        columns=[
            {"key": "employee", "label": _("Employee")},
            {"key": "department", "label": _("Department")},
            {"key": "ot_hours", "label": _("OT hours")},
        ],
        rows=rows,
        truncated=len(grouped) > len(rows),
    )

"""Shared exit-date resolution for workforce turnover metrics."""

from __future__ import annotations

from datetime import date
from typing import Iterator

from django.apps import apps
from django.db.models import Q

from report.engine import ReportFilters, apply_org_filters


def iter_exits(
    filters: ReportFilters,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    """
    Return exits in the date window as ``{employee_id, exit_date, source}``.

    Priority when multiple sources exist for one employee: archived offboarding
    ``notice_period_ends`` → approved resignation ``planned_to_leave_on`` →
    inactive employee with ``contract_end_date`` (fallback).
    """
    start = from_date or filters.from_date
    end = to_date or filters.to_date
    by_emp: dict[int, dict] = {}

    for row in _offboarding_archived_exits(filters, start, end):
        by_emp[row["employee_id"]] = row

    for row in _resignation_exits(filters, start, end):
        by_emp.setdefault(row["employee_id"], row)

    for row in _inactive_contract_exits(filters, start, end):
        by_emp.setdefault(row["employee_id"], row)

    return sorted(by_emp.values(), key=lambda r: (r["exit_date"], r["employee_id"]))


def exits_in_period(
    filters: ReportFilters,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> int:
    return len(iter_exits(filters, from_date=from_date, to_date=to_date))


def _offboarding_archived_exits(
    filters: ReportFilters, start: date, end: date
) -> Iterator[dict]:
    if not apps.is_installed("offboarding"):
        return
    try:
        OffboardingEmployee = apps.get_model("offboarding", "OffboardingEmployee")
    except LookupError:
        return

    qs = OffboardingEmployee.objects.filter(
        stage_id__type="archived",
        notice_period_ends__gte=start,
        notice_period_ends__lte=end,
        notice_period_ends__isnull=False,
    ).select_related(
        "employee_id",
        "employee_id__employee_work_info",
        # Callers read work_info.department_id.department for their
        # breakdowns; without this that is a query per exit row.
        "employee_id__employee_work_info__department_id",
    )
    qs = apply_org_filters(
        qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
        apply_employment_status=False,
    )
    for row in qs.iterator():
        emp = row.employee_id
        if not emp or not row.notice_period_ends:
            continue
        yield {
            "employee_id": emp.id,
            "exit_date": row.notice_period_ends,
            "source": "offboarding_archived",
            "employee": emp,
        }


def _resignation_exits(
    filters: ReportFilters, start: date, end: date
) -> Iterator[dict]:
    if not apps.is_installed("offboarding"):
        return
    try:
        ResignationLetter = apps.get_model("offboarding", "ResignationLetter")
    except LookupError:
        return

    qs = ResignationLetter.objects.filter(
        status="approved",
        planned_to_leave_on__gte=start,
        planned_to_leave_on__lte=end,
        planned_to_leave_on__isnull=False,
    ).select_related(
        "employee_id",
        "employee_id__employee_work_info",
        # Callers read work_info.department_id.department for their
        # breakdowns; without this that is a query per exit row.
        "employee_id__employee_work_info__department_id",
    )
    qs = apply_org_filters(
        qs,
        filters,
        prefix="employee_id__employee_work_info",
        employee_prefix="employee_id",
        apply_employment_status=False,
    )
    for row in qs.iterator():
        emp = row.employee_id
        if not emp or not row.planned_to_leave_on:
            continue
        yield {
            "employee_id": emp.id,
            "exit_date": row.planned_to_leave_on,
            "source": "resignation_approved",
            "employee": emp,
        }


def _inactive_contract_exits(
    filters: ReportFilters, start: date, end: date
) -> Iterator[dict]:
    from employee.models import Employee

    qs = (
        Employee.objects.filter(is_active=False)
        .filter(
            Q(employee_work_info__contract_end_date__gte=start)
            & Q(employee_work_info__contract_end_date__lte=end)
        )
        .select_related(
            "employee_work_info",
            "employee_work_info__department_id",
        )
    )
    qs = apply_org_filters(
        qs,
        filters,
        prefix="employee_work_info",
        employee_prefix="",
        apply_employment_status=False,
    )
    for emp in qs.iterator():
        wi = getattr(emp, "employee_work_info", None)
        exit_date = getattr(wi, "contract_end_date", None) if wi else None
        if not exit_date:
            continue
        yield {
            "employee_id": emp.id,
            "exit_date": exit_date,
            "source": "inactive_contract_end",
            "employee": emp,
        }


# Human-readable labels for the exit sources iter_exits reports, so a
# drill-down row can say where the date came from rather than leaking the
# internal key.
EXIT_SOURCE_LABELS = {
    "offboarding_archived": "Offboarding (archived)",
    "resignation": "Resignation",
    "inactive_contract": "Contract ended (inactive)",
}


def exit_drilldown(
    filters: ReportFilters,
    params: dict,
    request=None,
    *,
    title: str,
    from_date: date | None = None,
    to_date: date | None = None,
    extra_filter=None,
) -> dict:
    """
    Shared "who exited?" drill-down over the same sources as iter_exits.

    Every exit-shaped report needs the identical row payload, so they share
    this instead of each rebuilding the source-priority merge (and each
    risking a different answer from the KPI above it).

    ``extra_filter`` is an optional predicate on the exit row, for reports
    that narrow the cohort further (90-day attrition, say).
    """
    from django.utils.translation import gettext as _

    from report.drilldown import (
        apply_subordinate_scope,
        drilldown_payload,
        employee_link,
        empty_drilldown,
    )

    dimension = (params.get("dimension") or "exit").strip().lower()
    value = (params.get("value") or "").strip()

    rows_in = iter_exits(filters, from_date=from_date, to_date=to_date)
    if extra_filter is not None:
        rows_in = [r for r in rows_in if extra_filter(r)]

    # A drill-down is a fresh query, so the subordinate scope has to be
    # re-applied here -- it is not inherited from the report above it.
    if request is not None and rows_in:
        from employee.models import Employee

        allowed = apply_subordinate_scope(
            request,
            Employee.objects.filter(id__in=[r["employee_id"] for r in rows_in]),
            perm="employee.view_employee",
            field="id",
        )
        allowed_ids = set(allowed.values_list("id", flat=True))
        rows_in = [r for r in rows_in if r["employee_id"] in allowed_ids]

    # Optional narrowing by the clicked dimension.
    if value:

        def _dept(row):
            emp = row.get("employee")
            wi = getattr(emp, "employee_work_info", None) if emp else None
            dept = getattr(wi, "department_id", None) if wi else None
            return getattr(dept, "department", None)

        if dimension in ("department", "dept", "by_dept"):
            rows_in = [r for r in rows_in if _dept(r) == value]
            dimension = "department"
        elif dimension in ("source",):
            rows_in = [r for r in rows_in if r.get("source") == value]
        elif dimension in ("month",):
            rows_in = [r for r in rows_in if r["exit_date"].strftime("%b %Y") == value]

    if not rows_in:
        return empty_drilldown(title, dimension, value)

    limit = int((params.get("limit") or filters.extra.get("row_limit") or 200))
    total = len(rows_in)
    rows = []
    for row in rows_in[:limit]:
        emp = row.get("employee")
        wi = getattr(emp, "employee_work_info", None) if emp else None
        dept = getattr(wi, "department_id", None) if wi else None
        joined = getattr(wi, "date_joining", None) if wi else None
        tenure = ""
        if joined and row.get("exit_date"):
            tenure = round((row["exit_date"] - joined).days / 365.25, 1)
        rows.append(
            {
                "employee": str(emp) if emp else f"#{row['employee_id']}",
                "department": getattr(dept, "department", "") or "",
                "exit_date": row["exit_date"].isoformat(),
                "tenure_years": tenure,
                "source": _(
                    EXIT_SOURCE_LABELS.get(row.get("source"), row.get("source") or "")
                ),
                "url": employee_link(row["employee_id"]),
            }
        )

    return drilldown_payload(
        title=title,
        dimension=dimension,
        value=value,
        columns=[
            {"key": "employee", "label": _("Employee")},
            {"key": "department", "label": _("Department")},
            {"key": "exit_date", "label": _("Exit date")},
            {"key": "tenure_years", "label": _("Tenure (years)")},
            {"key": "source", "label": _("Source")},
        ],
        rows=rows,
        truncated=total > len(rows),
    )
